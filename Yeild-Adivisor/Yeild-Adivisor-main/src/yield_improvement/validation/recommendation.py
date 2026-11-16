"""Deterministic advisory recommendations. Opportunity size does not rank actions."""

from __future__ import annotations

from yield_improvement.hypotheses.contract import Hypothesis
from yield_improvement.opportunity.contract import Opportunity
from yield_improvement.validation.contract import GateTrace, Recommendation

STEPS: dict[tuple[str, str], list[str]] = {
    ("SPATIAL", "EDGE"): [
        "Verify the edge concentration on independent wafers.",
        "Verify the pattern across additional lots.",
        "Inspect die-coordinate concentration; do not infer missing X/Y.",
        "Check whether the association persists after lot stratification.",
    ],
    ("SPATIAL", "CENTER"): [
        "Verify the center concentration on independent wafers.",
        "Verify the pattern across additional lots.",
        "Inspect die-coordinate concentration; do not infer missing X/Y.",
        "Check whether the association persists after lot stratification.",
    ],
    ("SPATIAL", "RING"): [
        "Verify the ring pattern on independent wafers.",
        "Verify across additional lots.",
        "Inspect radial concentration; do not infer missing X/Y.",
        "Check whether the association persists after lot stratification.",
    ],
    ("EQUIPMENT", "DEGRADATION"): [
        "Compare multiple lots on the associated equipment versus controls.",
        "Verify equipment identity completeness.",
        "Check whether the association persists after lot and product stratification.",
        "This remains an association, not a confirmed cause.",
    ],
    ("PROCESS", "DRIFT"): [
        "Collect additional chronological lots.",
        "Verify timestamp and lot-order completeness.",
        "Check whether the trend persists on new material.",
        "Separate nested lot/wafer associations from a time trend.",
    ],
    ("ENVIRONMENT", "TEMPERATURE"): [
        "Verify temperature coverage on the eligible population.",
        "Repeat the comparison across independent lots.",
        "Test whether the association persists after product and lot stratification.",
    ],
    ("PARAMETRIC", "SHIFT"): [
        "Verify measurement coverage for the shifted parameter.",
        "Verify limit metadata exists; do not invent limits.",
        "Inspect the distribution shift on an independent sample.",
        "Check whether the fail association remains after stratification.",
    ],
    ("TEST", "LIMIT_SENSITIVITY"): [
        "Verify production limit metadata is present.",
        "Inspect the measurement distribution around the existing limit.",
        "Assess measurement and test-system repeatability.",
        "Engineering investigation only; the existing limit is not modified.",
    ],
    ("TEST", "SEQUENCE"): [
        "Later-test observations are censored by stop-on-fail behavior.",
        "Do not infer missing later-test outcomes or CSV row order.",
        "If sequence is in scope, confirm under controlled execution.",
    ],
    ("CONTACT", "PROBE"): [
        "Verify probe/card identity completeness.",
        "Compare independent lots on the associated contact hardware.",
        "Inspect spatial/contact-location consistency where coordinates exist.",
    ],
    ("PROCESS", "LOT_VARIATION"): [
        "Repeat the comparison on independent lots.",
        "Verify whether the lot association is stable or nested in drift/spatial structure.",
        "Lot identity is not automatically a root cause.",
    ],
    ("PROCESS", "WAFER_VARIATION"): [
        "Repeat the comparison on independent wafers.",
        "Verify whether the wafer association is nested in lot or spatial structure.",
        "Wafer identity is not automatically a root cause.",
    ],
    ("CORRELATED", "FAILURES"): [
        "Treat co-occurrence as a statistical association, not causation.",
        "Confirm pairing under continue-on-fail or a designed experiment.",
        "Stop-on-fail censors later tests and biases pairs.",
    ],
    ("UNION", "PRIMARY_EVIDENCE"): [
        "Review overlapping primary slices separately.",
        "Use the union of failed dies; do not add individual upper bounds.",
        "Do not collapse overlapping slices into a combined root cause.",
    ],
}


def steps_for(family: str | None, detail: str | None) -> list[str]:
    if family is None or detail is None:
        return ["Confirm the associated population on independent material. Production action remains forbidden."]
    return list(
        STEPS.get(
            (family, detail),
            [
                f"Confirm the {family}.{detail} association on independent material.",
                "Do not treat this as a confirmed cause or a production action.",
            ],
        )
    )


def decide_recommendation(
    traces: list[GateTrace],
    opportunity: Opportunity,
    hypothesis: Hypothesis | None,
) -> tuple[Recommendation, str, list[GateTrace]]:
    """First failed/unavailable gate with a recommendation wins. Opportunity size is ignored."""
    for trace in traces:
        if trace.status in {"FAIL", "UNAVAILABLE"} and trace.recommendation:
            return trace.recommendation, "; ".join(trace.reasons) or trace.name, traces
    # Conflicting-evidence WARNING may request REVIEW / NEEDS_MORE_DATA without blocking earlier PASS gates.
    for trace in traces:
        if trace.name == "CONFLICTING_EVIDENCE" and trace.status == "WARNING" and trace.recommendation:
            if trace.recommendation in {"REVIEW", "NEEDS_MORE_DATA", "REJECTED"}:
                if opportunity.family == "UNION":
                    return (
                        "REVIEW",
                        "Union of overlapping primary slices; not a combined root cause.",
                        traces,
                    )
                return trace.recommendation, "; ".join(trace.reasons), traces
    if opportunity.family == "UNION":
        return "REVIEW", "Union of overlapping primary slices; not a combined root cause and not double-counted.", traces
    if hypothesis and hypothesis.association_class == "SECONDARY_ASSOCIATION":
        return (
            "MONITOR",
            "Secondary association is not upgraded to primary evidence and is not a root cause.",
            traces,
        )
    if hypothesis and hypothesis.association_class == "WEAK_ASSOCIATION":
        return "MONITOR", "Weak association; observe on additional material. Not a confirmed cause.", traces
    if hypothesis and hypothesis.association_class == "PRIMARY_EVIDENCE":
        return (
            "INVESTIGATE",
            "Population is established and evidence is preliminary but meaningful; engineering investigation only.",
            traces,
        )
    return "NEEDS_MORE_DATA", "Fail-closed default. Opportunity size does not set the recommendation.", traces
