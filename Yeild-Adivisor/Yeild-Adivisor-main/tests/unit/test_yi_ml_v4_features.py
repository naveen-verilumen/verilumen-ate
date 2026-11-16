"""V4 feature experiment. Does not retrain and does not activate a model."""

from __future__ import annotations

import json

import pandas as pd

from yield_improvement.hypotheses.contract import HypothesisBundle
from yield_improvement.ml.benchmark import ACTIVE_FEATURE_CONTRACT
from yield_improvement.ml.config import load_ml_config
from yield_improvement.ml.dataset import load_ml_dataset
from yield_improvement.ml.evidence import attach_ml_evidence
from yield_improvement.ml.experiment_features import fit_experiment_builder, lot_relative_position
from yield_improvement.ml.features import fit_feature_builder
from yield_improvement.ml.reliability import NEEDS_MORE_DATA, ml_support_status
from yield_improvement.ml.split import make_splits
from yield_improvement.ml.v4_feature_experiment import PARAMS, audit_parametrics
from yield_improvement.model_lifecycle.hashes import CHAMPION_FILES, hash_files
from yield_improvement.model_lifecycle.registry import default_paths, load_registry
from yield_improvement.utils.paths import repo_root
from yield_improvement.yield_analysis.grid_region import grid_bounds, is_grid_border

DATASET = repo_root() / "data" / "synthetic" / "agent_visible" / "yi_synthetic_v2"
V1 = repo_root() / "artifacts" / "ml" / "yi_ml_v1"
V2 = repo_root() / "artifacts" / "ml" / "yi_ml_v2"
V3 = repo_root() / "artifacts" / "ml" / "yi_ml_v3_spatial"
V4 = repo_root() / "artifacts" / "ml" / "yi_ml_v4"


def _frame() -> pd.DataFrame:
    rows = []
    for index, (lot, x, y_value, stamp) in enumerate(
        [
            ("L001", 1, 5, "2026-11-01T08:00:00Z"),
            ("L001", 10, 5, "2026-11-01T12:00:00Z"),
            ("L001", 5, 1, "2026-11-01T16:00:00Z"),
            ("L001", 2, 2, "2026-11-01T20:00:00Z"),
            ("L002", 9, 9, "2026-11-03T08:00:00Z"),
            ("L002", 5, 10, "2026-11-03T18:00:00Z"),
        ]
    ):
        rows.append(
            {
                "x": float(x),
                "y": float(y_value),
                "timestamp": stamp,
                "tester_id": "T01",
                "probe_card_id": "PC01",
                "prober_id": "PR01",
                "temperature_c": 25.0,
                "voltage_v": 0.8,
                "site": 0,
                "lot_id": lot,
                "wafer_id": "W01",
                "die_id": f"D{index:03d}",
                "attempt_id": f"E{index}",
            }
        )
    return pd.DataFrame(rows)


def test_lot_relative_position_uses_timestamps_only():
    frame = _frame()
    labels = pd.Series([1, 0, 1, 0, 1, 0])
    position = lot_relative_position(frame)
    assert list(position.loc[frame["lot_id"] == "L001"]) == [0.0, 1 / 3, 2 / 3, 1.0]
    assert list(position.loc[frame["lot_id"] == "L002"]) == [0.0, 1.0]
    flipped = frame.copy()
    flipped["timestamp"] = list(reversed(frame["timestamp"]))
    assert not position.equals(lot_relative_position(flipped))
    assert lot_relative_position(frame).equals(lot_relative_position(frame.assign(ignored_label=labels)))


def test_relative_position_does_not_use_another_lot():
    frame = _frame()
    original = lot_relative_position(frame)
    shifted = frame.copy()
    shifted.loc[shifted["lot_id"] == "L002", "timestamp"] = ["2026-12-01T00:00:00Z", "2026-12-02T00:00:00Z"]
    updated = lot_relative_position(shifted)
    assert list(updated.loc[frame["lot_id"] == "L001"]) == list(original.loc[frame["lot_id"] == "L001"])


