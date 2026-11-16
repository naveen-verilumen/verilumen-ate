"""Performance comparison vs reference. Small n is INSUFFICIENT_DATA."""

from __future__ import annotations

import numpy as np

from yield_improvement.monitoring.performance import performance_drift
from yield_improvement.monitoring.thresholds import load_monitoring_config


def test_shuffled_labels_degrade():
    cfg = load_monitoring_config()
    rng = np.random.RandomState(7)
    p = np.linspace(0.05, 0.95, 120)
    y = (p > 0.5).astype(int)
    y_bad = rng.permutation(y)
    ref = {"roc_auc": 0.95, "pr_auc": 0.90, "brier": 0.08, "failure_capture_at_top_10_percent": 0.4, "failure_capture_at_top_20_percent": 0.6, "f1": 0.8, "precision": 0.8, "recall": 0.8}
    summary, _ = performance_drift(y_bad, p, ref, cfg, labeled=True)
    assert summary.status in {"DEGRADED", "REVIEW", "MONITOR"}


def test_unlabeled_performance_unavailable():
    cfg = load_monitoring_config()
    summary, details = performance_drift(None, np.array([0.2] * 50), {}, cfg, labeled=False)
    assert summary.status == "UNAVAILABLE"
    assert details == []
