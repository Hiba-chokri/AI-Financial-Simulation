"""
The single source of truth for the pipeline. Changing datasets = editing THIS
file (column names, roles...)  never the pipeline logic.

Features are declared by ROLE (numeric / categorical / boolean), not hardcoded
in the steps. Adding a new column later is a one-line change here, and the rest
of the pipeline adapts automatically.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Tuple


@dataclass
class MLConfig:

    csv_path: str = "data/raw/kc_house_data.csv"

    filters: Dict[str, str] = field(default_factory=dict)

    # Target engineering: price_per_sqft = price / sqft_living
    price_col: str = "price"
    area_col: str = "sqft_living"
    target: str = "price_per_sqft"

    # dataset-agnostic
    numeric_features: List[str] = field(default_factory=lambda: [
        "bedrooms", "bathrooms", "floors", "waterfront",
        "view", "condition", "grade", "sqft_above", "sqft_basement",
        "yr_built", "sqft_living15",
    ])
    categorical_features: List[str] = field(default_factory=lambda: ["zipcode"])
    boolean_features: List[str] = field(default_factory=list)  # all cols already numeric

    # Cleaning
    outlier_quantiles: Tuple[float, float] = (0.01, 0.99)
    deduplicate: bool = True

    # Modeling
    test_size: float = 0.25
    random_state: int = 42
    cv_folds: int = 3
    tune: bool = True
    primary_metric: str = "MAE"

    # Output artifacts
    model_path: str = "data/models/kc_pipeline.joblib"
    metadata_path: str = "data/models/kc_pipeline_meta.json"

    @property
    def all_features(self) -> List[str]:
        return self.numeric_features + self.categorical_features

    @property
    def required_columns(self) -> List[str]:
        cols = set(self.all_features) | {self.price_col, self.area_col}
        cols |= set(self.filters.keys())
        return sorted(cols)
