"""
Tests for the live exchange-rate fetch, cache, and fallback chain in
app/engine/currency.py.

Network calls are always mocked — these tests must never depend on internet
access or a real API key, and must be deterministic in CI.
"""
import httpx
import pytest

from app.engine import currency


@pytest.fixture(autouse=True)
def reset_currency_state(monkeypatch):
    """Every test starts from a clean, un-cached state with a fake API key,
    so config.EXCHANGE_RATE_API_KEY being unset locally can't hide bugs."""
    monkeypatch.setattr(currency.config, "EXCHANGE_RATE_API_KEY", "fake-test-key")
    monkeypatch.setattr(currency.config, "FX_REFRESH_SECONDS", 3600)
    currency._state = {
        "rates": dict(currency._BOOTSTRAP_RATES),
        "last_fetch_attempt": 0.0,
        "source": "bootstrap",
    }
    yield


def _mock_success(monkeypatch, usd: float, eur: float):
    def fake_get(url, timeout):
        return httpx.Response(
            200,
            json={"result": "success", "conversion_rates": {"USD": usd, "EUR": eur}},
            request=httpx.Request("GET", url),
        )
    monkeypatch.setattr(currency.httpx, "get", fake_get)


def _mock_failure(monkeypatch):
    def fake_get(url, timeout):
        raise httpx.ConnectError("simulated network failure")
    monkeypatch.setattr(currency.httpx, "get", fake_get)


# ── Live fetch success ─────────────────────────────────────────────────────────

def test_successful_fetch_updates_rates_and_source(monkeypatch):
    _mock_success(monkeypatch, usd=0.111, eur=0.101)
    rates = currency.get_rates()
    assert rates == {"MAD": 1.0, "USD": 0.111, "EUR": 0.101}
    assert currency.rates_status()["source"] == "live"


def test_convert_uses_the_live_rate(monkeypatch):
    _mock_success(monkeypatch, usd=0.2, eur=0.15)
    assert currency.convert(100.0, currency.Currency.USD) == pytest.approx(20.0)
    assert currency.convert(100.0, currency.Currency.EUR) == pytest.approx(15.0)
    assert currency.convert(100.0, currency.Currency.MAD) == pytest.approx(100.0)


# ── No API key configured ───────────────────────────────────────────────────────

def test_no_api_key_falls_back_to_bootstrap_rates(monkeypatch):
    monkeypatch.setattr(currency.config, "EXCHANGE_RATE_API_KEY", "")
    rates = currency.get_rates()
    assert rates == currency._BOOTSTRAP_RATES
    assert currency.rates_status()["source"] == "bootstrap"


# ── Live API unreachable ────────────────────────────────────────────────────────

def test_fetch_failure_on_cold_start_uses_bootstrap(monkeypatch):
    _mock_failure(monkeypatch)
    rates = currency.get_rates()
    assert rates == currency._BOOTSTRAP_RATES
    assert currency.rates_status()["source"] == "bootstrap"


def test_fetch_failure_after_a_prior_success_keeps_the_last_known_rate(monkeypatch):
    _mock_success(monkeypatch, usd=0.123, eur=0.113)
    first = currency.get_rates()
    assert first["USD"] == 0.123

    # force the cache to look stale, then simulate the provider going down
    currency._state["last_fetch_attempt"] = 0.0
    _mock_failure(monkeypatch)
    second = currency.get_rates()

    assert second == first                     # last known value preserved
    assert currency.rates_status()["source"] == "cached"


# ── Refresh cadence ──────────────────────────────────────────────────────────────

def test_fresh_cache_does_not_refetch(monkeypatch):
    calls = {"n": 0}

    def fake_get(url, timeout):
        calls["n"] += 1
        return httpx.Response(
            200, json={"result": "success", "conversion_rates": {"USD": 0.1, "EUR": 0.09}},
            request=httpx.Request("GET", url),
        )
    monkeypatch.setattr(currency.httpx, "get", fake_get)

    currency.get_rates()
    currency.get_rates()
    currency.get_rates()
    assert calls["n"] == 1  # only the first call was stale enough to fetch


def test_malformed_response_is_treated_as_a_failed_fetch(monkeypatch):
    def fake_get(url, timeout):
        return httpx.Response(200, json={"result": "error"}, request=httpx.Request("GET", url))
    monkeypatch.setattr(currency.httpx, "get", fake_get)

    rates = currency.get_rates()
    assert rates == currency._BOOTSTRAP_RATES
