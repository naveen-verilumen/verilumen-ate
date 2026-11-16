"""Contracts for the evidence-backed engineering recommendation engine.

Strictly advisory. Production action is FORBIDDEN. Production authorization is False.
Safety-eligible production is 0.0.
"""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from yield_improvement.reporting.contract import (
    DISCLAIMER as REPORTING_DISCLAIMER,
    EXTRA_FORBIDDEN_PHRASES,
    SAFETY_STATEMENT as REPORTING_SAFETY_STATEMENT,
)
from yield_improvement.validation.contract import FORBIDDEN_OUTPUT_PHRASES

RecommendationCategory = Literal[
    "Lot investigation",
    "Wafer investigation",
    "Spatial investigation",
    "Parametric investigation",
    "Equipment investigation",
    "Environmental investigation",
    "Test measurement/repeatability investigation",
    "Near-limit investigation",
    "Data-quality investigation",
]

PriorityTier = Literal["HIGH", "MEDIUM", "LOW"]
ConfidenceTier = Literal["HIGH", "MODERATE", "LOW", "INSUFFICIENT"]
MLEvidenceStatus = Literal["SUPPORTED", "NEEDS_MORE_DATA", "NOT_AVAILABLE"]

FeedbackStatus = Literal[
    "PROPOSED",
    "ACCEPTED_FOR_INVESTIGATION",
    "IN_PROGRESS",
    "CONFIRMED",
    "REJECTED",
    "INCONCLUSIVE",
    "VALIDATION_PENDING",
    "CLOSED",
]

EvidenceClassification = Literal[
    "OBSERVED_FACT",
    "STATISTICAL_ASSOCIATION",
    "UNCONFIRMED_HYPOTHESIS",
    "INSUFFICIENT_EVIDENCE",
]

EvidenceStrength = Literal["STRONG", "MODERATE", "WEAK", "INSUFFICIENT"]


RECOMMENDATION_DISCLAIMER = (
    "Advisory engineering recommendation only. Production action is FORBIDDEN. "
    "safety_eligible_production is 0%. This is not a confirmed root cause and not a promised yield gain."
)

ALL_FORBIDDEN_PHRASES = tuple(
    set(FORBIDDEN_OUTPUT_PHRASES + EXTRA_FORBIDDEN_PHRASES + (
        "approved for production",
        "authorized for production",
        "guaranteed yield",
        "set limit",
        "change limit",
        "modify recipe",
        "apply to production",
    ))
)


def _validate_no_forbidden_phrases(blob: str) -> None:
    lower_blob = blob.lower()
    for phrase in ALL_FORBIDDEN_PHRASES:
        if phrase in lower_blob:
            raise ValueError(f"forbidden phrase in recommendation output: {phrase}")


