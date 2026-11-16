"""Monitoring contracts: safety immutables and forbidden verbs."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from yield_improvement.monitoring.contracts import (
    CalibrationResult,
    DimensionSummary,
    ModelHealthReport,
)


def _report(**kwargs) -> ModelHealthReport:
    empty = DimensionSummary(dimension="x", status="HEALTHY", availability="AVAILABLE")
    cal = CalibrationResult(status="HEALTHY", availability="AVAILABLE")
    payload = dict(
        analysis_id="a",
        model_version="yi_ml_v1",
        feature_version="yi_ml_features_v1",
        calibration_version="yi_ml_cal_v1",
        reference_version="yi_ml_ref_v1",
        reference_dataset_id="ref",
        current_dataset_id="cur",
        label_mode="LABELED",
        n_lots=1,
        n_wafers=1,
        n_dies=10,
        feature_drift=empty.model_copy(update={"dimension": "feature_drift"}),
        prediction_drift=empty.model_copy(update={"dimension": "prediction_drift"}),
        target_drift=empty.model_copy(update={"dimension": "target_drift"}),
        calibration=cal,
        performance=empty.model_copy(update={"dimension": "performance"}),
        data_quality=empty.model_copy(update={"dimension": "data_quality"}),
        overall_status="HEALTHY",
    )
    payload.update(kwargs)
    return ModelHealthReport(**payload)


def test_production_immutables():
    report = _report()
    assert report.production_authorized is False
    assert report.production_action == "FORBIDDEN"
    assert report.safety_eligible_production_count == 0
    assert report.safety_eligible_production_rate == 0.0
    assert report.retrained is False
    assert report.model_replaced is False


def test_forbidden_recommendation_rejected():
    with pytest.raises(ValidationError):
        _report(recommendations=["DEPLOY_NEW_MODEL_AUTOMATICALLY"])


def test_limit_verb_rejected():
    with pytest.raises(ValidationError):
        _report(limitations=["please increase limit now"])


def test_versions_required_on_report():
    report = _report()
    assert report.model_version
    assert report.feature_version
    assert report.calibration_version
    assert report.reference_version
