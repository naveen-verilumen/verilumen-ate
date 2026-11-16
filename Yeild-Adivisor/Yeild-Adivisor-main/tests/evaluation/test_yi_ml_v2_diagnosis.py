"""Read-only diagnosis of the saved yi_ml_v2 candidate. Does not train or write artifacts."""

from __future__ import annotations

import json
import pickle

import numpy as np
import pytest

from yield_improvement.ml.benchmark import ACTIVE_FEATURE_CONTRACT
from yield_improvement.ml.dataset import PARAM_NAMES, load_ml_dataset
from yield_improvement.ml.features import fit_feature_builder
from yield_improvement.ml.split import make_splits
from yield_improvement.ml.config import load_ml_config
from yield_improvement.model_lifecycle.hashes import CHAMPION_FILES, hash_files
from yield_improvement.model_lifecycle.registry import default_paths, load_registry
from yield_improvement.synthetic.v2_generator import is_center, is_edge
from yield_improvement.utils.paths import repo_root

DATASET = repo_root() / "data" / "synthetic" / "agent_visible" / "yi_synthetic_v2"
V2 = repo_root() / "artifacts" / "ml" / "yi_ml_v2"
V1 = repo_root() / "artifacts" / "ml" / "yi_ml_v1"
GT = repo_root() / "evaluation" / "ground_truth" / "synthetic_v2" / "yi_synthetic_v2.json"
BLOCKED = {
    "VMIN",
    "VMAX",
    "IDDQ",
    "VDD",
    "SUPPLY_CURRENT",
    "CONTACT_RESISTANCE",
    "INTERCONNECT_RESISTANCE",
    "ON_RESISTANCE",
}


@pytest.fixture(scope="module")
def ml_data():
    return load_ml_dataset(DATASET)


@pytest.fixture(scope="module")
def evaluation():
    return json.loads((V2 / "evaluation.json").read_text(encoding="utf-8"))


def test_saved_contract_matches_v2_counts(ml_data):
    features = json.loads((V2 / "feature_list.json").read_text(encoding="utf-8"))
    meta = json.loads((V2 / "metadata.json").read_text(encoding="utf-8"))
    assert len(ml_data.frame) == 2500
    assert int(ml_data.y.sum()) == 251
    assert int((ml_data.y == 0).sum()) == 2249
    assert features == list(ACTIVE_FEATURE_CONTRACT)
    assert meta["feature_count"] == 16
    assert meta["n_folds"] == 5
    assert meta["parametric_join"] is False
    assert not (set(features) & BLOCKED)
    assert not (set(features) & set(PARAM_NAMES))
    manifest = json.loads((V2 / "training_manifest.json").read_text(encoding="utf-8"))
    assert len(manifest["folds"]) == 5
    assert [row["test_lot"] for row in manifest["folds"]] == ["L001", "L002", "L003", "L004", "L005"]


def test_pooled_metrics_are_worse_than_fold_averages_and_base_rate(ml_data, evaluation):
    pooled = evaluation["aggregate_calibrated"]
    folds = evaluation["per_lot_calibrated"]
    prevalence = float(ml_data.y.mean())
    mean_roc = float(np.mean([row["roc_auc"] for row in folds]))
    assert pooled["n_samples"] == 2500
    assert pooled["n_positives"] == 251
    assert pooled["roc_auc"] < 0.5 < mean_roc
    assert pooled["pr_auc"] < prevalence
    assert pooled["brier"] > prevalence * (1.0 - prevalence)
    assert pooled["failure_capture_at_top_10_percent"] < 0.10
    assert pooled["failure_capture_at_top_20_percent"] < 0.20
    by_lot = {row["lot"]: row for row in folds}
    assert by_lot["L004"]["n_positives"] == 97
    assert by_lot["L004"]["pr_auc"] < by_lot["L004"]["positive_rate"] + 0.02
    assert all(row["tp"] == 0 for row in evaluation["confusion_by_fold"] if row["test_lot"] != "L005")


def test_calibrated_scores_for_early_lots_stay_below_one_half(evaluation):
    for row in evaluation["per_lot_calibrated"]:
        if row["lot"] == "L005":
            continue
        usable = [b for b in row["reliability_bins"] if not b["insufficient_sample_size"]]
        assert usable
        assert all(b["bin"] < "0.5" for b in usable)