class ValidationStep(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    step_number: int = Field(ge=1)
    step_id: str
    title: str
    investigation_action: str
    required_evidence: str
    expected_measurement: str
    acceptance_criteria: str
    rejection_criteria: str
    limitations_and_safety: str


class ValidationProtocol(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    protocol_id: str
    target_hypothesis: str | None = None
    steps: list[ValidationStep] = Field(default_factory=list)
    control_comparison: str | None = None
    replication_check: str
    physical_fa_or_metrology: str | None = None
    split_lot_proposal: str | None = None
    downstream_reliability_risk: str
    disclaimer: str = RECOMMENDATION_DISCLAIMER


class SupportingEvidenceItem(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    evidence_type: str
    evidence_classification: EvidenceClassification
    source_dataset: str
    source_artifact: str
    entity_scope: str
    numerator: int | None = None
    denominator: int | None = None
    observed_value: float | int | str | None = None
    baseline_value: float | int | str | None = None
    comparison_baseline: str | None = None
    unit: str | None = None
    time_scope: str = "FIRST_PASS"
    validation_state: str = "NOT_EVALUATED"
    limitations: list[str] = Field(default_factory=list)


class EngineeringRecommendation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    # Identification
    recommendation_id: str
    hypothesis_id: str | None = None
    title: str
    summary: str = ""
    recommendation_category: RecommendationCategory
    status: FeedbackStatus = "PROPOSED"
    scope: Literal["GLOBAL", "LOT_SPECIFIC"] = "GLOBAL"
    lot_id: str | None = None


    # Priority & Ranking

    priority_rank: int = Field(ge=1)
    priority_tier: PriorityTier
    confidence_tier: ConfidenceTier
    ranking_score: float = Field(ge=0.0, le=1.0)
    ranking_rationale: str

    # Evidence
    observed_pattern: str
    target_population: str
    affected_die_count: int = Field(ge=0)
    eligible_die_count: int = Field(ge=1)
    subgroup_die_count: int | None = Field(default=None, ge=1)
    subgroup_failed_die_count: int | None = Field(default=None, ge=0)
    observed_failure_rate: float = Field(ge=0.0, le=1.0)
    baseline_failure_rate: float = Field(ge=0.0, le=1.0)
    supporting_detectors: list[str] = Field(default_factory=list)
    hypothesis_confidence: str
    ml_evidence_status: MLEvidenceStatus
    ml_evidence_notes: str
    missing_evidence: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)

    # Traceability & Evidence Quality
    observed_facts: list[str] = Field(default_factory=list)
    supporting_evidence: list[SupportingEvidenceItem] = Field(default_factory=list)
    evidence_strength: EvidenceStrength = "INSUFFICIENT"
    uncertainties: list[str] = Field(default_factory=list)
    data_gaps: list[str] = Field(default_factory=list)
    recommended_next_steps: list[str] = Field(default_factory=list)
    validation_status: str = "NOT_EVALUATED"


    # Action and reasoning
    recommended_action: str
    reason: str
    expected_information: str
    validation_method: str
    success_criteria: str
    required_data: list[str] = Field(default_factory=list)
    risk_if_ignored: str
    next_step_if_confirmed: str
    next_step_if_rejected: str

    # Validation
    validation_protocol: ValidationProtocol

    # Opportunity
    observed_loss_rate: float = Field(ge=0.0, le=1.0)
    upper_bound_rate: float | None = None
    upper_bound_count: int | None = None
    plausible_rate: float | None = None
    plausible_count: int | None = None
    safety_eligible_production_rate: Literal[0.0] = 0.0
    safety_eligible_production_count: Literal[0] = 0
    opportunity_disclaimer: str = (
        "Observed associated loss and upper-bound opportunities are diagnostic upper limits. "
        "They do not guarantee yield recovery. Safety-eligible production is 0%. Overlapping slices must not be summed."
    )

    # Safety Invariants
    production_action: Literal["FORBIDDEN"] = "FORBIDDEN"
    production_authorized: Literal[False] = False
    not_a_root_cause: Literal[True] = True
    safety_statement: str = REPORTING_SAFETY_STATEMENT
    safety_status: str = "ADVISORY_ONLY: Production action is FORBIDDEN. Production authorized: False."


    @field_validator("safety_eligible_production_rate")
    @classmethod
    def _rate_zero(cls, value: float) -> float:
        if value != 0.0:
            raise ValueError("safety_eligible_production_rate must be exactly 0.0")
        return 0.0

    @field_validator("safety_eligible_production_count")
    @classmethod
    def _count_zero(cls, value: int) -> int:
        if value != 0:
            raise ValueError("safety_eligible_production_count must be exactly 0")
        return 0

    @field_validator("production_action")
    @classmethod
    def _action_forbidden(cls, value: str) -> str:
        if value != "FORBIDDEN":
            raise ValueError("production_action must be FORBIDDEN")
        return "FORBIDDEN"

    @field_validator("production_authorized")
    @classmethod
    def _not_authorized(cls, value: bool) -> bool:
        if value is not False:
            raise ValueError("production_authorized must be False")
        return False

    @field_validator("not_a_root_cause")
    @classmethod
    def _root_cause_flag(cls, value: bool) -> bool:
        if value is not True:
            raise ValueError("not_a_root_cause must be True")
        return True

    @model_validator(mode="after")
    def _check_forbidden_language(self) -> EngineeringRecommendation:
        dump_str = self.model_dump_json()
        _validate_no_forbidden_phrases(dump_str)
        return self


class FeedbackRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    feedback_id: str
    recommendation_id: str
    dataset_id: str
    previous_status: FeedbackStatus
    new_status: FeedbackStatus
    engineer: str
    investigation_notes: str
    evidence_collected: list[str] = Field(default_factory=list)
    timestamp: str  # UTC ISO-8601
    investigation_conclusion: str | None = None
    hypothesis_confirmed: bool | None = None
    independent_validation_evidence: str | None = None
    validation_dataset: str | None = None
    pre_investigation_metrics: dict[str, Any] | None = None
    post_investigation_metrics: dict[str, Any] | None = None
    adverse_effects: str | None = None
    separately_authorized_corrective_action_ref: str | None = None

    # Safety Invariants
    production_action: Literal["FORBIDDEN"] = "FORBIDDEN"
    production_authorized: Literal[False] = False
    safety_eligible_production_rate: Literal[0.0] = 0.0

    @field_validator("production_action")
    @classmethod
    def _action_forbidden(cls, value: str) -> str:
        if value != "FORBIDDEN":
            raise ValueError("Feedback cannot authorize production action")
        return "FORBIDDEN"

    @field_validator("production_authorized")
    @classmethod
    def _not_authorized(cls, value: bool) -> bool:
        if value is not False:
            raise ValueError("Feedback cannot authorize production")
        return False

    @field_validator("safety_eligible_production_rate")
    @classmethod
    def _rate_zero(cls, value: float) -> float:
        if value != 0.0:
            raise ValueError("safety_eligible_production_rate must remain 0.0")
        return 0.0


class FeedbackCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    new_status: FeedbackStatus
    engineer: str = Field(min_length=1, max_length=100)
    investigation_notes: str = Field(min_length=1, max_length=5000)
    evidence_collected: list[str] = Field(default_factory=list)
    investigation_conclusion: str | None = Field(default=None, max_length=2000)
    hypothesis_confirmed: bool | None = None
    independent_validation_evidence: str | None = Field(default=None, max_length=2000)
    validation_dataset: str | None = Field(default=None, max_length=200)
    pre_investigation_metrics: dict[str, Any] | None = None
    post_investigation_metrics: dict[str, Any] | None = None
    adverse_effects: str | None = Field(default=None, max_length=2000)
    separately_authorized_corrective_action_ref: str | None = Field(default=None, max_length=200)


class FeedbackHistoryResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    recommendation_id: str
    dataset_id: str
    current_status: FeedbackStatus
    history: list[FeedbackRecord] = Field(default_factory=list)


class RecommendationBundle(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    dataset_id: str
    selected_lot_id: str | None = None
    lot_note: str | None = None
    recommendation_count: int
    recommendations: list[EngineeringRecommendation] = Field(default_factory=list)

    ranking_policy: str
    ranking_version: str
    evidence_limitations_summary: list[str] = Field(default_factory=list)
    ml_evidence_status: MLEvidenceStatus
    ml_evidence_summary: str
    safety_invariants: dict[str, Any] = Field(
        default_factory=lambda: {
            "production_action": "FORBIDDEN",
            "production_authorized": False,
            "safety_eligible_production": 0.0,
        }
    )
    production_action: Literal["FORBIDDEN"] = "FORBIDDEN"
    production_authorized: Literal[False] = False
    safety_eligible_production_rate: Literal[0.0] = 0.0
    disclaimer: str = RECOMMENDATION_DISCLAIMER