def test_experiment_border_and_default_contract_stay_separate():
    frame = _frame()
    y = pd.Series([0, 1, 0, 0, 1, 0], name="first_pass_fail")
    built = fit_experiment_builder(frame, y, grid_border=True, relative_time=True).transform(frame)
    bounds = grid_bounds([(float(x), float(y_value)) for x, y_value in zip(frame["x"], frame["y"])])
    expected = [
        "BORDER" if is_grid_border(float(x), float(y_value), bounds) else "INNER"
        for x, y_value in zip(frame["x"], frame["y"])
    ]
    assert list(built["spatial_region"]) == expected
    assert "relative_position_within_lot" in built.columns
    default = fit_feature_builder(frame, y).transform(frame)
    assert list(default.columns) == list(ACTIVE_FEATURE_CONTRACT)
    assert "relative_position_within_lot" not in default.columns
    assert set(default["spatial_region"]).issubset({"EDGE", "CENTER", "OTHER", "__missing__"})


def test_parametric_audit_rejects_in_test_measurements_and_retests():
    rows = audit_parametrics(DATASET)
    assert [row["parameter"] for row in rows] == list(PARAMS)
    assert all(row["decision"] == "REJECTED" and row["accepted_into_matrix"] is False for row in rows)
    assert all(row["first_pass_rows"] == 2500 for row in rows)
    assert all(row["retest_rows_excluded"] == 60 for row in rows)
    by_name = {row["parameter"]: row for row in rows}
    assert by_name["VMIN"]["limit_fail_rows"] == 28
    assert by_name["IDDQ"]["limit_fail_rows"] == 29
    assert by_name["VMAX"]["limit_fail_rows"] == 1


def test_v4_contract_split_and_lifecycle():
    data = load_ml_dataset(DATASET)
    assert len(data.frame) == 2500
    assert int(data.y.sum()) == 251
    assert data.frame[["lot_id", "wafer_id", "die_id"]].drop_duplicates().shape[0] == 2500
    strategy, splits = make_splits(data.groups.to_numpy(), load_ml_config())
    assert strategy == "leave_one_lot_out"
    assert len(splits) == 5
    groups = data.groups.to_numpy()
    for train_idx, test_idx in splits:
        assert len(train_idx) == 2000
        assert len(test_idx) == 500
        assert not (set(groups[train_idx]) & set(groups[test_idx]))
    meta = json.loads((V4 / "metadata.json").read_text(encoding="utf-8"))
    names = json.loads((V4 / "feature_list.json").read_text(encoding="utf-8"))
    assert meta["model_id"] == "yi_ml_v4"
    assert meta["state"] == "CANDIDATE"
    assert meta["parametric_join"] is False
    assert meta["ml_support_status"] == "NEEDS_MORE_DATA"
    assert meta["production_authorized"] is False
    assert meta["promoted"] is False
    assert "relative_position_within_lot" in names
    assert not any(name in names for name in PARAMS)
    leaked = {
        "first_pass_fail",
        "pass_fail",
        "failure_code",
        "scenario_id",
        "true_cause",
        "ground_truth",
        "attempt_id",
    }
    assert not (set(names) & leaked)
    registry = load_registry(default_paths())
    assert registry["active_version"] == "yi_ml_v1"
    assert registry["production_authorized"] is False
    assert registry["models"]["yi_ml_v1"]["state"] == "ACTIVE"
    assert registry["models"]["yi_ml_v2"]["state"] == "CANDIDATE"
    assert registry["models"]["yi_ml_v3_spatial"]["state"] == "CANDIDATE"
    assert registry["models"]["yi_ml_v4"]["state"] == "CANDIDATE"
    assert hash_files(V1, CHAMPION_FILES) == registry["models"]["yi_ml_v1"]["artifact_hashes"]
    assert hash_files(V2, CHAMPION_FILES) == json.loads((V2 / "hashes.json").read_text(encoding="utf-8"))
    assert hash_files(V3, CHAMPION_FILES) == json.loads((V3 / "hashes.json").read_text(encoding="utf-8"))
    assert hash_files(V4, CHAMPION_FILES) == json.loads((V4 / "hashes.json").read_text(encoding="utf-8"))
    pooled = json.loads((V4 / "metrics.json").read_text(encoding="utf-8"))["metrics"]
    assert ml_support_status(pooled, None, 0.1004) == NEEDS_MORE_DATA


def test_needs_more_data_is_not_presented_as_ml_support():
    bundle = HypothesisBundle(
        analysis_id="unit",
        n_eligible=10,
        no_confident_hypothesis=False,
        detector_summary={"spatial": "SIGNAL"},
    )
    updated = attach_ml_evidence(bundle, [], ml_support_status="NEEDS_MORE_DATA")
    assert updated.detector_summary["ml"] == "NEEDS_MORE_DATA"
    assert updated.detector_summary["ml_supported"] == "false"
    assert updated.hypotheses == []
    assert any("not ML-supported" in note for note in updated.limitations)
