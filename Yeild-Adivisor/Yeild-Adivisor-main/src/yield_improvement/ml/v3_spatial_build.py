"""Train yi_ml_v3_spatial. Does not rewrite yi_ml_v1 or yi_ml_v2."""

from __future__ import annotations

import json
import pickle
import sys
from pathlib import Path
from typing import Any

from yield_improvement.config.loader import load_config
from yield_improvement.ingestion.loader import load_die_attempts, load_test_results
from yield_improvement.ml.benchmark import ACTIVE_FEATURE_CONTRACT, run_lolo_models
from yield_improvement.ml.calibration import ProbabilityCalibrator
from yield_improvement.ml.config import load_ml_config
from yield_improvement.ml.contracts import DISCLAIMER
from yield_improvement.ml.dataset import load_ml_dataset
from yield_improvement.ml.evaluation import compute_metrics
from yield_improvement.ml.explain import permutation_ranks
from yield_improvement.ml.features import fit_grid_border_feature_builder
from yield_improvement.ml.models import make_model
from yield_improvement.ml.predict import predict_frame
from yield_improvement.ml.train import TrainedBundle, _weights
from yield_improvement.ml.v2_build import (
    DATASET_ID,
    EXPECTED_NEG,
    EXPECTED_POS,
    EXPECTED_ROWS,
    LEAKAGE_FIELDS,
    V2BuildError,
    _confusion,
    _git_revision,
    _mean_std,
    assert_training_contract,
    dataset_dir,
)
from yield_improvement.model_lifecycle.audit import append_event, utc_now
from yield_improvement.model_lifecycle.hashes import (
    CHAMPION_FILES,
    dumps,
    hash_files,
    hash_text,
    json_safe,
    sha256_file,
)
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

MODEL_ID = "yi_ml_v3_spatial"
BASELINE_ID = "yi_ml_v2"
SELECTED = "logistic"
COMPARE_KEYS = (
    "roc_auc",
    "pr_auc",
    "recall",
    "precision",
    "f1",
    "balanced_accuracy",
    "brier",
    "log_loss",
    "ece",
    "failure_capture_at_top_10_percent",
    "failure_capture_at_top_20_percent",
)
DATASET_FILES = (
    "die_attempts.csv",
    "test_results.csv",
    "parametric_measurements.csv",
)


def artifact_dir() -> Path:
    return repo_root() / "artifacts" / "ml" / MODEL_ID


def _baseline_dir() -> Path:
    return repo_root() / "artifacts" / "ml" / BASELINE_ID


def _file_hashes(folder: Path, names: tuple[str, ...]) -> dict[str, str]:
    return {name: sha256_file(folder / name) for name in names}


def _slim(row: dict[str, Any]) -> dict[str, Any]:
    return {key: row.get(key) for key in COMPARE_KEYS}


def _baseline_report() -> dict[str, Any]:
    folder = _baseline_dir()
    metrics = json.loads((folder / "metrics.json").read_text(encoding="utf-8"))
    evaluation = json.loads((folder / "evaluation.json").read_text(encoding="utf-8"))
    pooled = dict(metrics["metrics"])
    pooled["ece"] = evaluation.get("ece_calibrated")
    per_lot = []
    for row in evaluation["per_lot_calibrated"]:
        item = {"lot": row["lot"], **_slim(row)}
        per_lot.append(item)
    return {"model_id": BASELINE_ID, "pooled": pooled, "per_lot": per_lot}


