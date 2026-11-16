"""OpportunityBundle → ValidationBundle. Advisory only. Production remains forbidden."""

from __future__ import annotations

from pathlib import Path

from yield_improvement.config.loader import AppConfig, load_config
from yield_improvement.detectors.population import DetectorContext, build_context
from yield_improvement.detectors.runner import run_detectors
from yield_improvement.hypotheses.contract import Hypothesis, HypothesisBundle
from yield_improvement.ingestion.loader import (
    load_die_attempts,
    load_parametric_measurements,
    load_test_results,
)
from yield_improvement.opportunity.contract import Opportunity, OpportunityBundle
from yield_improvement.opportunity.engine import estimate_opportunities, production_safety_rate
from yield_improvement.validation.contract import (
    DISCLAIMER,
    GateTrace,
    Traceability,
    ValidationBundle,
    ValidationResult,
)
from yield_improvement.validation.data_quality import evaluate_data_quality
from yield_improvement.validation.evidence import (
    evaluate_conflicts,
    evaluate_evidence,
    independent_detector_count,
)
from yield_improvement.validation.population import evaluate_population
from yield_improvement.validation.recommendation import decide_recommendation, steps_for
from yield_improvement.validation.safety import evaluate_safety
from yield_improvement.yield_analysis.fpy import calculate_fpy


def _hyp_for(opportunity: Opportunity, hypotheses: HypothesisBundle) -> Hypothesis | None:
    if not opportunity.hypothesis_id:
        return None
    for hyp in hypotheses.hypotheses:
        if hyp.hypothesis_id == opportunity.hypothesis_id:
            return hyp
    return None


def _validate_one(
    opportunity: Opportunity,
    hypothesis: Hypothesis | None,
    ctx: DetectorContext,
    config: AppConfig,
    hypotheses: HypothesisBundle,
) -> ValidationResult:
    production_safety_rate(config)
    steps = steps_for(opportunity.family, opportunity.detail)
    safety = evaluate_safety(opportunity, config, proposed_steps=steps, proposed_reason="")
    quality = evaluate_data_quality(opportunity, ctx, config)
    population = evaluate_population(opportunity)
    evidence = evaluate_evidence(opportunity, hypothesis)
    conflict = evaluate_conflicts(opportunity, hypothesis)
    n_ind = independent_detector_count(list(hypothesis.supporting_detectors)) if hypothesis else 0
    confidence = GateTrace(
        name="CONFIDENCE",
        status="WARNING" if n_ind <= 1 else "PASS",
        reasons=[
            "evidence_score_is_descriptive_only_not_probability",
            "no_historical_replication_store",
            "single_statistical_view_cannot_be_high_confidence" if n_ind <= 1 else f"independent_views={n_ind}",
        ],
    )
    engineering = GateTrace(
        name="ENGINEERING_POLICY",
        status="PASS",
        reasons=[
            "advisory_states_only=INVESTIGATE|REVIEW|MONITOR|NEEDS_MORE_DATA|REJECTED",
            "production_action_forbidden",
            "no_limit_or_recipe_modification",
        ],
    )
    opportunity_gate = GateTrace(
        name="OPPORTUNITY",
        status="PASS",
        reasons=["opportunity_size_does_not_override_earlier_gates"],
    )
    traces = [safety, quality, population, evidence, conflict, confidence, engineering, opportunity_gate]
    recommendation, reason, traces = decide_recommendation(traces, opportunity, hypothesis)
    safety = evaluate_safety(opportunity, config, proposed_steps=steps, proposed_reason=reason)
    if safety.status == "FAIL" and safety.recommendation:
        recommendation, reason, traces = safety.recommendation, "; ".join(safety.reasons), [safety, *traces[1:]]
    gaps = list(opportunity.data_gaps)
    if hypothesis:
        gaps.extend(hypothesis.data_gaps)
    gaps.extend(r for t in traces for r in t.reasons if t.status in {"FAIL", "UNAVAILABLE", "WARNING"})
    limitations = [
        DISCLAIMER,
        "UNCONFIRMED association. not_a_root_cause remains true.",
        "Opportunity size does not override earlier safety, data-quality, population, or evidence gates.",
    ]
    if opportunity.family == "TEST" and opportunity.detail == "LIMIT_SENSITIVITY":
        limitations.append("Near-limit validation does not modify or propose a candidate limit.")
    if opportunity.family == "TEST" and opportunity.detail == "SEQUENCE":
        limitations.append("Later-test observations are censored by stop-on-fail behavior.")
    if hypothesis and hypothesis.association_class == "SECONDARY_ASSOCIATION":
        limitations.append("Secondary association is not treated as a root cause.")
    detectors = list(hypothesis.supporting_detectors) if hypothesis else []
    conflicting = list(hypothesis.conflicting_detectors) if hypothesis else []
    return ValidationResult(
        analysis_id=hypotheses.analysis_id,
        hypothesis_id=opportunity.hypothesis_id,
        opportunity_id=opportunity.opportunity_id,
        family=opportunity.family,
        detail=opportunity.detail,
        recommendation=recommendation,
        recommendation_reason=reason,
        evidence_tier=opportunity.evidence_tier,
        evidence_score=opportunity.evidence_score,
        observed_loss_rate=opportunity.observed_loss_rate,
        upper_bound_rate=opportunity.upper_bound_rate,
        plausible_rate=opportunity.plausible_rate,
        data_quality_status=quality.status,
        evidence_status=evidence.status,
        population_status=population.status,
        safety_status=safety.status,
        conflict_status=conflict.status,
        conflict_type=next((r.split("=", 1)[-1] for r in conflict.reasons if r.startswith("conflict_type=")), None),
        validation_required=list(steps),
        validation_steps=list(steps),
        supporting_detectors=detectors,
        conflicting_detectors=conflicting,
        data_gaps=list(dict.fromkeys(gaps)),
        assumptions=list(opportunity.assumptions),
        limitations=list(dict.fromkeys(limitations)),
        overlap_count=opportunity.overlap_count,
        union_count=opportunity.union_count,
        exclusive_count=opportunity.exclusive_count,
        intersection_count=opportunity.intersection_count,
        gate_trace=traces,
        safety_eligible_production_count=0,
        safety_eligible_production_rate=0.0,
        production_action="FORBIDDEN",
        production_authorized=False,
        invoked_agents=[],
        not_a_root_cause=True,
        traceability=Traceability(
            analysis_id=hypotheses.analysis_id,
            hypothesis_id=opportunity.hypothesis_id,
            opportunity_id=opportunity.opportunity_id,
            detector_ids=detectors,
            population_definition=opportunity.population_definition,
            eligible_population=opportunity.eligible_population,
            attribution_mode=opportunity.attribution_mode,
            calculation_method=opportunity.calculation_method,
            calibration_version=config.calibration.calibration_version,
            safety_policy_version=config.safety.policy_version,
            fpy_policy_version=config.fpy.fpy_policy_version,
        ),
        disclaimer=DISCLAIMER,
    )


