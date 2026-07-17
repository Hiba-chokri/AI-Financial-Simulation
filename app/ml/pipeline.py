"""
Stage 6 - Preprocessing pipeline (scikit-learn).

Builds a ColumnTransformer that imputes + scales numerics and imputes +
one-hot-encodes categoricals, then chains it with an estimator. Because it's a
single sklearn Pipeline, all preprocessing is fit on the TRAINING fold only --
this is what prevents data leakage. `handle_unknown="ignore"` lets inference
survive neighborhoods/categories unseen during training.

Column ROLES come from the config, so new features flow through automatically.
"""
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from .config import MLConfig


def build_preprocessor(config: MLConfig) -> ColumnTransformer:
    numeric = Pipeline([
        ("impute", SimpleImputer(strategy="median")),
        ("scale", StandardScaler()),
    ])
    categorical = Pipeline([
        ("impute", SimpleImputer(strategy="most_frequent")),
        ("onehot", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
    ])
    return ColumnTransformer([
        ("num", numeric, config.numeric_features),
        ("cat", categorical, config.categorical_features),
    ])


def build_pipeline(estimator, config: MLConfig) -> Pipeline:
    """Wrap an estimator with the shared preprocessing into one Pipeline."""
    return Pipeline([
        ("preprocess", build_preprocessor(config)),
        ("model", estimator),
    ])
