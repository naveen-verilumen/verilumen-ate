"""Target/base-rate drift vs unlabeled UNAVAILABLE."""

from __future__ import annotations

from yield_improvement.monitoring.target_drift import target_drift
from yield_improvement.monitoring.thresholds import load_monitoring_config


def test_unlabeled_target_unavailable():
    cfg = load_monitoring_config()
    summary = target_drift(0.2, None, 0, cfg, labeled=False)
    assert summary.status == "UNAVAILABLE"
    assert summary.availability == "UNAVAILABLE"


def test_rate_shift_review():
    cfg = load_monitoring_config()
    summary = target_drift(0.20, 0.45, 200, cfg, labeled=True)
    assert summary.status in {"MONITOR", "REVIEW"}


def test_small_labeled_sample_insufficient():
    cfg = load_monitoring_config()
    summary = target_drift(0.20, 0.21, 10, cfg, labeled=True)
    assert summary.status == "INSUFFICIENT_DATA"
