"""
Tests for GET /api/v1/neighborhoods pagination — both the generic slicing
helper (app/api/pagination.py) and the endpoint wiring on top of it.
"""
import pytest

from app.api.pagination import paginate

NEIGHBORHOODS = "/api/v1/neighborhoods"


# ── paginate() — pure slicing logic, no HTTP involved ──────────────────────────

def test_paginate_first_page():
    items = [f"h{i}" for i in range(10)]
    page = paginate(items, page=1, page_size=4)
    assert page["items"] == ["h0", "h1", "h2", "h3"]
    assert page["total"] == 10
    assert page["total_pages"] == 3
    assert page["has_next"] is True
    assert page["has_previous"] is False


def test_paginate_last_partial_page():
    items = [f"h{i}" for i in range(10)]
    page = paginate(items, page=3, page_size=4)
    assert page["items"] == ["h8", "h9"]
    assert page["has_next"] is False
    assert page["has_previous"] is True


def test_paginate_past_the_end_is_empty_not_an_error():
    items = [f"h{i}" for i in range(10)]
    page = paginate(items, page=99, page_size=4)
    assert page["items"] == []
    assert page["has_next"] is False
    assert page["has_previous"] is True


def test_paginate_empty_collection():
    page = paginate([], page=1, page_size=50)
    assert page["items"] == []
    assert page["total"] == 0
    assert page["total_pages"] == 1
    assert page["has_next"] is False
    assert page["has_previous"] is False


# ── /neighborhoods endpoint ────────────────────────────────────────────────────

def test_neighborhoods_default_page_is_well_formed(client, auth_headers):
    r = client.get(NEIGHBORHOODS, headers=auth_headers)
    assert r.status_code == 200
    d = r.json()
    assert set(d.keys()) == {
        "items", "total", "page", "page_size",
        "total_pages", "has_next", "has_previous",
    }
    assert d["page"] == 1
    assert d["page_size"] == 50
    assert len(d["items"]) <= d["page_size"]
    assert len(d["items"]) <= d["total"]


def test_neighborhoods_page_size_is_respected(client, auth_headers):
    r = client.get(NEIGHBORHOODS, params={"page_size": 5}, headers=auth_headers)
    d = r.json()
    assert len(d["items"]) <= 5
    assert d["page_size"] == 5


def test_neighborhoods_page_size_cap_is_enforced(client, auth_headers):
    r = client.get(NEIGHBORHOODS, params={"page_size": 10_000}, headers=auth_headers)
    assert r.status_code == 422  # le=500 violated


def test_neighborhoods_page_zero_is_rejected(client, auth_headers):
    r = client.get(NEIGHBORHOODS, params={"page": 0}, headers=auth_headers)
    assert r.status_code == 422  # ge=1 violated


def test_neighborhoods_far_page_returns_empty_list_cleanly(client, auth_headers):
    r = client.get(NEIGHBORHOODS, params={"page": 999_999}, headers=auth_headers)
    assert r.status_code == 200
    d = r.json()
    assert d["items"] == []
    assert d["has_next"] is False


def test_neighborhoods_pages_do_not_overlap(client, auth_headers):
    p1 = client.get(NEIGHBORHOODS, params={"page": 1, "page_size": 5}, headers=auth_headers).json()
    p2 = client.get(NEIGHBORHOODS, params={"page": 2, "page_size": 5}, headers=auth_headers).json()
    if p1["total"] > 5:
        assert set(p1["items"]).isdisjoint(p2["items"])


def test_neighborhoods_search_filters_results(client, auth_headers):
    unfiltered = client.get(NEIGHBORHOODS, params={"page_size": 500}, headers=auth_headers).json()
    if unfiltered["total"] == 0:
        pytest.skip("no GDV source available on this machine")
    sample = unfiltered["items"][0]
    needle = sample[:2]

    filtered = client.get(NEIGHBORHOODS, params={"search": needle, "page_size": 500},
                          headers=auth_headers).json()
    assert all(needle.lower() in item.lower() for item in filtered["items"])
    assert filtered["total"] <= unfiltered["total"]


def test_neighborhoods_search_with_no_match_returns_empty(client, auth_headers):
    r = client.get(NEIGHBORHOODS, params={"search": "zzz-does-not-exist-zzz"},
                   headers=auth_headers)
    assert r.status_code == 200
    d = r.json()
    assert d["items"] == []
    assert d["total"] == 0


def test_neighborhoods_still_requires_api_key(client):
    assert client.get(NEIGHBORHOODS).status_code == 401
