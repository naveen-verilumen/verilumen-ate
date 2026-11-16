"""Controlled V2 synthetic dataset: 5 lots × 5 wafers × 100 dies. Hidden GT is separate."""

from __future__ import annotations

import csv
import json
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml

from yield_improvement.synthetic.ground_truth import AGENT_MANIFEST_FORBIDDEN
from yield_improvement.utils.paths import repo_root

FORBIDDEN_AGENT_COLUMNS = set(AGENT_MANIFEST_FORBIDDEN)
HIDDEN_GT_DIR = "evaluation/ground_truth/synthetic_v2"

# Pre-sort oxide thickness is a stored measurement. It is not an input to fail_p,
# the fail bit, or parametric limit checks. The side stream is a separate Random.
OXIDE_COLUMN = "pre_sort_oxide_thickness_nm"
OXIDE_UNIT = "nm"
OXIDE_BASELINE_NM = 3.20
OXIDE_EFFECT_SCALE_NM = 8.0
OXIDE_NOISE_SD_NM = 0.05
OXIDE_SIDE_STREAM_SEED = 17_611_001


def _iso(ts: datetime) -> str:
    return ts.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_start(text: str) -> datetime:
    raw = text.replace("Z", "+00:00")
    ts = datetime.fromisoformat(raw)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc)