def _register_candidate(meta: dict[str, Any], hashes: dict[str, str]) -> str:
    paths = default_paths()
    before = champion_hashes(paths)
    registry = load_registry(paths)
    if registry.get("active_version") != CHAMPION_VERSION:
        raise V2BuildError("refusing to register while the active model is not yi_ml_v1")
    if MODEL_ID in registry.get("models", {}):
        raise V2BuildError(f"{MODEL_ID} is already in the registry")
    if BASELINE_ID not in registry.get("models", {}):
        raise V2BuildError("yi_ml_v2 is missing from the registry")
    assert_transition(None, "CANDIDATE", event="MODEL_CREATED")
    record = new_record(
        version=MODEL_ID,
        architecture="logistic_regression",
        state="CANDIDATE",
        dataset_id=DATASET_ID,
        dataset_dir=str(dataset_dir()),
        parent=None,
        artifact_hashes=hashes,
        training_config_hash=meta["training_config_hash"],
        notes=(
            "Experimental candidate. Same 16 columns as yi_ml_v2, with spatial_region "
            "set from the V2 grid border (BORDER/INNER). Not approved. Not active."
        ),
        seed=meta["seed"],
        python_version=meta["python_version"],
        sklearn_version=meta["sklearn_version"],
        feature_contract=list(ACTIVE_FEATURE_CONTRACT),
        feature_contract_version=meta["feature_set_version"],
    )
    record["source_model"] = None
    record["parent_model_version"] = None
    record["experiment"] = "corrected_v2_spatial_region"
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
            "reason": "yi_ml_v3_spatial experimental candidate. Not activated.",
            "artifact_hashes": hashes,
            "parent_version": None,
        },
    )
    assert_champion_unchanged(paths, before)
    return "CANDIDATE"


