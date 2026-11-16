"""Failure-mode association (not causation). Stop-on-fail censors later tests."""

from __future__ import annotations

from collections import defaultdict

from yield_improvement.detectors.common import cal, ev, insufficient, no_signal_result, raw_p, signal_result
from yield_improvement.detectors.contract import DetectorHypothesis
from yield_improvement.detectors.population import DetectorContext
from yield_improvement.detectors.stats import compare_proportions, fisher_exact_two_sided


KEYS = [
    "n_min_correlation",
    "n_min_group_compare",
    "min_effect_size_fpy_delta",
    "significance_level_alpha",
    "fdr_q",
]


def detect_correlation(ctx: DetectorContext):
    if not ctx.test_results:
        return insufficient(
            "correlation",
            "fisher_or_two_proportion_on_both_executed_fail_flags",
            reason="missing_test_results",
            sample_size=ctx.n_eligible,
            calibration_keys=KEYS,
        )
    first_ids = {d.attempt_id for d in ctx.dies}
    by_attempt: dict[str, dict[str, str]] = defaultdict(dict)
    n_not_exec = 0
    for row in ctx.test_results:
        if row.attempt_id not in first_ids:
            continue
        by_attempt[row.attempt_id][row.test_id] = row.test_pass_fail
        if row.test_pass_fail == "NOT_EXECUTED":
            n_not_exec += 1
    tests = sorted({tid for flags in by_attempt.values() for tid in flags})
    if len(tests) < 2:
        return insufficient(
            "correlation",
            "fisher_or_two_proportion_on_both_executed_fail_flags",
            reason="fewer_than_two_test_ids",
            sample_size=ctx.n_eligible,
            calibration_keys=KEYS,
        )
    min_n = int(cal(ctx.config, "n_min_correlation"))
    min_g = int(cal(ctx.config, "n_min_group_compare"))
    min_effect = cal(ctx.config, "min_effect_size_fpy_delta")
    alpha = cal(ctx.config, "significance_level_alpha")
    hypotheses: list[DetectorHypothesis] = []
    evidence = [ev("test_ids", tests), ev("not_executed_rows", n_not_exec)]
    for i, a in enumerate(tests):
        for b in tests[i + 1 :]:
            both = []
            for flags in by_attempt.values():
                sa, sb = flags.get(a), flags.get(b)
                if sa in {"PASS", "FAIL"} and sb in {"PASS", "FAIL"}:
                    both.append((sa == "FAIL", sb == "FAIL"))
            if len(both) < min_n:
                continue
            a_fail = [bf for af, bf in both if af]
            a_pass = [bf for af, bf in both if not af]
            if len(a_fail) < min_g or len(a_pass) < min_g:
                continue
            n11 = sum(1 for af, bf in both if af and bf)
            n10 = sum(1 for af, bf in both if af and not bf)
            n01 = sum(1 for af, bf in both if not af and bf)
            n00 = sum(1 for af, bf in both if not af and not bf)
            jaccard = n11 / (n11 + n10 + n01) if (n11 + n10 + n01) else 0.0
            cmp_ = compare_proportions(sum(a_fail), len(a_fail), sum(a_pass), len(a_pass))
            fisher_p = fisher_exact_two_sided(n11, n10, n01, n00)
            p_use = min(cmp_.p_value, fisher_p)
            hyp = DetectorHypothesis(
                detector="correlation",
                label=f"{a}~{b}",
                family="CORRELATED",
                detail="FAILURES",
                p_value=p_use,
                effect_size=jaccard,
                effect_size_metric="jaccard",
                sample_size=len(both),
                n_affected=n11,
                n_baseline=len(both) - n11,
                rate_affected=cmp_.rate1,
                rate_baseline=cmp_.rate2,
            )
            hypotheses.append(hyp)
            evidence.append(
                ev(
                    f"pair_{a}_{b}",
                    {
                        "n00": n00,
                        "n01": n01,
                        "n10": n10,
                        "n11": n11,
                        "jaccard": jaccard,
                        "p_later_given_a_fail": cmp_.rate1,
                        "p_later_given_a_pass": cmp_.rate2,
                        "rate_diff": cmp_.rate_diff,
                        "fisher_p": fisher_p,
                        "two_prop_p": cmp_.p_value,
                    },
                )
            )
    gaps = ["stop_on_fail_censors_pairs"]
    if not hypotheses:
        return insufficient(
            "correlation",
            "fisher_or_two_proportion_on_both_executed_fail_flags",
            reason="no_both_executed_pairs_meeting_n_min_correlation",
            sample_size=ctx.n_eligible,
            calibration_keys=KEYS,
            extra_gaps=gaps,
        )
    passing = [
        h
        for h in hypotheses
        if raw_p(h.p_value) <= alpha and (h.effect_size or 0) >= 0.15 and abs((h.rate_affected or 0) - (h.rate_baseline or 0)) >= min_effect
    ]
    if passing:
        winner = max(passing, key=lambda h: h.effect_size or 0.0)
        return signal_result(
            "correlation",
            "fisher_or_two_proportion_on_both_executed_fail_flags",
            family="CORRELATED",
            detail="FAILURES",
            sample_size=ctx.n_eligible,
            calibration_keys=KEYS,
            p_value=winner.p_value,
            effect_size=winner.effect_size,
            effect_size_metric="jaccard",
            affected={"pair": winner.label, "n11": winner.n_affected},
            baseline={"n_both_executed": winner.sample_size},
            evidence=evidence,
            data_gaps=gaps,
            hypotheses=hypotheses,
            confidence="LOW",
            counter_evidence=[ev("association_is_not_causation", True)],
        )
    winner = max(hypotheses, key=lambda h: h.effect_size or 0.0)
    return no_signal_result(
        "correlation",
        "fisher_or_two_proportion_on_both_executed_fail_flags",
        sample_size=ctx.n_eligible,
        calibration_keys=KEYS,
        evidence=evidence,
        data_gaps=gaps,
        hypotheses=hypotheses,
        p_value=winner.p_value,
        effect_size=winner.effect_size,
        effect_size_metric="jaccard",
        counter_evidence=[ev("association_is_not_causation", True)],
    )
