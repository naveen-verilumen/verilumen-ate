"""Read-only checks for the V2 predictive-signal investigation. Does not train."""

from __future__ import annotations

import hashlib
import json

import numpy as np
import pandas as pd
import pytest
from sklearn.metrics import roc_auc_score

from yield_improvement.ml.benchmark import ACTIVE_FEATURE_CONTRACT
from yield_improvement.ml.dataset import PARAM_NAMES, load_ml_dataset
from yield_improvement.ml.features import fit_feature_builder
from yield_improvement.model_lifecycle.hashes import CHAMPION_FILES, hash_files
from yield_improvement.model_lifecycle.registry import default_paths, load_registry
from yield_improvement.synthetic.v2_generator import is_edge
from yield_improvement.utils.paths import repo_root

DATASET = repo_root() / "data" / "synthetic" / "agent_visible" / "yi_synthetic_v2"
V1 = repo_root() / "artifacts" / "ml" / "yi_ml_v1"
V2 = repo_root() / "artifacts" / "ml" / "yi_ml_v2"
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
DATASET_HASHES = {
    "die_attempts.csv": "3aebf4b320ea086d8b4a86fd38a55cc7b362651fbb760dc8b83aff243f5fad4e",
    "parametric_measurements.csv": "ae99fe60313374b94a86fd5b1116f5ba9dead3cc1afa0b58d45a769035edb678",
    "test_results.csv": "843f6c38c20aa5744bd9380c2f341706a124aa33552a3b1020d62341e6ed0e9b",
}
# Registry after yi_ml_v4 was added as CANDIDATE. Earlier model records stay in place.
REGISTRY_HASH = "510218addf1c09fda4fe56d246ad040e68818d337a132fd907774dc8de88e9cd"


def _sha256(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _auc(y, score) -> float:
    raw = float(roc_auc_score(y, score))
    return raw if raw >= 0.5 else 1.0 - raw


@pytest.fixture(scope="module")
def ml_data():
    return load_ml_dataset(DATASET)


def test_dataset_and_registry_bytes_are_unchanged():
    for name, digest in DATASET_HASHES.items():
        assert _sha256(DATASET / name) == digest
    assert _sha256(repo_root() / "artifacts" / "ml" / "registry" / "registry.json") == REGISTRY_HASH


def test_model_artifacts_and_lifecycle_are_unchanged():
    registry = load_registry(default_paths())
    assert registry["active_version"] == "yi_ml_v1"
    assert registry["production_authorized"] is False
    assert registry["models"]["yi_ml_v1"]["state"] == "ACTIVE"
    assert registry["models"]["yi_ml_v2"]["state"] == "CANDIDATE"
    assert registry["models"]["yi_ml_v2"]["production_authorized"] is False
    assert hash_files(V1, CHAMPION_FILES) == registry["models"]["yi_ml_v1"]["artifact_hashes"]
    saved = json.loads((V2 / "hashes.json").read_text(encoding="utf-8"))
    assert hash_files(V2, CHAMPION_FILES) == saved
    features = json.loads((V2 / "feature_list.json").read_text(encoding="utf-8"))
    assert features == list(ACTIVE_FEATURE_CONTRACT)
    assert not (set(features) & BLOCKED)


def test_ml_matrix_has_no_parametric_or_hidden_columns(ml_data):
    assert len(ml_data.frame) == 2500
    assert int(ml_data.y.sum()) == 251
    assert int(ml_data.frame["y"].nunique()) == 10
    names = set(fit_feature_builder(ml_data.frame, ml_data.y).feature_names_)
    assert names == set(ACTIVE_FEATURE_CONTRACT)
    assert not (names & BLOCKED)
    assert not (names & set(PARAM_NAMES))
    hidden = {"scenario_id", "true_cause", "injected_effect", "generator_seed", "ground_truth", "expected_signal"}
    assert not (set(ml_data.frame.columns) & hidden)


def test_l004_failures_follow_time_and_not_the_current_border_feature(ml_data):
    frame = ml_data.frame
    y = ml_data.y.to_numpy()
    lot = frame["lot_id"].eq("L004").to_numpy()
    assert int(y[lot].sum()) == 97
    wafers = (
        pd.DataFrame({"wafer_id": frame.loc[lot, "wafer_id"], "y": y[lot]})
        .groupby("wafer_id")["y"]
        .mean()
    )
    assert float(wafers.loc["W05"]) > float(wafers.loc["W01"]) + 0.2
    stamps = pd.to_datetime(frame.loc[lot, "timestamp"], utc=True).astype(np.int64)
    assert _auc(y[lot], stamps.to_numpy()) > 0.70
    border = np.array([is_edge(int(x), int(yy), 10, 10) for x, yy in zip(frame["x"], frame["y"])])
    assert float(y[lot & border].mean()) - float(y[lot & ~border].mean()) < 0.05


def test_spatial_contract_is_redundant_and_misses_the_border(ml_data):
    frame = ml_data.frame
    y = ml_data.y.to_numpy()
    matrix = fit_feature_builder(frame, ml_data.y).transform(frame)
    assert np.corrcoef(matrix["die_x"].astype(float), matrix["normalized_x"].astype(float))[0, 1] == pytest.approx(1.0)
    assert np.corrcoef(matrix["radial_distance"].astype(float), matrix["edge_distance"].astype(float))[0, 1] == pytest.approx(-1.0)
    border = np.array([is_edge(int(x), int(yy), 10, 10) for x, yy in zip(frame["x"], frame["y"])])
    ml_edge = matrix["spatial_region"].eq("EDGE").to_numpy()
    assert int((border & ml_edge).sum()) / int(border.sum()) < 0.5
    lot2 = frame["lot_id"].eq("L002").to_numpy()
    assert float(y[lot2 & border].mean()) > float(y[lot2 & ~border].mean()) + 0.05


def test_parametric_file_is_not_in_the_matrix_and_vmin_separates_l004(ml_data):
    assert "VMIN" not in fit_feature_builder(ml_data.frame, ml_data.y).feature_names_
    raw = pd.read_csv(DATASET / "parametric_measurements.csv")
    first = ml_data.frame[["attempt_id", "lot_id"]].copy()
    first["y"] = ml_data.y.to_numpy()
    vmin = raw.loc[raw["parameter_name"].eq("VMIN"), ["attempt_id", "measurement"]]
    joined = first.merge(vmin, on="attempt_id", how="inner")
    assert len(joined) == 2500
    lot = joined["lot_id"].eq("L004").to_numpy()
    assert _auc(joined.loc[lot, "y"], joined.loc[lot, "measurement"].astype(float)) > 0.70


def test_ml_package_does_not_read_hidden_truth_or_call_another_agent():
    for path in (repo_root() / "src" / "yield_improvement" / "ml").rglob("*.py"):
        body = path.read_text(encoding="utf-8")
        assert "evaluation/ground_truth" not in body
        assert "sub" + "agent" not in body.lower()
