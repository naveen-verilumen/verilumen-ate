"""Enhanced V2 ML view: original outcomes plus pre_sort_oxide_thickness_nm.

The production dataset under data/synthetic/agent_visible/yi_synthetic_v2 stays
unchanged. This module writes a sibling copy that the production dataset selector
does not list.
"""

from __future__ import annotations

import csv
import hashlib
import json
import random
import shutil
from collections import Counter
from pathlib import Path
from typing import Any

from yield_improvement.synthetic.ground_truth import AGENT_MANIFEST_FORBIDDEN
from yield_improvement.synthetic.v2_generator import (
    OXIDE_COLUMN,
    OXIDE_UNIT,
    _csv_cell,
    _param_fail,
    build_population,
    build_tables,
    load_v2_config,
    oxide_thickness_nm,
    realize,
)
from yield_improvement.utils.paths import repo_root

SOURCE_DATASET_ID = "yi_synthetic_v2"
ENHANCED_DATASET_ID = "yi_synthetic_v2_ml_enhanced"
UNCHANGED_FILES = (
    "test_results.csv",
    "parametric_measurements.csv",
    "lot_metadata.csv",
    "wafer_metadata.csv",
    "lots.csv",
    "wafers.csv",
    "parts.csv",
    "equipment.csv",
    "manifest.json",
)
OUTCOME_TABLES = ("die_attempts", "test_results", "parametric_measurements")


class OutcomePreservationError(RuntimeError):
    """Raised when a regenerated outcome does not match the stored V2 dataset."""


def source_dataset_dir() -> Path:
    return repo_root() / "data" / "synthetic" / "agent_visible" / SOURCE_DATASET_ID


def enhanced_dataset_dir() -> Path:
    return repo_root() / "data" / "synthetic" / "ml_enhanced" / ENHANCED_DATASET_ID


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _cell_text(value: Any) -> str:
    return str(_csv_cell(value))


def generate_enhanced_population(
    *,
    oxide_stream_seed: int | None = None,
) -> tuple[dict[str, Any], list[Any], dict[str, list[dict[str, Any]]]]:
    cfg = load_v2_config()
    rng = random.Random(int(cfg["seed"]))
    kwargs = {} if oxide_stream_seed is None else {"oxide_stream_seed": oxide_stream_seed}
    dies = build_population(cfg, rng, **kwargs)
    realize(cfg, rng, dies)
    tables = build_tables(cfg, dies)
    return cfg, dies, tables


def preservation_mismatches(
    tables: dict[str, list[dict[str, Any]]],
    source: Path | None = None,
) -> list[str]:
    """Value-level differences on existing columns. The new measurement is ignored."""
    root = source or source_dataset_dir()
    mismatches: list[str] = []
    for name in OUTCOME_TABLES:
        original = _read_csv(root / f"{name}.csv")
        generated = tables[name]
        if len(original) != len(generated):
            mismatches.append(f"{name}: row count {len(generated)} != {len(original)}")
            continue
        original_fields = list(original[0].keys()) if original else []
        for index, (stored, fresh) in enumerate(zip(original, generated, strict=True)):
            for field in original_fields:
                if field not in fresh:
                    mismatches.append(f"{name} row {index} missing {field}")
                    continue
                left = stored[field]
                right = _cell_text(fresh[field])
                if left != right:
                    mismatches.append(f"{name} row {index} {field}: {right!r} != {left!r}")
                    if len(mismatches) >= 12:
                        return mismatches
    return mismatches


def assert_outcomes_preserved(tables: dict[str, list[dict[str, Any]]], source: Path | None = None) -> None:
    mismatches = preservation_mismatches(tables, source)
    if mismatches:
        preview = "; ".join(mismatches[:8])
        raise OutcomePreservationError(f"existing V2 outcomes changed: {preview}")


