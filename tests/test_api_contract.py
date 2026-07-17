"""
Request/response contract tests for /api/v1/simulate — what an integrating
platform (e.g. Daba.Cities) codes against.

Auth is exercised in test_api.py; here every request carries a valid key so we
can focus on validation, the response schema, currency math, fallbacks, and
API-vs-engine consistency. Tests that need the gitignored lookup artifact skip
cleanly when it's absent.
"""
import os

import pytest

from app.engine.currency import RATES_FROM_MAD

LOOKUP_PATH = "data/models/gdv_price_per_m2.json"
MODEL_PATH = "data/models/kc_pipeline.joblib"
SIMULATE = "/api/v1/simulate"

needs_lookup = pytest.mark.skipif(
    not os.path.exists(LOOKUP_PATH), reason="lookup artifact not present"
)
needs_model = pytest.mark.skipif(
    not os.path.exists(MODEL_PATH), reason="trained ML model not present"
)

BASE = {
    "plot_m2": 500,
    "land_price_mad": 4_500_000,
    "zone": "zone_e",
    "neighborhood": "Riviera",
    "gdv_method": "lookup",
    "currency": "MAD",
}

RESPONSE_FIELDS = {
    "currency", "total_investment_mad", "construction_subtotal_mad",
    "total_built_surface_m2", "construction_details", "gdv_method",
    "sellable_surface_m2", "price_per_m2", "gdv_mad", "ndv_mad",
    "soft_costs_mad", "overheads_mad", "net_profit_mad", "margin_pct", "roi_pct",
}


# ── Input validation (422s must fire before any engine code runs) ─────────────

@pytest.mark.parametrize("overrides", [
    {"plot_m2": -50},                     # gt=0 violated
    {"plot_m2": 0},
    {"land_price_mad": -1},               # ge=0 violated
    {"zone": "zone_z"},                   # unknown enum member
    {"currency": "GBP"},                  # unsupported currency
    {"gdv_method": "magic"},              # unknown valuator
    {"feasibility_pct": 1.5},             # le=1 violated
    {"contingency_percentage": -0.1},     # ge=0 violated
])
def test_invalid_input_is_rejected_with_422(client, auth_headers, overrides):
    r = client.post(SIMULATE, json={**BASE, **overrides}, headers=auth_headers)
    assert r.status_code == 422


@pytest.mark.parametrize("missing", ["plot_m2", "land_price_mad", "zone", "neighborhood"])
def test_missing_required_field_is_rejected(client, auth_headers, missing):
    body = {k: v for k, v in BASE.items() if k != missing}
    r = client.post(SIMULATE, json=body, headers=auth_headers)
    assert r.status_code == 422


def test_validation_error_names_the_offending_field(client, auth_headers):
    r = client.post(SIMULATE, json={**BASE, "plot_m2": -50}, headers=auth_headers)
    assert "plot_m2" in str(r.json()["detail"])


# ── Response schema ───────────────────────────────────────────────────────────

@needs_lookup
def test_response_contains_every_contract_field(client, auth_headers):
    r = client.post(SIMULATE, json=BASE, headers=auth_headers)
    assert r.status_code == 200
    assert set(r.json().keys()) == RESPONSE_FIELDS


@needs_lookup
def test_construction_details_items_are_well_formed(client, auth_headers):
    details = client.post(SIMULATE, json=BASE, headers=auth_headers).json()["construction_details"]
    assert len(details) > 0
    for item in details:
        assert set(item.keys()) == {"level", "surface_m2", "cost_m2", "total_mad"}
        assert item["surface_m2"] > 0
        assert item["total_mad"] == pytest.approx(item["surface_m2"] * item["cost_m2"], rel=1e-6)


