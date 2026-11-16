"""PSI/KS feature drift and unseen categories."""

from __future__ import annotations

import numpy as np
import pandas as pd

from yield_improvement.monitoring.feature_drift import compare_categorical, compare_numeric, feature_drift_table
from yield_improvement.monitoring.thresholds import load_monitoring_config


def test_identical_numeric_is_healthy():
    cfg = load_monitoring_config()
    rng = np.random.RandomState(7)
    x = rng.normal(size=200)
    rows = compare_numeric("temperature_c", x, x.copy(), cfg)
    assert all(r.status == "HEALTHY" for r in rows)


def test_shifted_numeric_reviews():
    cfg = load_monitoring_config()
    rng = np.random.RandomState(7)
    ref = rng.normal(size=200)
    cur = ref + 5.0
    rows = compare_numeric("temperature_c", ref, cur, cfg)
    assert any(r.status == "REVIEW" for r in rows)


def test_unseen_category_rate():
    cfg = load_monitoring_config()
    ref = pd.Series(["A"] * 50 + ["B"] * 50)
    cur = pd.Series(["C"] * 100)
    rows = compare_categorical("tester_id", ref, cur, cfg)
    unseen = next(r for r in rows if r.metric == "unseen_category_rate")
    assert unseen.current_value == 1.0
    assert unseen.status == "REVIEW"


def test_target_not_in_feature_table():
    cfg = load_monitoring_config()
    frame = pd.DataFrame({"temperature_c": np.linspace(20, 30, 40), "first_pass_fail": [0, 1] * 20})
    details = feature_drift_table(frame, frame.copy(), cfg)
    assert all(d.feature_name != "first_pass_fail" for d in details)
