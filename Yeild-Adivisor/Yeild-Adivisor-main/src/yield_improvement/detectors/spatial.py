"""Spatial concentration: grid-boundary BORDER/INNER, plus radial EDGE/CENTER/RING.

BORDER and INNER use the outermost observed X and Y. They are not distance from
the origin. EDGE, CENTER, and RING remain radial comparisons so existing radius
scenarios keep their identity. Neither comparison is a root cause.
"""

from __future__ import annotations

from yield_improvement.detectors.common import cal, ev, insufficient, no_signal_result, raw_p, signal_result
from yield_improvement.detectors.contract import DetectorHypothesis
from yield_improvement.detectors.population import DetectorContext, DieView
from yield_improvement.detectors.stats import compare_proportions
from yield_improvement.yield_analysis.grid_region import is_grid_border, is_positive_filled_grid


KEYS = [
    "n_min_wafer",
    "n_min_group_compare",
    "spatial_edge_radius_quantile",
    "spatial_center_radius_quantile",
    "spatial_ring_inner_quantile",
    "spatial_ring_outer_quantile",
    "spatial_nn_count",
    "spatial_fail_density_threshold",
    "min_effect_size_fpy_delta",
    "significance_level_alpha",
    "fdr_q",
]


def _quantile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    q = min(1.0, max(0.0, q))
    idx = int(q * (len(ordered) - 1))
    return ordered[idx]


