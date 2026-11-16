"""Train yi_ml_v2 on Yield Improvement V2. Never writes artifacts/ml/yi_ml_v1."""

from __future__ import annotations

import json
import pickle
import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from yield_improvement.config.loader import load_config
from yield_improvement.ingestion.loader import load_die_attempts
from yield_improvement.ml.benchmark import (
    ACTIVE_FEATURE_CONTRACT,
    CORE_MODELS,
    probe_extra_models,
    run_lolo_models,
)
from yield_improvement.ml.calibration import ProbabilityCalibrator
from yield_improvement.ml.config import load_feature_policy, load_ml_config
from yield_improvement.ml.contracts import DISCLAIMER
from yield_improvement.ml.dataset import PARAM_NAMES, load_ml_dataset
from yield_improvement.ml.evaluation import compute_metrics
from yield_improvement.ml.explain import permutation_ranks
from yield_improvement.ml.features import fit_feature_builder
from yield_improvement.ml.models import SIMPLICITY, make_model
from yield_improvement.ml.predict import predict_frame
from yield_improvement.ml.split import make_splits
from yield_improvement.ml.train import TrainedBundle, _weights
from yield_improvement.model_lifecycle.audit import append_event, utc_now
from yield_improvement.model_lifecycle.hashes import dumps, hash_files, hash_text, json_safe
from yield_improvement.model_lifecycle.registry import (
    CHAMPION_VERSION,
    assert_champion_unchanged,
    champion_hashes,
    default_paths,
    load_registry,
    new_record,
    put_record,
    save_registry,
)
from yield_improvement.model_lifecycle.states import assert_transition
from yield_improvement.utils.paths import repo_root
from yield_improvement.yield_analysis.fpy import calculate_fpy

MODEL_ID = "yi_ml_v2"
DATASET_ID = "yi_synthetic_v2"
EXPECTED_ROWS = 2500
EXPECTED_POS = 251
EXPECTED_NEG = 2249
BLOCKED_PARAMETRICS = (
    "VMIN",
    "VMAX",
    "IDDQ",
    "VDD",
    "SUPPLY_CURRENT",
    "CONTACT_RESISTANCE",
    "INTERCONNECT_RESISTANCE",
    "ON_RESISTANCE",
)
LEAKAGE_FIELDS = (
    "pass_fail",
    "failure_code",
    "disposition",
    "abort_flag",
    "is_retest",
    "attempt_number",
    "is_first_attempt",
    "sequence_index",
    "primary_failure_key",
    "primary_failure_code",
    "sbin",
    "hbin",
    "test_pass_fail",
    "is_first_fail",
    "scenario_id",
    "true_cause",
    "injected_effect",
    "generator_seed",
    "ground_truth",
    "recoverable_fraction",
)
EXTRA_SIMPLICITY = {"xgboost": 3, "lightgbm": 4, "catboost": 5}
ARCH_NAME = {
    "logistic": "logistic_regression",
    "random_forest": "random_forest",
    "hist_gbm": "hist_gradient_boosting",
    "xgboost": "xgboost",
    "lightgbm": "lightgbm",
    "catboost": "catboost",
}


class V2BuildError(RuntimeError):
    """Stop the V2 build without changing data or yi_ml_v1."""


def dataset_dir() -> Path:
    return repo_root() / "data" / "synthetic" / "agent_visible" / DATASET_ID


def artifact_dir() -> Path:
    return repo_root() / "artifacts" / "ml" / MODEL_ID


def _git_revision() -> str | None:
    try:
        done = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root(),
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return None
    if done.returncode != 0:
        return None
    text = done.stdout.strip()
    return text or None


def _simplicity(name: str) -> int:
    if name in SIMPLICITY:
        return SIMPLICITY[name]
    return EXTRA_SIMPLICITY[name]