@needs_lookup
def test_minimal_request_works_with_defaults(client, auth_headers):
    """Only the 4 required fields — every optional field must default sensibly."""
    minimal = {"plot_m2": 500, "land_price_mad": 4_500_000,
               "zone": "zone_e", "neighborhood": "Riviera", "gdv_method": "lookup"}
    r = client.post(SIMULATE, json=minimal, headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["currency"] == "USD"   # documented default output currency


# ── Financial coherence of the response ───────────────────────────────────────

@needs_lookup
def test_response_numbers_are_internally_consistent(client, auth_headers):
    d = client.post(SIMULATE, json=BASE, headers=auth_headers).json()
    # NDV = GDV * (1 - default 1% selling cost)
    assert d["ndv_mad"] == pytest.approx(d["gdv_mad"] * 0.99, rel=1e-9)
    # net profit = NDV - TDC
    assert d["net_profit_mad"] == pytest.approx(d["ndv_mad"] - d["total_investment_mad"], rel=1e-9)
    # margin = net / NDV, ROI = net / TDC (both as %)
    assert d["margin_pct"] == pytest.approx(d["net_profit_mad"] / d["ndv_mad"] * 100, rel=1e-6)
    assert d["roi_pct"] == pytest.approx(d["net_profit_mad"] / d["total_investment_mad"] * 100, rel=1e-6)
    # GDV = sellable area x price/m2
    assert d["gdv_mad"] == pytest.approx(d["sellable_surface_m2"] * d["price_per_m2"], rel=1e-9)


@needs_lookup
def test_api_matches_direct_engine_call(client, auth_headers):
    """The HTTP layer must add nothing and lose nothing vs calling the engine."""
    from app.engine.capex import ProjectFinancialInputs, compute_returns, generate_financial_model
    from app.engine.gdv import load_lookup, predict_price_per_m2
    from app.engine.matrix import ZoningCategory

    d = client.post(SIMULATE, json=BASE, headers=auth_headers).json()

    inputs = ProjectFinancialInputs(
        underground_parking_mad=3500.0, ground_floor_mad=4500.0,
        upper_floors_mad=4300.0, penthouse_mad=5000.0, demolition_cost_mad=150_000.0,
    )
    cost = generate_financial_model(500.0, 4_500_000.0,
                                    ZoningCategory.ZONE_E_COMMERCIAL, inputs, True)
    price = predict_price_per_m2("Riviera", load_lookup())
    returns = compute_returns(cost, price)

    assert d["total_investment_mad"] == pytest.approx(cost["TOTAL_NEEDED_INVESTMENT_MAD"])
    assert d["price_per_m2"] == pytest.approx(price)
    assert d["gdv_mad"] == pytest.approx(returns["gdv"])
    assert d["ndv_mad"] == pytest.approx(returns["ndv"])
    assert d["net_profit_mad"] == pytest.approx(returns["net_profit"])


# ── Currency conversion ───────────────────────────────────────────────────────

@needs_lookup
@pytest.mark.parametrize("code", ["USD", "EUR"])
def test_currency_converts_every_monetary_field(client, auth_headers, code):
    mad = client.post(SIMULATE, json={**BASE, "currency": "MAD"}, headers=auth_headers).json()
    conv = client.post(SIMULATE, json={**BASE, "currency": code}, headers=auth_headers).json()
    rate = RATES_FROM_MAD[code]

    for field in ["total_investment_mad", "construction_subtotal_mad", "price_per_m2",
                  "gdv_mad", "ndv_mad", "soft_costs_mad", "overheads_mad", "net_profit_mad"]:
        assert conv[field] == pytest.approx(mad[field] * rate, rel=1e-9), field
    # dimensionless / physical fields must NOT be converted
    assert conv["margin_pct"] == pytest.approx(mad["margin_pct"], rel=1e-9)
    assert conv["roi_pct"] == pytest.approx(mad["roi_pct"], rel=1e-9)
    assert conv["sellable_surface_m2"] == mad["sellable_surface_m2"]
    assert conv["total_built_surface_m2"] == mad["total_built_surface_m2"]
    assert conv["currency"] == code


# ── Fallback behavior ─────────────────────────────────────────────────────────

@needs_lookup
def test_unknown_neighborhood_falls_back_to_city_median(client, auth_headers):
    import json
    city_median = json.load(open(LOOKUP_PATH))["city_median"]
    r = client.post(SIMULATE, json={**BASE, "neighborhood": "Nowhere-Ville"},
                    headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["price_per_m2"] == pytest.approx(city_median)


@needs_lookup
def test_ml_method_silently_falls_back_when_model_missing(client, auth_headers, monkeypatch):
    """gdv_method=ml with no model must NOT 503 — it degrades to the lookup and
    labels the response so the caller knows."""
    from app.api import routes
    monkeypatch.setattr(routes, "_get_ml_bundle", lambda: None)
    r = client.post(SIMULATE, json={**BASE, "gdv_method": "ml"}, headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["gdv_method"] == "lookup (ml_unavailable)"


@needs_model
def test_ml_method_uses_ml_when_model_present(client, auth_headers):
    r = client.post(SIMULATE, json={**BASE, "gdv_method": "ml", "neighborhood": "98052"},
                    headers=auth_headers)
    assert r.status_code == 200
    d = r.json()
    assert d["gdv_method"] == "ml"
    assert d["price_per_m2"] > 0


# ── Hardening ─────────────────────────────────────────────────────────────────

def test_oversized_body_is_rejected_with_413(client, auth_headers):
    r = client.post(SIMULATE, json=BASE,
                    headers={**auth_headers, "Content-Length": "9999999"})
    assert r.status_code == 413
