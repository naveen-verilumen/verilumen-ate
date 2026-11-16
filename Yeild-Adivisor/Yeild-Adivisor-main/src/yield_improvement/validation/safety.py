"""Safety gate. Opportunity cannot override this module. Production remains forbidden."""

from __future__ import annotations

from yield_improvement.config.loader import AppConfig
from yield_improvement.opportunity.contract import Opportunity
from yield_improvement.opportunity.engine import production_safety_rate
from yield_improvement.validation.contract import FORBIDDEN_OUTPUT_PHRASES, GateTrace

_PROMISED_GAIN = (
    "fpy will increase",
    "promised fpy",
    "guaranteed yield",
    "predicted fpy improvement",
    "factory fpy gain",
    "will increase by",
)


def scan_forbidden_text(*parts: str) -> list[str]:
    blob = " ".join(p for p in parts if p).lower()
    hits = [p for p in FORBIDDEN_OUTPUT_PHRASES if p.lower() in blob]
    for phrase in _PROMISED_GAIN:
        if phrase in blob:
            hits.append(phrase)
    return hits


def evaluate_safety(
    opportunity: Opportunity,
    config: AppConfig,
    *,
    proposed_steps: list[str],
    proposed_reason: str,
) -> GateTrace:
    production_safety_rate(config)
    reasons: list[str] = []
    hits = scan_forbidden_text(
        opportunity.statement,
        proposed_reason,
        *proposed_steps,
        *opportunity.limitations,
    )
    if hits:
        reasons.append(f"forbidden_or_promised_gain_wording: {hits}")
    if opportunity.safety_eligible_production_rate != 0.0:
        reasons.append("non_zero_production_eligibility")
    if "APPROVED_FOR_PRODUCTION" in opportunity.status_flags:
        reasons.append("approved_for_production_flag")
    if config.safety.potential_specialist_investigation.invoked:
        reasons.append("specialist_invoked")
    if not config.safety.independent_of_opportunity:
        reasons.append("opportunity_must_not_override_safety")
    if reasons:
        return GateTrace(name="SAFETY", status="FAIL", recommendation="REJECTED", reasons=reasons)
    return GateTrace(
        name="SAFETY",
        status="PASS",
        reasons=["production_action=FORBIDDEN; safety_eligible_production=0; no specialist invocation"],
    )
