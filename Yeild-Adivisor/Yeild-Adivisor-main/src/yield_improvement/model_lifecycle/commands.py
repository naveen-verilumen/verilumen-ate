"""Public lifecycle commands used by the CLI. No automatic train/activate."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from yield_improvement.model_lifecycle.activation import activate_candidate, approve_candidate, reject_candidate
from yield_improvement.model_lifecycle.comparison import compare_candidate
from yield_improvement.model_lifecycle.evaluate import evaluate_version
from yield_improvement.model_lifecycle.registry import (
    CHAMPION_VERSION,
    LifecyclePaths,
    bootstrap_champion,
    default_paths,
    get_record,
    history_for,
    load_registry,
)
from yield_improvement.model_lifecycle.rollback import rollback_to
from yield_improvement.model_lifecycle.safety import assert_production_invariants, safety_payload
from yield_improvement.model_lifecycle.training import prepare_candidate, train_candidate
from yield_improvement.model_lifecycle.validation import validate_candidate
from yield_improvement.model_lifecycle.verify import verify_registry


def list_models(paths: LifecyclePaths | None = None) -> dict[str, Any]:
    assert_production_invariants()
    paths = paths or default_paths()
    bootstrap_champion(paths)
    registry = load_registry(paths)
    rows = []
    for version, rec in sorted(registry.get("models", {}).items()):
        rows.append(
            {
                "version": version,
                "architecture": rec.get("architecture"),
                "state": rec.get("state"),
                "created_at": rec.get("created_at"),
                "parent": rec.get("parent_model_version"),
                "validation_status": rec.get("validation_status"),
            }
        )
    return {"models": rows, "active_version": registry.get("active_version"), **safety_payload()}


def inspect_model(version: str, *, paths: LifecyclePaths | None = None) -> dict[str, Any]:
    assert_production_invariants()
    paths = paths or default_paths()
    bootstrap_champion(paths)
    registry = load_registry(paths)
    record = get_record(registry, version)
    return {
        "record": record,
        "artifact_hashes": record.get("artifact_hashes"),
        "evaluation_summary": record.get("evaluation_result"),
        "feature_contract": record.get("feature_contract"),
        "lifecycle_history": history_for(paths, version),
        **safety_payload(),
    }


def resolve_active_dir(paths: LifecyclePaths | None = None) -> Path:
    paths = paths or default_paths()
    registry = load_registry(paths)
    version = registry.get("active_version") or CHAMPION_VERSION
    if version not in (registry.get("models") or {}):
        bootstrap_champion(paths)
        version = CHAMPION_VERSION
    return paths.version_dir(version)


__all__ = [
    "prepare_candidate",
    "train_candidate",
    "evaluate_version",
    "compare_candidate",
    "validate_candidate",
    "approve_candidate",
    "activate_candidate",
    "reject_candidate",
    "rollback_to",
    "list_models",
    "inspect_model",
    "verify_registry",
    "resolve_active_dir",
]