def detect_spatial(ctx: DetectorContext):
    dies = [d for d in ctx.dies if d.x is not None and d.y is not None and d.r is not None]
    if not dies:
        return insufficient(
            "spatial",
            "zone_two_proportion_vs_complement",
            reason="missing_x_y",
            sample_size=ctx.n_eligible,
            calibration_keys=KEYS,
        )
    if len(dies) < int(cal(ctx.config, "n_min_wafer")):
        return insufficient(
            "spatial",
            "zone_two_proportion_vs_complement",
            reason="n_below_n_min_wafer",
            sample_size=len(dies),
            calibration_keys=KEYS,
        )
    radii = [float(d.r) for d in dies]
    q_edge = _quantile(radii, cal(ctx.config, "spatial_edge_radius_quantile"))
    q_center = _quantile(radii, cal(ctx.config, "spatial_center_radius_quantile"))
    q_ring_in = _quantile(radii, cal(ctx.config, "spatial_ring_inner_quantile"))
    q_ring_out = _quantile(radii, cal(ctx.config, "spatial_ring_outer_quantile"))
    min_g = int(cal(ctx.config, "n_min_group_compare"))
    min_effect = cal(ctx.config, "min_effect_size_fpy_delta")
    alpha = cal(ctx.config, "significance_level_alpha")

    xs = [float(d.x) for d in dies]
    ys = [float(d.y) for d in dies]
    bounds = (min(xs), max(xs), min(ys), max(ys))

    def on_border(die: DieView) -> bool:
        return is_grid_border(float(die.x), float(die.y), bounds)

    use_grid_border = is_positive_filled_grid([(float(d.x), float(d.y)) for d in dies])
    if use_grid_border:
        regions = {
            "BORDER": on_border,
            "INNER": lambda die: not on_border(die),
        }
    else:
        regions = {
            "EDGE": lambda die: float(die.r) >= q_edge,
            "CENTER": lambda die: float(die.r) <= q_center,
            "RING": lambda die: q_ring_in <= float(die.r) <= q_ring_out,
        }
    hypotheses: list[DetectorHypothesis] = []
    evidence = [
        ev(
            "grid_boundary",
            {
                "x_min": bounds[0],
                "x_max": bounds[1],
                "y_min": bounds[2],
                "y_max": bounds[3],
                "rule": "BORDER when x==x_min or x==x_max or y==y_min or y==y_max; INNER otherwise",
            },
        ),
        ev("radius_thresholds", {"edge": q_edge, "center": q_center, "ring": [q_ring_in, q_ring_out]}),
        ev("n_with_xy", len(dies)),
    ]
    for name, pred in regions.items():
        inside = [d for d in dies if pred(d)]
        outside = [d for d in dies if d not in inside]
        if len(inside) < min_g or len(outside) < min_g:
            evidence.append(ev(f"{name}_skipped", {"n_inside": len(inside), "n_outside": len(outside)}))
            continue
        f1 = sum(1 for d in inside if d.failed)
        f2 = sum(1 for d in outside if d.failed)
        cmp_ = compare_proportions(f1, len(inside), f2, len(outside))
        hyp = DetectorHypothesis(
            detector="spatial",
            label=name,
            family="SPATIAL",
            detail=name,
            p_value=cmp_.p_value,
            effect_size=cmp_.rate_diff,
            effect_size_metric="fail_rate_difference",
            sample_size=len(dies),
            n_affected=len(inside),
            n_baseline=len(outside),
            rate_affected=cmp_.rate1,
            rate_baseline=cmp_.rate2,
        )
        hypotheses.append(hyp)
        evidence.append(
            ev(
                f"region_{name}",
                {
                    "n": len(inside),
                    "fail_rate": round(cmp_.rate1, 6),
                    "complement_fail_rate": round(cmp_.rate2, 6),
                    "rate_diff": round(cmp_.rate_diff, 6),
                    "p_value": cmp_.p_value,
                    "test": cmp_.method,
                },
            )
        )

    nn_k = int(cal(ctx.config, "spatial_nn_count"))
    dens_thr = cal(ctx.config, "spatial_fail_density_threshold")
    fail_xy = [(float(d.x), float(d.y)) for d in dies if d.failed]
    if fail_xy and nn_k >= 1:
        dense = 0
        for d in dies:
            if not d.failed:
                continue
            dist = sorted((float(d.x) - x) ** 2 + (float(d.y) - y) ** 2 for x, y in fail_xy)
            neighbors = dist[1 : nn_k + 1]
            if neighbors and (len(neighbors) / nn_k) >= dens_thr:
                # dist includes self at 0; neighbor fail fraction among k nearest fails is tautological.
                # Use k nearest dies of any disposition instead.
                dense += 0
        all_xy = [(float(d.x), float(d.y), d.failed) for d in dies]
        dense_fails = 0
        checked = 0
        for d in dies:
            if not d.failed:
                continue
            checked += 1
            others = sorted(
                (((float(d.x) - x) ** 2 + (float(d.y) - y) ** 2), failed)
                for x, y, failed in all_xy
                if not (x == d.x and y == d.y)
            )[:nn_k]
            if others and sum(1 for _, failed in others if failed) / len(others) >= dens_thr:
                dense_fails += 1
        if checked:
            evidence.append(
                ev(
                    "nn_fail_density",
                    {"fail_dies_with_dense_fail_neighbors": dense_fails, "fail_dies": checked, "k": nn_k},
                )
            )

    if not hypotheses:
        return insufficient(
            "spatial",
            "zone_two_proportion_vs_complement",
            reason="spatial_regions_below_n_min_group_compare",
            sample_size=len(dies),
            calibration_keys=KEYS,
        )

    passing = [
        h
        for h in hypotheses
        if raw_p(h.p_value) <= alpha and (h.effect_size or 0) >= min_effect
    ]
    if passing:
        winner = max(passing, key=lambda h: h.effect_size or 0.0)
        wafers = {}
        for d in dies:
            wafers.setdefault((d.lot_id, d.wafer_id), []).append(d)
        replicated = 0
        pred = regions[str(winner.detail)]
        for members in wafers.values():
            if len(members) < min_g:
                continue
            inside = [d for d in members if pred(d)]
            outside = [d for d in members if d not in inside]
            if len(inside) < 5 or len(outside) < 5:
                continue
            r1 = sum(d.failed for d in inside) / len(inside)
            r2 = sum(d.failed for d in outside) / len(outside)
            if r1 - r2 >= min_effect / 2:
                replicated += 1
        conf = "MEDIUM" if replicated >= 2 else "LOW"
        return signal_result(
            "spatial",
            "zone_two_proportion_vs_complement + nn_fail_density",
            family="SPATIAL",
            detail=str(winner.detail),
            sample_size=len(dies),
            calibration_keys=KEYS,
            p_value=winner.p_value,
            effect_size=winner.effect_size,
            effect_size_metric="fail_rate_difference",
            affected={
                "region": winner.detail,
                "n": winner.n_affected,
                "fail_rate": winner.rate_affected,
            },
            baseline={"n": winner.n_baseline, "fail_rate": winner.rate_baseline},
            evidence=evidence + [ev("wafers_replicating_region", replicated)],
            hypotheses=hypotheses,
            confidence=conf,
        )
    winner = max(hypotheses, key=lambda h: h.effect_size or 0.0)
    return no_signal_result(
        "spatial",
        "zone_two_proportion_vs_complement + nn_fail_density",
        sample_size=len(dies),
        calibration_keys=KEYS,
        evidence=evidence,
        hypotheses=hypotheses,
        p_value=winner.p_value,
        effect_size=winner.effect_size,
        effect_size_metric="fail_rate_difference",
        counter_evidence=[ev("no_region_met_p_and_min_effect", True)],
    )
