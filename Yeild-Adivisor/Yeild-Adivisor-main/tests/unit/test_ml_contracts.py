"""ML contracts: probabilities, immutables, forbidden verbs."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from yield_improvement.ml.contracts import MLEvidence, MLPrediction, MLResult
from yield_improvement.ml.evaluation import compute_metrics
import numpy as np


def test_probability_range_rejected():
    with pytest.raises(ValidationError):
        MLPrediction(
            die_id="d",
            lot_id="L",
            wafer_id="W",
            predicted_probability=1.2,
            raw_probability=0.2,
            predicted_class=1,
            model_version="v",
            feature_set_version="f",
            calibration_version="c",
        )


def test_ml_result_rejects_limit_verb():
    with pytest.raises(ValidationError):
        MLResult(
            analysis_id="a",
            model_name="logistic",
            model_version="v",
            feature_set_version="f",
            calibration_version="c",
            split_strategy="leave_one_lot_out",
            seed=1,
            n_features=1,
            n_train=10,
            n_validation=0,
            n_test=2,
            metrics=compute_metrics(np.array([0, 1]), np.array([0.2, 0.8])),
            calibration={"method": "isotonic", "fitted": False, "note": "increase limit now"},  # type: ignore[arg-type]
            not_a_root_cause=True,
        )


def test_evidence_not_a_root_cause():
    item = MLEvidence(
        hypothesis_id="H-SPATIAL.EDGE",
        family="SPATIAL",
        detail="EDGE",
        predictive_strength=0.4,
        coverage=0.9,
        model_version="v",
        limitations=["predictive only"],
    )
    assert item.not_a_root_cause is True
    assert item.independence is False
    assert item.evidence_role == "SECONDARY_SUPPORT"


def test_production_immutables_on_result():
    result = MLResult(
        analysis_id="a",
        model_name="logistic",
        model_version="v",
        feature_set_version="f",
        calibration_version="c",
        split_strategy="leave_one_lot_out",
        seed=1,
        n_features=2,
        n_train=10,
        n_validation=0,
        n_test=2,
        metrics=compute_metrics(np.array([0, 1, 0, 1]), np.array([0.1, 0.9, 0.2, 0.8])),
        calibration={"method": "isotonic", "fitted": False, "note": "not fitted"},  # type: ignore[arg-type]
    )
    assert result.production_authorized is False
    assert result.production_action == "FORBIDDEN"
    assert result.safety_eligible_production_rate == 0.0
    assert result.invoked_agents == []
