"""Copy Phase 6 validation and investigation steps. Does not re-decide recommendations."""

from __future__ import annotations

from yield_improvement.hypotheses.contract import HypothesisBundle
from yield_improvement.reporting.contract import (
    CENSORING_NOTICE,
    NEAR_LIMIT_NOTICE,
    NO_ACTIONABLE_NOTICE,
    ReportDataGaps,
    ReportInvestigationItem,
    ReportValidation,
)
from yield_improvement.validation.contract import ValidationBundle, ValidationResult

_REQUIRED_TOKENS = (
    "missing_x_y",
    "missing_tester",
    "missing_denominator",
    "cannot_calculate_fpy",
    "missing_parametric",
    "missing_limits",
    "missing_timestamp",
    "missing_temperature",
    "missing_probe",
    "missing_eligible",
    "missing identifiers",
)
_DETECTOR_TOKENS = (
    "stop_on_fail",
    "stop-on-fail",
    "censored",
    "sequence",
)


def _validation_id(item: ValidationResult) -> str:
    """Presentation alias. Not a new analytical object."""
    return f"VAL-{item.opportunity_id}"


def build_validation_rows(bundle: ValidationBundle) -> list[ReportValidation]:
    rows: list[ReportValidation] = []
    for item in bundle.results:
        rows.append(
            ReportValidation(
                validation_id=_validation_id(item),
                analysis_id=item.analysis_id,
                hypothesis_id=item.hypothesis_id,
                opportunity_id=item.opportunity_id,
                family=item.family,
                detail=item.detail,
                recommendation=item.recommendation,
                recommendation_reason=item.recommendation_reason,
                safety_status=item.safety_status,
                data_quality_status=item.data_quality_status,
                population_status=item.population_status,
                evidence_status=item.evidence_status,
                conflict_status=item.conflict_status,
                conflict_type=item.conflict_type,
                validation_required=list(item.validation_required),
                validation_steps=list(item.validation_steps),
                conflicting_detectors=list(item.conflicting_detectors),
                data_gaps=list(item.data_gaps),
                production_action="FORBIDDEN",
                production_authorized=False,
                safety_eligible_production_count=0,
                safety_eligible_production_rate=0.0,
            )
        )
    return rows


def build_investigation_plan(
    hypotheses: HypothesisBundle,
    validation: ValidationBundle,
) -> list[ReportInvestigationItem]:
    if validation.no_actionable_recommendation:
        return []
    rank = {h.hypothesis_id: h.rank for h in hypotheses.hypotheses}
    items = list(validation.results)

    def _key(item: ValidationResult) -> tuple[int, str]:
        if item.hypothesis_id and item.hypothesis_id in rank:
            return (rank[item.hypothesis_id], item.opportunity_id)
        return (10_000, item.opportunity_id)

    items.sort(key=_key)
    plan: list[ReportInvestigationItem] = []
    for item in items:
        plan.append(
            ReportInvestigationItem(
                hypothesis_id=item.hypothesis_id,
                family=item.family,
                detail=item.detail,
                recommendation=item.recommendation,
                steps=list(item.validation_steps),
            )
        )
    return plan


def _classify(gap: str) -> str:
    low = gap.lower()
    if any(token in low for token in _REQUIRED_TOKENS):
        return "required"
    if any(token in low for token in _DETECTOR_TOKENS):
        return "detector_specific"
    return "recommended"


def build_data_gaps(
    hypotheses: HypothesisBundle,
    validation: ValidationBundle,
    extra: list[str],
) -> ReportDataGaps:
    seen: list[str] = []
    for source in (extra, hypotheses.data_gaps, validation.data_gaps):
        for gap in source:
            if gap not in seen:
                seen.append(gap)
    for item in validation.results:
        for gap in item.data_gaps:
            if gap not in seen:
                seen.append(gap)
    required: list[str] = []
    recommended: list[str] = []
    detector_specific: list[str] = []
    for gap in seen:
        bucket = _classify(gap)
        if bucket == "required":
            required.append(gap)
        elif bucket == "detector_specific":
            detector_specific.append(gap)
        else:
            recommended.append(gap)
    return ReportDataGaps(
        required=required,
        recommended=recommended,
        detector_specific=detector_specific,
        ungrouped=[],
    )


def near_limit_notice(validation: ValidationBundle, hypotheses: HypothesisBundle) -> str | None:
    if any(item.detail == "LIMIT_SENSITIVITY" for item in validation.results):
        return NEAR_LIMIT_NOTICE
    if any(h.detail == "LIMIT_SENSITIVITY" for h in hypotheses.hypotheses):
        return NEAR_LIMIT_NOTICE
    return None


def sequence_censoring_notice(validation: ValidationBundle, hypotheses: HypothesisBundle) -> str | None:
    blob = " ".join(validation.limitations).lower()
    if "stop-on-fail" in blob or "censored" in blob:
        return CENSORING_NOTICE
    if hypotheses.detector_summary.get("sequence") == "INSUFFICIENT_DATA":
        return CENSORING_NOTICE
    return None


def no_actionable_notice(validation: ValidationBundle, hypotheses: HypothesisBundle) -> str | None:
    if validation.no_actionable_recommendation or hypotheses.no_confident_hypothesis:
        return NO_ACTIONABLE_NOTICE
    return None
