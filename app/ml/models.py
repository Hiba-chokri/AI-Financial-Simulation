"""
Stage 9 - The candidate algorithms.

Three regressors spanning the usual quality/complexity trade-off:
  - ridge          : regularized linear baseline (fast, interpretable). If the
                     fancy models can't beat this, they aren't earning their keep.
  - random_forest  : robust non-linear, handles interactions, gives importances.
  - xgboost        : gradient boosting, usually the strongest on tabular data.

`get_param_grids` supplies small search spaces for hyperparameter tuning. Grid
keys are prefixed `model__` because the estimator is the "model" step of the
Pipeline built in pipeline.py.
"""
from typing import Dict

from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import Ridge
from xgboost import XGBRegressor

from .config import MLConfig


def get_models(config: MLConfig) -> Dict[str, object]:
    return {
        "ridge": Ridge(alpha=1.0, random_state=config.random_state),
        "random_forest": RandomForestRegressor(
            n_estimators=200, random_state=config.random_state, n_jobs=1
        ),
        "xgboost": XGBRegressor(
            n_estimators=200, max_depth=3, learning_rate=0.1,
            objective="reg:squarederror", random_state=config.random_state,
            n_jobs=1, verbosity=0,
        ),
    }


def get_param_grids() -> Dict[str, dict]:
    return {
        "ridge": {"model__alpha": [0.1, 1.0, 10.0]},
        "random_forest": {
            "model__n_estimators": [100, 300],
            "model__max_depth": [None, 5, 10],
        },
        "xgboost": {
            "model__n_estimators": [100, 300],
            "model__max_depth": [3, 5],
            "model__learning_rate": [0.05, 0.1],
        },
    }
