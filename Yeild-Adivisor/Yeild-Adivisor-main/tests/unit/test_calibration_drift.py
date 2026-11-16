"""Calibration bins and ranking-vs-calibration distinction."""

from __future__ import annotations

import numpy as np

from yield_improvement.monitoring.calibration_drift import calibration_drift
from yield_improvement.monitoring.thresholds import load_monitoring_config


def test_unlabeled_calibration_unavailable():
    cfg = load_monitoring_config()
    result = calibration_drift(None, np.array([0.2, 0.3]), None, cfg, labeled=False)
    assert result.status == "UNAVAILABLE"


def test_well_calibrated_healthy():
    cfg = load_monitoring_config()
    rng = np.random.RandomState(7)
    p = rng.uniform(0.05, 0.95, size=200)
    y = (rng.uniform(size=200) < p).astype(int)
    result = calibration_drift(y, p, 0.20, cfg, labeled=True)
    assert result.availability == "AVAILABLE"
    assert result.status in {"HEALTHY", "MONITOR"}
    assert "ranking may still be useful" in result.notes.lower()


def test_shifted_labels_calibration_warning():
    cfg = load_monitoring_config()
    rng = np.random.RandomState(7)
    p = rng.uniform(0.05, 0.25, size=200)
    y = np.concatenate([np.ones(160, dtype=int), np.zeros(40, dtype=int)])
    rng.shuffle(y)
    result = calibration_drift(y, p, 0.05, cfg, labeled=True)
    assert result.status in {"MONITOR", "REVIEW"}
    assert result.availability == "AVAILABLE"
