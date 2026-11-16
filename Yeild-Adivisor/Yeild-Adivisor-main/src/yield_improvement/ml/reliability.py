"""Whether ML evidence is reliable enough to support an investigation finding."""

from __future__ import annotations

from typing import Any

NEEDS_MORE_DATA = "NEEDS_MORE_DATA"
RELIABLE = "RELIABLE"


def constant_references(positive_rate: float) -> tuple[float, float]:
    rate = float(positive_rate)
    return rate, rate * (1.0 - rate)


def ml_support_status(
    pooled: dict[str, Any],
    per_lot: list[dict[str, Any]] | None,
    positive_rate: float,
) -> str:
    """Fail closed unless ranking and calibration beat a constant score on more than one lot.

    PR-AUC is compared with the failure rate. Brier is compared with p(1-p).
    ROC-AUC is compared with 0.5, not with the failure rate.
    """
    pr_ref, brier_ref = constant_references(positive_rate)
    pr = pooled.get("pr_auc")
    roc = pooled.get("roc_auc")
    brier = pooled.get("brier")
    if pr is None or roc is None or brier is None:
        return NEEDS_MORE_DATA
    if float(pr) <= pr_ref or float(roc) <= 0.5 or float(brier) >= brier_ref:
        return NEEDS_MORE_DATA
    if not per_lot:
        return RELIABLE
    helpful = 0
    for row in per_lot:
        lot_rate = row.get("positive_rate")
        lot_pr = row.get("pr_auc")
        lot_roc = row.get("roc_auc")
        if lot_rate is None or lot_pr is None or lot_roc is None:
            continue
        if float(lot_pr) > float(lot_rate) and float(lot_roc) > 0.55:
            helpful += 1
    if helpful < 3:
        return NEEDS_MORE_DATA
    return RELIABLE
