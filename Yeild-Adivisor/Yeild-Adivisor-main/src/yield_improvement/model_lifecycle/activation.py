"""Explicit human approval and activation. Approval never activates."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from yield_improvement.ml.benchmark import ACTIVE_FEATURE_CONTRACT
from yield_improvement.model_lifecycle.hashes import hash_files
from yield_improvement.model_lifecycle.registry import (
    CHAMPION_VERSION,
    LifecyclePaths,
    default_paths,
    get_record,
    load_registry,
    transition,
)
from yield_improvement.model_lifecycle.safety import assert_production_invariants, safety_payload
from yield_improvement.model_lifecycle.states import LifecycleError
from yield_improvement.model_lifecycle.training import CANDIDATE_FILES
from yield_improvement.model_lifecycle.validation import collect_validation_issues
from yield_improvement.model_lifecycle.versioning import parse_version


def approve_candidate(
    version: str,
    *,
    approved_by: str,
    paths: LifecyclePaths | None = None,
    reason: str = "human_approval",
) -> dict[str, Any]:
    assert_production_invariants()
    paths = paths or default_paths()
    if not approved_by or approved_by.strip() in {"", "unavailable"}:
        raise LifecycleError("approval requires an explicit --approved-by human identifier")
    registry = load_registry(paths)
    record = get_record(registry, version)
    if record["state"] != "VALIDATED":
        raise LifecycleError(f"approve requires VALIDATED, found {record['state']}")
    updated = transition(
        paths,
        version,
        "APPROVED",
        event="MODEL_APPROVED",
        actor=approved_by.strip(),
        reason=reason,
        extra={
            "approved_by": approved_by.strip(),
            "approved_at": None,  # filled below from event
            "notes": "Approved. Not active. Activation is a separate command.",
        },
    )
    event = updated.get("_event") or {}
    extra = {
        "approved_by": approved_by.strip(),
        "approved_at": event.get("timestamp"),
        "approval_event_id": event.get("event_id"),
        "notes": "Approved. Not active. Activation is a separate command.",
    }
    # Re-load and persist approval metadata without changing state again.
    registry = load_registry(paths)
    record = dict(get_record(registry, version))
    record.update(extra)
    from yield_improvement.model_lifecycle.registry import put_record, save_registry

    put_record(registry, record)
    save_registry(paths, registry)
    return {
        "model_version": version,
        "state": "APPROVED",
        "approved_by": extra["approved_by"],
        "approved_at": extra["approved_at"],
        "approval_event_id": extra["approval_event_id"],
        "activated": False,
        "active_version": registry.get("active_version"),
        **safety_payload(),
    }


def _assert_activatable(version: str, paths: LifecyclePaths) -> dict[str, Any]:
    registry = load_registry(paths)
    record = get_record(registry, version)
    parsed = parse_version(version)
    if record["state"] != "APPROVED":
        raise LifecycleError(f"activate requires APPROVED, found {record['state']}")
    if record.get("approved_by") in {None, "", "unavailable"}:
        raise LifecycleError("activate requires recorded human approval metadata")
    if parsed["is_candidate"]:
        dest = paths.version_dir(version)
        actual = hash_files(dest, CANDIDATE_FILES)
        expected = record.get("artifact_hashes") or {}
        if actual != expected:
            raise LifecycleError("activate refused: artifact hash mismatch")
        issues = collect_validation_issues(version, paths=paths)
        if issues:
            raise LifecycleError("activate refused: validation issues remain")
        meta_features = record.get("feature_contract") or []
        if set(ACTIVE_FEATURE_CONTRACT) - set(meta_features):
            raise LifecycleError("activate refused: feature contract mismatch")
    return record


def activate_candidate(
    version: str,
    *,
    activated_by: str,
    paths: LifecyclePaths | None = None,
    reason: str = "human_activation",
) -> dict[str, Any]:
    """Pointer-based activation. Does not copy files into yi_ml_v1/."""
    assert_production_invariants()
    paths = paths or default_paths()
    if not activated_by or not activated_by.strip():
        raise LifecycleError("activation requires an explicit --activated-by human identifier")
    if Path(version).exists() and ("/" in version or "\\" in version):
        raise LifecycleError("arbitrary paths cannot be activated; pass a registered model_version")
    _assert_activatable(version, paths)
    updated = transition(
        paths,
        version,
        "ACTIVE",
        event="MODEL_ACTIVATED",
        actor=activated_by.strip(),
        reason=reason,
        extra={"notes": "Activated by explicit human command. Previous champion retired, not deleted."},
    )
    registry = load_registry(paths)
    return {
        "model_version": version,
        "state": "ACTIVE",
        "activated_by": activated_by.strip(),
        "activated_at": updated.get("activated_at"),
        "previous_champion": CHAMPION_VERSION if version != CHAMPION_VERSION else None,
        "active_version": registry.get("active_version"),
        **safety_payload(),
    }


def reject_candidate(
    version: str,
    *,
    rejected_by: str = "unavailable",
    reason: str,
    paths: LifecyclePaths | None = None,
) -> dict[str, Any]:
    assert_production_invariants()
    paths = paths or default_paths()
    record = get_record(load_registry(paths), version)
    if record["state"] not in {"CANDIDATE", "VALIDATED", "APPROVED"}:
        raise LifecycleError(f"cannot reject {record['state']}")
    transition(
        paths,
        version,
        "REJECTED",
        event="MODEL_REJECTED",
        actor=rejected_by or "unavailable",
        reason=reason,
        extra={"validation_status": "REJECTED", "notes": reason},
    )
    return {"model_version": version, "state": "REJECTED", **safety_payload()}
