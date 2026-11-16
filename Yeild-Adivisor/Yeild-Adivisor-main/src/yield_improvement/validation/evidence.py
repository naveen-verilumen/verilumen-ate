"""Evidence and conflict gates. evidence_score is descriptive, not a probability."""

from __future__ import annotations

from yield_improvement.hypotheses.contract import Hypothesis
from yield_improvement.hypotheses.identity import CORRELATED_PARENTS
from yield_improvement.opportunity.contract import Opportunity
from yield_improvement.validation.contract import GateTrace


def independent_detector_count(detectors: list[str]) -> int:
    names = [d for d in detectors if d and d != "no_signal"]
    if len(names) <= 1:
        return len(names)
    independent = 0
    for i, a in enumerate(names):
        nested = False
        for b in names:
            if a == b:
                continue
            if a in CORRELATED_PARENTS.get(b, ()) or b in CORRELATED_PARENTS.get(a, ()):
                nested = True
                break
        if not nested:
            independent += 1
    return max(1, independent) if names else 0


def evaluate_evidence(opportunity: Opportunity, hypothesis: Hypothesis | None) -> GateTrace:
    if hypothesis is None and opportunity.family == "UNION":
        return GateTrace(
            name="EVIDENCE_SUFFICIENCY",
            status="PASS",
            reasons=["union_item_has_no_independent_evidence_claim"],
        )
    if hypothesis is None:
        return GateTrace(
            name="EVIDENCE_SUFFICIENCY",
            status="UNAVAILABLE",
            recommendation="NEEDS_MORE_DATA",
            reasons=["hypothesis_unavailable"],
        )
    reasons: list[str] = [
        "evidence_score_is_descriptive_only_not_probability_of_cause_or_recovery",
    ]
    n_ind = independent_detector_count(list(hypothesis.supporting_detectors))
    if n_ind <= 1:
        reasons.append("single_statistical_view_cannot_be_high_confidence")
    if hypothesis.association_class == "SECONDARY_ASSOCIATION":
        reasons.append("secondary_association_is_not_upgraded_to_primary")
    if hypothesis.association_class == "INSUFFICIENT_EVIDENCE" or hypothesis.evidence_tier == "INSUFFICIENT_EVIDENCE":
        return GateTrace(
            name="EVIDENCE_SUFFICIENCY",
            status="UNAVAILABLE",
            recommendation="NEEDS_MORE_DATA",
            reasons=reasons + ["insufficient_evidence"],
        )
    if opportunity.family == "TEST" and opportunity.detail == "SEQUENCE":
        return GateTrace(
            name="EVIDENCE_SUFFICIENCY",
            status="UNAVAILABLE",
            recommendation="NEEDS_MORE_DATA",
            reasons=reasons + ["later_tests_censored_by_stop_on_fail"],
        )
    if hypothesis.data_gaps and opportunity.status == "INSUFFICIENT_DATA":
        return GateTrace(
            name="EVIDENCE_SUFFICIENCY",
            status="UNAVAILABLE",
            recommendation="NEEDS_MORE_DATA",
            reasons=reasons + list(hypothesis.data_gaps[:6]),
        )
    return GateTrace(name="EVIDENCE_SUFFICIENCY", status="PASS", reasons=reasons)


def evaluate_conflicts(opportunity: Opportunity, hypothesis: Hypothesis | None) -> GateTrace:
    if hypothesis is None:
        return GateTrace(name="CONFLICTING_EVIDENCE", status="PASS", reasons=["no_hypothesis_conflict_record"])
    if hypothesis.association_class == "SECONDARY_ASSOCIATION":
        return GateTrace(
            name="CONFLICTING_EVIDENCE",
            status="WARNING",
            reasons=["nested_or_secondary_association_preserved_not_upgraded"],
        )
    reasons: list[str] = []
    conflict_type: str | None = None
    if hypothesis.conflicting_detectors:
        reasons.append(f"conflicting_detectors={list(hypothesis.conflicting_detectors)}")
        conflict_type = "CONFLICTING_DETECTORS"
    nested = [
        c
        for c in hypothesis.counter_evidence
        if "nested" in str(c).lower() or "grain" in str(c).lower()
    ]
    if nested:
        reasons.append("nested_grain_counter_evidence")
        conflict_type = "NESTED_GRAIN"
    if hypothesis.counter_evidence and not nested:
        reasons.append("counter_evidence_present")
        conflict_type = conflict_type or "COUNTER_EVIDENCE"
    if opportunity.overlap_count > 0 and opportunity.included_in_union and opportunity.family != "UNION":
        reasons.append("overlapping_primary_slices")
        conflict_type = conflict_type or "OVERLAPPING_SLICES"
    if not reasons:
        return GateTrace(name="CONFLICTING_EVIDENCE", status="PASS", reasons=["no_major_conflict_recorded"])
    rec = "NEEDS_MORE_DATA"
    if conflict_type in {"CONFLICTING_DETECTORS", "NESTED_GRAIN", "OVERLAPPING_SLICES"}:
        rec = "REVIEW"
    elif conflict_type == "COUNTER_EVIDENCE" and independent_detector_count(list(hypothesis.supporting_detectors)) <= 1:
        rec = "NEEDS_MORE_DATA"
    return GateTrace(
        name="CONFLICTING_EVIDENCE",
        status="WARNING",
        recommendation=rec,
        reasons=reasons + [f"conflict_type={conflict_type}", "hypothesis_not_deleted"],
    )
