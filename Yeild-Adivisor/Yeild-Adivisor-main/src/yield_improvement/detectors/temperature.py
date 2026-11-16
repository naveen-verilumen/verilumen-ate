"""Temperature vs failure rate. Reports mix so confounding is visible."""

from __future__ import annotations

from collections import defaultdict

from yield_improvement.detectors.common import ev, group_vs_rest
from yield_improvement.detectors.contract import DetectorResult
from yield_improvement.detectors.population import DetectorContext


def detect_temperature(ctx: DetectorContext) -> DetectorResult:
    result = group_vs_rest(
        ctx,
        detector="temperature",
        family="ENVIRONMENT",
        key_fn=lambda d: None if d.temperature_c is None else f"{d.temperature_c:g}",
        missing_gap="missing_temperature_c",
        min_group_key="n_min_group_compare",
        min_slice_key=None,
        method="temperature_group_vs_rest_two_proportion_or_fisher",
        hypothesis_detail="TEMPERATURE",
    )
    if result.status == "INSUFFICIENT_DATA":
        return result
    lots_by_temp: dict[str, set[str]] = defaultdict(set)
    testers_by_temp: dict[str, set[str]] = defaultdict(set)
    for die in ctx.dies:
        if die.temperature_c is None:
            continue
        key = f"{die.temperature_c:g}"
        lots_by_temp[key].add(die.lot_id)
        if die.tester_id:
            testers_by_temp[key].add(die.tester_id)
    extra = [
        ev("lots_per_temperature", {k: sorted(v) for k, v in lots_by_temp.items()}),
        ev("testers_per_temperature", {k: sorted(v) for k, v in testers_by_temp.items()}),
        ev(
            "confounding_note",
            True,
            "Temperature association may still be mixed with lot/equipment; not a root cause.",
        ),
    ]
    evidence = list(result.evidence) + extra
    detail = "TEMPERATURE" if result.status == "SIGNAL" else result.hypothesis_detail
    return result.model_copy(
        update={
            "evidence": evidence,
            "hypothesis_detail": detail if result.status == "SIGNAL" else result.hypothesis_detail,
            "hypothesis_family": "ENVIRONMENT" if result.status == "SIGNAL" else result.hypothesis_family,
        }
    )
