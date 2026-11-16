"""Charts from EngineeringReport fields only. Titles are associative, not causal."""

from __future__ import annotations

from yield_improvement.config.test_catalog import format_test_label
from yield_improvement.dashboard.formatting import format_rate
from yield_improvement.reporting.contract import EngineeringReport


def fpy_overview_rows(report: EngineeringReport) -> list[dict[str, float | str]]:
    fpy = report.fpy_summary
    return [
        {"metric": "FPY", "value": 0.0 if fpy.fpy is None else fpy.fpy},
        {"metric": "FPY loss", "value": 0.0 if fpy.fpy_loss is None else fpy.fpy_loss},
    ]


def primary_failure_pareto_rows(report: EngineeringReport) -> list[dict[str, object]]:
    return [
        {
            "failure_key": row.failure_key,
            "label": format_test_label(row.failure_key),
            "dies": row.affected_die_count,
            "share_of_eligible": row.percentage_of_eligible,
            "attribution": "PRIMARY_FAILURE",
        }
        for row in report.loss_summary.primary_failure
    ]


def any_fail_pareto_rows(report: EngineeringReport) -> list[dict[str, object]]:
    return [
        {
            "failure_key": row.failure_key,
            "label": format_test_label(row.failure_key),
            "dies": row.affected_die_count,
            "share_of_eligible": row.percentage_of_eligible,
            "attribution": "ANY_FAIL",
        }
        for row in report.loss_summary.any_fail
    ]


def hypothesis_evidence_rows(report: EngineeringReport) -> list[dict[str, object]]:
    return [
        {
            "rank": hyp.rank,
            "hypothesis": f"{hyp.family}.{hyp.detail}",
            "evidence_score": hyp.evidence_score,
            "tier": hyp.evidence_tier,
        }
        for hyp in report.hypotheses
    ]


def associated_opportunity_rows(report: EngineeringReport) -> list[dict[str, object]]:
    rows = []
    for opp in report.opportunities:
        label = f"{opp.family}.{opp.detail}" if opp.family else opp.opportunity_id
        rows.append(
            {
                "item": label,
                "observed": opp.observed_loss_rate,
                "upper_bound": opp.upper_bound_rate if opp.upper_bound_rate is not None else 0.0,
                "plausible_display": format_rate(opp.plausible_rate)
                if not opp.plausible_unavailable
                else "Not estimable",
            }
        )
    return rows


def overlap_union_rows(report: EngineeringReport) -> list[dict[str, object]]:
    ov = report.overlap
    return [
        {
            "series": "sum of individual upper bounds",
            "rate": ov.sum_of_individual_upper_bounds_rate or 0.0,
        },
        {
            "series": "combined union",
            "rate": ov.union_upper_bound_rate or 0.0,
        },
    ]


def validation_distribution(report: EngineeringReport) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in report.validation:
        counts[item.recommendation] = counts.get(item.recommendation, 0) + 1
    return counts


CHART_TITLES = {
    "fpy": "FPY overview",
    "primary_pareto": "Observed Primary Failure Loss",
    "any_fail_pareto": "Observed Any-Fail Loss (not combined with PRIMARY_FAILURE)",
    "evidence": "Hypothesis evidence scores (preliminary; not P(cause))",
    "opportunity": "Associated Opportunity",
    "overlap": "Overlap versus combined union",
    "validation": "Validation recommendation counts",
}
