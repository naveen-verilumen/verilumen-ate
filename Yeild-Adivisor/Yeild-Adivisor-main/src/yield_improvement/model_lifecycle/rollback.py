"""Explicit rollback to a registered retired model. Never copies arbitrary files."""

from __future__ import annotations

from typing import Any

from yield_improvement.model_lifecycle.hashes import hash_files
from yield_improvement.model_lifecycle.registry import (
    LifecyclePaths,
    default_paths,
    get_record,
    load_registry,
    transition,
)
from yield_improvement.model_lifecycle.safety import assert_production_invariants, safety_payload
from yield_improvement.model_lifecycle.states import LifecycleError
from yield_improvement.model_lifecycle.training import CANDIDATE_FILES
from yield_improvement.model_lifecycle.versioning import parse_version
from yield_improvement.model_lifecycle.hashes import CHAMPION_FILES


def rollback_to(
    target: str,
    *,
    rolled_back_by: str,
    paths: LifecyclePaths | None = None,
    reason: str = "human_rollback",
) -> dict[str, Any]:
    assert_production_invariants()
    paths = paths or default_paths()
    if not rolled_back_by or not rolled_back_by.strip():
        raise LifecycleError("rollback requires an explicit --rolled-back-by human identifier")
    registry = load_registry(paths)
    record = get_record(registry, target)
    if record["state"] not in {"RETIRED", "ACTIVE"}:
        raise LifecycleError(f"rollback target must be RETIRED or ACTIVE, found {record['state']}")
    dest = paths.version_dir(target)
    names = CANDIDATE_FILES if parse_version(target)["is_candidate"] else CHAMPION_FILES
    actual = hash_files(dest, names)
    expected = record.get("artifact_hashes") or {}
    if expected and actual != expected:
        raise LifecycleError("rollback refused: target artifact hash mismatch")
    if record.get("feature_contract_version") is None:
        raise LifecycleError("rollback refused: feature contract missing")
    if record["state"] == "ACTIVE":
        return {
            "model_version": target,
            "state": "ACTIVE",
            "note": "Target is already ACTIVE; no pointer change.",
            **safety_payload(),
        }
    updated = transition(
        paths,
        target,
        "ACTIVE",
        event="MODEL_ROLLED_BACK",
        actor=rolled_back_by.strip(),
        reason=reason,
        extra={"notes": "Rolled back by explicit human command. Displaced model retired, not deleted."},
    )
    registry = load_registry(paths)
    return {
        "model_version": target,
        "state": "ACTIVE",
        "rolled_back_by": rolled_back_by.strip(),
        "activated_at": updated.get("activated_at"),
        "active_version": registry.get("active_version"),
        **safety_payload(),
    }
