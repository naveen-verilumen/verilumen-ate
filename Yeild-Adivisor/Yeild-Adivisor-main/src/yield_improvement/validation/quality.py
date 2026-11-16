"""Structured data-quality helpers."""

from __future__ import annotations

from collections import defaultdict

from yield_improvement.config.loader import AppConfig
from yield_improvement.models.canonical import DieAttempt, TestResult
from yield_improvement.models.results import DataQualityIssue
from yield_improvement.yield_analysis.taxonomy import sbin_disposition


def _issue(severity: str, code: str, message: str, **kwargs) -> DataQualityIssue:
    return DataQualityIssue(severity=severity, code=code, message=message, **kwargs)


def collect_quality_issues(
    attempts: list[DieAttempt],
    test_results: list[TestResult],
    config: AppConfig,
) -> list[DataQualityIssue]:
    issues: list[DataQualityIssue] = []
    attempt_ids = {a.attempt_id for a in attempts}

    testers = [a.tester_id for a in attempts]
    if testers and all(t is None for t in testers):
        issues.append(
            _issue("UNAVAILABLE", "EQUIPMENT_UNAVAILABLE", "tester_id missing on all attempts")
        )

    xy = [(a.x, a.y) for a in attempts]
    if xy and all(x is None or y is None for x, y in xy):
        issues.append(
            _issue("UNAVAILABLE", "SPATIAL_UNAVAILABLE", "x/y missing; spatial analysis unavailable")
        )

    unknown_bins: set[int] = set()
    for a in attempts:
        if a.sbin is not None and sbin_disposition(config, a.sbin) is None:
            unknown_bins.add(a.sbin)
            issues.append(
                _issue(
                    "WARNING",
                    "UNMAPPED_BIN",
                    f"sbin {a.sbin} is not in bin_map",
                    die_id=a.die_id,
                    field="sbin",
                    attempt_id=a.attempt_id,
                )
            )

    mapped_codes = set(config.bin_map.failure_code_map)
    for a in attempts:
        if a.failure_code and a.failure_code not in mapped_codes:
            issues.append(
                _issue(
                    "WARNING",
                    "UNMAPPED_FAILURE_CODE",
                    f"failure_code {a.failure_code!r} is not in failure_code_map",
                    die_id=a.die_id,
                    field="failure_code",
                    attempt_id=a.attempt_id,
                )
            )

    orphans: set[str] = set()
    for tr in test_results:
        if tr.attempt_id not in attempt_ids and tr.attempt_id not in orphans:
            orphans.add(tr.attempt_id)
            issues.append(
                _issue(
                    "ERROR",
                    "REFERENTIAL_INTEGRITY",
                    f"test_results attempt_id {tr.attempt_id} not in die_attempts",
                    attempt_id=tr.attempt_id,
                )
            )

    fail_attempts = [a for a in attempts if a.pass_fail == "FAIL" or a.abort_flag]
    tests_by_attempt: dict[str, list[TestResult]] = defaultdict(list)
    for tr in test_results:
        tests_by_attempt[tr.attempt_id].append(tr)
    for a in fail_attempts:
        failed = [t for t in tests_by_attempt.get(a.attempt_id, []) if t.test_pass_fail == "FAIL"]
        if len(failed) >= 2 and all(t.sequence_index is None for t in failed) and not any(
            t.is_first_fail is True for t in failed
        ):
            issues.append(
                _issue(
                    "WARNING",
                    "MISSING_SEQUENCE",
                    "Multiple fails without is_first_fail or sequence_index",
                    die_id=a.die_id,
                    attempt_id=a.attempt_id,
                )
            )

    return issues
