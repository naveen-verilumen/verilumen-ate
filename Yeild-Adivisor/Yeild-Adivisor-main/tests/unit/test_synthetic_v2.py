"""Phase 11A: controlled V2 hierarchy, hidden GT isolation, deterministic generation."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from yield_improvement.synthetic.ground_truth import AGENT_MANIFEST_FORBIDDEN
from yield_improvement.synthetic.v2_generator import generate_v2, is_center, is_edge, load_v2_config
from yield_improvement.utils.paths import active_synthetic_dir, repo_root

ACTIVE = "yi_synthetic_v2"
FORBIDDEN = {name.lower() for name in AGENT_MANIFEST_FORBIDDEN}


def _agent_dir() -> Path:
    return active_synthetic_dir() / ACTIVE


def _csv(name: str) -> list[dict[str, str]]:
    path = _agent_dir() / name
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_v2_config_structure():
    cfg = load_v2_config()
    assert cfg["dataset_id"] == ACTIVE
    assert cfg["seed"] == 20261101
    assert cfg["n_lots"] == 5
    assert cfg["wafers_per_lot"] == 5
    assert cfg["dies_per_wafer"] == 100
    assert cfg["wafer_grid_x"] == 10
    assert cfg["wafer_grid_y"] == 10
    assert 8 <= int(cfg["tests_per_die"]) <= 12


def test_generation_is_deterministic():
    a = generate_v2(write=False)
    b = generate_v2(write=False)
    assert a["lot_fpy"] == b["lot_fpy"]
    assert a["overall_fpy"] == b["overall_fpy"]
    assert a["first_pass_attempts"] == b["first_pass_attempts"]
    assert a["test_result_rows"] == b["test_result_rows"]
    assert a["quality_checks"] == b["quality_checks"]


def test_written_v2_hierarchy():
    attempts = _csv("die_attempts.csv")
    first = [row for row in attempts if row["attempt_number"] == "1"]
    lots = {row["lot_id"] for row in first}
    wafers = {(row["lot_id"], row["wafer_id"]) for row in first}
    dies = {(row["lot_id"], row["wafer_id"], row["die_id"]) for row in first}
    assert lots == {f"L{i:03d}" for i in range(1, 6)}
    assert len(wafers) == 25
    assert len(dies) == 2500
    assert len(first) == 2500
    for lot in lots:
        assert sum(1 for row in first if row["lot_id"] == lot) == 500
        assert {row["wafer_id"] for row in first if row["lot_id"] == lot} == {f"W{i:02d}" for i in range(1, 6)}
    for lot, wafer in wafers:
        subset = [row for row in first if row["lot_id"] == lot and row["wafer_id"] == wafer]
        assert len(subset) == 100
        coords = {(int(float(row["x"])), int(float(row["y"]))) for row in subset}
        assert coords == {(x, y) for y in range(1, 11) for x in range(1, 11)}


def test_wafer_id_is_not_globally_unique():
    first = [row for row in _csv("die_attempts.csv") if row["attempt_number"] == "1"]
    assert len({row["wafer_id"] for row in first}) == 5
    assert len({(row["lot_id"], row["wafer_id"]) for row in first}) == 25


def test_no_duplicate_dies_or_orphan_records():
    attempts = _csv("die_attempts.csv")
    first = [row for row in attempts if row["attempt_number"] == "1"]
    keys = [(row["lot_id"], row["wafer_id"], row["die_id"]) for row in first]
    assert len(keys) == len(set(keys))
    attempt_ids = {row["attempt_id"] for row in attempts}
    tests = _csv("test_results.csv")
    params = _csv("parametric_measurements.csv")
    assert all(row["attempt_id"] in attempt_ids for row in tests)
    assert all(row["attempt_id"] in attempt_ids for row in params)
    die_keys = {(row["lot_id"], row["wafer_id"], row["die_id"]) for row in first}
    assert {(row["lot_id"], row["wafer_id"], row["die_id"]) for row in _csv("parts.csv")} == die_keys


def test_first_pass_and_retest_consistency():
    attempts = _csv("die_attempts.csv")
    first = {(row["lot_id"], row["wafer_id"], row["die_id"]): row for row in attempts if row["attempt_number"] == "1"}
    retests = [row for row in attempts if int(row["attempt_number"]) > 1]
    assert all(row["is_first_attempt"] == "true" for row in first.values())
    for row in retests:
        parent = first[(row["lot_id"], row["wafer_id"], row["die_id"])]
        assert parent["pass_fail"] == "FAIL"
        assert row["is_first_attempt"] == "false"
        assert row["is_retest"] == "true"
    tests = _csv("test_results.csv")
    by_attempt: dict[str, list[dict[str, str]]] = {}
    for row in tests:
        by_attempt.setdefault(row["attempt_id"], []).append(row)
    for die_row in first.values():
        rows = by_attempt[die_row["attempt_id"]]
        if die_row["pass_fail"] == "PASS":
            assert all(r["test_pass_fail"] == "PASS" for r in rows)
        else:
            assert any(r["test_pass_fail"] == "FAIL" for r in rows)


def test_timestamps_are_chronological():
    first = [row for row in _csv("die_attempts.csv") if row["attempt_number"] == "1"]
    by_lot = {}
    for row in first:
        by_lot.setdefault(row["lot_id"], []).append(row["timestamp"])
    lot_starts = [min(by_lot[f"L{i:03d}"]) for i in range(1, 6)]
    assert lot_starts == sorted(lot_starts)
    stamps = [row["timestamp"] for row in first]
    assert stamps == sorted(stamps)


def test_no_hidden_labels_in_agent_visible():
    folder = _agent_dir()
    for path in folder.glob("*.csv"):
        with path.open(encoding="utf-8", newline="") as handle:
            headers = [h.lower() for h in next(csv.reader(handle))]
        assert FORBIDDEN.isdisjoint(headers), path.name
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    assert FORBIDDEN.isdisjoint({k.lower() for k in manifest})
    assert "creation_seed" not in manifest
    assert "seed" not in manifest


def test_hidden_ground_truth_is_separate():
    hidden = repo_root() / "evaluation" / "ground_truth" / "synthetic_v2" / f"{ACTIVE}.json"
    assert hidden.is_file()
    payload = json.loads(hidden.read_text(encoding="utf-8"))
    assert payload["seed"] == 20261101
    assert payload["lots"]["L001"]["role"] == "BASELINE"
    assert payload["lots"]["L002"]["role"] == "SPATIAL_EDGE"
    assert payload["lots"]["L003"]["role"] == "EQUIPMENT"
    assert payload["lots"]["L004"]["role"] == "PROCESS_DRIFT"
    assert payload["lots"]["L005"]["role"] == "WEAK_MIXED"
    assert not (_agent_dir() / "ground_truth.json").exists()


def test_failure_rate_and_spatial_variation():
    first = [row for row in _csv("die_attempts.csv") if row["attempt_number"] == "1"]
    n = len(first)
    n_pass = sum(1 for row in first if row["pass_fail"] == "PASS")
    overall = n_pass / n
    assert 0.80 <= overall <= 0.95
    lot_fpy = {}
    for lot in (f"L{i:03d}" for i in range(1, 6)):
        rows = [row for row in first if row["lot_id"] == lot]
        lot_fpy[lot] = sum(1 for row in rows if row["pass_fail"] == "PASS") / len(rows)
        assert 0.70 <= lot_fpy[lot] <= 0.99
    assert len(set(round(v, 4) for v in lot_fpy.values())) > 1
    edge = [row for row in first if row["lot_id"] == "L002" and is_edge(int(float(row["x"])), int(float(row["y"])), 10, 10)]
    inner = [row for row in first if row["lot_id"] == "L002" and not is_edge(int(float(row["x"])), int(float(row["y"])), 10, 10)]
    edge_fail = sum(row["pass_fail"] == "FAIL" for row in edge) / len(edge)
    inner_fail = sum(row["pass_fail"] == "FAIL" for row in inner) / len(inner)
    assert edge_fail > inner_fail
    center = [row for row in first if is_center(int(float(row["x"])), int(float(row["y"])), 10, 10)]
    assert center


def test_active_directory_contains_only_v2():
    root = active_synthetic_dir()
    names = sorted(p.name for p in root.iterdir() if p.is_dir() and (p / "die_attempts.csv").is_file())
    assert names == [ACTIVE]
    assert not any(name.startswith("ds_") for name in names)


def test_champion_artifact_untouched():
    from yield_improvement.model_lifecycle.hashes import hash_files
    from yield_improvement.model_lifecycle.registry import default_paths

    hashes = hash_files(default_paths().version_dir("yi_ml_v1"))
    assert hashes["model.pkl"] == "cab3a1b74560263b59b8d6c95f852b15fc91d7a0b91f311576a10aa11aeb2d70"
    assert (repo_root() / "artifacts" / "ml" / "yi_ml_v1" / "model.pkl").is_file()