def clip(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def weighted_choice(rng: random.Random, items: list[str], weights: list[float]) -> str:
    draw = rng.random()
    acc = 0.0
    for item, weight in zip(items, weights, strict=True):
        acc += weight
        if draw <= acc:
            return item
    return items[-1]


def load_v2_config(path: Path | None = None) -> dict[str, Any]:
    cfg_path = path or (repo_root() / "configs" / "synthetic_v2.yaml")
    payload = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("synthetic_v2.yaml must be a mapping")
    return payload


def is_edge(x: int, y: int, nx: int, ny: int) -> bool:
    return x in {1, nx} or y in {1, ny}


def is_center(x: int, y: int, nx: int, ny: int) -> bool:
    cx0 = (nx // 2) - 1
    cy0 = (ny // 2) - 1
    return cx0 <= x <= cx0 + 3 and cy0 <= y <= cy0 + 3


@dataclass
class DieDraw:
    lot_id: str
    wafer_id: str
    die_id: str
    lot_index: int
    wafer_index: int
    x: int
    y: int
    tester_id: str
    probe_card_id: str
    prober_id: str
    temperature_c: float
    voltage_v: float
    timestamp: datetime
    fail_p: float
    pre_sort_oxide_thickness_nm: float = 0.0
    failed: bool = False
    fail_test_ids: list[str] = field(default_factory=list)
    failure_code: str | None = None
    measurements: dict[str, float] = field(default_factory=dict)
    retest_attempts: int = 0
    retest_final_pass: bool = False


def _draw_param(rng: random.Random, spec: dict[str, Any], shift: float = 0.0) -> float:
    mean = float(spec["pass_mean"]) + shift
    sd = float(spec["pass_sd"])
    return rng.gauss(mean, sd)


def _param_fail(value: float, spec: dict[str, Any]) -> bool:
    upper = spec.get("upper_limit")
    lower = spec.get("lower_limit")
    if upper is not None and value > float(upper):
        return True
    if lower is not None and value < float(lower):
        return True
    return False


def oxide_side_rng(stream_seed: int = OXIDE_SIDE_STREAM_SEED) -> random.Random:
    """Random stream for oxide metrology noise. This is not the main generator stream."""
    return random.Random(int(stream_seed))


def oxide_thickness_nm(lot_eff: float, wafer_eff: float, side_rng: random.Random) -> float:
    """Approved pre-sort oxide thickness in nm.

    Inputs are the existing lot and wafer process offsets plus one draw from the
    side stream. Fail probability, the fail bit, limits, and outcomes are not inputs.
    """
    return (
        OXIDE_BASELINE_NM
        + OXIDE_EFFECT_SCALE_NM * float(lot_eff)
        + OXIDE_EFFECT_SCALE_NM * float(wafer_eff)
        + side_rng.gauss(0.0, OXIDE_NOISE_SD_NM)
    )


def build_population(
    cfg: dict[str, Any],
    rng: random.Random,
    *,
    oxide_stream_seed: int = OXIDE_SIDE_STREAM_SEED,
) -> list[DieDraw]:
    nx = int(cfg["wafer_grid_x"])
    ny = int(cfg["wafer_grid_y"])
    n_lots = int(cfg["n_lots"])
    n_wafers = int(cfg["wafers_per_lot"])
    n_dies = int(cfg["dies_per_wafer"])
    if nx * ny != n_dies:
        raise ValueError("dies_per_wafer must equal wafer_grid_x * wafer_grid_y")
    start = _parse_start(cfg["time"]["start"])
    base = cfg["baseline"]
    lot_cfg = cfg["lots"]
    testers = list(cfg["testers"])
    tester_w = [float(x) for x in cfg["tester_weights"]]
    cards = list(cfg["probe_cards"])
    probers = list(cfg["probers"])
    tester_effects = {t: rng.gauss(0.0, float(base["tester_effect_sd"])) for t in testers}
    side_rng = oxide_side_rng(oxide_stream_seed)
    dies: list[DieDraw] = []
    for lot_i in range(n_lots):
        lot_id = f"L{lot_i + 1:03d}"
        hidden = lot_cfg[lot_id]
        lot_start = start + timedelta(days=int(cfg["time"]["days_per_lot"]) * lot_i)
        lot_eff = rng.gauss(0.0, float(base["lot_effect_sd"]))
        for w_i in range(n_wafers):
            wafer_id = f"W{w_i + 1:02d}"
            wafer_start = lot_start + timedelta(hours=int(cfg["time"]["hours_per_wafer"]) * w_i)
            wafer_eff = rng.gauss(0.0, float(base["wafer_effect_sd"]))
            die_n = 0
            for y in range(1, ny + 1):
                for x in range(1, nx + 1):
                    die_n += 1
                    die_id = f"D{die_n:03d}"
                    tester = weighted_choice(rng, testers, tester_w)
                    extra = float(hidden.get("extra_p") or 0.0)
                    if hidden.get("extra_p_edge") and is_edge(x, y, nx, ny):
                        extra += float(hidden["extra_p_edge"])
                    if hidden.get("affected_tester") == tester:
                        extra += float(hidden.get("extra_p_tester") or 0.0)
                    extra += float(hidden.get("extra_p_per_wafer") or 0.0) * w_i
                    die_noise = rng.gauss(0.0, float(base["die_noise_sd"]))
                    fail_p = clip(
                        float(base["p_fail"])
                        + lot_eff
                        + wafer_eff
                        + tester_effects[tester]
                        + extra
                        + die_noise,
                        0.01,
                        0.42,
                    )
                    thickness = round(oxide_thickness_nm(lot_eff, wafer_eff, side_rng), 6)
                    hot = rng.random() < float(base["hot_fraction"])
                    temp = float(base["hot_temperature_c"] if hot else base["temperature_c"])
                    temp += rng.gauss(0.0, float(base["temperature_sd"]))
                    voltage = float(base["voltage_v"]) + rng.gauss(0.0, float(base["voltage_sd"]))
                    ts = wafer_start + timedelta(seconds=int(cfg["time"]["seconds_per_die"]) * (die_n - 1))
                    dies.append(
                        DieDraw(
                            lot_id=lot_id,
                            wafer_id=wafer_id,
                            die_id=die_id,
                            lot_index=lot_i,
                            wafer_index=w_i,
                            x=x,
                            y=y,
                            tester_id=tester,
                            probe_card_id=rng.choice(cards),
                            prober_id=rng.choice(probers),
                            temperature_c=round(temp, 3),
                            voltage_v=round(voltage, 4),
                            timestamp=ts,
                            fail_p=fail_p,
                            pre_sort_oxide_thickness_nm=thickness,
                        )
                    )
    if len(dies) != n_lots * n_wafers * n_dies:
        raise ValueError("die count mismatch")
    return dies


def realize(cfg: dict[str, Any], rng: random.Random, dies: list[DieDraw]) -> None:
    tests = list(cfg["tests"])
    params = cfg["parametric"]
    lot_cfg = cfg["lots"]
    nx = int(cfg["wafer_grid_x"])
    ny = int(cfg["wafer_grid_y"])
    for die in dies:
        hidden = lot_cfg[die.lot_id]
        shifts = {name: 0.0 for name in params}
        if hidden.get("role") == "SPATIAL_EDGE" and is_edge(die.x, die.y, nx, ny):
            shifts["CONTACT_RESISTANCE"] = 0.45
            shifts["IDDQ"] = 6.0
        if hidden.get("role") == "EQUIPMENT" and die.tester_id == hidden.get("affected_tester"):
            shifts["CONTACT_RESISTANCE"] = 0.35
        if hidden.get("role") == "PROCESS_DRIFT":
            shifts["VMIN"] = 0.04 * die.wafer_index
            shifts["IDDQ"] = 3.0 * die.wafer_index
        if hidden.get("role") == "WEAK_MIXED" and is_edge(die.x, die.y, nx, ny):
            shifts["IDDQ"] = 2.0
        for name, spec in params.items():
            die.measurements[name] = _draw_param(rng, spec, shifts[name])
        param_fails = [name for name, spec in params.items() if _param_fail(die.measurements[name], spec)]
        die.failed = rng.random() < die.fail_p
        fail_ids: list[str] = []
        if die.failed:
            if "CONTACT_RESISTANCE" in param_fails or hidden.get("role") in {"SPATIAL_EDGE", "EQUIPMENT"}:
                fail_ids.append("T004")
            if "IDDQ" in param_fails:
                fail_ids.append("T005")
            if "VMIN" in param_fails:
                fail_ids.append("T006")
            if not fail_ids:
                fail_ids.append(rng.choice([t["test_id"] for t in tests]))
            if rng.random() < 0.28:
                extra = rng.choice([t["test_id"] for t in tests])
                if extra not in fail_ids:
                    fail_ids.append(extra)
        elif param_fails:
            die.failed = True
            if "IDDQ" in param_fails:
                fail_ids.append("T005")
            elif "VMIN" in param_fails:
                fail_ids.append("T006")
            elif "CONTACT_RESISTANCE" in param_fails:
                fail_ids.append("T004")
            else:
                fail_ids.append("T008")
        die.fail_test_ids = fail_ids
        if die.failed and not die.fail_test_ids:
            die.fail_test_ids = [tests[0]["test_id"]]
        if die.failed:
            ordered = sorted(
                die.fail_test_ids,
                key=lambda tid: next(t["sequence_index"] for t in tests if t["test_id"] == tid),
            )
            primary = next(t for t in tests if t["test_id"] == ordered[0])
            die.failure_code = primary["failure_code"]
        if die.failed and rng.random() < float(cfg["retest_rate"]):
            die.retest_attempts = 1
            die.retest_final_pass = rng.random() < float(cfg["retest_pass_rate"])
            if (not die.retest_final_pass) and rng.random() < float(cfg["second_retest_rate"]):
                die.retest_attempts = 2
                die.retest_final_pass = rng.random() < float(cfg["retest_pass_rate"])


def _test_rows(cfg: dict[str, Any], die: DieDraw, attempt_id: str, passed: bool) -> list[dict[str, Any]]:
    rows = []
    fail_set = set(die.fail_test_ids) if not passed else set()
    first_fail_seq = 10**9
    if fail_set:
        first_fail_seq = min(
            next(t["sequence_index"] for t in cfg["tests"] if t["test_id"] == tid) for tid in fail_set
        )
    for spec in cfg["tests"]:
        seq = int(spec["sequence_index"])
        if passed:
            status, code, first = "PASS", "", ""
        elif spec["test_id"] in fail_set:
            status, code = "FAIL", spec["failure_code"]
            first = "true" if seq == first_fail_seq else "false"
        elif seq > first_fail_seq:
            status, code, first = "NOT_EXECUTED", "", ""
        else:
            status, code, first = "PASS", "", ""
        rows.append(
            {
                "attempt_id": attempt_id,
                "lot_id": die.lot_id,
                "wafer_id": die.wafer_id,
                "die_id": die.die_id,
                "test_id": spec["test_id"],
                "sequence_index": seq,
                "test_pass_fail": status,
                "pass_fail": status,
                "failure_code": code,
                "is_first_fail": first,
                "timestamp": _iso(die.timestamp),
            }
        )
    return rows


def _param_rows(cfg: dict[str, Any], die: DieDraw, attempt_id: str) -> list[dict[str, Any]]:
    rows = []
    for name, spec in cfg["parametric"].items():
        value = die.measurements[name]
        failed = _param_fail(value, spec)
        rows.append(
            {
                "attempt_id": attempt_id,
                "lot_id": die.lot_id,
                "wafer_id": die.wafer_id,
                "die_id": die.die_id,
                "parameter_name": name,
                "parameter": name,
                "measurement": round(value, 6),
                "value": round(value, 6),
                "unit": spec.get("unit"),
                "lower_limit": spec.get("lower_limit"),
                "upper_limit": spec.get("upper_limit"),
                "condition_id": "NONE",
                "pass_fail": "FAIL" if failed else "PASS",
                "temperature_c": die.temperature_c,
                "voltage_v": die.voltage_v,
                "timestamp": _iso(die.timestamp),
            }
        )
    return rows


def _attempt_id(die: DieDraw, n: int) -> str:
    return f"E-{die.lot_id}-{die.wafer_id}-{die.die_id}-{n}"


def build_tables(cfg: dict[str, Any], dies: list[DieDraw]) -> dict[str, list[dict[str, Any]]]:
    die_attempts: list[dict[str, Any]] = []
    test_results: list[dict[str, Any]] = []
    parametric: list[dict[str, Any]] = []
    for die in dies:
        aid = _attempt_id(die, 1)
        passed = not die.failed
        sbin = cfg["sbin_pass"]
        if not passed:
            sbin = next(t["sbin"] for t in cfg["tests"] if t["test_id"] == die.fail_test_ids[0])
        row = {
            "attempt_id": aid,
            "lot_id": die.lot_id,
            "wafer_id": die.wafer_id,
            "die_id": die.die_id,
            "product_id": cfg["product_id"],
            "step_id": cfg["step_id"],
            "part_class": "PRODUCTION",
            "timestamp": _iso(die.timestamp),
            "attempt_number": 1,
            "is_first_attempt": True,
            "is_retest": False,
            "is_rework": False,
            "abort_flag": False,
            "x": die.x,
            "y": die.y,
            "tester_id": die.tester_id,
            "probe_card_id": die.probe_card_id,
            "prober_id": die.prober_id,
            "site": ((die.x - 1) % 2),
            "temperature_c": die.temperature_c,
            "voltage_v": die.voltage_v,
            "pass_fail": "PASS" if passed else "FAIL",
            "sbin": sbin,
            "hbin": cfg["hbin_pass"] if passed else cfg["hbin_fail"],
            "failure_code": "" if passed else die.failure_code,
            "disposition": "PASS" if passed else "FAIL",
            "record_status": "VALID",
            OXIDE_COLUMN: die.pre_sort_oxide_thickness_nm,
        }
        die_attempts.append(row)
        test_results.extend(_test_rows(cfg, die, aid, passed))
        parametric.extend(_param_rows(cfg, die, aid))
        for n in range(2, 2 + die.retest_attempts):
            aid_n = _attempt_id(die, n)
            ts = die.timestamp + timedelta(seconds=30 * (n - 1))
            if n == 1 + die.retest_attempts:
                retest_pass = die.retest_final_pass
            else:
                retest_pass = False
            die_attempts.append(
                {
                    **row,
                    "attempt_id": aid_n,
                    "timestamp": _iso(ts),
                    "attempt_number": n,
                    "is_first_attempt": False,
                    "is_retest": True,
                    "pass_fail": "PASS" if retest_pass else "FAIL",
                    "sbin": cfg["sbin_pass"] if retest_pass else sbin,
                    "hbin": cfg["hbin_pass"] if retest_pass else cfg["hbin_fail"],
                    "failure_code": "" if retest_pass else die.failure_code,
                    "disposition": "PASS" if retest_pass else "FAIL",
                }
            )
            test_results.extend(_test_rows(cfg, die, aid_n, retest_pass))
            parametric.extend(_param_rows(cfg, die, aid_n))
    lots = []
    wafers = []
    parts = []
    for die in dies:
        parts.append(
            {
                "lot_id": die.lot_id,
                "wafer_id": die.wafer_id,
                "die_id": die.die_id,
                "product_id": cfg["product_id"],
                "part_class": "PRODUCTION",
                "x": die.x,
                "y": die.y,
                "site": (die.x - 1) % 2,
                "is_rework": False,
                "is_engineering": False,
                "is_calibration": False,
            }
        )
    for lot_i in range(int(cfg["n_lots"])):
        lot_id = f"L{lot_i + 1:03d}"
        lot_dies = [d for d in dies if d.lot_id == lot_id]
        start_ts = _iso(min(d.timestamp for d in lot_dies))
        end_ts = _iso(max(d.timestamp for d in lot_dies))
        lots.append(
            {
                "lot_id": lot_id,
                "product_id": cfg["product_id"],
                "step_id": cfg["step_id"],
                "start_timestamp": start_ts,
                "end_timestamp": end_ts,
                "start_ts": start_ts,
                "quantity_declared": len(lot_dies),
                "hold_flag": False,
            }
        )
        for w_i in range(int(cfg["wafers_per_lot"])):
            wafer_id = f"W{w_i + 1:02d}"
            wdies = [d for d in lot_dies if d.wafer_id == wafer_id]
            w_start = _iso(min(d.timestamp for d in wdies))
            w_end = _iso(max(d.timestamp for d in wdies))
            wafers.append(
                {
                    "lot_id": lot_id,
                    "wafer_id": wafer_id,
                    "wafer_sequence": w_i + 1,
                    "slot": w_i + 1,
                    "process_tool_id": "TOOL-A",
                    "process_chamber_id": "",
                    "start_timestamp": w_start,
                    "end_timestamp": w_end,
                    "start_ts": w_start,
                }
            )
    equipment = [
        {"equipment_id": "T01", "equipment_type": "TESTER", "parent_equipment_id": "", "vendor": "ADV", "model": "T-A"},
        {"equipment_id": "T02", "equipment_type": "TESTER", "parent_equipment_id": "", "vendor": "ADV", "model": "T-B"},
        {"equipment_id": "T03", "equipment_type": "TESTER", "parent_equipment_id": "", "vendor": "ADV", "model": "T-C"},
        {"equipment_id": "PC01", "equipment_type": "PROBE_CARD", "parent_equipment_id": "", "vendor": "PCV", "model": "PC-A"},
        {"equipment_id": "PC02", "equipment_type": "PROBE_CARD", "parent_equipment_id": "", "vendor": "PCV", "model": "PC-B"},
        {"equipment_id": "PC03", "equipment_type": "PROBE_CARD", "parent_equipment_id": "", "vendor": "PCV", "model": "PC-C"},
        {"equipment_id": "PR01", "equipment_type": "PROBER", "parent_equipment_id": "", "vendor": "PRB", "model": "P-A"},
        {"equipment_id": "PR02", "equipment_type": "PROBER", "parent_equipment_id": "", "vendor": "PRB", "model": "P-B"},
    ]
    return {
        "die_attempts": die_attempts,
        "test_results": test_results,
        "parametric_measurements": parametric,
        "lot_metadata": lots,
        "wafer_metadata": wafers,
        "lots": lots,
        "wafers": wafers,
        "parts": parts,
        "equipment": equipment,
    }


def _csv_cell(value: Any) -> Any:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return ""
    return value


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: _csv_cell(row.get(key)) for key in fields})


def assert_no_hidden_columns(rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    forbidden = {x.lower() for x in FORBIDDEN_AGENT_COLUMNS}
    hits = [c for c in rows[0].keys() if c.lower() in forbidden]
    if hits:
        raise ValueError(f"hidden columns on agent-visible table: {hits}")


def summarize(cfg: dict[str, Any], dies: list[DieDraw], tables: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    first = [r for r in tables["die_attempts"] if int(r["attempt_number"]) == 1]
    retests = [r for r in tables["die_attempts"] if int(r["attempt_number"]) > 1]
    lot_fpy: dict[str, float] = {}
    for lot_id in sorted({d.lot_id for d in dies}):
        rows = [r for r in first if r["lot_id"] == lot_id]
        n = len(rows)
        n_pass = sum(1 for r in rows if r["pass_fail"] == "PASS")
        lot_fpy[lot_id] = n_pass / n if n else 0.0
    wafer_fpy: dict[str, dict[str, int]] = {}
    for row in first:
        key = f"{row['lot_id']}/{row['wafer_id']}"
        wafer_fpy.setdefault(key, {"n": 0, "pass": 0})
        wafer_fpy[key]["n"] += 1
        if row["pass_fail"] == "PASS":
            wafer_fpy[key]["pass"] += 1
    wafer_rates = {k: v["pass"] / v["n"] for k, v in wafer_fpy.items()}
    nx, ny = int(cfg["wafer_grid_x"]), int(cfg["wafer_grid_y"])
    edge = [d for d in dies if is_edge(d.x, d.y, nx, ny)]
    center = [d for d in dies if is_center(d.x, d.y, nx, ny)]
    edge_fail = sum(1 for d in edge if d.failed) / len(edge)
    center_fail = sum(1 for d in center if d.failed) / len(center)
    tester_fail = {}
    for t in cfg["testers"]:
        subset = [d for d in dies if d.tester_id == t]
        tester_fail[t] = sum(1 for d in subset if d.failed) / len(subset)
    return {
        "dataset_id": cfg["dataset_id"],
        "dataset_version": cfg["dataset_version"],
        "seed": cfg["seed"],
        "n_lots": int(cfg["n_lots"]),
        "n_wafers": int(cfg["n_lots"]) * int(cfg["wafers_per_lot"]),
        "n_dies": len(dies),
        "dies_per_wafer": int(cfg["dies_per_wafer"]),
        "dies_per_lot": int(cfg["wafers_per_lot"]) * int(cfg["dies_per_wafer"]),
        "first_pass_attempts": len(first),
        "retest_attempts": len(retests),
        "test_result_rows": len(tables["test_results"]),
        "parametric_rows": len(tables["parametric_measurements"]),
        "lot_fpy": lot_fpy,
        "wafer_fpy": wafer_rates,
        "overall_fpy": sum(1 for r in first if r["pass_fail"] == "PASS") / len(first),
        "edge_fail_rate": edge_fail,
        "center_fail_rate": center_fail,
        "tester_fail_rate": tester_fail,
        "n_unique_dies": len({(d.lot_id, d.wafer_id, d.die_id) for d in dies}),
    }


def run_quality_checks(cfg: dict[str, Any], dies: list[DieDraw], tables: dict[str, list[dict[str, Any]]], summary: dict[str, Any]) -> dict[str, str]:
    checks: dict[str, str] = {}
    lots = {d.lot_id for d in dies}
    wafers = {(d.lot_id, d.wafer_id) for d in dies}
    unique = {(d.lot_id, d.wafer_id, d.die_id) for d in dies}
    checks["n_lots"] = "PASS" if len(lots) == 5 else "FAIL"
    checks["n_wafers"] = "PASS" if len(wafers) == 25 else "FAIL"
    checks["n_dies"] = "PASS" if len(dies) == 2500 and len(unique) == 2500 else "FAIL"
    checks["dies_per_lot"] = "PASS" if all(sum(1 for d in dies if d.lot_id == lot) == 500 for lot in lots) else "FAIL"
    checks["dies_per_wafer"] = "PASS" if all(sum(1 for d in dies if d.lot_id == l and d.wafer_id == w) == 100 for l, w in wafers) else "FAIL"
    coords = {(d.x, d.y) for d in dies if d.lot_id == "L001" and d.wafer_id == "W01"}
    checks["grid_10x10"] = "PASS" if coords == {(x, y) for y in range(1, 11) for x in range(1, 11)} else "FAIL"
    first = [r for r in tables["die_attempts"] if int(r["attempt_number"]) == 1]
    checks["first_pass_per_die"] = "PASS" if len(first) == 2500 else "FAIL"
    retests = [r for r in tables["die_attempts"] if int(r["attempt_number"]) > 1]
    first_by_die = {(r["lot_id"], r["wafer_id"], r["die_id"]): r for r in first}
    retest_ok = True
    for row in retests:
        parent = first_by_die[(row["lot_id"], row["wafer_id"], row["die_id"])]
        if parent["pass_fail"] != "FAIL":
            retest_ok = False
        if row["is_first_attempt"] is True or str(row["is_first_attempt"]).lower() == "true":
            retest_ok = False
    checks["retest_does_not_overwrite_first_pass"] = "PASS" if retest_ok else "FAIL"
    attempt_ids = {r["attempt_id"] for r in tables["die_attempts"]}
    checks["no_orphan_tests"] = "PASS" if all(r["attempt_id"] in attempt_ids for r in tables["test_results"]) else "FAIL"
    checks["no_orphan_parametric"] = "PASS" if all(r["attempt_id"] in attempt_ids for r in tables["parametric_measurements"]) else "FAIL"
    stamps = [r["timestamp"] for r in first]
    checks["timestamps_sorted"] = "PASS" if stamps == sorted(stamps) else "FAIL"
    fpy = summary["overall_fpy"]
    checks["fpy_range"] = "PASS" if 0.80 <= fpy <= 0.95 else "FAIL"
    lot2 = [d for d in dies if d.lot_id == "L002"]
    nx, ny = int(cfg["wafer_grid_x"]), int(cfg["wafer_grid_y"])
    edge2 = [d for d in lot2 if is_edge(d.x, d.y, nx, ny)]
    inner2 = [d for d in lot2 if not is_edge(d.x, d.y, nx, ny)]
    checks["l002_edge_higher_fail"] = (
        "PASS" if sum(d.failed for d in edge2) / len(edge2) > sum(d.failed for d in inner2) / len(inner2) else "FAIL"
    )
    t01 = summary["tester_fail_rate"]["T01"]
    others = [summary["tester_fail_rate"][t] for t in ("T02", "T03")]
    checks["equipment_not_trivial"] = "PASS" if t01 < 0.5 and min(others) > 0.0 else "FAIL"
    headers_ok = True
    forbidden = {x.lower() for x in FORBIDDEN_AGENT_COLUMNS}
    for rows in tables.values():
        if rows and any(c.lower() in forbidden for c in rows[0]):
            headers_ok = False
    checks["no_hidden_labels_agent_visible"] = "PASS" if headers_ok else "FAIL"
    checks["hierarchy"] = "PASS" if all(v == "PASS" for k, v in checks.items() if k in {"n_lots", "n_wafers", "n_dies", "grid_10x10"}) else "FAIL"
    return checks


def generate_v2(*, write: bool = True, seed: int | None = None) -> dict[str, Any]:
    cfg = load_v2_config()
    if seed is not None:
        cfg["seed"] = seed
    rng = random.Random(int(cfg["seed"]))
    dies = build_population(cfg, rng)
    realize(cfg, rng, dies)
    tables = build_tables(cfg, dies)
    for _name, rows in tables.items():
        assert_no_hidden_columns(rows)
    summary = summarize(cfg, dies, tables)
    checks = run_quality_checks(cfg, dies, tables, summary)
    summary["quality_checks"] = checks
    if write:
        agent = repo_root() / "data" / "synthetic" / "agent_visible" / cfg["dataset_id"]
        agent.mkdir(parents=True, exist_ok=True)
        production_attempts = [
            {key: value for key, value in row.items() if key != OXIDE_COLUMN} for row in tables["die_attempts"]
        ]
        _write_csv(agent / "die_attempts.csv", production_attempts)
        _write_csv(agent / "test_results.csv", tables["test_results"])
        _write_csv(agent / "parametric_measurements.csv", tables["parametric_measurements"])
        _write_csv(agent / "lot_metadata.csv", tables["lot_metadata"])
        _write_csv(agent / "wafer_metadata.csv", tables["wafer_metadata"])
        _write_csv(agent / "lots.csv", tables["lots"])
        _write_csv(agent / "wafers.csv", tables["wafers"])
        _write_csv(agent / "parts.csv", tables["parts"])
        _write_csv(agent / "equipment.csv", tables["equipment"])
        manifest = {
            "dataset_id": cfg["dataset_id"],
            "dataset_version": cfg["dataset_version"],
            "display_name": cfg["display_name"],
            "dataset_type": cfg["dataset_type"],
            "n_lots": summary["n_lots"],
            "n_wafers": summary["n_wafers"],
            "n_dies": summary["n_dies"],
            "wafers_per_lot": int(cfg["wafers_per_lot"]),
            "dies_per_wafer": int(cfg["dies_per_wafer"]),
            "product_id": cfg["product_id"],
            "created_at": _parse_start(cfg["time"]["start"]).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        for key in FORBIDDEN_AGENT_COLUMNS:
            if key in manifest:
                raise ValueError(f"forbidden manifest key {key}")
        (agent / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        gt_dir = repo_root() / HIDDEN_GT_DIR
        gt_dir.mkdir(parents=True, exist_ok=True)
        hidden = {
            "dataset_id": cfg["dataset_id"],
            "dataset_version": cfg["dataset_version"],
            "seed": cfg["seed"],
            "difficulty": "medium",
            "lots": cfg["lots"],
            "summary": summary,
        }
        (gt_dir / f"{cfg['dataset_id']}.json").write_text(
            json.dumps(hidden, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        (gt_dir / "RUN_SUMMARY.json").write_text(
            json.dumps(
                {
                    "dataset_id": cfg["dataset_id"],
                    "seed": cfg["seed"],
                    "n_lots": summary["n_lots"],
                    "n_dies": summary["n_dies"],
                    "overall_fpy": summary["overall_fpy"],
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        summary["agent_dir"] = str(agent)
        summary["hidden_gt"] = str(gt_dir / f"{cfg['dataset_id']}.json")
        val_path = repo_root() / "evaluation" / "results" / "synthetic_v2_validation.json"
        val_path.parent.mkdir(parents=True, exist_ok=True)
        validation = {
            "dataset_id": cfg["dataset_id"],
            "dataset_version": cfg["dataset_version"],
            "seed": cfg["seed"],
            "n_lots": summary["n_lots"],
            "n_wafers": summary["n_wafers"],
            "n_dies": summary["n_dies"],
            "dies_per_wafer": summary["dies_per_wafer"],
            "dies_per_lot": summary["dies_per_lot"],
            "first_pass_attempts": summary["first_pass_attempts"],
            "retest_attempts": summary["retest_attempts"],
            "test_result_rows": summary["test_result_rows"],
            "parametric_rows": summary["parametric_rows"],
            "overall_fpy": summary["overall_fpy"],
            "lot_fpy": summary["lot_fpy"],
            "wafer_fpy": summary["wafer_fpy"],
            "edge_fail_rate": summary["edge_fail_rate"],
            "center_fail_rate": summary["center_fail_rate"],
            "tester_fail_rate": summary["tester_fail_rate"],
            "quality_checks": checks,
            "hidden_ground_truth": str(gt_dir / f"{cfg['dataset_id']}.json"),
            "agent_visible": str(agent),
            "yi_ml_v1_modified": False,
            "ml_retrained": False,
            "production_action": "FORBIDDEN",
        }
        val_path.write_text(json.dumps(validation, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        summary["validation_path"] = str(val_path)
    return summary
