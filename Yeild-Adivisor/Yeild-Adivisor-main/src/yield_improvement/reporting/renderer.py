"""JSON and Markdown export. Formatting only."""

from __future__ import annotations

import json
from pathlib import Path

from yield_improvement.reporting.contract import EngineeringReport, ReportHypothesis, ReportOpportunity


def _pct(value: float | None) -> str:
    if value is None:
        return "Unavailable"
    return f"{100.0 * value:.2f}%"


def _plausible(item: ReportHypothesis | ReportOpportunity) -> str:
    if item.plausible_unavailable or item.plausible_rate is None:
        return "Not estimable"
    return f"{_pct(item.plausible_rate)} ({item.calibration_status if isinstance(item, ReportOpportunity) else 'PRELIMINARY / CALIBRATION-DEPENDENT'})"


def render_markdown(report: EngineeringReport) -> str:
    fpy = report.fpy_summary
    lines: list[str] = [
        f"# Engineering Report `{report.report_id}`",
        "",
        f"Dataset `{report.dataset_id}` · analysis `{report.analysis_id}` · generated {report.generated_at}",
        "",
        "## Safety Restrictions",
        "",
        report.safety_statement,
        "",
        f"- production_action: `{report.production_action}`",
        f"- production_authorized: `{report.production_authorized}`",
        f"- safety_eligible_production_rate: `{report.safety_eligible_production_rate}`",
        "",
        "## Executive Summary",
        "",
        report.executive_summary.text,
        "",
        "## FPY Summary",
        "",
        f"- Eligible dies: {fpy.eligible_die_count}",
        f"- First-pass passes: {fpy.first_pass_pass_count}",
        f"- First-pass fails: {fpy.first_pass_fail_count}",
        f"- Excluded: {fpy.excluded_count}",
        f"- FPY: {_pct(fpy.fpy)}",
        f"- FPY loss: {_pct(fpy.fpy_loss)}",
        f"- Policy: {fpy.fpy_policy_version} / abort {fpy.abort_policy}",
        "",
    ]
    for note in fpy.policy_notes:
        lines.append(f"- {note}")
    lines += ["", "## Loss Pareto", ""]
    if not report.loss_summary.primary_available:
        lines.append(report.loss_summary.primary_unavailable_note or "No primary failure attribution available")
        lines.append("")
    else:
        lines.append("PRIMARY_FAILURE (not combined with ANY_FAIL):")
        lines.append("")
        for row in report.loss_summary.primary_failure:
            lines.append(
                f"- {row.failure_key} family={row.family} detail={row.detail}: "
                f"{row.affected_die_count} dies ({_pct(row.percentage_of_eligible)} of eligible)"
            )
        lines.append("")
        lines.append("ANY_FAIL (overlapping; not summed with PRIMARY_FAILURE):")
        lines.append("")
        for row in report.loss_summary.any_fail:
            lines.append(
                f"- {row.failure_key}: {row.affected_die_count} dies ({_pct(row.percentage_of_eligible)} of eligible)"
            )
        lines.append("")
    lines += ["## Evidence Findings", ""]
    for item in report.evidence_findings:
        ident = f"{item.family}.{item.detail}" if item.family else "n/a"
        lines.append(
            f"- `{item.detector}` status={item.status} identity={ident} "
            f"effect={item.effect_size} method={item.method}"
        )
    lines += ["", "## Hypotheses", "", report.evidence_score_notice, ""]
    if report.no_actionable_notice:
        lines.append(report.no_actionable_notice)
        lines.append("")
    for hyp in report.hypotheses:
        lines += [
            f"### Rank {hyp.rank}: {hyp.family}.{hyp.detail} (`{hyp.hypothesis_id}`)",
            "",
            f"- Status: {hyp.status} (not a root cause)",
            f"- Evidence tier: {hyp.evidence_tier}; score: {hyp.evidence_score} ({hyp.score_status})",
            f"- Observed loss: {_pct(hyp.observed_loss_rate)}",
            f"- Upper bound: {_pct(hyp.upper_bound_rate)}",
            f"- Plausible opportunity: {_plausible(hyp)}",
            f"- Validation recommendation: {hyp.validation_recommendation or 'Unavailable'}",
            f"- Statement: {hyp.statement}",
            f"- Why it exists: {hyp.why_it_exists}",
            f"- Supporting detectors: {', '.join(hyp.supporting_detectors) or 'none'}",
            f"- Conflicting detectors: {', '.join(hyp.conflicting_detectors) or 'none'}",
            "",
        ]
    lines += ["## Opportunity Analysis", "", "Upper bound ≠ predicted FPY improvement.", ""]
    for opp in report.opportunities:
        lines += [
            f"### {opp.family}.{opp.detail} (`{opp.opportunity_id}`)" if opp.family else f"### {opp.opportunity_id}",
            "",
            f"- OBSERVED: {_pct(opp.observed_loss_rate)} ({opp.observed_loss_count} dies)",
            f"- UPPER BOUND: {_pct(opp.upper_bound_rate)}",
            f"- PRELIMINARY / CALIBRATION-DEPENDENT plausible: {_plausible(opp)}",
            f"- Attribution: {opp.attribution_mode}",
            f"- Affected population: {opp.affected_population_count} / definition `{opp.population_definition}`",
            f"- Overlap={opp.overlap_count}; exclusive={opp.exclusive_count}; union={opp.union_count}",
            "",
        ]
    ov = report.overlap
    lines += [
        "## Overlap / Union",
        "",
        report.overlap_notice,
        "",
        f"- Sum of individual upper bounds: {_pct(ov.sum_of_individual_upper_bounds_rate)}",
        f"- Combined union upper bound: {_pct(ov.union_upper_bound_rate)} ({ov.union_upper_bound_count} dies)",
        f"- Intersection fail count: {ov.intersection_fail_count}",
        f"- Note: {ov.note}",
        "",
        "## Validation",
        "",
    ]
    if report.no_actionable_recommendation:
        lines.append(report.no_actionable_notice or "No actionable hypothesis identified.")
        lines.append("")
    for item in report.validation:
        lines += [
            f"### {item.family}.{item.detail} (`{item.validation_id}`)" if item.family else f"### {item.validation_id}",
            "",
            f"- Recommendation: {item.recommendation} — {item.recommendation_reason}",
            f"- Safety / data quality / population / evidence: "
            f"{item.safety_status} / {item.data_quality_status} / {item.population_status} / {item.evidence_status}",
            f"- Conflict: {item.conflict_status} ({item.conflict_type or 'none'})",
            "",
        ]
        for step in item.validation_steps:
            lines.append(f"  - {step}")
        lines.append("")
    if report.near_limit_notice:
        lines += ["### Near-limit", "", report.near_limit_notice, ""]
    if report.sequence_censoring_notice:
        lines += ["### Sequence censoring", "", report.sequence_censoring_notice, ""]
    lines += ["## Investigation Plan", ""]
    if not report.investigation_plan:
        lines.append("No investigation plan. No actionable hypothesis identified.")
        lines.append("")
    for item in report.investigation_plan:
        ident = f"{item.family}.{item.detail}" if item.family else (item.hypothesis_id or "item")
        lines.append(f"Hypothesis: {ident} (recommendation {item.recommendation})")
        for i, step in enumerate(item.steps, 1):
            lines.append(f"  {i}. {step}")
        lines.append("")
    gaps = report.data_gaps
    lines += ["## Data Gaps", "", "### Required"]
    lines.extend(f"- {g}" for g in gaps.required) if gaps.required else lines.append("- none recorded")
    lines += ["", "### Recommended"]
    lines.extend(f"- {g}" for g in gaps.recommended) if gaps.recommended else lines.append("- none recorded")
    lines += ["", "### Detector-specific"]
    lines.extend(f"- {g}" for g in gaps.detector_specific) if gaps.detector_specific else lines.append("- none recorded")
    lines += ["",
        "## Traceability",
        "",
        f"- report_id: {report.traceability.report_id}",
        f"- analysis_id: {report.traceability.analysis_id}",
        f"- dataset_id: {report.traceability.dataset_id}",
        f"- pipeline_version: {report.traceability.pipeline_version}",
        f"- fpy_policy: {report.traceability.fpy_policy_version}",
        f"- calibration: {report.traceability.calibration_version}",
        f"- safety_policy: {report.traceability.safety_policy_version}",
        f"- hypothesis_ids: {', '.join(report.traceability.hypothesis_ids) or 'none'}",
        f"- opportunity_ids: {', '.join(report.traceability.opportunity_ids) or 'none'}",
        f"- validation_ids: {', '.join(report.traceability.validation_ids) or 'none'}",
        "",
        "## Limitations",
        "",
    ]
    for note in report.limitations:
        lines.append(f"- {note}")
    lines.append("")
    return "\n".join(lines) + "\n"


def write_reports(report: EngineeringReport, out_dir: str | Path) -> tuple[Path, Path]:
    folder = Path(out_dir)
    folder.mkdir(parents=True, exist_ok=True)
    json_path = folder / f"{report.dataset_id}_engineering_report.json"
    md_path = folder / f"{report.dataset_id}_engineering_report.md"
    json_path.write_text(json.dumps(report.to_public_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    return json_path, md_path


def load_report_json(path: str | Path) -> EngineeringReport:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return EngineeringReport.model_validate(payload)
