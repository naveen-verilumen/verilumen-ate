"""Controlled spatial experiment. Does not retrain and does not activate a model."""

from __future__ import annotations

import json

import pandas as pd

from yield_improvement.config.loader import load_config
from yield_improvement.ingestion.loader import load_die_attempts, load_test_results
from yield_improvement.ml.benchmark import ACTIVE_FEATURE_CONTRACT
from yield_improvement.ml.config import load_feature_policy, load_ml_config
from yield_improvement.ml.dataset import PARAM_NAMES, load_ml_dataset
from yield_improvement.ml.features import fit_feature_builder, fit_grid_border_feature_builder
from yield_improvement.ml.pipeline import load_artifact
from yield_improvement.ml.split import make_splits
from yield_improvement.model_lifecycle.hashes import CHAMPION_FILES, hash_files
from yield_improvement.model_lifecycle.registry import default_paths, load_registry
from yield_improvement.utils.paths import repo_root
from yield_improvement.yield_analysis.fpy import calculate_fpy
from yield_improvement.yield_analysis.grid_region import grid_bounds, is_grid_border

DATASET = repo_root() / "data" / "synthetic" / "agent_visible" / "yi_synthetic_v2"
V1 = repo_root() / "artifacts" / "ml" / "yi_ml_v1"
V2 = repo_root() / "artifacts" / "ml" / "yi_ml_v2"
V3 = repo_root() / "artifacts" / "ml" / "yi_ml_v3_spatial"
LEAKAGE = {
    "first_pass_fail",
    "pass_fail",
    "failure_code",
    "primary_failure",
    "primary_failure_code",
    "primary_failure_key",
    "test_id",
    "sequence_index",
    "is_first_fail",
    "retest",
    "is_retest",
    "attempt_id",
    "scenario_id",
    "true_cause",
    "ground_truth",
    "injected_effect",
    "generator_seed",
    "recoverable_fraction",
}


def _frame() -> pd.DataFrame:
    rows = []
    points = [(1, 5), (10, 5), (5, 1), (5, 10), (2, 2), (9, 9), (1, 1), (10, 10)]
    for index, (x, y) in enumerate(points):
        rows.append(
            {
                "x": float(x),
                "y": float(y),
                "timestamp": "2026-11-01T08:00:00Z",
                "tester_id": "T01",
                "probe_card_id": "PC01",
                "prober_id": "PR01",
                "temperature_c": 25.0,
                "voltage_v": 0.8,
                "site": 0,
                "lot_id": "L001" if index < 4 else "L002",
                "wafer_id": "W01",
                "die_id": f"D{index:03d}",
                "attempt_id": f"E{index}",
            }
        )
    return pd.DataFrame(rows)


def test_grid_border_labels_use_existing_bounds():
    frame = _frame()
    y = pd.Series([0, 1, 0, 1, 0, 0, 1, 0], name="first_pass_fail")
    built = fit_grid_border_feature_builder(frame, y).transform(frame)
    bounds = grid_bounds([(float(x), float(ypos)) for x, ypos in zip(frame["x"], frame["y"])])
    expected = [
        "BORDER" if is_grid_border(float(x), float(ypos), bounds) else "INNER"
        for x, ypos in zip(frame["x"], frame["y"])
    ]
    assert list(built["spatial_region"]) == expected
    by_xy = {(int(x), int(ypos)): region for x, ypos, region in zip(frame["x"], frame["y"], built["spatial_region"])}
    assert by_xy[(1, 5)] == "BORDER"
    assert by_xy[(10, 5)] == "BORDER"
    assert by_xy[(5, 1)] == "BORDER"
    assert by_xy[(5, 10)] == "BORDER"
    assert by_xy[(2, 2)] == "INNER"
    assert by_xy[(9, 9)] == "INNER"
    radius = fit_feature_builder(frame, y).transform(frame)
    assert set(radius["spatial_region"]).issubset({"EDGE", "CENTER", "OTHER", "__missing__"})


