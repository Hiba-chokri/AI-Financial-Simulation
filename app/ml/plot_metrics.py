"""
Run:  python -m app.ml.plot_metrics
Reads kc_pipeline_meta.json and saves a side-by-side bar-chart comparison of
all candidate models across the four evaluation metrics.
Output: data/models/metrics_comparison.png
"""
import json
import os
from typing import Optional

import matplotlib.pyplot as plt
import numpy as np

from .config import MLConfig

_METRICS = {
    "MAE":  {"label": "MAE  (lower ↓ better)",  "lower_better": True},
    "RMSE": {"label": "RMSE (lower ↓ better)",  "lower_better": True},
    "MAPE": {"label": "MAPE % (lower ↓ better)", "lower_better": True},
    "R2":   {"label": "R²   (higher ↑ better)",  "lower_better": False},
}


def plot_metrics(meta_path: Optional[str] = None, out_path: Optional[str] = None) -> str:
    config = MLConfig()
    meta_path = meta_path or config.metadata_path
    out_path = out_path or os.path.join(os.path.dirname(meta_path), "metrics_comparison.png")

    with open(meta_path, encoding="utf-8") as fh:
        meta = json.load(fh)

    metrics = meta["metrics"]          # {model_name: {MAE, RMSE, MAPE, R2}}
    best = meta["best_model"]
    models = list(metrics.keys())
    colors = ["#2196F3" if m != best else "#4CAF50" for m in models]

    fig, axes = plt.subplots(4, 1, figsize=(7, 14))
    fig.suptitle("Model comparison — KC house price per sqft", fontsize=13, fontweight="bold")

    x = np.arange(len(models))
    bar_width = 0.5

    for ax, (key, info) in zip(axes, _METRICS.items()):
        values = [metrics[m][key] for m in models]
        bars = ax.bar(x, values, width=bar_width, color=colors, edgecolor="white", linewidth=0.8)
        ax.set_title(info["label"], fontsize=9, pad=6)
        ax.set_xticks(x)
        ax.set_xticklabels([m.replace("_", "\n") for m in models], fontsize=9)
        ax.yaxis.set_tick_params(labelsize=8)
        ax.spines[["top", "right"]].set_visible(False)

        # value label on top of each bar
        for bar, v in zip(bars, values):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() * 1.02,
                f"{v:.2f}",
                ha="center", va="bottom", fontsize=8,
            )

    # legend
    from matplotlib.patches import Patch
    fig.legend(
        handles=[Patch(color="#4CAF50", label=f"winner: {best}"),
                 Patch(color="#2196F3", label="other models")],
        loc="lower center", ncol=2, fontsize=9, frameon=False,
        bbox_to_anchor=(0.5, -0.04),
    )

    fig.tight_layout(rect=[0, 0.04, 1, 1])
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out_path


if __name__ == "__main__":
    path = plot_metrics()
    print(f"Saved -> {path}")
