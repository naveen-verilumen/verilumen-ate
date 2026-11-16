"""Load monitoring.yaml. Thresholds remain TO_BE_CALIBRATED."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

from yield_improvement.utils.errors import ConfigError
from yield_improvement.utils.paths import configs_dir


class Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class FeatureDriftThr(Frozen):
    psi_warning: float
    psi_review: float
    ks_warning: float
    ks_review: float
    unseen_category_warning: float
    unseen_category_review: float
    category_shift_warning: float
    category_shift_review: float
    n_features_review_for_multi: int


class PredictionDriftThr(Frozen):
    mean_abs_warning: float
    mean_abs_review: float
    psi_warning: float
    psi_review: float
    ks_warning: float
    ks_review: float
    positive_rate_abs_warning: float
    positive_rate_abs_review: float


class TargetDriftThr(Frozen):
    abs_warning: float
    abs_review: float
    relative_warning: float
    relative_review: float


class CalibrationThr(Frozen):
    brier_increase_warning: float
    brier_increase_review: float
    ece_warning: float
    ece_review: float


class PerformanceThr(Frozen):
    roc_auc_drop_warning: float
    roc_auc_drop_review: float
    pr_auc_drop_warning: float
    pr_auc_drop_review: float
    capture10_drop_warning: float
    capture10_drop_review: float


class HealthRule(Frozen):
    id: str
    result: str


class HealthPolicy(Frozen):
    notes: list[str] = Field(default_factory=list)
    rules: list[HealthRule] = Field(default_factory=list)


class MonitoringConfig(Frozen):
    monitoring_version: str
    reference_version: str
    status: str
    seed: int
    min_current_samples: int
    min_bin_count: int
    min_lot_samples: int
    psi_bins: int
    calibration_bins: int
    feature_drift: FeatureDriftThr
    prediction_drift: PredictionDriftThr
    target_drift: TargetDriftThr
    calibration: CalibrationThr
    performance: PerformanceThr
    health_policy: HealthPolicy
    recommendations: dict[str, str]
    limitations: list[str] = Field(default_factory=list)


def load_monitoring_config(path: Path | None = None) -> MonitoringConfig:
    file_path = path or (configs_dir() / "monitoring.yaml")
    if not file_path.is_file():
        raise ConfigError(f"Missing {file_path}")
    payload = yaml.safe_load(file_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ConfigError("monitoring.yaml must be a mapping")
    try:
        return MonitoringConfig.model_validate(payload)
    except Exception as exc:  # noqa: BLE001
        raise ConfigError(f"Invalid monitoring.yaml: {exc}") from exc


def worst_metric_status(*statuses: str) -> str:
    order = ["REVIEW", "DEGRADED", "WARNING", "INSUFFICIENT_DATA", "UNAVAILABLE", "HEALTHY"]
    rank = {name: i for i, name in enumerate(order)}
    present = [s for s in statuses if s in rank]
    if not present:
        return "HEALTHY"
    return min(present, key=lambda s: rank[s])


def dimension_from_metrics(statuses: list[str], *, availability: str) -> str:
    if availability == "UNAVAILABLE":
        return "UNAVAILABLE"
    if availability == "INSUFFICIENT_DATA":
        return "INSUFFICIENT_DATA"
    mapped = []
    for status in statuses:
        if status == "REVIEW":
            mapped.append("REVIEW")
        elif status == "WARNING":
            mapped.append("MONITOR")
        elif status == "DEGRADED":
            mapped.append("DEGRADED")
        elif status == "INSUFFICIENT_DATA":
            mapped.append("INSUFFICIENT_DATA")
        elif status == "UNAVAILABLE":
            mapped.append("UNAVAILABLE")
        else:
            mapped.append("HEALTHY")
    if "DEGRADED" in mapped:
        return "DEGRADED"
    if "REVIEW" in mapped:
        return "REVIEW"
    if "MONITOR" in mapped:
        return "MONITOR"
    if mapped and all(s == "INSUFFICIENT_DATA" for s in mapped):
        return "INSUFFICIENT_DATA"
    return "HEALTHY"