def test_spatial_feature_does_not_match_generator_border(ml_data):
    frame = ml_data.frame
    builder = fit_feature_builder(frame, ml_data.y)
    region = builder.transform(frame)["spatial_region"]
    border = np.array([is_edge(int(x), int(y), 10, 10) for x, y in zip(frame["x"], frame["y"])])
    middle = np.array([is_center(int(x), int(y), 10, 10) for x, y in zip(frame["x"], frame["y"])])
    ml_edge = region.eq("EDGE").to_numpy()
    ml_center = region.eq("CENTER").to_numpy()
    assert int((border & ml_edge).sum()) / int(border.sum()) < 0.5
    assert int((middle & ml_center).sum()) / int(middle.sum()) < 0.2
    y = ml_data.y.to_numpy()
    lot2 = frame["lot_id"].eq("L002").to_numpy()
    assert float(y[lot2 & border].mean()) > float(y[lot2 & ~border].mean()) + 0.05


def test_coordinate_pairs_are_exactly_collinear(ml_data):
    matrix = fit_feature_builder(ml_data.frame, ml_data.y).transform(ml_data.frame)
    pairs = (
        ("die_x", "normalized_x", 1.0),
        ("die_y", "normalized_y", 1.0),
        ("radial_distance", "edge_distance", -1.0),
    )
    for left, right, expected in pairs:
        corr = float(np.corrcoef(matrix[left].astype(float), matrix[right].astype(float))[0, 1])
        assert corr == pytest.approx(expected, abs=1e-6)


def test_held_out_lot_timestamps_fall_outside_training_range(ml_data):
    cfg = load_ml_config()
    groups = ml_data.groups.to_numpy()
    _, splits = make_splits(groups, cfg)
    saw_negative = False
    saw_large_positive = False
    for train_idx, test_idx in splits:
        builder = fit_feature_builder(ml_data.frame.iloc[train_idx], ml_data.y.iloc[train_idx])
        epoch = builder.transform(ml_data.frame.iloc[test_idx])["timestamp_epoch"].astype(float)
        lot = set(groups[test_idx])
        assert len(lot) == 1
        if "L001" in lot:
            assert float(epoch.max()) < 0.0
            saw_negative = True
        if "L005" in lot:
            assert float(epoch.min()) > 100_000.0
            saw_large_positive = True
    assert saw_negative and saw_large_positive


def test_offline_ground_truth_comparison_stays_out_of_the_ml_package(evaluation):
    hidden = json.loads(GT.read_text(encoding="utf-8"))
    signals = {lot: row["expected_signal"] for lot, row in hidden["lots"].items()}
    assert signals == {
        "L001": "NONE",
        "L002": "SPATIAL.EDGE",
        "L003": "EQUIPMENT.DEGRADATION",
        "L004": "PROCESS.DRIFT",
        "L005": "WEAK",
    }
    by_lot = {row["lot"]: row for row in evaluation["per_lot_calibrated"]}
    assert by_lot["L002"]["roc_auc"] > by_lot["L001"]["roc_auc"]
    assert by_lot["L004"]["failure_capture_at_top_10_percent"] < 0.10
    ml_src = repo_root() / "src" / "yield_improvement" / "ml"
    for path in ml_src.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "evaluation/ground_truth" not in text
        assert "synthetic_v2" not in text or path.name == "v2_build.py"


def test_lifecycle_flags_remain_candidate_and_unauthorized():
    registry = load_registry(default_paths())
    assert registry["active_version"] == "yi_ml_v1"
    assert registry["production_authorized"] is False
    assert registry["models"]["yi_ml_v1"]["state"] == "ACTIVE"
    assert registry["models"]["yi_ml_v2"]["state"] == "CANDIDATE"
    assert registry["models"]["yi_ml_v2"]["production_authorized"] is False
    assert hash_files(V1, CHAMPION_FILES) == registry["models"]["yi_ml_v1"]["artifact_hashes"]
    blob = pickle.loads((V2 / "model.pkl").read_bytes())
    assert blob["model_name"] == "logistic"
    assert list(blob["feature_names"]) == list(ACTIVE_FEATURE_CONTRACT)
