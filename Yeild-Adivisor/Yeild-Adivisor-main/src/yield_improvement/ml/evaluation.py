"""Classification metrics and failure-capture-at-risk-budget. Not yield improvement."""

from __future__ import annotations

import numpy as np
from sklearn.metrics import (
    average_precision_score,
    balanced_accuracy_score,
    brier_score_loss,
    f1_score,
    log_loss,
    precision_score,
    recall_score,
    roc_auc_score,
)

from yield_improvement.ml.contracts import MLMetrics


def failure_capture_at_fraction(y: np.ndarray, proba: np.ndarray, fraction: float) -> float | None:
    if y.size == 0 or int(y.sum()) == 0:
        return None
    k = max(1, int(np.ceil(fraction * len(y))))
    order = np.argsort(-proba)
    captured = float(y[order][:k].sum())
    return captured / float(y.sum())


def compute_metrics(y: np.ndarray, proba: np.ndarray) -> MLMetrics:
    pred = (proba >= 0.5).astype(int)
    roc = pr = None
    if len(np.unique(y)) > 1:
        roc = float(roc_auc_score(y, proba))
        pr = float(average_precision_score(y, proba))
    try:
        ll = float(log_loss(y, np.clip(proba, 1e-6, 1 - 1e-6), labels=[0, 1]))
    except ValueError:
        ll = None
    return MLMetrics(
        roc_auc=roc,
        pr_auc=pr,
        precision=float(precision_score(y, pred, zero_division=0)),
        recall=float(recall_score(y, pred, zero_division=0)),
        f1=float(f1_score(y, pred, zero_division=0)),
        balanced_accuracy=float(balanced_accuracy_score(y, pred)),
        brier=float(brier_score_loss(y, proba)),
        log_loss=ll,
        failure_capture_at_top_10_percent=failure_capture_at_fraction(y, proba, 0.10),
        failure_capture_at_top_20_percent=failure_capture_at_fraction(y, proba, 0.20),
        positive_rate=float(y.mean()) if y.size else None,
        n_samples=int(y.size),
        n_positives=int(y.sum()),
    )
