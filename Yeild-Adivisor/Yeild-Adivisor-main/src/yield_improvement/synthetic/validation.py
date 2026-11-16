"""Validate generated tables against canonical schema, integrity, leakage, and scenario sanity."""

from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

import pandas as pd

from yield_improvement.config.loader import AppConfig
from yield_improvement.ingestion.loader import parse_die_attempts, parse_test_results
from yield_improvement.models.canonical import Equipment, Lot, ParametricMeasurement, Part, Wafer
from yield_improvement.synthetic.baseline import DieState, Profile
from yield_improvement.synthetic.config import SyntheticConfig
from yield_improvement.synthetic.ground_truth import AGENT_MANIFEST_FORBIDDEN
from yield_improvement.synthetic.scenarios import InjectionResult
from yield_improvement.utils.parse import as_optional_bool, as_optional_datetime, as_optional_float, as_optional_int, as_optional_str
from yield_improvement.validation.quality import collect_quality_issues


class GeneratorValidationError(ValueError):
    """Generated data is invalid. Never silently repaired."""


def _issue(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def _first_pass(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [r for r in rows if int(r["attempt_number"]) == 1]


def _fail_rate(rows: list[dict[str, Any]]) -> float:
    if not rows:
        return 0.0
    return sum(1 for r in rows if r["pass_fail"] == "FAIL") / len(rows)


def _mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def validate_canonical_tables(
    tables: dict[str, list[dict[str, Any]]],
    app_config: AppConfig,
) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    da_df = pd.DataFrame(tables["die_attempts"])
    tr_df = pd.DataFrame(tables["test_results"])
    attempts, da_issues = parse_die_attempts(da_df, app_config, source="synthetic")
    tests, tr_issues = parse_test_results(tr_df, app_config, source="synthetic")
    for item in [*da_issues, *tr_issues]:
        if item.severity == "ERROR":
            issues.append(_issue(item.code, item.message))
    issues.extend(_issue(i.code, i.message) for i in collect_quality_issues(attempts, tests, app_config) if i.severity == "ERROR")

    for row in tables["lots"]:
        try:
            Lot(
                lot_id=str(row["lot_id"]),
                product_id=str(row["product_id"]),
                step_id=str(row["step_id"]),
                start_ts=as_optional_datetime(row.get("start_ts")),
                quantity_declared=as_optional_int(row.get("quantity_declared")),
                hold_flag=as_optional_bool(row.get("hold_flag")),
            )
        except Exception as exc:  # noqa: BLE001
            issues.append(_issue("LOT_SCHEMA", str(exc)))
    for row in tables["wafers"]:
        try:
            Wafer(
                lot_id=str(row["lot_id"]),
                wafer_id=str(row["wafer_id"]),
                slot=as_optional_int(row.get("slot")),
                process_tool_id=as_optional_str(row.get("process_tool_id")),
                process_chamber_id=as_optional_str(row.get("process_chamber_id")),
                start_ts=as_optional_datetime(row.get("start_ts")),
            )
        except Exception as exc:  # noqa: BLE001
            issues.append(_issue("WAFER_SCHEMA", str(exc)))
    for row in tables["parts"]:
        try:
            Part(
                lot_id=str(row["lot_id"]),
                wafer_id=str(row["wafer_id"]),
                die_id=str(row["die_id"]),
                product_id=str(row["product_id"]),
                part_class=as_optional_str(row.get("part_class")),
                x=as_optional_float(row.get("x")),
                y=as_optional_float(row.get("y")),
                site=as_optional_int(row.get("site")),
                is_rework=as_optional_bool(row.get("is_rework")),
                is_engineering=as_optional_bool(row.get("is_engineering")),
                is_calibration=as_optional_bool(row.get("is_calibration")),
            )
        except Exception as exc:  # noqa: BLE001
            issues.append(_issue("PART_SCHEMA", str(exc)))
    for row in tables["equipment"]:
        try:
            Equipment(
                equipment_id=str(row["equipment_id"]),
                equipment_type=str(row["equipment_type"]),
                parent_equipment_id=as_optional_str(row.get("parent_equipment_id")),
                vendor=as_optional_str(row.get("vendor")),
                model=as_optional_str(row.get("model")),
            )
        except Exception as exc:  # noqa: BLE001
            issues.append(_issue("EQUIPMENT_SCHEMA", str(exc)))
    for row in tables["parametric_measurements"]:
        try:
            ParametricMeasurement(
                attempt_id=str(row["attempt_id"]),
                parameter_name=str(row["parameter_name"]),
                condition_id=str(row.get("condition_id") or "NONE"),
                measurement=float(row["measurement"]),
                lower_limit=as_optional_float(row.get("lower_limit")),
                upper_limit=as_optional_float(row.get("upper_limit")),
                unit=as_optional_str(row.get("unit")),
                pass_fail=as_optional_str(row.get("pass_fail")),
                temperature_c=as_optional_float(row.get("temperature_c")),
                voltage_v=as_optional_float(row.get("voltage_v")),
            )
        except Exception as exc:  # noqa: BLE001
            issues.append(_issue("PARAMETRIC_SCHEMA", str(exc)))
            break
    return issues


def validate_integrity(
    tables: dict[str, list[dict[str, Any]]],
    profile: Profile,
) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    attempts = tables["die_attempts"]
    lot_ids = {r["lot_id"] for r in tables["lots"]}
    wafer_keys = {(r["lot_id"], r["wafer_id"]) for r in tables["wafers"]}
    part_keys = {(r["lot_id"], r["wafer_id"], r["die_id"]) for r in tables["parts"]}
    attempt_ids = [r["attempt_id"] for r in attempts]
    if len(attempt_ids) != len(set(attempt_ids)):
        issues.append(_issue("UNIQUE_ID", "duplicate attempt_id"))
    if len(part_keys) != len(tables["parts"]):
        issues.append(_issue("UNIQUE_ID", "duplicate part identity"))

    for row in attempts:
        if row["lot_id"] not in lot_ids:
            issues.append(_issue("HIERARCHY", f"lot {row['lot_id']} missing from lots"))
            break
        if (row["lot_id"], row["wafer_id"]) not in wafer_keys:
            issues.append(_issue("HIERARCHY", f"wafer {row['lot_id']}/{row['wafer_id']} missing"))
            break
        if (row["lot_id"], row["wafer_id"], row["die_id"]) not in part_keys:
            issues.append(_issue("HIERARCHY", f"part missing for {row['die_id']}"))
            break
        if row["pass_fail"] not in {"PASS", "FAIL"}:
            issues.append(_issue("DISPOSITION", f"invalid pass_fail {row['pass_fail']}"))
            break
        x, y = float(row["x"]), float(row["y"])
        if math.hypot(x, y) > profile.wafer_radius + 1e-6:
            issues.append(_issue("COORDINATE", f"die {row['die_id']} outside wafer radius"))
            break

    by_die: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in attempts:
        by_die[(row["lot_id"], row["wafer_id"], row["die_id"])].append(row)
    for key, group in by_die.items():
        ordered = sorted(group, key=lambda r: int(r["attempt_number"]))
        for index, row in enumerate(ordered, start=1):
            if int(row["attempt_number"]) != index:
                issues.append(_issue("ATTEMPT_ORDER", f"attempt_number gap for {key}"))
                break
            if index == 1 and (row["is_first_attempt"] not in {True, "true"}):
                issues.append(_issue("ATTEMPT_ORDER", f"first attempt flag {key}"))
                break
            if index > 1 and (row["is_retest"] not in {True, "true"}):
                issues.append(_issue("ATTEMPT_ORDER", f"retest flag {key}"))
                break

    attempt_set = set(attempt_ids)
    for row in tables["test_results"]:
        if row["attempt_id"] not in attempt_set:
            issues.append(_issue("TEST_RESULT", f"orphan test_results {row['attempt_id']}"))
            break
        if row["test_pass_fail"] not in {"PASS", "FAIL", "NOT_EXECUTED", "INVALID"}:
            issues.append(_issue("TEST_RESULT", f"bad test_pass_fail {row['test_pass_fail']}"))
            break

    for row in tables["parametric_measurements"]:
        if row["attempt_id"] not in attempt_set:
            issues.append(_issue("PARAMETRIC", f"orphan parametric {row['attempt_id']}"))
            break
        measurement = float(row["measurement"])
        upper = row.get("upper_limit")
        lower = row.get("lower_limit")
        expected = "PASS"
        if upper not in (None, "") and measurement > float(upper):
            expected = "FAIL"
        if lower not in (None, "") and measurement < float(lower):
            expected = "FAIL"
        if row["pass_fail"] != expected:
            issues.append(
                _issue(
                    "PARAMETRIC",
                    f"{row['parameter_name']} pass_fail {row['pass_fail']} != {expected} for {measurement}",
                )
            )
            break
    return issues


def _json_keys(payload: Any) -> set[str]:
    keys: set[str] = set()
    if isinstance(payload, dict):
        for key, value in payload.items():
            keys.add(str(key))
            keys |= _json_keys(value)
    elif isinstance(payload, list):
        for item in payload:
            keys |= _json_keys(item)
    return keys


def forbidden_keys_present(keys: set[str]) -> list[str]:
    forbidden = set(AGENT_MANIFEST_FORBIDDEN)
    return sorted(k for k in keys if k in forbidden)


def assert_no_ground_truth_leakage(agent_dir: Path) -> None:
    hits: list[str] = []
    for path in sorted(agent_dir.rglob("*")):
        if not path.is_file():
            continue
        if path.name.lower().startswith("ground_truth"):
            hits.append(f"{path.name}: ground-truth filename in agent-visible tree")
        if path.suffix.lower() == ".csv":
            header = path.read_text(encoding="utf-8").splitlines()[:1]
            if header:
                cols = {c.strip() for c in header[0].split(",")}
                leaked = forbidden_keys_present(cols)
                if leaked:
                    hits.append(f"{path.name} columns {leaked}")
        elif path.suffix.lower() == ".json":
            payload = json.loads(path.read_text(encoding="utf-8"))
            leaked = forbidden_keys_present(_json_keys(payload))
            if leaked:
                hits.append(f"{path.name} keys {leaked}")
    if hits:
        raise GeneratorValidationError("Ground-truth leakage: " + "; ".join(hits))


def scan_tables_for_leakage(tables: dict[str, list[dict[str, Any]]], manifest: dict[str, Any]) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    keys = set(manifest)
    for name, rows in tables.items():
        if rows:
            keys |= set(rows[0].keys())
    leaked = forbidden_keys_present(keys)
    if leaked:
        issues.append(_issue("GROUND_TRUTH_LEAK", f"forbidden fields: {leaked}"))
    return issues


def run_scenario_sanity(
    scenario_id: str,
    tables: dict[str, list[dict[str, Any]]],
    injection: InjectionResult,
    cfg: SyntheticConfig,
) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    delta = cfg.sanity.min_rate_delta
    first = _first_pass(tables["die_attempts"])
    overall = _fail_rate(first)
    params = injection.injected_parameters

    def rate(pred) -> float:
        subset = [r for r in first if pred(r)]
        return _fail_rate(subset)

    def radius(row: dict[str, Any]) -> float:
        return math.hypot(float(row["x"]), float(row["y"]))

    if scenario_id in {"S02", "S15"}:
        thr = float(params["radius_threshold"])
        if rate(lambda r: radius(r) >= thr) - rate(lambda r: radius(r) < thr) < delta:
            issues.append(_issue("SANITY_S02", "edge failure rate not elevated vs interior"))
    if scenario_id == "S03":
        thr = float(params["radius_threshold"])
        if rate(lambda r: radius(r) <= thr) - rate(lambda r: radius(r) > thr) < delta:
            issues.append(_issue("SANITY_S03", "center failure rate not elevated vs outer"))
    if scenario_id == "S04":
        inner, outer = float(params["inner"]), float(params["outer"])
        ring = rate(lambda r: inner <= radius(r) <= outer)
        other = rate(lambda r: radius(r) < inner or radius(r) > outer)
        if ring - other < delta:
            issues.append(_issue("SANITY_S04", "ring region not elevated"))
    if scenario_id == "S05":
        tester = params["affected_tester"]
        if rate(lambda r: r["tester_id"] == tester) - rate(lambda r: r["tester_id"] != tester) < delta:
            issues.append(_issue("SANITY_S05", "affected tester not different from control"))
    if scenario_id in {"S06", "S15"}:
        lots = sorted({r["lot_id"] for r in first})
        early = [r for r in first if r["lot_id"] in lots[: max(1, len(lots) // 3)]]
        late = [r for r in first if r["lot_id"] in lots[-max(1, len(lots) // 3) :]]
        need = delta / 2 if scenario_id == "S15" else delta
        if _fail_rate(late) - _fail_rate(early) < need:
            issues.append(_issue("SANITY_S06", "later lots not higher failure rate than early lots"))
    if scenario_id == "S07":
        hot = float(params["hot_threshold_c"])
        if rate(lambda r: float(r["temperature_c"]) >= hot) - rate(lambda r: float(r["temperature_c"]) < hot) < delta:
            issues.append(_issue("SANITY_S07", "hot temperature rate not elevated"))
    if scenario_id == "S08":
        bad = set(params["affected_lots"])
        param_rows = [p for p in tables["parametric_measurements"] if p["parameter_name"] == params["parameter"]]
        aid_lot = {r["attempt_id"]: r["lot_id"] for r in first}
        affected_m = [float(p["measurement"]) for p in param_rows if aid_lot.get(p["attempt_id"]) in bad]
        control_m = [float(p["measurement"]) for p in param_rows if aid_lot.get(p["attempt_id"]) not in bad]
        if _mean(affected_m) - _mean(control_m) < float(params["extra_mean"]) / 3:
            issues.append(_issue("SANITY_S08", "parameter mean did not shift on affected lots"))
    if scenario_id == "S09":
        limit = float(params["production_upper_limit"])
        lo = float(params["near_limit_lo"]) * limit
        hi = float(params["near_limit_hi"]) * limit
        param_rows = [p for p in tables["parametric_measurements"] if p["parameter_name"] == params["parameter"]]
        frac = sum(1 for p in param_rows if lo <= float(p["measurement"]) <= hi) / max(1, len(param_rows))
        if frac < 0.95:
            issues.append(_issue("SANITY_S09", "measurements not concentrated near limit"))
        if any(float(p["upper_limit"]) != limit for p in param_rows):
            issues.append(_issue("SANITY_S09", "production upper_limit was modified"))
        if "tight_limit" in (tables["die_attempts"][0].keys() if tables["die_attempts"] else []):
            issues.append(_issue("SANITY_S09", "tight_limit leaked to die_attempts"))
    if scenario_id == "S10":
        card = params["affected_probe_card"]
        if rate(lambda r: r["probe_card_id"] == card) - rate(lambda r: r["probe_card_id"] != card) < delta:
            issues.append(_issue("SANITY_S10", "affected probe card not elevated"))
    if scenario_id in {"S11", "S14"}:
        by_attempt: dict[str, dict[str, str]] = defaultdict(dict)
        seq: dict[str, dict[str, int]] = defaultdict(dict)
        for row in tables["test_results"]:
            by_attempt[row["attempt_id"]][row["test_id"]] = row["test_pass_fail"]
            if row.get("sequence_index") not in (None, ""):
                seq[row["attempt_id"]][row["test_id"]] = int(row["sequence_index"])
        first_ids = {r["attempt_id"] for r in first}
        cond_num = cond_den = base_num = base_den = 0
        for aid, tests in by_attempt.items():
            if aid not in first_ids:
                continue
            iddq = tests.get("T_IDDQ")
            func = tests.get("T_FUNC")
            if iddq == "FAIL":
                precedes = seq[aid].get("T_IDDQ", 0) < seq[aid].get("T_FUNC", 99)
                if scenario_id == "S11" and not precedes:
                    continue
                cond_den += 1
                if func == "FAIL":
                    cond_num += 1
            elif iddq == "PASS":
                base_den += 1
                if func == "FAIL":
                    base_num += 1
        cond = cond_num / cond_den if cond_den else 0.0
        base = base_num / base_den if base_den else 0.0
        if cond - base < delta / 2:
            issues.append(_issue(f"SANITY_{scenario_id}", "failure-mode association not visible"))
    if scenario_id == "S12":
        bad = set(params["affected_lots"])
        if rate(lambda r: r["lot_id"] in bad) - rate(lambda r: r["lot_id"] not in bad) < delta:
            issues.append(_issue("SANITY_S12", "bad lots not elevated"))
    if scenario_id == "S13":
        bad = set(params["affected_wafers"])
        if rate(lambda r: f"{r['lot_id']}/{r['wafer_id']}" in bad) - rate(
            lambda r: f"{r['lot_id']}/{r['wafer_id']}" not in bad
        ) < delta:
            issues.append(_issue("SANITY_S13", "bad wafers not elevated"))
    if scenario_id in {"S01", "S16"}:
        testers = {r["tester_id"] for r in first}
        spreads = [_fail_rate([r for r in first if r["tester_id"] == t]) for t in testers]
        if spreads and max(spreads) - min(spreads) > 0.28:
            issues.append(_issue("SANITY_NO_EQUIP", "equipment split too large for no-equipment scenario"))
        med = sorted(radius(r) for r in first)[len(first) // 2]
        spatial = abs(rate(lambda r: radius(r) >= med) - rate(lambda r: radius(r) < med))
        if spatial > 0.22:
            issues.append(_issue("SANITY_NO_SPATIAL", "spatial split too large for non-spatial scenario"))
    if scenario_id == "S16" and params:
        issues.append(_issue("SANITY_S16", "S16 must not inject systematic parameters"))
    if scenario_id == "S01" and overall <= 0:
        issues.append(_issue("SANITY_S01", "S01 produced no failures"))
    return issues


def run_generator_validation(
    *,
    tables: dict[str, list[dict[str, Any]]],
    dies: list[DieState],
    cfg: SyntheticConfig,
    profile: Profile,
    injection: InjectionResult,
    scenario_id: str,
    app_config: AppConfig,
    agent_manifest: dict[str, Any],
) -> dict[str, Any]:
    errors: list[dict[str, str]] = []
    errors.extend(validate_canonical_tables(tables, app_config))
    errors.extend(validate_integrity(tables, profile))
    errors.extend(scan_tables_for_leakage(tables, agent_manifest))
    sanity = run_scenario_sanity(scenario_id, tables, injection, cfg)
    n_first = len(_first_pass(tables["die_attempts"]))
    fpy = 1.0 - _fail_rate(_first_pass(tables["die_attempts"])) if n_first else None
    baseline_ok = True
    if scenario_id == "S16" and fpy is not None:
        if not (cfg.baseline.expected_fpy_min - 0.08 <= fpy <= cfg.baseline.expected_fpy_max + 0.05):
            sanity.append(_issue("BASELINE_FPY", f"S16 FPY {fpy:.3f} outside expected band"))
            baseline_ok = False
    status = "PASSED" if not errors and not sanity else "FAILED"
    return {
        "status": status,
        "n_dies": len(dies),
        "first_pass_fpy": fpy,
        "canonical_errors": errors,
        "sanity_issues": sanity,
        "sanity_status": "PASSED" if not sanity else "FAILED",
        "baseline_fpy_ok": baseline_ok,
        "leakage": "none" if not any(i["code"] == "GROUND_TRUTH_LEAK" for i in errors) else "detected",
    }
