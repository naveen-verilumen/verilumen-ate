"""Shared detector construction helpers."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Callable

from yield_improvement.config.loader import AppConfig
from yield_improvement.detectors.contract import (
    DetectorHypothesis,
    DetectorResult,
    EvidenceItem,
)
from yield_improvement.detectors.population import DetectorContext, DieView
from yield_improvement.detectors.stats import candidate, compare_proportions


def cal(config: AppConfig, key: str) -> float:
    return float(candidate(config.calibration.parameters, key))


def raw_p(p: float | None) -> float:
    """0.0 is a valid p-value; do not treat it as missing."""
    return 1.0 if p is None else p


def ev(name: str, value: Any, note: str | None = None) -> EvidenceItem:
    return EvidenceItem(name=name, value=value, note=note)


def insufficient(
    detector: str,
    method: str,
    *,
    reason: str,
    sample_size: int | None,
    calibration_keys: list[str],
    extra_gaps: list[str] | None = None,
) -> DetectorResult:
    gaps = [reason, *(extra_gaps or [])]
    return DetectorResult(
        detector=detector,
        status="INSUFFICIENT_DATA",
        not_a_root_cause=True,
        confidence="INSUFFICIENT",
        data_gaps=gaps,
        sample_size=sample_size,
        method=method,
        calibration_keys=calibration_keys,
        evidence=[ev("insufficient_reason", reason)],
    )


def no_signal_result(
    detector: str,
    method: str,
    *,
    sample_size: int,
    calibration_keys: list[str],
    evidence: list[EvidenceItem] | None = None,
    counter_evidence: list[EvidenceItem] | None = None,
    data_gaps: list[str] | None = None,
    hypotheses: list[DetectorHypothesis] | None = None,
    p_value: float | None = None,
    effect_size: float | None = None,
    effect_size_metric: str | None = None,
) -> DetectorResult:
    return DetectorResult(
        detector=detector,
        status="NO_SIGNAL",
        not_a_root_cause=True,
        confidence="LOW",
        evidence=evidence or [],
        counter_evidence=counter_evidence or [],
        data_gaps=data_gaps or [],
        sample_size=sample_size,
        method=method,
        calibration_keys=calibration_keys,
        hypotheses=hypotheses or [],
        p_value=p_value,
        effect_size=effect_size,
        effect_size_metric=effect_size_metric,
    )


def signal_result(
    detector: str,
    method: str,
    *,
    family: str,
    detail: str,
    sample_size: int,
    calibration_keys: list[str],
    p_value: float | None,
    effect_size: float | None,
    effect_size_metric: str,
    affected: dict[str, Any] | None,
    baseline: dict[str, Any] | None,
    evidence: list[EvidenceItem],
    counter_evidence: list[EvidenceItem] | None = None,
    data_gaps: list[str] | None = None,
    hypotheses: list[DetectorHypothesis] | None = None,
    confidence: str = "LOW",
) -> DetectorResult:
    return DetectorResult(
        detector=detector,
        status="SIGNAL",
        not_a_root_cause=True,
        hypothesis_family=family,
        hypothesis_detail=detail,
        affected_population=affected,
        baseline_population=baseline,
        effect_size=effect_size,
        effect_size_metric=effect_size_metric,
        p_value=p_value,
        confidence=confidence,  # type: ignore[arg-type]
        evidence=evidence,
        counter_evidence=counter_evidence or [],
        data_gaps=data_gaps or [],
        sample_size=sample_size,
        method=method,
        calibration_keys=calibration_keys,
        hypotheses=hypotheses or [],
    )


def group_vs_rest(
    ctx: DetectorContext,
    *,
    detector: str,
    family: str,
    key_fn: Callable[[DieView], str | None],
    missing_gap: str,
    min_group_key: str,
    min_slice_key: str | None,
    method: str,
    extra_keys: list[str] | None = None,
    hypothesis_detail: str | None = None,
) -> DetectorResult:
    """Compare each group's fail rate to the complement. Association only."""
    keys = [
        "n_min_group_compare",
        "min_effect_size_fpy_delta",
        "significance_level_alpha",
        "fdr_q",
        min_group_key,
    ]
    if min_slice_key:
        keys.append(min_slice_key)
    if extra_keys:
        keys.extend(extra_keys)
    dies = ctx.dies
    labeled = [(d, key_fn(d)) for d in dies]
    present = [d for d, k in labeled if k is not None]
    if not present:
        return insufficient(
            detector, method, reason=missing_gap, sample_size=ctx.n_eligible, calibration_keys=keys
        )
    min_group = int(cal(ctx.config, min_group_key))
    min_slice = int(cal(ctx.config, min_slice_key)) if min_slice_key else min_group
    min_effect = cal(ctx.config, "min_effect_size_fpy_delta")
    groups: dict[str, list[DieView]] = defaultdict(list)
    for die, key in labeled:
        if key is None:
            continue
        groups[key].append(die)
    usable = {k: v for k, v in groups.items() if len(v) >= min_group}
    if len(present) < min_slice or len(usable) < 2:
        return insufficient(
            detector,
            method,
            reason="group_sample_below_calibration_minimum",
            sample_size=len(present),
            calibration_keys=keys,
            extra_gaps=[f"usable_groups={len(usable)} min_group={min_group} min_slice={min_slice}"],
        )
    hypotheses: list[DetectorHypothesis] = []
    best: DetectorHypothesis | None = None
    evidence: list[EvidenceItem] = []
    skipped = [k for k, v in groups.items() if len(v) < min_group]
    if skipped:
        evidence.append(ev("skipped_sparse_groups", skipped, "below n_min_group_compare"))
    for name, members in sorted(usable.items(), key=lambda kv: kv[0]):
        rest = [d for d in present if key_fn(d) != name]
        if len(rest) < min_group:
            continue
        f1 = sum(1 for d in members if d.failed)
        f2 = sum(1 for d in rest if d.failed)
        cmp_ = compare_proportions(f1, len(members), f2, len(rest))
        hyp = DetectorHypothesis(
            detector=detector,
            label=str(name),
            family=family,
            detail=hypothesis_detail or str(name),
            p_value=cmp_.p_value,
            effect_size=cmp_.rate_diff,
            effect_size_metric="fail_rate_difference",
            sample_size=len(members) + len(rest),
            n_affected=len(members),
            n_baseline=len(rest),
            rate_affected=cmp_.rate1,
            rate_baseline=cmp_.rate2,
        )
        hypotheses.append(hyp)
        evidence.append(
            ev(
                f"group_{name}",
                {
                    "n": len(members),
                    "fail_rate": round(cmp_.rate1, 6),
                    "rest_fail_rate": round(cmp_.rate2, 6),
                    "rate_diff": round(cmp_.rate_diff, 6),
                    "risk_ratio": cmp_.risk_ratio,
                    "p_value": cmp_.p_value,
                    "test": cmp_.method,
                },
            )
        )
        if best is None or raw_p(hyp.p_value) < raw_p(best.p_value):
            best = hyp
    if not hypotheses:
        return insufficient(
            detector, method, reason="no_comparable_groups", sample_size=len(present), calibration_keys=keys
        )
    # Preliminary status uses raw p; runner applies BH and may demote.
    alpha = cal(ctx.config, "significance_level_alpha")
    winner = max(hypotheses, key=lambda h: abs(h.effect_size or 0.0))
    # Prefer the largest |effect| among those with p<=alpha; else smallest p.
    passing = [h for h in hypotheses if raw_p(h.p_value) <= alpha and abs(h.effect_size or 0) >= min_effect]
    if passing:
        winner = max(passing, key=lambda h: abs(h.effect_size or 0.0))
        return signal_result(
            detector,
            method,
            family=family,
            detail=hypothesis_detail or str(winner.detail),
            sample_size=len(present),
            calibration_keys=keys,
            p_value=winner.p_value,
            effect_size=winner.effect_size,
            effect_size_metric="fail_rate_difference",
            affected={
                "group": winner.label,
                "n": winner.n_affected,
                "fail_rate": winner.rate_affected,
            },
            baseline={"n": winner.n_baseline, "fail_rate": winner.rate_baseline},
            evidence=evidence,
            counter_evidence=[
                ev("association_is_not_causation", True, "group rate difference only"),
            ],
            hypotheses=hypotheses,
            confidence="LOW",
        )
    return no_signal_result(
        detector,
        method,
        sample_size=len(present),
        calibration_keys=keys,
        evidence=evidence,
        hypotheses=hypotheses,
        p_value=winner.p_value if winner else (best.p_value if best else None),
        effect_size=winner.effect_size if winner else None,
        effect_size_metric="fail_rate_difference",
        counter_evidence=[ev("no_group_met_p_and_effect_size", True)],
    )
