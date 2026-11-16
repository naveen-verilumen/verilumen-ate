"""Probe-card / contact association. Does not infer probe issues from generic fails."""

from __future__ import annotations

from yield_improvement.detectors.common import group_vs_rest
from yield_improvement.detectors.population import DetectorContext


def detect_contact(ctx: DetectorContext):
    return group_vs_rest(
        ctx,
        detector="contact",
        family="CONTACT",
        key_fn=lambda d: d.probe_card_id,
        missing_gap="missing_probe_card_id",
        min_group_key="n_min_group_compare",
        min_slice_key="n_min_equipment_slice",
        method="probe_card_vs_rest_two_proportion_or_fisher",
    )
