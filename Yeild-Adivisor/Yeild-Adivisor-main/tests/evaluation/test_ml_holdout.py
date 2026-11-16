"""ML holdout and integration. Ground truth is joined only here."""

from __future__ import annotations

import json

from yield_improvement.evaluation.ml import evaluate_all_ml, write_ml_evaluation
from yield_improvement.hypotheses.composer import compose
from yield_improvement.ml.contracts import MLEvidence
from yield_improvement.utils.paths import phase2_agent_visible_dir, repo_root
from yield_improvement.validation.contract import GateTrace
from yield_improvement.validation.recommendation import decide_recommendation
from yield_improvement.opportunity.contract import Opportunity


def _id_for(scenario: str) -> str:
    payload = json.loads(
        (repo_root() / "evaluation" / "ground_truth" / "synthetic" / "RUN_SUMMARY.json").read_text(encoding="utf-8")
    )
    for item in payload["scenarios"]:
        if item["scenario_id"] == scenario:
            return item["dataset_id"]
    raise AssertionError(scenario)


def _dir(scenario: str):
    return phase2_agent_visible_dir() / _id_for(scenario)


def test_ml_package_isolation_from_evaluation_module():
    src = repo_root() / "src" / "yield_improvement" / "ml"
    for path in src.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "yield_improvement.evaluation" not in text
        assert "RUN_SUMMARY" not in text
        assert "evaluation/ground_truth" not in text


def test_ml_evidence_reaches_hypothesis(config):
    from yield_improvement.detectors.contract import DetectorBundle, DetectorResult

    spatial = DetectorResult(
        detector="spatial",
        status="SIGNAL",
        not_a_root_cause=True,
        hypothesis_family="SPATIAL",
        hypothesis_detail="EDGE",
        effect_size=0.12,
        effect_size_metric="fail_rate_difference",
        p_value=1e-4,
        adjusted_p_value=1e-4,
        correction_method="benjamini_hochberg",
        sample_size=400,
        method="unit",
        affected_population={"label": "EDGE"},
    )
    bundle = DetectorBundle(
        n_eligible=400,
        correction_method="benjamini_hochberg",
        fdr_q=0.1,
        alpha=0.05,
        min_effect_size=0.02,
        results={"spatial": spatial},
    )
    ml = [
        MLEvidence(
            hypothesis_id="H-SPATIAL.EDGE",
            family="SPATIAL",
            detail="EDGE",
            predictive_strength=0.5,
            coverage=1.0,
            model_version="yi_ml_v1",
            prediction_summary={"high_risk_fail_rate": 0.4},
            limitations=["predictive only"],
        )
    ]
    hyps = compose(bundle, config, analysis_id="unit", ml_evidence=ml)
    edge = next(h for h in hyps.hypotheses if h.detail == "EDGE")
    assert any(isinstance(e, dict) and e.get("source") == "ml" for e in edge.evidence)
    assert edge.not_a_root_cause is True
    assert hyps.detector_summary.get("ml") == "PREDICTIVE_SUPPORT"


def test_ml_does_not_create_hypothesis_alone(config):
    from yield_improvement.detectors.contract import DetectorBundle, DetectorResult

    quiet = DetectorResult(
        detector="spatial",
        status="NO_SIGNAL",
        not_a_root_cause=True,
        correction_method="benjamini_hochberg",
        sample_size=400,
        method="unit",
    )
    bundle = DetectorBundle(
        n_eligible=400,
        correction_method="benjamini_hochberg",
        fdr_q=0.1,
        alpha=0.05,
        min_effect_size=0.02,
        results={"spatial": quiet},
    )
    ml = [
        MLEvidence(
            hypothesis_id="H-SPATIAL.EDGE",
            family="SPATIAL",
            detail="EDGE",
            predictive_strength=0.9,
            coverage=1.0,
            model_version="yi_ml_v1",
            limitations=["predictive only"],
        )
    ]
    hyps = compose(bundle, config, analysis_id="unit", ml_evidence=ml)
    assert hyps.hypotheses == []
    assert hyps.no_confident_hypothesis is True
    assert "without a matching statistical hypothesis" in " ".join(hyps.limitations)


