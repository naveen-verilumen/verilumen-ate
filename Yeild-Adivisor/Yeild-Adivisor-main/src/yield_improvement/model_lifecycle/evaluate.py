"""Candidate evaluation. Uses Phase 8B LOLO protocol. Never activates."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from yield_improvement.config.loader import AppConfig, load_config
from yield_improvement.ml.config import load_ml_config
from yield_improvement.ml.dataset import load_ml_dataset
from yield_improvement.ml.benchmark import ACTIVE_FEATURE_CONTRACT, run_lolo_models
from yield_improvement.model_lifecycle.audit import append_event
from yield_improvement.model_lifecycle.hashes import dumps, hash_files, json_safe
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
from yield_improvement.model_lifecycle.training import CANDIDATE_FILES
from yield_improvement.model_lifecycle.versioning import parse_version, APPROVED_ARCHITECTURE


def evaluate_version(
    version: str,
    *,
    paths: LifecyclePaths | None = None,
    config: AppConfig | None = None,
    dataset_dir: str | Path | None = None,
) -> dict[str, Any]:
    assert_production_invariants()
    paths = paths or default_paths()
    before = champion_hashes(paths)
    registry = load_registry(paths)
    record = get_record(registry, version)
    parsed = parse_version(version)
    dest = paths.version_dir(version)
    if parsed["is_candidate"] and not (dest / "model.pkl").is_file():
        raise LifecycleError(f"candidate {version} has not been trained")
    prepare = {}
    if (dest / "prepare.json").is_file():
        prepare = json.loads((dest / "prepare.json").read_text(encoding="utf-8"))
    data_dir = Path(dataset_dir or prepare.get("dataset_dir") or record.get("dataset_dir") or "")
    if not data_dir or not data_dir.is_dir():
        raise LifecycleError("evaluate requires a dataset_dir")
    app = config or load_config()
    cfg = load_ml_config()
    data = load_ml_dataset(data_dir, config=app)
    architecture = APPROVED_ARCHITECTURE
    bench = run_lolo_models(data, model_names=[architecture], cfg=cfg, with_importance=True)
    model_block = bench["models"][architecture]
    payload = {
        "model_version": version,
        "architecture": architecture,
        "split_strategy": bench["split_strategy"],
        "n_lots": bench["n_lots"],
        "n_samples": bench["n_samples"],
        "n_positives": bench["n_positives"],
        "same_folds": True,
        "feature_contract": list(ACTIVE_FEATURE_CONTRACT),
        "feature_names": model_block["feature_names"],
        "fold_assignments": bench["fold_assignments"],
        "raw_metrics": model_block["raw"],
        "calibrated_metrics": model_block["calibrated"],
        "per_lot_metrics": {"raw": model_block["per_lot_raw"], "calibrated": model_block["per_lot_calibrated"]},
        "lot_stability": model_block["lot_stability_raw"],
        "feature_importance_stability": model_block["feature_importance_stability"],
        "operational": {
            "train_seconds": model_block["train_seconds"],
            "inference_seconds": model_block["inference_seconds"],
            "complexity": model_block["complexity"],
        },
        "calibration_analysis": {
            "raw_brier": model_block["raw"].get("brier"),
            "calibrated_brier": model_block["calibrated"].get("brier"),
            "raw_log_loss": model_block["raw"].get("log_loss"),
            "calibrated_log_loss": model_block["calibrated"].get("log_loss"),
            "raw_ece": model_block["raw"].get("ece"),
            "calibrated_ece": model_block["calibrated"].get("ece"),
            "raw_reliability_bins": model_block["raw"].get("reliability_bins"),
            "calibrated_reliability_bins": model_block["calibrated"].get("reliability_bins"),
        },
        "activated": False,
        **safety_payload(),
    }
    out_path = paths.evaluation_path(version)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(dumps(json_safe(payload)), encoding="utf-8")
    if parsed["is_candidate"]:
        hashes = hash_files(dest, CANDIDATE_FILES)
        metrics_path = dest / "metrics.json"
        metrics_path.write_text(
            dumps({"model_name": architecture, "metrics": payload["raw_metrics"], "disclaimer": "Predictive only."}),
            encoding="utf-8",
        )
        hashes = hash_files(dest, CANDIDATE_FILES)
        (dest / "hashes.json").write_text(dumps(hashes), encoding="utf-8")
        record = dict(record)
        record["artifact_hashes"] = hashes
        record["evaluation_result"] = {
            "raw_metrics": payload["raw_metrics"],
            "calibrated_metrics": payload["calibrated_metrics"],
            "lot_stability": payload["lot_stability"],
            "n_lots": payload["n_lots"],
        }
        put_record(registry, record)
        save_registry(paths, registry)
    else:
        record = dict(record)
        record["evaluation_result"] = {
            "raw_metrics": payload["raw_metrics"],
            "calibrated_metrics": payload["calibrated_metrics"],
            "lot_stability": payload["lot_stability"],
            "n_lots": payload["n_lots"],
            "source": "lifecycle_evaluate_sidecar",
        }
        put_record(registry, record)
        save_registry(paths, registry)
    append_event(
        paths.audit_path,
        {
            "event_type": "MODEL_EVALUATED",
            "model_version": version,
            "previous_state": record["state"],
            "new_state": record["state"],
            "actor": "unavailable",
            "reason": "retrain_evaluate",
            "artifact_hashes": record.get("artifact_hashes") or {},
            "parent_version": record.get("parent_model_version"),
        },
    )
    assert_champion_unchanged(paths, before)
    if paths.root == default_paths().root and load_registry(paths).get("active_version") != CHAMPION_VERSION:
        raise LifecycleError("evaluate must not change the active champion")
    payload["state"] = record["state"]
    return payload
