"""Checks for the V2 architecture benchmark. Does not train models."""

from __future__ import annotations

import json

import numpy as np
import pytest

from yield_improvement.ml.benchmark import ACTIVE_FEATURE_CONTRACT, _assert_feature_contract
from yield_improvement.ml.config import LeakageError, load_feature_policy
from yield_improvement.ml.dataset import assert_no_forbidden_columns
from yield_improvement.ml.benchmark_v1 import (
    BENCHMARK_ID,
    PROTECTED,
    REGISTRY_HASH,
    SEQUENCE_SLOTS,
    artifact_dir,
    audit_gru_sequence,
    dataset_dir,
)
from yield_improvement.ml.calibration import ProbabilityCalibrator
from yield_improvement.ml.dataset import load_ml_dataset
from yield_improvement.ml.evaluation import compute_metrics
from yield_improvement.ml.features import fit_feature_builder
from yield_improvement.ml.split import make_splits
from yield_improvement.ml.config import load_ml_config
from yield_improvement.model_lifecycle.hashes import CHAMPION_FILES, hash_files, sha256_file
from yield_improvement.model_lifecycle.registry import default_paths, load_registry
from yield_improvement.utils.paths import repo_root


def _results() -> dict:
    path = artifact_dir() / "results.json"
    assert path.is_file(), "benchmark_v1 results.json must already exist"
    return json.loads(path.read_text(encoding="utf-8"))


def test_lolo_folds_are_five_lots_without_overlap():
    report = _results()
    folds = report["fold_assignments"]
    assert report["split_strategy"] == "leave_one_lot_out"
    assert len(folds) == 5
    held = []
    for row in folds:
        assert row["train_samples"] == 2000
        assert row["test_samples"] == 500
        assert row["test_lot"] not in row["training_lots"]
        assert len(row["training_lots"]) == 4
        held.append(row["test_lot"])
    assert sorted(held) == ["L001", "L002", "L003", "L004", "L005"]
    data = load_ml_dataset(dataset_dir())
    strategy, splits = make_splits(data.groups.to_numpy(), load_ml_config())
    assert strategy == "leave_one_lot_out"
    assert len(splits) == 5
    groups = data.groups.to_numpy()
    for train_idx, test_idx in splits:
        assert len(train_idx) == 2000 and len(test_idx) == 500
        assert set(groups[train_idx]).isdisjoint(set(groups[test_idx]))


def test_feature_contract_excludes_target_and_parametrics():
    report = _results()
    assert report["feature_contract"] == list(ACTIVE_FEATURE_CONTRACT)
    assert report["parametric_measurements_included"] is False
    blocked = {
        "first_pass_fail",
        "pass_fail",
        "failure_code",
        "primary_failure",
        "sbin",
        "scenario_id",
        "true_cause",
        "ground_truth",
        "injected_effect",
        "VMIN",
        "VMAX",
        "IDDQ",
        "relative_position_within_lot",
    }
    assert not (set(report["feature_contract"]) & blocked)
    data = load_ml_dataset(dataset_dir())
    names = list(fit_feature_builder(data.frame, data.y).feature_names_)
    assert names == list(ACTIVE_FEATURE_CONTRACT)
    for payload in report["models"].values():
        assert payload["feature_names"] == list(ACTIVE_FEATURE_CONTRACT)
    with pytest.raises(ValueError, match="ground_truth"):
        _assert_feature_contract(["die_x", "ground_truth"])
    with pytest.raises(LeakageError, match="failure_code"):
        assert_no_forbidden_columns(["failure_code", "first_pass_fail"], load_feature_policy())


