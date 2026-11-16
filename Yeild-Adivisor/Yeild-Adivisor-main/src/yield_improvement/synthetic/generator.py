"""Generate canonical tables from DieState after scenario injection."""

from __future__ import annotations

import hashlib
import json
import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from yield_improvement.config.loader import AppConfig, load_config
from yield_improvement.pipeline import run_pipeline
from yield_improvement.synthetic.baseline import DieState, Profile, build_baseline
from yield_improvement.synthetic.config import ParamDef, SyntheticConfig, load_synthetic_config
from yield_improvement.synthetic.ground_truth import AGENT_MANIFEST_FORBIDDEN, GroundTruth
from yield_improvement.synthetic.scenarios import CORE_SCENARIOS, InjectionResult, apply_scenario
from yield_improvement.synthetic.validation import (
    GeneratorValidationError,
    assert_no_ground_truth_leakage,
    run_generator_validation,
)
from yield_improvement.utils.errors import ConfigError
from yield_improvement.utils.paths import phase2_agent_visible_dir, repo_root


def dataset_id_for(version: str, profile: str, seed: int, scenario_id: str) -> str:
    payload = f"{version}|{profile}|{seed}|{scenario_id}".encode("utf-8")
    return "ds_" + hashlib.sha256(payload).hexdigest()[:16]


def seed_hash(seed: int) -> str:
    return hashlib.sha256(str(seed).encode("utf-8")).hexdigest()[:16]


def _iso(ts: datetime) -> str:
    return ts.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _param_pass(value: float, spec: ParamDef) -> bool:
    if spec.upper_limit is not None and value > spec.upper_limit:
        return False
    if spec.lower_limit is not None and value < spec.lower_limit:
        return False
    return True


def _draw_measurement(rng: random.Random, spec: ParamDef) -> float:
    noise = rng.gauss(0.0, spec.pass_sd)
    return spec.pass_mean + noise


def _sbin_for(cfg: SyntheticConfig, failure_code: str | None, passed: bool) -> int:
    if passed:
        return cfg.sbin_pass
    for test in cfg.tests:
        if test.failure_code == failure_code:
            return test.sbin
    return cfg.tests[0].sbin


def realize_outcomes(
    cfg: SyntheticConfig,
    rng: random.Random,
    dies: list[DieState],
    injection: InjectionResult,
) -> None:
    tests = list(cfg.tests)
    test_ids = [t.test_id for t in tests]
    iddq = cfg.parametric["IDDQ"]
    vmin = cfg.parametric["VMIN"]
    sequence_extra = float(injection.flags.get("extra_p", 0.0)) if injection.flags.get("sequence") else 0.0
    force_code = injection.flags.get("force_failure_code")
    force_card = injection.flags.get("affected_probe_card")
    parametric_name = injection.flags.get("parameter")

    for die in dies:
        if "IDDQ" not in die.measurements:
            die.measurements["IDDQ"] = _draw_measurement(rng, iddq)
        if "VMIN" not in die.measurements:
            die.measurements["VMIN"] = _draw_measurement(rng, vmin)

        iddq_fail = not _param_pass(die.measurements["IDDQ"], iddq)
        vmin_fail = not _param_pass(die.measurements["VMIN"], vmin)

        if die.fail_test_ids:
            die.failed = True
        elif injection.flags.get("sequence"):
            seq = die.sequence_by_test
            iddq_seq = seq.get("T_IDDQ", 5)
            func_seq = seq.get("T_FUNC", 8)
            iddq_test_fail = rng.random() < die.fail_p
            func_fail = False
            if iddq_test_fail and iddq_seq < func_seq:
                func_fail = rng.random() < sequence_extra
            elif rng.random() < die.fail_p * 0.15:
                func_fail = True
            fail_ids: list[str] = []
            if iddq_test_fail:
                fail_ids.append("T_IDDQ")
            if func_fail:
                fail_ids.append("T_FUNC")
            if vmin_fail:
                fail_ids.append("T_VMIN")
            die.fail_test_ids = fail_ids
            die.failed = bool(fail_ids)
        elif parametric_name:
            fail_ids = []
            if iddq_fail:
                fail_ids.append("T_IDDQ")
            if vmin_fail:
                fail_ids.append("T_VMIN")
            if fail_ids:
                die.fail_test_ids = fail_ids
                die.failed = True
            else:
                die.failed = False
        else:
            die.failed = rng.random() < die.fail_p
            if die.failed:
                if force_code and (force_card is None or die.probe_card_id == force_card):
                    match = next(t for t in tests if t.failure_code == force_code)
                    die.fail_test_ids = [match.test_id]
                elif iddq_fail:
                    die.fail_test_ids = ["T_IDDQ"]
                elif vmin_fail:
                    die.fail_test_ids = ["T_VMIN"]
                else:
                    die.fail_test_ids = [rng.choice(test_ids)]
            elif iddq_fail or vmin_fail:
                die.failed = True
                die.fail_test_ids = ["T_IDDQ"] if iddq_fail else ["T_VMIN"]

        if die.failed and not die.fail_test_ids:
            die.fail_test_ids = [rng.choice(test_ids)]

        if die.failed:
            ordered = sorted(die.fail_test_ids, key=lambda tid: die.sequence_by_test.get(tid, 99))
            primary = next(t for t in tests if t.test_id == ordered[0])
            die.failure_code = primary.failure_code
        else:
            die.failure_code = None


