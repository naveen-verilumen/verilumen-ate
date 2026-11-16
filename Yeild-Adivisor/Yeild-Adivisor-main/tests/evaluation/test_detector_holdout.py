"""Holdout and scenario evaluation. Ground truth is joined only here, after detectors run."""

from __future__ import annotations

import json

from yield_improvement.detectors.runner import run_detectors_on_dir
from yield_improvement.evaluation import EXPECTED_SIGNALS, evaluate_all_synthetic, write_evaluation
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


def test_detectors_do_not_import_ground_truth():
    src = repo_root() / "src" / "yield_improvement" / "detectors"
    hits = []
    for path in src.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for token in (
            "true_cause",
            "scenario_id",
            "RUN_SUMMARY",
            "yield_improvement.evaluation",
        ):
            if token in text:
                hits.append(f"{path.name}: {token}")
    assert hits == []


def test_s16_no_signal_holdout(config):
    bundle = run_detectors_on_dir(_agent_dir(_id_for("S16")), config=config)
    assert bundle.results["no_signal"].status == "SIGNAL"
    assert bundle.results["no_signal"].hypothesis_detail in {
        "NO_MEANINGFUL_SIGNAL",
        "INSUFFICIENT_EVIDENCE",
    }
    systematic = [
        "spatial",
        "equipment",
        "temporal",
        "temperature",
        "parametric",
        "near_limit",
        "sequence",
        "contact",
        "lot",
        "wafer",
        "correlation",
    ]
    fired = [name for name in systematic if bundle.results[name].status == "SIGNAL"]
    assert fired == [], f"S16 false positives: {fired}"


def test_s01_random_holdout(config):
    bundle = run_detectors_on_dir(_agent_dir(_id_for("S01")), config=config)
    assert bundle.results["no_signal"].status == "SIGNAL"
    spatial_fp = bundle.results["spatial"].status == "SIGNAL"
    equipment_fp = bundle.results["equipment"].status == "SIGNAL"
    temporal_fp = bundle.results["temporal"].status == "SIGNAL"
    assert not spatial_fp
    assert not equipment_fp
    assert not temporal_fp


def test_s02_spatial_edge(config):
    bundle = run_detectors_on_dir(_agent_dir(_id_for("S02")), config=config)
    spatial = bundle.results["spatial"]
    assert spatial.status == "SIGNAL"
    assert spatial.hypothesis_family == "SPATIAL"
    assert spatial.hypothesis_detail == "EDGE"
    assert spatial.not_a_root_cause is True


def test_s15_dual_cause(config):
    bundle = run_detectors_on_dir(_agent_dir(_id_for("S15")), config=config)
    assert bundle.results["spatial"].status == "SIGNAL"
    assert bundle.results["spatial"].hypothesis_detail == "EDGE"
    assert bundle.results["temporal"].status == "SIGNAL"
    assert bundle.results["temporal"].hypothesis_detail == "DRIFT"


def test_s05_equipment_association_not_cause(config):
    bundle = run_detectors_on_dir(_agent_dir(_id_for("S05")), config=config)
    eq = bundle.results["equipment"]
    assert eq.status == "SIGNAL"
    assert eq.hypothesis_family == "EQUIPMENT"
    assert eq.not_a_root_cause is True


def test_s09_near_limit_does_not_change_limits(config):
    bundle = run_detectors_on_dir(_agent_dir(_id_for("S09")), config=config)
    nl = bundle.results["near_limit"]
    assert nl.status == "SIGNAL"
    assert nl.hypothesis_detail == "LIMIT_SENSITIVITY"
    assert any(e.name == "production_opportunity" and e.value == 0.0 for e in nl.evidence)
    assert any(e.name == "does_not_modify_limits" for e in (nl.counter_evidence or []))


def test_evaluation_table_has_required_columns(config):
    report = evaluate_all_synthetic(config=config)
    assert report["n_rows"] == 16 * 12
    row = report["rows"][0]
    for key in (
        "scenario",
        "detector",
        "expected_signal",
        "observed_signal",
        "status",
        "effect_size",
        "p_value",
        "adjusted_p_value",
        "correct",
        "false_positive",
        "false_negative",
        "sample_size",
    ):
        assert key in row
    s16 = [r for r in report["rows"] if r["scenario"] == "S16" and r["detector"] == "no_signal"]
    assert s16 and s16[0]["correct"] is True
    s02_spatial = [r for r in report["rows"] if r["scenario"] == "S02" and r["detector"] == "spatial"]
    assert s02_spatial and s02_spatial[0]["correct"] is True
    write_evaluation(config=config)
    assert EXPECTED_SIGNALS["S15"]["spatial"][1] == "EDGE"
