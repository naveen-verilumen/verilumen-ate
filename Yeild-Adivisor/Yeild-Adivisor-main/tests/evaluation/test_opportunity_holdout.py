"""Phase 5 holdout. Ground truth is joined only here, after opportunity estimation."""

from __future__ import annotations

import json

from yield_improvement.evaluation.opportunity import evaluate_all_opportunities, write_opportunity_evaluation
from yield_improvement.opportunity.engine import estimate_from_dir
from yield_improvement.utils.paths import phase2_agent_visible_dir, repo_root


def _agent_dir(dataset_id: str):
    return phase2_agent_visible_dir() / dataset_id


def _id_for(scenario: str) -> str:
    path = repo_root() / "evaluation" / "ground_truth" / "synthetic" / "RUN_SUMMARY.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    for item in payload["scenarios"]:
        if item["scenario_id"] == scenario:
            return item["dataset_id"]
    raise AssertionError(scenario)


def test_opportunity_engine_does_not_import_ground_truth():
    src = repo_root() / "src" / "yield_improvement" / "opportunity"
    hits = []
    for path in src.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for token in ("true_cause", "scenario_id", "RUN_SUMMARY", "yield_improvement.evaluation"):
            if token in text:
                hits.append(f"{path.name}: {token}")
    assert hits == []


def test_s01_no_invented_opportunity(config):
    bundle = estimate_from_dir(_agent_dir(_id_for("S01")), config=config)
    assert bundle.no_actionable_opportunity is True
    assert bundle.opportunities == []
    assert bundle.summary.observed_loss_rate >= 0.0
    assert bundle.summary.safety_eligible_total_rate == 0.0


def test_s16_no_invented_opportunity(config):
    bundle = estimate_from_dir(_agent_dir(_id_for("S16")), config=config)
    assert bundle.no_actionable_opportunity is True
    assert bundle.opportunities == []
    assert bundle.summary.safety_eligible_total_rate == 0.0


def test_s15_dual_cause_not_double_counted(config):
    bundle = estimate_from_dir(_agent_dir(_id_for("S15")), config=config)
    edge = next(o for o in bundle.opportunities if o.family == "SPATIAL" and o.detail == "EDGE")
    drift = next(o for o in bundle.opportunities if o.family == "PROCESS" and o.detail == "DRIFT")
    union = next(o for o in bundle.opportunities if o.opportunity_id == "OPP-UNION-PRIMARY")
    assert edge.safety_eligible_production_rate == 0.0
    assert drift.safety_eligible_production_rate == 0.0
    summed = bundle.summary.sum_of_individual_upper_bounds_rate
    assert bundle.summary.union_upper_bound_rate <= summed + 1e-12
    assert union.union_count == union.upper_bound_count
    lot = [o for o in bundle.opportunities if o.detail == "LOT_VARIATION"]
    if lot:
        assert lot[0].included_in_union is False
    assert "sum of individual" not in union.statement.lower() or "not the sum" in union.statement.lower()


def test_s09_does_not_change_limits(config):
    bundle = estimate_from_dir(_agent_dir(_id_for("S09")), config=config)
    item = next(o for o in bundle.opportunities if o.detail == "LIMIT_SENSITIVITY")
    blob = json.dumps(bundle.to_public_dict()).lower()
    assert "set_limit" not in blob
    assert "increase test limit" not in blob
    assert "candidate_limit" not in blob
    assert item.safety_eligible_production_rate == 0.0
    assert item.plausible_unavailable is True
    assert any("does not modify" in n.lower() for n in item.limitations)


def test_s11_does_not_invent_sequence_opportunity(config):
    bundle = estimate_from_dir(_agent_dir(_id_for("S11")), config=config)
    seq = [o for o in bundle.opportunities if o.family == "TEST" and o.detail == "SEQUENCE"]
    assert seq == []
    assert bundle.summary.safety_eligible_total_rate == 0.0


def test_every_opportunity_production_zero_on_holdout(config):
    report = evaluate_all_opportunities(config=config)
    assert report["n_scenarios"] == 16
    assert report["s01_no_actionable"] is True
    assert report["s16_no_actionable"] is True
    assert report["s15_both_present"] is True
    assert report["s15_union_le_sum"] is True
    assert report["all_production_zero"] is True
    assert report["s09_no_limit_change"] is True
    write_opportunity_evaluation(config=config)
    by = {r["scenario"]: r for r in report["rows"]}
    assert by["S08"]["missing_expected"] == []
    assert by["S12"]["missing_expected"] == []
    assert by["S13"]["missing_expected"] == []
    for row in report["rows"]:
        assert row["production_eligible"] == 0.0
