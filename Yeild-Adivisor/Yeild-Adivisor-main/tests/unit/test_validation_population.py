"""Population arithmetic is checked, never silently clamped."""

from __future__ import annotations

from yield_improvement.opportunity.contract import Opportunity
from yield_improvement.validation.population import evaluate_population


def _opp(**kwargs) -> Opportunity:
    base = dict(
        opportunity_id="OPP-X",
        hypothesis_id="H-X",
        family="EQUIPMENT",
        detail="DEGRADATION",
        association_class="PRIMARY_EVIDENCE",
        attribution_mode="PRIMARY_FAILURE",
        status="ESTIMATED",
        status_flags=["NOT_ELIGIBLE_FOR_PRODUCTION"],
        observed_loss_count=2,
        observed_loss_rate=0.2,
        upper_bound_count=2,
        upper_bound_rate=0.2,
        plausible_count=1,
        plausible_rate=0.1,
        plausible_unavailable=False,
        eligible_population=10,
        affected_population_count=5,
        population_definition="tester_id=T03",
        calculation_method="unit",
        statement="Yield loss is associated with equipment identity.",
    )
    base.update(kwargs)
    return Opportunity(**base)


def test_valid_population_passes():
    gate = evaluate_population(_opp())
    assert gate.status == "PASS"


def test_affected_exceeds_denominator_rejected():
    gate = evaluate_population(_opp(affected_population_count=12, eligible_population=10, observed_loss_count=2))
    assert gate.status == "FAIL"
    assert gate.recommendation == "REJECTED"
    assert any("affected_count_exceeds" in r for r in gate.reasons)


def test_observed_exceeds_affected_rejected():
    gate = evaluate_population(_opp(observed_loss_count=6, affected_population_count=5, upper_bound_count=6))
    assert gate.status == "FAIL"
    assert any("observed_loss_count_exceeds" in r for r in gate.reasons)


def test_plausible_exceeds_upper_rejected():
    gate = evaluate_population(_opp(plausible_count=5, upper_bound_count=2, observed_loss_count=2))
    assert gate.status == "FAIL"
    assert any("plausible_count_exceeds" in r for r in gate.reasons)


def test_missing_denominator_needs_more_data():
    gate = evaluate_population(_opp(eligible_population=0, affected_population_count=0, observed_loss_count=0, upper_bound_count=0, plausible_count=0))
    assert gate.status == "FAIL"
    assert gate.recommendation == "NEEDS_MORE_DATA"


def test_unknown_attribution_rejected():
    payload = _opp().model_dump()
    payload["attribution_mode"] = "MIXED"
    gate = evaluate_population(Opportunity.model_construct(**payload))
    assert gate.status == "FAIL"
    assert gate.recommendation == "REJECTED"


def test_unresolved_population_needs_more_data():
    gate = evaluate_population(
        _opp(
            status="INSUFFICIENT_DATA",
            population_definition="unresolved:SPATIAL.EDGE",
            statement="Population could not be established; no numerical opportunity invented.",
            observed_loss_count=0,
            upper_bound_count=None,
            upper_bound_rate=None,
            plausible_count=None,
            plausible_rate=None,
            plausible_unavailable=True,
            affected_population_count=0,
        )
    )
    assert gate.status == "UNAVAILABLE"
    assert gate.recommendation == "NEEDS_MORE_DATA"
