"""Phase 7 engineering-report contracts. Presentation only. Production remains forbidden."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from yield_improvement.validation.contract import FORBIDDEN_OUTPUT_PHRASES

ProductionAction = Literal["FORBIDDEN"]
AttributionMode = Literal["PRIMARY_FAILURE", "ANY_FAIL"]

EXTRA_FORBIDDEN_PHRASES = (
    "fpy can improve",
    "the root cause is",
    "will recover",
    "candidate limit",
    "recommended limit",
    "new limit",
    "expected yield improvement",
    "guaranteed improvement",
    "edge_and_drift",
    "edge + drift root cause",
)

SAFETY_STATEMENT = (
    "PRODUCTION ACTION: FORBIDDEN. "
    "SAFETY-ELIGIBLE PRODUCTION: 0. "
    "PRODUCTION AUTHORIZED: NO. "
    "This analysis is advisory. No production change is authorized."
)

NEAR_LIMIT_NOTICE = (
    "Near-limit evidence requires engineering validation. "
    "This system does not recommend or modify test limits."
)

CENSORING_NOTICE = (
    "Sequence evidence is censored because later tests are not observed "
    "after an earlier failure."
)

NO_ACTIONABLE_NOTICE = "No actionable hypothesis identified."

EVIDENCE_SCORE_NOTICE = (
    "Evidence score is a preliminary analytical score. "
    "It is not a probability of root cause or probability of recovery."
)

OVERLAP_NOTICE = "Individual opportunities must not be summed when populations overlap."

DISCLAIMER = (
    "Advisory engineering report only. Production action is FORBIDDEN. "
    "safety_eligible_production is 0%. This is not a confirmed root cause and not a predicted FPY gain."
)


def _blob(model: BaseModel) -> str:
    return model.model_dump_json().lower()


class ReportParetoRow(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    attribution_mode: AttributionMode
    failure_key: str
    family: str | None = None
    detail: str | None = None
    affected_die_count: int
    percentage_of_eligible: float
    share_of_fails: float
    selection_rule: str | None = None
    taxonomy_code: str | None = None


class ReportFpySummary(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    eligible_die_count: int
    first_pass_pass_count: int
    first_pass_fail_count: int
    excluded_count: int
    fpy: float | None
    fpy_loss: float | None
    fpy_policy_version: str
    abort_policy: str
    policy_notes: list[str] = Field(default_factory=list)


class ReportLossSummary(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    primary_failure: list[ReportParetoRow] = Field(default_factory=list)
    any_fail: list[ReportParetoRow] = Field(default_factory=list)
    primary_available: bool
    primary_unavailable_note: str | None = None
    modes_not_combined: Literal[True] = True


class ReportEvidenceFinding(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    detector: str
    status: str
    family: str | None = None
    detail: str | None = None
    method: str
    effect_size: float | None = None
    effect_size_metric: str | None = None
    p_value: float | None = None
    adjusted_p_value: float | None = None
    sample_size: int | None = None
    data_gaps: list[str] = Field(default_factory=list)
    not_a_root_cause: Literal[True] = True


class ReportHypothesis(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    rank: int
    hypothesis_id: str
    family: str
    detail: str
    status: str
    statement: str
    explanation: str
    why_it_exists: str
    association_class: str
    evidence_tier: str
    evidence_score: float
    score_status: str
    supporting_detectors: list[str] = Field(default_factory=list)
    conflicting_detectors: list[str] = Field(default_factory=list)
    statistical_evidence: list[dict[str, Any]] = Field(default_factory=list)
    effect_sizes: list[dict[str, Any]] = Field(default_factory=list)
    affected_population: dict[str, Any] | None = None
    data_coverage: dict[str, Any] = Field(default_factory=dict)
    data_gaps: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    validation_required: list[str] = Field(default_factory=list)
    validation_steps: list[str] = Field(default_factory=list)
    validation_recommendation: str | None = None
    opportunity_id: str | None = None
    observed_loss_rate: float | None = None
    upper_bound_rate: float | None = None
    plausible_rate: float | None = None
    plausible_unavailable: bool = True
    overlap_count: int | None = None
    exclusive_count: int | None = None
    union_count: int | None = None
    intersection_count: int | None = None
    not_a_root_cause: Literal[True] = True


class ReportOpportunity(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    opportunity_id: str
    hypothesis_id: str | None
    family: str | None = None
    detail: str | None = None
    attribution_mode: AttributionMode
    status: str
    observed_loss_count: int
    observed_loss_rate: float
    upper_bound_count: int | None = None
    upper_bound_rate: float | None = None
    plausible_count: int | None = None
    plausible_rate: float | None = None
    plausible_unavailable: bool
    plausible_label: str
    calibration_status: str
    affected_population_count: int
    population_definition: str
    included_in_union: bool = False
    overlap_count: int = 0
    exclusive_count: int | None = None
    union_count: int | None = None
    intersection_count: int = 0
    statement: str
    safety_eligible_production_rate: Literal[0.0] = 0.0


class ReportOverlap(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    sum_of_individual_upper_bounds_rate: float | None = None
    union_upper_bound_rate: float | None = None
    union_upper_bound_count: int | None = None
    intersection_fail_count: int | None = None
    sum_exceeds_observed: bool | None = None
    note: str
    individuals: list[dict[str, Any]] = Field(default_factory=list)


class ReportValidation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    validation_id: str
    analysis_id: str
    hypothesis_id: str | None
    opportunity_id: str
    family: str | None = None
    detail: str | None = None
    recommendation: str
    recommendation_reason: str
    safety_status: str
    data_quality_status: str
    population_status: str
    evidence_status: str
    conflict_status: str | None = None
    conflict_type: str | None = None
    validation_required: list[str] = Field(default_factory=list)
    validation_steps: list[str] = Field(default_factory=list)
    conflicting_detectors: list[str] = Field(default_factory=list)
    data_gaps: list[str] = Field(default_factory=list)
    production_action: ProductionAction = "FORBIDDEN"
    production_authorized: Literal[False] = False
    safety_eligible_production_count: Literal[0] = 0
    safety_eligible_production_rate: Literal[0.0] = 0.0


class ReportInvestigationItem(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    hypothesis_id: str | None
    family: str | None
    detail: str | None
    recommendation: str | None
    steps: list[str] = Field(default_factory=list)


class ReportDataGaps(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    required: list[str] = Field(default_factory=list)
    recommended: list[str] = Field(default_factory=list)
    detector_specific: list[str] = Field(default_factory=list)
    ungrouped: list[str] = Field(default_factory=list)


class ReportTraceability(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    report_id: str
    analysis_id: str
    dataset_id: str
    pipeline_version: str
    generated_at: str
    fpy_policy_version: str
    calibration_version: str
    safety_policy_version: str
    config_versions: dict[str, str] = Field(default_factory=dict)
    hypothesis_ids: list[str] = Field(default_factory=list)
    opportunity_ids: list[str] = Field(default_factory=list)
    validation_ids: list[str] = Field(default_factory=list)
    detector_ids: list[str] = Field(default_factory=list)


class ReportSummary(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    text: str
    eligible_die_count: int
    first_pass_pass_count: int
    first_pass_fail_count: int
    fpy: float | None
    fpy_loss_rate: float | None
    n_signal_detectors: int
    n_hypotheses: int
    n_investigate: int
    largest_observed_associated_loss_rate: float | None


class EngineeringReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    report_id: str
    analysis_id: str
    generated_at: str
    dataset_id: str
    executive_summary: ReportSummary
    fpy_summary: ReportFpySummary
    loss_summary: ReportLossSummary
    evidence_findings: list[ReportEvidenceFinding] = Field(default_factory=list)
    hypotheses: list[ReportHypothesis] = Field(default_factory=list)
    opportunities: list[ReportOpportunity] = Field(default_factory=list)
    overlap: ReportOverlap
    validation: list[ReportValidation] = Field(default_factory=list)
    no_actionable_recommendation: bool
    investigation_plan: list[ReportInvestigationItem] = Field(default_factory=list)
    data_gaps: ReportDataGaps
    limitations: list[str] = Field(default_factory=list)
    safety_statement: str
    near_limit_notice: str | None = None
    sequence_censoring_notice: str | None = None
    no_actionable_notice: str | None = None
    evidence_score_notice: str = EVIDENCE_SCORE_NOTICE
    overlap_notice: str = OVERLAP_NOTICE
    traceability: ReportTraceability
    configuration_versions: dict[str, str] = Field(default_factory=dict)
    production_action: ProductionAction = "FORBIDDEN"
    production_authorized: Literal[False] = False
    safety_eligible_production_count: Literal[0] = 0
    safety_eligible_production_rate: Literal[0.0] = 0.0
    invoked_agents: list[str] = Field(default_factory=list)
    disclaimer: str = DISCLAIMER
    pipeline_version: str

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
            raise ValueError("invoked_agents must be empty")
        return []

    @model_validator(mode="after")
    def _no_forbidden_phrases(self) -> EngineeringReport:
        blob = _blob(self)
        for phrase in FORBIDDEN_OUTPUT_PHRASES + EXTRA_FORBIDDEN_PHRASES:
            if phrase.lower() in blob:
                raise ValueError(f"forbidden phrase in engineering report: {phrase}")
        if self.safety_statement != SAFETY_STATEMENT:
            raise ValueError("safety_statement must be the immutable Phase 7 banner")
        return self

    def to_public_dict(self) -> dict[str, Any]:
        payload = self.model_dump(mode="json")
        payload["production_action"] = "FORBIDDEN"
        payload["production_authorized"] = False
        payload["safety_eligible_production_rate"] = 0.0
        payload["safety_eligible_production_count"] = 0
        payload["invoked_agents"] = []
        payload["safety_statement"] = SAFETY_STATEMENT
        payload["disclaimer"] = DISCLAIMER
        return payload
