"""Architecture benchmark protocol: same LOLO folds, no leakage, nested calibration."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from yield_improvement.ml.benchmark import (
    CORE_MODELS,
    EXTRA_CANDIDATES,
    _assert_feature_contract,
    fold_assignments,
    probe_extra_models,
    run_lolo_models,
)
from yield_improvement.ml.calibration import ProbabilityCalibrator
from yield_improvement.ml.dataset import MLDataset
from yield_improvement.ml.models import MODEL_ORDER


def _tiny_dataset(n_per_lot: int = 16, n_lots: int = 3, seed: int = 7) -> MLDataset:
    rng = np.random.RandomState(seed)
    lots = np.repeat([f"L{i}" for i in range(n_lots)], n_per_lot)
    n = len(lots)
    x = rng.uniform(-1.0, 1.0, n)
    y_coord = rng.uniform(-1.0, 1.0, n)
    fail = (x > 0.15).astype(int)
    flip = rng.rand(n) < 0.12
    fail = np.where(flip, 1 - fail, fail)
    frame = pd.DataFrame(
        {
            "x": x,
            "y": y_coord,
            "timestamp": ["2026-03-01T08:00:00Z"] * n,
            "tester_id": np.where(rng.rand(n) > 0.5, "T01", "T02"),
            "probe_card_id": ["PC-1"] * n,
            "prober_id": ["PRB-1"] * n,
            "temperature_c": rng.normal(25.0, 3.0, n),
            "voltage_v": [0.8] * n,
            "site": rng.randint(0, 2, n),
            "lot_id": lots,
            "wafer_id": [f"W{i % 2}" for i in range(n)],
            "die_id": [f"D{i}" for i in range(n)],
            "attempt_id": [f"E{i}" for i in range(n)],
        }
    )
    return MLDataset(frame=frame, y=pd.Series(fail), groups=pd.Series(lots), analysis_id="tiny-arch")


def test_production_model_order_unchanged():
    assert MODEL_ORDER == ("logistic", "random_forest", "hist_gbm")
    assert CORE_MODELS == MODEL_ORDER


def test_same_lolo_folds_across_models():
    data = _tiny_dataset()
    bench = run_lolo_models(data, model_names=["logistic", "random_forest"], with_importance=False)
    assert bench["same_folds_all_models"] is True
    lots_a = [row["lot"] for row in bench["models"]["logistic"]["per_lot_raw"]]
    lots_b = [row["lot"] for row in bench["models"]["random_forest"]["per_lot_raw"]]
    assert lots_a == lots_b
    assert lots_a == [row["held_out_lot"] for row in bench["fold_assignments"]]
    assert set(lots_a) == {"L0", "L1", "L2"}


def test_no_lot_or_wafer_leakage_in_fold_assignments():
    data = _tiny_dataset()
    _, splits, rows = fold_assignments(data)
    lots = data.groups.astype(str).to_numpy()
    wafers = data.frame["wafer_id"].astype(str).to_numpy()
    for (train_idx, test_idx), meta in zip(splits, rows):
        train_lots = set(lots[train_idx])
        test_lots = set(lots[test_idx])
        assert train_lots.isdisjoint(test_lots)
        assert train_lots & test_lots == set()
        train_w = set(zip(lots[train_idx], wafers[train_idx]))
        test_w = set(zip(lots[test_idx], wafers[test_idx]))
        assert train_w.isdisjoint(test_w)
        assert meta["held_out_lot"] in test_lots
        assert meta["held_out_lot"] not in train_lots


def test_hidden_gt_features_rejected_on_source_frame():
    data = _tiny_dataset()
    bad = data.frame.copy()
    bad["scenario_id"] = "S99"
    leaked = MLDataset(frame=bad, y=data.y, groups=data.groups, analysis_id="leak")
    with pytest.raises(ValueError, match="forbidden"):
        run_lolo_models(leaked, model_names=["logistic"], with_importance=False)


def test_true_cause_rejected_as_model_feature():
    with pytest.raises(ValueError, match="forbidden"):
        _assert_feature_contract(["die_x", "true_cause", "edge_distance"])


def test_lot_id_not_allowed_as_transformed_feature():
    with pytest.raises(ValueError, match="forbidden"):
        _assert_feature_contract(["die_x", "lot_id"], allow_identity_keys=False)


def test_fold_local_calibration_never_sees_held_out_labels(monkeypatch):
    data = _tiny_dataset()
    seen: list[np.ndarray] = []
    original = ProbabilityCalibrator.fit

    def wrapped(self, raw, y):
        seen.append(np.asarray(y, dtype=int).copy())
        return original(self, raw, y)

    monkeypatch.setattr(ProbabilityCalibrator, "fit", wrapped)
    run_lolo_models(data, model_names=["logistic"], with_importance=False)
    _, splits, _ = fold_assignments(data)
    y = data.y.to_numpy()
    assert len(seen) == len(splits)
    for recorded, (train_idx, test_idx) in zip(seen, splits):
        assert np.array_equal(recorded, y[train_idx])
        assert not np.array_equal(recorded, y[test_idx])


def test_per_lot_metrics_and_stability():
    data = _tiny_dataset()
    bench = run_lolo_models(data, model_names=["logistic"], with_importance=False)
    rows = bench["models"]["logistic"]["per_lot_raw"]
    assert len(rows) == 3
    for row in rows:
        assert "lot" in row
        assert "roc_auc" in row
        assert "pr_auc" in row
        assert "brier" in row
        assert "failure_capture_at_top_10_percent" in row
        assert "failure_capture_at_top_20_percent" in row
        assert "calibration_error" in row
    stab = bench["models"]["logistic"]["lot_stability_raw"]
    for key in ("roc_auc", "pr_auc", "brier", "failure_capture_at_top_10_percent", "failure_capture_at_top_20_percent"):
        summary = stab[key]
        assert set(summary) >= {"mean", "std", "min", "max", "n"}
        assert summary["n"] == 3


def test_paired_fold_comparisons():
    data = _tiny_dataset()
    bench = run_lolo_models(data, model_names=["logistic", "random_forest"], with_importance=False)
    pairs = bench["paired_fold_comparisons"]
    pr = next(p for p in pairs if p["model_a"] == "logistic" and p["model_b"] == "random_forest" and p["metric"] == "pr_auc")
    assert pr["n_folds"] == 3
    assert "mean_paired_difference_a_minus_b" in pr
    assert "std_paired_difference" in pr
    assert pr["n_folds_a_better"] + pr["n_folds_b_better"] <= pr["n_folds"]
    assert pr["n_folds_a_better"] >= 0 and pr["n_folds_b_better"] >= 0


def test_feature_importance_stability_is_predictive_not_causal():
    data = _tiny_dataset()
    bench = run_lolo_models(data, model_names=["logistic"], with_importance=True, importance_max_rows=40)
    rows = bench["models"]["logistic"]["feature_importance_stability"]
    assert rows
    for row in rows:
        assert "mean_importance" in row
        assert "std_importance" in row
        assert "rank_mean" in row
        assert "rank_std" in row
        assert "n_folds_top5" in row
        assert "n_folds_top10" in row
        assert "not a causal" in row["note"].lower()
        assert "root cause" not in row["note"].lower() or "not" in row["note"].lower()


def test_raw_and_calibrated_metrics_are_both_persisted():
    data = _tiny_dataset()
    bench = run_lolo_models(data, model_names=["logistic"], with_importance=False)
    raw = bench["models"]["logistic"]["raw"]
    cal = bench["models"]["logistic"]["calibrated"]
    for payload in (raw, cal):
        for key in ("roc_auc", "pr_auc", "precision", "recall", "f1", "balanced_accuracy", "brier", "log_loss"):
            assert key in payload
        assert "failure_capture_at_top_5_percent" in payload
        assert "failure_capture_at_top_10_percent" in payload
        assert "failure_capture_at_top_20_percent" in payload
        assert "reliability_bins" in payload


def test_deterministic_evaluation():
    data = _tiny_dataset()
    a = run_lolo_models(data, model_names=["logistic"], with_importance=False)
    b = run_lolo_models(data, model_names=["logistic"], with_importance=False)
    assert a["models"]["logistic"]["raw"]["pr_auc"] == b["models"]["logistic"]["raw"]["pr_auc"]
    assert a["models"]["logistic"]["raw"]["brier"] == b["models"]["logistic"]["raw"]["brier"]
    assert [row["held_out_lot"] for row in a["fold_assignments"]] == [row["held_out_lot"] for row in b["fold_assignments"]]


def test_extra_candidates_are_probed_not_installed():
    available, unavailable = probe_extra_models()
    for name in available:
        assert name in EXTRA_CANDIDATES
    for name, reason in unavailable.items():
        assert name in EXTRA_CANDIDATES
        assert "unavailable_due_to_environment" in reason
    assert set(available) | set(unavailable) == set(EXTRA_CANDIDATES)


def test_transformed_features_stay_on_contract():
    data = _tiny_dataset()
    bench = run_lolo_models(data, model_names=["logistic"], with_importance=False)
    names = bench["models"]["logistic"]["feature_names"]
    forbidden = {"lot_id", "wafer_id", "die_id", "scenario_id", "true_cause", "injected_effect", "sequence", "later_test"}
    lowered = {n.lower() for n in names}
    assert forbidden.isdisjoint(lowered)
    for token in ("sequence", "later_test", "test_index"):
        assert not any(token in n.lower() for n in names)
