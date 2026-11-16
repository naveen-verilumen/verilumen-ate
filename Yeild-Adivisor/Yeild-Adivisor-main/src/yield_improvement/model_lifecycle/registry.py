"""On-disk registry. Champion status is a lifecycle property, not a metric ranking."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from yield_improvement.ml.benchmark import ACTIVE_FEATURE_CONTRACT
from yield_improvement.ml.config import load_ml_config
from yield_improvement.ml.pipeline import artifact_dir
from yield_improvement.model_lifecycle.audit import append_event, read_events, utc_now
from yield_improvement.model_lifecycle.hashes import CHAMPION_FILES, dumps, hash_files, json_safe
from yield_improvement.model_lifecycle.safety import assert_production_invariants, safety_payload
from yield_improvement.model_lifecycle.states import LifecycleError, ModelState, assert_transition
from yield_improvement.model_lifecycle.versioning import CHAMPION_ARCHITECTURE, parse_version
from yield_improvement.utils.paths import repo_root

REGISTRY_VERSION = "yi_ml_registry_v1"
CHAMPION_VERSION = "yi_ml_v1"


@dataclass
class LifecyclePaths:
    root: Path

    @property
    def registry_dir(self) -> Path:
        return self.root / "registry"

    @property
    def registry_path(self) -> Path:
        return self.registry_dir / "registry.json"

    @property
    def audit_path(self) -> Path:
        return self.registry_dir / "audit.jsonl"

    @property
    def candidates_dir(self) -> Path:
        return self.root / "candidates"

    @property
    def evaluations_dir(self) -> Path:
        return self.registry_dir / "evaluations"

    def version_dir(self, version: str) -> Path:
        parsed = parse_version(version)
        if parsed["is_candidate"]:
            return self.candidates_dir / version
        return self.root / version

    def evaluation_path(self, version: str) -> Path:
        parsed = parse_version(version)
        if parsed["is_candidate"]:
            return self.version_dir(version) / "evaluation.json"
        return self.evaluations_dir / f"{version}.json"


def default_paths() -> LifecyclePaths:
    return LifecyclePaths(root=repo_root() / "artifacts" / "ml")


def empty_registry() -> dict[str, Any]:
    return {
        "registry_version": REGISTRY_VERSION,
        "active_version": None,
        "models": {},
        **safety_payload(),
    }


def load_registry(paths: LifecyclePaths) -> dict[str, Any]:
    assert_production_invariants()
    if not paths.registry_path.is_file():
        return empty_registry()
    payload = json.loads(paths.registry_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise LifecycleError("registry.json is not an object")
    payload.setdefault("models", {})
    payload.setdefault("active_version", None)
    payload.setdefault("registry_version", REGISTRY_VERSION)
    payload.update(safety_payload())
    return payload


def save_registry(paths: LifecyclePaths, payload: dict[str, Any]) -> None:
    assert_production_invariants(payload)
    paths.registry_dir.mkdir(parents=True, exist_ok=True)
    body = dict(payload)
    body.update(safety_payload())
    paths.registry_path.write_text(dumps(body), encoding="utf-8")


def get_record(registry: dict[str, Any], version: str) -> dict[str, Any]:
    record = registry.get("models", {}).get(version)
    if not record:
        raise LifecycleError(f"unknown model version: {version}")
    return record


def put_record(registry: dict[str, Any], record: dict[str, Any]) -> None:
    version = record["model_version"]
    registry.setdefault("models", {})[version] = record
    if record.get("state") == "ACTIVE":
        registry["active_version"] = version


def champion_hashes(paths: LifecyclePaths) -> dict[str, str]:
    return hash_files(paths.version_dir(CHAMPION_VERSION), CHAMPION_FILES)


def assert_champion_unchanged(paths: LifecyclePaths, before: dict[str, str]) -> None:
    after = champion_hashes(paths)
    if before != after:
        raise LifecycleError(f"FAIL CLOSED: champion artifacts mutated: {before} vs {after}")


def new_record(
    *,
    version: str,
    architecture: str,
    state: ModelState,
    dataset_id: str | None,
    dataset_dir: str | None,
    parent: str | None,
    artifact_hashes: dict[str, str] | None = None,
    training_config_hash: str | None = None,
    notes: str = "",
    seed: int | None = None,
    python_version: str | None = None,
    sklearn_version: str | None = None,
    feature_contract: list[str] | None = None,
    feature_contract_version: str = "yi_ml_features_v1",
) -> dict[str, Any]:
    return {
        "model_version": version,
        "architecture": architecture,
        "state": state,
        "created_at": utc_now(),
        "dataset_id": dataset_id,
        "dataset_dir": dataset_dir,
        "feature_contract_version": feature_contract_version,
        "feature_contract": list(feature_contract or ACTIVE_FEATURE_CONTRACT),
        "training_config_hash": training_config_hash,
        "artifact_hashes": artifact_hashes or {},
        "evaluation_result": None,
        "parent_model_version": parent,
        "approved_by": "unavailable",
        "approved_at": None,
        "approval_event_id": None,
        "activated_by": None,
        "activated_at": None,
        "retired_at": None,
        "rollback_target": None,
        "notes": notes,
        "python_version": python_version,
        "sklearn_version": sklearn_version,
        "seed": seed,
        "validation_status": "PENDING",
        "comparison_status": None,
        **safety_payload(),
    }


def bootstrap_champion(paths: LifecyclePaths | None = None) -> dict[str, Any]:
    """Register existing yi_ml_v1 as ACTIVE. Does not retrain or rewrite champion files."""
    paths = paths or default_paths()
    before = champion_hashes(paths)
    registry = load_registry(paths)
    if CHAMPION_VERSION in registry.get("models", {}):
        assert_champion_unchanged(paths, before)
        return registry
    cfg = load_ml_config()
    folder = artifact_dir(cfg) if paths.root == default_paths().root else paths.version_dir(CHAMPION_VERSION)
    meta = {}
    meta_path = folder / "metadata.json"
    if meta_path.is_file():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    metrics = {}
    metrics_path = folder / "metrics.json"
    if metrics_path.is_file():
        metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    hashes = hash_files(folder, CHAMPION_FILES)
    record = new_record(
        version=CHAMPION_VERSION,
        architecture=CHAMPION_ARCHITECTURE,
        state="ACTIVE",
        dataset_id=meta.get("analysis_id"),
        dataset_dir=None,
        parent=None,
        artifact_hashes=hashes,
        training_config_hash=None,
        notes="Existing Phase 7 champion registered by Phase 9 bootstrap. Not retrained.",
        seed=meta.get("seed", cfg.seed),
        feature_contract=meta.get("feature_names") or list(ACTIVE_FEATURE_CONTRACT),
        feature_contract_version=meta.get("feature_set_version") or cfg.feature_set_version,
    )
    record["activated_by"] = "unavailable"
    record["activated_at"] = meta.get("trained_at") or utc_now()
    record["evaluation_result"] = {
        "source": "artifact_metrics_json",
        "metrics": metrics.get("metrics"),
        "model_name": metrics.get("model_name"),
        "note": "Bootstrap copy of persisted metrics. Not a new training run.",
    }
    record["validation_status"] = "BOOTSTRAPPED_ACTIVE"
    assert_transition(None, "ACTIVE", event="MODEL_CREATED")
    put_record(registry, record)
    registry["active_version"] = CHAMPION_VERSION
    save_registry(paths, registry)
    append_event(
        paths.audit_path,
        {
            "event_type": "MODEL_CREATED",
            "model_version": CHAMPION_VERSION,
            "previous_state": None,
            "new_state": "ACTIVE",
            "actor": "unavailable",
            "reason": "bootstrap_existing_champion",
            "artifact_hashes": hashes,
            "parent_version": None,
        },
    )
    append_event(
        paths.audit_path,
        {
            "event_type": "MODEL_ACTIVATED",
            "model_version": CHAMPION_VERSION,
            "previous_state": None,
            "new_state": "ACTIVE",
            "actor": "unavailable",
            "reason": "bootstrap_existing_champion",
            "artifact_hashes": hashes,
            "parent_version": None,
        },
    )
    assert_champion_unchanged(paths, before)
    return load_registry(paths)


def transition(
    paths: LifecyclePaths,
    version: str,
    new_state: ModelState,
    *,
    event: str,
    actor: str,
    reason: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    before = None
    if paths.version_dir(CHAMPION_VERSION).is_dir() and (paths.version_dir(CHAMPION_VERSION) / "model.pkl").is_file():
        before = hash_files(paths.version_dir(CHAMPION_VERSION), CHAMPION_FILES)
    registry = load_registry(paths)
    record = get_record(registry, version)
    previous = record["state"]
    assert_transition(previous, new_state, event=event)
    record = dict(record)
    record["state"] = new_state
    if extra:
        record.update(extra)
    if new_state == "ACTIVE":
        previous_active = registry.get("active_version")
        if previous_active and previous_active != version:
            old = dict(get_record(registry, previous_active))
            assert_transition(old["state"], "RETIRED", event="MODEL_RETIRED")
            old["state"] = "RETIRED"
            old["retired_at"] = utc_now()
            old["rollback_target"] = version
            put_record(registry, old)
            append_event(
                paths.audit_path,
                {
                    "event_type": "MODEL_RETIRED",
                    "model_version": previous_active,
                    "previous_state": "ACTIVE",
                    "new_state": "RETIRED",
                    "actor": actor or "unavailable",
                    "reason": reason,
                    "artifact_hashes": old.get("artifact_hashes") or {},
                    "parent_version": old.get("parent_model_version"),
                },
            )
        registry["active_version"] = version
        record["activated_by"] = actor or "unavailable"
        record["activated_at"] = utc_now()
    put_record(registry, record)
    save_registry(paths, registry)
    event_row = append_event(
        paths.audit_path,
        {
            "event_type": event,
            "model_version": version,
            "previous_state": previous,
            "new_state": new_state,
            "actor": actor or "unavailable",
            "reason": reason,
            "artifact_hashes": record.get("artifact_hashes") or {},
            "parent_version": record.get("parent_model_version"),
        },
    )
    if before is not None:
        assert_champion_unchanged(paths, before)
    record["_event"] = event_row
    return record


def history_for(paths: LifecyclePaths, version: str) -> list[dict[str, Any]]:
    return [row for row in read_events(paths.audit_path) if row.get("model_version") == version]
