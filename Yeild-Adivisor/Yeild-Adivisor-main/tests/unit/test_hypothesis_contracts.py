"""Hypothesis schema, identity, ranking, composition. No ground truth."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from yield_improvement.detectors.contract import DetectorBundle, DetectorResult
from yield_improvement.hypotheses.composer import compose
from yield_improvement.hypotheses.contract import Hypothesis
from yield_improvement.hypotheses.identity import hypothesis_id, identity_for
from yield_improvement.hypotheses.ranking import evidence_score, evidence_tier
from yield_improvement.utils.paths import repo_root


def _result(
    detector: str,
    status: str = "NO_SIGNAL",
    *,
    family: str | None = None,
    detail: str | None = None,
    effect: float | None = None,
    metric: str | None = "fail_rate_difference",
    p: float | None = None,
    adj: float | None = None,
    n: int = 400,
    method: str = "unit_test",
    gaps: list[str] | None = None,
    evidence: list | None = None,
    counter: list | None = None,
    affected: dict | None = None,
) -> DetectorResult:
    from yield_improvement.detectors.contract import EvidenceItem

    return DetectorResult(
        detector=detector,
        status=status,  # type: ignore[arg-type]
        not_a_root_cause=True,
        hypothesis_family=family,
        hypothesis_detail=detail,
        affected_population=affected,
        effect_size=effect,
        effect_size_metric=metric,
        p_value=p,
        adjusted_p_value=adj,
        correction_method="benjamini_hochberg",
        sample_size=n,
        method=method,
        data_gaps=gaps or [],
        evidence=evidence or [],
        counter_evidence=counter or [],
    )


def _bundle(results: dict[str, DetectorResult], n: int = 400) -> DetectorBundle:
    return DetectorBundle(
        n_eligible=n,
        correction_method="benjamini_hochberg",
        fdr_q=0.10,
        alpha=0.05,
        min_effect_size=0.02,
        results=results,
        data_gaps=sorted({g for r in results.values() for g in r.data_gaps}),
    )


def test_hypothesis_schema_not_a_root_cause(config):
    hyp = Hypothesis(
        hypothesis_id="H-SPATIAL.EDGE",
        family="SPATIAL",
        detail="EDGE",
        statement="Yield loss is associated with wafer-edge location.",
        association_class="PRIMARY_EVIDENCE",
        evidence_tier="MODERATE_EVIDENCE",
        evidence_score=0.7,
        confidence_level="MEDIUM",
        rank=1,
    )
    assert hyp.not_a_root_cause is True
    assert hyp.status == "UNCONFIRMED"
    with pytest.raises(ValidationError):
        Hypothesis(
            hypothesis_id="H-X",
            family="X",
            detail="Y",
            statement="bad",
            association_class="PRIMARY_EVIDENCE",
            evidence_tier="WEAK_EVIDENCE",
            evidence_score=0.1,
            confidence_level="LOW",
            rank=1,
            not_a_root_cause=False,
        )


def test_no_confirmed_root_cause_field():
    fields = Hypothesis.model_fields
    assert "confirmed_root_cause" not in fields
    assert "root_cause_confirmed" not in fields
    assert "root_cause" not in fields
    dumped = Hypothesis(
        hypothesis_id="H-A.B",
        family="A",
        detail="B",
        statement="Yield loss is associated with A.B.",
        association_class="PRIMARY_EVIDENCE",
        evidence_tier="WEAK_EVIDENCE",
        evidence_score=0.2,
        confidence_level="LOW",
        rank=1,
    ).model_dump()
    assert dumped["not_a_root_cause"] is True
    assert "confirmed_root_cause" not in dumped


def test_identity_deterministic():
    res = _result("spatial", "SIGNAL", family="SPATIAL", detail="EDGE")
    assert identity_for("spatial", res) == ("SPATIAL", "EDGE")
    assert hypothesis_id("SPATIAL", "EDGE") == "H-SPATIAL.EDGE"
    assert identity_for("temporal", _result("temporal", "SIGNAL", family="PROCESS", detail="DRIFT")) == (
        "PROCESS",
        "DRIFT",
    )
    assert identity_for("no_signal", _result("no_signal", "SIGNAL", family="NONE", detail="NO_MEANINGFUL_SIGNAL")) is None


def test_duplicate_evidence_composes_one_hypothesis(config):
    spatial = _result(
        "spatial",
        "SIGNAL",
        family="SPATIAL",
        detail="EDGE",
        effect=0.12,
        p=0.001,
        adj=0.01,
        n=400,
    )
    twin = _result(
        "spatial_repeat",
        "SIGNAL",
        family="SPATIAL",
        detail="EDGE",
        effect=0.11,
        p=0.002,
        adj=0.02,
        n=400,
        method="repeat_view",
    )
    bundle = compose(_bundle({"spatial": spatial, "spatial_repeat": twin}), config, analysis_id="dup")
    edges = [h for h in bundle.hypotheses if h.family == "SPATIAL" and h.detail == "EDGE"]
    assert len(edges) == 1
    assert set(edges[0].supporting_detectors) >= {"spatial", "spatial_repeat"}
    assert len(edges[0].statistical_evidence) >= 2


def test_spatial_and_drift_remain_separate(config):
    bundle = compose(
        _bundle(
            {
                "spatial": _result("spatial", "SIGNAL", family="SPATIAL", detail="EDGE", effect=0.2, p=1e-6, adj=1e-5),
                "temporal": _result(
                    "temporal", "SIGNAL", family="PROCESS", detail="DRIFT", effect=0.3, p=0.001, adj=0.01
                ),
            }
        ),
        config,
    )
    ids = {(h.family, h.detail) for h in bundle.hypotheses}
    assert ("SPATIAL", "EDGE") in ids
    assert ("PROCESS", "DRIFT") in ids
    assert not any("EDGE" in h.detail and "DRIFT" in h.detail for h in bundle.hypotheses)


def test_evidence_propagation(config):
    from yield_improvement.detectors.contract import EvidenceItem

    spatial = _result(
        "spatial",
        "SIGNAL",
        family="SPATIAL",
        detail="EDGE",
        effect=0.14,
        p=0.001,
        adj=0.01,
        evidence=[EvidenceItem(name="edge_fail_rate", value=0.142)],
        affected={"label": "EDGE", "n": 80, "rate": 0.142},
        gaps=["missing_x_y_on_some_dies"],
    )
    out = compose(_bundle({"spatial": spatial}), config)
    hyp = out.hypotheses[0]
    assert hyp.affected_population["label"] == "EDGE"
    assert any(e.get("name") == "edge_fail_rate" for e in hyp.evidence)
    assert "missing_x_y_on_some_dies" in hyp.data_gaps
    assert hyp.statistical_evidence[0].p_value == 0.001
    assert hyp.statistical_evidence[0].adjusted_p_value == 0.01
    assert hyp.statistical_evidence[0].effect_size == 0.14
    assert "UNCONFIRMED" in hyp.explanation
    assert "not a root cause" in hyp.explanation.lower()


def test_counter_evidence_not_manufactured(config):
    spatial = _result("spatial", "SIGNAL", family="SPATIAL", detail="EDGE", effect=0.2, p=1e-4, adj=1e-3)
    out = compose(_bundle({"spatial": spatial}), config)
    hyp = out.hypotheses[0]
    assert hyp.counter_evidence == [] or all("invent" not in str(c).lower() for c in hyp.counter_evidence)


def test_nested_lot_is_secondary_when_drift_present(config):
    out = compose(
        _bundle(
            {
                "temporal": _result(
                    "temporal", "SIGNAL", family="PROCESS", detail="DRIFT", effect=0.4, p=0.001, adj=0.01
                ),
                "lot": _result("lot", "SIGNAL", family="PROCESS", detail="LOT_VARIATION", effect=0.15, p=0.002, adj=0.02),
            }
        ),
        config,
    )
    by_id = {h.hypothesis_id: h for h in out.hypotheses}
    assert by_id["H-PROCESS.DRIFT"].association_class == "PRIMARY_EVIDENCE"
    assert by_id["H-PROCESS.LOT_VARIATION"].association_class in {
        "SECONDARY_ASSOCIATION",
        "WEAK_ASSOCIATION",
    }
    assert "lot" in by_id["H-PROCESS.DRIFT"].supporting_detectors
    assert any(s.role == "CORRELATED_SUPPORT" for s in by_id["H-PROCESS.DRIFT"].statistical_evidence)
    assert any("nested" in str(c).lower() or "grain" in str(c).lower() for c in by_id["H-PROCESS.LOT_VARIATION"].counter_evidence)


def test_missing_data_does_not_invent_sequence(config):
    seq = _result(
        "sequence",
        "INSUFFICIENT_DATA",
        gaps=["sequence_pairs_below_n_min_sequence_pairs", "stop_on_fail_biases_unexecuted_later_tests"],
    )
    none = _result("no_signal", "SIGNAL", family="NONE", detail="NO_MEANINGFUL_SIGNAL")
    out = compose(_bundle({"sequence": seq, "no_signal": none}), config)
    assert not any(h.family == "TEST" and h.detail == "SEQUENCE" for h in out.hypotheses)
    assert any("stop-on-fail" in note.lower() or "censored" in note.lower() for note in out.limitations)


def test_no_signal_bundle_has_no_confident_hypothesis(config):
    none = _result("no_signal", "SIGNAL", family="NONE", detail="NO_MEANINGFUL_SIGNAL")
    spatial = _result("spatial", "NO_SIGNAL")
    out = compose(_bundle({"spatial": spatial, "no_signal": none}), config)
    assert out.no_confident_hypothesis is True
    assert out.hypotheses == []


def test_ranking_is_deterministic(config):
    results = {
        "spatial": _result("spatial", "SIGNAL", family="SPATIAL", detail="EDGE", effect=0.25, p=1e-8, adj=1e-7),
        "temporal": _result("temporal", "SIGNAL", family="PROCESS", detail="DRIFT", effect=0.10, p=0.01, adj=0.04),
        "lot": _result("lot", "SIGNAL", family="PROCESS", detail="LOT_VARIATION", effect=0.08, p=0.02, adj=0.05),
    }
    a = compose(_bundle(results), config, analysis_id="r")
    b = compose(_bundle(results), config, analysis_id="r")
    assert [h.hypothesis_id for h in a.hypotheses] == [h.hypothesis_id for h in b.hypotheses]
    assert [h.evidence_score for h in a.hypotheses] == [h.evidence_score for h in b.hypotheses]
    assert [h.rank for h in a.hypotheses] == list(range(1, len(a.hypotheses) + 1))


def test_score_is_not_one_minus_p(config):
    score = evidence_score(
        config=config,
        p_value=0.001,
        adjusted_p_value=0.001,
        effect_size=0.02,
        effect_size_metric="fail_rate_difference",
        sample_size=40,
        n_gaps=2,
        n_counter=1,
        association_class="PRIMARY_EVIDENCE",
        independent_support=False,
    )
    assert score != pytest.approx(0.999)
    assert 0.0 <= score <= 1.0
    assert evidence_tier(score, config, independent_support=False) in {
        "STRONG_EVIDENCE",
        "MODERATE_EVIDENCE",
        "WEAK_EVIDENCE",
        "INSUFFICIENT_EVIDENCE",
    }


def test_every_composed_hypothesis_not_a_root_cause(config):
    out = compose(
        _bundle(
            {
                "spatial": _result("spatial", "SIGNAL", family="SPATIAL", detail="CENTER", effect=0.2, p=1e-5, adj=1e-4),
                "equipment": _result(
                    "equipment",
                    "SIGNAL",
                    family="EQUIPMENT",
                    detail="DEGRADATION",
                    effect=0.12,
                    p=0.001,
                    adj=0.01,
                    affected={"label": "T03"},
                ),
            }
        ),
        config,
    )
    public = out.to_public_dict()
    assert "confirmed_root_cause" not in public
    for hyp in out.hypotheses:
        assert hyp.not_a_root_cause is True
        assert hyp.status == "UNCONFIRMED"
        assert "caused" not in hyp.statement.lower()
        assert "associated" in hyp.statement.lower()
    for hyp in public["hypotheses"]:
        assert hyp["not_a_root_cause"] is True


def test_hypotheses_package_does_not_import_ground_truth():
    src = repo_root() / "src" / "yield_improvement" / "hypotheses"
    hits = []
    for path in src.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for token in ("true_cause", "scenario_id", "RUN_SUMMARY", "yield_improvement.evaluation"):
            if token in text:
                hits.append(f"{path.name}: {token}")
    assert hits == []


def test_coverage_fraction_cannot_exceed_one(config):
    spatial = _result(
        "spatial",
        "SIGNAL",
        family="SPATIAL",
        detail="EDGE",
        effect=0.12,
        p=0.001,
        adj=0.01,
        n=20000,
    )
    bundle = compose(_bundle({"spatial": spatial}, n=2500), config, analysis_id="coverage")
    assert bundle.hypotheses
    for hyp in bundle.hypotheses:
        fraction = hyp.data_coverage.get("fraction")
        assert fraction is not None
        assert fraction <= 1.0
        assert hyp.data_coverage["n_used"] <= hyp.data_coverage["n_eligible"]
        assert hyp.data_coverage["n_eligible"] == 2500
        assert hyp.data_coverage["n_used"] == 2500
        assert fraction == 1.0
