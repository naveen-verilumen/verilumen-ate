"""V2 synthetic test catalog overlay. Display-only; IDs and analysis stay unchanged."""

from __future__ import annotations

import csv
import hashlib

import yaml

from yield_improvement.config.test_catalog import (
    NO_SEMANTIC_NAME,
    catalog_by_id,
    format_test_label,
    load_v2_test_catalog,
    _load_v2_test_catalog_cached,
    _load_yaml_cached,
    public_test_catalog,
)
from yield_improvement.model_lifecycle.hashes import hash_files
from yield_improvement.model_lifecycle.registry import default_paths
from yield_improvement.utils.paths import active_synthetic_dir, configs_dir

CHAMPION_HASHES = {
    "feature_list.json": "3e4db1e3de47382f5533fe0e54d442f638f83e4bac7b0eeb2c7da6364462e0d7",
    "metadata.json": "6a3ffa163e808042c5cd08d270c0d7fe042e42d977a1b166e88ef2d7b37d71ad",
    "metrics.json": "16ea9d76745142efc8f2b61eee28ce614cd255fa36c42a4efe6aedfdabadddec",
    "model.pkl": "cab3a1b74560263b59b8d6c95f852b15fc91d7a0b91f311576a10aa11aeb2d70",
}

TEST_RESULTS_HASH = "843f6c38c20aa5744bd9380c2f341706a124aa33552a3b1020d62341e6ed0e9b"
UNCLASSIFIED = "Unclassified V2 Test"

GENERATOR_SLOT_NAMES = {
    "T001": "CONTINUITY",
    "T002": "OPENS",
    "T003": "SHORTS",
    "T004": "CONTACT",
    "T005": "IDDQ",
    "T006": "VMIN",
    "T007": "VMAX",
    "T008": "LEAKAGE",
    "T009": "FUNCTIONAL",
    "T010": "SCAN",
}


def _reload_catalog() -> None:
    _load_v2_test_catalog_cached.cache_clear()
    _load_yaml_cached.cache_clear()


def _generator_tests() -> list[dict]:
    path = configs_dir() / "synthetic_v2.yaml"
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    return list(payload["tests"])


def test_catalog_display_names_copy_generator_program_slots():
    _reload_catalog()
    payload = load_v2_test_catalog()
    by_id = catalog_by_id()
    public = public_test_catalog()
    assert payload["source"] == "SYNTHETIC_V2_GENERATOR_PROGRAM_SLOTS"
    assert list(by_id) == [f"T{i:03d}" for i in range(1, 11)]
    assert len(public["tests"]) == 10
    gen_by_id = {row["test_id"]: row for row in _generator_tests()}
    assert set(gen_by_id) == set(GENERATOR_SLOT_NAMES)
    for test_id, slot_name in GENERATOR_SLOT_NAMES.items():
        assert gen_by_id[test_id]["failure_code"] == slot_name
        row = by_id[test_id]
        assert row["test_name"] == slot_name
        assert row["test_type"] == slot_name
        assert row["classified"] is False
        assert UNCLASSIFIED not in str(row["test_name"])
        assert format_test_label(test_id) == f"{test_id} — {slot_name}"
    for row in public["tests"]:
        assert UNCLASSIFIED not in row["test_name"]
        assert UNCLASSIFIED not in row["display_label"]
        assert row["display_label"] == f"{row['test_id']} — {row['test_name']}"
        assert row["test_name"] == GENERATOR_SLOT_NAMES[row["test_id"]]


def test_unknown_txxx_does_not_use_unclassified():
    _reload_catalog()
    label = format_test_label("T099")
    assert label == f"T099 — {NO_SEMANTIC_NAME}"
    assert UNCLASSIFIED not in label


def test_format_test_label_uses_generator_slots_for_all_ten_ids():
    _reload_catalog()
    stale = {
        "T004": {"test_id": "T004", "test_name": "Functional Test", "test_type": "FUNCTIONAL"},
        "T003": {"test_id": "T003", "test_name": "Leakage Test", "test_type": "LEAKAGE"},
        "T007": {"test_id": "T007", "test_name": "Unclassified V2 Test", "test_type": "UNCLASSIFIED"},
    }
    for test_id, slot_name in GENERATOR_SLOT_NAMES.items():
        assert format_test_label(test_id) == f"{test_id} — {slot_name}"
        assert format_test_label(test_id.lower()) == f"{test_id} — {slot_name}"
        assert format_test_label(f" {test_id} ") == f"{test_id} — {slot_name}"
    assert format_test_label("T004", stale) == "T004 — CONTACT"
    assert format_test_label("T003", stale) == "T003 — SHORTS"
    assert format_test_label("T007", stale) == "T007 — VMAX"
    public = public_test_catalog()
    by_id = {row["test_id"]: row for row in public["tests"]}
    for test_id, slot_name in GENERATOR_SLOT_NAMES.items():
        assert by_id[test_id]["test_name"] == slot_name
        assert by_id[test_id]["test_type"] == slot_name
        assert by_id[test_id]["display_label"] == f"{test_id} — {slot_name}"
        assert "UNCLASSIFIED" not in by_id[test_id]["test_name"]
        assert UNCLASSIFIED not in by_id[test_id]["display_label"]


def test_non_test_keys_are_unchanged():
    assert format_test_label("CONTACT_FAIL") == "CONTACT_FAIL"
    assert format_test_label("PROCESS.LOT_VARIATION") == "PROCESS.LOT_VARIATION"


def test_public_catalog_keeps_test_id():
    _reload_catalog()
    public = public_test_catalog()
    t004 = next(row for row in public["tests"] if row["test_id"] == "T004")
    assert t004["test_id"] == "T004"
    assert t004["test_name"] == "CONTACT"
    assert t004["test_type"] == "CONTACT"
    assert t004["display_label"] == "T004 — CONTACT"


def test_fail_rows_keep_generator_failure_codes_and_dataset_bytes():
    path = active_synthetic_dir() / "yi_synthetic_v2" / "test_results.csv"
    assert hashlib.sha256(path.read_bytes()).hexdigest() == TEST_RESULTS_HASH
    observed: dict[str, set[str]] = {test_id: set() for test_id in GENERATOR_SLOT_NAMES}
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if row["test_pass_fail"] != "FAIL":
                continue
            observed[row["test_id"]].add(row["failure_code"])
    for test_id, slot_name in GENERATOR_SLOT_NAMES.items():
        assert observed[test_id] == {slot_name}


def test_champion_untouched_by_catalog():
    assert hash_files(default_paths().version_dir("yi_ml_v1")) == CHAMPION_HASHES
