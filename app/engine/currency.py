"""
Currency conversion for API outputs.

All internal engines compute in MAD; this module converts to whichever
currency the caller requested. Rates are fetched LIVE from exchangerate-api.com
and cached for `config.FX_REFRESH_SECONDS` (default 6h) — exchange rates drift
over time, so a rate hardcoded once in source code would silently go stale.

Resilience: if the live API is unreachable, the LAST successfully fetched rate
keeps being served (never fails a request just because the FX provider hiccuped).
The one exception is process cold-start: if the very first fetch attempt fails
(e.g. no network, no API key configured yet), there is no "last known" rate to
fall back to, so `_BOOTSTRAP_RATES` seeds the cache. That seed is overwritten by
the live API the moment a fetch succeeds and is never consulted again after that.
"""
import threading
import time
from enum import Enum
from typing import Dict, Optional

import httpx

from app.core import config


class Currency(str, Enum):
    MAD = "MAD"
    USD = "USD"
    EUR = "EUR"


# Bootstrap-only seed — see module docstring. Not "the" exchange rate, just
# what keeps the service answering if live rates were never reachable.
_BOOTSTRAP_RATES: Dict[str, float] = {
    "MAD": 1.0,
    "USD": 0.099,
    "EUR": 0.091,
}

_FETCH_TIMEOUT_SECONDS = 5.0
_RETRY_BACKOFF_SECONDS = 60  # a failed fetch retries in 1 min, not a full 6h cycle

_lock = threading.Lock()
_state = {
    "rates": dict(_BOOTSTRAP_RATES),
    "last_fetch_attempt": 0.0,
    "source": "bootstrap",  # "bootstrap" | "live" | "cached" (live, but a refresh just failed)
}


def _fetch_live_rates() -> Optional[Dict[str, float]]:
    """One HTTP call to exchangerate-api.com. Returns None on any failure."""
    if not config.EXCHANGE_RATE_API_KEY:
        return None
    url = f"https://v6.exchangerate-api.com/v6/{config.EXCHANGE_RATE_API_KEY}/latest/MAD"
    try:
        resp = httpx.get(url, timeout=_FETCH_TIMEOUT_SECONDS)
        resp.raise_for_status()
        data = resp.json()
        if data.get("result") != "success":
            return None
        rates = data["conversion_rates"]
        return {"MAD": 1.0, "USD": float(rates["USD"]), "EUR": float(rates["EUR"])}
    except (httpx.HTTPError, KeyError, ValueError):
        return None


def _refresh_if_stale() -> None:
    now = time.monotonic()
    with _lock:
        if (now - _state["last_fetch_attempt"]) < config.FX_REFRESH_SECONDS:
            return

    fresh = _fetch_live_rates()
    with _lock:
        if fresh is not None:
            _state["rates"] = fresh
            _state["last_fetch_attempt"] = now
            _state["source"] = "live"
        else:
            # Keep serving whatever we already had; retry sooner than a full
            # cycle so a transient outage self-heals quickly.
            _state["last_fetch_attempt"] = now - config.FX_REFRESH_SECONDS + _RETRY_BACKOFF_SECONDS
            if _state["source"] == "live":
                _state["source"] = "cached"


def get_rates() -> Dict[str, float]:
    """Current MAD-based rates: live if the cache isn't stale, else the last
    known value (refreshed lazily — see module docstring for the fallback chain)."""
    _refresh_if_stale()
    with _lock:
        return dict(_state["rates"])


def rates_status() -> Dict[str, object]:
    """For observability (e.g. GET /health) — is conversion using live data?"""
    with _lock:
        return {"source": _state["source"], "rates": dict(_state["rates"])}


def convert(amount_mad: float, to: Currency) -> float:
    """Convert a MAD amount to the target currency using the current rate."""
    return amount_mad * get_rates()[to.value]
