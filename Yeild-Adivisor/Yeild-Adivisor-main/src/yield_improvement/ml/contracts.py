"""ML Pydantic contracts. Predictive only. extra=forbid."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

FORBIDDEN_PHRASES = (
    "SET_LIMIT",
    "increase limit",
    "decrease limit",
    "change limit",
    "optimize limit",
    "set new limit",
    "candidate limit",
    "APPROVED_FOR_PRODUCTION",
    "the root cause is",
    "guaranteed improvement",
    "recovered yield",
)

DISCLAIMER = (
    "ML output is a predictive association for first-pass failure. "
    "It is not a confirmed root cause, not a causal effect, not a predicted FPY gain, "
    "and not a production authorization."
)


class Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class MLPrediction(Frozen):
    die_id: str
    lot_id: str
    wafer_id: str
    predicted_probability: float
    raw_probability: float
    calibrated_probability: float | None = None
    predicted_class: Literal[0, 1]
    model_version: str
    feature_set_version: str
    calibration_version: str

    @field_validator("predicted_probability", "raw_probability")
    @classmethod
    def _unit(cls, value: float) -> float:
        if not 0.0 <= value <= 1.0:
            raise ValueError("probability must be in [0, 1]")
        return value


class MLEvidence(Frozen):
    hypothesis_id: str | None
    family: str
    detail: str
    evidence_type: Literal["ML_PREDICTIVE_ASSOCIATION"] = "ML_PREDICTIVE_ASSOCIATION"
    evidence_role: Literal["SECONDARY_SUPPORT"] = "SECONDARY_SUPPORT"
    affected_population: dict[str, Any] = Field(default_factory=dict)
    prediction_summary: dict[str, Any] = Field(default_factory=dict)
    feature_importance: list[dict[str, Any]] = Field(default_factory=list)
    predictive_strength: float
    coverage: float
    independence: Literal[False] = False
    model_version: str
    limitations: list[str] = Field(default_factory=list)
    not_a_root_cause: Literal[True] = True

    @field_validator("predictive_strength", "coverage")
    @classmethod
    def _unit_fields(cls, value: float) -> float:
        if not 0.0 <= value <= 1.0:
            raise ValueError("must be in [0, 1]")
        return value


class MLMetrics(Frozen):
    roc_auc: float | None = None
    pr_auc: float | None = None
    precision: float | None = None
    recall: float | None = None
    f1: float | None = None
    balanced_accuracy: float | None = None
    brier: float | None = None
    log_loss: float | None = None
    failure_capture_at_top_10_percent: float | None = None
    failure_capture_at_top_20_percent: float | None = None
    positive_rate: float | None = None
    n_samples: int = 0
    n_positives: int = 0

    @field_validator("roc_auc", "pr_auc", "precision", "recall", "f1", "balanced_accuracy")
    @classmethod
    def _not_accuracy_primary(cls, value: float | None) -> float | None:
        return value


class MLCalibration(Frozen):
    method: str
    fitted: bool
    brier_raw: float | None = None
    brier_calibrated: float | None = None
    note: str


class MLResult(Frozen):
    analysis_id: str
    model_name: str
    model_version: str
    feature_set_version: str
    calibration_version: str
    split_strategy: str
    seed: int
    n_features: int
    n_train: int
    n_validation: int
    n_test: int
    metrics: MLMetrics
    comparison: list[dict[str, Any]] = Field(default_factory=list)
    calibration: MLCalibration
    predictions: list[MLPrediction] = Field(default_factory=list)
    feature_importance: list[dict[str, Any]] = Field(default_factory=list)
    evidence: list[MLEvidence] = Field(default_factory=list)
    feature_names: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    not_a_root_cause: Literal[True] = True
    production_action: Literal["FORBIDDEN"] = "FORBIDDEN"
    production_authorized: Literal[False] = False
    safety_eligible_production_rate: Literal[0.0] = 0.0
    invoked_agents: list[str] = Field(default_factory=list)
    disclaimer: str = DISCLAIMER

    @field_validator("invoked_agents")
    @classmethod
    def _no_invoke(cls, value: list[str]) -> list[str]:
        if value:
            raise ValueError("invoked_agents must be empty")
        return []

    @model_validator(mode="after")
    def _phrases(self) -> MLResult:
        blob = self.model_dump_json().lower()
        for phrase in FORBIDDEN_PHRASES:
            if phrase.lower() in blob:
                raise ValueError(f"forbidden phrase in ML result: {phrase}")
        return self

    def to_public_dict(self) -> dict[str, Any]:
        payload = self.model_dump(mode="json")
        payload["production_action"] = "FORBIDDEN"
        payload["production_authorized"] = False
        payload["safety_eligible_production_rate"] = 0.0
        payload["not_a_root_cause"] = True
        payload["disclaimer"] = DISCLAIMER
        return payload
