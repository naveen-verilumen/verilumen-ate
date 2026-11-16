"""Phase 6 holdout. Ground truth is joined only here."""

from __future__ import annotations

import json

from yield_improvement.evaluation.validation import evaluate_all_validation, write_validation_evaluation
from yield_improvement.utils.paths import phase2_agent_visible_dir, repo_root
from yield_improvement.validation.validator import validate_from_dir


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


def test_validator_does_not_import_ground_truth():
    src = repo_root() / "src" / "yield_improvement" / "validation"
    hits = []
    for path in src.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for token in ("true_cause", "scenario_id", "RUN_SUMMARY", "yield_improvement.evaluation"):
            if token in text:
                hits.append(f"{path.name}: {token}")
    assert hits == []


def test_s01_no_invented_recommendation(config):
    bundle = validate_from_dir(_dir("S01"), config=config)
    assert bundle.no_actionable_recommendation is True
    assert bundle.results == []
    assert bundle.observed_loss_rate >= 0.0
    assert bundle.production_authorized is False
    assert bundle.safety_eligible_production_rate == 0.0


def test_s16_no_invented_recommendation(config):
    bundle = validate_from_dir(_dir("S16"), config=config)
    assert bundle.no_actionable_recommendation is True
    assert bundle.results == []


def test_s02_edge_is_evidence_based(config):
    bundle = validate_from_dir(_dir("S02"), config=config)
    edge = next(r for r in bundle.results if r.family == "SPATIAL" and r.detail == "EDGE")
    assert edge.recommendation in {"INVESTIGATE", "REVIEW", "MONITOR", "NEEDS_MORE_DATA"}
    assert edge.recommendation != "REJECTED"
    assert "associated" in edge.limitations[0].lower() or edge.not_a_root_cause is True
    assert edge.production_authorized is False


def test_s15_keeps_edge_and_drift_separate(config):
    bundle = validate_from_dir(_dir("S15"), config=config)
    families = {(r.family, r.detail) for r in bundle.results if r.hypothesis_id}
    assert ("SPATIAL", "EDGE") in families
    assert ("PROCESS", "DRIFT") in families
    assert not any(r.family == "UNION" and r.recommendation == "INVESTIGATE" for r in bundle.results)
    union = next(r for r in bundle.results if r.opportunity_id == "OPP-UNION-PRIMARY")
    assert union.recommendation == "REVIEW"
    assert "not a combined root cause" in union.recommendation_reason.lower() or "not a combined" in union.recommendation_reason.lower()
    assert bundle.overlap_summary["union_upper_bound_rate"] <= bundle.overlap_summary["sum_of_individual_upper_bounds_rate"] + 1e-12
    lot = [r for r in bundle.results if r.detail == "LOT_VARIATION"]
    if lot:
        assert lot[0].recommendation in {"MONITOR", "REVIEW", "NEEDS_MORE_DATA"}
        assert lot[0].recommendation != "INVESTIGATE" or lot[0].family != "PROCESS"


def test_s09_no_limit_recommendation(config):
    bundle = validate_from_dir(_dir("S09"), config=config)
    item = next(r for r in bundle.results if r.detail == "LIMIT_SENSITIVITY")
    assert item.recommendation in {"INVESTIGATE", "REVIEW", "NEEDS_MORE_DATA"}
    blob = json.dumps(bundle.to_public_dict()).lower()
    for phrase in ("set_limit", "increase limit", "decrease limit", "change limit", "optimize limit", "set new limit"):
        assert phrase not in blob
    assert item.safety_eligible_production_rate == 0.0


def test_s11_sequence_censoring(config):
    bundle = validate_from_dir(_dir("S11"), config=config)
    seq = [r for r in bundle.results if r.family == "TEST" and r.detail == "SEQUENCE"]
    assert not any(r.recommendation == "INVESTIGATE" for r in seq)
    assert any("stop-on-fail" in n.lower() or "censored" in n.lower() for n in bundle.limitations)


def test_phase6_holdout_table(config):
    report = evaluate_all_validation(config=config)
    assert report["n_scenarios"] == 16
    assert report["s01_no_actionable"] is True
    assert report["s16_no_actionable"] is True
    assert report["s15_edge_and_drift"] is True
    assert report["s15_no_combined_root_cause"] is True
    assert report["s15_union_not_sum"] is True
    assert report["s09_no_limit_change"] is True
    assert report["s11_no_sequence_investigate"] is True
    assert report["s11_censoring_recorded"] is True
    assert report["all_production_zero"] is True
    assert report["no_invocations"] is True
    assert report["safety_violations"] == 0
    write_validation_evaluation(config=config)
    by = {r["scenario"]: r for r in report["rows"]}
    assert by["S03"]["has_center"] is True
    assert by["S04"]["has_ring"] is True
    assert by["S05"]["no_limit_change"] is True
    assert by["S08"]["n_results"] >= 1
    assert by["S12"]["n_results"] >= 1
    assert by["S13"]["n_results"] >= 1
    assert by["S14"]["n_results"] >= 1


def test_validation_is_deterministic(config):
    folder = _dir("S02")
    a = validate_from_dir(folder, config=config)
    b = validate_from_dir(folder, config=config)
    assert a.model_dump() == b.model_dump()
