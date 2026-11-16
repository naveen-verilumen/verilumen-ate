"""Data-quality and pipeline result contracts."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Severity = Literal["ERROR", "WARNING", "ASSUMPTION", "UNAVAILABLE"]
PipelineStatus = Literal["OK", "INVALID"]


class DataQualityIssue(BaseModel):
    model_config = ConfigDict(frozen=True)

    severity: Severity
    code: str
    message: str
    die_id: str | None = None
    lot_id: str | None = None
    wafer_id: str | None = None
    field: str | None = None
    attempt_id: str | None = None


class Exclusion(BaseModel):
    model_config = ConfigDict(frozen=True)

    die_id: str
    lot_id: str
    wafer_id: str
    reason: str
    notes: str | None = None


class DieOutcome(BaseModel):
    model_config = ConfigDict(frozen=True)

    lot_id: str
    wafer_id: str
    die_id: str
    first_pass_disposition: str
    final_disposition: str | None = None
    fpy_counts_as: str
    attempt_id: str
    part_class: str | None = None
    part_class_assumed_production: bool = False
    abort_flag: bool = False
    retested: bool = False
    primary_failure_key: str | None = None
    primary_failure_code: str | None = None
    primary_failure_family: str | None = None
    primary_failure_detail: str | None = None
    selection_method: str | None = None


class ParetoRow(BaseModel):
    model_config = ConfigDict(frozen=True)

    failure_key: str
    failure_code: str | None = None
    taxonomy_code: str | None = None
    n_dies: int
    contribution: float
    share_of_fails: float
    overlap_allowed: bool
    selection_rule: str | None = None


class CofailRow(BaseModel):
    model_config = ConfigDict(frozen=True)

    die_id: str
    failure_key: str
    attribution_role: Literal["COFAIL"] = "COFAIL"


class PrimaryFailureRow(BaseModel):
    model_config = ConfigDict(frozen=True)

    die_id: str
    lot_id: str
    wafer_id: str
    primary_failure_code: str | None
    primary_failure_key: str
    primary_failure_family: str
    primary_failure_detail: str
    selection_method: str
    taxonomy_code: str


class FpyResult(BaseModel):
    """Structured FPY output — more than a scalar."""

    model_config = ConfigDict(frozen=True)

    status: PipelineStatus
    fpy_policy_version: str
    abort_policy: str
    eligible_die_count: int
    first_pass_pass_count: int
    first_pass_fail_count: int
    excluded_count: int
    fpy: float | None
    fpy_loss: float | None
    final_yield: float | None = None
    retest_rate_of_eligible: float | None = None
    n_retested: int = 0
    retest_recovery: float | None = None
    escape_rate: None = None
    escape_status: str = "unavailable"
    invariant_ok: bool
    part_class_assumed_production: bool = False
    assumed_production_dies: list[str] = Field(default_factory=list)
    exclusions: list[Exclusion] = Field(default_factory=list)
    per_die: list[DieOutcome] = Field(default_factory=list)
    primary_failures: list[PrimaryFailureRow] = Field(default_factory=list)
    primary_fail_pareto: list[ParetoRow] = Field(default_factory=list)
    any_fail_pareto: list[ParetoRow] = Field(default_factory=list)
    cofail: list[CofailRow] = Field(default_factory=list)
    assumptions: list[DataQualityIssue] = Field(default_factory=list)
    data_quality_flags: list[DataQualityIssue] = Field(default_factory=list)
    errors: list[DataQualityIssue] = Field(default_factory=list)
    warnings: list[DataQualityIssue] = Field(default_factory=list)

    # Fixture aliases
    @property
    def n_eligible(self) -> int:
        return self.eligible_die_count

    @property
    def n_first_pass_pass(self) -> int:
        return self.first_pass_pass_count

    @property
    def n_first_pass_fail(self) -> int:
        return self.first_pass_fail_count

    @property
    def n_excluded(self) -> int:
        return self.excluded_count

    def to_public_dict(self) -> dict[str, Any]:
        payload = self.model_dump(mode="json")
        payload["n_eligible"] = self.eligible_die_count
        payload["n_first_pass_pass"] = self.first_pass_pass_count
        payload["n_first_pass_fail"] = self.first_pass_fail_count
        payload["n_excluded"] = self.excluded_count
        return payload
