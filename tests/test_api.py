"""
Smoke tests for the HTTP layer — focused on the security contract.

The auth tests are artifact-free. The one end-to-end success test needs a GDV
source (the gitignored lookup JSON or trained model); it skips cleanly if neither
is present on the machine running the tests.
"""
import os

import pytest

LOOKUP_PATH = "data/models/gdv_price_per_m2.json"
MODEL_PATH = "data/models/kc_pipeline.joblib"

SIMULATE = "/api/v1/simulate"
BASE_REQUEST = {
    "plot_m2": 500,
    "land_price_mad": 4_500_000,
    "zone": "zone_e",
    "neighborhood": "Riviera",
    "gdv_method": "lookup",
    "currency": "MAD",
}


def test_health_is_public(client):
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_simulate_without_key_is_rejected(client):
    assert client.post(SIMULATE, json=BASE_REQUEST).status_code == 401


def test_simulate_with_wrong_key_is_rejected(client):
    r = client.post(SIMULATE, json=BASE_REQUEST, headers={"X-API-Key": "nope"})
    assert r.status_code == 401


def test_neighborhoods_requires_key(client, auth_headers):
    assert client.get("/api/v1/neighborhoods").status_code == 401
    assert client.get("/api/v1/neighborhoods", headers=auth_headers).status_code == 200


def test_security_headers_present(client):
    h = client.get("/api/v1/health").headers
    assert h.get("x-content-type-options") == "nosniff"
    assert h.get("x-frame-options") == "DENY"
    assert h.get("referrer-policy") == "no-referrer"


@pytest.mark.skipif(
    not (os.path.exists(LOOKUP_PATH) or os.path.exists(MODEL_PATH)),
    reason="No GDV artifact (lookup JSON / trained model) available on this machine.",
)
def test_simulate_with_valid_key_returns_full_breakdown(client, auth_headers):
    r = client.post(SIMULATE, json=BASE_REQUEST, headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    for field in (
        "total_investment_mad",
        "gdv_mad",
        "ndv_mad",
        "soft_costs_mad",
        "overheads_mad",
        "net_profit_mad",
        "margin_pct",
        "roi_pct",
        "currency",
    ):
        assert field in body
    assert body["currency"] == "MAD"
    assert body["ndv_mad"] <= body["gdv_mad"]
