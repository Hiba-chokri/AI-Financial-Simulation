"""
Stage 1 - Ingestion.

Source-abstracted: today it reads a CSV, but the rest of the pipeline only sees
a standardized DataFrame, so a future scraper/DB/API loader can drop in here
without changing anything downstream.
"""
import pandas as pd


def load_raw(csv_path: str) -> pd.DataFrame:
    """Load a raw CSV and standardize column names (lowercase, underscores)."""
    df = pd.read_csv(csv_path)
    df.columns = df.columns.str.lower().str.replace(" ", "_")
    return df


if __name__ == "__main__":
    # review of the dataset 
    from .config import MLConfig

    df = load_raw(MLConfig().csv_path)
    print(f"\nDataset: {MLConfig().csv_path}")
    print(f"Shape: {df.shape[0]:,} rows x {df.shape[1]} columns\n")
    print(df.head(10).to_string())
