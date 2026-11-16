"""Primary-fail (additive) and any-fail (overlapping) attribution."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from yield_improvement.config.loader import AppConfig
from yield_improvement.models.canonical import DieAttempt, Failure, TestResult
from yield_improvement.models.results import CofailRow, ParetoRow, PrimaryFailureRow
from yield_improvement.yield_analysis.taxonomy import map_taxonomy, split_taxonomy


@dataclass
class AttributionResult:
    primary_failures: list[PrimaryFailureRow]
    primary_pareto: list[ParetoRow]
    any_fail_pareto: list[ParetoRow]
    cofail: list[CofailRow]
    failure_events: list[Failure]


def _taxonomy_for_key(
    config: AppConfig,
    *,
    failure_code: str | None,
    sbin: int | None,
    hbin: int | None,
    fallback: str | None = None,
) -> str:
    if fallback:
        return fallback
    return map_taxonomy(config, failure_code=failure_code, sbin=sbin, hbin=hbin)


def select_primary(
    attempt: DieAttempt,
    failed_tests: list[TestResult],
    config: AppConfig,
) -> tuple[str, str | None, str, str, list[TestResult]]:
    """
    Returns failure_key, failure_code, selection_method, taxonomy_code, cofail_tests.
    """
    if attempt.abort_flag and not failed_tests:
        tax = map_taxonomy(config, failure_code="ABORT", sbin=attempt.sbin)
        return "ABORT", attempt.failure_code or "ABORT", "abort", tax, []

    if not failed_tests:
        if attempt.failure_code:
            tax = map_taxonomy(config, failure_code=attempt.failure_code, sbin=attempt.sbin)
            return attempt.failure_code, attempt.failure_code, "failure_code", tax, []
        if attempt.sbin is not None:
            tax = map_taxonomy(config, sbin=attempt.sbin, hbin=attempt.hbin)
            return f"BIN:{attempt.sbin}", attempt.failure_code, "bin", tax, []
        return (
            "UNKNOWN_PRIMARY_FAILURE",
            None,
            "UNKNOWN_PRIMARY_FAILURE",
            "UNKNOWN.PRIMARY_UNORDERED",
            [],
        )

    trues = [t for t in failed_tests if t.is_first_fail is True]
    if len(trues) == 1:
        primary = trues[0]
        cofail = [t for t in failed_tests if t.test_id != primary.test_id]
        tax = map_taxonomy(config, failure_code=primary.failure_code, sbin=attempt.sbin)
        return primary.test_id, primary.failure_code, "is_first_fail", tax, cofail
    if len(trues) > 1:
        return (
            "UNKNOWN_PRIMARY_FAILURE",
            None,
            "UNKNOWN_PRIMARY_FAILURE",
            "UNKNOWN.PRIMARY_UNORDERED",
            failed_tests,
        )

    if failed_tests and all(t.sequence_index is not None for t in failed_tests):
        min_seq = min(t.sequence_index for t in failed_tests if t.sequence_index is not None)
        at_min = [t for t in failed_tests if t.sequence_index == min_seq]
        if len(at_min) == 1:
            primary = at_min[0]
            cofail = [t for t in failed_tests if t.test_id != primary.test_id]
            tax = map_taxonomy(config, failure_code=primary.failure_code, sbin=attempt.sbin)
            return primary.test_id, primary.failure_code, "sequence_index", tax, cofail
        return (
            "UNKNOWN_PRIMARY_FAILURE",
            None,
            "UNKNOWN_PRIMARY_FAILURE",
            "UNKNOWN.PRIMARY_UNORDERED",
            failed_tests,
        )

    if len(failed_tests) == 1:
        primary = failed_tests[0]
        tax = map_taxonomy(config, failure_code=primary.failure_code, sbin=attempt.sbin)
        return primary.test_id, primary.failure_code, "single_failed_test", tax, []

    return (
        "UNKNOWN_PRIMARY_FAILURE",
        None,
        "UNKNOWN_PRIMARY_FAILURE",
        "UNKNOWN.PRIMARY_UNORDERED",
        failed_tests,
    )


def _pareto(
    counts: dict[str, tuple[int, str | None, str | None]],
    n_eligible: int,
    n_fail: int,
    *,
    overlap_allowed: bool,
    selection_rule: str | None = None,
) -> list[ParetoRow]:
    rows: list[ParetoRow] = []
    for key in sorted(counts.keys()):
        n_dies, failure_code, taxonomy_code = counts[key]
        contribution = (n_dies / n_eligible) if n_eligible else 0.0
        share = (n_dies / n_fail) if n_fail else 0.0
        rows.append(
            ParetoRow(
                failure_key=key,
                failure_code=failure_code,
                taxonomy_code=taxonomy_code,
                n_dies=n_dies,
                contribution=contribution,
                share_of_fails=share,
                overlap_allowed=overlap_allowed,
                selection_rule=selection_rule,
            )
        )
    rows.sort(key=lambda r: (-r.n_dies, r.failure_key))
    return rows


def attribute_failures(
    fail_attempts: list[DieAttempt],
    test_results: list[TestResult],
    config: AppConfig,
    *,
    n_eligible: int,
    n_fail: int,
) -> AttributionResult:
    by_attempt: dict[str, list[TestResult]] = defaultdict(list)
    for tr in test_results:
        by_attempt[tr.attempt_id].append(tr)

    primary_rows: list[PrimaryFailureRow] = []
    cofail_rows: list[CofailRow] = []
    events: list[Failure] = []
    primary_counts: dict[str, tuple[int, str | None, str | None]] = {}
    any_counts: dict[str, tuple[int, str | None, str | None]] = {}

    for attempt in sorted(fail_attempts, key=lambda a: a.die_key()):
        failed = [
            t
            for t in by_attempt.get(attempt.attempt_id, [])
            if t.test_pass_fail == "FAIL"
        ]
        failed.sort(key=lambda t: (t.sequence_index is None, t.sequence_index or 0, t.test_id))

        key, code, method, tax, cofail_tests = select_primary(attempt, failed, config)
        family, detail = split_taxonomy(config, tax)
        primary_rows.append(
            PrimaryFailureRow(
                die_id=attempt.die_id,
                lot_id=attempt.lot_id,
                wafer_id=attempt.wafer_id,
                primary_failure_code=code,
                primary_failure_key=key,
                primary_failure_family=family,
                primary_failure_detail=detail,
                selection_method=method,
                taxonomy_code=tax,
            )
        )
        events.append(
            Failure(
                lot_id=attempt.lot_id,
                wafer_id=attempt.wafer_id,
                die_id=attempt.die_id,
                attempt_id=attempt.attempt_id,
                attribution_role="PRIMARY",
                failure_key=key,
                taxonomy_code=tax,
                failure_code=code,
                sbin=attempt.sbin,
                test_id=key if failed else None,
                selection_method=method,
            )
        )
        prev = primary_counts.get(key)
        primary_counts[key] = ((prev[0] + 1) if prev else 1, code, tax)

        any_keys: list[tuple[str, str | None, str]] = []
        if failed:
            for t in failed:
                t_tax = map_taxonomy(config, failure_code=t.failure_code, sbin=attempt.sbin)
                any_keys.append((t.test_id, t.failure_code, t_tax))
        else:
            any_keys.append((key, code, tax))
        seen_any: set[str] = set()
        for a_key, a_code, a_tax in any_keys:
            if a_key in seen_any:
                continue
            seen_any.add(a_key)
            prev_a = any_counts.get(a_key)
            any_counts[a_key] = ((prev_a[0] + 1) if prev_a else 1, a_code, a_tax)

        for t in cofail_tests:
            cofail_rows.append(CofailRow(die_id=attempt.die_id, failure_key=t.test_id))
            events.append(
                Failure(
                    lot_id=attempt.lot_id,
                    wafer_id=attempt.wafer_id,
                    die_id=attempt.die_id,
                    attempt_id=attempt.attempt_id,
                    attribution_role="COFAIL",
                    failure_key=t.test_id,
                    taxonomy_code=map_taxonomy(config, failure_code=t.failure_code, sbin=attempt.sbin),
                    failure_code=t.failure_code,
                    sbin=attempt.sbin,
                    test_id=t.test_id,
                    selection_method="cofail",
                )
            )

    primary_rule = None
    if primary_rows:
        methods = {p.selection_method for p in primary_rows}
        if methods == {"is_first_fail"}:
            primary_rule = "is_first_fail=true"

    return AttributionResult(
        primary_failures=primary_rows,
        primary_pareto=_pareto(
            primary_counts, n_eligible, n_fail, overlap_allowed=False, selection_rule=primary_rule
        ),
        any_fail_pareto=_pareto(any_counts, n_eligible, n_fail, overlap_allowed=True),
        cofail=sorted(cofail_rows, key=lambda c: (c.die_id, c.failure_key)),
        failure_events=events,
    )
