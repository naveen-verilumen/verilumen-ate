"""Prediction-distribution drift is not treated as failure by itself."""

from __future__ import annotations

import numpy as np

from yield_improvement.monitoring.prediction_drift import prediction_drift
from yield_improvement.monitoring.thresholds import load_monitoring_config


def test_same_predictions_healthy():
    cfg = load_monitoring_config()
    rng = np.random.RandomState(7)
    p = rng.uniform(0.1, 0.4, size=80)
    summary = prediction_drift(p, p.copy(), cfg)
    assert summary.status == "HEALTHY"
    assert "not automatically model failure" in summary.notes.lower()


def test_shifted_predictions_flagged():
    cfg = load_monitoring_config()
    rng = np.random.RandomState(7)
    ref = rng.uniform(0.1, 0.3, size=80)
    cur = rng.uniform(0.6, 0.9, size=80)
    summary = prediction_drift(ref, cur, cfg)
    assert summary.status in {"MONITOR", "REVIEW"}
