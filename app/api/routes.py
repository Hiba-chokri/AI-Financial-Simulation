"""
API endpoints.

Thin HTTP layer: it validates input (via schemas), calls the existing engines
(Capex for cost, Lookup/ML for GDV), and returns JSON. No business logic lives
here -- it only orchestrates the same functions the scripts and Streamlit use.
"""
from functools import lru_cache
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.pagination import paginate
from app.api.schemas import (
    GDVMethod,
    PaginatedNeighborhoods,
    SimulationRequest,
    SimulationResponse,
)
from app.api.security import require_api_key
from app.engine.capex import (
    ProjectFinancialInputs,
    compute_returns,
    generate_financial_model,
)
from app.engine.currency import convert, rates_status
from app.engine.gdv import load_lookup, predict_price_per_m2, train_from_dataset
from app.ml import predict as ml_predict
from app.ml.config import MLConfig as _MLConfig

_ml_config = _MLConfig()

router = APIRouter()


@lru_cache(maxsize=1)
def _get_lookup():
    try:
        return load_lookup()
    except FileNotFoundError:
        return train_from_dataset()


@lru_cache(maxsize=1)
def _get_ml_bundle():
    try:
        return ml_predict.load_model()
    except FileNotFoundError:
        return None


@router.get(
    "/health",
    tags=["meta"],
    summary="Liveness and dependency status",
    response_description="Service status plus the state of its two live dependencies.",
)
def health() -> dict:
    """
    Public, no API key required — safe for load balancers and uptime monitors
    to poll freely.

    Returns three things:

    - **status** — always `"ok"` if this response was returned at all.
    - **ml_model_loaded** — whether the trained price-prediction model is in
      memory. `false` doesn't mean the service is broken: `/simulate` still
      works, it just falls back to the neighborhood lookup for GDV instead of
      the ML model.
    - **fx_rates_source** — how current the currency-conversion rates are:
        - `"live"` — fetched from the exchange-rate provider within the
          configured refresh window.
        - `"cached"` — the last live fetch failed, so a previously fetched
          rate is still being served (never blocks a request).
        - `"bootstrap"` — no live fetch has ever succeeded (no API key
          configured, or the provider was unreachable on startup); fixed
          fallback rates are in use.
    """
    return {
        "status": "ok",
        "ml_model_loaded": _get_ml_bundle() is not None,
        "fx_rates_source": rates_status()["source"],
    }


def _all_neighborhoods() -> list:
    """Every known location identifier, unpaginated (internal use only)."""
    bundle = _get_ml_bundle()
    if bundle and bundle.get("training_neighborhoods"):
        return sorted(bundle["training_neighborhoods"])
    # fallback: Casablanca lookup (if ML bundle not available)
    try:
        return sorted(_get_lookup()["neighborhoods"].keys())
    except Exception:
        return []


@router.get(
    "/neighborhoods",
    tags=["meta"],
    response_model=PaginatedNeighborhoods,
    dependencies=[Depends(require_api_key)],
    summary="List valid location identifiers",
    response_description="One page of location identifiers, plus pagination metadata.",
    responses={
        401: {"description": "Missing or invalid API key."},
        422: {"description": "page, page_size, or search failed validation."},
    },
)
def neighborhoods(
    page: int = Query(1, ge=1, description="Page number, 1-indexed"),
    page_size: int = Query(50, ge=1, le=500, description="Items per page (max 500)"),
    search: Optional[str] = Query(None, description="Case-insensitive substring filter"),
) -> PaginatedNeighborhoods:
    """
    Returns the location identifiers accepted by the `neighborhood` field on
    `POST /simulate` — sending a value not in this list still works (the GDV
    valuator falls back to a city-wide median), but a value that *is* listed
    here is guaranteed to have specific, calibrated pricing data behind it.

    **Paginated by design** — never assume the full list fits in one response,
    even though today's dataset is small enough that it would. Use `search`
    to jump straight to a known location instead of paging through everything.
    A `page` past the last one returns an empty `items` list, not an error —
    safe to keep incrementing `page` until `has_next` is `false`.
    """
    all_hoods = _all_neighborhoods()
    if search:
        needle = search.strip().lower()
        all_hoods = [h for h in all_hoods if needle in h.lower()]
    return PaginatedNeighborhoods(**paginate(all_hoods, page, page_size))


