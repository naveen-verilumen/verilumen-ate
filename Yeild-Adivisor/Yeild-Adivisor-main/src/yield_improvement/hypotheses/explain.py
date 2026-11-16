"""Deterministic explanation templates. No LLM."""

from __future__ import annotations

from yield_improvement.hypotheses.contract import Hypothesis


def _fmt(value: float | None, digits: int = 4) -> str:
    if value is None:
        return "unavailable"
    return f"{value:.{digits}g}"


def _pct_points(value: float | None) -> str:
    if value is None:
        return "unavailable"
    return f"{100.0 * value:+.2f} percentage points"


def render_explanation(hyp: Hypothesis) -> str:
    lines = [
        f"Hypothesis: {hyp.statement}",
        f"Identity: {hyp.family}.{hyp.detail}",
        f"Status: {hyp.status}",
        "This is not a root cause. not_a_root_cause=true.",
        f"Association class: {hyp.association_class}",
        f"Evidence tier: {hyp.evidence_tier} (PRELIMINARY evidence_score={hyp.evidence_score}; not a causal probability).",
        f"Confidence level: {hyp.confidence_level}",
        "",
        "Evidence:",
    ]
    if not hyp.statistical_evidence:
        lines.append("- None recorded.")
    for item in hyp.statistical_evidence:
        lines.append(
            f"- Detector {item.detector} ({item.role}): method={item.method}; "
            f"n={item.sample_size}; effect={_fmt(item.effect_size)} ({item.effect_size_metric}); "
            f"p={_fmt(item.p_value)}; adjusted_p={_fmt(item.adjusted_p_value)}."
        )
        if item.effect_size_metric == "fail_rate_difference":
            lines.append(f"  Fail-rate difference: {_pct_points(item.effect_size)}.")
    if hyp.affected_population:
        lines.append(f"- Affected population: {hyp.affected_population}")
    lines.append("")
    lines.append("Counter-evidence:")
    if not hyp.counter_evidence:
        lines.append("- None observed.")
    else:
        for item in hyp.counter_evidence:
            lines.append(f"- {item}")
    lines.append("")
    lines.append("Data gaps:")
    if not hyp.data_gaps:
        lines.append("- None recorded on this hypothesis.")
    else:
        for gap in hyp.data_gaps:
            lines.append(f"- {gap}")
    lines.append("")
    lines.append("Validation required:")
    for step in hyp.validation_required:
        lines.append(f"- {step}")
    lines.append("")
    lines.append("Limitations:")
    for note in hyp.limitations:
        lines.append(f"- {note}")
    return "\n".join(lines)
