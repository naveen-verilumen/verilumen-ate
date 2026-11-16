"""Deterministic overall health from independent dimensions. Never a magic score."""

from __future__ import annotations

from yield_improvement.monitoring.contracts import (
    CalibrationResult,
    DimensionSummary,
    HealthState,
    Recommendation,
)
from yield_improvement.monitoring.thresholds import MonitoringConfig

DEGRADED_LIKE = {"DEGRADED"}
REVIEW_LIKE = {"REVIEW"}
MONITOR_LIKE = {"MONITOR"}


def decide_health(
    *,
    cfg: MonitoringConfig,
    n_current: int,
    labeled: bool,
    feature: DimensionSummary,
    prediction: DimensionSummary,
    target: DimensionSummary,
    calibration: CalibrationResult,
    performance: DimensionSummary,
    data_quality: DimensionSummary,
    n_feature_review: int,
) -> tuple[HealthState, list[str], list[Recommendation]]:
    triggers: list[str] = []
    for rule in cfg.health_policy.rules:
        rid = rule.id
        if rid == "critical_data_quality" and data_quality.status == "REVIEW":
            triggers.append("critical_data_quality")
            return "REVIEW", triggers, [_rec(cfg, "REVIEW")]
        if rid == "insufficient_sample" and n_current < cfg.min_current_samples:
            triggers.append("insufficient_sample")
            return "INSUFFICIENT_DATA", triggers, [_rec(cfg, "INSUFFICIENT_DATA")]
        if rid == "severe_performance" and performance.status == "DEGRADED":
            triggers.append("severe_performance")
            extra: list[str] = ["severe_performance"]
            recs = [_rec(cfg, "DEGRADED")]
            if n_feature_review >= cfg.feature_drift.n_features_review_for_multi or prediction.status in REVIEW_LIKE:
                extra.append("multi_signal_with_performance")
                recs = [_rec(cfg, "NEEDS_RETRAINING")]
                return "NEEDS_RETRAINING", extra, recs
            return "DEGRADED", extra, recs
        if rid == "severe_calibration" and calibration.status == "REVIEW":
            triggers.append("severe_calibration")
            return "REVIEW", triggers, [_rec(cfg, "REVIEW")]
        if rid == "multi_signal_retrain":
            signals = 0
            if feature.status in {"REVIEW", "MONITOR"}:
                signals += 1
            if prediction.status in {"REVIEW", "MONITOR"}:
                signals += 1
            if target.status in {"REVIEW", "MONITOR"}:
                signals += 1
            if calibration.status in {"REVIEW", "MONITOR"}:
                signals += 1
            if labeled and signals >= 3:
                triggers.append("multi_signal_retrain")
                return "NEEDS_RETRAINING", triggers, [_rec(cfg, "NEEDS_RETRAINING")]
        if rid == "multi_feature_drift" and n_feature_review >= cfg.feature_drift.n_features_review_for_multi:
            triggers.append("multi_feature_drift")
            return "MONITOR", triggers, [_rec(cfg, "MONITOR")]
        if rid == "any_review_dimension":
            if any(
                s.status == "REVIEW"
                for s in (feature, prediction, target, data_quality)
            ) or calibration.status == "REVIEW" or performance.status == "REVIEW":
                triggers.append("any_review_dimension")
                return "REVIEW", triggers, [_rec(cfg, "REVIEW")]
        if rid == "any_warning_dimension":
            if any(s.status == "MONITOR" for s in (feature, prediction, target, performance, data_quality)) or calibration.status == "MONITOR":
                triggers.append("any_warning_dimension")
                return "MONITOR", triggers, [_rec(cfg, "MONITOR")]
        if rid == "default":
            triggers.append("default_healthy")
            return "HEALTHY", triggers, [_rec(cfg, "HEALTHY")]
    return "INSUFFICIENT_DATA", ["policy_fell_through"], [_rec(cfg, "INSUFFICIENT_DATA")]


def _rec(cfg: MonitoringConfig, state: str) -> Recommendation:
    value = cfg.recommendations.get(state, "CONTINUE_MONITORING")
    return value  # type: ignore[return-value]
