"""
Stage 3+5 - Cleaning & feature engineering (config-driven).

Filters rows, coerces types, maps Yes/No booleans, derives the target
(price_per_m2), clips target outliers, selects the modelling columns, and
optionally deduplicates. Every column it touches comes from the config, so a
new dataset/feature is handled by editing config.py, not this file.

Note on scaling/encoding: those live in pipeline.py (fit on TRAIN only) to avoid
leakage -- they are deliberately NOT done here.
"""
import pandas as pd

from .config import MLConfig


def _coerce_numeric(df: pd.DataFrame, cols) -> pd.DataFrame:
    for c in cols:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def build_features(df: pd.DataFrame, config: MLConfig) -> pd.DataFrame:
    """Raw DataFrame -> clean, model-ready table (features + target)."""
    df = df.copy()

    # 1. Row filters (e.g. city == Casablanca)
    for col, value in config.filters.items():
        df[col] = df[col].astype(str).str.strip().str.title()
        df = df[df[col] == value]

    # 2. Boolean features -> 1/0.  Handles: yes/no, true/false, 1/0 (text or int).
    _BOOL_MAP = {"yes": 1.0, "no": 0.0, "true": 1.0, "false": 0.0, "1": 1.0, "0": 0.0}
    for col in config.boolean_features:
        df[col] = df[col].astype(str).str.strip().str.lower().map(_BOOL_MAP)

    # 3. Numeric coercion (non-boolean numerics + the target's source columns)
    numeric_to_coerce = [c for c in config.numeric_features if c not in config.boolean_features]
    df = _coerce_numeric(df, numeric_to_coerce + [config.price_col, config.area_col])

    # 4. Derive the target: price per m2
    df = df.dropna(subset=[config.price_col, config.area_col])
    df = df[(df[config.area_col] > 0) & (df[config.price_col] > 0)]
    df[config.target] = df[config.price_col] / df[config.area_col]

    # 5. Clip target outliers (mistyped listings shouldn't drag the model)
    lo, hi = df[config.target].quantile(list(config.outlier_quantiles))
    df = df[(df[config.target] >= lo) & (df[config.target] <= hi)]

    # 6. Cast categorical columns to str so numeric-valued categories (e.g. zipcode)
    #    are treated as labels, not numbers, by OneHotEncoder.
    for col in config.categorical_features:
        if col in df.columns:
            df[col] = df[col].astype(str)

    # 7. Keep only modelling columns
    df = df[config.all_features + [config.target]].reset_index(drop=True)

    # 8. Deduplicate BEFORE the split (prevents train/test leakage)
    if config.deduplicate:
        before = len(df)
        df = df.drop_duplicates().reset_index(drop=True)
        df.attrs["dedup_dropped"] = before - len(df)
        df.attrs["rows_before_dedup"] = before

    return df
