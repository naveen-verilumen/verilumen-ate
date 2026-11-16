"""Deterministic wafer-sort FPY. Unique-die grain. Policy from YAML only."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from yield_improvement.config.loader import AppConfig
from yield_improvement.models.canonical import DieAttempt, TestResult
from yield_improvement.models.results import (
    DataQualityIssue,
    DieOutcome,
    Exclusion,
    FpyResult,
)
from yield_improvement.yield_analysis.attribution import attribute_failures
from yield_improvement.yield_analysis.taxonomy import sbin_disposition


def _issue(severity: str, code: str, message: str, **kwargs) -> DataQualityIssue:
    return DataQualityIssue(severity=severity, code=code, message=message, **kwargs)


def resolve_disposition(attempt: DieAttempt, config: AppConfig) -> str | None:
    """Return PASS or FAIL, else None (not a valid first-pass disposition)."""
    policy = config.fpy
    if attempt.abort_flag and policy.abort_is_first_pass_fail:
        return "FAIL"
    if attempt.pass_fail in {"PASS", "FAIL"}:
        return attempt.pass_fail
    mapped = sbin_disposition(config, attempt.sbin)
    if mapped in {"PASS", "FAIL"}:
        return mapped
    return None


def _is_first_attempt_row(attempt: DieAttempt) -> bool:
    if attempt.attempt_number == 1:
        return True
    if attempt.is_first_attempt is True:
        return True
    return False


def _sort_key(attempt: DieAttempt) -> tuple:
    ts = attempt.timestamp or datetime.min
    number = attempt.attempt_number if attempt.attempt_number is not None else 10**9
    return (ts, number, attempt.attempt_id)


def calculate_fpy(
    attempts: list[DieAttempt],
    config: AppConfig,
    test_results: list[TestResult] | None = None,
    extra_issues: list[DataQualityIssue] | None = None,
) -> FpyResult:
    issues: list[DataQualityIssue] = list(extra_issues or [])
    tests = test_results or []

    if not attempts:
        issues.append(_issue("ERROR", "NO_ATTEMPTS", "No die_attempts rows after load"))
        return _invalid_result(config, issues)

    products = {a.product_id for a in attempts}
    steps = {a.step_id for a in attempts}
    if len(products) > 1 or len(steps) > 1:
        issues.append(
            _issue(
                "ERROR",
                "POPULATION_MIX",
                f"Analysis requires one product+step; got products={sorted(products)} steps={sorted(steps)}",
            )
        )
        return _invalid_result(config, issues)

    by_die: dict[tuple[str, str, str], list[DieAttempt]] = defaultdict(list)
    attempt_ids: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    for row in attempts:
        if row.record_status == "REJECT":
            continue
        key = row.die_key()
        by_die[key].append(row)
        attempt_ids[row.attempt_id].append(key)

    ambiguous: set[tuple[str, str, str]] = set()
    for key, rows in by_die.items():
        seen_attempts: dict[str, int] = defaultdict(int)
        for row in rows:
            seen_attempts[row.attempt_id] += 1
        if any(count > 1 for count in seen_attempts.values()):
            ambiguous.add(key)
            issues.append(
                _issue(
                    "ERROR",
                    "AMBIGUOUS_DUPLICATE",
                    "Duplicate die/attempt_id — die excluded",
                    lot_id=key[0],
                    wafer_id=key[1],
                    die_id=key[2],
                    attempt_id=rows[0].attempt_id,
                )
            )

    excluded_classes = set(config.fpy.excluded_part_classes)
    treat_as = config.fpy.part_class_missing.treat_as
    assume_flag_name = config.fpy.part_class_missing.flag

    eligible: list[DieOutcome] = []
    exclusions: list[Exclusion] = []
    assumed: list[str] = []
    first_pass_attempts: dict[tuple[str, str, str], DieAttempt] = {}

    for key in sorted(by_die.keys()):
        lot_id, wafer_id, die_id = key
        rows = sorted(by_die[key], key=_sort_key)

        if not lot_id or not wafer_id or not die_id:
            exclusions.append(Exclusion(die_id=die_id or "", lot_id=lot_id, wafer_id=wafer_id, reason="MISSING_IDENTITY"))
            continue

        if key in ambiguous:
            exclusions.append(
                Exclusion(die_id=die_id, lot_id=lot_id, wafer_id=wafer_id, reason="AMBIGUOUS_DUPLICATE")
            )
            continue

        representative = rows[0]
        part_class = representative.part_class
        assumed_prod = False
        if part_class is None:
            part_class = treat_as
            assumed_prod = True
            assumed.append(die_id)
            issues.append(
                _issue(
                    "ASSUMPTION",
                    assume_flag_name,
                    f"Missing part_class treated as {treat_as}",
                    lot_id=lot_id,
                    wafer_id=wafer_id,
                    die_id=die_id,
                    field="part_class",
                )
            )
        elif part_class not in {
            "PRODUCTION",
            "ENGINEERING",
            "CALIBRATION",
            "QA_SAMPLE",
            "REWORK",
            "UNKNOWN",
        }:
            issues.append(
                _issue(
                    "WARNING",
                    "UNKNOWN_PART_CLASS",
                    f"Unexpected part_class {part_class}",
                    die_id=die_id,
                    field="part_class",
                )
            )

        if part_class in excluded_classes:
            exclusions.append(
                Exclusion(die_id=die_id, lot_id=lot_id, wafer_id=wafer_id, reason=part_class)
            )
            continue

        if any(r.is_rework is True for r in rows):
            exclusions.append(Exclusion(die_id=die_id, lot_id=lot_id, wafer_id=wafer_id, reason="REWORK"))
            continue

        first_rows = [r for r in rows if _is_first_attempt_row(r)]
        if not first_rows:
            exclusions.append(
                Exclusion(die_id=die_id, lot_id=lot_id, wafer_id=wafer_id, reason="RETEST_ONLY")
            )
            continue

        first_rows = sorted(first_rows, key=_sort_key)
        first = first_rows[0]
        if first.timestamp is None:
            exclusions.append(
                Exclusion(die_id=die_id, lot_id=lot_id, wafer_id=wafer_id, reason="MISSING_TIMESTAMP")
            )
            continue

        disposition = resolve_disposition(first, config)
        if disposition is None:
            exclusions.append(
                Exclusion(die_id=die_id, lot_id=lot_id, wafer_id=wafer_id, reason="MISSING_DISPOSITION")
            )
            continue

        last_with_disp = first
        for row in rows:
            disp = resolve_disposition(row, config)
            if disp is not None:
                last_with_disp = row
        final_disp = resolve_disposition(last_with_disp, config)
        retested = any((r.is_retest is True) or (r.attempt_number is not None and r.attempt_number >= 2) for r in rows)

        first_pass_attempts[key] = first
        eligible.append(
            DieOutcome(
                lot_id=lot_id,
                wafer_id=wafer_id,
                die_id=die_id,
                first_pass_disposition=disposition,
                final_disposition=final_disp,
                fpy_counts_as=disposition,
                attempt_id=first.attempt_id,
                part_class=part_class,
                part_class_assumed_production=assumed_prod,
                abort_flag=first.abort_flag,
                retested=retested,
            )
        )

    n_eligible = len(eligible)
    n_pass = sum(1 for d in eligible if d.first_pass_disposition == "PASS")
    n_fail = sum(1 for d in eligible if d.first_pass_disposition == "FAIL")
    invariant_ok = n_eligible == n_pass + n_fail
    if not invariant_ok:
        issues.append(
            _issue(
                "ERROR",
                "FPY_INVARIANT",
                f"n_eligible={n_eligible} != pass+fail={n_pass + n_fail}",
            )
        )

    fpy = (n_pass / n_eligible) if n_eligible else None
    fpy_loss = (n_fail / n_eligible) if n_eligible else None
    n_final_pass = sum(1 for d in eligible if d.final_disposition == "PASS")
    final_yield = (n_final_pass / n_eligible) if n_eligible else None
    n_retested = sum(1 for d in eligible if d.retested)
    retest_rate = (n_retested / n_eligible) if n_eligible else None
    recovered = sum(
        1
        for d in eligible
        if d.first_pass_disposition == "FAIL" and d.final_disposition == "PASS"
    )
    retest_recovery = (recovered / n_fail) if n_fail else 0.0

    fail_attempts = [
        first_pass_attempts[d.lot_id, d.wafer_id, d.die_id]
        for d in eligible
        if d.first_pass_disposition == "FAIL"
    ]
    attribution = attribute_failures(fail_attempts, tests, config, n_eligible=n_eligible, n_fail=n_fail)

    per_die = []
    primary_by_physical_die = {
        (p.lot_id, p.wafer_id, p.die_id): p for p in attribution.primary_failures
    }
    for d in eligible:
        extra = primary_by_physical_die.get((d.lot_id, d.wafer_id, d.die_id))
        per_die.append(
            d.model_copy(
                update={
                    "primary_failure_key": extra.primary_failure_key if extra else None,
                    "primary_failure_code": extra.primary_failure_code if extra else None,
                    "primary_failure_family": extra.primary_failure_family if extra else None,
                    "primary_failure_detail": extra.primary_failure_detail if extra else None,
                    "selection_method": extra.selection_method if extra else None,
                }
            )
        )

    errors = [i for i in issues if i.severity == "ERROR"]
    warnings = [i for i in issues if i.severity == "WARNING"]
    assumptions = [i for i in issues if i.severity == "ASSUMPTION"]
    status = "INVALID" if any(i.code in {"POPULATION_MIX", "FPY_INVARIANT", "NO_ATTEMPTS"} for i in errors) else "OK"
    if n_eligible == 0 and any(i.code == "NO_ATTEMPTS" for i in errors):
        status = "INVALID"

    return FpyResult(
        status=status,
        fpy_policy_version=config.fpy.fpy_policy_version,
        abort_policy=config.fpy.abort_policy,
        eligible_die_count=n_eligible,
        first_pass_pass_count=n_pass,
        first_pass_fail_count=n_fail,
        excluded_count=len(exclusions),
        fpy=fpy,
        fpy_loss=fpy_loss,
        final_yield=final_yield,
        retest_rate_of_eligible=retest_rate,
        n_retested=n_retested,
        retest_recovery=retest_recovery if n_fail else (0.0 if n_eligible else None),
        escape_rate=None,
        escape_status="unavailable",
        invariant_ok=invariant_ok,
        part_class_assumed_production=bool(assumed),
        assumed_production_dies=sorted(assumed),
        exclusions=sorted(exclusions, key=lambda e: (e.lot_id, e.wafer_id, e.die_id, e.reason)),
        per_die=per_die,
        primary_failures=attribution.primary_failures,
        primary_fail_pareto=attribution.primary_pareto,
        any_fail_pareto=attribution.any_fail_pareto,
        cofail=attribution.cofail,
        assumptions=assumptions,
        data_quality_flags=issues,
        errors=errors,
        warnings=warnings,
    )


def _invalid_result(config: AppConfig, issues: list[DataQualityIssue]) -> FpyResult:
    errors = [i for i in issues if i.severity == "ERROR"]
    return FpyResult(
        status="INVALID",
        fpy_policy_version=config.fpy.fpy_policy_version,
        abort_policy=config.fpy.abort_policy,
        eligible_die_count=0,
        first_pass_pass_count=0,
        first_pass_fail_count=0,
        excluded_count=0,
        fpy=None,
        fpy_loss=None,
        invariant_ok=False,
        data_quality_flags=issues,
        errors=errors,
        warnings=[i for i in issues if i.severity == "WARNING"],
        assumptions=[i for i in issues if i.severity == "ASSUMPTION"],
    )
