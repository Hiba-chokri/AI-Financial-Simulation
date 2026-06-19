import pandas as pd
from typing import Optional

# --- Feature contract for Submodel C (GDV) ---
# Shared so the model trainer and the inference path agree on columns.
TARGET: str = "price_per_m2"
CATEGORICAL_FEATURES: list[str] = ["nighberd", "type"]
NUMERIC_FEATURES: list[str] = [
    "chambres", "salles_de_bains", "floor", "ascenseur", "terrasse", "parking"
]
FEATURE_COLUMNS: list[str] = CATEGORICAL_FEATURES + NUMERIC_FEATURES

# Yes/No string columns to coerce into 1/0 booleans.
_BOOLEAN_COLUMNS: list[str] = ["ascenseur", "terrasse", "parking"]

def ingest_kaggle_dataset(file_path: str) -> Optional[pd.DataFrame]:
    """
    Loads the raw Kaggle CSV, standardizes column names, and strictly 
    filters for Casablanca to maintain mathematical accuracy with AUC zoning laws.
    """
    print(f"Loading dataset from: {file_path}...")
    
    try:
        # Load the raw CSV
        df: pd.DataFrame = pd.read_csv(file_path)
        
        # Standardize column names (lowercase, replace spaces with underscores)
        df.columns = df.columns.str.lower().str.replace(' ', '_')
        print("\n--- Original dataset sample (10) ---")
        print(df.head(10))
        
        # --- THE SCOPE RESTRICTION ---
        initial_row_count: int = len(df)
        
        # Clean the 'city' column: strip whitespace and format to Title Case
        df['city'] = df['city'].astype(str).str.strip().str.title()
        
        # Filter strictly for Casablanca
        df = df[df['city'] == 'Casablanca']
        
        filtered_row_count: int = len(df)
        dropped_rows: int = initial_row_count - filtered_row_count
        
        print(f"Initial dataset size: {initial_row_count} rows")
        print(f"Filtered out {dropped_rows} non-Casablanca properties.")
        print(f"Active Casablanca rows ready for ML Engine: {filtered_row_count}")

        print("\n--- Filtered dataset sample (10) ---")
        print(df.head(10))
        
        # Show a sample of the neighborhoods we are working with
        print("\n--- Casablanca Neighborhood Sample ---")
        print(df['nighberd'].value_counts().head(10))
        
        return df
        
    except FileNotFoundError:
        print(f"Error: Could not find the file at {file_path}.")
        return None
    except Exception as e:
        print(f"An error occurred during ingestion: {e}")
        return None


def prepare_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Turns the filtered Casablanca listings into a clean, model-ready table for
    Submodel C (GDV). Computes the target `price_per_m2`, coerces numeric and
    Yes/No columns, and strips junk rows / price-per-m2 outliers so the regressor
    learns from believable listings only.

    Returns a DataFrame containing FEATURE_COLUMNS + TARGET (NaNs in numeric
    features are intentionally kept — XGBoost handles missing values natively).
    """
    df = df.copy()

    # Coerce price and surface to numeric; non-parseable values become NaN.
    df["new_price"] = pd.to_numeric(df["new_price"], errors="coerce")
    df["surface"] = pd.to_numeric(df["surface"], errors="coerce")

    # Numeric supporting features (e.g. floor "RDC" -> NaN, left for XGBoost).
    for col in ["chambres", "salles_de_bains", "floor"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Yes/No -> 1/0; anything else (NaN, blanks) -> NaN.
    for col in _BOOLEAN_COLUMNS:
        df[col] = (
            df[col].astype(str).str.strip().str.lower()
            .map({"yes": 1.0, "no": 0.0})
        )

    # Drop rows we can't build a target from, then compute price per m2.
    df = df.dropna(subset=["new_price", "surface"])
    df = df[(df["surface"] > 0) & (df["new_price"] > 0)]
    df[TARGET] = df["new_price"] / df["surface"]

    # Strip price-per-m2 outliers (keep the 1st-99th percentile) so a handful of
    # mistyped listings don't drag the model.
    low, high = df[TARGET].quantile([0.01, 0.99])
    before = len(df)
    df = df[(df[TARGET] >= low) & (df[TARGET] <= high)]
    print(
        f"\n--- Feature prep ---\n"
        f"Outlier filter on {TARGET}: kept {len(df)}/{before} rows "
        f"(MAD/m2 range {low:,.0f} - {high:,.0f})."
    )

    model_df = df[FEATURE_COLUMNS + [TARGET]].reset_index(drop=True)
    print(f"Model-ready rows: {len(model_df)} | columns: {list(model_df.columns)}")
    return model_df


if __name__ == "__main__":
    csv_path: str = "data/raw/Housing_data.csv"
    cleaned_data: Optional[pd.DataFrame] = ingest_kaggle_dataset(csv_path)

    if cleaned_data is not None:
        print("\nIngestion Successful. Data is legally aligned and ready for Submodel C: The Valuation AI (GDV).")
        features = prepare_features(cleaned_data)
        print("\n--- Model-ready sample (5) ---")
        print(features.head(5))