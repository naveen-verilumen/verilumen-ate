"""Permutation importance. SHAP is optional and never required."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.inspection import permutation_importance


def permutation_ranks(pipeline, x: pd.DataFrame, y: np.ndarray, seed: int, max_rows: int = 160) -> list[dict]:
    if len(x) == 0:
        return []
    if len(x) > max_rows:
        rng = np.random.RandomState(seed)
        idx = rng.choice(len(x), size=max_rows, replace=False)
        x_use = x.iloc[idx]
        y_use = y[idx]
    else:
        x_use = x
        y_use = y
    scoring = "roc_auc" if len(np.unique(y_use)) > 1 else "neg_brier_score"
    result = permutation_importance(
        pipeline,
        x_use,
        y_use,
        n_repeats=2,
        random_state=seed,
        scoring=scoring,
        n_jobs=1,
    )
    rows = []
    for name, mean, std in zip(x.columns, result.importances_mean, result.importances_std):
        rows.append(
            {
                "feature": str(name),
                "importance": float(max(0.0, mean)),
                "std": float(std),
                "kind": "predictive_permutation_importance",
                "note": "Predictive importance only. Not a causal effect.",
            }
        )
    rows.sort(key=lambda r: -r["importance"])
    return rows
