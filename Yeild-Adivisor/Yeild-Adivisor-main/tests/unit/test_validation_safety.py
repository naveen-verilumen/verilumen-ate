"""Safety gate: forbidden verbs, production zero, opportunity cannot override."""

from __future__ import annotations

from yield_improvement.opportunity.contract import Opportunity
from yield_improvement.validation.safety import evaluate_safety, scan_forbidden_text


def _opp(**kwargs) -> Opportunity:
    base = dict(
        opportunity_id="OPP-H-EQUIPMENT.DEGRADATION",
        hypothesis_id="H-EQUIPMENT.DEGRADATION",
        family="EQUIPMENT",
        detail="DEGRADATION",
        association_class="PRIMARY_EVIDENCE",
        attribution_mode="PRIMARY_FAILURE",
        status="ESTIMATED",
        status_flags=["NOT_ELIGIBLE_FOR_PRODUCTION"],
        observed_loss_count=4,
        observed_loss_rate=0.4,
        upper_bound_count=4,
        upper_bound_rate=0.4,
        plausible_count=None,
        plausible_rate=None,
        plausible_unavailable=True,
        eligible_population=10,
        affected_population_count=6,
        population_definition="tester_id=T03",
        calculation_method="unit",
        statement="Yield loss is associated with equipment identity (T03).",
    )
    base.update(kwargs)
    return Opportunity(**base)


def test_scan_detects_set_limit():
    assert scan_forbidden_text("please SET_LIMIT now")


def test_scan_detects_increase_limit():
    assert any("increase limit" in h.lower() or h.lower() == "increase limit" for h in scan_forbidden_text("increase limit by 10"))


def test_safety_pass_on_associative_wording(config):
    gate = evaluate_safety(_opp(), config, proposed_steps=["Compare lots on associated equipment."], proposed_reason="INVESTIGATE")
    assert gate.status == "PASS"
    assert gate.recommendation is None


def test_safety_rejects_promised_gain(config):
    gate = evaluate_safety(
        _opp(),
        config,
        proposed_steps=["none"],
        proposed_reason="FPY will increase by 3%",
    )
    assert gate.status == "FAIL"
    assert gate.recommendation == "REJECTED"


def test_safety_rejects_change_limit_step(config):
    gate = evaluate_safety(
        _opp(family="TEST", detail="LIMIT_SENSITIVITY"),
        config,
        proposed_steps=["change limit to a new candidate"],
        proposed_reason="REVIEW",
    )
    assert gate.status == "FAIL"
    assert gate.recommendation == "REJECTED"


def test_opportunity_cannot_override_failed_data_quality():
    from yield_improvement.validation.contract import GateTrace
    from yield_improvement.validation.recommendation import decide_recommendation

    traces = [
        GateTrace(name="SAFETY", status="PASS", reasons=["ok"]),
        GateTrace(
            name="DATA_QUALITY",
            status="UNAVAILABLE",
            recommendation="NEEDS_MORE_DATA",
            reasons=["missing_x_y"],
        ),
        GateTrace(name="OPPORTUNITY", status="PASS", reasons=["ignored"]),
    ]
    rec, reason, _ = decide_recommendation(traces, _opp(observed_loss_rate=0.9, upper_bound_rate=0.9), None)
    assert rec == "NEEDS_MORE_DATA"
    assert "missing_x_y" in reason


def test_config_independent_of_opportunity(config):
    assert config.safety.independent_of_opportunity is True
    assert config.safety.principle_order[0] == "SAFETY"
    assert "OPPORTUNITY" == config.safety.principle_order[-1]
    assert config.safety.potential_specialist_investigation.invoked is False
    assert config.safety.engineering_recommendation_states == [
        "INVESTIGATE",
        "REVIEW",
        "MONITOR",
        "NEEDS_MORE_DATA",
        "REJECTED",
    ]
    assert config.safety.phase6_validation["opportunity_cannot_override_earlier_gates"] is True
    assert config.safety.phase6_validation["no_limit_modification"] is True
    assert config.safety.phase6_validation["invoked_specialists"] is False
