"""Feature allow/deny, no fabricated coordinates, FPY target."""

from __future__ import annotations

import pandas as pd
import pytest

from yield_improvement.ml.config import LeakageError, load_feature_policy
from yield_improvement.ml.dataset import MLDataset, assert_no_forbidden_columns, build_dataset
from yield_improvement.ml.features import fit_feature_builder
from yield_improvement.models.canonical import DieAttempt


def _attempt(**kwargs) -> DieAttempt:
    base = dict(
        attempt_id="E1",
        lot_id="L1",
        wafer_id="W1",
        die_id="D1",
        product_id="DEV_A",
        step_id="WS_SORT",
        part_class="PRODUCTION",
        timestamp="2026-03-01T08:00:00Z",
        attempt_number=1,
        is_first_attempt=True,
        is_retest=False,
        pass_fail="PASS",
        disposition="PASS",
        record_status="VALID",
    )
    base.update(kwargs)
    return DieAttempt(**base)


def test_target_is_first_pass_fail(config):
    attempts = [
        _attempt(attempt_id="E1", die_id="D1", pass_fail="PASS", disposition="PASS"),
        _attempt(attempt_id="E2", die_id="D2", pass_fail="FAIL", disposition="FAIL", sbin=8),
    ]
    data = build_dataset(attempts, config, analysis_id="t")
    assert list(data.y) == [0, 1]
    assert "pass_fail" not in data.frame.columns
    assert "failure_code" not in data.frame.columns


def test_missing_xy_not_fabricated(config):
    attempts = [
        _attempt(attempt_id="E1", die_id="D1", x=None, y=None, pass_fail="FAIL", disposition="FAIL", sbin=8),
        _attempt(attempt_id="E2", die_id="D2", lot_id="L2", x=None, y=None),
    ]
    data = build_dataset(attempts, config)
    builder = fit_feature_builder(data.frame, data.y)
    x = builder.transform(data.frame)
    if "die_x" in x.columns:
        assert x["die_x"].isna().all()


def test_forbidden_feature_fails_closed():
    policy = load_feature_policy()
    with pytest.raises(LeakageError):
        assert_no_forbidden_columns(["die_x", "scenario_id"], policy)


def test_categorical_not_integer_codes():
    frame = pd.DataFrame(
        {
            "x": [0.0, 1.0, 0.0, 1.0],
            "y": [0.0, 0.0, 1.0, 1.0],
            "timestamp": ["2026-03-01T08:00:00Z"] * 4,
            "tester_id": ["T01", "T02", "T01", "T02"],
            "probe_card_id": ["PC-1"] * 4,
            "prober_id": ["PRB-1"] * 4,
            "temperature_c": [25, 25, 85, 85],
            "voltage_v": [0.8] * 4,
            "site": [0, 1, 0, 1],
            "lot_id": ["L1", "L1", "L2", "L2"],
            "wafer_id": ["W"] * 4,
            "die_id": ["D1", "D2", "D3", "D4"],
            "attempt_id": ["E1", "E2", "E3", "E4"],
        }
    )
    y = pd.Series([0, 1, 0, 1])
    x = fit_feature_builder(frame, y).transform(frame)
    assert pd.api.types.is_string_dtype(x["tester_id"]) or x["tester_id"].dtype == object
    assert not pd.api.types.is_integer_dtype(x["tester_id"])
    assert set(x["tester_id"]) <= {"T01", "T02"}


def test_lot_id_is_not_a_model_feature():
    frame = pd.DataFrame(
        {
            "x": [0.0, 1.0, 0.0, 1.0],
            "y": [0.0, 0.0, 1.0, 1.0],
            "timestamp": ["2026-03-01T08:00:00Z"] * 4,
            "tester_id": ["T01", "T02", "T01", "T02"],
            "probe_card_id": ["PC-1"] * 4,
            "prober_id": ["PRB-1"] * 4,
            "temperature_c": [25, 25, 85, 85],
            "voltage_v": [0.8] * 4,
            "site": [0, 1, 0, 1],
            "lot_id": ["L1", "L1", "L2", "L2"],
            "wafer_id": ["W"] * 4,
            "die_id": ["D1", "D2", "D3", "D4"],
            "attempt_id": ["E1", "E2", "E3", "E4"],
        }
    )
    y = pd.Series([0, 1, 0, 1])
    x = fit_feature_builder(frame, y).transform(frame)
    assert "lot_id" not in x.columns
    assert "wafer_id" not in x.columns
    assert "die_id" not in x.columns
    assert "scenario_id" not in x.columns


def test_group_fail_rate_fit_on_train_only():
    train = pd.DataFrame(
        {
            "x": [0.0, 1.0],
            "y": [0.0, 1.0],
            "timestamp": ["2026-03-01T08:00:00Z"] * 2,
            "tester_id": ["T_HOT", "T_HOT"],
            "probe_card_id": ["PC-1"] * 2,
            "prober_id": ["PRB-1"] * 2,
            "temperature_c": [25, 25],
            "voltage_v": [0.8, 0.8],
            "site": [0, 1],
            "lot_id": ["L1", "L1"],
            "wafer_id": ["W"] * 2,
            "die_id": ["D1", "D2"],
            "attempt_id": ["E1", "E2"],
        }
    )
    y_train = pd.Series([1, 1])
    builder = fit_feature_builder(train, y_train)
    test = train.copy()
    test["tester_id"] = ["T_UNSEEN", "T_UNSEEN"]
    test["lot_id"] = ["L2", "L2"]
    x_test = builder.transform(test)
    # Unseen tester must use training global mean, not the held-out labels.
    assert x_test["tester_fail_rate"].tolist() == [1.0, 1.0]


def test_no_sequence_or_later_test_features():
    frame = pd.DataFrame(
        {
            "x": [0.0, 1.0],
            "y": [0.0, 1.0],
            "timestamp": ["2026-03-01T08:00:00Z"] * 2,
            "tester_id": ["T01", "T01"],
            "probe_card_id": ["PC-1"] * 2,
            "prober_id": ["PRB-1"] * 2,
            "temperature_c": [25, 25],
            "voltage_v": [0.8, 0.8],
            "site": [0, 1],
            "lot_id": ["L1", "L2"],
            "wafer_id": ["W"] * 2,
            "die_id": ["D1", "D2"],
            "attempt_id": ["E1", "E2"],
            "later_test_pass": [1, 0],
            "test_index": [1, 4],
        }
    )
    y = pd.Series([0, 1])
    x = fit_feature_builder(frame, y).transform(frame)
    lowered = {c.lower() for c in x.columns}
    assert "later_test_pass" not in lowered
    assert "test_index" not in lowered
    assert "sequence" not in lowered


def test_positive_rate_is_measured_not_assumed(config):
    attempts = [
        _attempt(attempt_id=f"E{i}", die_id=f"D{i}", lot_id="L1" if i < 3 else "L2")
        for i in range(8)
    ]
    attempts[0] = _attempt(attempt_id="E0", die_id="D0", lot_id="L1", pass_fail="FAIL", disposition="FAIL", sbin=8)
    data = build_dataset(attempts, config, analysis_id="imb")
    rate = float(data.y.mean())
    assert 0.0 < rate < 1.0
    assert rate != 0.5