def _attempt_id(die: DieState, attempt_number: int) -> str:
    return f"E-{die.lot_id}-{die.wafer_id}-{die.die_id}-{attempt_number}"


def _test_rows_for_attempt(
    cfg: SyntheticConfig,
    die: DieState,
    attempt_id: str,
    passed: bool,
    is_retest_pass: bool,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    fail_set = set(die.fail_test_ids) if (not passed and not is_retest_pass) else set()
    first_fail = None
    if fail_set:
        first_fail = min(fail_set, key=lambda tid: die.sequence_by_test.get(tid, 99))
    first_fail_seq = die.sequence_by_test.get(first_fail, 10**9) if first_fail else 10**9
    for spec in cfg.tests:
        seq = die.sequence_by_test.get(spec.test_id, spec.sequence_index)
        if is_retest_pass or passed:
            status = "PASS"
            is_first = ""
            code = ""
        elif spec.test_id in fail_set:
            status = "FAIL"
            is_first = "true" if spec.test_id == first_fail else "false"
            code = spec.failure_code
        elif seq > first_fail_seq:
            status = "NOT_EXECUTED"
            is_first = ""
            code = ""
        else:
            status = "PASS"
            is_first = ""
            code = ""
        rows.append(
            {
                "attempt_id": attempt_id,
                "test_id": spec.test_id,
                "test_pass_fail": status,
                "sequence_index": seq,
                "is_first_fail": is_first,
                "failure_code": code,
            }
        )
    return rows


def _parametric_rows(
    cfg: SyntheticConfig,
    die: DieState,
    attempt_id: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for name, spec in cfg.parametric.items():
        value = die.measurements.get(name)
        if value is None:
            continue
        passed = _param_pass(value, spec)
        rows.append(
            {
                "attempt_id": attempt_id,
                "parameter_name": name,
                "condition_id": "NONE",
                "measurement": value,
                "lower_limit": spec.lower_limit,
                "upper_limit": spec.upper_limit,
                "unit": spec.unit,
                "pass_fail": "PASS" if passed else "FAIL",
                "temperature_c": die.temperature_c,
                "voltage_v": 0.8,
            }
        )
    return rows


def build_tables(
    cfg: SyntheticConfig,
    dies: list[DieState],
    injection: InjectionResult,
    rng: random.Random,
) -> dict[str, list[dict[str, Any]]]:
    die_attempts: list[dict[str, Any]] = []
    test_results: list[dict[str, Any]] = []
    parametric: list[dict[str, Any]] = []
    retest_rate = float(injection.flags.get("retest_pass_rate", 0.0))

    for die in dies:
        passed = not die.failed
        aid = _attempt_id(die, 1)
        sbin = _sbin_for(cfg, die.failure_code, passed)
        row = {
            "lot_id": die.lot_id,
            "wafer_id": die.wafer_id,
            "die_id": die.die_id,
            "product_id": cfg.product_id,
            "step_id": cfg.step_id,
            "part_class": "PRODUCTION",
            "x": die.x,
            "y": die.y,
            "attempt_id": aid,
            "timestamp": _iso(die.timestamp),
            "attempt_number": 1,
            "is_first_attempt": True,
            "is_retest": False,
            "is_rework": False,
            "abort_flag": False,
            "pass_fail": "PASS" if passed else "FAIL",
            "sbin": sbin,
            "hbin": cfg.hbin_pass if passed else cfg.hbin_fail,
            "failure_code": "" if passed else die.failure_code,
            "tester_id": die.tester_id,
            "probe_card_id": die.probe_card_id,
            "prober_id": "PRB-1",
            "site": die.site,
            "temperature_c": die.temperature_c,
            "voltage_v": 0.8,
            "disposition": "PASS" if passed else "FAIL",
            "record_status": "VALID",
        }
        die_attempts.append(row)
        test_results.extend(_test_rows_for_attempt(cfg, die, aid, passed, False))
        parametric.extend(_parametric_rows(cfg, die, aid))

        if (not passed) and retest_rate > 0 and rng.random() < retest_rate:
            aid2 = _attempt_id(die, 2)
            ts2 = die.timestamp + timedelta(seconds=30)
            die_attempts.append(
                {
                    **row,
                    "attempt_id": aid2,
                    "timestamp": _iso(ts2),
                    "attempt_number": 2,
                    "is_first_attempt": False,
                    "is_retest": True,
                    "pass_fail": "PASS",
                    "sbin": 2,
                    "hbin": cfg.hbin_pass,
                    "failure_code": "",
                    "disposition": "PASS",
                }
            )
            test_results.extend(_test_rows_for_attempt(cfg, die, aid2, True, True))
            parametric.extend(_parametric_rows(cfg, die, aid2))

    lots: list[dict[str, Any]] = []
    seen_lots: set[str] = set()
    wafers: list[dict[str, Any]] = []
    seen_wafers: set[tuple[str, str]] = set()
    parts: list[dict[str, Any]] = []
    for die in dies:
        if die.lot_id not in seen_lots:
            seen_lots.add(die.lot_id)
            n_dies = sum(1 for d in dies if d.lot_id == die.lot_id)
            lots.append(
                {
                    "lot_id": die.lot_id,
                    "product_id": cfg.product_id,
                    "step_id": cfg.step_id,
                    "start_ts": _iso(die.timestamp),
                    "quantity_declared": n_dies,
                    "hold_flag": False,
                }
            )
        key = (die.lot_id, die.wafer_id)
        if key not in seen_wafers:
            seen_wafers.add(key)
            wafers.append(
                {
                    "lot_id": die.lot_id,
                    "wafer_id": die.wafer_id,
                    "slot": die.wafer_index_in_lot + 1,
                    "process_tool_id": "TOOL-A",
                    "process_chamber_id": "",
                    "start_ts": _iso(die.timestamp),
                }
            )
        parts.append(
            {
                "lot_id": die.lot_id,
                "wafer_id": die.wafer_id,
                "die_id": die.die_id,
                "product_id": cfg.product_id,
                "part_class": "PRODUCTION",
                "x": die.x,
                "y": die.y,
                "site": die.site,
                "is_rework": False,
                "is_engineering": False,
                "is_calibration": False,
            }
        )

    equipment = [
        {"equipment_id": t, "equipment_type": "TESTER", "parent_equipment_id": "", "vendor": "SYN", "model": "T200"}
        for t in cfg.testers
    ]
    equipment.append(
        {"equipment_id": "PRB-1", "equipment_type": "PROBER", "parent_equipment_id": "", "vendor": "SYN", "model": "P1"}
    )
    for card in cfg.probe_cards:
        equipment.append(
            {
                "equipment_id": card,
                "equipment_type": "PROBE_CARD",
                "parent_equipment_id": "PRB-1",
                "vendor": "SYN",
                "model": "PC",
            }
        )

    return {
        "lots": lots,
        "wafers": wafers,
        "parts": parts,
        "die_attempts": die_attempts,
        "test_results": test_results,
        "parametric_measurements": parametric,
        "equipment": equipment,
    }


def _cell(value: Any) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    import csv

    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: _cell(row[k]) for k in fieldnames})


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


