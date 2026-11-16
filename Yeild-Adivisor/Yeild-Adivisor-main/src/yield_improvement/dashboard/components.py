"""Streamlit widgets bound to EngineeringReport. No detector or FPY calls."""

from __future__ import annotations

from yield_improvement.dashboard.charts import (
    CHART_TITLES,
    any_fail_pareto_rows,
    associated_opportunity_rows,
    fpy_overview_rows,
    hypothesis_evidence_rows,
    overlap_union_rows,
    primary_failure_pareto_rows,
    validation_distribution,
)
from yield_improvement.dashboard.formatting import format_count, format_plausible, format_rate
from yield_improvement.reporting.contract import EngineeringReport


def _st():
    import streamlit as st

    return st


def render_safety_banner(report: EngineeringReport) -> None:
    st = _st()
    st.error(report.safety_statement)
    st.caption(
        f"production_action={report.production_action} · "
        f"production_authorized={report.production_authorized} · "
        f"safety_eligible_production={report.safety_eligible_production_rate}"
    )


def render_overview(report: EngineeringReport) -> None:
    st = _st()
    st.header("Overview")
    render_safety_banner(report)
    fpy = report.fpy_summary
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("FPY", format_rate(fpy.fpy))
    c2.metric("FPY Loss", format_rate(fpy.fpy_loss))
    c3.metric("Eligible Dies", format_count(fpy.eligible_die_count))
    c4.metric("First-Pass Fails", format_count(fpy.first_pass_fail_count))
    c5.metric("Hypotheses", format_count(len(report.hypotheses)))
    c6.metric("Investigations", format_count(report.executive_summary.n_investigate))
    st.write(report.executive_summary.text)
    if report.no_actionable_notice:
        st.info(report.no_actionable_notice)
    st.subheader(CHART_TITLES["primary_pareto"])
    primary = primary_failure_pareto_rows(report)
    if not primary:
        st.warning(report.loss_summary.primary_unavailable_note or "No primary failure attribution available")
    else:
        st.bar_chart({row["label"]: row["dies"] for row in primary})
    st.caption("Hypothesis order is the Phase 4 rank. Opportunity size does not re-rank this table.")
    st.dataframe(
        [
            {
                "Rank": hyp.rank,
                "Hypothesis": f"{hyp.family}.{hyp.detail}",
                "Evidence tier": hyp.evidence_tier,
                "Evidence score": hyp.evidence_score,
                "Validation": hyp.validation_recommendation or "Unavailable",
            }
            for hyp in report.hypotheses
        ],
        hide_index=True,
    )
    st.caption(report.evidence_score_notice)
    dist = validation_distribution(report)
    if dist:
        st.subheader(CHART_TITLES["validation"])
        st.bar_chart(dist)


def render_fpy_loss(report: EngineeringReport) -> None:
    st = _st()
    st.header("FPY Loss")
    render_safety_banner(report)
    fpy = report.fpy_summary
    st.write(
        {
            "eligible_die_count": fpy.eligible_die_count,
            "first_pass_pass_count": fpy.first_pass_pass_count,
            "first_pass_fail_count": fpy.first_pass_fail_count,
            "FPY": format_rate(fpy.fpy),
            "FPY_loss": format_rate(fpy.fpy_loss),
        }
    )
    for note in fpy.policy_notes:
        st.write(f"- {note}")
    st.subheader(CHART_TITLES["fpy"])
    st.bar_chart({row["metric"]: row["value"] for row in fpy_overview_rows(report)})
    st.subheader(CHART_TITLES["primary_pareto"])
    primary = primary_failure_pareto_rows(report)
    if not primary:
        st.warning(report.loss_summary.primary_unavailable_note or "No primary failure attribution available")
    else:
        st.bar_chart({row["label"]: row["share_of_eligible"] for row in primary})
    st.subheader(CHART_TITLES["any_fail_pareto"])
    any_fail = any_fail_pareto_rows(report)
    if any_fail:
        st.bar_chart({row["label"]: row["share_of_eligible"] for row in any_fail})
    else:
        st.caption("No ANY_FAIL rows in the upstream FPY result.")
    st.info("PRIMARY_FAILURE and ANY_FAIL are displayed separately and are never combined.")


def render_evidence(report: EngineeringReport) -> None:
    st = _st()
    st.header("Evidence")
    render_safety_banner(report)
    st.dataframe(
        [
            {
                "Detector": item.detector,
                "Status": item.status,
                "Family": item.family,
                "Detail": item.detail,
                "Effect": item.effect_size,
                "p": item.p_value,
                "adjusted_p": item.adjusted_p_value,
            }
            for item in report.evidence_findings
        ],
        hide_index=True,
    )


