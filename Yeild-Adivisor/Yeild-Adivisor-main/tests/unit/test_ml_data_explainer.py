from __future__ import annotations

import json

from yield_improvement.ml.data_explainer import explain_dataset, read_champion_feature_list, write_audit
from yield_improvement.model_lifecycle.hashes import hash_files
from yield_improvement.utils.paths import phase2_agent_visible_dir, repo_root

CHAMPION_HASHES = {
    "feature_list.json": "3e4db1e3de47382f5533fe0e54d442f638f83e4bac7b0eeb2c7da6364462e0d7",
    "metadata.json": "6a3ffa163e808042c5cd08d270c0d7fe042e42d977a1b166e88ef2d7b37d71ad",
    "metrics.json": "16ea9d76745142efc8f2b61eee28ce614cd255fa36c42a4efe6aedfdabadddec",
    "model.pkl": "cab3a1b74560263b59b8d6c95f852b15fc91d7a0b91f311576a10aa11aeb2d70",
}

CHAMPION_DS = phase2_agent_visible_dir() / "ds_0b5542c71e1a13e0"


def test_feature_list_matches_artifact():
    payload = explain_dataset(CHAMPION_DS)
    assert payload["feature_list"]["champion_artifact"] == read_champion_feature_list()
    assert payload["feature_list"]["n_champion_features"] == 16


def test_fold_count_matches_lots_and_no_overlap():
    payload = explain_dataset(CHAMPION_DS)
    lots = payload["lots"]
    assert payload["split"]["n_folds"] == len(lots)
    seen_test: list[str] = []
    for fold in payload["folds"]:
        assert fold["lot_overlap"] == []
        assert len(fold["test_lots"]) == 1
        seen_test.extend(fold["test_lots"])
        assert set(fold["training_lots"]).isdisjoint(set(fold["test_lots"]))
        assert fold["train_dies"] + fold["test_dies"] == payload["population_counts"]["ml_samples"]
    assert sorted(seen_test) == lots
    assert payload["split"]["every_lot_exactly_once_as_test"] is True


def test_excluded_leakage_columns_absent_from_model_features():
    payload = explain_dataset(CHAMPION_DS)
    features = set(payload["feature_list"]["champion_artifact"])
    forbidden = {
        "lot_id",
        "wafer_id",
        "die_id",
        "scenario_id",
        "true_cause",
        "injected_effect",
        "generator_seed",
        "pass_fail",
        "disposition",
        "sbin",
        "is_retest",
        "first_pass_fail",
        "sequence_index",
    }
    assert forbidden.isdisjoint(features)
    assert payload["leakage_audit"] == "PASS"


def test_target_definition_matches_implementation():
    payload = explain_dataset(CHAMPION_DS)
    target = payload["target_definition"]
    assert target["name"] == "first_pass_fail"
    assert "FAIL" in target["positive"]
    assert "PASS" in target["negative"]
    pop = payload["population_counts"]
    assert pop["ml_equals_eligible"] is True
    assert pop["positive_labels"] + pop["negative_labels"] == pop["ml_samples"]
    assert pop["positive_labels"] == pop["first_pass_fail_count"]


def test_audit_is_deterministic(tmp_path):
    first = explain_dataset(CHAMPION_DS)
    second = explain_dataset(CHAMPION_DS)
    p1 = tmp_path / "a.json"
    p2 = tmp_path / "b.json"
    write_audit(first, p1)
    write_audit(second, p2)
    assert p1.read_text(encoding="utf-8") == p2.read_text(encoding="utf-8")


def test_explain_does_not_modify_champion():
    before = hash_files(repo_root() / "artifacts" / "ml" / "yi_ml_v1")
    explain_dataset(CHAMPION_DS)
    after = hash_files(repo_root() / "artifacts" / "ml" / "yi_ml_v1")
    assert before == after == CHAMPION_HASHES
