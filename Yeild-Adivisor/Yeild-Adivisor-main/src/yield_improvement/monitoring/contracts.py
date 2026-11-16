"""Monitoring contracts. Advisory model health only. extra=forbid."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

HealthState = Literal[
    "HEALTHY",
    "MONITOR",
    "REVIEW",
    "DEGRADED",
    "NEEDS_RETRAINING",
    "INSUFFICIENT_DATA",
]
DimensionStatus = Literal[
    "HEALTHY",
    "MONITOR",
    "REVIEW",
    "DEGRADED",
    "INSUFFICIENT_DATA",
    "UNAVAILABLE",
]
MetricStatus = Literal["HEALTHY", "WARNING", "REVIEW", "INSUFFICIENT_DATA", "UNAVAILABLE"]
Recommendation = Literal[
    "CONTINUE_MONITORING",
    "REVIEW_MODEL",
    "COLLECT_MORE_DATA",
    "INVESTIGATE_DRIFT",
    "CONSIDER_RETRAINING",
]
LabelMode = Literal["LABELED", "UNLABELED"]

FORBIDDEN_PHRASES = (
    "SET_LIMIT",
    "increase limit",
    "decrease limit",
    "change limit",
    "optimize limit",
    "DEPLOY_NEW_MODEL_AUTOMATICALLY",
    "CHANGE_LIMIT",
    "CHANGE_RECIPE",
    "MODIFY_ATE",
    "MODIFY_EQUIPMENT",
    "APPROVED_FOR_PRODUCTION",
    "the root cause is",
    "recovered yield",
    "guaranteed improvement",
)

DISCLAIMER = (
    "Model health is advisory. It is not a production authorization, not a root cause, "
    "not a causal effect, and not an instruction to retrain or replace the model automatically."
)

DEGRADED_EVIDENCE_STATES = frozenset({"DEGRADED", "NEEDS_RETRAINING", "INSUFFICIENT_DATA"})


class Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class MonitoringMetric(Frozen):
    metric_name: str
    dimension: str
    reference_value: float | None = None
    current_value: float | None = None
    delta: float | None = None
    threshold: float | None = None
    status: MetricStatus
    sample_size: int | None = None
    notes: str = ""


class FeatureDriftResult(Frozen):
    feature_name: str
    data_type: Literal["numeric", "categorical"]
    metric: str
    reference_value: float | None = None
    current_value: float | None = None
    status: MetricStatus
    reference_sample_size: int
    current_sample_size: int
    notes: str = ""


class CalibrationBin(Frozen):
    bin: str
    mean_prediction: float | None = None
    observed_failure_rate: float | None = None
    sample_count: int
    insufficient_sample_size: bool = False


class CalibrationResult(Frozen):
    status: DimensionStatus
    availability: Literal["AVAILABLE", "UNAVAILABLE", "INSUFFICIENT_DATA"]
    brier_reference: float | None = None
    brier_current: float | None = None
    brier_delta: float | None = None
    ece_current: float | None = None
    bins: list[CalibrationBin] = Field(default_factory=list)
    notes: str = ""


class PerformanceResult(Frozen):
    metric: str
    reference_value: float | None = None
    current_value: float | None = None
    delta: float | None = None
    status: MetricStatus
    notes: str = ""


class DimensionSummary(Frozen):
    dimension: str
    status: DimensionStatus
    availability: Literal["AVAILABLE", "UNAVAILABLE", "INSUFFICIENT_DATA"]
    metrics: list[MonitoringMetric] = Field(default_factory=list)
    notes: str = ""


class ModelHealthReport(Frozen):
    analysis_id: str
    model_version: str
    feature_version: str
    calibration_version: str
    reference_version: str
    reference_dataset_id: str
    current_dataset_id: str
    label_mode: LabelMode
    n_lots: int
    n_wafers: int
    n_dies: int
    feature_drift: DimensionSummary
    prediction_drift: DimensionSummary
    target_drift: DimensionSummary
    calibration: CalibrationResult
    performance: DimensionSummary
    data_quality: DimensionSummary
    overall_status: HealthState
    triggers: list[str] = Field(default_factory=list)
    recommendations: list[Recommendation] = Field(default_factory=list)
    feature_drift_details: list[FeatureDriftResult] = Field(default_factory=list)
    performance_details: list[PerformanceResult] = Field(default_factory=list)
    lot_summaries: list[dict[str, Any]] = Field(default_factory=list)
    temporal: list[dict[str, Any]] = Field(default_factory=list)
    temporal_available: bool = False
    limitations: list[str] = Field(default_factory=list)
    production_action: Literal["FORBIDDEN"] = "FORBIDDEN"
    production_authorized: Literal[False] = False
    safety_eligible_production_count: Literal[0] = 0
    safety_eligible_production_rate: Literal[0.0] = 0.0
    retrained: Literal[False] = False
    model_replaced: Literal[False] = False
    active_model_version: str | None = None
    invoked_agents: list[str] = Field(default_factory=list)
    disclaimer: str = DISCLAIMER

    @field_validator("invoked_agents")
    @classmethod
    def _no_invoke(cls, value: list[str]) -> list[str]:
        if value:
            raise ValueError("invoked_agents must be empty")
        return []

    @field_validator("recommendations")
    @classmethod
    def _allowed_rec(cls, value: list[str]) -> list[str]:
        forbidden = {
            "DEPLOY_NEW_MODEL_AUTOMATICALLY",
            "CHANGE_LIMIT",
            "CHANGE_RECIPE",
            "MODIFY_ATE",
            "MODIFY_EQUIPMENT",
        }
        for item in value:
            if item in forbidden:
                raise ValueError(f"forbidden recommendation: {item}")
        return value

    @model_validator(mode="after")
    def _phrases(self) -> ModelHealthReport:
        blob = self.model_dump_json().lower()
        for phrase in FORBIDDEN_PHRASES:
            if phrase.lower() in blob:
                raise ValueError(f"forbidden phrase in monitoring report: {phrase}")
        return self

    def to_public_dict(self) -> dict[str, Any]:
        payload = self.model_dump(mode="json")
        payload["production_action"] = "FORBIDDEN"
        payload["production_authorized"] = False
        payload["safety_eligible_production_count"] = 0
        payload["safety_eligible_production_rate"] = 0.0
        payload["retrained"] = False
        payload["model_replaced"] = False
        payload["active_model_version"] = payload.get("active_model_version") or payload.get("model_version")
        payload["disclaimer"] = DISCLAIMER
        return payload
