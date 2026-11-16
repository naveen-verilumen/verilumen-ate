"""Near-limit concentration. Never proposes a new limit. Opportunity remains 0%."""

from __future__ import annotations

from yield_improvement.detectors.common import cal, ev, insufficient, no_signal_result, signal_result
from yield_improvement.detectors.contract import DetectorHypothesis
from yield_improvement.detectors.population import DetectorContext
from yield_improvement.detectors.stats import compare_proportions, median


KEYS = [
    "near_limit_delta",
    "near_limit_fail_share_min",
    "near_limit_median_proximity_max",
    "near_limit_mass_min",
    "n_min_near_limit",
    "n_min_group_compare",
    "min_effect_size_fpy_delta",
    "significance_level_alpha",
    "fdr_q",
]


def _nearest_limit(measurement: float, lower: float | None, upper: float | None) -> float | None:
    candidates: list[float] = []
    if lower is not None:
        candidates.append(lower)
    if upper is not None:
        candidates.append(upper)
    if not candidates:
        return None
    return min(candidates, key=lambda lim: abs(measurement - lim))


def detect_near_limit(ctx: DetectorContext):
    if not ctx.parametric:
        return insufficient(
            "near_limit",
            "limit_proximity_band + near_vs_far_fail_rate",
            reason="missing_parametric_measurements",
            sample_size=ctx.n_eligible,
            calibration_keys=KEYS,
        )
    delta = cal(ctx.config, "near_limit_delta")
    share_min = cal(ctx.config, "near_limit_fail_share_min")
    prox_max = cal(ctx.config, "near_limit_median_proximity_max")
    mass_min = cal(ctx.config, "near_limit_mass_min")
    min_n = int(cal(ctx.config, "n_min_near_limit"))
    min_g = int(cal(ctx.config, "n_min_group_compare"))
    alpha = cal(ctx.config, "significance_level_alpha")
    min_effect = cal(ctx.config, "min_effect_size_fpy_delta")
    first_fail = {d.attempt_id: d.failed for d in ctx.dies}

    records: list[tuple[float, float, bool]] = []  # proximity, measurement, die_failed
    n_missing_limit = 0
    for row in ctx.parametric:
        failed = first_fail.get(row.attempt_id)
        if failed is None:
            continue
        limit = _nearest_limit(row.measurement, row.lower_limit, row.upper_limit)
        if limit is None or abs(limit) == 0:
            n_missing_limit += 1
            continue
        prox = abs(row.measurement - limit) / abs(limit)
        records.append((prox, row.measurement, failed))
    if not records:
        return insufficient(
            "near_limit",
            "limit_proximity_band + near_vs_far_fail_rate",
            reason="missing_limits",
            sample_size=ctx.n_eligible,
            calibration_keys=KEYS,
        )
    if len(records) < min_n:
        return insufficient(
            "near_limit",
            "limit_proximity_band + near_vs_far_fail_rate",
            reason="n_below_n_min_near_limit",
            sample_size=len(records),
            calibration_keys=KEYS,
        )
    near = [r for r in records if r[0] <= delta]
    far = [r for r in records if r[0] > delta]
    fail_share_near = (sum(1 for r in near if r[2]) / len(near)) if near else 0.0
    fails = [r for r in records if r[2]]
    fail_near_frac = (sum(1 for r in fails if r[0] <= delta) / len(fails)) if fails else 0.0
    med_prox = median([r[0] for r in records])
    mass_near = len(near) / len(records)
    evidence = [
        ev("near_limit_delta", delta, "fraction_of_abs_limit; TO_BE_CALIBRATED"),
        ev("n_measurements", len(records)),
        ev("n_near", len(near)),
        ev("fail_rate_near", fail_share_near),
        ev("fail_rate_far", (sum(1 for r in far if r[2]) / len(far)) if far else None),
        ev("fraction_of_fails_near_limit", fail_near_frac),
        ev("median_proximity", med_prox),
        ev("mass_near", mass_near),
        ev("production_opportunity", 0.0, "Immutable. Detector must not recommend SET_LIMIT."),
    ]
    gaps = []
    if n_missing_limit:
        gaps.append(f"rows_without_limits={n_missing_limit}")
    hyp = None
    if len(near) >= min_g and len(far) >= min_g:
        cmp_ = compare_proportions(
            sum(1 for r in near if r[2]),
            len(near),
            sum(1 for r in far if r[2]),
            len(far),
        )
        hyp = DetectorHypothesis(
            detector="near_limit",
            label="near_vs_far",
            family="TEST",
            detail="LIMIT_SENSITIVITY",
            p_value=cmp_.p_value,
            effect_size=cmp_.rate_diff,
            effect_size_metric="fail_rate_difference",
            sample_size=len(records),
            n_affected=len(near),
            n_baseline=len(far),
            rate_affected=cmp_.rate1,
            rate_baseline=cmp_.rate2,
        )
        evidence.append(ev("near_vs_far", {"rate_diff": cmp_.rate_diff, "p_value": cmp_.p_value, "test": cmp_.method}))
        rate_hit = cmp_.p_value <= alpha and cmp_.rate_diff >= min_effect
    else:
        rate_hit = False
        gaps.append("near_or_far_band_below_n_min_group_compare")

    concentration_hit = med_prox <= prox_max and mass_near >= mass_min
    if rate_hit or concentration_hit:
        if concentration_hit and not rate_hit:
            conc = DetectorHypothesis(
                detector="near_limit",
                label="measurement_mass_near_limit",
                family="TEST",
                detail="LIMIT_SENSITIVITY",
                p_value=None,
                effect_size=mass_near,
                effect_size_metric="near_limit_mass",
                sample_size=len(records),
                n_affected=len(near),
                n_baseline=len(far),
            )
            hyps = [conc]
            p_use = None
            eff = mass_near
            metric = "near_limit_mass"
        else:
            hyps = [hyp] if hyp else []
            p_use = hyp.p_value if hyp else None
            eff = hyp.effect_size if hyp else mass_near
            metric = hyp.effect_size_metric if hyp else "near_limit_mass"
        return signal_result(
            "near_limit",
            "limit_proximity_band + near_vs_far_fail_rate",
            family="TEST",
            detail="LIMIT_SENSITIVITY",
            sample_size=len(records),
            calibration_keys=KEYS,
            p_value=p_use,
            effect_size=eff,
            effect_size_metric=metric,
            affected={"band": f"|x-L| <= {delta}*|L|", "n": len(near), "fail_rate": fail_share_near, "mass_near": mass_near},
            baseline={"n": len(far)},
            evidence=evidence,
            data_gaps=gaps,
            hypotheses=hyps,
            confidence="LOW",
            counter_evidence=[
                ev("does_not_modify_limits", True),
                ev("safety_eligible_production", 0.0),
            ],
        )
    return no_signal_result(
        "near_limit",
        "limit_proximity_band + near_vs_far_fail_rate",
        sample_size=len(records),
        calibration_keys=KEYS,
        evidence=evidence,
        data_gaps=gaps,
        hypotheses=[hyp] if hyp else [],
        p_value=hyp.p_value if hyp else None,
        effect_size=hyp.effect_size if hyp else fail_near_frac,
        effect_size_metric="fail_rate_difference" if hyp else "fraction_of_fails_near_limit",
        counter_evidence=[ev("does_not_modify_limits", True)],
    )
