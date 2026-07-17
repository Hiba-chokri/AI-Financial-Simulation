"""
Model quality gate — the MLOps checkpoint between "trained" and "shippable".

Reads the metadata sidecar written by train.py and fails (non-zero exit) if the
winning model does not meet the minimum bar. CI calls this right after training;
a failing gate blocks the artifact from being published.

Run:  python -m app.ml.quality_gate
"""
import json
import sys

from .config import MLConfig

# Minimum acceptable performance for the published model. Thresholds are set
# from the KC baseline (R2 0.75 / MAPE 14.2) with margin for retrain variance;
# tighten them as the model matures or the dataset changes.
MIN_R2 = 0.70
MAX_MAPE = 20.0


def run_gate(metadata_path: str = "") -> int:
    path = metadata_path or MLConfig().metadata_path
    with open(path, "r", encoding="utf-8") as fh:
        meta = json.load(fh)

    best = meta["best_model"]
    metrics = meta["metrics"][best]
    r2, mape = metrics["R2"], metrics["MAPE"]

    print(f"Quality gate for '{best}' (trained {meta.get('created_at', '?')})")
    print(f"  R2   {r2:.4f}   (minimum {MIN_R2})")
    print(f"  MAPE {mape:.2f}%  (maximum {MAX_MAPE}%)")

    failures = []
    if r2 < MIN_R2:
        failures.append(f"R2 {r2:.4f} is below the {MIN_R2} minimum")
    if mape > MAX_MAPE:
        failures.append(f"MAPE {mape:.2f}% exceeds the {MAX_MAPE}% maximum")

    if failures:
        for reason in failures:
            print(f"GATE FAILED: {reason}")
        return 1

    print("GATE PASSED: model meets the publishing bar.")
    return 0


if __name__ == "__main__":
    sys.exit(run_gate())
