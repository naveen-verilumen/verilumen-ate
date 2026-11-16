"""Deterministic, evidence-backed ranking policy for engineering recommendations.

Transparent, reproducible, policy-driven scoring.
Never allows opportunity size or unverified claims to override safety or evidence gates.
"""

from __future__ import annotations

from typing import Any

from yield_improvement.recommendations.contracts import (
    ConfidenceTier,
    EngineeringRecommendation,
    PriorityTier,
)

RANKING_POLICY_NAME = "Evidence-First Engineering Priority Policy"
RANKING_POLICY_VERSION = "yi_rec_rank_v1"


def compute_recommendation_score(
    rec: EngineeringRecommendation,
    association_class: str,
    evidence_tier: str,
    data_gaps: list[str],
) -> tuple[float, str, ConfidenceTier]:
    """Compute transparent deterministic ranking score, human rationale, and confidence tier.

    Components:
    1. Association Class Base Weight (max 0.50)
    2. Evidence Quality & Multi-Detector Independence (max 0.25)
    3. Actionability & Systematic Loss Relevance (max 0.20)
    4. Opportunity Context (max 0.05) - strictly bounded so opportunity cannot override evidence.
    """
    # Safety Gate Check
    if rec.production_action != "FORBIDDEN" or rec.production_authorized or rec.safety_eligible_production_rate != 0.0:
        return 0.0, "Safety violation: non-forbidden production action", "INSUFFICIENT"

    if evidence_tier == "INSUFFICIENT_EVIDENCE" or association_class == "INSUFFICIENT_EVIDENCE":
        rationale = "Downgraded due to insufficient data coverage or unverified denominator."
        return 0.15, rationale, "INSUFFICIENT"

    # 1. Association class base (0.15 - 0.50)
    assoc_upper = association_class.upper()
    if "PRIMARY" in assoc_upper:
        base_weight = 0.50
        class_desc = "Primary evidence association"
    elif "SECONDARY" in assoc_upper:
        base_weight = 0.30
        class_desc = "Secondary exploratory association"
    elif "WEAK" in assoc_upper:
        base_weight = 0.20
        class_desc = "Weak statistical association"
    else:
        base_weight = 0.25
        class_desc = "General statistical association"

    # 2. Evidence quality and detector independence (0.0 - 0.25)
    detectors = rec.supporting_detectors
    n_detectors = len(detectors)
    # Detectors that reflect genuinely distinct analytical domains
    distinct_families = set()
    for d in detectors:
        if d in {"lot", "wafer", "temporal"}:
            distinct_families.add("process")
        elif d in {"spatial", "wafer_map"}:
            distinct_families.add("spatial")
        elif d in {"parametric", "near_limit"}:
            distinct_families.add("electrical")
        elif d in {"equipment", "tester", "probe_card"}:
            distinct_families.add("hardware")
        else:
            distinct_families.add(d)

    if len(distinct_families) >= 2:
        independence_score = 0.12
        indep_desc = "Multi-domain detector confirmation"
    elif n_detectors >= 2:
        independence_score = 0.08
        indep_desc = "Multi-detector confirmation"
    else:
        independence_score = 0.04
        indep_desc = "Single-detector observation"

    # Data gap penalty
    if not data_gaps or len(data_gaps) == 0:
        gap_score = 0.08
    elif len(data_gaps) <= 2:
        gap_score = 0.04
    else:
        gap_score = 0.01

    # Population coverage
    coverage_ratio = min(1.0, rec.affected_die_count / max(1, rec.eligible_die_count))
    pop_score = round(coverage_ratio * 0.05, 4)

    evidence_component = round(independence_score + gap_score + pop_score, 4)

    # 3. Actionability & Excess Loss Relevance (0.0 - 0.20)
    excess_rate = max(0.0, rec.observed_failure_rate - rec.baseline_failure_rate)
    excess_score = min(0.12, round(excess_rate * 0.6, 4))

    action_concrete_score = 0.08 if len(rec.recommended_action) > 30 else 0.04
    action_component = round(excess_score + action_concrete_score, 4)

    # 4. Opportunity Context (0.0 - 0.05) - strictly bounded
    plausible = rec.plausible_rate or 0.0
    opp_component = min(0.05, round(plausible * 0.5, 4))

    raw_score = base_weight + evidence_component + action_component + opp_component
    final_score = min(0.9999, max(0.01, round(raw_score, 4)))

    # Determine confidence tier
    if "PRIMARY" in assoc_upper and final_score >= 0.70 and len(data_gaps) <= 1:
        confidence: ConfidenceTier = "HIGH"
    elif final_score >= 0.45:
        confidence = "MODERATE"
    elif final_score >= 0.25:
        confidence = "LOW"
    else:
        confidence = "INSUFFICIENT"

    rationale = (
        f"{class_desc} (base={base_weight:.2f}) with {indep_desc} (+{independence_score:.2f}), "
        f"data quality completeness (+{gap_score:.2f}), systematic excess fail rate of "
        f"{excess_rate * 100:.1f}% (+{excess_score:.2f}), and actionability (+{action_concrete_score:.2f})."
    )

    return final_score, rationale, confidence


def rank_recommendations(
    recommendations: list[EngineeringRecommendation],
) -> list[EngineeringRecommendation]:
    """Rank recommendations deterministically and assign priority ranks and tiers.

    Tie-breaking:
    1. Score descending
    2. Hypothesis ID ascending (stable)
    3. Recommendation ID ascending (stable)
    """
    if not recommendations:
        return []

    # Sort deterministically
    sorted_recs = sorted(
        recommendations,
        key=lambda r: (
            -r.ranking_score,
            r.hypothesis_id or "",
            r.recommendation_id,
        ),
    )

    ranked: list[EngineeringRecommendation] = []
    total = len(sorted_recs)

    for idx, rec in enumerate(sorted_recs, start=1):
        # Priority tier assignment based on rank and score
        if idx <= 2 and rec.ranking_score >= 0.60:
            priority: PriorityTier = "HIGH"
        elif idx <= 4 or rec.ranking_score >= 0.40:
            priority = "MEDIUM"
        else:
            priority = "LOW"

        # Construct updated model preserving immutability
        updated = rec.model_copy(
            update={
                "priority_rank": idx,
                "priority_tier": priority,
            }
        )
        ranked.append(updated)

    return ranked
