"""Wafer-level fail-rate differences. Sparse wafers are skipped, not labeled defective."""

from __future__ import annotations

from yield_improvement.detectors.common import group_vs_rest
from yield_improvement.detectors.population import DetectorContext


def detect_wafer(ctx: DetectorContext):
    return group_vs_rest(
        ctx,
        detector="wafer",
        family="PROCESS",
        key_fn=lambda d: f"{d.lot_id}/{d.wafer_id}",
        missing_gap="missing_wafer_id",
        min_group_key="n_min_group_compare",
        min_slice_key="n_min_wafer",
        method="wafer_vs_rest_two_proportion_or_fisher",
    )
