"""Population arithmetic and attribution checks. Invalid numbers are not clamped."""

from __future__ import annotations

from yield_improvement.opportunity.contract import Opportunity
from yield_improvement.validation.contract import GateTrace


def evaluate_population(opportunity: Opportunity) -> GateTrace:
    reasons: list[str] = []
    n = opportunity.eligible_population
    affected = opportunity.affected_population_count
    observed = opportunity.observed_loss_count
    upper = opportunity.upper_bound_count
    plausible = opportunity.plausible_count

    if n < 1:
        return GateTrace(
            name="POPULATION_VALIDITY",
            status="FAIL",
            recommendation="NEEDS_MORE_DATA",
            reasons=["missing_eligible_denominator"],
        )
    if not opportunity.population_definition:
        return GateTrace(
            name="POPULATION_VALIDITY",
            status="FAIL",
            recommendation="NEEDS_MORE_DATA",
            reasons=["missing_population_definition"],
        )
    if not opportunity.attribution_mode:
        return GateTrace(
            name="POPULATION_VALIDITY",
            status="FAIL",
            recommendation="REJECTED",
            reasons=["missing_attribution_mode"],
        )
    if opportunity.attribution_mode not in {"PRIMARY_FAILURE", "ANY_FAIL"}:
        return GateTrace(
            name="POPULATION_VALIDITY",
            status="FAIL",
            recommendation="REJECTED",
            reasons=["unknown_attribution_mode"],
        )
    if affected > n:
        reasons.append("affected_count_exceeds_eligible_denominator")
    if observed > affected:
        reasons.append("observed_loss_count_exceeds_affected_count")
    if upper is not None and upper > affected:
        reasons.append("upper_bound_count_exceeds_affected_count")
    if plausible is not None and upper is not None and plausible > upper:
        reasons.append("plausible_count_exceeds_upper_bound_count")
    if reasons:
        return GateTrace(
            name="POPULATION_VALIDITY",
            status="FAIL",
            recommendation="REJECTED",
            reasons=reasons,
        )
    unresolved = (
        "unresolved" in opportunity.population_definition
        or opportunity.status == "INSUFFICIENT_DATA"
        or "could not be established" in opportunity.statement.lower()
    )
    if unresolved and opportunity.family != "UNION":
        return GateTrace(
            name="POPULATION_VALIDITY",
            status="UNAVAILABLE",
            recommendation="NEEDS_MORE_DATA",
            reasons=["population_cannot_be_established"],
        )
    return GateTrace(
        name="POPULATION_VALIDITY",
        status="PASS",
        reasons=[
            f"attribution={opportunity.attribution_mode}",
            f"affected={affected}<=eligible={n}",
            f"observed={observed}<=affected",
        ],
    )
