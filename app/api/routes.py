"""
API endpoints.

Thin HTTP layer: it validates input (via schemas), calls the existing engines
(Capex for cost, Lookup/ML for GDV), and returns JSON. No business logic lives
here -- it only orchestrates the same functions the scripts and Streamlit use.
"""
from functools import lru_cache
from typing import List

from fastapi import APIRouter, Depends, HTTPException

from app.api.schemas import GDVMethod, SimulationRequest, SimulationResponse
from app.api.security import require_api_key
from app.engine.capex import (
    ProjectFinancialInputs,
    compute_returns,
    generate_financial_model,
)
from app.engine.currency import convert
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


@router.get("/health", tags=["meta"])
def health() -> dict:
    return {"status": "ok", "ml_model_loaded": _get_ml_bundle() is not None}


@router.get("/neighborhoods", tags=["meta"], dependencies=[Depends(require_api_key)])
def neighborhoods() -> List[str]:
    """Returns the location identifiers the ML model was trained on."""
    bundle = _get_ml_bundle()
    if bundle and bundle.get("training_neighborhoods"):
        return sorted(bundle["training_neighborhoods"])
    # fallback: Casablanca lookup (if ML bundle not available)
    try:
        return sorted(_get_lookup()["neighborhoods"].keys())
    except Exception:
        return []


@router.post(
    "/simulate",
    response_model=SimulationResponse,
    tags=["valuation"],
    dependencies=[Depends(require_api_key)],
)
def simulate(req: SimulationRequest) -> SimulationResponse:
    """Full project valuation: cost (Capex) + GDV + profit."""
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