AGENT_TABLES = (
    "lots",
    "wafers",
    "parts",
    "die_attempts",
    "test_results",
    "parametric_measurements",
    "equipment",
)


@dataclass
class GeneratedDataset:
    dataset_id: str
    scenario_id: str
    profile: str
    seed: int
    tables: dict[str, list[dict[str, Any]]]
    dies: list[DieState]
    ground_truth: GroundTruth
    agent_manifest: dict[str, Any]
    validation_report: dict[str, Any]
    agent_dir: Path | None = None
    ground_truth_dir: Path | None = None


def generate_dataset(
    scenario_id: str,
    *,
    config: SyntheticConfig | None = None,
    seed: int | None = None,
    profile_name: str | None = None,
    app_config: AppConfig | None = None,
    write: bool = False,
    agent_root: Path | None = None,
    gt_root: Path | None = None,
) -> GeneratedDataset:
    cfg = config or load_synthetic_config()
    if scenario_id not in cfg.scenarios and scenario_id not in CORE_SCENARIOS:
        raise ConfigError(f"Unknown scenario {scenario_id!r}")
    profile_key = profile_name or cfg.active_profile
    profile: Profile = cfg.profile(profile_key)
    used_seed = cfg.seed if seed is None else seed
    rng = random.Random(used_seed)

    dies = build_baseline(cfg, rng, profile)
    injection = apply_scenario(scenario_id, cfg, rng, dies, profile)
    realize_outcomes(cfg, rng, dies, injection)
    tables = build_tables(cfg, dies, injection, rng)

    ds_id = dataset_id_for(cfg.generator_version, profile_key, used_seed, scenario_id)
    gt = GroundTruth(
        scenario_id=scenario_id,
        dataset_id=ds_id,
        generator_version=cfg.generator_version,
        seed=used_seed,
        profile=profile_key,
        true_causes=injection.true_causes,
        injected_parameters=injection.injected_parameters,
        affected_population=injection.affected_population,
        expected_signal=injection.expected_signal,
        confounders=injection.confounders,
        difficulty=injection.difficulty,
        notes=injection.notes,
    )

    n_first = sum(1 for r in tables["die_attempts"] if int(r["attempt_number"]) == 1)
    n_fail = sum(1 for r in tables["die_attempts"] if int(r["attempt_number"]) == 1 and r["pass_fail"] == "FAIL")
    n_pass = n_first - n_fail
    fpy = n_pass / n_first if n_first else None

    agent_manifest = {
        "dataset_id": ds_id,
        "generator_version": cfg.generator_version,
        "profile": profile_key,
        "product_id": cfg.product_id,
        "step_id": cfg.step_id,
        "row_counts": {name: len(tables[name]) for name in AGENT_TABLES},
        "lot_count": len(tables["lots"]),
        "wafer_count": len(tables["wafers"]),
        "die_count": len(tables["parts"]),
        "attempt_count": len(tables["die_attempts"]),
        "optional_data_available": [
            "x",
            "y",
            "tester_id",
            "probe_card_id",
            "temperature_c",
            "test_results",
            "parametric_measurements",
        ],
        "seed_hash": seed_hash(used_seed),
        "canonical_validation": "pending",
        "first_pass_fpy": fpy,
    }
    for key in AGENT_MANIFEST_FORBIDDEN:
        if key in agent_manifest:
            raise GeneratorValidationError(f"Agent manifest contains forbidden key {key}")

    app = app_config or load_config()
    report = run_generator_validation(
        tables=tables,
        dies=dies,
        cfg=cfg,
        profile=profile,
        injection=injection,
        scenario_id=scenario_id,
        app_config=app,
        agent_manifest=agent_manifest,
    )
    if report["status"] != "PASSED":
        raise GeneratorValidationError(json.dumps(report, indent=2))
    agent_manifest["canonical_validation"] = "passed"

    bundle = GeneratedDataset(
        dataset_id=ds_id,
        scenario_id=scenario_id,
        profile=profile_key,
        seed=used_seed,
        tables=tables,
        dies=dies,
        ground_truth=gt,
        agent_manifest=agent_manifest,
        validation_report=report,
    )
    if write:
        persist_dataset(bundle, agent_root=agent_root, gt_root=gt_root, app_config=app)
    return bundle


