"""Append-only JSONL audit trail. Historical events are never rewritten."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from yield_improvement.model_lifecycle.hashes import json_safe, sha256_bytes
from yield_improvement.model_lifecycle.safety import assert_production_invariants, safety_payload
from yield_improvement.model_lifecycle.states import EVENT_TYPES, LifecycleError


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def append_event(path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    assert_production_invariants()
    event_type = payload.get("event_type")
    if event_type not in EVENT_TYPES:
        raise LifecycleError(f"unknown audit event_type: {event_type}")
    body = {k: v for k, v in payload.items() if k != "event_id"}
    stamp = payload.get("timestamp") or utc_now()
    body["timestamp"] = stamp
    event_id = "evt-" + sha256_bytes(json.dumps(json_safe(body), sort_keys=True).encode("utf-8"))[:16]
    event = {
        "event_id": event_id,
        "timestamp": stamp,
        "event_type": event_type,
        "model_version": payload.get("model_version"),
        "previous_state": payload.get("previous_state"),
        "new_state": payload.get("new_state"),
        "actor": payload.get("actor") or "unavailable",
        "reason": payload.get("reason") or "",
        "artifact_hashes": payload.get("artifact_hashes") or {},
        "parent_version": payload.get("parent_version"),
        **safety_payload(),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(json_safe(event), sort_keys=True) + "\n")
    return event


def read_events(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rows.append(json.loads(line))
    return rows
