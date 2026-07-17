"""
Stages 7-12 - The orchestrator.

ingest -> validate -> clean/feature-engineer -> split -> train each candidate
(with optional GridSearch tuning + cross-validation) -> evaluate on the held-out
test set -> pick the winner by the primary metric -> persist the fitted Pipeline
plus a metadata sidecar.

Run:  python -m app.ml.train
"""
import json
import os
import time
import warnings as _warnings
from typing import Dict, Optional, Tuple

import joblib
import numpy as np
import pandas as pd
from sklearn.exceptions import ConvergenceWarning
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import GridSearchCV, train_test_split

from .config import MLConfig
from .features import build_features
from .ingest import load_raw
from .models import get_models, get_param_grids
from .pipeline import build_pipeline
from .validate import validate_raw

_warnings.filterwarnings("ignore", category=ConvergenceWarning)


def _metrics(y_true: np.ndarray, y_pred: np.ndarray) -> Dict[str, float]:
    mae = float(mean_absolute_error(y_true, y_pred))
    rmse = float(mean_squared_error(y_true, y_pred) ** 0.5)
    denom = np.clip(np.abs(y_true), 1e-9, None)
    mape = float(np.mean(np.abs((y_true - y_pred) / denom)) * 100)
    r2 = float(r2_score(y_true, y_pred)) if len(y_true) > 1 else float("nan")
    return {"MAE": mae, "RMSE": rmse, "MAPE": mape, "R2": r2}


def run_training(config: Optional[MLConfig] = None) -> Tuple[pd.DataFrame, str]:
    config = config or MLConfig()
    notes = []

    # 1-3. Ingest -> validate -> clean / feature engineer
    raw = load_raw(config.csv_path)
    validate_raw(raw, config)
    data = build_features(raw, config)

    n = len(data)
    dedup_dropped = data.attrs.get("dedup_dropped", 0)
    if dedup_dropped:
        notes.append(
            f"Deduplicated before split: dropped {dedup_dropped} duplicate rows "
            f"({data.attrs.get('rows_before_dedup')} -> {n}) to prevent leakage."
        )
    if n < 50:
        notes.append(
            f"DATA CAVEAT: only {n} unique rows after dedup. Metrics below are a "
            f"PIPELINE SMOKE TEST, not a trustworthy model. Swap in a larger "
            f"dataset via config.py to get meaningful results."
        )

    X, y = data[config.all_features], data[config.target]

    # 7. Split
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=config.test_size, random_state=config.random_state
    )
    cv = max(2, min(config.cv_folds, len(X_train)))

    # 9-11. Train / tune / evaluate each candidate
    models, grids = get_models(config), get_param_grids()
    results: Dict[str, Dict[str, float]] = {}
    fitted: Dict[str, object] = {}
    best_params: Dict[str, dict] = {}

    for name, estimator in models.items():
        pipe = build_pipeline(estimator, config)
        if config.tune and name in grids and len(X_train) >= cv:
            try:
                search = GridSearchCV(
                    pipe, grids[name], cv=cv,
                    scoring="neg_mean_absolute_error", n_jobs=1, error_score=np.nan,
                )
                search.fit(X_train, y_train)
                model = search.best_estimator_
                best_params[name] = search.best_params_
            except Exception as exc:  # robustness: fall back to untuned fit
                notes.append(f"Tuning failed for {name} ({exc}); used default params.")
                model = pipe.fit(X_train, y_train)
        else:
            model = pipe.fit(X_train, y_train)

        preds = model.predict(X_test)
        results[name] = _metrics(y_test.to_numpy(), preds)
        fitted[name] = model

    table = pd.DataFrame(results).T[["MAE", "RMSE", "MAPE", "R2"]]

    # 12. Pick winner (lower MAE/RMSE/MAPE is better; R2 higher is better)
    ascending = config.primary_metric != "R2"
    best_name = table[config.primary_metric].sort_values(ascending=ascending).index[0]
    best_model = fitted[best_name]

    # Persist artifact + metadata. We also stash what the fallback layer needs:
    # which neighborhoods were actually seen in training (coverage check) and the
    # plausible target range (sanity check).
    os.makedirs(os.path.dirname(config.model_path), exist_ok=True)
    cat_col = config.categorical_features[0] if config.categorical_features else None
    training_neighborhoods = (
        sorted(X_train[cat_col].dropna().astype(str).unique().tolist())
        if cat_col and cat_col in X_train.columns else []
    )
    joblib.dump(
        {
            "pipeline": best_model,
            "features": config.all_features,
            "target": config.target,
            "training_neighborhoods": training_neighborhoods,
            "target_min": float(y.min()),
            "target_max": float(y.max()),
        },
        config.model_path,
    )
    metadata = {
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "best_model": best_name,
        "primary_metric": config.primary_metric,
        "metrics": results,
        "best_params": best_params,
        "n_rows_modelled": n,
        "train_rows": len(X_train),
        "test_rows": len(X_test),
        "features": {
            "numeric": config.numeric_features,
            "categorical": config.categorical_features,
            "target": config.target,
        },
        "notes": notes,
    }
    with open(config.metadata_path, "w", encoding="utf-8") as fh:
        json.dump(metadata, fh, ensure_ascii=False, indent=2)

    return table, best_name


if __name__ == "__main__":
    config = MLConfig()
    table, best = run_training(config)

    print("\n=== ML PIPELINE: MODEL COMPARISON (GDV price/m2) ===")
    print(table.round(2).to_string())
    print(f"\nWinner by {config.primary_metric}: {best}")
    print(f"Saved model    -> {config.model_path}")
    print(f"Saved metadata -> {config.metadata_path}")

    with open(config.metadata_path, encoding="utf-8") as fh:
        for note in json.load(fh)["notes"]:
            print(f"  ! {note}")