def select_model(comparison: list[dict[str, Any]], cfg) -> str:
    """Same rule as ml/train.py: highest PR-AUC, then lower Brier, then the simpler model."""

    def _key(row: dict[str, Any]) -> tuple:
        pr = row["pr_auc"] if row["pr_auc"] is not None else -1.0
        brier = row["brier"] if row["brier"] is not None else 1.0
        return (-pr, brier, _simplicity(row["model"]))

    ranked = sorted(comparison, key=_key)
    if cfg.selection.prefer_simpler_if_close and len(ranked) > 1:
        best_pr = ranked[0]["pr_auc"] or -1.0
        close = [row for row in ranked if (row["pr_auc"] or -1.0) >= best_pr - cfg.selection.close_tolerance]
        ranked = sorted(close, key=lambda row: (_simplicity(row["model"]), row["brier"] or 1.0))
    return str(ranked[0]["model"])


def _confusion(y: np.ndarray, proba: np.ndarray, threshold: float = 0.5) -> dict[str, int]:
    pred = (np.asarray(proba) >= threshold).astype(int)
    actual = np.asarray(y).astype(int)
    tp = int(((pred == 1) & (actual == 1)).sum())
    tn = int(((pred == 0) & (actual == 0)).sum())
    fp = int(((pred == 1) & (actual == 0)).sum())
    fn = int(((pred == 0) & (actual == 1)).sum())
    return {"threshold": threshold, "tp": tp, "tn": tn, "fp": fp, "fn": fn}


def _mean_std(rows: list[dict[str, Any]], key: str) -> dict[str, float | None]:
    values = [float(row[key]) for row in rows if row.get(key) is not None]
    if not values:
        return {"mean": None, "std": None}
    arr = np.array(values, dtype=float)
    return {
        "mean": float(arr.mean()),
        "std": float(arr.std(ddof=1)) if arr.size > 1 else 0.0,
    }


