"""Copy Phase 5 opportunity and overlap fields. Does not re-estimate opportunity."""

from __future__ import annotations

from yield_improvement.opportunity.contract import Opportunity, OpportunityBundle
from yield_improvement.reporting.contract import OVERLAP_NOTICE, ReportOpportunity, ReportOverlap
from yield_improvement.validation.contract import ValidationBundle


def _plausible_label(item: Opportunity) -> str:
    if item.plausible_unavailable or item.plausible_rate is None:
        return "Not estimable"
    return item.calibration_status


def build_opportunities(bundle: OpportunityBundle) -> list[ReportOpportunity]:
    rows: list[ReportOpportunity] = []
    for item in bundle.opportunities:
        rows.append(
            ReportOpportunity(
                opportunity_id=item.opportunity_id,
                hypothesis_id=item.hypothesis_id,
                family=item.family,
                detail=item.detail,
                attribution_mode=item.attribution_mode,
                status=item.status,
                observed_loss_count=item.observed_loss_count,
                observed_loss_rate=item.observed_loss_rate,
                upper_bound_count=item.upper_bound_count,
                upper_bound_rate=item.upper_bound_rate,
                plausible_count=item.plausible_count,
                plausible_rate=item.plausible_rate,
                plausible_unavailable=item.plausible_unavailable,
                plausible_label=_plausible_label(item),
                calibration_status=item.calibration_status,
                affected_population_count=item.affected_population_count,
                population_definition=item.population_definition,
                included_in_union=item.included_in_union,
                overlap_count=item.overlap_count,
                exclusive_count=item.exclusive_count,
                union_count=item.union_count,
                intersection_count=item.intersection_count,
                statement=item.statement,
                safety_eligible_production_rate=0.0,
            )
        )
    return rows


def build_overlap(opportunities: OpportunityBundle, validation: ValidationBundle) -> ReportOverlap:
    summary = opportunities.summary
    copied = dict(validation.overlap_summary)
    individuals = [
        {
            "opportunity_id": item.opportunity_id,
            "hypothesis_id": item.hypothesis_id,
            "family": item.family,
            "detail": item.detail,
            "affected_population_count": item.affected_population_count,
            "observed_loss_rate": item.observed_loss_rate,
            "upper_bound_rate": item.upper_bound_rate,
            "overlap_count": item.overlap_count,
            "exclusive_count": item.exclusive_count,
            "union_count": item.union_count,
            "intersection_count": item.intersection_count,
            "included_in_union": item.included_in_union,
        }
        for item in opportunities.opportunities
        if item.family != "UNION"
    ]
    note = copied.get("note") or OVERLAP_NOTICE
    return ReportOverlap(
        sum_of_individual_upper_bounds_rate=summary.sum_of_individual_upper_bounds_rate,
        union_upper_bound_rate=summary.union_upper_bound_rate,
        union_upper_bound_count=summary.union_upper_bound_count,
        intersection_fail_count=summary.intersection_fail_count,
        sum_exceeds_observed=summary.sum_of_individual_upper_bounds_exceeds_observed,
        note=str(note),
        individuals=individuals,
    )
