"""Phase 6 validation contracts. Advisory investigation only. Production is forbidden."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Recommendation = Literal["INVESTIGATE", "REVIEW", "MONITOR", "NEEDS_MORE_DATA", "REJECTED"]
GateStatus = Literal["PASS", "WARNING", "FAIL", "UNAVAILABLE"]
ProductionAction = Literal["FORBIDDEN"]

FORBIDDEN_OUTPUT_PHRASES = (
    "APPROVED_FOR_PRODUCTION",
    "SET_LIMIT",
    "CHANGE_LIMIT",
    "MODIFY_RECIPE",
    "MODIFY_ATE",
    "MODIFY_EQUIPMENT",
    "WRITE_ATE",
    "CHANGE_RECIPE",
    "APPLY_TO_PRODUCTION",
    "increase limit",
    "decrease limit",
    "change limit",
    "optimize limit",
    "set new limit",
)

DISCLAIMER = (
    "Advisory engineering validation only. Production action is FORBIDDEN. "
    "safety_eligible_production is 0%. This is not a confirmed root cause and not a predicted FPY gain."
)


class GateTrace(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    status: GateStatus
    recommendation: Recommendation | None = None
    reasons: list[str] = Field(default_factory=list)


class Traceability(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    analysis_id: str
    hypothesis_id: str | None
    opportunity_id: str
    detector_ids: list[str] = Field(default_factory=list)
    population_definition: str
    eligible_population: int
    attribution_mode: str
    calculation_method: str
    calibration_version: str
    safety_policy_version: str
    fpy_policy_version: str


class ValidationResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    analysis_id: str
    hypothesis_id: str | None
    opportunity_id: str
    family: str | None = None
    detail: str | None = None
    recommendation: Recommendation
    recommendation_reason: str
    evidence_tier: str | None = None
    evidence_score: float | None = None
    observed_loss_rate: float
    upper_bound_rate: float | None = None
    plausible_rate: float | None = None
    data_quality_status: GateStatus
    evidence_status: GateStatus
    population_status: GateStatus
    safety_status: GateStatus
    conflict_status: GateStatus = "PASS"
    conflict_type: str | None = None
    validation_required: list[str] = Field(default_factory=list)
    validation_steps: list[str] = Field(default_factory=list)
    supporting_detectors: list[str] = Field(default_factory=list)
    conflicting_detectors: list[str] = Field(default_factory=list)
    data_gaps: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    overlap_count: int = 0
    union_count: int | None = None
    exclusive_count: int | None = None
    intersection_count: int = 0
    gate_trace: list[GateTrace] = Field(default_factory=list)
    safety_eligible_production_count: Literal[0] = 0
    safety_eligible_production_rate: Literal[0.0] = 0.0
    production_action: ProductionAction = "FORBIDDEN"
    production_authorized: Literal[False] = False
    invoked_agents: list[str] = Field(default_factory=list)
    not_a_root_cause: Literal[True] = True
    traceability: Traceability
    disclaimer: str = DISCLAIMER

    @field_validator("safety_eligible_production_rate")
    @classmethod
    def _rate_zero(cls, value: float) -> float:
        if value != 0.0:
            raise ValueError("safety_eligible_production_rate must be 0")
        return 0.0

    @field_validator("safety_eligible_production_count")
    @classmethod
    def _count_zero(cls, value: int) -> int:
        if value != 0:
            raise ValueError("safety_eligible_production_count must be 0")
        return 0

    @field_validator("production_action")
    @classmethod
    def _action_forbidden(cls, value: str) -> str:
        if value != "FORBIDDEN":
            raise ValueError("production_action must be FORBIDDEN")
        return value

    @field_validator("production_authorized")
    @classmethod
    def _not_authorized(cls, value: bool) -> bool:
        if value:
            raise ValueError("production_authorized must be false")
        return False

    @field_validator("invoked_agents")
    @classmethod
    def _no_invocations(cls, value: list[str]) -> list[str]:
        if value:
            raise ValueError("invoked_agents must be empty; specialists are labels only")
        return []

    @model_validator(mode="after")
    def _no_forbidden_phrases(self) -> ValidationResult:
        blob = json_blob(self)
        for phrase in FORBIDDEN_OUTPUT_PHRASES:
            if phrase.lower() in blob:
                raise ValueError(f"forbidden phrase in validation output: {phrase}")
        if self.recommendation not in {
            "INVESTIGATE",
            "REVIEW",
            "MONITOR",
            "NEEDS_MORE_DATA",
            "REJECTED",
        }:
            raise ValueError("invalid recommendation")
        return self


class ValidationBundle(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    analysis_id: str
    current_fpy: float | None = None
    observed_loss_rate: float
    eligible_population: int
    attribution_mode: str
    results: list[ValidationResult] = Field(default_factory=list)
    no_actionable_recommendation: bool
    overlap_summary: dict[str, Any] = Field(default_factory=dict)
    data_gaps: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    safety_eligible_production_count: Literal[0] = 0
    safety_eligible_production_rate: Literal[0.0] = 0.0
    production_action: ProductionAction = "FORBIDDEN"
    production_authorized: Literal[False] = False
    invoked_agents: list[str] = Field(default_factory=list)
    disclaimer: str = DISCLAIMER
    config_versions: dict[str, str] = Field(default_factory=dict)

    @field_validator("safety_eligible_production_rate")
    @classmethod
    def _rate_zero(cls, value: float) -> float:
        if value != 0.0:
            raise ValueError("safety_eligible_production_rate must be 0")
        return 0.0

    @field_validator("production_authorized")
    @classmethod
    def _not_authorized(cls, value: bool) -> bool:
        if value:
            raise ValueError("production_authorized must be false")
        return False

    @field_validator("invoked_agents")
    @classmethod
    def _no_invocations(cls, value: list[str]) -> list[str]:
        if value:
            raise ValueError("invoked_agents must be empty")
        return []

    def to_public_dict(self) -> dict[str, Any]:
        payload = self.model_dump(mode="json")
        payload["safety_eligible_production_rate"] = 0.0
        payload["safety_eligible_production_count"] = 0
        payload["production_action"] = "FORBIDDEN"
        payload["production_authorized"] = False
        payload["invoked_agents"] = []
        payload["disclaimer"] = DISCLAIMER
        return payload


def json_blob(model: BaseModel) -> str:
    return model.model_dump_json().lower()
