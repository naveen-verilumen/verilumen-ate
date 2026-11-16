"""Parametric distribution shift. Requires a distributional change, not mere presence of a parameter."""

from __future__ import annotations

from collections import defaultdict

from yield_improvement.detectors.common import cal, ev, insufficient, no_signal_result, raw_p, signal_result
from yield_improvement.detectors.contract import DetectorHypothesis
from yield_improvement.detectors.population import DetectorContext
from yield_improvement.detectors.stats import ks_two_sample, median


KEYS = [
    "n_min_parametric",
    "ks_d_min",
    "psi_shift_flag",
    "significance_level_alpha",
    "fdr_q",
    "min_effect_size_fpy_delta",
]


def _psi(a: list[float], b: list[float], bins: int = 10) -> float:
    if not a or not b:
        return 0.0
    lo = min(min(a), min(b))
    hi = max(max(a), max(b))
    if hi <= lo:
        return 0.0
    width = (hi - lo) / bins
    def hist(vals: list[float]) -> list[float]:
        counts = [0.0] * bins
        for v in vals:
            idx = min(bins - 1, int((v - lo) / width))
            counts[idx] += 1
        n = len(vals)
        return [(c + 0.5) / (n + 0.5 * bins) for c in counts]
    pa, pb = hist(a), hist(b)
    return sum((x - y) * __import__("math").log(x / y) for x, y in zip(pa, pb))


def detect_parametric(ctx: DetectorContext):
    if not ctx.parametric:
        return insufficient(
            "parametric",
            "ks_two_sample_lot_vs_complement + psi",
            reason="missing_parametric_measurements",
            sample_size=ctx.n_eligible,
            calibration_keys=KEYS,
        )
    first_ids = {d.attempt_id for d in ctx.dies}
    by_param_lot: dict[tuple[str, str], list[float]] = defaultdict(list)
    attempt_lot = {d.attempt_id: d.lot_id for d in ctx.dies}
    for row in ctx.parametric:
        if row.attempt_id not in first_ids:
            continue
        lot = attempt_lot.get(row.attempt_id)
        if lot is None:
            continue
        by_param_lot[(row.parameter_name, lot)].append(row.measurement)
    min_n = int(cal(ctx.config, "n_min_parametric"))
    d_min = cal(ctx.config, "ks_d_min")
    psi_thr = cal(ctx.config, "psi_shift_flag")
    alpha = cal(ctx.config, "significance_level_alpha")
    params = sorted({p for p, _ in by_param_lot})
    if not params:
        return insufficient(
            "parametric",
            "ks_two_sample_lot_vs_complement + psi",
            reason="no_first_pass_parametric_rows",
            sample_size=ctx.n_eligible,
            calibration_keys=KEYS,
        )
    hypotheses: list[DetectorHypothesis] = []
    evidence = [ev("parameters", params)]
    for param in params:
        lots = {lot: vals for (p, lot), vals in by_param_lot.items() if p == param and len(vals) >= min_n}
        if len(lots) < 2:
            evidence.append(ev(f"{param}_skipped", "fewer than 2 lots meeting n_min_parametric"))
            continue
        for lot, vals in sorted(lots.items()):
            complement = [v for other, ov in lots.items() if other != lot for v in ov]
            if len(complement) < min_n:
                continue
            d_stat, p_val = ks_two_sample(vals, complement)
            psi = _psi(vals, complement)
            med_delta = median(vals) - median(complement)
            hyp = DetectorHypothesis(
                detector="parametric",
                label=f"{param}:{lot}",
                family="PARAMETRIC",
                detail="SHIFT",
                p_value=p_val,
                effect_size=d_stat,
                effect_size_metric="ks_d",
                sample_size=len(vals) + len(complement),
                n_affected=len(vals),
                n_baseline=len(complement),
            )
            hypotheses.append(hyp)
            evidence.append(
                ev(
                    f"ks_{param}_{lot}",
                    {
                        "ks_d": d_stat,
                        "p_value": p_val,
                        "psi": psi,
                        "median_delta": med_delta,
                        "n_lot": len(vals),
                        "n_complement": len(complement),
                    },
                )
            )
    if not hypotheses:
        return insufficient(
            "parametric",
            "ks_two_sample_lot_vs_complement + psi",
            reason="parametric_groups_below_n_min_parametric",
            sample_size=ctx.n_eligible,
            calibration_keys=KEYS,
        )
    passing = [
        h
        for h in hypotheses
        if raw_p(h.p_value) <= alpha and (h.effect_size or 0) >= d_min
    ]
    if passing:
        winner = max(passing, key=lambda h: h.effect_size or 0.0)
        return signal_result(
            "parametric",
            "ks_two_sample_lot_vs_complement + psi",
            family="PARAMETRIC",
            detail="SHIFT",
            sample_size=ctx.n_eligible,
            calibration_keys=KEYS,
            p_value=winner.p_value,
            effect_size=winner.effect_size,
            effect_size_metric="ks_d",
            affected={"comparison": winner.label, "n": winner.n_affected},
            baseline={"n": winner.n_baseline},
            evidence=evidence,
            hypotheses=hypotheses,
            confidence="LOW",
            counter_evidence=[ev("large_n_ks_guarded_by_ks_d_min", d_min)],
        )
    winner = max(hypotheses, key=lambda h: h.effect_size or 0.0)
    return no_signal_result(
        "parametric",
        "ks_two_sample_lot_vs_complement + psi",
        sample_size=ctx.n_eligible,
        calibration_keys=KEYS,
        evidence=evidence,
        hypotheses=hypotheses,
        p_value=winner.p_value,
        effect_size=winner.effect_size,
        effect_size_metric="ks_d",
        counter_evidence=[ev("no_lot_met_ks_d_and_p", {"ks_d_min": d_min, "psi_flag": psi_thr})],
    )
