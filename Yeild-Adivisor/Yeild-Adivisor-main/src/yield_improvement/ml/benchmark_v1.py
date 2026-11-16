"""Architecture benchmark on the V2 contract. Does not write yi_ml_v1 or earlier candidates."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd

from yield_improvement.ml.benchmark import (
    ACTIVE_FEATURE_CONTRACT,
    probe_extra_models,
    run_lolo_models,
)
from yield_improvement.ml.config import load_ml_config
from yield_improvement.ml.contracts import DISCLAIMER
from yield_improvement.ml.dataset import load_ml_dataset
from yield_improvement.ml.reliability import constant_references, ml_support_status
from yield_improvement.ml.v2_build import (
    DATASET_ID,
    EXPECTED_NEG,
    EXPECTED_POS,
    EXPECTED_ROWS,
    V2BuildError,
    assert_training_contract,
)
from yield_improvement.model_lifecycle.hashes import CHAMPION_FILES, hash_files, json_safe
from yield_improvement.model_lifecycle.registry import default_paths, load_registry
from yield_improvement.utils.paths import repo_root

BENCHMARK_ID = "benchmark_v1"
PROTECTED = ("yi_ml_v1", "yi_ml_v2", "yi_ml_v3_spatial", "yi_ml_v4")
DATASET_FILES = ("die_attempts.csv", "parametric_measurements.csv", "test_results.csv")
REGISTRY_HASH = "510218addf1c09fda4fe56d246ad040e68818d337a132fd907774dc8de88e9cd"
SEQUENCE_SLOTS = (
    ("T001", 1, "CONTINUITY"),
    ("T002", 2, "OPENS"),
    ("T003", 3, "SHORTS"),
    ("T004", 4, "CONTACT"),
    ("T005", 5, "IDDQ"),
    ("T006", 6, "VMIN"),
    ("T007", 7, "VMAX"),
    ("T008", 8, "LEAKAGE"),
    ("T009", 9, "FUNCTIONAL"),
    ("T010", 10, "SCAN"),
)
OUTCOME_COLUMNS = {
    "pass_fail",
    "test_pass_fail",
    "failure_code",
    "is_first_fail",
    "primary_failure",
    "primary_failure_code",
    "primary_failure_key",
    "sbin",
    "hbin",
    "disposition",
    "first_pass_fail",
    "scenario_id",
    "true_cause",
    "ground_truth",
    "injected_effect",
    "generator_seed",
    "recoverable_fraction",
}
METRIC_KEYS = (
    "roc_auc",
    "pr_auc",
    "precision",
    "recall",
    "f1",
    "balanced_accuracy",
    "brier",
    "log_loss",
    "ece",
    "failure_capture_at_top_10_percent",
    "failure_capture_at_top_20_percent",
    "positive_rate",
    "n_samples",
    "n_positives",
)


def dataset_dir() -> Path:
    return repo_root() / "data" / "synthetic" / "agent_visible" / DATASET_ID


def artifact_dir() -> Path:
    folder = repo_root() / "artifacts" / "ml" / BENCHMARK_ID
    if folder.name in PROTECTED:
        raise V2BuildError("benchmark output collided with a protected model directory")
    return folder


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _dataset_hashes(folder: Path) -> dict[str, str]:
    return {name: _sha256(folder / name) for name in DATASET_FILES}


def _protected_hashes() -> dict[str, dict[str, str]]:
    root = repo_root() / "artifacts" / "ml"
    return {name: hash_files(root / name, CHAMPION_FILES) for name in PROTECTED}


def _slim(row: dict[str, Any]) -> dict[str, Any]:
    out = {}
    if "lot" in row:
        out["lot"] = row["lot"]
    for key in METRIC_KEYS:
        if key in row:
            out[key] = row[key]
    return out


def audit_gru_sequence(folder: Path | None = None) -> dict[str, Any]:
    """Decide whether a die-level test sequence can be built without the label.

    The ten slots are real. Their stored fields are identity, slot position, or
    the test outcome. A sequence of those outcomes is the first-pass label.
    """
    folder = folder or dataset_dir()
    attempts = pd.read_csv(folder / "die_attempts.csv")
    tests = pd.read_csv(folder / "test_results.csv")
    first = attempts.loc[attempts["attempt_number"].astype(int) == 1].copy()
    first_ids = set(first["attempt_id"].astype(str))
    retest_rows = int((~tests["attempt_id"].astype(str).isin(first_ids)).sum())
    fp = tests.loc[tests["attempt_id"].astype(str).isin(first_ids)].copy()
    unique_orders: list[tuple[str, ...]] = []
    seen: set[tuple[str, ...]] = set()
    for _, group in fp.groupby("attempt_id", sort=False):
        order = tuple(group.sort_values("sequence_index")["test_id"].astype(str))
        if order not in seen:
            seen.add(order)
            unique_orders.append(order)
    expected = tuple(slot[0] for slot in SEQUENCE_SLOTS)
    columns = [str(c) for c in tests.columns]
    outcome = [c for c in columns if c.lower() in OUTCOME_COLUMNS]
    identity = [c for c in columns if c.lower() in {"attempt_id", "lot_id", "wafer_id", "die_id"}]
    position = [c for c in columns if c.lower() in {"test_id", "sequence_index"}]
    repeated = [c for c in columns if c.lower() == "timestamp"]
    used = set(outcome + identity + position + repeated)
    measurements = [c for c in columns if c not in used]
    any_fail = fp.groupby("attempt_id")["test_pass_fail"].apply(lambda s: bool((s.astype(str) == "FAIL").any()))
    attempt_fail = first.set_index(first["attempt_id"].astype(str))["pass_fail"].astype(str).eq("FAIL")
    aligned = any_fail.reindex(attempt_fail.index)
    n_compared = int(aligned.notna().sum())
    n_equal = int((aligned.fillna(False).to_numpy() == attempt_fail.to_numpy()).sum()) if n_compared else 0
    blocked = (not measurements) or (n_compared > 0 and n_equal == n_compared)
    return {
        "model": "gru",
        "status": "BLOCKED_LEAKAGE_RISK" if blocked else "EVALUATED",
        "trained": False,
        "sequence_slots": [{"test_id": a, "sequence_index": b, "slot": c} for a, b, c in SEQUENCE_SLOTS],
        "observed_first_pass_orders": [list(order) for order in unique_orders],
        "expected_order": list(expected),
        "order_matches_defined_slots": unique_orders == [expected],
        "first_pass_attempt_count": int(len(first_ids)),
        "retest_rows_excluded": retest_rows,
        "columns": columns,
        "identity_columns": identity,
        "position_columns": position,
        "repeated_context_columns": repeated,
        "outcome_columns": outcome,
        "measurement_columns": measurements,
        "dies_compared": n_compared,
        "dies_where_any_test_fail_equals_attempt_fail": n_equal,
        "metrics": None,
        "reason": (
            "Each first-pass die has the ten slots in order, but the only step fields are identity, "
            "slot position, a repeated timestamp, and the test outcome. Any test FAIL matches the "
            "attempt FAIL, so a sequence of those outcomes is the target. No leakage-free per-step "
            "measurement exists on the test table. Parametric measurements are not used, and no "
            "replacement sequence was invented."
        ),
    }


def _availability() -> dict[str, dict[str, str]]:
    available, unavailable = probe_extra_models()
    status = {
        "logistic": {"status": "EVALUATED", "dependency": "scikit-learn"},
        "random_forest": {"status": "EVALUATED", "dependency": "scikit-learn"},
        "extra_trees": {"status": "EVALUATED", "dependency": "scikit-learn"},
        "hist_gbm": {"status": "EVALUATED", "dependency": "scikit-learn"},
        "mlp": {"status": "EVALUATED", "dependency": "scikit-learn"},
        "xgboost": {
            "status": "EVALUATED" if "xgboost" in available else "UNAVAILABLE",
            "dependency": "xgboost",
            "detail": unavailable.get("xgboost", "import_ok"),
        },
        "lightgbm": {
            "status": "EVALUATED" if "lightgbm" in available else "UNAVAILABLE",
            "dependency": "lightgbm",
            "detail": unavailable.get("lightgbm", "import_ok"),
        },
        "gru": {"status": "BLOCKED_LEAKAGE_RISK", "dependency": "not_trained"},
    }
    return status


def _configurations(cfg) -> dict[str, Any]:
    rf = cfg.models.random_forest
    hist = cfg.models.hist_gbm
    logistic = cfg.models.logistic
    return {
        "logistic": {
            "class_weight": logistic.class_weight,
            "max_iter": logistic.max_iter,
            "solver": "lbfgs",
        },
        "random_forest": {
            "n_estimators": rf.n_estimators,
            "max_depth": rf.max_depth,
            "min_samples_leaf": rf.min_samples_leaf,
            "class_weight": rf.class_weight,
        },
        "extra_trees": {
            "n_estimators": rf.n_estimators,
            "max_depth": rf.max_depth,
            "min_samples_leaf": rf.min_samples_leaf,
            "class_weight": rf.class_weight,
            "note": "Same size budget as random forest. No extra search.",
        },
        "hist_gbm": {
            "max_depth": hist.max_depth,
            "learning_rate": hist.learning_rate,
            "max_iter": hist.max_iter,
            "min_samples_leaf": hist.min_samples_leaf,
            "sample_weight": "balanced",
        },
        "xgboost": {
            "n_estimators": 50,
            "max_depth": 4,
            "learning_rate": 0.08,
            "subsample": 0.9,
            "colsample_bytree": 0.9,
            "scale_pos_weight": "n_negative/n_positive on the training fold",
        },
        "lightgbm": {
            "n_estimators": 50,
            "max_depth": 4,
            "learning_rate": 0.08,
            "scale_pos_weight": "n_negative/n_positive on the training fold",
        },
        "mlp": {
            "hidden_layer_sizes": [16],
            "activation": "relu",
            "solver": "adam",
            "alpha": 0.0001,
            "batch_size": 64,
            "learning_rate_init": 0.001,
            "max_iter": 80,
            "early_stopping": False,
            "sample_weight": "balanced",
            "preprocessing": "fold-local median, standard scale, one-hot",
        },
    }


def run_benchmark() -> dict[str, Any]:
    cfg = load_ml_config()
    data = load_ml_dataset(dataset_dir())
    contract = assert_training_contract(data, cfg)
    before_models = _protected_hashes()
    before_data = _dataset_hashes(dataset_dir())
    registry_path = default_paths().registry_path
    before_registry = _sha256(registry_path)
    if before_registry != REGISTRY_HASH:
        raise V2BuildError("registry hash changed before the benchmark started")
    registry = load_registry(default_paths())
    if registry.get("active_version") != "yi_ml_v1" or registry.get("production_authorized") is not False:
        raise V2BuildError("active model or production authorization is not in the required state")
    availability = _availability()
    names = [
        name
        for name in ("logistic", "random_forest", "extra_trees", "hist_gbm", "xgboost", "lightgbm", "mlp")
        if availability[name]["status"] == "EVALUATED"
    ]
    trained = run_lolo_models(data, model_names=names, cfg=cfg, with_importance=False)
    for payload in trained["models"].values():
        if list(payload["feature_names"]) != list(ACTIVE_FEATURE_CONTRACT):
            raise V2BuildError("benchmark left the V2 feature contract")
    pr_ref, brier_ref = constant_references(float(trained["positive_rate"]))
    models_out: dict[str, Any] = {}
    for name in names:
        payload = trained["models"][name]
        calibrated = _slim(payload["calibrated"])
        raw = _slim(payload["raw"])
        per_cal = [_slim(row) for row in payload["per_lot_calibrated"]]
        per_raw = [_slim(row) for row in payload["per_lot_raw"]]
        support = ml_support_status(calibrated, per_cal, float(trained["positive_rate"]))
        models_out[name] = {
            "status": "EVALUATED",
            "state": "CANDIDATE",
            "promoted": False,
            "ml_support_status": support,
            "feature_names": payload["feature_names"],
            "n_features": payload["n_features"],
            "train_seconds": payload["train_seconds"],
            "inference_seconds": payload["inference_seconds"],
            "complexity": payload["complexity"],
            "raw": raw,
            "calibrated": calibrated,
            "per_lot_raw": per_raw,
            "per_lot_calibrated": per_cal,
            "lot_stability_raw": payload["lot_stability_raw"],
        }
    gru = audit_gru_sequence(dataset_dir())
    if gru["status"] != "BLOCKED_LEAKAGE_RISK" or gru["trained"]:
        raise V2BuildError("GRU sequence was not blocked")
    after_models = _protected_hashes()
    after_data = _dataset_hashes(dataset_dir())
    after_registry = _sha256(registry_path)
    if before_models != after_models or before_data != after_data or before_registry != after_registry:
        raise V2BuildError("benchmark changed a protected model, the dataset, or the registry")
    report = {
        "benchmark_id": BENCHMARK_ID,
        "dataset_id": DATASET_ID,
        "dataset_path": f"data/synthetic/agent_visible/{DATASET_ID}/",
        "target": "first_pass_fail",
        "state": "CANDIDATE",
        "active_model": "yi_ml_v1",
        "promoted": False,
        "automatic_activation": False,
        "production_authorized": False,
        "selected_model": None,
        "disclaimer": DISCLAIMER,
        "split_strategy": trained["split_strategy"],
        "n_samples": trained["n_samples"],
        "n_positives": trained["n_positives"],
        "n_negatives": EXPECTED_NEG,
        "positive_rate": trained["positive_rate"],
        "constant_pr_auc": pr_ref,
        "constant_brier": brier_ref,
        "roc_reference": 0.5,
        "feature_contract": list(ACTIVE_FEATURE_CONTRACT),
        "parametric_measurements_included": False,
        "fold_assignments": contract["folds"],
        "same_folds_all_models": True,
        "calibration": {
            "method": "isotonic",
            "fit_on": "training_fold_raw_scores_only",
            "held_out_lot_labels_used": False,
        },
        "configurations": _configurations(cfg),
        "seed": cfg.seed,
        "availability": availability,
        "models": models_out,
        "unavailable": [name for name, row in availability.items() if row["status"] == "UNAVAILABLE"],
        "blocked": {"gru": gru},
        "integrity": {
            "protected_hashes_before": before_models,
            "protected_hashes_after": after_models,
            "dataset_hashes_before": before_data,
            "dataset_hashes_after": after_data,
            "registry_sha256_before": before_registry,
            "registry_sha256_after": after_registry,
            "expected_rows": EXPECTED_ROWS,
            "expected_positives": EXPECTED_POS,
        },
    }
    folder = artifact_dir()
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "results.json").write_text(json.dumps(json_safe(report), indent=2), encoding="utf-8")
    return report


def main() -> None:
    report = run_benchmark()
    print(json.dumps({
        "benchmark_id": report["benchmark_id"],
        "evaluated": list(report["models"]),
        "unavailable": report["unavailable"],
        "blocked": list(report["blocked"]),
        "support": {name: row["ml_support_status"] for name, row in report["models"].items()},
        "active_model": report["active_model"],
        "production_authorized": report["production_authorized"],
    }, indent=2))


if __name__ == "__main__":
    main()
