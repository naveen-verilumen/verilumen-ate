"""Validation gate. Passing evaluation is not approval and not activation."""

from __future__ import annotations

import json
from typing import Any

from yield_improvement.ml.benchmark import ACTIVE_FEATURE_CONTRACT, FORBIDDEN_FEATURES
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

REQUIRED_METRIC_KEYS = (
    "roc_auc",
    "pr_auc",
    "precision",
    "recall",
    "f1",
    "balanced_accuracy",
    "brier",
    "log_loss",
    "failure_capture_at_top_5_percent",
    "failure_capture_at_top_10_percent",
    "failure_capture_at_top_20_percent",
)


def _fail(kind: str, message: str) -> dict[str, Any]:
    return {"ok": False, "kind": kind, "message": message}


def collect_validation_issues(version: str, *, paths: LifecyclePaths) -> list[dict[str, Any]]:
    registry = load_registry(paths)
    record = get_record(registry, version)
    issues: list[dict[str, Any]] = []
    parsed = parse_version(version)
    dest = paths.version_dir(version)
    if parsed["is_candidate"]:
        try:
            actual = hash_files(dest, CANDIDATE_FILES)
        except LifecycleError as exc:
            issues.append(_fail("schema", str(exc)))
            return issues
        expected = record.get("artifact_hashes") or {}
        if expected and expected != actual:
            issues.append(_fail("hash", "artifact hashes do not match the registry"))
        meta_path = dest / "metadata.json"
        if not meta_path.is_file():
            issues.append(_fail("schema", "metadata.json missing"))
        else:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            names = [n.lower() for n in meta.get("feature_names") or []]
            if any(n in FORBIDDEN_FEATURES or n in {"scenario_id", "true_cause"} for n in names):
                issues.append(_fail("leakage", "forbidden feature in candidate metadata"))
            contract = list(meta.get("feature_contract") or names)
            if contract[:16] != list(ACTIVE_FEATURE_CONTRACT) and set(ACTIVE_FEATURE_CONTRACT) - set(contract):
                issues.append(_fail("feature_contract", "feature contract does not match Phase 7/8 allowlist"))
            if meta.get("seed") is None:
                issues.append(_fail("reproducibility", "seed missing"))
        eval_path = paths.evaluation_path(version)
        if not eval_path.is_file() and not record.get("evaluation_result"):
            issues.append(_fail("incomplete", "LOLO evaluation is missing"))
        else:
            payload = record.get("evaluation_result") or {}
            if eval_path.is_file():
                payload = json.loads(eval_path.read_text(encoding="utf-8"))
            raw = payload.get("raw_metrics") or payload.get("metrics") or {}
            cal = payload.get("calibrated_metrics") or {}
            if payload.get("split_strategy") not in {None, "leave_one_lot_out"} and "leave_one_lot_out" not in str(
                payload.get("split_strategy")
            ):
                issues.append(_fail("split", "evaluation is not leave-one-lot-out"))
            for key in REQUIRED_METRIC_KEYS:
                if raw.get(key) is None and key not in {"failure_capture_at_top_5_percent"}:
                    issues.append(_fail("metrics", f"missing raw metric {key}"))
            if cal and cal.get("brier") is None:
                issues.append(_fail("calibration", "calibrated Brier missing"))
            if not payload.get("lot_stability") and not (record.get("evaluation_result") or {}).get("lot_stability"):
                issues.append(_fail("metrics", "lot stability missing"))
        if record.get("production_authorized") is True:
            issues.append(_fail("safety", "production_authorized must be false"))
    else:
        issues.append(_fail("state", "only candidates can become VALIDATED through this gate"))
    if record["state"] not in {"CANDIDATE", "VALIDATED", "APPROVED"}:
        issues.append(_fail("state", f"cannot validate from {record['state']}"))
    return issues


def validate_candidate(
    version: str,
    *,
    paths: LifecyclePaths | None = None,
) -> dict[str, Any]:
    assert_production_invariants()
    paths = paths or default_paths()
    issues = collect_validation_issues(version, paths=paths)
    hard = [i for i in issues if i["kind"] not in {"incomplete"}]
    incomplete = [i for i in issues if i["kind"] == "incomplete"]
    registry = load_registry(paths)
    record = get_record(registry, version)
    if hard:
        if record["state"] == "CANDIDATE":
            transition(
                paths,
                version,
                "REJECTED",
                event="MODEL_REJECTED",
                actor="unavailable",
                reason="; ".join(i["message"] for i in hard),
                extra={"validation_status": "FAILED", "notes": "Validation failed; candidate rejected."},
            )
        return {
            "model_version": version,
            "validated": False,
            "state": "REJECTED" if record["state"] == "CANDIDATE" else record["state"],
            "issues": hard + incomplete,
            **safety_payload(),
        }
    if incomplete:
        return {
            "model_version": version,
            "validated": False,
            "state": record["state"],
            "issues": incomplete,
            **safety_payload(),
        }
    if record["state"] == "CANDIDATE":
        transition(
            paths,
            version,
            "VALIDATED",
            event="MODEL_VALIDATED",
            actor="unavailable",
            reason="mandatory_validation_passed",
            extra={"validation_status": "PASSED", "notes": "Validated. Not approved. Not active."},
        )
    return {
        "model_version": version,
        "validated": True,
        "state": "VALIDATED",
        "issues": [],
        **safety_payload(),
    }
