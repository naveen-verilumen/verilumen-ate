"""First-pass wafer-map payload for dashboard visualization.

Does not call FPY per-die copies and does not key records by die_id alone.
"""

from __future__ import annotations

import csv
from collections import defaultdict
from typing import Any

from yield_improvement.api.service import display_lot_name, find_dataset_dir


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"true", "1", "yes"}


def _attempt_number(row: dict[str, str]) -> int:
    raw = (row.get("attempt_number") or "").strip()
    try:
        return int(float(raw))
    except ValueError:
        return 10**9


def _is_first_pass(row: dict[str, str]) -> bool:
    if _truthy(row.get("is_first_attempt")):
        return True
    return _attempt_number(row) == 1


def _coord(row: dict[str, str], key: str) -> int | None:
    raw = (row.get(key) or "").strip()
    if not raw:
        return None
    try:
        return int(float(raw))
    except ValueError:
        return None


def _sequence(row: dict[str, str]) -> int:
    raw = (row.get("sequence_index") or "").strip()
    try:
        return int(float(raw))
    except ValueError:
        return 10**9


def _first_fail_test(rows: list[dict[str, str]]) -> dict[str, str] | None:
    flagged = [row for row in rows if _truthy(row.get("is_first_fail"))]
    if flagged:
        flagged.sort(key=_sequence)
        return flagged[0]
    failed = [
        row
        for row in rows
        if (row.get("test_pass_fail") or row.get("pass_fail") or "").strip().upper() == "FAIL"
    ]
    if not failed:
        return None
    failed.sort(key=_sequence)
    return failed[0]


def build_wafer_map(dataset_id: str) -> dict[str, Any]:
    folder = find_dataset_dir(dataset_id)
    if folder is None:
        raise FileNotFoundError(f"dataset not found: {dataset_id}")
    attempts_path = folder / "die_attempts.csv"
    tests_path = folder / "test_results.csv"
    if not attempts_path.is_file():
        raise FileNotFoundError(f"dataset not found: {dataset_id}")

    attempts_by_die: dict[tuple[str, str, str], list[dict[str, str]]] = defaultdict(list)
    with attempts_path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            lot_id = (row.get("lot_id") or "").strip()
            wafer_id = (row.get("wafer_id") or "").strip()
            die_id = (row.get("die_id") or "").strip()
            if not lot_id or not wafer_id or not die_id:
                continue
            attempts_by_die[(lot_id, wafer_id, die_id)].append(row)

    tests_by_attempt: dict[str, list[dict[str, str]]] = defaultdict(list)
    if tests_path.is_file():
        with tests_path.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                attempt_id = (row.get("attempt_id") or "").strip()
                if attempt_id:
                    tests_by_attempt[attempt_id].append(row)

    params_path = folder / "parametric_measurements.csv"
    params_by_attempt: dict[str, dict[str, float | None]] = defaultdict(dict)
    if params_path.is_file():
        with params_path.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                attempt_id = (row.get("attempt_id") or "").strip()
                pname = (row.get("parameter_name") or row.get("parameter") or "").strip()
                if not attempt_id or not pname:
                    continue
                raw_val = (row.get("measurement") or row.get("value") or "").strip()
                val: float | None = None
                if raw_val:
                    try:
                        val = float(raw_val)
                    except ValueError:
                        val = None
                params_by_attempt[attempt_id][pname] = val

    dies: list[dict[str, Any]] = []
    wafers_by_lot: dict[str, set[str]] = defaultdict(set)
    for (lot_id, wafer_id, die_id), rows in attempts_by_die.items():
        first_rows = [row for row in rows if _is_first_pass(row)]
        if not first_rows:
            continue
        first_rows.sort(key=lambda row: (_attempt_number(row), row.get("timestamp") or ""))
        first = first_rows[0]
        result = (first.get("pass_fail") or first.get("disposition") or "").strip().upper()
        if result not in {"PASS", "FAIL"}:
            continue
        first_att_id = (first.get("attempt_id") or "").strip()
        retest_available = any(not _is_first_pass(row) for row in rows)
        failed_test_id = None
        failure_code = None
        is_first_fail = None
        if result == "FAIL":
            match = _first_fail_test(tests_by_attempt.get(first_att_id, []))
            if match is not None:
                failed_test_id = (match.get("test_id") or "").strip() or None
                failure_code = (match.get("failure_code") or "").strip() or None
                is_first_fail = True
            else:
                failure_code = (first.get("failure_code") or "").strip() or None
                is_first_fail = False
        wafers_by_lot[lot_id].add(wafer_id)
        die_measurements = params_by_attempt.get(first_att_id) or {}
        dies.append(
            {
                "lot_id": lot_id,
                "wafer_id": wafer_id,
                "die_id": die_id,
                "x": _coord(first, "x"),
                "y": _coord(first, "y"),
                "first_pass_result": result,
                "failed_test_id": failed_test_id,
                "failure_code": failure_code,
                "is_first_fail": is_first_fail,
                "retest_available": retest_available,
                "measurements": die_measurements,
            }
        )

    dies.sort(key=lambda row: (row["lot_id"], row["wafer_id"], row["y"] or 0, row["x"] or 0, row["die_id"]))
    lots = [
        {
            "lot_id": lot_id,
            "display_name": display_lot_name(lot_id),
            "wafers": sorted(wafers),
        }
        for lot_id, wafers in sorted(wafers_by_lot.items())
    ]
    n_pass = sum(1 for row in dies if row["first_pass_result"] == "PASS")
    n_fail = sum(1 for row in dies if row["first_pass_result"] == "FAIL")
    return {
        "dataset_id": dataset_id,
        "source": "first_pass_attempts",
        "grain": "lot_id+wafer_id+die_id",
        "n_dies": len(dies),
        "n_pass": n_pass,
        "n_fail": n_fail,
        "lots": lots,
        "dies": dies,
        "production_action": "FORBIDDEN",
        "production_authorized": False,
    }