def render_hypotheses(report: EngineeringReport) -> None:
    st = _st()
    st.header("Hypotheses")
    render_safety_banner(report)
    st.caption(report.evidence_score_notice)
    if report.no_actionable_notice and not report.hypotheses:
        st.info(report.no_actionable_notice)
        return
    st.dataframe(
        [
            {
                "Rank": hyp.rank,
                "Hypothesis": f"{hyp.family}.{hyp.detail}",
                "Family": hyp.family,
                "Detail": hyp.detail,
                "Status": hyp.status,
                "Evidence Tier": hyp.evidence_tier,
                "Evidence Score": hyp.evidence_score,
                "Observed Loss": format_rate(hyp.observed_loss_rate),
                "Upper Bound": format_rate(hyp.upper_bound_rate),
                "Plausible Opportunity": format_plausible(hyp.plausible_rate, hyp.plausible_unavailable),
                "Validation Recommendation": hyp.validation_recommendation or "Unavailable",
            }
            for hyp in report.hypotheses
        ],
        hide_index=True,
    )
    scores = hypothesis_evidence_rows(report)
    if scores:
        st.subheader(CHART_TITLES["evidence"])
        st.bar_chart({row["hypothesis"]: row["evidence_score"] for row in scores})
    for hyp in report.hypotheses:
        with st.expander(f"Rank {hyp.rank}: {hyp.family}.{hyp.detail}"):
            st.write(hyp.statement)
            st.write(hyp.why_it_exists)
            st.json(
                {
                    "supporting_detectors": hyp.supporting_detectors,
                    "conflicting_detectors": hyp.conflicting_detectors,
                    "statistical_evidence": hyp.statistical_evidence,
                    "effect_sizes": hyp.effect_sizes,
                    "affected_population": hyp.affected_population,
                    "data_coverage": hyp.data_coverage,
                    "data_gaps": hyp.data_gaps,
                    "limitations": hyp.limitations,
                    "validation_steps": hyp.validation_steps,
                }
            )


def render_opportunity(report: EngineeringReport) -> None:
    st = _st()
    st.header("Opportunity")
    render_safety_banner(report)
    st.caption("Upper bound ≠ predicted FPY improvement.")
    st.dataframe(
        [
            {
                "ID": opp.opportunity_id,
                "Hypothesis": f"{opp.family}.{opp.detail}" if opp.family else "n/a",
                "OBSERVED": format_rate(opp.observed_loss_rate),
                "UPPER BOUND": format_rate(opp.upper_bound_rate),
                "PRELIMINARY / CALIBRATION-DEPENDENT": format_plausible(opp.plausible_rate, opp.plausible_unavailable),
                "Attribution": opp.attribution_mode,
                "Affected": opp.affected_population_count,
                "Overlap": opp.overlap_count,
                "Exclusive": opp.exclusive_count,
                "Union": opp.union_count,
            }
            for opp in report.opportunities
        ],
        hide_index=True,
    )
    assoc = associated_opportunity_rows(report)
    if assoc:
        st.subheader(CHART_TITLES["opportunity"])
        st.bar_chart({row["item"]: row["observed"] for row in assoc})
    st.subheader("Overlap / union")
    st.write(report.overlap_notice)
    st.write(report.overlap.note)
    st.write(
        {
            "sum_of_individual_upper_bounds": format_rate(report.overlap.sum_of_individual_upper_bounds_rate),
            "combined_union": format_rate(report.overlap.union_upper_bound_rate),
            "intersection_fail_count": report.overlap.intersection_fail_count,
        }
    )
    ov_rows = overlap_union_rows(report)
    st.subheader(CHART_TITLES["overlap"])
    st.bar_chart({row["series"]: row["rate"] for row in ov_rows})
    if report.near_limit_notice:
        st.warning(report.near_limit_notice)


def render_validation(report: EngineeringReport) -> None:
    st = _st()
    st.header("Validation")
    render_safety_banner(report)
    if report.no_actionable_notice:
        st.info(report.no_actionable_notice)
    if report.sequence_censoring_notice:
        st.warning(report.sequence_censoring_notice)
    if report.near_limit_notice:
        st.warning(report.near_limit_notice)
    for item in report.validation:
        st.subheader(f"{item.family}.{item.detail}" if item.family else item.validation_id)
        st.write(f"Recommendation (copied from Phase 6): **{item.recommendation}**")
        st.write(item.recommendation_reason)
        st.write(
            {
                "safety": item.safety_status,
                "data_quality": item.data_quality_status,
                "population": item.population_status,
                "evidence": item.evidence_status,
                "conflict": item.conflict_status,
                "conflict_type": item.conflict_type,
            }
        )
        st.write("Validation steps (investigation only; not a production action):")
        for step in item.validation_steps:
            st.write(f"- {step}")
    st.subheader("Investigation plan")
    if not report.investigation_plan:
        st.info("No investigation plan.")
        return
    for item in report.investigation_plan:
        st.write(f"Hypothesis: {item.family}.{item.detail} · {item.recommendation}")
        for i, step in enumerate(item.steps, 1):
            st.write(f"{i}. {step}")


def render_data_quality(report: EngineeringReport) -> None:
    st = _st()
    st.header("Data Quality")
    render_safety_banner(report)
    st.subheader("Required")
    st.write(report.data_gaps.required or ["none recorded"])
    st.subheader("Recommended")
    st.write(report.data_gaps.recommended or ["none recorded"])
    st.subheader("Detector-specific")
    st.write(report.data_gaps.detector_specific or ["none recorded"])
    if report.sequence_censoring_notice:
        st.warning(report.sequence_censoring_notice)


def render_traceability(report: EngineeringReport) -> None:
    st = _st()
    st.header("Traceability")
    render_safety_banner(report)
    t = report.traceability
    st.json(
        {
            "report_id": t.report_id,
            "analysis_id": t.analysis_id,
            "dataset_id": t.dataset_id,
            "generated_at": t.generated_at,
            "pipeline_version": t.pipeline_version,
            "fpy_policy_version": t.fpy_policy_version,
            "calibration_version": t.calibration_version,
            "safety_policy_version": t.safety_policy_version,
            "config_versions": t.config_versions,
            "hypothesis_ids": t.hypothesis_ids,
            "opportunity_ids": t.opportunity_ids,
            "validation_ids": t.validation_ids,
            "detector_ids": t.detector_ids,
        }
    )
    st.caption("Every displayed KPI is copied from the EngineeringReport, which copies Phase 1–6 fields.")
