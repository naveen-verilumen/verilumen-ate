"""Yield Improvement V2 ML contract. Does not retrain and does not touch yi_ml_v1."""

from __future__ import annotations

import json

import pandas as pd
import pytest

from yield_improvement.config.loader import load_config
from yield_improvement.ingestion.loader import load_die_attempts
from yield_improvement.ml.benchmark import ACTIVE_FEATURE_CONTRACT
from yield_improvement.ml.config import load_feature_policy, load_ml_config
from yield_improvement.ml.dataset import PARAM_NAMES, load_ml_dataset
from yield_improvement.ml.pipeline import load_artifact
from yield_improvement.ml.predict import predict_frame
from yield_improvement.ml.split import make_splits
from yield_improvement.model_lifecycle.hashes import CHAMPION_FILES, hash_files
from yield_improvement.model_lifecycle.registry import default_paths, load_registry
from yield_improvement.utils.paths import repo_root
from yield_improvement.yield_analysis.fpy import calculate_fpy

DATASET = repo_root() / "data" / "synthetic" / "agent_visible" / "yi_synthetic_v2"
V2 = repo_root() / "artifacts" / "ml" / "yi_ml_v2"
V1 = repo_root() / "artifacts" / "ml" / "yi_ml_v1"
BLOCKED = (
    "VMIN",
    "VMAX",
    "IDDQ",
    "VDD",
    "SUPPLY_CURRENT",
    "CONTACT_RESISTANCE",
    "INTERCONNECT_RESISTANCE",
    "ON_RESISTANCE",
)


@pytest.fixture(scope="module")
def ml_data():
    return load_ml_dataset(DATASET)


def test_exactly_2500_ml_rows(ml_data):
    assert len(ml_data.frame) == 2500
    assert len(ml_data.y) == 2500


def test_label_counts(ml_data):
    assert int(ml_data.y.sum()) == 251
    assert int((ml_data.y == 0).sum()) == 2249
    assert ml_data.y.name == "first_pass_fail"


def test_physical_die_uniqueness(ml_data):
    keys = ml_data.frame[["lot_id", "wafer_id", "die_id"]]
    assert keys.drop_duplicates().shape[0] == 2500
    assert int(ml_data.frame["die_id"].nunique()) < 2500


def test_no_duplicate_ml_rows(ml_data):
    assert not ml_data.frame["attempt_id"].duplicated().any()
    assert not ml_data.frame.duplicated(subset=["lot_id", "wafer_id", "die_id"]).any()


def test_sixteen_features_and_no_parametric_or_leakage_columns():
    names = json.loads((V2 / "feature_list.json").read_text(encoding="utf-8"))
    assert names == list(ACTIVE_FEATURE_CONTRACT)
    assert len(names) == 16
    denied = {c.lower() for c in load_feature_policy().denied_columns}
    blocked = {c.lower() for c in list(BLOCKED) + list(PARAM_NAMES)}
    assert not any(name.lower() in denied or name.lower() in blocked for name in names)


def test_five_lolo_folds_with_no_lot_overlap(ml_data):
    strategy, splits = make_splits(ml_data.groups.to_numpy(), load_ml_config())
    assert strategy == "leave_one_lot_out"
    assert len(splits) == 5
    groups = ml_data.groups.to_numpy()
    held = []
    for train_idx, test_idx in splits:
        train_lots = set(groups[train_idx])
        test_lots = set(groups[test_idx])
        assert train_lots.isdisjoint(test_lots)
        assert len(train_idx) == 2000
        assert len(test_idx) == 500
        assert len(test_lots) == 1
        held.append(next(iter(test_lots)))
    assert sorted(held) == ["L001", "L002", "L003", "L004", "L005"]
    assert len(set(held)) == 5


def test_retest_pass_does_not_change_first_pass_target(ml_data):
    app = load_config()
    attempts = load_die_attempts(DATASET / "die_attempts.csv", app).attempts
    fpy = calculate_fpy(attempts, app, test_results=None)
    recovered = [
        d
        for d in fpy.per_die
        if d.first_pass_disposition == "FAIL" and d.final_disposition == "PASS"
    ]
    assert recovered
    frame = ml_data.frame
    y = ml_data.y.to_numpy()
    for outcome in recovered:
        mask = (
            (frame["lot_id"].astype(str) == outcome.lot_id)
            & (frame["wafer_id"].astype(str) == outcome.wafer_id)
            & (frame["die_id"].astype(str) == outcome.die_id)
        ).to_numpy()
        assert int(mask.sum()) == 1
        assert int(y[mask][0]) == 1
        assert str(frame.loc[mask, "attempt_id"].iloc[0]) == outcome.attempt_id


def test_yi_ml_v1_unchanged_and_still_active():
    registry = load_registry(default_paths())
    assert registry["active_version"] == "yi_ml_v1"
    assert registry["models"]["yi_ml_v1"]["state"] == "ACTIVE"
    assert hash_files(V1, CHAMPION_FILES) == registry["models"]["yi_ml_v1"]["artifact_hashes"]
    text = (V1 / "metadata.json").read_text(encoding="utf-8")
    assert "yi_synthetic_v2" not in text


def test_v2_artifact_and_candidate_registry():
    assert (V2 / "model.pkl").is_file()
    meta = json.loads((V2 / "metadata.json").read_text(encoding="utf-8"))
    assert meta["model_id"] == "yi_ml_v2"
    assert meta["dataset_id"] == "yi_synthetic_v2"
    assert meta["sample_count"] == 2500
    assert meta["positive_count"] == 251
    assert meta["negative_count"] == 2249
    assert meta["feature_count"] == 16
    assert meta["parametric_join"] is False
    assert meta["source_model"] is None
    assert meta["n_folds"] == 5
    assert meta["state"] == "CANDIDATE"
    assert meta["automatic_activation"] is False
    registry = load_registry(default_paths())
    assert registry["models"]["yi_ml_v2"]["state"] == "CANDIDATE"
    assert registry["active_version"] != "yi_ml_v2"


def test_loaded_model_predicts_probability_without_root_cause(ml_data):
    bundle = load_artifact(V2, load_ml_config())
    rows = predict_frame(
        bundle,
        ml_data.frame.head(5),
        model_version="yi_ml_v2",
        feature_set_version="yi_ml_features_v1",
        calibration_version="yi_ml_cal_v1",
    )
    assert len(rows) == 5
    for row in rows:
        payload = row.model_dump()
        assert "predicted_probability" in payload
        assert payload["predicted_class"] in {0, 1}
        assert 0.0 <= payload["predicted_probability"] <= 1.0
        assert "root_cause" not in payload
        assert not any(str(value).startswith("Root cause") for value in payload.values())
    assert bundle.feature_names == list(ACTIVE_FEATURE_CONTRACT)
    assert not any(name in BLOCKED or name in PARAM_NAMES for name in bundle.feature_names)


def test_manifest_has_no_hidden_ground_truth():
    manifest = json.loads((V2 / "training_manifest.json").read_text(encoding="utf-8"))
    blob = json.dumps(manifest).lower()
    assert manifest["hidden_ground_truth_stored"] is False
    for token in ("true_cause", "scenario_id", "injected_effect", "expected_signal"):
        assert token not in blob
    frame = pd.read_csv(DATASET / "die_attempts.csv", nrows=0)
    assert "scenario_id" not in frame.columns
