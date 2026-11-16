"""Deterministic health policy and threshold config."""

from __future__ import annotations

import numpy as np

from yield_improvement.monitoring.feature_drift import compare_numeric
from yield_improvement.monitoring.health import decide_health
from yield_improvement.monitoring.contracts import CalibrationResult, DimensionSummary
from yield_improvement.monitoring.thresholds import load_monitoring_config


def _dim(name, status, availability="AVAILABLE"):
    return DimensionSummary(dimension=name, status=status, availability=availability)


def test_thresholds_come_from_yaml():
    cfg = load_monitoring_config()
    assert cfg.status == "TO_BE_CALIBRATED"
    assert cfg.feature_drift.psi_review == 0.25
    assert cfg.min_current_samples == 40


def test_small_sample_insufficient_not_retrain():
    cfg = load_monitoring_config()
    healthy = _dim("feature_drift", "HEALTHY")
    cal = CalibrationResult(status="UNAVAILABLE", availability="UNAVAILABLE")
    state, triggers, recs = decide_health(
        cfg=cfg,
        n_current=10,
        labeled=True,
        feature=healthy,
        prediction=_dim("prediction_drift", "HEALTHY"),
        target=_dim("target_drift", "HEALTHY"),
        calibration=cal,
        performance=_dim("performance", "HEALTHY"),
        data_quality=_dim("data_quality", "HEALTHY"),
        n_feature_review=0,
    )
    assert state == "INSUFFICIENT_DATA"
    assert "CONSIDER_RETRAINING" not in recs
    assert "insufficient_sample" in triggers


def test_performance_degraded_without_equating_drift():
    cfg = load_monitoring_config()
    cal = CalibrationResult(status="HEALTHY", availability="AVAILABLE")
    state, _, _ = decide_health(
        cfg=cfg,
        n_current=200,
        labeled=True,
        feature=_dim("feature_drift", "HEALTHY"),
        prediction=_dim("prediction_drift", "HEALTHY"),
        target=_dim("target_drift", "HEALTHY"),
        calibration=cal,
        performance=_dim("performance", "DEGRADED"),
        data_quality=_dim("data_quality", "HEALTHY"),
        n_feature_review=0,
    )
    assert state == "DEGRADED"


def test_numeric_repeatable():
    cfg = load_monitoring_config()
    rng = np.random.RandomState(7)
    a = rng.normal(size=80)
    b = a + 1.0
    x = compare_numeric("die_x", a, b, cfg)
    y = compare_numeric("die_x", a, b, cfg)
    assert [r.current_value for r in x] == [r.current_value for r in y]