def persist_dataset(
    bundle: GeneratedDataset,
    *,
    agent_root: Path | None = None,
    gt_root: Path | None = None,
    app_config: AppConfig | None = None,
) -> GeneratedDataset:
    root = repo_root()
    agent_base = agent_root or phase2_agent_visible_dir()
    gt_base = gt_root or (root / "evaluation" / "ground_truth" / "synthetic")
    agent_dir = agent_base / bundle.dataset_id
    gt_dir = gt_base / bundle.dataset_id
    agent_dir.mkdir(parents=True, exist_ok=True)
    gt_dir.mkdir(parents=True, exist_ok=True)

    for name in AGENT_TABLES:
        write_csv(agent_dir / f"{name}.csv", bundle.tables[name])
    write_json(agent_dir / "manifest.json", bundle.agent_manifest)

    write_json(gt_dir / "ground_truth.json", bundle.ground_truth.model_dump(mode="json"))
    write_json(
        gt_dir / "scenario_manifest.json",
        {
            "dataset_id": bundle.dataset_id,
            "scenario_id": bundle.scenario_id,
            "generator_version": bundle.ground_truth.generator_version,
            "seed": bundle.seed,
            "profile": bundle.profile,
            "true_causes": [c.model_dump() for c in bundle.ground_truth.true_causes],
        },
    )
    write_json(gt_dir / "validation_report.json", bundle.validation_report)

    assert_no_ground_truth_leakage(agent_dir)
    app = app_config or load_config()
    da = agent_dir / "die_attempts.csv"
    tr = agent_dir / "test_results.csv"
    result = run_pipeline(da, tr, config=app)
    if result.status != "OK":
        raise GeneratorValidationError(
            f"Written dataset failed canonical pipeline: {[e.model_dump() for e in result.errors]}"
        )
    bundle.agent_dir = agent_dir
    bundle.ground_truth_dir = gt_dir
    bundle.validation_report["pipeline_fpy"] = result.fpy
    bundle.validation_report["pipeline_status"] = result.status
    write_json(gt_dir / "validation_report.json", bundle.validation_report)
    return bundle


