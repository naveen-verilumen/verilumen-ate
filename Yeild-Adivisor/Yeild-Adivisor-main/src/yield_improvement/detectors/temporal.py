"""Temporal / drift detector: early vs late windows + Mann-Kendall on lot rates."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from yield_improvement.detectors.common import cal, ev, insufficient, no_signal_result, signal_result
from yield_improvement.detectors.contract import DetectorHypothesis
from yield_improvement.detectors.population import DetectorContext, DieView
from yield_improvement.detectors.stats import compare_proportions, mann_kendall


KEYS = [
    "n_min_temporal_lots",
    "n_min_lot",
    "n_min_group_compare",
    "ewma_lambda",
    "min_effect_size_fpy_delta",
    "significance_level_alpha",
    "fdr_q",
]


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


def detect_temporal(ctx: DetectorContext):
    dies = [d for d in ctx.dies if d.timestamp is not None]
    lots = _lot_order(ctx.dies if dies else ctx.dies)
    min_lots = int(cal(ctx.config, "n_min_temporal_lots"))
    min_lot_n = int(cal(ctx.config, "n_min_lot"))
    if len(lots) < min_lots:
        return insufficient(
            "temporal",
            "early_late_two_proportion + mann_kendall",
            reason="insufficient_lot_history",
            sample_size=ctx.n_eligible,
            calibration_keys=KEYS,
            extra_gaps=[f"n_lots={len(lots)} n_min_temporal_lots={min_lots}"],
        )
    by_lot: dict[str, list[DieView]] = defaultdict(list)
    for die in ctx.dies:
        by_lot[die.lot_id].append(die)
    rates: list[float] = []
    ordered_usable: list[str] = []
    for lot in lots:
        members = by_lot[lot]
        if len(members) < min_lot_n:
            continue
        rates.append(sum(1 for d in members if d.failed) / len(members))
        ordered_usable.append(lot)
    if len(ordered_usable) < min_lots:
        return insufficient(
            "temporal",
            "early_late_two_proportion + mann_kendall",
            reason="usable_lots_below_n_min_temporal_lots",
            sample_size=ctx.n_eligible,
            calibration_keys=KEYS,
        )
    k = max(1, len(ordered_usable) // 3)
    early_lots = set(ordered_usable[:k])
    late_lots = set(ordered_usable[-k:])
    early = [d for d in ctx.dies if d.lot_id in early_lots]
    late = [d for d in ctx.dies if d.lot_id in late_lots]
    min_g = int(cal(ctx.config, "n_min_group_compare"))
    if len(early) < min_g or len(late) < min_g:
        return insufficient(
            "temporal",
            "early_late_two_proportion + mann_kendall",
            reason="early_or_late_window_below_n_min_group_compare",
            sample_size=ctx.n_eligible,
            calibration_keys=KEYS,
        )
    cmp_ = compare_proportions(
        sum(1 for d in late if d.failed),
        len(late),
        sum(1 for d in early if d.failed),
        len(early),
    )
    tau, mk_p = mann_kendall(rates)
    lam = cal(ctx.config, "ewma_lambda")
    ewma = rates[0]
    ewma_series = [ewma]
    for r in rates[1:]:
        ewma = lam * r + (1 - lam) * ewma
        ewma_series.append(ewma)
    min_effect = cal(ctx.config, "min_effect_size_fpy_delta")
    alpha = cal(ctx.config, "significance_level_alpha")
    hyp_window = DetectorHypothesis(
        detector="temporal",
        label="late_vs_early",
        family="PROCESS",
        detail="DRIFT",
        p_value=cmp_.p_value,
        effect_size=cmp_.rate_diff,
        effect_size_metric="fail_rate_difference",
        sample_size=len(early) + len(late),
        n_affected=len(late),
        n_baseline=len(early),
        rate_affected=cmp_.rate1,
        rate_baseline=cmp_.rate2,
    )
    hyp_mk = DetectorHypothesis(
        detector="temporal",
        label="mann_kendall",
        family="PROCESS",
        detail="DRIFT",
        p_value=mk_p,
        effect_size=tau,
        effect_size_metric="mann_kendall_tau",
        sample_size=len(ordered_usable),
    )
    evidence = [
        ev("lot_order", ordered_usable),
        ev("lot_fail_rates", {lot: rates[i] for i, lot in enumerate(ordered_usable)}),
        ev("early_lots", sorted(early_lots)),
        ev("late_lots", sorted(late_lots)),
        ev("late_vs_early", {"rate_diff": cmp_.rate_diff, "p_value": cmp_.p_value, "test": cmp_.method}),
        ev("mann_kendall", {"tau": tau, "p_value": mk_p}),
        ev("ewma", ewma_series, f"lambda={lam} (supporting trace, not a production control limit)"),
    ]
    window_hit = (cmp_.p_value <= alpha and abs(cmp_.rate_diff) >= min_effect)
    mk_hit = mk_p <= alpha and abs(tau) >= 0.5
    if window_hit or (mk_hit and abs(cmp_.rate_diff) >= min_effect / 2):
        return signal_result(
            "temporal",
            "early_late_two_proportion + mann_kendall + ewma_trace",
            family="PROCESS",
            detail="DRIFT",
            sample_size=ctx.n_eligible,
            calibration_keys=KEYS,
            p_value=min(cmp_.p_value, mk_p),
            effect_size=cmp_.rate_diff,
            effect_size_metric="fail_rate_difference",
            affected={"lots": sorted(late_lots), "n": len(late), "fail_rate": cmp_.rate1},
            baseline={"lots": sorted(early_lots), "n": len(early), "fail_rate": cmp_.rate2},
            evidence=evidence,
            hypotheses=[hyp_window, hyp_mk],
            confidence="MEDIUM" if window_hit and mk_hit else "LOW",
            counter_evidence=[ev("lot_order_assumed_chronological", True)],
        )
    return no_signal_result(
        "temporal",
        "early_late_two_proportion + mann_kendall + ewma_trace",
        sample_size=ctx.n_eligible,
        calibration_keys=KEYS,
        evidence=evidence,
        hypotheses=[hyp_window, hyp_mk],
        p_value=min(cmp_.p_value, mk_p),
        effect_size=cmp_.rate_diff,
        effect_size_metric="fail_rate_difference",
    )
