"""Yield opportunity contracts. Analytical estimates only. Production eligibility is 0."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

AttributionMode = Literal["PRIMARY_FAILURE", "ANY_FAIL"]
OpportunityStatus = Literal[
    "OBSERVED",
    "ESTIMATED",
    "PRELIMINARY",
    "INSUFFICIENT_DATA",
    "OVERLAPPING",
    "NOT_ESTIMABLE",
    "NOT_ELIGIBLE_FOR_PRODUCTION",
]

DISCLAIMER = (
    "Observed loss is not a predicted FPY gain. Upper bound assumes every fail in this "
    "slice is recoverable, which is usually false. Safety-eligible production opportunity is 0%."
)


class Opportunity(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    opportunity_id: str
    hypothesis_id: str | None
    family: str | None = None
    detail: str | None = None
    association_class: str | None = None
    attribution_mode: AttributionMode
    status: OpportunityStatus
    status_flags: list[str] = Field(default_factory=list)
    observed_loss_count: int
    observed_loss_rate: float
    upper_bound_count: int | None
    upper_bound_rate: float | None
    plausible_count: int | None
    plausible_rate: float | None
    plausible_unavailable: bool
    safety_eligible_production_count: Literal[0] = 0
    safety_eligible_production_rate: Literal[0.0] = 0.0
    overlap_count: int = 0
    union_count: int | None = None
    exclusive_count: int | None = None
    intersection_count: int = 0
    included_in_union: bool = False
    evidence_tier: str | None = None
    evidence_score: float | None = None
    eligible_population: int
    affected_population_count: int
    population_definition: str
    affected_die_ids: list[str] = Field(default_factory=list)
    calculation_method: str
    calibration_status: Literal["TO_BE_CALIBRATED", "PRELIMINARY"] = "PRELIMINARY"
    assumptions: list[str] = Field(default_factory=list)
    data_gaps: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    statement: str = ""
    disclaimer: str = DISCLAIMER

    @field_validator("safety_eligible_production_rate")
    @classmethod
    def _prod_rate_zero(cls, value: float) -> float:
        if value != 0.0:
            raise ValueError("safety_eligible_production_rate must be 0")
        return 0.0

    @field_validator("safety_eligible_production_count")
    @classmethod
    def _prod_count_zero(cls, value: int) -> int:
        if value != 0:
            raise ValueError("safety_eligible_production_count must be 0")
        return 0

    @model_validator(mode="after")
    def _flags_forbid_production(self) -> Opportunity:
        if "NOT_ELIGIBLE_FOR_PRODUCTION" not in self.status_flags:
            raise ValueError("status_flags must include NOT_ELIGIBLE_FOR_PRODUCTION")
        if "APPROVED_FOR_PRODUCTION" in self.status_flags:
            raise ValueError("APPROVED_FOR_PRODUCTION is not a V1 opportunity status")
        return self


class OpportunitySummary(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    current_fpy: float | None
    eligible_population: int
    observed_loss_count: int
    observed_loss_rate: float
    attribution_mode: AttributionMode
    sum_of_individual_upper_bounds_rate: float
    sum_of_individual_upper_bounds_exceeds_observed: bool
    union_upper_bound_count: int
    union_upper_bound_rate: float
    intersection_fail_count: int
    plausible_total_rate: float | None
    plausible_unavailable: bool
    safety_eligible_total_count: Literal[0] = 0
    safety_eligible_total_rate: Literal[0.0] = 0.0
    no_actionable_opportunity: bool
    calculation_method: str
    calibration_status: Literal["TO_BE_CALIBRATED", "PRELIMINARY"] = "PRELIMINARY"


class OpportunityBundle(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    analysis_id: str
    attribution_mode: AttributionMode
    summary: OpportunitySummary
    opportunities: list[Opportunity] = Field(default_factory=list)
    no_actionable_opportunity: bool
    data_gaps: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    disclaimer: str = DISCLAIMER
    calibration_status: Literal["TO_BE_CALIBRATED", "PRELIMINARY"] = "PRELIMINARY"
    config_versions: dict[str, str] = Field(default_factory=dict)

    def to_public_dict(self) -> dict[str, Any]:
        payload = self.model_dump(mode="json")
        payload.pop("approved_for_production", None)
        payload["disclaimer"] = DISCLAIMER
        payload["summary"]["safety_eligible_total_rate"] = 0.0
        payload["summary"]["safety_eligible_total_count"] = 0
        for item in payload.get("opportunities", []):
            item["safety_eligible_production_rate"] = 0.0
            item["safety_eligible_production_count"] = 0
            item["disclaimer"] = DISCLAIMER
            item.pop("approved_for_production", None)
        return payload
