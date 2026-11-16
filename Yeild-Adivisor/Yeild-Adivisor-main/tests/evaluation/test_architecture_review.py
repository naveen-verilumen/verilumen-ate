"""Architecture review evaluation: immutability, policies, persisted evidence."""

from __future__ import annotations

import json

from yield_improvement.evaluation.architecture_review import (
    REQUIRED_JSON_KEYS,
    hash_active_artifact,
)
from yield_improvement.evaluation.ml import LIMIT_PHRASES
from yield_improvement.ml.benchmark import CORE_MODELS, run_lolo_models
from yield_improvement.ml.dataset import MLDataset
from yield_improvement.ml.models import MODEL_ORDER
from yield_improvement.utils.paths import repo_root

import numpy as np
import pandas as pd


def _review_path():
    return repo_root() / "evaluation" / "results" / "model_architecture_review.json"


def _load_review() -> dict:
    path = _review_path()
    assert path.is_file(), "model_architecture_review.json must be written by the evaluation-only benchmark"
    return json.loads(path.read_text(encoding="utf-8"))


def _tiny_dataset() -> MLDataset:
    rng = np.random.RandomState(7)
    lots = np.repeat(["A", "B", "C"], 12)
    n = len(lots)
    x = rng.uniform(-1, 1, n)
    frame = pd.DataFrame(
        {
            "x": x,
            "y": rng.uniform(-1, 1, n),
            "timestamp": ["2026-03-01T08:00:00Z"] * n,
            "tester_id": ["T01"] * n,
            "probe_card_id": ["PC-1"] * n,
            "prober_id": ["PRB-1"] * n,
            "temperature_c": rng.normal(25, 2, n),
            "voltage_v": [0.8] * n,
            "site": [0] * n,
            "lot_id": lots,
            "wafer_id": ["W0"] * n,
            "die_id": [f"D{i}" for i in range(n)],
            "attempt_id": [f"E{i}" for i in range(n)],
        }
    )
    y = pd.Series((x > 0).astype(int))
    return MLDataset(frame=frame, y=y, groups=pd.Series(lots), analysis_id="immut")


def test_active_model_immutable_during_benchmark():
    before = hash_active_artifact()
    run_lolo_models(_tiny_dataset(), model_names=["logistic"], with_importance=False)
    after = hash_active_artifact()
    assert before == after
    review = _load_review()
    assert review["active_artifact_sha256_before"] == review["active_artifact_sha256_after"]
    live = hash_active_artifact()
    assert live == review["active_artifact_sha256_after"]
    assert review["retrained_active"] is False
    assert review["active_model"]["artifact"] == "yi_ml_v1"
    assert review["active_model"]["name"] == "logistic"


def test_review_json_has_required_keys_and_safety():
    review = _load_review()
    for key in REQUIRED_JSON_KEYS:
        assert key in review
    assert review["production_authorized"] is False
    assert review["production_action"] == "FORBIDDEN"
    assert review["safety_eligible_production_count"] == 0
    assert review["safety_eligible_production_rate"] == 0.0
    assert review["invoked_agents"] == []
    assert review["decision"] in {"KEEP_LOGISTIC", "CONSIDER_ALTERNATIVE", "INCONCLUSIVE"}
    assert review["dataset_summary"]["n_lots"] == 8
    assert review["decision_rationale"]["n_lots"] == 8
    assert review["feature_contract"] == [
        "die_x",
        "die_y",
        "normalized_x",
        "normalized_y",
        "radial_distance",
        "edge_distance",
        "spatial_region",
        "timestamp_epoch",
        "temperature_c",
        "voltage_v",
        "site",
        "tester_id",
        "probe_card_id",
        "prober_id",
        "tester_fail_rate",
        "probe_fail_rate",
    ]
    assert set(CORE_MODELS).issubset(set(review["models_evaluated"]))
    assert MODEL_ORDER == ("logistic", "random_forest", "hist_gbm")
    for name in review["unavailable_models"]:
        assert review["unavailable_models"][name]["status"] == "NOT_EVALUATED"
        assert review["unavailable_models"][name]["reason"] == "unavailable_due_to_environment"


