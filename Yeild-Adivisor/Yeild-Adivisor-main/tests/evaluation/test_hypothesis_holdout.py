"""Phase 4 holdout. Ground truth is joined only here, after composition."""

from __future__ import annotations

import json

from yield_improvement.evaluation.hypotheses import (
    EXPECTED_HYPOTHESES,
    evaluate_all_hypotheses,
    write_hypothesis_evaluation,
)
from yield_improvement.hypotheses.composer import compose_from_dir
from yield_improvement.utils.paths import phase2_agent_visible_dir, repo_root


def _agent_dir(dataset_id: str):
    return phase2_agent_visible_dir() / dataset_id


def _summary():
    path = repo_root() / "evaluation" / "ground_truth" / "synthetic" / "RUN_SUMMARY.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _id_for(scenario: str) -> str:
    for item in _summary()["scenarios"]:
        if item["scenario_id"] == scenario:
            return item["dataset_id"]
    raise AssertionError(scenario)


def test_composer_does_not_import_ground_truth():
    src = repo_root() / "src" / "yield_improvement" / "hypotheses"
    hits = []
    for path in src.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for token in ("true_cause", "scenario_id", "RUN_SUMMARY", "yield_improvement.evaluation"):
            if token in text:
                hits.append(f"{path.name}: {token}")
    assert hits == []


def test_s01_no_confident_hypothesis(config):
    bundle = compose_from_dir(_agent_dir(_id_for("S01")), config=config)
    assert bundle.no_confident_hypothesis is True
    primary = [h for h in bundle.hypotheses if h.association_class == "PRIMARY_EVIDENCE"]
    assert primary == []
    for hyp in bundle.hypotheses:
        assert hyp.not_a_root_cause is True
        assert hyp.status == "UNCONFIRMED"


def test_s16_no_confident_hypothesis(config):
    bundle = compose_from_dir(_agent_dir(_id_for("S16")), config=config)
    assert bundle.no_confident_hypothesis is True
    assert bundle.hypotheses == []


def test_s02_spatial_edge_present(config):
    bundle = compose_from_dir(_agent_dir(_id_for("S02")), config=config)
    ids = {(h.family, h.detail) for h in bundle.hypotheses}
    assert ("SPATIAL", "EDGE") in ids
    edge = next(h for h in bundle.hypotheses if h.detail == "EDGE")
    assert edge.not_a_root_cause is True
    assert edge.status == "UNCONFIRMED"
    assert "associated" in edge.statement.lower()


def test_s15_dual_cause_uncollapsed(config):
    bundle = compose_from_dir(_agent_dir(_id_for("S15")), config=config)
    ids = {(h.family, h.detail) for h in bundle.hypotheses}
    assert ("SPATIAL", "EDGE") in ids
    assert ("PROCESS", "DRIFT") in ids
    assert not any("+" in h.detail or ( "EDGE" in h.detail and "DRIFT" in h.detail) for h in bundle.hypotheses)
    edge = next(h for h in bundle.hypotheses if h.family == "SPATIAL" and h.detail == "EDGE")
    drift = next(h for h in bundle.hypotheses if h.family == "PROCESS" and h.detail == "DRIFT")
    assert edge.association_class == "PRIMARY_EVIDENCE"
    assert drift.association_class == "PRIMARY_EVIDENCE"
    lot = [h for h in bundle.hypotheses if h.detail == "LOT_VARIATION"]
    if lot:
        assert lot[0].association_class in {"SECONDARY_ASSOCIATION", "WEAK_ASSOCIATION"}
        assert lot[0].not_a_root_cause is True
    for hyp in bundle.hypotheses:
        assert hyp.not_a_root_cause is True


def test_s11_sequence_insufficient_not_invented(config):
    bundle = compose_from_dir(_agent_dir(_id_for("S11")), config=config)
    seq = [h for h in bundle.hypotheses if h.family == "TEST" and h.detail == "SEQUENCE"]
    assert seq == []
    assert bundle.detector_summary.get("sequence") == "INSUFFICIENT_DATA"
    assert any("stop-on-fail" in note.lower() or "censored" in note.lower() for note in bundle.limitations)
    for hyp in bundle.hypotheses:
        assert hyp.not_a_root_cause is True


def test_s05_equipment_associative_wording(config):
    bundle = compose_from_dir(_agent_dir(_id_for("S05")), config=config)
    eq = next(h for h in bundle.hypotheses if h.family == "EQUIPMENT")
    assert eq.detail == "DEGRADATION"
    assert "caused" not in eq.statement.lower()
    assert "associated" in eq.statement.lower()
    assert eq.validation_required
    assert eq.not_a_root_cause is True


def test_phase4_evaluation_table(config):
    report = evaluate_all_hypotheses(config=config)
    assert report["n_scenarios"] == 16
    assert report["s01_no_confident"] is True
    assert report["s16_no_confident"] is True
    assert report["s15_dual_cause_ok"] is True
    assert report["all_not_a_root_cause"] is True
    by_s = {row["scenario"]: row for row in report["rows"]}
    for sid, expected in EXPECTED_HYPOTHESES.items():
        if sid in {"S01", "S16", "S11"}:
            continue
        assert by_s[sid]["expected_recovered"] is True, (sid, by_s[sid]["missing_hypothesis"])
        observed_expected = set(by_s[sid]["expected_present"])
        for family, detail in expected:
            assert f"{family}.{detail}" in observed_expected
    write_hypothesis_evaluation(config=config)
