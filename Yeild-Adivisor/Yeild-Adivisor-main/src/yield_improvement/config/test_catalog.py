"""V2 synthetic test catalog overlay. Display metadata only; IDs stay T001–T010."""

from __future__ import annotations

import re
from pathlib import Path
from functools import lru_cache
from typing import Any

import yaml

from yield_improvement.utils.errors import ConfigError
from yield_improvement.utils.paths import configs_dir

TEST_ID_RE = re.compile(r"^T\d{3}$")
TEST_ID_TOKEN_RE = re.compile(r"\bT\d{3}\b")
NO_SEMANTIC_NAME = "No semantic test name defined in V2 source"


def _catalog_path():
    return configs_dir() / "v2_test_catalog.yaml"


def _generator_path():
    return configs_dir() / "synthetic_v2.yaml"


def normalize_test_id(test_id: str) -> str:
    key = str(test_id).strip().upper()
    if TEST_ID_RE.fullmatch(key):
        return key
    return str(test_id).strip()


@lru_cache(maxsize=4)
def _load_yaml_cached(path_str: str, mtime_ns: int) -> dict[str, Any]:
    payload = yaml.safe_load(Path(path_str).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ConfigError(f"YAML is not an object: {path_str}")
    return payload


def generator_program_slots() -> dict[str, str]:
    """Authoritative V2 display names: tests[].failure_code from synthetic_v2.yaml."""
    path = _generator_path()
    if not path.is_file():
        raise ConfigError(f"Missing V2 generator config: {path}")
    payload = _load_yaml_cached(str(path), path.stat().st_mtime_ns)
    slots: dict[str, str] = {}
    for row in payload.get("tests") or []:
        if not isinstance(row, dict):
            continue
        test_id = normalize_test_id(str(row.get("test_id") or ""))
        code = str(row.get("failure_code") or "").strip()
        if TEST_ID_RE.fullmatch(test_id) and code:
            slots[test_id] = code
    return slots


@lru_cache(maxsize=1)
def _load_v2_test_catalog_cached(mtime_ns: int) -> dict[str, Any]:
    path = _catalog_path()
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("tests"), list):
        raise ConfigError("v2_test_catalog.yaml must contain a tests list")
    return payload


def load_v2_test_catalog() -> dict[str, Any]:
    path = _catalog_path()
    if not path.is_file():
        raise ConfigError(f"Missing V2 test catalog: {path}")
    return _load_v2_test_catalog_cached(path.stat().st_mtime_ns)


def catalog_entries() -> list[dict[str, Any]]:
    return list(load_v2_test_catalog()["tests"])


def catalog_by_id() -> dict[str, dict[str, Any]]:
    return {normalize_test_id(str(row["test_id"])): row for row in catalog_entries() if row.get("test_id")}


def display_label(test_id: str, *, test_name: str | None = None) -> str:
    name = test_name or NO_SEMANTIC_NAME
    return f"{normalize_test_id(test_id)} — {name}"


def format_test_label(test_id: str, lookup: dict[str, dict[str, Any]] | None = None) -> str:
    """Map a machine test_id to a dashboard label. T001–T010 use generator failure_code."""
    key = normalize_test_id(test_id)
    slot = generator_program_slots().get(key)
    if slot:
        return display_label(key, test_name=slot)
    table = lookup if lookup is not None else catalog_by_id()
    entry = table.get(key) or table.get(str(test_id).strip())
    if entry is not None:
        return display_label(key, test_name=str(entry.get("test_name") or NO_SEMANTIC_NAME))
    if TEST_ID_RE.fullmatch(key):
        return display_label(key, test_name=NO_SEMANTIC_NAME)
    return str(test_id).strip()


def replace_test_ids_in_text(text: str, lookup: dict[str, dict[str, Any]] | None = None) -> str:
    def _sub(match: re.Match[str]) -> str:
        return format_test_label(match.group(0), lookup)

    return TEST_ID_TOKEN_RE.sub(_sub, text)


def public_test_catalog() -> dict[str, Any]:
    raw = load_v2_test_catalog()
    slots = generator_program_slots()
    tests: list[dict[str, Any]] = []
    for row in catalog_entries():
        test_id = normalize_test_id(str(row["test_id"]))
        test_name = slots.get(test_id) or str(row.get("test_name") or NO_SEMANTIC_NAME)
        tests.append(
            {
                "test_id": test_id,
                "test_name": test_name,
                "test_type": test_name,
                "description": str(row.get("description") or ""),
                "sequence_index": row.get("sequence_index"),
                "classified": bool(row.get("classified", False)),
                "display_label": display_label(test_id, test_name=test_name),
            }
        )
    missing = [tid for tid in slots if tid not in {row["test_id"] for row in tests}]
    for test_id in missing:
        test_name = slots[test_id]
        tests.append(
            {
                "test_id": test_id,
                "test_name": test_name,
                "test_type": test_name,
                "description": "",
                "sequence_index": int(test_id[1:]),
                "classified": False,
                "display_label": display_label(test_id, test_name=test_name),
            }
        )
    tests.sort(key=lambda row: row["test_id"])
    return {
        "catalog_id": raw.get("catalog_id"),
        "catalog_version": raw.get("catalog_version"),
        "dataset_id": raw.get("dataset_id"),
        "source": "SYNTHETIC_V2_GENERATOR_PROGRAM_SLOTS",
        "note": str(raw.get("note") or "").strip(),
        "tests": tests,
    }