def assert_training_contract(data, cfg) -> dict[str, Any]:
    frame = data.frame
    y = data.y.to_numpy()
    if len(frame) != EXPECTED_ROWS:
        raise V2BuildError(f"expected {EXPECTED_ROWS} ML rows, found {len(frame)}")
    n_pos = int(y.sum())
    n_neg = int((y == 0).sum())
    if n_pos != EXPECTED_POS or n_neg != EXPECTED_NEG:
        raise V2BuildError(f"target counts {n_pos} fail / {n_neg} pass, expected {EXPECTED_POS}/{EXPECTED_NEG}")
    keys = frame[["lot_id", "wafer_id", "die_id"]]
    if int(keys.drop_duplicates().shape[0]) != EXPECTED_ROWS:
        raise V2BuildError("physical die key (lot_id, wafer_id, die_id) is not unique")
    if frame["attempt_id"].duplicated().any():
        raise V2BuildError("duplicate attempt_id on ML rows")
    if int(frame["die_id"].nunique()) == EXPECTED_ROWS:
        raise V2BuildError("die_id alone must not be treated as globally unique")
    builder = fit_feature_builder(frame, data.y, policy=load_feature_policy())
    names = list(builder.feature_names_)
    if names != list(ACTIVE_FEATURE_CONTRACT):
        raise V2BuildError(f"feature contract mismatch: {names}")
    blocked = [name for name in list(BLOCKED_PARAMETRICS) + list(PARAM_NAMES) if name in names or name in frame.columns]
    if blocked:
        raise V2BuildError(f"parametric columns entered the ML frame: {blocked}")
    denied = {c.lower() for c in load_feature_policy().denied_columns}
    leaked = [c for c in names if c.lower() in denied]
    if leaked:
        raise V2BuildError(f"leakage columns in features: {leaked}")
    groups = data.groups.to_numpy()
    strategy, splits = make_splits(groups, cfg)
    if strategy != "leave_one_lot_out" or len(splits) != 5:
        raise V2BuildError(f"expected 5 LOLO folds, found {strategy} n={len(splits)}")
    seen_test: list[str] = []
    fold_rows = []
    for fold_number, (train_idx, test_idx) in enumerate(splits, start=1):
        train_lots = set(groups[train_idx])
        test_lots = set(groups[test_idx])
        if train_lots & test_lots:
            raise V2BuildError("lot leakage across train/test")
        if len(test_lots) != 1 or len(train_idx) != 2000 or len(test_idx) != 500:
            raise V2BuildError("fold sizes are not 2000/500 with one test lot")
        lot = sorted(test_lots)[0]
        seen_test.append(lot)
        fold_rows.append(
            {
                "fold": fold_number,
                "test_lot": lot,
                "training_lots": sorted(train_lots),
                "train_samples": int(len(train_idx)),
                "test_samples": int(len(test_idx)),
                "train_positives": int(y[train_idx].sum()),
                "train_negatives": int((y[train_idx] == 0).sum()),
                "test_positives": int(y[test_idx].sum()),
                "test_negatives": int((y[test_idx] == 0).sum()),
            }
        )
    if sorted(seen_test) != ["L001", "L002", "L003", "L004", "L005"]:
        raise V2BuildError(f"each lot must be the test lot once, found {seen_test}")
    app = load_config()
    attempts = load_die_attempts(dataset_dir() / "die_attempts.csv", app).attempts
    fpy = calculate_fpy(attempts, app, test_results=None)
    if fpy.eligible_die_count != EXPECTED_ROWS or fpy.first_pass_pass_count != EXPECTED_NEG or fpy.first_pass_fail_count != EXPECTED_POS:
        raise V2BuildError(
            f"FPY mismatch eligible={fpy.eligible_die_count} pass={fpy.first_pass_pass_count} fail={fpy.first_pass_fail_count}"
        )
    eligible_keys = {(d.lot_id, d.wafer_id, d.die_id) for d in fpy.per_die}
    ml_keys = set(zip(frame["lot_id"].astype(str), frame["wafer_id"].astype(str), frame["die_id"].astype(str)))
    if eligible_keys != ml_keys:
        raise V2BuildError(
            f"physical die set mismatch missing={len(eligible_keys - ml_keys)} extra={len(ml_keys - eligible_keys)}"
        )
    by_id = {a.attempt_id: a for a in attempts}
    recovered = 0
    for outcome in fpy.per_die:
        if outcome.first_pass_disposition != "FAIL" or outcome.final_disposition != "PASS":
            continue
        recovered += 1
        mask = (
            (frame["lot_id"].astype(str) == outcome.lot_id)
            & (frame["wafer_id"].astype(str) == outcome.wafer_id)
            & (frame["die_id"].astype(str) == outcome.die_id)
        ).to_numpy()
        if int(mask.sum()) != 1 or int(y[mask][0]) != 1:
            raise V2BuildError("a retest PASS changed or duplicated the first-pass target")
        attempt = by_id[outcome.attempt_id]
        if attempt.attempt_number != 1 or str(frame.loc[mask, "attempt_id"].iloc[0]) != outcome.attempt_id:
            raise V2BuildError("ML row is not joined to the first-pass attempt")
    if recovered == 0:
        raise V2BuildError("expected at least one first-fail die that later passed")
    return {
        "features": names,
        "numeric": list(builder.numeric_features_),
        "categorical": list(builder.categorical_features_),
        "folds": fold_rows,
        "fpy": fpy.fpy,
        "fpy_loss": fpy.fpy_loss,
        "recovered_still_positive": recovered,
    }


def _register_candidate(meta: dict[str, Any], hashes: dict[str, str]) -> str:
    paths = default_paths()
    before = champion_hashes(paths)
    registry = load_registry(paths)
    if registry.get("active_version") != CHAMPION_VERSION:
        raise V2BuildError("refusing to register while the active model is not yi_ml_v1")
    if MODEL_ID in registry.get("models", {}):
        raise V2BuildError(f"{MODEL_ID} is already in the registry")
    assert_transition(None, "CANDIDATE", event="MODEL_CREATED")
    record = new_record(
        version=MODEL_ID,
        architecture=meta["architecture"],
        state="CANDIDATE",
        dataset_id=DATASET_ID,
        dataset_dir=str(dataset_dir()),
        parent=None,
        artifact_hashes=hashes,
        training_config_hash=meta["training_config_hash"],
        notes="V2 candidate trained on yi_synthetic_v2. Not approved. Not active. Predictive evidence only.",
        seed=meta["seed"],
        python_version=meta["python_version"],
        sklearn_version=meta["sklearn_version"],
        feature_contract=list(ACTIVE_FEATURE_CONTRACT),
        feature_contract_version=meta["feature_set_version"],
    )
    record["source_model"] = None
    record["parent_model_version"] = None
    put_record(registry, record)
    if registry.get("active_version") != CHAMPION_VERSION:
        raise V2BuildError("registration changed the active model")
    save_registry(paths, registry)
    append_event(
        paths.audit_path,
        {
            "event_type": "MODEL_CREATED",
            "model_version": MODEL_ID,
            "previous_state": None,
            "new_state": "CANDIDATE",
            "actor": "unavailable",
            "reason": "yi_ml_v2 trained on Yield Improvement V2. Not activated.",
            "artifact_hashes": hashes,
            "parent_version": None,
        },
    )
    assert_champion_unchanged(paths, before)
    return "CANDIDATE"


