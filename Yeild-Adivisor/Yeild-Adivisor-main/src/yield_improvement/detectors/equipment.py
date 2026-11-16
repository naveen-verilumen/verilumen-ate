"""Equipment/tester association. Association is not causation."""

from __future__ import annotations

from yield_improvement.detectors.common import group_vs_rest
from yield_improvement.detectors.population import DetectorContext


def detect_equipment(ctx: DetectorContext):
    return group_vs_rest(
        ctx,
        detector="equipment",
        family="EQUIPMENT",
        key_fn=lambda d: d.tester_id,
        missing_gap="missing_tester_id",
        min_group_key="n_min_group_compare",
        min_slice_key="n_min_equipment_slice",
        method="group_vs_rest_two_proportion_or_fisher",
        extra_keys=[],
    )
