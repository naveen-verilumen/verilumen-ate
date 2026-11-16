"""Executive summary and FPY/loss presentation. Formatting only; no FPY recalculation."""

from __future__ import annotations

from yield_improvement.detectors.contract import DetectorBundle
from yield_improvement.hypotheses.contract import HypothesisBundle
from yield_improvement.models.results import FpyResult, ParetoRow
from yield_improvement.opportunity.contract import OpportunityBundle
from yield_improvement.reporting.contract import (
    ReportFpySummary,
    ReportLossSummary,
    ReportParetoRow,
    ReportSummary,
)
from yield_improvement.validation.contract import ValidationBundle

POLICY_NOTES = [
    "Retest passes do not count as first-pass passes.",
    "Rework lots/dies are excluded from the FPY denominator.",
    "Engineering and calibration part classes are excluded.",
    "Missing disposition is excluded from the eligible first-pass population.",
]


def _split_code(code: str | None) -> tuple[str | None, str | None]:
    """Presentation split of an existing taxonomy code. Does not remap bins."""
    if not code:
        return None, None
    if "." not in code:
        return code, None
    family, _, detail = code.partition(".")
    return family, detail


def _pareto_rows(rows: list[ParetoRow], mode: str) -> list[ReportParetoRow]:
    out: list[ReportParetoRow] = []
    for row in rows:
        family, detail = _split_code(row.taxonomy_code)
        out.append(
            ReportParetoRow(
                attribution_mode=mode,  # type: ignore[arg-type]
                failure_key=row.failure_key,
                family=family,
                detail=detail,
                affected_die_count=row.n_dies,
                percentage_of_eligible=row.contribution,
                share_of_fails=row.share_of_fails,
                selection_rule=row.selection_rule,
                taxonomy_code=row.taxonomy_code,
            )
        )
    return out


def build_fpy_summary(fpy: FpyResult) -> ReportFpySummary:
    return ReportFpySummary(
        eligible_die_count=fpy.eligible_die_count,
        first_pass_pass_count=fpy.first_pass_pass_count,
        first_pass_fail_count=fpy.first_pass_fail_count,
        excluded_count=fpy.excluded_count,
        fpy=fpy.fpy,
        fpy_loss=fpy.fpy_loss,
        fpy_policy_version=fpy.fpy_policy_version,
        abort_policy=fpy.abort_policy,
        policy_notes=list(POLICY_NOTES),
    )


def build_loss_summary(fpy: FpyResult) -> ReportLossSummary:
    primary = _pareto_rows(list(fpy.primary_fail_pareto), "PRIMARY_FAILURE")
    any_fail = _pareto_rows(list(fpy.any_fail_pareto), "ANY_FAIL")
    available = len(primary) > 0
    return ReportLossSummary(
        primary_failure=primary,
        any_fail=any_fail,
        primary_available=available,
        primary_unavailable_note=None if available else "No primary failure attribution available",
    )


def _pct(value: float | None) -> str:
    """Display-only conversion of an existing rate to a percentage string."""
    if value is None:
        return "Unavailable"
    return f"{100.0 * value:.2f}%"


def build_executive_summary(
    fpy: FpyResult,
    detectors: DetectorBundle,
    hypotheses: HypothesisBundle,
    opportunities: OpportunityBundle,
    validation: ValidationBundle,
) -> ReportSummary:
    n_signal = sum(
        1 for name, res in detectors.results.items() if name != "no_signal" and res.status == "SIGNAL"
    )
    n_hyp = len(hypotheses.hypotheses)
    n_investigate = sum(1 for item in validation.results if item.recommendation == "INVESTIGATE")
    associated = [
        item.observed_loss_rate
        for item in opportunities.opportunities
        if item.hypothesis_id and item.family != "UNION"
    ]
    largest = max(associated) if associated else None

    lines = [
        f"FPY was {_pct(fpy.fpy)} across {fpy.eligible_die_count} eligible dies.",
        (
            f"Observed first-pass loss was {_pct(fpy.fpy_loss)} "
            f"({fpy.first_pass_fail_count} first-pass fails, {fpy.first_pass_pass_count} first-pass passes)."
        ),
    ]
    if n_signal:
        lines.append(f"The analysis identified {n_signal} statistical evidence patterns.")
    else:
        lines.append("No systematic detector produced a SIGNAL.")
    if validation.no_actionable_recommendation or n_hyp == 0:
        lines.append("No actionable hypothesis identified.")
    else:
        lines.append(f"{n_hyp} hypotheses were generated.")
        if largest is not None:
            lines.append(f"The largest observed associated loss was {_pct(largest)}.")
        counts: dict[str, int] = {}
        for item in validation.results:
            counts[item.recommendation] = counts.get(item.recommendation, 0) + 1
        if counts:
            parts = ", ".join(f"{name} ({n})" for name, n in sorted(counts.items()))
            lines.append(f"The validation layer classified the available evidence as {parts}.")
        lines.append("Recommendations require engineering validation and do not authorize production action.")
    return ReportSummary(
        text=" ".join(lines),
        eligible_die_count=fpy.eligible_die_count,
        first_pass_pass_count=fpy.first_pass_pass_count,
        first_pass_fail_count=fpy.first_pass_fail_count,
        fpy=fpy.fpy,
        fpy_loss_rate=fpy.fpy_loss,
        n_signal_detectors=n_signal,
        n_hypotheses=n_hyp,
        n_investigate=n_investigate,
        largest_observed_associated_loss_rate=largest,
    )
