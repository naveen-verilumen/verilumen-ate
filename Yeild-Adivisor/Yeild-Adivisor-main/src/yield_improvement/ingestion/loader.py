"""Normalize CSV/Parquet rows into canonical DieAttempt / TestResult objects."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from yield_improvement.config.loader import AppConfig
from yield_improvement.models.canonical import DieAttempt, ParametricMeasurement, TestResult
from yield_improvement.models.results import DataQualityIssue
from yield_improvement.utils.errors import LoadError
from yield_improvement.utils.parse import (
    as_optional_bool,
    as_optional_datetime,
    as_optional_float,
    as_optional_int,
    as_optional_str,
    is_missing,
)

DIE_ATTEMPT_REQUIRED = (
    "lot_id",
    "wafer_id",
    "die_id",
    "product_id",
    "step_id",
    "attempt_id",
)

TEST_RESULT_REQUIRED = ("attempt_id", "test_id", "test_pass_fail")
PARAMETRIC_REQUIRED = ("attempt_id", "parameter_name", "measurement")


class LoadResult:
    def __init__(
        self,
        *,
        attempts: list[DieAttempt],
        test_results: list[TestResult],
        issues: list[DataQualityIssue],
        source: str,
        parametric: list[ParametricMeasurement] | None = None,
    ) -> None:
        self.attempts = attempts
        self.test_results = test_results
        self.parametric = parametric or []
        self.issues = issues
        self.source = source


def _dataframe_from_path(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise LoadError(f"File not found: {path}")
    suffix = path.suffix.lower()
    try:
        if suffix == ".csv":
            return pd.read_csv(path, dtype=str, keep_default_na=False, na_values=[])
        if suffix in {".parquet", ".pq"}:
            return pd.read_parquet(path)
        raise LoadError(f"Unsupported file type {suffix} for {path}")
    except LoadError:
        raise
    except Exception as exc:  # noqa: BLE001 — convert I/O/parse failures
        raise LoadError(f"Cannot read {path}: {exc}") from exc


def load_csv(path: Path | str) -> pd.DataFrame:
    return _dataframe_from_path(Path(path))


def load_parquet(path: Path | str) -> pd.DataFrame:
    return _dataframe_from_path(Path(path))


def _forbidden_columns(columns: list[str], config: AppConfig) -> list[str]:
    forbidden = set(config.allowlist.forbidden_columns_on_agent_visible_tables)
    return [c for c in columns if c in forbidden]


def _issue(
    severity: str,
    code: str,
    message: str,
    **kwargs: Any,
) -> DataQualityIssue:
    return DataQualityIssue(severity=severity, code=code, message=message, **kwargs)


def _normalize_sbin(row: dict[str, Any]) -> Any:
    if not is_missing(row.get("sbin")):
        return row.get("sbin")
    return row.get("bin")


def parse_die_attempts(df: pd.DataFrame, config: AppConfig, *, source: str) -> tuple[list[DieAttempt], list[DataQualityIssue]]:
    issues: list[DataQualityIssue] = []
    columns = [str(c) for c in df.columns]
    forbidden = _forbidden_columns(columns, config)
    if forbidden:
        issues.append(
            _issue(
                "ERROR",
                "FORBIDDEN_COLUMN",
                f"Forbidden columns on agent-visible table: {forbidden}",
            )
        )
        return [], issues

    missing_required = [c for c in DIE_ATTEMPT_REQUIRED if c not in columns]
    if missing_required:
        issues.append(
            _issue(
                "ERROR",
                "MISSING_REQUIRED_COLUMNS",
                f"die_attempts missing columns: {missing_required}",
            )
        )
        return [], issues

    attempts: list[DieAttempt] = []
    records = df.to_dict("records")
    for index, raw in enumerate(records):
        row = {str(k): raw[k] for k in raw}
        row_num = index + 2  # header is line 1
        lot_id = as_optional_str(row.get("lot_id"))
        wafer_id = as_optional_str(row.get("wafer_id"))
        die_id = as_optional_str(row.get("die_id"))
        product_id = as_optional_str(row.get("product_id"))
        step_id = as_optional_str(row.get("step_id"))
        attempt_id = as_optional_str(row.get("attempt_id")) or as_optional_str(row.get("test_execution_id"))

        if not all([lot_id, wafer_id, die_id, product_id, step_id, attempt_id]):
            issues.append(
                _issue(
                    "ERROR",
                    "MISSING_IDENTITY",
                    "Row missing required identity/product fields",
                    die_id=die_id,
                    lot_id=lot_id,
                    wafer_id=wafer_id,
                    attempt_id=attempt_id,
                    field="identity",
                )
            )
            continue

        abort_raw = as_optional_bool(row.get("abort_flag"))
        if not is_missing(row.get("abort_flag")) and abort_raw is None:
            issues.append(
                _issue(
                    "ERROR",
                    "INVALID_VALUE",
                    "abort_flag is not a boolean",
                    die_id=die_id,
                    field="abort_flag",
                    attempt_id=attempt_id,
                )
            )
            continue

        is_first = as_optional_bool(row.get("is_first_attempt"))
        is_retest = as_optional_bool(row.get("is_retest"))
        is_rework = as_optional_bool(row.get("is_rework"))
        if is_rework is None:
            is_rework = as_optional_bool(row.get("rework_flag"))
        bool_fields = {
            "is_first_attempt": (is_first, row.get("is_first_attempt")),
            "is_retest": (is_retest, row.get("is_retest")),
            "is_rework": (
                is_rework,
                row.get("is_rework") if not is_missing(row.get("is_rework")) else row.get("rework_flag"),
            ),
        }
        for field_name, (parsed, raw_val) in bool_fields.items():
            if is_missing(raw_val):
                continue
            if parsed is None:
                issues.append(
                    _issue(
                        "ERROR",
                        "INVALID_VALUE",
                        f"{field_name} is not a boolean",
                        die_id=die_id,
                        field=field_name,
                        attempt_id=attempt_id,
                    )
                )

        part_class = as_optional_str(row.get("part_class"))
        if part_class is not None:
            part_class = part_class.upper()

        pass_fail = as_optional_str(row.get("pass_fail"))
        if pass_fail is not None:
            pass_fail = pass_fail.upper()
            if pass_fail not in {"PASS", "FAIL"}:
                issues.append(
                    _issue(
                        "ERROR",
                        "INVALID_VALUE",
                        f"pass_fail {pass_fail!r} is not PASS/FAIL",
                        die_id=die_id,
                        field="pass_fail",
                        attempt_id=attempt_id,
                    )
                )
                pass_fail = None

        timestamp = as_optional_datetime(row.get("timestamp"))
        if is_missing(row.get("timestamp")):
            issues.append(
                _issue(
                    "ERROR",
                    "MISSING_TIMESTAMP",
                    "timestamp missing",
                    die_id=die_id,
                    lot_id=lot_id,
                    wafer_id=wafer_id,
                    attempt_id=attempt_id,
                    field="timestamp",
                )
            )
        elif timestamp is None:
            issues.append(
                _issue(
                    "ERROR",
                    "INVALID_VALUE",
                    "timestamp is not ISO-8601 UTC",
                    die_id=die_id,
                    field="timestamp",
                    attempt_id=attempt_id,
                )
            )

        attempt_number = as_optional_int(row.get("attempt_number"))
        if attempt_number is not None and attempt_number < 1:
            issues.append(
                _issue(
                    "ERROR",
                    "INVALID_VALUE",
                    "attempt_number must be >= 1",
                    die_id=die_id,
                    field="attempt_number",
                    attempt_id=attempt_id,
                )
            )
            attempt_number = None

        sbin = as_optional_int(_normalize_sbin(row))
        hbin = as_optional_int(row.get("hbin"))

        attempts.append(
            DieAttempt(
                attempt_id=attempt_id,
                lot_id=lot_id,
                wafer_id=wafer_id,
                die_id=die_id,
                product_id=product_id,
                step_id=step_id,
                part_class=part_class,
                timestamp=timestamp,
                attempt_number=attempt_number,
                is_first_attempt=is_first,
                is_retest=is_retest,
                is_rework=is_rework,
                abort_flag=bool(abort_raw) if abort_raw is not None else False,
                disposition=as_optional_str(row.get("disposition")),
                pass_fail=pass_fail,
                sbin=sbin,
                hbin=hbin,
                failure_code=as_optional_str(row.get("failure_code")),
                tester_id=as_optional_str(row.get("tester_id")),
                probe_card_id=as_optional_str(row.get("probe_card_id")),
                prober_id=as_optional_str(row.get("prober_id")),
                site=as_optional_int(row.get("site")),
                temperature_c=as_optional_float(row.get("temperature_c")),
                voltage_v=as_optional_float(row.get("voltage_v")),
                record_status=as_optional_str(row.get("record_status")),
                x=as_optional_float(row.get("x")),
                y=as_optional_float(row.get("y")),
                source_row=row_num,
            )
        )
    return attempts, issues


def parse_test_results(df: pd.DataFrame, config: AppConfig, *, source: str) -> tuple[list[TestResult], list[DataQualityIssue]]:
    issues: list[DataQualityIssue] = []
    columns = [str(c) for c in df.columns]
    forbidden = _forbidden_columns(columns, config)
    if forbidden:
        issues.append(
            _issue("ERROR", "FORBIDDEN_COLUMN", f"Forbidden columns: {forbidden}")
        )
        return [], issues
    missing_required = [c for c in TEST_RESULT_REQUIRED if c not in columns]
    if missing_required:
        issues.append(
            _issue("ERROR", "MISSING_REQUIRED_COLUMNS", f"test_results missing columns: {missing_required}")
        )
        return [], issues

    results: list[TestResult] = []
    records = df.to_dict("records")
    for index, raw in enumerate(records):
        row = {str(k): raw[k] for k in raw}
        attempt_id = as_optional_str(row.get("attempt_id"))
        test_id = as_optional_str(row.get("test_id"))
        test_pass_fail = as_optional_str(row.get("test_pass_fail"))
        if test_pass_fail:
            test_pass_fail = test_pass_fail.upper()
        if not attempt_id or not test_id or not test_pass_fail:
            issues.append(
                _issue(
                    "ERROR",
                    "MISSING_REQUIRED_FIELDS",
                    "test_results row missing attempt_id/test_id/test_pass_fail",
                    attempt_id=attempt_id,
                )
            )
            continue
        if test_pass_fail not in {"PASS", "FAIL", "NOT_EXECUTED", "INVALID"}:
            issues.append(
                _issue(
                    "ERROR",
                    "INVALID_VALUE",
                    f"test_pass_fail {test_pass_fail!r} invalid",
                    attempt_id=attempt_id,
                    field="test_pass_fail",
                )
            )
            continue
        is_first_fail = as_optional_bool(row.get("is_first_fail"))
        results.append(
            TestResult(
                attempt_id=attempt_id,
                test_id=test_id,
                test_pass_fail=test_pass_fail,
                sequence_index=as_optional_int(row.get("sequence_index")),
                is_first_fail=is_first_fail,
                failure_code=as_optional_str(row.get("failure_code")),
                source_row=int(index) + 2,
            )
        )
    return results, issues


def load_die_attempts(path: Path | str, config: AppConfig) -> LoadResult:
    frame = _dataframe_from_path(Path(path))
    attempts, issues = parse_die_attempts(frame, config, source=str(path))
    return LoadResult(attempts=attempts, test_results=[], issues=issues, source=str(path))


def load_test_results(path: Path | str, config: AppConfig) -> LoadResult:
    frame = _dataframe_from_path(Path(path))
    results, issues = parse_test_results(frame, config, source=str(path))
    return LoadResult(attempts=[], test_results=results, issues=issues, source=str(path))


def parse_parametric_measurements(
    df: pd.DataFrame, config: AppConfig, *, source: str
) -> tuple[list[ParametricMeasurement], list[DataQualityIssue]]:
    issues: list[DataQualityIssue] = []
    columns = [str(c) for c in df.columns]
    forbidden = _forbidden_columns(columns, config)
    if forbidden:
        issues.append(
            _issue("ERROR", "FORBIDDEN_COLUMN", f"Forbidden columns: {forbidden}")
        )
        return [], issues
    missing_required = [c for c in PARAMETRIC_REQUIRED if c not in columns]
    if missing_required:
        issues.append(
            _issue("ERROR", "MISSING_REQUIRED_COLUMNS", f"parametric missing columns: {missing_required}")
        )
        return [], issues
    rows: list[ParametricMeasurement] = []
    records = df.to_dict("records")
    for raw in records:
        row = {str(k): raw[k] for k in raw}
        attempt_id = as_optional_str(row.get("attempt_id"))
        parameter_name = as_optional_str(row.get("parameter_name"))
        measurement = as_optional_float(row.get("measurement"))
        if not attempt_id or not parameter_name or measurement is None:
            issues.append(
                _issue(
                    "ERROR",
                    "MISSING_REQUIRED_FIELDS",
                    "parametric row missing attempt_id/parameter_name/measurement",
                    attempt_id=attempt_id,
                    field="measurement",
                )
            )
            continue
        pass_fail = as_optional_str(row.get("pass_fail"))
        if pass_fail:
            pass_fail = pass_fail.upper()
        rows.append(
            ParametricMeasurement(
                attempt_id=attempt_id,
                parameter_name=parameter_name,
                condition_id=as_optional_str(row.get("condition_id")) or "NONE",
                measurement=measurement,
                lower_limit=as_optional_float(row.get("lower_limit")),
                upper_limit=as_optional_float(row.get("upper_limit")),
                unit=as_optional_str(row.get("unit")),
                pass_fail=pass_fail,
                temperature_c=as_optional_float(row.get("temperature_c")),
                voltage_v=as_optional_float(row.get("voltage_v")),
            )
        )
    return rows, issues


def load_parametric_measurements(path: Path | str, config: AppConfig) -> LoadResult:
    frame = _dataframe_from_path(Path(path))
    rows, issues = parse_parametric_measurements(frame, config, source=str(path))
    return LoadResult(attempts=[], test_results=[], parametric=rows, issues=issues, source=str(path))