@router.post(
    "/simulate",
    response_model=SimulationResponse,
    tags=["valuation"],
    dependencies=[Depends(require_api_key)],
    summary="Run a full development valuation",
    response_description="Cost, revenue, and profit breakdown for the requested project.",
    responses={
        401: {"description": "Missing or invalid API key."},
        413: {"description": "Request body exceeds the configured size limit."},
        422: {"description": "One or more fields failed validation (see `detail` for which)."},
    },
)
def simulate(req: SimulationRequest) -> SimulationResponse:
    """
    Given a plot of land, autonomously designs a zoning-compliant building on
    it, prices the full construction cost, estimates what it will sell for,
    and returns the resulting profit — a complete developer pro-forma in one
    call.

    **What happens, in order:**

    1. **Cost (TDC — Total Development Cost).** A building is generated level
       by level (underground parking, ground floor, upper floors, penthouse)
       under the legal limits of `zone` — it never proposes a structure that
       exceeds the zone's floor-area or height caps. Each level is costed at
       the rate you supply. Soft costs (5 sub-lines), overheads, and
       contingency are added on top to produce the total.
    2. **Revenue (GDV → NDV).** `price_per_m2` comes from either the trained
       ML model or a neighborhood lookup table (`gdv_method` chooses which;
       see the fallback note below). GDV = sellable area × price/m² —
       underground parking is excluded, since it isn't sold at residential
       rates. NDV subtracts `selling_cost_pct` (agent fees, closing costs)
       to get the amount the developer actually nets.
    3. **Profit.** `net_profit_mad = NDV − TDC`, with `margin_pct` (profit ÷
       NDV) and `roi_pct` (profit ÷ TDC) alongside it.

    All monetary fields in the response are converted to whichever
    `currency` you requested (MAD, USD, or EUR) at current exchange rates —
    see `GET /health` to check whether those rates are live or cached.

    **ML fallback:** if `gdv_method="ml"` but no trained model is loaded, the
    request does **not** fail — it silently uses the neighborhood lookup
    instead, and the response's `gdv_method` field reports
    `"lookup (ml_unavailable)"` so you know which valuator actually priced it.
    """
    # --- Cost side (Submodel B) ---
    inputs = ProjectFinancialInputs(
        underground_parking_mad=req.underground_parking_mad,
        ground_floor_mad=req.ground_floor_mad,
        upper_floors_mad=req.upper_floors_mad,
        penthouse_mad=req.penthouse_mad,
        feasibility_pct=req.feasibility_pct,
        architecture_pct=req.architecture_pct,
        landscaping_env_pct=req.landscaping_env_pct,
        structural_pct=req.structural_pct,
        pm_marketing_pct=req.pm_marketing_pct,
        overheads_pct=req.overheads_pct,
        contingency_percentage=req.contingency_percentage,
        demolition_cost_mad=req.demolition_cost_mad,
    )
    cost = generate_financial_model(
        raw_plot_m2=req.plot_m2,
        land_price_mad=req.land_price_mad,
        zone=req.zone,
        inputs=inputs,
        requires_demolition=req.requires_demolition,
    )
    # --- Revenue side (Submodel C) ---
    actual_gdv_method = req.gdv_method.value
    bundle = _get_ml_bundle()

    if req.gdv_method == GDVMethod.ml and bundle is not None:
        cat_key = _ml_config.categorical_features[0]
        features = {cat_key: req.neighborhood}
        for feat in _ml_config.numeric_features:
            features[feat] = getattr(req.unit, feat)
        price_per_m2 = ml_predict.predict_price_per_m2(features, bundle)
    else:
        price_per_m2 = predict_price_per_m2(req.neighborhood, _get_lookup())
        if req.gdv_method == GDVMethod.ml:
            actual_gdv_method = "lookup (ml_unavailable)"

    # --- Bottom line (lives in capex.py) ---
    returns = compute_returns(cost, price_per_m2, req.selling_cost_pct)

    # --- Currency conversion ---
    cur = req.currency
    fx = lambda amt: convert(amt, cur)

    converted_details = [
        {**item, "cost_m2": fx(item["cost_m2"]), "total_mad": fx(item["total_mad"])}
        for item in cost["construction_details"]
    ]

    return SimulationResponse(
        currency=cur.value,
        total_investment_mad=fx(cost["TOTAL_NEEDED_INVESTMENT_MAD"]),
        construction_subtotal_mad=fx(cost["construction_subtotal_mad"]),
        total_built_surface_m2=cost["total_built_surface_m2"],
        construction_details=converted_details,
        gdv_method=actual_gdv_method,
        sellable_surface_m2=returns["sellable_m2"],
        price_per_m2=fx(price_per_m2),
        gdv_mad=fx(returns["gdv"]),
        ndv_mad=fx(returns["ndv"]),
        soft_costs_mad=fx(cost["other_costs"]["soft_costs_mad"]),
        overheads_mad=fx(cost["other_costs"]["overheads_mad"]),
        net_profit_mad=fx(returns["net_profit"]),
        margin_pct=returns["margin_pct"],
        roi_pct=returns["roi_pct"],
    )