def test_gru_sequence_is_blocked_instead_of_using_outcomes():
    audit = audit_gru_sequence(dataset_dir())
    assert audit["status"] == "BLOCKED_LEAKAGE_RISK"
    assert audit["trained"] is False
    assert audit["metrics"] is None
    assert audit["order_matches_defined_slots"] is True
    assert [row["test_id"] for row in audit["sequence_slots"]] == [slot[0] for slot in SEQUENCE_SLOTS]
    assert audit["first_pass_attempt_count"] == 2500
    assert audit["retest_rows_excluded"] > 0
    assert "test_pass_fail" in audit["outcome_columns"]
    assert "failure_code" in audit["outcome_columns"]
    assert audit["measurement_columns"] == []
    assert audit["dies_where_any_test_fail_equals_attempt_fail"] == audit["dies_compared"] == 2500
    report = _results()
    assert report["blocked"]["gru"]["status"] == "BLOCKED_LEAKAGE_RISK"
    assert "gru" not in report["models"]


def test_metric_bundle_and_fold_local_calibration():
    y = np.array([0, 0, 0, 0, 0, 1, 1])
    proba = np.array([0.1, 0.1, 0.1, 0.2, 0.2, 0.8, 0.9])
    metrics = compute_metrics(y, proba)
    assert metrics.n_samples == 7
    assert metrics.n_positives == 2
    assert metrics.positive_rate == pytest.approx(2 / 7)
    assert metrics.roc_auc == 1.0
    assert metrics.pr_auc == 1.0
    assert metrics.failure_capture_at_top_20_percent == 1.0
    assert metrics.failure_capture_at_top_10_percent == 0.5
    raw_train = np.linspace(0.05, 0.95, 12)
    y_train = np.array([0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1])
    calibrator = ProbabilityCalibrator().fit(raw_train, y_train)
    assert calibrator.fitted is True
    held_out = np.array([0.2, 0.8])
    transformed = calibrator.transform(held_out)
    assert transformed.shape == held_out.shape
    assert transformed.min() >= 0.0 and transformed.max() <= 1.0
    report = _results()
    assert report["calibration"]["fit_on"] == "training_fold_raw_scores_only"
    assert report["calibration"]["held_out_lot_labels_used"] is False
    for payload in report["models"].values():
        assert payload["raw"]["brier"] is not None
        assert payload["calibrated"]["brier"] is not None
        assert payload["calibrated"]["ece"] is not None


def test_benchmark_artifact_stays_a_candidate_and_leaves_yi_ml_v1_active():
    report = _results()
    assert report["benchmark_id"] == BENCHMARK_ID
    assert report["state"] == "CANDIDATE"
    assert report["promoted"] is False
    assert report["automatic_activation"] is False
    assert report["production_authorized"] is False
    assert report["selected_model"] is None
    assert report["active_model"] == "yi_ml_v1"
    assert report["n_samples"] == 2500
    assert report["n_positives"] == 251
    assert report["positive_rate"] == 0.1004
    registry = load_registry(default_paths())
    assert registry["active_version"] == "yi_ml_v1"
    assert registry["models"]["yi_ml_v1"]["state"] == "ACTIVE"
    assert registry["production_authorized"] is False
    integrity = report["integrity"]
    assert integrity["protected_hashes_before"] == integrity["protected_hashes_after"]
    assert integrity["dataset_hashes_before"] == integrity["dataset_hashes_after"]
    assert integrity["registry_sha256_before"] == integrity["registry_sha256_after"] == REGISTRY_HASH
    root = repo_root() / "artifacts" / "ml"
    for name in PROTECTED:
        assert hash_files(root / name, CHAMPION_FILES) == integrity["protected_hashes_after"][name]
    assert sha256_file(default_paths().registry_path) == REGISTRY_HASH
    for name, payload in report["models"].items():
        assert payload["state"] == "CANDIDATE"
        assert payload["promoted"] is False
        assert payload["status"] == "EVALUATED"
        assert name not in PROTECTED
        for lot_row in payload["per_lot_calibrated"]:
            assert lot_row["lot"] in {"L001", "L002", "L003", "L004", "L005"}
            assert lot_row["n_samples"] == 500
