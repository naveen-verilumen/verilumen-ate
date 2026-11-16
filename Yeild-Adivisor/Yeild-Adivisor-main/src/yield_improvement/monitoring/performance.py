"""Current vs reference ranking/performance. Capture metrics are diagnostic, not yield."""

from __future__ import annotations

import numpy as np

from yield_improvement.ml.evaluation import compute_metrics
from yield_improvement.monitoring.contracts import DimensionSummary, MonitoringMetric, PerformanceResult
from yield_improvement.monitoring.feature_drift import _band
from yield_improvement.monitoring.thresholds import MonitoringConfig, dimension_from_metrics


def _drop_status(delta: float | None, warn: float, review: float) -> str:
    """delta = current - reference. Negative is degradation for AUC/capture."""
    if delta is None:
        return "INSUFFICIENT_DATA"
    drop = -delta
    return _band(drop, warn, review)


def performance_drift(
    y: np.ndarray | None,
    proba: np.ndarray,
    reference_metrics: dict[str, float | None],
    cfg: MonitoringConfig,
    *,
    labeled: bool,
) -> tuple[DimensionSummary, list[PerformanceResult]]:
    if not labeled or y is None:
        empty = DimensionSummary(
            dimension="performance",
            status="UNAVAILABLE",
            availability="UNAVAILABLE",
            notes="Performance requires first-pass outcomes. Labels were not fabricated.",
        )
        return empty, []
    if y.size < cfg.min_current_samples or len(np.unique(y)) < 2:
        empty = DimensionSummary(
            dimension="performance",
            status="INSUFFICIENT_DATA",
            availability="INSUFFICIENT_DATA",
            notes="Too few labeled current samples for ROC/PR comparison.",
        )
        return empty, []
    current = compute_metrics(y, np.clip(proba, 0.0, 1.0))
    pairs = [
        ("roc_auc", current.roc_auc, reference_metrics.get("roc_auc"), cfg.performance.roc_auc_drop_warning, cfg.performance.roc_auc_drop_review, True),
        ("pr_auc", current.pr_auc, reference_metrics.get("pr_auc"), cfg.performance.pr_auc_drop_warning, cfg.performance.pr_auc_drop_review, True),
        ("failure_capture_at_top_10_percent", current.failure_capture_at_top_10_percent, reference_metrics.get("failure_capture_at_top_10_percent"), cfg.performance.capture10_drop_warning, cfg.performance.capture10_drop_review, True),
        ("failure_capture_at_top_20_percent", current.failure_capture_at_top_20_percent, reference_metrics.get("failure_capture_at_top_20_percent"), cfg.performance.capture10_drop_warning, cfg.performance.capture10_drop_review, True),
        ("brier", current.brier, reference_metrics.get("brier"), cfg.calibration.brier_increase_warning, cfg.calibration.brier_increase_review, False),
        ("f1", current.f1, reference_metrics.get("f1"), 0.08, 0.15, True),
        ("precision", current.precision, reference_metrics.get("precision"), 0.08, 0.15, True),
        ("recall", current.recall, reference_metrics.get("recall"), 0.08, 0.15, True),
    ]
    details: list[PerformanceResult] = []
    metrics: list[MonitoringMetric] = []
    for name, cur, ref, warn, review, higher_better in pairs:
        delta = None if cur is None or ref is None else float(cur) - float(ref)
        if higher_better:
            status = _drop_status(delta, warn, review)
        else:
            status = _band(delta if delta is not None else None, warn, review)
        details.append(
            PerformanceResult(
                metric=name,
                reference_value=None if ref is None else float(ref),
                current_value=None if cur is None else float(cur),
                delta=delta,
                status=status,  # type: ignore[arg-type]
                notes="Capture metrics are diagnostic concentration, not a yield-recovery claim.",
            )
        )
        metrics.append(
            MonitoringMetric(
                metric_name=name,
                dimension="performance",
                reference_value=None if ref is None else float(ref),
                current_value=None if cur is None else float(cur),
                delta=delta,
                threshold=warn,
                status=status,  # type: ignore[arg-type]
                sample_size=int(y.size),
                notes="Compared to the immutable reference snapshot, not a hidden holdout.",
            )
        )
    status = dimension_from_metrics([m.status for m in metrics], availability="AVAILABLE")
    if status == "REVIEW":
        status = "DEGRADED"
    summary = DimensionSummary(
        dimension="performance",
        status=status,  # type: ignore[arg-type]
        availability="AVAILABLE",
        metrics=metrics,
        notes="Performance degradation is evaluated independently of feature drift.",
    )
    return summary, details