def generate_core_scenarios(
    *,
    config: SyntheticConfig | None = None,
    seed: int | None = None,
    profile_name: str | None = None,
    write: bool = True,
) -> list[GeneratedDataset]:
    cfg = config or load_synthetic_config()
    out: list[GeneratedDataset] = []
    for scenario_id in CORE_SCENARIOS:
        out.append(
            generate_dataset(
                scenario_id,
                config=cfg,
                seed=seed,
                profile_name=profile_name,
                write=write,
            )
        )
    if write:
        gt_root = repo_root() / "evaluation" / "ground_truth" / "synthetic"
        summary = {
            "generator_version": cfg.generator_version,
            "profile": profile_name or cfg.active_profile,
            "seed": cfg.seed if seed is None else seed,
            "scenarios": [
                {
                    "dataset_id": item.dataset_id,
                    "scenario_id": item.scenario_id,
                    "die_count": item.agent_manifest["die_count"],
                    "attempt_count": item.agent_manifest["attempt_count"],
                    "first_pass_fpy": item.agent_manifest["first_pass_fpy"],
                    "validation": item.validation_report["status"],
                    "sanity": item.validation_report.get("sanity_status"),
                    "pipeline_fpy": item.validation_report.get("pipeline_fpy"),
                }
                for item in out
            ],
        }
        write_json(gt_root / "RUN_SUMMARY.json", summary)
    return out