def test_v3_matrix_uses_border_inner_and_physical_die_key():
    data = load_ml_dataset(DATASET)
    assert len(data.frame) == 2500
    assert int(data.y.sum()) == 251
    assert int((data.y == 0).sum()) == 2249
    keys = data.frame[["lot_id", "wafer_id", "die_id"]]
    assert keys.drop_duplicates().shape[0] == 2500
    assert int(data.frame["die_id"].nunique()) == 100
    same = data.frame[data.frame["die_id"] == "D001"]
    assert same[["lot_id", "wafer_id"]].drop_duplicates().shape[0] == 25
    built = fit_grid_border_feature_builder(data.frame, data.y).transform(data.frame)
    assert list(built.columns) == list(ACTIVE_FEATURE_CONTRACT)
    assert len(built.columns) == 16
    assert set(built["spatial_region"]) == {"BORDER", "INNER"}
    denied = {c.lower() for c in load_feature_policy().denied_columns}
    blocked = {c.lower() for c in PARAM_NAMES} | {name.lower() for name in LEAKAGE}
    assert not any(name.lower() in denied or name.lower() in blocked for name in built.columns)
    joined = data.frame[["x", "y"]].copy()
    joined["region"] = built["spatial_region"].to_numpy()
    border = joined[joined["region"] == "BORDER"]
    inner = joined[joined["region"] == "INNER"]
    assert ((border["x"].isin([1, 10])) | (border["y"].isin([1, 10]))).all()
    assert (~inner["x"].isin([1, 10]) & ~inner["y"].isin([1, 10])).all()


def test_five_lolo_folds_do_not_share_a_lot():
    data = load_ml_dataset(DATASET)
    strategy, splits = make_splits(data.groups.to_numpy(), load_ml_config())
    assert strategy == "leave_one_lot_out"
    assert len(splits) == 5
    groups = data.groups.to_numpy()
    held = []
    for train_idx, test_idx in splits:
        train_lots = set(groups[train_idx])
        test_lots = set(groups[test_idx])
        assert not (train_lots & test_lots)
        assert len(train_idx) == 2000
        assert len(test_idx) == 500
        assert len(test_lots) == 1
        held.append(next(iter(test_lots)))
    assert sorted(held) == ["L001", "L002", "L003", "L004", "L005"]


def test_v3_artifact_is_separate_and_prior_models_are_unchanged():
    assert (V3 / "model.pkl").is_file()
    assert (V3 / "metadata.json").is_file()
    assert (V3 / "feature_list.json").is_file()
    assert (V3 / "metrics.json").is_file()
    meta = json.loads((V3 / "metadata.json").read_text(encoding="utf-8"))
    assert meta["model_id"] == "yi_ml_v3_spatial"
    assert meta["state"] == "CANDIDATE"
    assert meta["automatic_activation"] is False
    assert meta["production_authorized"] is False
    assert meta["model_family"] == "logistic_regression"
    assert meta["spatial_region_values"] == ["BORDER", "INNER"]
    assert json.loads((V3 / "feature_list.json").read_text(encoding="utf-8")) == list(ACTIVE_FEATURE_CONTRACT)
    saved = json.loads((V3 / "hashes.json").read_text(encoding="utf-8"))
    assert hash_files(V3, CHAMPION_FILES) == saved
    registry = load_registry(default_paths())
    assert registry["active_version"] == "yi_ml_v1"
    assert registry["production_authorized"] is False
    assert registry["models"]["yi_ml_v1"]["state"] == "ACTIVE"
    assert registry["models"]["yi_ml_v2"]["state"] == "CANDIDATE"
    assert registry["models"]["yi_ml_v3_spatial"]["state"] == "CANDIDATE"
    assert hash_files(V1, CHAMPION_FILES) == registry["models"]["yi_ml_v1"]["artifact_hashes"]
    assert hash_files(V2, CHAMPION_FILES) == json.loads((V2 / "hashes.json").read_text(encoding="utf-8"))
    bundle = load_artifact(V3, load_ml_config())
    sample = load_ml_dataset(DATASET).frame.head(20)
    region = bundle.builder.transform(sample)["spatial_region"]
    assert set(region).issubset({"BORDER", "INNER"})


def test_fpy_and_pareto_totals_unchanged():
    app = load_config()
    attempts = load_die_attempts(DATASET / "die_attempts.csv", app).attempts
    tests = load_test_results(DATASET / "test_results.csv", app).test_results
    fpy = calculate_fpy(attempts, app, test_results=tests)
    assert fpy.eligible_die_count == 2500
    assert fpy.first_pass_pass_count == 2249
    assert fpy.first_pass_fail_count == 251
    assert fpy.fpy == 0.8996
    assert fpy.fpy_loss == 0.1004
    assert sum(row.n_dies for row in fpy.primary_fail_pareto) == 251