def _first_pass(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [row for row in rows if int(row["attempt_number"]) == 1]


def outcome_counts(rows: list[dict[str, Any]]) -> dict[str, Any]:
    first = _first_pass(rows)
    failures = sum(1 for row in first if row["pass_fail"] == "FAIL")
    passes = sum(1 for row in first if row["pass_fail"] == "PASS")
    eligible = len(first)
    return {
        "eligible_dies": eligible,
        "first_pass_failures": failures,
        "first_pass_passes": passes,
        "fpy": (passes / eligible) if eligible else 0.0,
        "fpy_loss": (failures / eligible) if eligible else 0.0,
        "primary_failure_counts": dict(Counter(row["failure_code"] for row in first if row["pass_fail"] == "FAIL")),
    }


def _numeric(value: Any) -> float:
    if value is None or value == "":
        raise ValueError("missing oxide thickness")
    return float(value)


def measurement_statistics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    import statistics

    first = _first_pass(rows)
    values = [_numeric(row[OXIDE_COLUMN]) for row in first]
    missing = sum(1 for row in first if row.get(OXIDE_COLUMN) in (None, ""))
    ordered = sorted(values)

    def _group(key_fn):
        groups: dict[str, list[float]] = {}
        for row, value in zip(first, values, strict=True):
            groups.setdefault(key_fn(row), []).append(value)
        summary = {}
        for key in sorted(groups):
            series = groups[key]
            summary[key] = {
                "n": len(series),
                "mean": statistics.fmean(series),
                "std": statistics.stdev(series) if len(series) > 1 else 0.0,
            }
        return summary

    pass_vals = [value for row, value in zip(first, values, strict=True) if row["pass_fail"] == "PASS"]
    fail_vals = [value for row, value in zip(first, values, strict=True) if row["pass_fail"] == "FAIL"]
    return {
        "column": OXIDE_COLUMN,
        "unit": OXIDE_UNIT,
        "n": len(values),
        "missing": missing,
        "min": min(values),
        "max": max(values),
        "mean": statistics.fmean(values),
        "median": statistics.median(values),
        "std": statistics.stdev(values),
        "lot": _group(lambda row: row["lot_id"]),
        "wafer": _group(lambda row: f"{row['lot_id']}/{row['wafer_id']}"),
        "by_first_pass": {
            "PASS": {
                "n": len(pass_vals),
                "mean": statistics.fmean(pass_vals),
                "std": statistics.stdev(pass_vals),
            },
            "FAIL": {
                "n": len(fail_vals),
                "mean": statistics.fmean(fail_vals),
                "std": statistics.stdev(fail_vals),
            },
        },
    }


def _thickness_by_attempt(tables: dict[str, list[dict[str, Any]]]) -> dict[str, str]:
    mapped: dict[str, str] = {}
    for row in tables["die_attempts"]:
        mapped[str(row["attempt_id"])] = _cell_text(row[OXIDE_COLUMN])
    return mapped


def write_enhanced_dataset(dest: Path | None = None) -> dict[str, Any]:
    """Copy V2 and append the oxide column. Refuses to write if outcomes differ."""
    source = source_dataset_dir()
    target = dest or enhanced_dataset_dir()
    before = {name: file_sha256(source / name) for name in ("die_attempts.csv", "test_results.csv", "parametric_measurements.csv")}
    _cfg, dies, tables = generate_enhanced_population()
    assert_outcomes_preserved(tables, source)
    counts = outcome_counts(tables["die_attempts"])
    if counts["eligible_dies"] != 2500 or counts["first_pass_failures"] != 251 or counts["first_pass_passes"] != 2249:
        raise OutcomePreservationError(f"unexpected first-pass counts: {counts}")

    if target.resolve() == source.resolve():
        raise OutcomePreservationError("refusing to overwrite the original V2 dataset")
    target.mkdir(parents=True, exist_ok=True)
    for name in UNCHANGED_FILES:
        shutil.copy2(source / name, target / name)

    original_attempts = _read_csv(source / "die_attempts.csv")
    thickness = _thickness_by_attempt(tables)
    fields = list(original_attempts[0].keys()) + [OXIDE_COLUMN]
    written_rows: list[dict[str, str]] = []
    with (target / "die_attempts.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in original_attempts:
            aid = row["attempt_id"]
            if aid not in thickness:
                raise OutcomePreservationError(f"no oxide thickness for attempt {aid}")
            enriched = dict(row)
            enriched[OXIDE_COLUMN] = thickness[aid]
            writer.writerow(enriched)
            written_rows.append(enriched)

    after = {name: file_sha256(source / name) for name in before}
    if after != before:
        raise OutcomePreservationError("original V2 files changed while writing the enhanced copy")

    stats = measurement_statistics(written_rows)
    lineage = {
        "source_dataset_id": SOURCE_DATASET_ID,
        "source_path": "data/synthetic/agent_visible/yi_synthetic_v2/",
        "enhanced_dataset_id": ENHANCED_DATASET_ID,
        "enhanced_path": "data/synthetic/ml_enhanced/yi_synthetic_v2_ml_enhanced/",
        "relationship": "yi_synthetic_v2 + pre_sort_oxide_thickness_nm = enhanced ML candidate dataset",
        "added_column": OXIDE_COLUMN,
        "unit": OXIDE_UNIT,
        "same_scenario": True,
        "second_manufacturing_world": False,
        "yi_ml_v5_trained": False,
        "model_activated": False,
        "source_sha256": before,
        "outcome_counts": {key: counts[key] for key in ("eligible_dies", "first_pass_failures", "first_pass_passes", "fpy", "fpy_loss")},
        "distribution": stats,
        "n_physical_dies": len({(d.lot_id, d.wafer_id, d.die_id) for d in dies}),
    }
    forbidden = {name.lower() for name in AGENT_MANIFEST_FORBIDDEN}
    if any(key.lower() in forbidden for key in lineage):
        raise OutcomePreservationError("lineage document contains a hidden-truth field")
    (target / "enhancement.json").write_text(json.dumps(lineage, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return lineage


def _source_text(fn: Any) -> str:
    import inspect

    return inspect.getsource(fn)


def leakage_report(
    dies: list[Any],
    tables: dict[str, list[dict[str, Any]]],
    dataset: Path | None = None,
) -> dict[str, bool]:
    """Checks that the oxide measurement stays out of disposition and hidden-truth fields."""
    population = _source_text(build_population)
    fail_at = population.index("fail_p = clip(")
    oxide_at = population.index("oxide_thickness_nm(")
    fail_stmt = population[fail_at:oxide_at]
    formula = _source_text(oxide_thickness_nm)
    realize_src = _source_text(realize)
    limit_src = _source_text(_param_fail)
    cfg = load_v2_config()
    root = dataset or enhanced_dataset_dir()
    headers: list[str] = [key for rows in tables.values() if rows for key in rows[0]]
    if root.is_dir():
        for path in sorted(root.glob("*.csv")):
            with path.open(encoding="utf-8", newline="") as handle:
                headers.extend(csv.DictReader(handle).fieldnames or [])
        lineage_path = root / "enhancement.json"
        if lineage_path.is_file():
            headers.extend(json.loads(lineage_path.read_text(encoding="utf-8")).keys())
    forbidden = {name.lower() for name in AGENT_MANIFEST_FORBIDDEN}
    header_names = {name.lower() for name in headers}
    thicknesses = [float(die.pre_sort_oxide_thickness_nm) for die in dies]
    fail_ps = [float(die.fail_p) for die in dies]
    derived_tokens = ("first_pass_fail", "failure_code", "pass_fail", "test_pass_fail", "primary_failure", "die.failed")
    return {
        "not_read_by_fail_p": OXIDE_COLUMN not in fail_stmt and "oxide_thickness_nm" not in fail_stmt and fail_at < oxide_at,
        "not_read_by_die_failed": OXIDE_COLUMN not in realize_src and "pre_sort_oxide_thickness_nm" not in realize_src,
        "not_read_by_parameter_limits": OXIDE_COLUMN not in limit_src and OXIDE_COLUMN not in cfg["parametric"],
        "not_derived_from_first_pass_fail": "first_pass" not in formula and "pass_fail" not in formula,
        "not_derived_from_failure_code": "failure_code" not in formula,
        "not_derived_from_test_outcome": "test_pass" not in formula and "test_results" not in formula,
        "not_derived_from_primary_failure": "primary" not in formula and all(token not in formula for token in derived_tokens),
        "no_scenario_id": "scenario_id" not in header_names and "scenario_id" not in formula,
        "no_true_cause": "true_cause" not in header_names and "true_cause" not in formula,
        "no_ground_truth": "ground_truth" not in header_names and "ground_truth" not in formula,
        "no_injected_effect": "injected_effect" not in header_names and "injected_effect" not in formula,
        "no_generator_seed": "generator_seed" not in header_names and "generator_seed" not in formula,
        "not_a_copy_of_fail_probability": all(abs(thickness - fail_p) > 1.0 for thickness, fail_p in zip(thicknesses, fail_ps, strict=True)),
        "no_forbidden_header": forbidden.isdisjoint(header_names),
    }