def test_ml_cannot_override_safety():
    traces = [
        GateTrace(name="SAFETY", status="PASS", reasons=["ok"]),
        GateTrace(
            name="DATA_QUALITY",
            status="FAIL",
            recommendation="NEEDS_MORE_DATA",
            reasons=["cannot_calculate_fpy_denominator"],
        ),
    ]
    opp = Opportunity(
        opportunity_id="OPP-X",
        hypothesis_id="H-SPATIAL.EDGE",
        family="SPATIAL",
        detail="EDGE",
        association_class="PRIMARY_EVIDENCE",
        attribution_mode="PRIMARY_FAILURE",
        status="ESTIMATED",
        status_flags=["NOT_ELIGIBLE_FOR_PRODUCTION"],
        observed_loss_count=80,
        observed_loss_rate=0.8,
        upper_bound_count=80,
        upper_bound_rate=0.8,
        plausible_count=None,
        plausible_rate=None,
        plausible_unavailable=True,
        eligible_population=100,
        affected_population_count=90,
        population_definition="ml_high_risk",
        calculation_method="unit",
        statement="large associated loss",
        evidence_score=0.99,
    )
    rec, reason, _ = decide_recommendation(traces, opp, None)
    assert rec == "NEEDS_MORE_DATA"
    assert opp.safety_eligible_production_rate == 0.0


def test_ml_holdout_table(config):
    report = evaluate_all_ml(config=config)
    assert report["n_scenarios"] == 16
    assert report["s16_no_forced"] is True
    assert report["s15_separate"] is True
    assert report["s09_no_limit_change"] is True
    assert report["all_production_unauthorized"] is True
    assert report["all_production_zero"] is True
    write_ml_evaluation(config=config)
    by = {r["scenario"]: r for r in report["rows"]}
    assert by["S02"]["metrics"]["n_samples"] > 0
    assert 0.0 <= (by["S02"]["failure_capture_top10"] or 0) <= 1.0
    assert by["S11"]["no_limit_change"] is True
    blob = json.dumps(report).lower()
    assert "increase limit" not in blob
    assert "the root cause is" not in blob
    assert "recovered yield" not in blob
    s11_top = [f.lower() for f in by["S11"]["top_features"]]
    assert not any("sequence" in f or "later_test" in f or "test_index" in f for f in s11_top)
    assert by["S16"]["n_hypotheses"] == 0
    assert by["S09"]["no_limit_change"] is True
    assert by["S15"]["has_edge"] and by["S15"]["has_drift"]
    assert not by["S15"]["combined_root_cause"]


def test_ml_does_not_rescore_or_count_as_independent(config):
    from yield_improvement.detectors.contract import DetectorBundle, DetectorResult

    spatial = DetectorResult(
        detector="spatial",
        status="SIGNAL",
        not_a_root_cause=True,
        hypothesis_family="SPATIAL",
        hypothesis_detail="EDGE",
        effect_size=0.12,
        effect_size_metric="fail_rate_difference",
        p_value=1e-4,
        adjusted_p_value=1e-4,
        correction_method="benjamini_hochberg",
        sample_size=400,
        method="unit",
        affected_population={"label": "EDGE"},
    )
    bundle = DetectorBundle(
        n_eligible=400,
        correction_method="benjamini_hochberg",
        fdr_q=0.1,
        alpha=0.05,
        min_effect_size=0.02,
        results={"spatial": spatial},
    )
    ml = [
        MLEvidence(
            hypothesis_id="H-SPATIAL.EDGE",
            family="SPATIAL",
            detail="EDGE",
            predictive_strength=0.99,
            coverage=1.0,
            model_version="yi_ml_v1",
            prediction_summary={"high_risk_fail_rate": 0.9},
            limitations=["predictive only"],
        )
    ]
    without = compose(bundle, config, analysis_id="unit")
    with_ml = compose(bundle, config, analysis_id="unit", ml_evidence=ml)
    edge_wo = next(h for h in without.hypotheses if h.detail == "EDGE")
    edge_w = next(h for h in with_ml.hypotheses if h.detail == "EDGE")
    assert edge_wo.evidence_score == edge_w.evidence_score
    assert edge_wo.rank == edge_w.rank
    assert ml[0].independence is False
    assert "not summed" in " ".join(with_ml.limitations).lower() or "not added into evidence_score" in " ".join(
        with_ml.limitations
    )
