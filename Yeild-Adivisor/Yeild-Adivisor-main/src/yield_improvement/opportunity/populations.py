"""Reproducible affected-population definitions. Does not invent missing fields."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime

from yield_improvement.config.loader import AppConfig
from yield_improvement.detectors.common import cal
from yield_improvement.detectors.population import DetectorContext, DieView
from yield_improvement.hypotheses.contract import Hypothesis
from yield_improvement.yield_analysis.grid_region import grid_bounds, is_grid_border


def die_key(die: DieView) -> str:
    return f"{die.lot_id}/{die.wafer_id}/{die.die_id}"


@dataclass(frozen=True)
class PopulationSlice:
    definition: str
    affected: frozenset[str]
    complement: frozenset[str]
    data_gaps: tuple[str, ...]
    resolvable: bool


def _quantile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    q = min(1.0, max(0.0, q))
    idx = int(q * (len(ordered) - 1))
    return ordered[idx]


def _label(hyp: Hypothesis) -> str | None:
    pop = hyp.affected_population or {}
    for key in ("label", "group", "region", "comparison"):
        value = pop.get(key)
        if value is not None:
            return str(value)
    for item in hyp.statistical_evidence:
        affected = item.affected_population or {}
        for key in ("label", "group", "region", "comparison"):
            value = affected.get(key)
            if value is not None:
                return str(value)
    return None


def _lot_order(dies: list[DieView]) -> list[str]:
    first_ts: dict[str, datetime] = {}
    for die in dies:
        if die.timestamp is None:
            continue
        prev = first_ts.get(die.lot_id)
        if prev is None or die.timestamp < prev:
            first_ts[die.lot_id] = die.timestamp
    if first_ts:
        return [lot for lot, _ in sorted(first_ts.items(), key=lambda kv: (kv[1], kv[0]))]
    return sorted({d.lot_id for d in dies})


def _all_keys(ctx: DetectorContext) -> frozenset[str]:
    return frozenset(die_key(d) for d in ctx.dies)


def _from_members(members: list[DieView], ctx: DetectorContext, definition: str, gaps: list[str]) -> PopulationSlice:
    affected = frozenset(die_key(d) for d in members)
    complement = _all_keys(ctx) - affected
    return PopulationSlice(definition, affected, complement, tuple(gaps), True)


def _empty(definition: str, ctx: DetectorContext, gaps: list[str]) -> PopulationSlice:
    return PopulationSlice(definition, frozenset(), _all_keys(ctx), tuple(gaps), False)


def resolve_population(hyp: Hypothesis, ctx: DetectorContext, config: AppConfig) -> PopulationSlice:
    family, detail = hyp.family, hyp.detail
    if family == "SPATIAL":
        return _spatial(detail, ctx, config)
    if family == "EQUIPMENT" and detail == "DEGRADATION":
        return _group(ctx, lambda d: d.tester_id, _label(hyp), "tester_id", "missing_tester_id")
    if family == "CONTACT" and detail == "PROBE":
        return _group(ctx, lambda d: d.probe_card_id, _label(hyp), "probe_card_id", "missing_probe_card_id")
    if family == "ENVIRONMENT" and detail == "TEMPERATURE":
        return _group(
            ctx,
            lambda d: None if d.temperature_c is None else f"{d.temperature_c:g}",
            _label(hyp),
            "temperature_c",
            "missing_temperature_c",
        )
    if family == "PROCESS" and detail == "DRIFT":
        return _drift(ctx, config)
    if family == "PROCESS" and detail == "LOT_VARIATION":
        return _group(ctx, lambda d: d.lot_id, _label(hyp), "lot_id", "missing_lot_id")
    if family == "PROCESS" and detail == "WAFER_VARIATION":
        return _group(
            ctx,
            lambda d: f"{d.lot_id}/{d.wafer_id}",
            _label(hyp),
            "lot_id/wafer_id",
            "missing_wafer_id",
        )
    if family == "PARAMETRIC" and detail == "SHIFT":
        return _parametric(hyp, ctx)
    if family == "TEST" and detail == "LIMIT_SENSITIVITY":
        return _near_limit(ctx, config)
    if family == "TEST" and detail == "SEQUENCE":
        return _empty(
            "sequence_not_reconstructed",
            ctx,
            ["Later-test observations are censored by stop-on-fail behavior."],
        )
    if family == "CORRELATED" and detail == "FAILURES":
        return _correlated(hyp, ctx)
    return _empty(f"unresolved:{family}.{detail}", ctx, [f"no_population_rule_for_{family}.{detail}"])


def _group(ctx: DetectorContext, key_fn, label: str | None, field: str, missing_gap: str) -> PopulationSlice:
    if not label:
        return _empty(f"{field}=unknown", ctx, ["affected_group_label_unavailable"])
    present = [d for d in ctx.dies if key_fn(d) is not None]
    if not present:
        return _empty(f"{field}={label}", ctx, [missing_gap])
    members = [d for d in present if str(key_fn(d)) == str(label)]
    if not members:
        return _empty(f"{field}={label}", ctx, [f"no_dies_matching_{field}"])
    return _from_members(members, ctx, f"{field}={label}", [])


def _spatial(detail: str, ctx: DetectorContext, config: AppConfig) -> PopulationSlice:
    dies = [d for d in ctx.dies if d.x is not None and d.y is not None and d.r is not None]
    if not dies:
        return _empty(f"spatial.{detail}", ctx, ["missing_x_y"])
    radii = [float(d.r) for d in dies]
    q_edge = _quantile(radii, cal(config, "spatial_edge_radius_quantile"))
    q_center = _quantile(radii, cal(config, "spatial_center_radius_quantile"))
    q_in = _quantile(radii, cal(config, "spatial_ring_inner_quantile"))
    q_out = _quantile(radii, cal(config, "spatial_ring_outer_quantile"))
    bounds = grid_bounds([(float(d.x), float(d.y)) for d in dies])
    if detail == "BORDER":
        members = [d for d in dies if is_grid_border(float(d.x), float(d.y), bounds)]
        definition = (
            f"grid boundary x in {{{bounds[0]}, {bounds[1]}}} or y in {{{bounds[2]}, {bounds[3]}}}"
        )
    elif detail == "INNER":
        members = [d for d in dies if not is_grid_border(float(d.x), float(d.y), bounds)]
        definition = "interior of observed x/y grid bounds"
    elif detail == "EDGE":
        members = [d for d in dies if float(d.r) >= q_edge]
        definition = f"radius >= edge_quantile({q_edge})"
    elif detail == "CENTER":
        members = [d for d in dies if float(d.r) <= q_center]
        definition = f"radius <= center_quantile({q_center})"
    elif detail == "RING":
        members = [d for d in dies if q_in <= float(d.r) <= q_out]
        definition = f"ring_inner({q_in}) <= radius <= ring_outer({q_out})"
    else:
        return _empty(f"spatial.{detail}", ctx, ["unknown_spatial_detail"])
    return _from_members(members, ctx, definition, [])


def _drift(ctx: DetectorContext, config: AppConfig) -> PopulationSlice:
    lots = _lot_order(ctx.dies)
    min_lots = int(cal(config, "n_min_temporal_lots"))
    min_lot_n = int(cal(config, "n_min_lot"))
    by_lot: dict[str, list[DieView]] = defaultdict(list)
    for die in ctx.dies:
        by_lot[die.lot_id].append(die)
    usable = [lot for lot in lots if len(by_lot[lot]) >= min_lot_n]
    if len(usable) < min_lots:
        return _empty("late_lot_third", ctx, ["insufficient_lot_history"])
    k = max(1, len(usable) // 3)
    late = set(usable[-k:])
    members = [d for d in ctx.dies if d.lot_id in late]
    return _from_members(members, ctx, f"late_lot_third={sorted(late)}", [])


def _parametric(hyp: Hypothesis, ctx: DetectorContext) -> PopulationSlice:
    label = _label(hyp) or ""
    lot = label.split(":")[-1] if ":" in label else label
    if not lot:
        return _empty("parametric_lot=unknown", ctx, ["affected_lot_unavailable"])
    members = [d for d in ctx.dies if d.lot_id == lot]
    if not members:
        return _empty(f"lot_id={lot}", ctx, ["no_dies_matching_lot_id"])
    return _from_members(members, ctx, f"parametric_shift_lot={lot}", [])


def _near_limit(ctx: DetectorContext, config: AppConfig) -> PopulationSlice:
    if not ctx.parametric:
        return _empty("near_limit_band", ctx, ["missing_parametric_measurements"])
    delta = cal(config, "near_limit_delta")
    by_attempt = ctx.parametric_by_attempt()
    members: list[DieView] = []
    for die in ctx.dies:
        rows = by_attempt.get(die.attempt_id, [])
        near = False
        for row in rows:
            limit = None
            candidates = [v for v in (row.lower_limit, row.upper_limit) if v is not None]
            if not candidates:
                continue
            limit = min(candidates, key=lambda lim: abs(row.measurement - lim))
            if abs(limit) < 1e-12:
                continue
            if abs(row.measurement - limit) <= delta * abs(limit):
                near = True
                break
        if near:
            members.append(die)
    if not members:
        gaps = ["no_measurements_in_near_limit_band"]
        if any(row.lower_limit is None and row.upper_limit is None for rows in by_attempt.values() for row in rows):
            gaps.append("missing_limits")
        return _empty(f"|x-L| <= {delta}*|L|", ctx, gaps)
    return _from_members(members, ctx, f"|x-L| <= {delta}*|L|", [])


def _correlated(hyp: Hypothesis, ctx: DetectorContext) -> PopulationSlice:
    label = _label(hyp) or ""
    if "~" not in label:
        return _empty("correlated_pair=unknown", ctx, ["correlated_pair_label_unavailable"])
    left, right = label.split("~", 1)
    by_attempt = ctx.tests_by_attempt()
    members: list[DieView] = []
    for die in ctx.dies:
        rows = by_attempt.get(die.attempt_id, [])
        flags = {r.test_id: r.test_pass_fail for r in rows}
        if flags.get(left) == "FAIL" and flags.get(right) == "FAIL":
            members.append(die)
    if not members:
        return _empty(f"both_fail({left},{right})", ctx, ["no_both_executed_fail_pairs"])
    return _from_members(members, ctx, f"both_executed_fail({left}~{right})", [])
