"""
Submodel C: GDV (Gross Development Value) valuation.

The Casablanca dataset collapses to ~17 unique price points across 12 neighborhoods
(each row duplicated ~187x), so a learned regressor (XGBoost/RandomForest) is not
statistically justified -- it would only memorize and leak across a train/test split.

Instead this builds an honest, transparent **price-per-m2 lookup table**: the median
MAD/m2 per neighborhood, with a city-wide median fallback for unseen neighborhoods.
The public interface (`estimate_gdv`) is intentionally identical to what a real model
would expose, so the internals can be swapped for ML once Phase 2 brings real data.

Note: `type` (Studio/Appartement/Bureau) is intentionally excluded -- in this data it is
confounded with unit size (small studios inflate MAD/m2), which would bias a development
valuation. Neighborhood is the stable signal we trust.
"""
import json
import os
from typing import Dict, Optional

import pandas as pd

from app.scraper.cleaner import ingest_kaggle_dataset, prepare_features

LOOKUP_PATH: str = "data/models/gdv_price_per_m2.json"


def _normalize_neighborhood(name: str) -> str:
    """Match the cleaning applied during ingestion (strip + Title Case)."""
    return str(name).strip().title()


def build_price_lookup(df: pd.DataFrame) -> Dict[str, object]:
    """
    Builds the price-per-m2 lookup from model-ready features.
    Returns {"neighborhoods": {name: median_ppm2}, "city_median": float, "n_points": int}.
    """
    by_hood = df.groupby("nighberd")["price_per_m2"].median()
    lookup: Dict[str, object] = {
        "neighborhoods": {k: round(float(v), 2) for k, v in by_hood.items()},
        "city_median": round(float(df["price_per_m2"].median()), 2),
        "n_points": int(df.drop_duplicates(subset=["nighberd", "price_per_m2"]).shape[0]),
    }
    return lookup


def save_lookup(lookup: Dict[str, object], path: str = LOOKUP_PATH) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(lookup, fh, ensure_ascii=False, indent=2)
    print(f"Saved GDV price/m2 lookup -> {path}")


def load_lookup(path: str = LOOKUP_PATH) -> Dict[str, object]:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def predict_price_per_m2(neighborhood: str, lookup: Optional[Dict[str, object]] = None) -> float:
    """
    Returns the resale-proxy MAD/m2 for a neighborhood, falling back to the
    city-wide median when the neighborhood is unknown.
    """
    if lookup is None:
        lookup = load_lookup()
    hoods: Dict[str, float] = lookup["neighborhoods"]
    key = _normalize_neighborhood(neighborhood)
    if key in hoods:
        return float(hoods[key])
    print(f"[GDV] Neighborhood '{neighborhood}' not in lookup -> using city median.")
    return float(lookup["city_median"])


def estimate_gdv(
    sellable_m2: float,
    neighborhood: str,
    lookup: Optional[Dict[str, object]] = None,
) -> float:
    """
    GDV = sellable (above-ground) built area x resale-proxy MAD/m2.
    `sellable_m2` must EXCLUDE underground parking (parking != residential MAD/m2);
    valuation.py is responsible for stripping it from the Capex output.
    """
    return sellable_m2 * predict_price_per_m2(neighborhood, lookup)


def train_from_dataset(csv_path: str = "data/raw/Housing_data.csv") -> Dict[str, object]:
    """Loads + cleans the dataset, builds the lookup, and persists it."""
    df = ingest_kaggle_dataset(csv_path)
    if df is None:
        raise RuntimeError(f"Could not load dataset at {csv_path}")
    features = prepare_features(df)
    lookup = build_price_lookup(features)
    save_lookup(lookup)
    return lookup


if __name__ == "__main__":
    lookup = train_from_dataset()

    print("\n--- GDV PRICE/m2 LOOKUP (Submodel C) ---")
    print(f"City-wide median fallback: {lookup['city_median']:,.0f} MAD/m2")
    print(f"Neighborhoods covered: {len(lookup['neighborhoods'])} "
          f"(built from {lookup['n_points']} unique price points)")
    for hood, ppm2 in sorted(lookup["neighborhoods"].items(),
                             key=lambda kv: kv[1], reverse=True):
        print(f"  {hood:<18} {ppm2:>12,.0f} MAD/m2")

    # Sanity demo: value a 600 m2 sellable build in Belvédère vs an unknown hood.
    print("\n--- Sanity check ---")
    for hood in ["Belvédère", "Riviera", "Nowhere-Ville"]:
        gdv = estimate_gdv(600.0, hood, lookup)
        print(f"  600 m2 sellable in {hood:<14} -> GDV {gdv:,.0f} MAD")
