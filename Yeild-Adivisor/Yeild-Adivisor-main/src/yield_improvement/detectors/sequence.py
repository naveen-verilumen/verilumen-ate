"""Test-sequence association. Does not infer order from CSV row order."""

from __future__ import annotations

from collections import defaultdict

from yield_improvement.detectors.common import cal, ev, insufficient, no_signal_result, raw_p, signal_result
from yield_improvement.detectors.contract import DetectorHypothesis
from yield_improvement.detectors.population import DetectorContext
from yield_improvement.detectors.stats import compare_proportions


KEYS = [
    "n_min_sequence_pairs",
    "n_min_group_compare",
    "min_effect_size_fpy_delta",
    "significance_level_alpha",
    "fdr_q",
]


def detect_sequence(ctx: DetectorContext):
    if not ctx.test_results:
        return insufficient(
            "sequence",
            "conditional_fail_given_preceding_test",
            reason="missing_test_results",
            sample_size=ctx.n_eligible,
            calibration_keys=KEYS,
        )
    first_ids = {d.attempt_id for d in ctx.dies}
    by_attempt: dict[str, list] = defaultdict(list)
    n_missing_seq = 0
    n_rows = 0
    for row in ctx.test_results:
        if row.attempt_id not in first_ids:
            continue
        n_rows += 1
        if row.sequence_index is None:
            n_missing_seq += 1
            continue
        by_attempt[row.attempt_id].append(row)
    if n_rows == 0:
        return insufficient(
            "sequence",
            "conditional_fail_given_preceding_test",
            reason="missing_test_results",
            sample_size=ctx.n_eligible,
            calibration_keys=KEYS,
        )
    if n_missing_seq == n_rows:
        return insufficient(
            "sequence",
            "conditional_fail_given_preceding_test",
            reason="missing_sequence_index",
            sample_size=ctx.n_eligible,
            calibration_keys=KEYS,
        )
    min_pairs = int(cal(ctx.config, "n_min_sequence_pairs"))
    min_g = int(cal(ctx.config, "n_min_group_compare"))
    min_effect = cal(ctx.config, "min_effect_size_fpy_delta")
    alpha = cal(ctx.config, "significance_level_alpha")
    stop_on_fail = 0
    executed_pairs: dict[tuple[str, str], list[tuple[bool, bool]]] = defaultdict(list)
    for rows in by_attempt.values():
        ordered = sorted(rows, key=lambda r: (r.sequence_index, r.test_id))
        if any(r.test_pass_fail == "NOT_EXECUTED" for r in ordered):
            stop_on_fail += 1
        executed = [r for r in ordered if r.test_pass_fail in {"PASS", "FAIL"}]
        for i, earlier in enumerate(executed):
            for later in executed[i + 1 :]:
                if earlier.sequence_index >= later.sequence_index:
                    continue
                executed_pairs[(earlier.test_id, later.test_id)].append(
                    (earlier.test_pass_fail == "FAIL", later.test_pass_fail == "FAIL")
                )
    evidence = [
        ev("attempts_with_sequence", len(by_attempt)),
        ev("attempts_with_not_executed", stop_on_fail, "stop-on-fail censors later tests"),
    ]
    if not executed_pairs:
        return insufficient(
            "sequence",
            "conditional_fail_given_preceding_test",
            reason="no_both_executed_test_pairs",
            sample_size=ctx.n_eligible,
            calibration_keys=KEYS,
            extra_gaps=["stop_on_fail_may_censor_later_tests"],
        )
    hypotheses: list[DetectorHypothesis] = []
    for pair, flags in sorted(executed_pairs.items()):
        if len(flags) < min_pairs:
            continue
        a_fail = [later for earlier, later in flags if earlier]
        a_pass = [later for earlier, later in flags if not earlier]
        if len(a_fail) < min_g or len(a_pass) < min_g:
            continue
        cmp_ = compare_proportions(sum(a_fail), len(a_fail), sum(a_pass), len(a_pass))
        hyp = DetectorHypothesis(
            detector="sequence",
            label=f"{pair[1]}|preceded_by|{pair[0]}",
            family="TEST",
            detail="SEQUENCE",
            p_value=cmp_.p_value,
            effect_size=cmp_.rate_diff,
            effect_size_metric="fail_rate_difference",
            sample_size=len(flags),
            n_affected=len(a_fail),
            n_baseline=len(a_pass),
            rate_affected=cmp_.rate1,
            rate_baseline=cmp_.rate2,
        )
        hypotheses.append(hyp)
        evidence.append(
            ev(
                f"pair_{pair[0]}_{pair[1]}",
                {
                    "p_later_fail_given_earlier_fail": cmp_.rate1,
                    "p_later_fail_given_earlier_pass": cmp_.rate2,
                    "rate_diff": cmp_.rate_diff,
                    "p_value": cmp_.p_value,
                    "n_both_executed": len(flags),
                    "test": cmp_.method,
                },
            )
        )
    gaps = ["stop_on_fail_biases_unexecuted_later_tests"]
    if not hypotheses:
        return insufficient(
            "sequence",
            "conditional_fail_given_preceding_test",
            reason="sequence_pairs_below_n_min_sequence_pairs",
            sample_size=ctx.n_eligible,
            calibration_keys=KEYS,
            extra_gaps=gaps,
        )
    passing = [
        h
        for h in hypotheses
        if raw_p(h.p_value) <= alpha and abs(h.effect_size or 0) >= min_effect
    ]
    if passing:
        winner = max(passing, key=lambda h: abs(h.effect_size or 0.0))
        return signal_result(
            "sequence",
            "conditional_fail_given_preceding_test",
            family="TEST",
            detail="SEQUENCE",
            sample_size=ctx.n_eligible,
            calibration_keys=KEYS,
            p_value=winner.p_value,
            effect_size=winner.effect_size,
            effect_size_metric="fail_rate_difference",
            affected={"pair": winner.label, "n_preceding_fail": winner.n_affected},
            baseline={"n_preceding_pass": winner.n_baseline},
            evidence=evidence,
            data_gaps=gaps,
            hypotheses=hypotheses,
            confidence="LOW",
            counter_evidence=[ev("row_order_not_used", True, "sequence_index required")],
        )
    winner = max(hypotheses, key=lambda h: abs(h.effect_size or 0.0))
    return no_signal_result(
        "sequence",
        "conditional_fail_given_preceding_test",
        sample_size=ctx.n_eligible,
        calibration_keys=KEYS,
        evidence=evidence,
        data_gaps=gaps,
        hypotheses=hypotheses,
        p_value=winner.p_value,
        effect_size=winner.effect_size,
        effect_size_metric="fail_rate_difference",
        counter_evidence=[ev("row_order_not_used", True)],
    )
