"""Candidate vs champion comparison. Not a single opaque score. Never activates."""

from __future__ import annotations

import json
from typing import Any

from yield_improvement.ml.config import load_ml_config
from yield_improvement.model_lifecycle.audit import append_event
from yield_improvement.model_lifecycle.hashes import dumps, json_safe
from yield_improvement.model_lifecycle.registry import (
    CHAMPION_VERSION,
    LifecyclePaths,
    assert_champion_unchanged,
    champion_hashes,
    default_paths,
    get_record,
    load_registry,
    put_record,
    save_registry,
)
from yield_improvement.model_lifecycle.safety import assert_production_invariants, safety_payload
from yield_improvement.model_lifecycle.states import LifecycleError

ComparisonStatus = str  # SUPERIOR | COMPARABLE | INFERIOR | INCONCLUSIVE


def _metric(block: dict[str, Any] | None, key: str) -> float | None:
    if not block:
        return None
    raw = block.get("raw_metrics") or block.get("metrics") or block
    if isinstance(raw, dict) and key in raw:
        val = raw.get(key)
        return None if val is None else float(val)
    val = block.get(key)
    return None if val is None else float(val)


def _stability(block: dict[str, Any] | None, key: str) -> float | None:
    if not block:
        return None
    stab = block.get("lot_stability") or {}
    row = stab.get(key) or {}
    std = row.get("std")
    return None if std is None else float(std)


def compare_candidate(
    candidate_version: str,
    champion_version: str = CHAMPION_VERSION,
    *,
    paths: LifecyclePaths | None = None,
) -> dict[str, Any]:
    assert_production_invariants()
    paths = paths or default_paths()
    before = champion_hashes(paths)
    registry = load_registry(paths)
    cand = get_record(registry, candidate_version)
    champ = get_record(registry, champion_version)
    cand_eval = cand.get("evaluation_result")
    champ_eval = champ.get("evaluation_result")
    cand_path = paths.evaluation_path(candidate_version)
    champ_path = paths.evaluation_path(champion_version)
    if cand_path.is_file():
        cand_eval = json.loads(cand_path.read_text(encoding="utf-8"))
    if champ_path.is_file():
        champ_eval = json.loads(champ_path.read_text(encoding="utf-8"))
    close = load_ml_config().selection.close_tolerance
    dimensions: dict[str, Any] = {}
    status: ComparisonStatus = "INCONCLUSIVE"
    reasons = [
        f"n_lots is small; conclusions are preliminary.",
        "No single metric selects the model. Calibrated metrics are not mixed with another model's raw scores.",
        "This comparison does not approve or activate any model.",
    ]
    if cand.get("dataset_id") and champ.get("dataset_id") and cand["dataset_id"] != champ["dataset_id"]:
        status = "INCONCLUSIVE"
        reasons.append("dataset_id differs; fail closed rather than comparing incomparable populations.")
    elif not cand_eval or not champ_eval:
        status = "INCONCLUSIVE"
        reasons.append("evaluation_result missing on candidate or champion.")
    else:
        keys = {
            "pr_auc": "higher",
            "roc_auc": "higher",
            "failure_capture_at_top_10_percent": "higher",
            "failure_capture_at_top_20_percent": "higher",
            "brier": "lower",
            "ece": "lower",
        }
        missing = []
        for key, direction in keys.items():
            a = _metric(cand_eval, key)
            b = _metric(champ_eval, key)
            if a is None or b is None:
                missing.append(key)
                dimensions[key] = {"candidate": a, "champion": b, "delta_candidate_minus_champion": None}
                continue
            delta = a - b
            dimensions[key] = {
                "candidate": a,
                "champion": b,
                "delta_candidate_minus_champion": delta,
                "better": ("candidate" if ((delta > 0) if direction == "higher" else (delta < 0)) else "champion")
                if abs(delta) > 1e-12
                else "tie",
            }
        cand_sd = _stability(cand_eval, "pr_auc")
        champ_sd = _stability(champ_eval, "pr_auc")
        dimensions["lot_pr_auc_std"] = {
            "candidate": cand_sd,
            "champion": champ_sd,
            "delta_candidate_minus_champion": None if cand_sd is None or champ_sd is None else cand_sd - champ_sd,
        }
        dimensions["complexity"] = {
            "candidate": cand.get("architecture"),
            "champion": champ.get("architecture"),
            "note": "Prefer simpler architecture when metrics are within close_tolerance.",
        }
        dimensions["dependency_burden"] = {
            "candidate": "sklearn_logistic",
            "champion": "sklearn_logistic",
        }
        if missing:
            status = "INCONCLUSIVE"
            reasons.append(f"missing metrics: {missing}")
        else:
            dpr = dimensions["pr_auc"]["delta_candidate_minus_champion"]
            cap10_c = dimensions["failure_capture_at_top_10_percent"]["candidate"]
            cap10_h = dimensions["failure_capture_at_top_10_percent"]["champion"]
            cap20_c = dimensions["failure_capture_at_top_20_percent"]["candidate"]
            cap20_h = dimensions["failure_capture_at_top_20_percent"]["champion"]
            capture_ok = cap10_c + 1e-12 >= cap10_h - 0.03 and cap20_c + 1e-12 >= cap20_h - 0.03
            stable_ok = cand_sd is None or champ_sd is None or cand_sd <= champ_sd + 0.03
            if abs(dpr) <= close and capture_ok:
                status = "COMPARABLE"
                reasons.append(f"PR-AUC difference {dpr:.4f} is within close_tolerance={close}.")
            elif dpr > close and capture_ok and stable_ok:
                status = "SUPERIOR"
                reasons.append("Candidate exceeds PR-AUC close_tolerance without losing capture or lot stability.")
            elif dpr < -close or not capture_ok:
                status = "INFERIOR"
                reasons.append("Candidate is below PR-AUC close_tolerance or loses diagnostic capture.")
            else:
                status = "INCONCLUSIVE"
                reasons.append("Mixed dimensions without a consistent advantage.")
            if cand_sd is None or champ_sd is None:
                if status == "SUPERIOR":
                    status = "INCONCLUSIVE"
                    reasons.append("Lot stability unavailable; fail closed instead of declaring SUPERIOR.")
    result = {
        "candidate_version": candidate_version,
        "champion_version": champion_version,
        "candidate_status": status,
        "close_tolerance": close,
        "dimensions": dimensions,
        "reasons": reasons,
        "n_lots": (cand_eval or {}).get("n_lots") or (champ_eval or {}).get("n_lots"),
        "activated": False,
        **safety_payload(),
    }
    dest = paths.version_dir(candidate_version)
    if dest.is_dir():
        (dest / "comparison.json").write_text(dumps(json_safe(result)), encoding="utf-8")
    cand = dict(cand)
    cand["comparison_status"] = status
    put_record(registry, cand)
    save_registry(paths, registry)
    append_event(
        paths.audit_path,
        {
            "event_type": "MODEL_COMPARED",
            "model_version": candidate_version,
            "previous_state": cand["state"],
            "new_state": cand["state"],
            "actor": "unavailable",
            "reason": f"compare_status={status}",
            "artifact_hashes": cand.get("artifact_hashes") or {},
            "parent_version": champion_version,
        },
    )
    assert_champion_unchanged(paths, before)
    return result