def build_yi_ml_v2() -> dict[str, Any]:
    paths = default_paths()
    before = champion_hashes(paths)
    dest = artifact_dir()
    if dest.exists():
        raise V2BuildError(f"refusing to overwrite {dest}")
    folder = dataset_dir()
    app = load_config()
    cfg = load_ml_config()
    data = load_ml_dataset(folder, config=app)
    contract = assert_training_contract(data, cfg)
    print("FEATURE_LIST")
    for name in contract["features"]:
        print(name)
    print("EXCLUDED_LEAKAGE_FIELDS")
    for name in LEAKAGE_FIELDS:
        print(name)
    print("PARAMETRIC_JOIN false")
    print("LOLO_FOLDS")
    for row in contract["folds"]:
        print(json.dumps(row))

    available, unavailable = probe_extra_models()
    model_names = list(CORE_MODELS) + available
    bench = run_lolo_models(data, model_names=model_names, cfg=cfg, with_importance=False)
    comparison = []
    for name in model_names:
        raw = bench["models"][name]["raw"]
        comparison.append(
            {
                "model": name,
                "roc_auc": raw.get("roc_auc"),
                "pr_auc": raw.get("pr_auc"),
                "f1": raw.get("f1"),
                "recall": raw.get("recall"),
                "brier": raw.get("brier"),
                "failure_capture_at_top_10_percent": raw.get("failure_capture_at_top_10_percent"),
                "failure_capture_at_top_20_percent": raw.get("failure_capture_at_top_20_percent"),
            }
        )
    selected = select_model(comparison, cfg)
    block = bench["models"][selected]
    y = data.y.to_numpy()
    groups = data.groups.to_numpy()
    oof_cal = bench["_oof"][selected]["cal"]
    oof_raw = bench["_oof"][selected]["raw"]
    fold_confusion = []
    for row in contract["folds"]:
        mask = groups == row["test_lot"]
        fold_confusion.append({"test_lot": row["test_lot"], **_confusion(y[mask], oof_cal[mask])})
    aggregate_cm = _confusion(y, oof_cal)
    cal_metrics = compute_metrics(y, oof_cal)
    fold_summary = {
        key: _mean_std(block["per_lot_calibrated"], key)
        for key in (
            "roc_auc",
            "pr_auc",
            "precision",
            "recall",
            "f1",
            "balanced_accuracy",
            "brier",
            "log_loss",
            "failure_capture_at_top_10_percent",
            "failure_capture_at_top_20_percent",
        )
    }

    builder = fit_feature_builder(data.frame, data.y)
    x_all = builder.transform(data.frame)
    if list(x_all.columns) != list(ACTIVE_FEATURE_CONTRACT):
        raise V2BuildError("final feature matrix left the 16-feature contract")
    numeric = [c for c in builder.numeric_features_ if c in x_all.columns]
    categorical = [c for c in builder.categorical_features_ if c in x_all.columns]
    pipeline = make_model(selected, cfg, cfg.seed, numeric, categorical) if selected in CORE_MODELS else None
    if pipeline is None:
        from yield_improvement.ml.benchmark import make_benchmark_model

        pipeline = make_benchmark_model(selected, cfg, cfg.seed, numeric, categorical, y)
    if selected == "hist_gbm":
        pipeline.fit(x_all, y, clf__sample_weight=_weights(y))
    else:
        pipeline.fit(x_all, y)
    calibrator = ProbabilityCalibrator().fit(oof_raw, y)
    importances = permutation_ranks(pipeline, x_all, y, cfg.seed)
    for row in importances:
        row["interpretation"] = "predictive association only; not a root cause"
    bundle = TrainedBundle(
        model_name=selected,
        pipeline=pipeline,
        builder=builder,
        calibrator=calibrator,
        oof_raw=oof_raw,
        oof_cal=oof_cal,
        comparison=comparison,
        split_strategy="leave_one_lot_out",
        n_train=2000,
        n_test=500,
        feature_names=list(x_all.columns),
    )
    predictions = predict_frame(
        bundle,
        data.frame.head(1),
        model_version=MODEL_ID,
        feature_set_version=cfg.feature_set_version,
        calibration_version=cfg.calibration_version,
    )
    if not predictions or predictions[0].predicted_class not in {0, 1}:
        raise V2BuildError("inference smoke check failed")
    pred_dump = predictions[0].model_dump()
    if "root_cause" in pred_dump or any("root cause" in str(v).lower() for v in pred_dump.values()):
        raise V2BuildError("prediction payload contains a root-cause field")

    try:
        import sklearn

        sklearn_version = sklearn.__version__
    except Exception:  # noqa: BLE001
        sklearn_version = "unavailable"
    trained_at = utc_now()
    config_hash = hash_text(
        (repo_root() / "configs" / "ml.yaml").read_text(encoding="utf-8")
        + "\n"
        + (repo_root() / "configs" / "ml_feature_allowlist.yaml").read_text(encoding="utf-8")
    )
    meta = {
        "model_id": MODEL_ID,
        "model_version": MODEL_ID,
        "model_name": selected,
        "architecture": ARCH_NAME.get(selected, selected),
        "model_family": ARCH_NAME.get(selected, selected),
        "dataset_id": DATASET_ID,
        "dataset_path": "data/synthetic/agent_visible/yi_synthetic_v2/",
        "sample_count": EXPECTED_ROWS,
        "positive_count": EXPECTED_POS,
        "negative_count": EXPECTED_NEG,
        "target": "first_pass_fail",
        "target_encoding": {"FAIL": 1, "PASS": 0},
        "feature_count": 16,
        "feature_names": list(x_all.columns),
        "feature_contract": list(ACTIVE_FEATURE_CONTRACT),
        "feature_set_version": cfg.feature_set_version,
        "preprocessing_version": cfg.feature_set_version,
        "split": "leave_one_lot_out",
        "split_strategy": "leave_one_lot_out",
        "n_folds": 5,
        "parametric_join": False,
        "source_model": None,
        "training_date": trained_at,
        "trained_at": trained_at,
        "calibration_method": cfg.calibration.method,
        "calibration_version": cfg.calibration_version,
        "seed": cfg.seed,
        "decision_threshold": 0.5,
        "threshold_fit_on_test_fold": False,
        "git_revision": _git_revision(),
        "python_version": sys.version.split()[0],
        "sklearn_version": sklearn_version,
        "training_config_hash": config_hash,
        "n_samples": EXPECTED_ROWS,
        "n_features": 16,
        "analysis_id": DATASET_ID,
        "state": "CANDIDATE",
        "production_action": "FORBIDDEN",
        "production_authorized": False,
        "automatic_activation": False,
        "evidence_role": "SECONDARY_SUPPORT",
        "disclaimer": DISCLAIMER,
        "not_a_root_cause": True,
        "unavailable_models": unavailable,
        "selected_metrics": cal_metrics.model_dump(),
    }
    preprocessing = {
        "numeric": {
            "columns": numeric,
            "imputer": "SimpleImputer(strategy=median)",
            "scaler": "StandardScaler",
            "fit_on": "all V2 rows for the deployed artifact; each LOLO fold refit on its training lots only",
        },
        "categorical": {
            "columns": categorical,
            "imputer": "SimpleImputer(strategy=most_frequent)",
            "encoder": "OneHotEncoder(handle_unknown=ignore)",
        },
        "missing_in_v2_matrix": {col: int(pd.Series(x_all[col]).isna().sum()) for col in x_all.columns},
    }
    calibration = {
        "method": cfg.calibration.method,
        "fold_local": "isotonic fit on each fold's training-lot raw probabilities only",
        "deployed": "isotonic fit on pooled out-of-fold raw probabilities, not on in-sample fitted probabilities",
        "test_fold_used_to_fit": False,
        "fitted": bool(calibrator.fitted),
    }
    evaluation = {
        "selection_policy": "max pooled raw PR-AUC, then lower Brier, then simpler model within close_tolerance 0.02",
        "selection_metric_source": "raw_out_of_fold",
        "reported_operating_point": "calibrated out-of-fold probabilities, threshold 0.5",
        "comparison_raw": comparison,
        "selected_model": selected,
        "aggregate_calibrated": cal_metrics.model_dump(),
        "aggregate_raw": block["raw"],
        "fold_mean_std_calibrated": fold_summary,
        "per_lot_calibrated": block["per_lot_calibrated"],
        "per_lot_raw": block["per_lot_raw"],
        "confusion_by_fold": fold_confusion,
        "confusion_aggregate": aggregate_cm,
        "feature_importance": importances,
        "importance_wording": "predictive association / model feature importance. Not a root cause.",
        "ece_calibrated": block["calibrated"].get("ece"),
        "disclaimer": DISCLAIMER,
    }
    manifest = {
        "dataset_id": DATASET_ID,
        "dataset_path": "data/synthetic/agent_visible/yi_synthetic_v2/",
        "files_used": ["die_attempts.csv"],
        "files_read_but_not_joined": [
            "parametric_measurements.csv",
            "test_results.csv",
        ],
        "parametric_join_note": (
            "The existing loader reads parametric_measurements.csv and keeps only the historical V1 parameter names. "
            "Those names are absent from Yield Improvement V2, so no parametric column enters the feature matrix."
        ),
        "parametric_join": False,
        "row_counts": {"ml_rows": EXPECTED_ROWS, "positive": EXPECTED_POS, "negative": EXPECTED_NEG},
        "feature_list": list(ACTIVE_FEATURE_CONTRACT),
        "target": "first_pass_fail = 1 if DieOutcome.first_pass_disposition == FAIL else 0",
        "lot_ids": ["L001", "L002", "L003", "L004", "L005"],
        "folds": contract["folds"],
        "preprocessing": preprocessing,
        "model_configuration": {
            "candidates": model_names,
            "selected": selected,
            "seed": cfg.seed,
            "ml_yaml": "configs/ml.yaml",
        },
        "evaluation_configuration": {
            "split": "leave_one_lot_out",
            "threshold": 0.5,
            "calibration": cfg.calibration.method,
        },
        "hidden_ground_truth_stored": False,
        "fpy": contract["fpy"],
        "fpy_loss": contract["fpy_loss"],
    }
    dest.mkdir(parents=True, exist_ok=False)
    blob = pickle.dumps(
        {
            "pipeline": pipeline,
            "builder": builder,
            "calibrator": calibrator,
            "model_name": selected,
            "feature_names": list(x_all.columns),
            "split_strategy": "leave_one_lot_out",
        },
        protocol=4,
    )
    (dest / "model.pkl").write_bytes(blob)
    (dest / "metadata.json").write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (dest / "feature_list.json").write_text(json.dumps(list(x_all.columns), indent=2) + "\n", encoding="utf-8")
    (dest / "metrics.json").write_text(dumps(json_safe({"model_name": selected, "metrics": cal_metrics.model_dump(), "comparison": comparison, "fold_mean_std": fold_summary, "disclaimer": DISCLAIMER})), encoding="utf-8")
    (dest / "preprocessing.json").write_text(json.dumps(preprocessing, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (dest / "calibration.json").write_text(json.dumps(calibration, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (dest / "evaluation.json").write_text(dumps(json_safe(evaluation)), encoding="utf-8")
    (dest / "training_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    hashes = hash_files(dest, ("model.pkl", "metadata.json", "feature_list.json", "metrics.json"))
    (dest / "hashes.json").write_text(dumps(hashes), encoding="utf-8")
    state = _register_candidate(meta, hashes)
    assert_champion_unchanged(paths, before)
    summary = {
        "model": selected,
        "state": state,
        "metrics": cal_metrics.model_dump(),
        "ece": block["calibrated"].get("ece"),
        "folds": contract["folds"],
        "comparison": comparison,
        "importances": importances[:8],
        "confusion": aggregate_cm,
        "fold_summary": fold_summary,
        "unavailable": unavailable,
    }
    print("SELECTED", selected)
    print("METRICS", json.dumps(cal_metrics.model_dump()))
    return summary


def main() -> int:
    build_yi_ml_v2()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
