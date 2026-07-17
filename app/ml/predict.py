"""
Stage 13 - Inference (with a graceful fallback chain).

`predict_price_per_m2` is the raw ML prediction. `predict_with_fallback` wraps it
with three safety checks and degrades to the neighborhood lookup table when the ML
answer can't be trusted:

  Tier 1  availability  -> ML model missing/unloadable         -> lookup
  Tier 2  coverage      -> location not in the ML training set  -> lookup
  Tier 3  plausibility  -> ML price outside a sane band         -> lookup
  (the lookup itself falls back to the city-wide median for unknown locations)

Every result reports its `source` and `confidence`, so nothing fails silently.

Dataset-agnostic: the categorical "location" column (zipcode, neighborhood, ...)
is read from MLConfig, so this file never needs editing when the dataset changes.
"""
from typing import Dict, Optional

import joblib
import pandas as pd

from .config import MLConfig


def load_model(path: Optional[str] = None) -> dict:
    """Load the model bundle saved by train.py."""
    return joblib.load(path or MLConfig().model_path)


def _location_key() -> str:
    """Name of the categorical location column for the active dataset (e.g. 'zipcode')."""
    cats = MLConfig().categorical_features
    return cats[0] if cats else ""


def predict_price_per_m2(features: Dict[str, object], bundle: Optional[dict] = None) -> float:
    """Predict price/m2 from a dict of feature values (missing ones -> imputed)."""
    bundle = bundle or load_model()
    row = {col: features.get(col) for col in bundle["features"]}
    X = pd.DataFrame([row])
    return float(bundle["pipeline"].predict(X)[0])


def _normalize(name: object) -> str:
    return str(name).strip().title()


def _lookup_result(location: str, lookup: dict, reason: str) -> Dict[str, object]:
    """Resolve a price from the lookup, labelling lookup vs city-median fallback."""
    by_lower = {str(k).strip().lower(): v for k, v in lookup["neighborhoods"].items()}
    key = str(location).strip().lower()
    if key in by_lower:
        return {"price_per_m2": float(by_lower[key]), "source": "lookup",
                "confidence": "medium", "reason": reason}
    return {"price_per_m2": float(lookup["city_median"]), "source": "city_median",
            "confidence": "low", "reason": f"{reason}; location unknown to lookup"}


def predict_with_fallback(
    features: Dict[str, object],
    lookup: Optional[dict] = None,
    bundle: Optional[dict] = None,
) -> Dict[str, object]:
    """
    Trust the ML model only when it's available, the location was in training,
    and the output is plausible; otherwise fall back to the lookup.
    Returns {price_per_m2, source, confidence, reason}.
    """
    if lookup is None:
        from app.engine.gdv import load_lookup
        lookup = load_lookup()
    location = _normalize(features.get(_location_key()))

    # Tier 1 - availability
    if bundle is None:
        try:
            bundle = load_model()
        except FileNotFoundError:
            return _lookup_result(location, lookup, "ML model unavailable")

    # Tier 2 - coverage
    trained = set(bundle.get("training_neighborhoods", []))
    if trained and location not in trained:
        return _lookup_result(location, lookup, f"'{location}' not in ML training set")

    # ML prediction
    price = predict_price_per_m2(features, bundle)

    # Tier 3 - plausibility (generous band around the training target range)
    lo = 0.5 * bundle.get("target_min", 0.0)
    hi = 1.5 * bundle.get("target_max", float("inf"))
    if not (lo <= price <= hi):
        return _lookup_result(
            location, lookup,
            f"ML price {price:,.0f} outside plausible band [{lo:,.0f}, {hi:,.0f}]",
        )

    return {"price_per_m2": price, "source": "ml", "confidence": "high",
            "reason": "ML in-coverage and plausible"}


def estimate_gdv(
    sellable_m2: float,
    features: Dict[str, object],
    bundle: Optional[dict] = None,
) -> float:
    """GDV = sellable (above-ground) area x predicted price/m2."""
    return sellable_m2 * predict_price_per_m2(features, bundle)


if __name__ == "__main__":
    # Demo the fallback chain across every location the ML model was trained on,
    # plus one fake location to trigger the deepest (city-median) fallback.
    bundle = load_model()
    loc_key = _location_key()

    # A representative unit: median-ish values for the numeric features.
    base = {"bedrooms": 3, "bathrooms": 2.0, "floors": 1.0, "waterfront": 0,
            "view": 0, "condition": 3, "grade": 7, "sqft_above": 1500,
            "sqft_basement": 0, "yr_built": 1990, "sqft_living15": 1500}

    trained = sorted(bundle.get("training_neighborhoods", []))
    lo = 0.5 * bundle.get("target_min", 0.0)
    hi = 1.5 * bundle.get("target_max", 0.0)
    print("=== GDV FALLBACK REPORT ===")
    print(f"Location column: '{loc_key}'")
    print(f"ML training locations: {len(trained)}")
    print(f"Plausible price band: [{lo:,.0f}, {hi:,.0f}] price/m2\n")
    print(f"{'Location':<18}{'Source':<14}{'Conf':<8}{'Price/m2':>10}   Reason")
    print("-" * 90)

    test_locations = trained[:10] + ["Nowhere-Ville"]
    counts: Dict[str, int] = {}
    for loc in test_locations:
        r = predict_with_fallback({**base, loc_key: loc}, bundle=bundle)
        counts[r["source"]] = counts.get(r["source"], 0) + 1
        print(f"{loc:<18}{r['source']:<14}{r['confidence']:<8}"
              f"{r['price_per_m2']:>10,.0f}   {r['reason']}")

    print("-" * 90)
    print("Summary by source:", {k: counts[k] for k in sorted(counts)})
