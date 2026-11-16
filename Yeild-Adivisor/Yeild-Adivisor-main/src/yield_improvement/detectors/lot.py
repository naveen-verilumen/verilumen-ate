"""Lot-level fail-rate differences. Lowest-yield lot is not automatically defective."""

from __future__ import annotations

from yield_improvement.detectors.common import group_vs_rest
from yield_improvement.detectors.population import DetectorContext


def detect_lot(ctx: DetectorContext):
    return group_vs_rest(
        ctx,
        detector="lot",
        family="PROCESS",
        key_fn=lambda d: d.lot_id,
        missing_gap="missing_lot_id",
        min_group_key="n_min_lot",
        min_slice_key=None,
        method="lot_vs_rest_two_proportion_or_fisher",
    )
