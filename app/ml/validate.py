"""
Stage 2 - Data-contract validation.

Runs immediately after ingestion: if a new dataset is missing required columns
or is empty, we fail LOUD and early instead of producing a silently-wrong model.
Kept dependency-free (plain checks); swap in Pandera/Great Expectations later if
you want richer contracts.
"""
import pandas as pd

from .config import MLConfig


class DataContractError(Exception):
    """Raised when an incoming dataset violates the expected schema."""


def validate_raw(df: pd.DataFrame, config: MLConfig) -> None:
    """Assert the raw DataFrame satisfies the minimum contract for this config."""
    if df is None or df.empty:
        raise DataContractError("Dataset is empty or could not be loaded.")

    missing = [c for c in config.required_columns if c not in df.columns]
    if missing:
        raise DataContractError(
            f"Dataset is missing required columns: {missing}. "
            f"Present columns: {list(df.columns)}"
        )
