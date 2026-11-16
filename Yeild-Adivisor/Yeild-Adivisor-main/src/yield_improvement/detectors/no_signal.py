"""No-signal / insufficient-evidence detector. Must fire when others do not."""

from __future__ import annotations

from yield_improvement.detectors.common import ev
from yield_improvement.detectors.contract import DetectorResult
from yield_improvement.detectors.population import DetectorContext

SYSTEMATIC = (
    "spatial",
    "equipment",
    "temporal",
    "temperature",
    "parametric",
    "near_limit",
    "sequence",
    "contact",
    "lot",
    "wafer",
    "correlation",
)


def detect_no_signal(ctx: DetectorContext, others: dict[str, DetectorResult]) -> DetectorResult:
    signals = [name for name in SYSTEMATIC if others.get(name) and others[name].status == "SIGNAL"]
    insufficient = [
        name for name in SYSTEMATIC if others.get(name) and others[name].status == "INSUFFICIENT_DATA"
    ]
    no_sig = [name for name in SYSTEMATIC if others.get(name) and others[name].status == "NO_SIGNAL"]
    evidence = [
        ev("systematic_signals", signals),
        ev("no_signal_detectors", no_sig),
        ev("insufficient_detectors", insufficient),
        ev("n_eligible", ctx.n_eligible),
    ]
    if ctx.n_eligible < 1:
        return DetectorResult(
            detector="no_signal",
            status="INSUFFICIENT_DATA",
            not_a_root_cause=True,
            hypothesis_family="NONE",
            hypothesis_detail="INSUFFICIENT_EVIDENCE",
            confidence="INSUFFICIENT",
            evidence=evidence,
            data_gaps=["no_eligible_dies"],
            sample_size=ctx.n_eligible,
            method="rule_no_systematic_signal",
            calibration_keys=[],
        )
    if signals:
        return DetectorResult(
            detector="no_signal",
            status="NO_SIGNAL",
            not_a_root_cause=True,
            confidence="LOW",
            evidence=evidence,
            sample_size=ctx.n_eligible,
            method="rule_no_systematic_signal",
            calibration_keys=[],
            counter_evidence=[ev("other_detectors_reported_signal", signals)],
        )
    if len(insufficient) > len(no_sig):
        detail = "INSUFFICIENT_EVIDENCE"
        status = "SIGNAL"
        conf = "INSUFFICIENT"
    else:
        detail = "NO_MEANINGFUL_SIGNAL"
        status = "SIGNAL"
        conf = "LOW"
    return DetectorResult(
        detector="no_signal",
        status=status,
        not_a_root_cause=True,
        hypothesis_family="NONE",
        hypothesis_detail=detail,
        confidence=conf,  # type: ignore[arg-type]
        evidence=evidence,
        sample_size=ctx.n_eligible,
        method="rule_no_systematic_signal",
        calibration_keys=[],
        data_gaps=[f"insufficient:{n}" for n in insufficient],
    )
