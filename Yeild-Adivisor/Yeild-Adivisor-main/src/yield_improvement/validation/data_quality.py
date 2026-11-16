"""Data-quality gate. Never fabricates missing fields."""

from __future__ import annotations

from yield_improvement.config.loader import AppConfig
from yield_improvement.detectors.population import DetectorContext
from yield_improvement.models.results import DataQualityIssue
from yield_improvement.opportunity.contract import Opportunity
from yield_improvement.validation.contract import GateTrace
from yield_improvement.validation.quality import collect_quality_issues


def _required_missing(family: str | None, detail: str | None, ctx: DetectorContext) -> list[str]:
    gaps: list[str] = []
    if family == "SPATIAL" and not any(d.x is not None and d.y is not None for d in ctx.dies):
        gaps.append("missing_x_y")
    if family == "EQUIPMENT" and not any(d.tester_id for d in ctx.dies):
        gaps.append("missing_tester_id")
    if family == "CONTACT" and not any(d.probe_card_id for d in ctx.dies):
        gaps.append("missing_probe_card_id")
    if family == "ENVIRONMENT" and not any(d.temperature_c is not None for d in ctx.dies):
        gaps.append("missing_temperature_c")
    if family == "PROCESS" and detail == "DRIFT" and not any(d.timestamp for d in ctx.dies):
        gaps.append("missing_timestamp")
    if family == "PARAMETRIC" and not ctx.parametric:
        gaps.append("missing_parametric_measurements")
    if family == "TEST" and detail == "LIMIT_SENSITIVITY":
        if not ctx.parametric:
            gaps.append("missing_parametric_measurements")
        elif all(r.lower_limit is None and r.upper_limit is None for r in ctx.parametric):
            gaps.append("missing_limits")
    if family == "TEST" and detail == "SEQUENCE":
        gaps.append("stop_on_fail_censors_later_tests")
    if family == "CORRELATED" and not ctx.test_results:
        gaps.append("missing_test_results")
    return gaps


def evaluate_data_quality(
    opportunity: Opportunity,
    ctx: DetectorContext,
    config: AppConfig,
    issues: list[DataQualityIssue] | None = None,
) -> GateTrace:
    collected = issues if issues is not None else collect_quality_issues(ctx.attempts, ctx.test_results, config)
    reasons: list[str] = []
    if ctx.n_eligible < 1:
        return GateTrace(
            name="DATA_QUALITY",
            status="FAIL",
            recommendation="NEEDS_MORE_DATA",
            reasons=["cannot_calculate_fpy_denominator"],
        )
    errors = [i for i in collected if i.severity == "ERROR"]
    if errors:
        return GateTrace(
            name="DATA_QUALITY",
            status="FAIL",
            recommendation="NEEDS_MORE_DATA",
            reasons=[f"{i.code}:{i.message}" for i in errors[:8]],
        )
    missing = _required_missing(opportunity.family, opportunity.detail, ctx)
    if missing:
        return GateTrace(
            name="DATA_QUALITY",
            status="UNAVAILABLE",
            recommendation="NEEDS_MORE_DATA",
            reasons=missing,
        )
    warnings = [i for i in collected if i.severity in {"WARNING", "UNAVAILABLE", "ASSUMPTION"}]
    if warnings:
        reasons = [i.code for i in warnings[:8]]
        return GateTrace(name="DATA_QUALITY", status="WARNING", reasons=reasons)
    return GateTrace(name="DATA_QUALITY", status="PASS", reasons=["required_fields_present_for_this_family"])
