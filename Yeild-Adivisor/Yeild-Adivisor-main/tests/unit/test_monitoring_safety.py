"""Monitoring never retrains, never authorizes production, never disables statistics."""

from __future__ import annotations

from yield_improvement.hypotheses.composer import compose
from yield_improvement.ml.contracts import MLEvidence
from yield_improvement.ml.evidence import attach_ml_evidence
from yield_improvement.monitoring.contracts import ModelHealthReport
from yield_improvement.utils.paths import repo_root


def test_monitoring_package_does_not_train():
    src = repo_root() / "src" / "yield_improvement" / "monitoring"
    hits = []
    for path in src.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for token in ("select_and_train", "run_ml(", "HistGradientBoosting", "fit("):
            if token in text and token != "fit(":
                hits.append(f"{path.name}: {token}")
        assert "yield_improvement.evaluation" not in text
        assert "evaluation/ground_truth" not in text
        assert "RUN_SUMMARY" not in text
    assert hits == []


def test_degraded_ml_does_not_drop_statistical_hypothesis(config):
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
            limitations=["predictive only"],
        )
    ]
    hyps = compose(bundle, config, analysis_id="unit", ml_evidence=ml, model_health_status="DEGRADED")
    edge = next(h for h in hyps.hypotheses if h.detail == "EDGE")
    ml_packet = next(e for e in edge.evidence if isinstance(e, dict) and e.get("source") == "ml")
    assert ml_packet["trust"] == "REDUCED"
    assert ml_packet["model_health_status"] == "DEGRADED"
    assert hyps.detector_summary["ml"] == "ML_FLAGGED"
    assert edge.not_a_root_cause is True


def test_attach_does_not_retrain():
    from yield_improvement.hypotheses.contract import HypothesisBundle

    bundle = HypothesisBundle(
        analysis_id="a",
        n_eligible=10,
        no_confident_hypothesis=True,
        hypotheses=[],
        limitations=[],
        detector_summary={"spatial": "NO_SIGNAL"},
        score_status="PRELIMINARY",
    )
    out = attach_ml_evidence(bundle, [], model_health_status="NEEDS_RETRAINING")
    assert out.hypotheses == []
    assert out.detector_summary["ml"] == "ML_FLAGGED"