def validate_opportunities(
    opportunities: OpportunityBundle,
    hypotheses: HypothesisBundle,
    ctx: DetectorContext,
    config: AppConfig,
) -> ValidationBundle:
    production_safety_rate(config)
    results: list[ValidationResult] = []
    no_actionable = opportunities.no_actionable_opportunity or hypotheses.no_confident_hypothesis
    if not no_actionable:
        for item in opportunities.opportunities:
            results.append(_validate_one(item, _hyp_for(item, hypotheses), ctx, config, hypotheses))
    overlap = {
        "sum_of_individual_upper_bounds_rate": opportunities.summary.sum_of_individual_upper_bounds_rate,
        "union_upper_bound_rate": opportunities.summary.union_upper_bound_rate,
        "union_upper_bound_count": opportunities.summary.union_upper_bound_count,
        "intersection_fail_count": opportunities.summary.intersection_fail_count,
        "sum_exceeds_observed": opportunities.summary.sum_of_individual_upper_bounds_exceeds_observed,
        "note": "Combined opportunity is the union of failed dies, not the sum of rates, and is not a root cause.",
    }
    limitations = [
        DISCLAIMER,
        "No specialist agent is invoked. Domain names may appear only as unused labels.",
        "safety_eligible_production remains 0 from configs/safety_policy.yaml.",
    ]
    if no_actionable:
        limitations.append(
            "No actionable recommendation. Overall observed FPY loss is reported without an invented cause."
        )
    seq = hypotheses.detector_summary.get("sequence")
    if seq == "INSUFFICIENT_DATA":
        limitations.append("Later-test observations are censored by stop-on-fail behavior.")
    return ValidationBundle(
        analysis_id=hypotheses.analysis_id,
        current_fpy=opportunities.summary.current_fpy,
        observed_loss_rate=opportunities.summary.observed_loss_rate,
        eligible_population=opportunities.summary.eligible_population,
        attribution_mode=opportunities.attribution_mode,
        results=results,
        no_actionable_recommendation=no_actionable,
        overlap_summary=overlap,
        data_gaps=list(opportunities.data_gaps),
        limitations=limitations,
        safety_eligible_production_count=0,
        safety_eligible_production_rate=0.0,
        production_action="FORBIDDEN",
        production_authorized=False,
        invoked_agents=[],
        disclaimer=DISCLAIMER,
        config_versions={
            **opportunities.config_versions,
            "safety_policy": config.safety.policy_version,
        },
    )


def validate_from_dir(dataset_dir: str | Path, config: AppConfig | None = None) -> ValidationBundle:
    """Load agent-visible files once, then hypotheses → opportunity → validation."""
    from yield_improvement.hypotheses.composer import compose

    folder = Path(dataset_dir)
    cfg = config or load_config()
    attempts = load_die_attempts(folder / "die_attempts.csv", cfg).attempts
    tests = []
    tr = folder / "test_results.csv"
    if tr.is_file():
        tests = load_test_results(tr, cfg).test_results
    parametric = []
    pm = folder / "parametric_measurements.csv"
    if pm.is_file():
        parametric = load_parametric_measurements(pm, cfg).parametric
    ctx = build_context(attempts, cfg, test_results=tests, parametric=parametric)
    detectors = run_detectors(attempts, cfg, test_results=tests, parametric=parametric)
    fpy = calculate_fpy(attempts, cfg, test_results=tests)
    hyps = compose(detectors, cfg, fpy=fpy.fpy, analysis_id=folder.name)
    opportunities = estimate_opportunities(hyps, ctx, cfg)
    return validate_opportunities(opportunities, hyps, ctx, cfg)
