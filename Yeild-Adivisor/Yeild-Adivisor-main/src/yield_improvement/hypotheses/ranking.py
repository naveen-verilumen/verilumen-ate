"""Transparent PRELIMINARY evidence_score. Not a causal probability."""

from __future__ import annotations

from yield_improvement.config.loader import AppConfig
from yield_improvement.detectors.common import cal
from yield_improvement.hypotheses.contract import AssociationClass, EvidenceTier


def evidence_score(
    *,
    config: AppConfig,
    p_value: float | None,
    adjusted_p_value: float | None,
    effect_size: float | None,
    effect_size_metric: str | None,
    sample_size: int | None,
    n_gaps: int,
    n_counter: int,
    association_class: AssociationClass,
    independent_support: bool,
) -> float:
    """Weighted evidence strength in [0, 1]. Explicitly not P(root cause)."""
    q = cal(config, "fdr_q")
    alpha = cal(config, "significance_level_alpha")
    n_ref = cal(config, "hypothesis_n_ref")
    rate_ref = cal(config, "hypothesis_effect_ref_rate_diff")

    if adjusted_p_value is not None and adjusted_p_value <= q:
        sig = 1.0
    elif p_value is not None and p_value <= alpha:
        sig = 0.55
    elif p_value is None and effect_size is not None:
        sig = 0.40  # non-p path (e.g. near-limit mass)
    else:
        sig = 0.0

    mag = abs(effect_size) if effect_size is not None else 0.0
    metric = effect_size_metric or "fail_rate_difference"
    if metric == "fail_rate_difference":
        eff = min(1.0, mag / max(rate_ref, 1e-9))
    elif metric == "ks_d":
        eff = min(1.0, mag / 0.40)
    elif metric == "jaccard":
        eff = min(1.0, mag / 0.30)
    elif metric == "mann_kendall_tau":
        eff = min(1.0, mag / 0.80)
    elif metric == "near_limit_mass":
        eff = min(1.0, mag / 0.40)
    else:
        eff = min(1.0, mag)

    sample = 0.0 if not sample_size else min(1.0, sample_size / max(n_ref, 1.0))
    coverage = max(0.0, 1.0 - 0.15 * min(4, n_gaps))
    independence = 1.0 if independent_support else 0.0
    counter = min(1.0, 0.25 * n_counter)

    raw = (
        0.30 * sig
        + 0.30 * eff
        + 0.15 * sample
        + 0.15 * coverage
        + 0.10 * independence
        - 0.15 * counter
    )
    raw = max(0.0, min(1.0, raw))
    if association_class == "SECONDARY_ASSOCIATION":
        raw *= 0.65
    elif association_class == "WEAK_ASSOCIATION":
        raw *= 0.45
    elif association_class == "INSUFFICIENT_EVIDENCE":
        raw *= 0.25
    return round(raw, 4)


def evidence_tier(score: float, config: AppConfig, *, independent_support: bool) -> EvidenceTier:
    strong = cal(config, "hypothesis_score_strong")
    moderate = cal(config, "hypothesis_score_moderate")
    weak = cal(config, "hypothesis_score_weak")
    if score >= strong and independent_support:
        return "STRONG_EVIDENCE"
    if score >= moderate or (score >= strong and not independent_support):
        # One detector is one view. Do not treat correlated or singleton
        # packets as STRONG_EVIDENCE.
        return "MODERATE_EVIDENCE"
    if score >= weak:
        return "WEAK_EVIDENCE"
    return "INSUFFICIENT_EVIDENCE"


def confidence_level(tier: EvidenceTier, independent_support: bool) -> str:
    if tier == "INSUFFICIENT_EVIDENCE":
        return "INSUFFICIENT"
    if tier == "WEAK_EVIDENCE":
        return "LOW"
    if tier == "STRONG_EVIDENCE" and independent_support:
        return "MEDIUM"  # HIGH still UNCONFIRMED; V1 does not claim HIGH
    if tier in {"MODERATE_EVIDENCE", "STRONG_EVIDENCE"}:
        return "MEDIUM"
    return "LOW"
