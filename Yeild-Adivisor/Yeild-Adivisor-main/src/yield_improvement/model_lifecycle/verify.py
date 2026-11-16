"""Registry integrity verification. Fail closed. Do not auto-repair."""

from __future__ import annotations

from typing import Any

from yield_improvement.model_lifecycle.audit import read_events
from yield_improvement.model_lifecycle.hashes import CHAMPION_FILES, hash_files
from yield_improvement.model_lifecycle.registry import (
    CHAMPION_VERSION,
    LifecyclePaths,
    default_paths,
    load_registry,
)
from yield_improvement.model_lifecycle.safety import assert_production_invariants, safety_payload
from yield_improvement.model_lifecycle.states import ALLOWED_TRANSITIONS, LifecycleError
from yield_improvement.model_lifecycle.training import CANDIDATE_FILES
from yield_improvement.model_lifecycle.versioning import parse_version


def verify_registry(paths: LifecyclePaths | None = None) -> dict[str, Any]:
    assert_production_invariants()
    paths = paths or default_paths()
    issues: list[str] = []
    try:
        registry = load_registry(paths)
    except LifecycleError as exc:
        return {"status": "NEEDS_REVIEW", "issues": [str(exc)], **safety_payload()}
    models = registry.get("models") or {}
    if len(models) != len(set(models)):
        issues.append("duplicate version keys")
    active = [v for v, rec in models.items() if rec.get("state") == "ACTIVE"]
    if len(active) != 1:
        issues.append(f"expected exactly one ACTIVE model, found {active}")
    if registry.get("active_version") not in models and models:
        issues.append("active_version pointer is missing from models")
    if registry.get("active_version") and registry["active_version"] not in active and active:
        issues.append("active_version pointer does not match ACTIVE records")
    seen_versions = []
    for version, rec in models.items():
        if version in seen_versions:
            issues.append(f"duplicate version {version}")
        seen_versions.append(version)
        try:
            parse_version(version)
        except LifecycleError as exc:
            issues.append(str(exc))
        dest = paths.version_dir(version)
        names = CANDIDATE_FILES if parse_version(version)["is_candidate"] else CHAMPION_FILES
        if dest.is_dir() and (dest / "model.pkl").is_file():
            try:
                actual = hash_files(dest, names)
                expected = rec.get("artifact_hashes") or {}
                if expected and actual != expected:
                    issues.append(f"hash mismatch for {version}")
            except LifecycleError as exc:
                issues.append(str(exc))
        if rec.get("state") == "APPROVED":
            if rec.get("approved_by") in {None, "", "unavailable"} or not rec.get("approval_event_id"):
                issues.append(f"APPROVED model {version} missing approval metadata")
        if rec.get("state") == "ACTIVE":
            if not rec.get("activated_at"):
                issues.append(f"ACTIVE model {version} missing activation timestamp")
        if rec.get("state") == "RETIRED" and not rec.get("retired_at"):
            issues.append(f"RETIRED model {version} missing retired_at")
        if rec.get("production_authorized") is True:
            issues.append(f"{version} production_authorized is not false")
    events = read_events(paths.audit_path)
    ids = [e.get("event_id") for e in events]
    if len(ids) != len(set(ids)):
        issues.append("audit trail has duplicate event_id values")
    for event in events:
        prev, new = event.get("previous_state"), event.get("new_state")
        if prev and new and event.get("event_type") not in {"MODEL_EVALUATED", "MODEL_COMPARED"}:
            if prev == new:
                continue
            if (prev, new) not in ALLOWED_TRANSITIONS and not (
                prev is None and new in {"CANDIDATE", "ACTIVE"}
            ):
                issues.append(f"audit has invalid transition {prev}->{new} for {event.get('event_id')}")
    status = "OK" if not issues else "NEEDS_REVIEW"
    return {
        "status": status,
        "issues": issues,
        "active_version": registry.get("active_version") or CHAMPION_VERSION,
        "n_models": len(models),
        "n_events": len(events),
        **safety_payload(),
    }
