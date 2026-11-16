"""Evidence rules: score is not probability; secondary not upgraded; single view not HIGH."""

from __future__ import annotations

from yield_improvement.hypotheses.contract import Hypothesis
from yield_improvement.opportunity.contract import Opportunity
from yield_improvement.validation.evidence import evaluate_conflicts, evaluate_evidence, independent_detector_count


def _hyp(**kwargs) -> Hypothesis:
    base = dict(
        hypothesis_id="H-SPATIAL.EDGE",
        family="SPATIAL",
        detail="EDGE",
        statement="Yield loss is associated with wafer-edge location.",
        association_class="PRIMARY_EVIDENCE",
        evidence_tier="MODERATE_EVIDENCE",
        evidence_score=0.7,
        confidence_level="MEDIUM",
        rank=1,
        supporting_detectors=["spatial"],
    )
    base.update(kwargs)
    return Hypothesis(**base)


def _opp(**kwargs) -> Opportunity:
    base = dict(
        opportunity_id="OPP-H-SPATIAL.EDGE",
        hypothesis_id="H-SPATIAL.EDGE",
        family="SPATIAL",
        detail="EDGE",
        association_class="PRIMARY_EVIDENCE",
        attribution_mode="PRIMARY_FAILURE",
        status="PRELIMINARY",
        status_flags=["NOT_ELIGIBLE_FOR_PRODUCTION"],
        observed_loss_count=2,
        observed_loss_rate=0.2,
        upper_bound_count=2,
        upper_bound_rate=0.2,
        plausible_count=1,
        plausible_rate=0.1,
        plausible_unavailable=False,
        eligible_population=10,
        affected_population_count=4,
        population_definition="radius>=edge",
        calculation_method="unit",
        statement="Observed loss associated with SPATIAL.EDGE is 20.0 percentage points; this represents an upper bound, not a predicted improvement.",
    )
    base.update(kwargs)
    return Opportunity(**base)


def test_single_detector_is_one_view():
    assert independent_detector_count(["spatial"]) == 1
    assert independent_detector_count(["temporal", "lot"]) == 1


def test_evidence_score_not_treated_as_probability():
    gate = evaluate_evidence(_opp(), _hyp())
    assert any("descriptive_only" in r for r in gate.reasons)
    assert any("high_confidence" in r for r in gate.reasons)
    assert gate.status == "PASS"


def test_secondary_not_upgraded():
    hyp = _hyp(association_class="SECONDARY_ASSOCIATION", hypothesis_id="H-PROCESS.LOT_VARIATION", family="PROCESS", detail="LOT_VARIATION")
    gate = evaluate_evidence(_opp(family="PROCESS", detail="LOT_VARIATION", association_class="SECONDARY_ASSOCIATION"), hyp)
    assert any("not_upgraded" in r for r in gate.reasons)
    conflict = evaluate_conflicts(_opp(association_class="SECONDARY_ASSOCIATION"), hyp)
    assert conflict.recommendation is None


def test_sequence_censored_needs_more_data():
    hyp = _hyp(
        hypothesis_id="H-TEST.SEQUENCE",
        family="TEST",
        detail="SEQUENCE",
        supporting_detectors=["sequence"],
    )
    gate = evaluate_evidence(_opp(family="TEST", detail="SEQUENCE", hypothesis_id="H-TEST.SEQUENCE"), hyp)
    assert gate.status == "UNAVAILABLE"
    assert gate.recommendation == "NEEDS_MORE_DATA"


def test_conflicting_evidence_preserved_not_deleted():
    hyp = _hyp(conflicting_detectors=["lot"], counter_evidence=[{"note": "disappears after lot control"}])
    gate = evaluate_conflicts(_opp(), hyp)
    assert gate.status == "WARNING"
    assert "hypothesis_not_deleted" in gate.reasons
    assert gate.recommendation in {"REVIEW", "NEEDS_MORE_DATA"}


def test_unavailable_evidence_not_fabricated():
    hyp = _hyp(association_class="INSUFFICIENT_EVIDENCE", evidence_tier="INSUFFICIENT_EVIDENCE", confidence_level="INSUFFICIENT")
    gate = evaluate_evidence(_opp(status="INSUFFICIENT_DATA"), hyp)
    assert gate.status == "UNAVAILABLE"
    assert gate.recommendation == "NEEDS_MORE_DATA"