def build_yi_ml_v3_spatial() -> dict[str, Any]:
    paths = default_paths()
    before_champion = champion_hashes(paths)
    dest = artifact_dir()
    if dest.exists():
        raise V2BuildError(f"refusing to overwrite {dest}")
    data_hashes = _file_hashes(dataset_dir(), DATASET_FILES)
    v1_before = hash_files(repo_root() / "artifacts" / "ml" / "yi_ml_v1", CHAMPION_FILES)
    v2_before = hash_files(_baseline_dir(), CHAMPION_FILES)
    cfg = load_ml_config()
    app = load_config()
    data = load_ml_dataset(dataset_dir(), config=app)
    contract = assert_training_contract(data, cfg)
    builder = fit_grid_border_feature_builder(data.frame, data.y)
    x_all = builder.transform(data.frame)
    if list(x_all.columns) != list(ACTIVE_FEATURE_CONTRACT):
        raise V2BuildError("feature matrix left the 16-column contract")
    regions = set(x_all["spatial_region"].astype(str))
    if regions != {"BORDER", "INNER"}:
        raise V2BuildError(f"spatial_region must be BORDER/INNER, found {sorted(regions)}")
    if any(token in regions for token in ("EDGE", "CENTER", "OTHER")):
        raise V2BuildError("radius-quantile spatial labels entered the V3 matrix")
    y = data.y.to_numpy()
    bench = run_lolo_models(
        data,
        model_names=[SELECTED],
        cfg=cfg,
        with_importance=False,
        builder_factory=fit_grid_border_feature_builder,
    )
    block = bench["models"][SELECTED]
    groups = data.groups.to_numpy()
    oof_cal = bench["_oof"][SELECTED]["cal"]
    oof_raw = bench["_oof"][SELECTED]["raw"]
    fold_confusion = []
    for row in contract["folds"]:
        mask = groups == row["test_lot"]
        fold_confusion.append({"test_lot": row["test_lot"], **_confusion(y[mask], oof_cal[mask])})
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
    numeric = [c for c in builder.numeric_features_ if c in x_all.columns]
    categorical = [c for c in builder.categorical_features_ if c in x_all.columns]
    pipeline = make_model(SELECTED, cfg, cfg.seed, numeric, categorical)
    pipeline.fit(x_all, y)
    calibrator = ProbabilityCalibrator().fit(oof_raw, y)
    importances = permutation_ranks(pipeline, x_all, y, cfg.seed)
    for row in importances:
        row["interpretation"] = "predictive association only; not a root cause"
    bundle = TrainedBundle(
        model_name=SELECTED,
        pipeline=pipeline,
        builder=builder,
        calibrator=calibrator,
        oof_raw=oof_raw,
        oof_cal=oof_cal,
        comparison=[{"model": SELECTED, **_slim(block["raw"])}],
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
    if "root_cause" in predictions[0].model_dump():
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
    pooled = cal_metrics.model_dump()
    pooled["ece"] = block["calibrated"].get("ece")
    per_lot = [{"lot": row["lot"], **_slim(row)} for row in block["per_lot_calibrated"]]
    baseline = _baseline_report()
    constant_rate = float(y.mean())
    comparison = {
        "baseline_model": BASELINE_ID,
        "experiment_model": MODEL_ID,
        "feature_change": "spatial_region values EDGE/CENTER/OTHER replaced by BORDER/INNER",
        "feature_count": {"yi_ml_v2": 16, "yi_ml_v3_spatial": 16},
        "constant_positive_rate": constant_rate,
        "constant_brier": float(constant_rate * (1.0 - constant_rate)),
        "pooled": {"yi_ml_v2": baseline["pooled"], "yi_ml_v3_spatial": pooled},
        "per_lot": {
            "yi_ml_v2": baseline["per_lot"],
            "yi_ml_v3_spatial": per_lot,
        },
        "promoted": False,
        "interpretation_rule": "Do not promote from a single metric or a single held-out lot.",
    }
    meta = {
        "model_id": MODEL_ID,
        "model_version": MODEL_ID,
        "model_name": SELECTED,
        "architecture": "logistic_regression",
        "model_family": "logistic_regression",
        "dataset_id": DATASET_ID,
        "dataset_path": f"data/synthetic/agent_visible/{DATASET_ID}/",
        "sample_count": EXPECTED_ROWS,
        "positive_count": EXPECTED_POS,
        "negative_count": EXPECTED_NEG,
        "target": "first_pass_fail",
        "target_encoding": {"FAIL": 1, "PASS": 0},
        "feature_count": 16,
        "feature_names": list(x_all.columns),
        "feature_contract": list(ACTIVE_FEATURE_CONTRACT),
        "spatial_region_values": ["BORDER", "INNER"],
        "spatial_region_source": "yield_improvement.yield_analysis.grid_region",
        "baseline_model": BASELINE_ID,
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
        "selected_metrics": pooled,
        "experiment": "corrected_v2_spatial_region",
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
            "spatial_region": "BORDER if the die is on the training-grid boundary, otherwise INNER",
        },
    }
    calibration = {
        "method": cfg.calibration.method,
        "fold_local": "isotonic fit on each fold's training-lot raw probabilities only",
        "deployed": "isotonic fit on pooled out-of-fold raw probabilities, not on in-sample fitted probabilities",
        "test_fold_used_to_fit": False,
        "fitted": bool(calibrator.fitted),
    }
    evaluation = {
        "experiment": "corrected_v2_spatial_region",
        "baseline_model": BASELINE_ID,
        "selected_model": SELECTED,
        "reported_operating_point": "calibrated out-of-fold probabilities, threshold 0.5",
        "aggregate_calibrated": pooled,
        "aggregate_raw": block["raw"],
        "fold_mean_std_calibrated": fold_summary,
        "per_lot_calibrated": block["per_lot_calibrated"],
        "per_lot_raw": block["per_lot_raw"],
        "confusion_by_fold": fold_confusion,
        "confusion_aggregate": _confusion(y, oof_cal),
        "feature_importance": importances,
        "importance_wording": "predictive association / model feature importance. Not a root cause.",
        "ece_calibrated": pooled.get("ece"),
        "comparison_to_yi_ml_v2": comparison,
        "disclaimer": DISCLAIMER,
        "promoted": False,
    }
    manifest = {
        "dataset_id": DATASET_ID,
        "dataset_path": f"data/synthetic/agent_visible/{DATASET_ID}/",
        "files_used": ["die_attempts.csv"],
        "files_read_but_not_joined": ["parametric_measurements.csv", "test_results.csv"],
        "parametric_join": False,
        "row_counts": {"ml_rows": EXPECTED_ROWS, "positive": EXPECTED_POS, "negative": EXPECTED_NEG},
        "feature_list": list(ACTIVE_FEATURE_CONTRACT),
        "spatial_region_values": ["BORDER", "INNER"],
        "target": "first_pass_fail = 1 if DieOutcome.first_pass_disposition == FAIL else 0",
        "lot_ids": ["L001", "L002", "L003", "L004", "L005"],
        "folds": contract["folds"],
        "baseline_model": BASELINE_ID,
        "hidden_ground_truth_stored": False,
        "fpy": contract["fpy"],
        "fpy_loss": contract["fpy_loss"],
        "leakage_fields_excluded": list(LEAKAGE_FIELDS),
    }
    dest.mkdir(parents=True, exist_ok=False)
    blob = pickle.dumps(
        {
            "pipeline": pipeline,
            "builder": builder,
            "calibrator": calibrator,
            "model_name": SELECTED,
            "feature_names": list(x_all.columns),
            "split_strategy": "leave_one_lot_out",
        },
        protocol=4,
    )
    (dest / "model.pkl").write_bytes(blob)
    (dest / "metadata.json").write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (dest / "feature_list.json").write_text(json.dumps(list(x_all.columns), indent=2) + "\n", encoding="utf-8")
    (dest / "metrics.json").write_text(
        dumps(
            json_safe(
                {
                    "model_name": SELECTED,
                    "metrics": pooled,
                    "fold_mean_std": fold_summary,
                    "per_lot": per_lot,
                    "disclaimer": DISCLAIMER,
                }
            )
        ),
        encoding="utf-8",
    )
    (dest / "preprocessing.json").write_text(json.dumps(preprocessing, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (dest / "calibration.json").write_text(json.dumps(calibration, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (dest / "evaluation.json").write_text(dumps(json_safe(evaluation)), encoding="utf-8")
    (dest / "comparison.json").write_text(dumps(json_safe(comparison)), encoding="utf-8")
    (dest / "training_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    hashes = hash_files(dest, CHAMPION_FILES)
    (dest / "hashes.json").write_text(dumps(hashes), encoding="utf-8")
    state = _register_candidate(meta, hashes)
    if hash_files(repo_root() / "artifacts" / "ml" / "yi_ml_v1", CHAMPION_FILES) != v1_before:
        raise V2BuildError("yi_ml_v1 artifacts changed")
    if hash_files(_baseline_dir(), CHAMPION_FILES) != v2_before:
        raise V2BuildError("yi_ml_v2 artifacts changed")
    if _file_hashes(dataset_dir(), DATASET_FILES) != data_hashes:
        raise V2BuildError("dataset files changed")
    attempts = load_die_attempts(dataset_dir() / "die_attempts.csv", app).attempts
    tests = load_test_results(dataset_dir() / "test_results.csv", app).test_results
    fpy = calculate_fpy(attempts, app, test_results=tests)
    if (
        fpy.eligible_die_count != EXPECTED_ROWS
        or fpy.first_pass_pass_count != EXPECTED_NEG
        or fpy.first_pass_fail_count != EXPECTED_POS
        or sum(row.n_dies for row in fpy.primary_fail_pareto) != EXPECTED_POS
    ):
        raise V2BuildError("FPY or Pareto totals changed")
    assert_champion_unchanged(paths, before_champion)
    summary = {
        "model": SELECTED,
        "state": state,
        "metrics": pooled,
        "per_lot": per_lot,
        "baseline_pooled": baseline["pooled"],
        "baseline_per_lot": baseline["per_lot"],
        "constant_positive_rate": constant_rate,
        "folds": contract["folds"],
        "regions": sorted(regions),
    }
    print(json.dumps(json_safe(summary), indent=2))
    return summary


def main() -> int:
    build_yi_ml_v3_spatial()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
