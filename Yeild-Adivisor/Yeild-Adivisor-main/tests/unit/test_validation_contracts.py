"""Validation contract immutables and forbidden phrases."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from yield_improvement.validation.contract import Traceability, ValidationBundle, ValidationResult
from yield_improvement.utils.paths import repo_root


def _trace(**kwargs) -> Traceability:
    base = dict(
        analysis_id="a",
        hypothesis_id="H-SPATIAL.EDGE",
        opportunity_id="OPP-H-SPATIAL.EDGE",
        detector_ids=["spatial"],
        population_definition="radius>=edge",
        eligible_population=10,
        attribution_mode="PRIMARY_FAILURE",
        calculation_method="unit",
        calibration_version="yi_calibration_v1",
        safety_policy_version="yi_safety_v1",
        fpy_policy_version="yi_fpy_v1",
    )
    base.update(kwargs)
    return Traceability(**base)


def _result(**kwargs) -> ValidationResult:
    base = dict(
        analysis_id="a",
        hypothesis_id="H-SPATIAL.EDGE",
        opportunity_id="OPP-H-SPATIAL.EDGE",
        family="SPATIAL",
        detail="EDGE",
        recommendation="INVESTIGATE",
        recommendation_reason="population established; engineering investigation only",
        observed_loss_rate=0.1,
        data_quality_status="PASS",
        evidence_status="PASS",
        population_status="PASS",
        safety_status="PASS",
        validation_steps=["Verify the edge concentration on independent wafers."],
        safety_eligible_production_count=0,
        safety_eligible_production_rate=0.0,
        production_action="FORBIDDEN",
        production_authorized=False,
        invoked_agents=[],
        not_a_root_cause=True,
        traceability=_trace(),
    )
    base.update(kwargs)
    return ValidationResult(**base)


def test_production_authorized_true_rejected():
    with pytest.raises(ValidationError):
        _result(production_authorized=True)


def test_non_zero_production_rate_rejected():
    with pytest.raises(ValidationError):
        _result(safety_eligible_production_rate=0.1)


def test_non_zero_production_count_rejected():
    with pytest.raises(ValidationError):
        _result(safety_eligible_production_count=3)


def test_forbidden_action_rejected():
    with pytest.raises(ValidationError):
        _result(production_action="SET_LIMIT")


def test_invoked_agents_rejected():
    with pytest.raises(ValidationError):
        _result(invoked_agents=["other_agent"])


def test_set_limit_phrase_rejected():
    with pytest.raises(ValidationError):
        _result(validation_steps=["SET_LIMIT to a new value"])


def test_approved_for_production_phrase_rejected():
    with pytest.raises(ValidationError):
        _result(recommendation_reason="APPROVED_FOR_PRODUCTION")


def test_defaults_are_advisory():
    item = _result()
    assert item.production_action == "FORBIDDEN"
    assert item.production_authorized is False
    assert item.safety_eligible_production_rate == 0.0
    assert item.invoked_agents == []
    assert item.not_a_root_cause is True
    assert item.recommendation in {"INVESTIGATE", "REVIEW", "MONITOR", "NEEDS_MORE_DATA", "REJECTED"}


def test_bundle_immutables():
    bundle = ValidationBundle(
        analysis_id="a",
        observed_loss_rate=0.1,
        eligible_population=10,
        attribution_mode="PRIMARY_FAILURE",
        results=[],
        no_actionable_recommendation=True,
    )
    public = bundle.to_public_dict()
    assert public["production_action"] == "FORBIDDEN"
    assert public["production_authorized"] is False
    assert public["safety_eligible_production_rate"] == 0.0
    assert public["invoked_agents"] == []


def test_traceability_required_fields():
    item = _result()
    t = item.traceability
    assert t.analysis_id
    assert t.opportunity_id
    assert t.population_definition
    assert t.eligible_population == 10
    assert t.attribution_mode == "PRIMARY_FAILURE"
    assert t.safety_policy_version
    assert t.calibration_version


def test_validation_package_isolation():
    src = repo_root() / "src" / "yield_improvement" / "validation"
    hits = []
    for path in src.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for token in ("true_cause", "scenario_id", "RUN_SUMMARY", "yield_improvement.evaluation"):
            if token in text:
                hits.append(f"{path.name}: {token}")
    assert hits == []


def test_high_is_not_a_recommendation_state():
    with pytest.raises(ValidationError):
        _result(recommendation="HIGH")


def test_medium_is_not_a_recommendation_state():
    with pytest.raises(ValidationError):
        _result(recommendation="LOW")