def test_raw_and_calibrated_not_mixed_and_per_lot_present():
    review = _load_review()
    for name in review["models_evaluated"]:
        raw = review["raw_metrics"][name]
        cal = review["calibrated_metrics"][name]
        assert "pr_auc" in raw and "pr_auc" in cal
        assert "brier" in raw and "brier" in cal
        assert name in review["per_lot_metrics"]
        assert len(review["per_lot_metrics"][name]["raw"]) == 8
        stab = review["lot_stability"][name]
        for key in ("roc_auc", "pr_auc", "brier", "failure_capture_at_top_10_percent", "failure_capture_at_top_20_percent"):
            assert set(stab[key]) >= {"mean", "std", "min", "max"}
        cal_block = review["calibration_analysis"][name]
        assert "raw_brier" in cal_block and "calibrated_brier" in cal_block
        assert "raw_reliability_bins" in cal_block
    assert review["paired_fold_comparisons"]
    assert review["fold_assignments"]
    train_test = [(set(r["train_lots"]), {r["held_out_lot"]}) for r in review["fold_assignments"]]
    for train, test in train_test:
        assert train.isdisjoint(test)


def test_s09_safety_policy():
    review = _load_review()
    assert review["scenario_policy"]["s09_no_limit"] is True
    blob = json.dumps(review).lower()
    for phrase in LIMIT_PHRASES:
        assert phrase not in blob
    assert "increase limit" not in blob
    assert "change limit" not in blob
    assert "relax limit" not in blob
    assert "modify threshold" not in blob


def test_s11_sequence_policy():
    review = _load_review()
    assert review["scenario_policy"]["s11_no_sequence_features"] is True
    s11 = next(r for r in review["scenario_results"] if r["scenario"] == "S11")
    for name, block in s11["models"].items():
        lowered = [f.lower() for f in block["feature_names"]]
        assert not any("sequence" in f or "later_test" in f or "test_index" in f for f in lowered)
        assert "lot_id" not in lowered
        assert "wafer_id" not in lowered


def test_s15_edge_and_drift_remain_separate():
    review = _load_review()
    assert review["scenario_policy"]["s15_separate"] is True
    s15 = next(r for r in review["scenario_results"] if r["scenario"] == "S15")
    for name, block in s15["models"].items():
        assert block["has_edge"] is True
        assert block["has_drift"] is True
        assert block["combined_root_cause"] is False
    blob = json.dumps(s15).lower()
    assert "edge_and_drift" not in blob


def test_s16_no_forced_hypothesis():
    review = _load_review()
    assert review["scenario_policy"]["s16_no_forced"] is True
    s16 = next(r for r in review["scenario_results"] if r["scenario"] == "S16")
    for name, block in s16["models"].items():
        assert block["no_confident_hypothesis"] is True
        assert block["n_hypotheses"] == 0


def test_s01_does_not_invent_hypothesis():
    review = _load_review()
    assert review["scenario_policy"]["s01_no_forced"] is True
    s01 = next(r for r in review["scenario_results"] if r["scenario"] == "S01")
    for name, block in s01["models"].items():
        assert block["no_confident_hypothesis"] is True


def test_s12_s13_do_not_use_identity_features():
    review = _load_review()
    assert review["scenario_policy"]["s12_no_lot_id_feature"] is True
    assert review["scenario_policy"]["s13_no_wafer_id_feature"] is True
    for sid in ("S12", "S13"):
        row = next(r for r in review["scenario_results"] if r["scenario"] == sid)
        for name, block in row["models"].items():
            assert "lot_id" not in block["feature_names"]
            assert "wafer_id" not in block["feature_names"]


def test_review_markdown_exists_and_does_not_activate():
    path = repo_root() / "docs" / "MODEL_ARCHITECTURE_REVIEW.md"
    text = path.read_text(encoding="utf-8").lower()
    assert path.is_file()
    assert "yi_ml_v1" in text
    assert "does not replace the active artifact" in text or "does not retrain" in text
    assert "production_authorized: false" in text
    assert "n_lots" in text
