"""Assemble EngineeringReport from existing Phase 1–6 outputs. No analytical recomputation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from yield_improvement.config.loader import AppConfig, load_config
from yield_improvement.detectors.contract import DetectorBundle
from yield_improvement.detectors.population import DetectorContext, build_context
from yield_improvement.detectors.runner import run_detectors
from yield_improvement.hypotheses.composer import compose
from yield_improvement.hypotheses.contract import Hypothesis, HypothesisBundle
from yield_improvement.ingestion.loader import (
    load_die_attempts,
    load_parametric_measurements,
    load_test_results,
)
from yield_improvement.models.results import FpyResult
from yield_improvement.opportunity.contract import Opportunity, OpportunityBundle
from yield_improvement.opportunity.engine import estimate_opportunities
from yield_improvement.reporting.contract import (
    DISCLAIMER,
    SAFETY_STATEMENT,
    EngineeringReport,
    ReportHypothesis,
)
from yield_improvement.reporting.evidence import build_evidence_findings
from yield_improvement.reporting.opportunity import build_opportunities, build_overlap
from yield_improvement.reporting.summary import build_executive_summary, build_fpy_summary, build_loss_summary
from yield_improvement.reporting.traceability import build_traceability
from yield_improvement.reporting.validation import (
    build_data_gaps,
    build_investigation_plan,
    build_validation_rows,
    near_limit_notice,
    no_actionable_notice,
    sequence_censoring_notice,
)
from yield_improvement.validation.contract import ValidationBundle, ValidationResult
from yield_improvement.validation.validator import validate_opportunities
from yield_improvement.yield_analysis.fpy import calculate_fpy


@dataclass(frozen=True)
class AnalysisSnapshot:
    dataset_id: str
    fpy: FpyResult
    detectors: DetectorBundle
    hypotheses: HypothesisBundle
    opportunities: OpportunityBundle
    validation: ValidationBundle
    context: DetectorContext


def load_canonical_data(
    dataset_dir: str | Path,
    config: AppConfig | None = None,
) -> tuple[list[DieAttempt], list[TestResult], list[ParametricMeasurement], AppConfig]:
    folder = Path(dataset_dir)
    cfg = config or load_config()
    attempts = load_die_attempts(folder / "die_attempts.csv", cfg).attempts
    tests: list[TestResult] = []
    tr = folder / "test_results.csv"
    if tr.is_file():
        tests = load_test_results(tr, cfg).test_results
    parametric: list[ParametricMeasurement] = []
    pm = folder / "parametric_measurements.csv"
    if pm.is_file():
        parametric = load_parametric_measurements(pm, cfg).parametric
    return attempts, tests, parametric, cfg


def run_analysis_pipeline(
    dataset_id: str,
    attempts: list[DieAttempt],
    test_results: list[TestResult],
    parametric: list[ParametricMeasurement],
    config: AppConfig,
    *,
    lot_id: str | None = None,
) -> AnalysisSnapshot:
    """Run analysis pipeline with lot-filtering applied in memory if lot_id is specified."""
    if lot_id:
        attempts = [row for row in attempts if row.lot_id == lot_id]
        attempt_ids = {row.attempt_id for row in attempts}
        test_results = [row for row in test_results if row.attempt_id in attempt_ids]
        parametric = [row for row in parametric if row.attempt_id in attempt_ids]

    ctx = build_context(attempts, config, test_results=test_results, parametric=parametric)
    detectors = run_detectors(attempts, config, test_results=test_results, parametric=parametric)
    fpy = calculate_fpy(attempts, config, test_results=test_results)
    hyps = compose(detectors, config, fpy=fpy.fpy, analysis_id=dataset_id)
    opportunities = estimate_opportunities(hyps, ctx, config)
    validation = validate_opportunities(opportunities, hyps, ctx, config)
    return AnalysisSnapshot(
        dataset_id=dataset_id,
        fpy=fpy,
        detectors=detectors,
        hypotheses=hyps,
        opportunities=opportunities,
        validation=validation,
        context=ctx,
    )


def load_analysis(
    dataset_dir: str | Path,
    config: AppConfig | None = None,
    *,
    lot_id: str | None = None,
) -> AnalysisSnapshot:
    """One load, then the existing Phase 1–6 functions. No duplicated formulas."""
    folder = Path(dataset_dir)
    attempts, tests, parametric, cfg = load_canonical_data(folder, config)
    return run_analysis_pipeline(
        folder.name, attempts, tests, parametric, cfg, lot_id=lot_id
    )


def build_report_from_data(
    dataset_id: str,
    attempts: list[DieAttempt],
    test_results: list[TestResult],
    parametric: list[ParametricMeasurement],
    config: AppConfig,
    *,
    generated_at: str | None = None,
    lot_id: str | None = None,
) -> EngineeringReport:
    """Build an EngineeringReport reusing already loaded canonical data in memory."""
    snapshot = run_analysis_pipeline(
        dataset_id, attempts, test_results, parametric, config, lot_id=lot_id
    )
    return build_report(snapshot, generated_at=generated_at)


def _opp_for(hyp: Hypothesis, opportunities: OpportunityBundle) -> Opportunity | None:
    for item in opportunities.opportunities:
        if item.hypothesis_id == hyp.hypothesis_id:
            return item
    return None


def _val_for(hyp: Hypothesis, validation: ValidationBundle) -> ValidationResult | None:
    for item in validation.results:
        if item.hypothesis_id == hyp.hypothesis_id:
            return item
    return None


def _report_hypotheses(
    hypotheses: HypothesisBundle,
    opportunities: OpportunityBundle,
    validation: ValidationBundle,
) -> list[ReportHypothesis]:
    rows: list[ReportHypothesis] = []
    for hyp in hypotheses.hypotheses:
        opp = _opp_for(hyp, opportunities)
        val = _val_for(hyp, validation)
        why = hyp.explanation or (
            f"Composed from supporting detectors: {', '.join(hyp.supporting_detectors) or 'none'}."
        )
        rows.append(
            ReportHypothesis(
                rank=hyp.rank,
                hypothesis_id=hyp.hypothesis_id,
                family=hyp.family,
                detail=hyp.detail,
                status=hyp.status,
                statement=hyp.statement,
                explanation=hyp.explanation,
                why_it_exists=why,
                association_class=hyp.association_class,
                evidence_tier=hyp.evidence_tier,
                evidence_score=hyp.evidence_score,
                score_status=hyp.score_status,
                supporting_detectors=list(hyp.supporting_detectors),
                conflicting_detectors=list(hyp.conflicting_detectors),
                statistical_evidence=[item.model_dump(mode="json") for item in hyp.statistical_evidence],
                effect_sizes=list(hyp.effect_sizes),
                affected_population=hyp.affected_population,
                data_coverage=dict(hyp.data_coverage),
                data_gaps=list(hyp.data_gaps),
                limitations=list(hyp.limitations),
                validation_required=list(val.validation_required) if val else [],
                validation_steps=list(val.validation_steps) if val else [],
                validation_recommendation=val.recommendation if val else None,
                opportunity_id=opp.opportunity_id if opp else None,
                observed_loss_rate=opp.observed_loss_rate if opp else None,
                upper_bound_rate=opp.upper_bound_rate if opp else None,
                plausible_rate=opp.plausible_rate if opp else None,
                plausible_unavailable=opp.plausible_unavailable if opp else True,
                overlap_count=opp.overlap_count if opp else None,
                exclusive_count=opp.exclusive_count if opp else None,
                union_count=opp.union_count if opp else None,
                intersection_count=opp.intersection_count if opp else None,
                not_a_root_cause=True,
            )
        )
    return rows


def build_report(snapshot: AnalysisSnapshot, *, generated_at: str | None = None) -> EngineeringReport:
    from yield_improvement import __version__
    stamp = generated_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    report_id = f"RPT-{snapshot.dataset_id}"
    validation_rows = build_validation_rows(snapshot.validation)
    limitations = [
        DISCLAIMER,
        "This report copies Phase 1–6 outputs. It does not recalculate FPY, evidence, opportunity, or validation.",
        *list(snapshot.validation.limitations),
    ]
    extra_gaps = list(snapshot.detectors.data_gaps)
    return EngineeringReport(
        report_id=report_id,
        analysis_id=snapshot.hypotheses.analysis_id,
        generated_at=stamp,
        dataset_id=snapshot.dataset_id,
        executive_summary=build_executive_summary(
            snapshot.fpy,
            snapshot.detectors,
            snapshot.hypotheses,
            snapshot.opportunities,
            snapshot.validation,
        ),
        fpy_summary=build_fpy_summary(snapshot.fpy),
        loss_summary=build_loss_summary(snapshot.fpy),
        evidence_findings=build_evidence_findings(snapshot.detectors),
        hypotheses=_report_hypotheses(snapshot.hypotheses, snapshot.opportunities, snapshot.validation),
        opportunities=build_opportunities(snapshot.opportunities),
        overlap=build_overlap(snapshot.opportunities, snapshot.validation),
        validation=validation_rows,
        no_actionable_recommendation=snapshot.validation.no_actionable_recommendation,
        investigation_plan=build_investigation_plan(snapshot.hypotheses, snapshot.validation),
        data_gaps=build_data_gaps(snapshot.hypotheses, snapshot.validation, extra_gaps),
        limitations=list(dict.fromkeys(limitations)),
        safety_statement=SAFETY_STATEMENT,
        near_limit_notice=near_limit_notice(snapshot.validation, snapshot.hypotheses),
        sequence_censoring_notice=sequence_censoring_notice(snapshot.validation, snapshot.hypotheses),
        no_actionable_notice=no_actionable_notice(snapshot.validation, snapshot.hypotheses),
        traceability=build_traceability(
            report_id=report_id,
            dataset_id=snapshot.dataset_id,
            generated_at=stamp,
            pipeline_version=__version__,
            detectors=snapshot.detectors,
            hypotheses=snapshot.hypotheses,
            opportunities=snapshot.opportunities,
            validation=snapshot.validation,
            validation_rows=validation_rows,
        ),
        configuration_versions=dict(snapshot.validation.config_versions),
        production_action="FORBIDDEN",
        production_authorized=False,
        safety_eligible_production_count=0,
        safety_eligible_production_rate=0.0,
        invoked_agents=[],
        disclaimer=DISCLAIMER,
        pipeline_version=__version__,
    )


def build_report_from_dir(
    dataset_dir: str | Path,
    config: AppConfig | None = None,
    *,
    generated_at: str | None = None,
    lot_id: str | None = None,
) -> EngineeringReport:
    return build_report(load_analysis(dataset_dir, config=config, lot_id=lot_id), generated_at=generated_at)
