"""First-pass failure rate drift. Distinct from model/prediction drift."""

from __future__ import annotations

from yield_improvement.monitoring.contracts import DimensionSummary, MonitoringMetric
from yield_improvement.monitoring.feature_drift import _band
from yield_improvement.monitoring.thresholds import MonitoringConfig, dimension_from_metrics


def target_drift(
    reference_rate: float | None,
    current_rate: float | None,
    n_current: int,
    cfg: MonitoringConfig,
    *,
    labeled: bool,
) -> DimensionSummary:
    if not labeled:
        return DimensionSummary(
            dimension="target_drift",
            status="UNAVAILABLE",
            availability="UNAVAILABLE",
            notes="First-pass labels are not available. Target drift was not fabricated.",
        )
    if current_rate is None or n_current < cfg.min_current_samples:
        return DimensionSummary(
            dimension="target_drift",
            status="INSUFFICIENT_DATA",
            availability="INSUFFICIENT_DATA",
            notes="Too few labeled current dies for a stable fail-rate comparison.",
        )
    assert reference_rate is not None
    abs_delta = abs(current_rate - reference_rate)
    rel = abs_delta / reference_rate if reference_rate > 1e-9 else None
    metrics = [
        MonitoringMetric(
            metric_name="first_pass_fail_rate_abs_delta",
            dimension="target_drift",
            reference_value=reference_rate,
            current_value=current_rate,
            delta=abs_delta,
            threshold=cfg.target_drift.abs_warning,
            status=_band(abs_delta, cfg.target_drift.abs_warning, cfg.target_drift.abs_review),
            sample_size=n_current,
            notes="Process base-rate change is not the same as model drift.",
        ),
        MonitoringMetric(
            metric_name="first_pass_fail_rate_relative_delta",
            dimension="target_drift",
            reference_value=reference_rate,
            current_value=current_rate,
            delta=rel,
            threshold=cfg.target_drift.relative_warning,
            status=_band(rel, cfg.target_drift.relative_warning, cfg.target_drift.relative_review)
            if rel is not None
            else "INSUFFICIENT_DATA",
            sample_size=n_current,
            notes="Relative change vs the immutable reference fail rate.",
        ),
    ]
    status = dimension_from_metrics([m.status for m in metrics], availability="AVAILABLE")
    return DimensionSummary(
        dimension="target_drift",
        status=status,  # type: ignore[arg-type]
        availability="AVAILABLE",
        metrics=metrics,
        notes="Target drift can occur while the model remains well calibrated.",
    )
