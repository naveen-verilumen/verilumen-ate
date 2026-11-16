"""Pydantic schemas for YAML configuration. Malformed files raise ConfigError."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class LaxModel(BaseModel):
    """Nested YAML that may grow keys; required fields still validated."""

    model_config = ConfigDict(extra="allow", frozen=True)


class FpyFormula(FrozenModel):
    numerator: str
    denominator: str
    invariant: str


class PartClassMissing(FrozenModel):
    treat_as: str
    flag: str
    status: str


class DuplicateRule(FrozenModel):
    same_die_distinct_attempts: str
    same_die_same_attempt_id_same_timestamp: str
    same_die_same_attempt_id_different_payload: str


class IdentityPolicy(FrozenModel):
    primary: list[str]
    fallback_xy: str


class PassFailFromBin(FrozenModel):
    if_pass_fail_present: str
    elif_sbin_mappable: str
    else_field: str = Field(alias="else")

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)


class ParametricEquality(FrozenModel):
    UPPER_fail_iff: str
    LOWER_fail_iff: str
    equality: str


class FpyPolicy(FrozenModel):
    fpy_policy_version: str
    status: str
    insertion: str
    formula: FpyFormula
    abort_policy: str
    abort_is_first_pass_fail: bool
    part_class_missing: PartClassMissing
    excluded_part_classes: list[str]
    excluded_if: list[str]
    duplicate_rule: DuplicateRule
    identity: IdentityPolicy
    pass_fail_from_bin: PassFailFromBin
    parametric_equality: ParametricEquality
    escape_rate: str

    @field_validator("excluded_part_classes")
    @classmethod
    def _nonempty_classes(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("excluded_part_classes must not be empty")
        return value


class TaxonomyFamily(LaxModel):
    details: list[str]
    meaning: str | None = None
    requires: str | None = None


class MappingRule(LaxModel):
    id: str
    rule: str


class TaxonomyConfig(LaxModel):
    taxonomy_version: str
    status: str
    separator: str
    format: str
    families: dict[str, TaxonomyFamily]
    mapping_rules: list[MappingRule] | None = None
    primary_selection_order_for_die: list[str] | None = None
    forbidden: list[str] | None = None

    def allowed_codes(self) -> set[str]:
        codes: set[str] = set()
        sep = self.separator
        for family, spec in self.families.items():
            for detail in spec.details:
                codes.add(f"{family}{sep}{detail}")
        return codes

    def split(self, code: str) -> tuple[str, str]:
        if self.separator not in code:
            return "UNKNOWN", "UNSPECIFIED"
        family, detail = code.split(self.separator, 1)
        allowed = self.allowed_codes()
        if code not in allowed:
            return "UNKNOWN", "UNMAPPED_CODE"
        return family, detail


class BinRow(LaxModel):
    bin_number: int
    bin_kind: str
    bin_name: str | None = None
    disposition: str
    failure_code: str | None = None
    taxonomy_code: str | None = None
    notes: str | None = None


class UnmappedBehavior(FrozenModel):
    unknown_sbin: str
    unknown_failure_code: str
    do_not_guess: bool


class BinMapConfig(LaxModel):
    bin_map_version: str
    status: str
    taxonomy_version: str
    sbin: list[BinRow]
    hbin: list[BinRow] = Field(default_factory=list)
    failure_code_map: dict[str, str]
    unmapped_behavior: UnmappedBehavior
    resolution_order: list[str] | None = None

    def sbin_by_number(self) -> dict[int, BinRow]:
        return {row.bin_number: row for row in self.sbin}

    def hbin_by_number(self) -> dict[int, BinRow]:
        return {row.bin_number: row for row in self.hbin}


class SafetyEligibleProduction(FrozenModel):
    value: float
    unit: str
    immutable: bool
    overwrite_allowed: bool

    @model_validator(mode="after")
    def _zero_immutable(self) -> SafetyEligibleProduction:
        if self.immutable and self.value != 0.0:
            raise ValueError("safety_eligible_production.value must be 0 when immutable")
        if self.overwrite_allowed:
            raise ValueError("overwrite_allowed must be false in V1")
        return self


class SpecialistInvestigation(FrozenModel):
    invoked: bool
    domains: list[str]

    @field_validator("invoked")
    @classmethod
    def _never_invoked(cls, value: bool) -> bool:
        if value:
            raise ValueError("potential_specialist_investigation.invoked must be false in V1")
        return value


class DecisionRule(LaxModel):
    id: str
    when: str
    then: str
    note: str | None = None
    safety_violation: bool | None = None
    run_status: str | None = None
    invoked: bool | None = None

    @field_validator("when", mode="before")
    @classmethod
    def _when_must_be_string(cls, value: object) -> str:
        # YAML booleans (`when: true`) are rejected. Use a quoted predicate
        # such as "ALWAYS" for the fail-closed default.
        if isinstance(value, bool):
            raise ValueError(
                "decision_table.when must be a quoted string, not a YAML boolean. "
                "Use when: \"ALWAYS\" for the fail-closed default."
            )
        return str(value)


class EscapeRatePolicy(FrozenModel):
    v1_status: str
    infer_from_fpy: bool


class SafetyConfig(LaxModel):
    policy_version: str
    status: str
    principle_order: list[str]
    safety_eligible_production: SafetyEligibleProduction
    production_action: str
    escape_rate: EscapeRatePolicy
    allowed_actions: list[str]
    forbidden_actions: list[str]
    recommendation_status: list[str]
    potential_specialist_investigation: SpecialistInvestigation
    decision_table: list[DecisionRule]
    independent_of_opportunity: bool
    engineering_recommendation_states: list[str] | None = None
    phase6_validation: dict[str, Any] | None = None


class CalibrationConfig(LaxModel):
    calibration_version: str
    status: str
    parameters: dict[str, Any]
    evaluation_bars: dict[str, Any] | None = None
    hard_bars_not_calibrated: dict[str, Any] | None = None


class AllowlistConfig(LaxModel):
    allowlist_version: str
    status: str
    agent_may_read: list[str]
    agent_must_not_read: list[str]
    forbidden_columns_on_agent_visible_tables: list[str]
    forbidden_imports: list[str]
    potential_specialist_investigation: dict[str, Any] | None = None
