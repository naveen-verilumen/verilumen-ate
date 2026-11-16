"""Controlled V4 feature experiments. Does not rewrite yi_ml_v1, yi_ml_v2, or yi_ml_v3_spatial."""

from __future__ import annotations

import json
import pickle
import sys
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from yield_improvement.config.loader import load_config
from yield_improvement.ingestion.loader import load_die_attempts, load_test_results
from yield_improvement.ml.benchmark import ACTIVE_FEATURE_CONTRACT, run_lolo_models
from yield_improvement.ml.calibration import ProbabilityCalibrator
from yield_improvement.ml.config import load_ml_config
from yield_improvement.ml.contracts import DISCLAIMER
from yield_improvement.ml.dataset import load_ml_dataset
from yield_improvement.ml.evaluation import compute_metrics
from yield_improvement.ml.experiment_features import fit_experiment_builder
from yield_improvement.ml.features import fit_feature_builder
from yield_improvement.ml.models import make_model
from yield_improvement.ml.predict import predict_frame
from yield_improvement.ml.reliability import ml_support_status
from yield_improvement.ml.train import TrainedBundle
from yield_improvement.ml.v2_build import (
    DATASET_ID,
    EXPECTED_NEG,
    EXPECTED_POS,
    EXPECTED_ROWS,
    V2BuildError,
    _git_revision,
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

MODEL_ID = "yi_ml_v4"
PARAMS = (
    "VMIN",
    "VMAX",
    "IDDQ",
    "SUPPLY_CURRENT",
    "CONTACT_RESISTANCE",
    "INTERCONNECT_RESISTANCE",
    "ON_RESISTANCE",
    "VDD",
)
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
    "positive_rate",
)
DATASET_FILES = ("die_attempts.csv", "test_results.csv", "parametric_measurements.csv")
PROTECTED = ("yi_ml_v1", "yi_ml_v2", "yi_ml_v3_spatial")


def artifact_dir() -> Path:
    return repo_root() / "artifacts" / "ml" / MODEL_ID


def _slim(row: dict[str, Any]) -> dict[str, Any]:
    return {key: row.get(key) for key in COMPARE_KEYS}


def _saved_report(model_id: str) -> dict[str, Any]:
    folder = repo_root() / "artifacts" / "ml" / model_id
    metrics = json.loads((folder / "metrics.json").read_text(encoding="utf-8"))
    evaluation = json.loads((folder / "evaluation.json").read_text(encoding="utf-8"))
    pooled = dict(metrics.get("metrics") or {})
    pooled["ece"] = evaluation.get("ece_calibrated", pooled.get("ece"))
    per_lot = []
    for row in evaluation.get("per_lot_calibrated") or metrics.get("per_lot") or []:
        per_lot.append({"lot": row.get("lot") or row.get("test_lot"), **_slim(row)})
    return {"model_id": model_id, "pooled": pooled, "per_lot": per_lot, "retrained": False}


def audit_parametrics(folder: Path | None = None) -> list[dict[str, Any]]:
    """Decide whether each V2 measurement may enter the first-pass feature matrix."""
    root = folder or dataset_dir()
    attempts = pd.read_csv(root / "die_attempts.csv")
    params = pd.read_csv(root / "parametric_measurements.csv")
    first_ids = set(attempts.loc[attempts["attempt_number"].astype(int) == 1, "attempt_id"].astype(str))
    params["attempt_id"] = params["attempt_id"].astype(str)
    first = params[params["attempt_id"].isin(first_ids)]
    retest = params[~params["attempt_id"].isin(first_ids)]
    die_fail = set(
        attempts.loc[
            (attempts["attempt_number"].astype(int) == 1) & (attempts["pass_fail"].astype(str) == "FAIL"),
            "attempt_id",
        ].astype(str)
    )
    rows = []
    for name in PARAMS:
        block = first[first["parameter_name"].astype(str) == name]
        limit_fail = block[block["pass_fail"].astype(str) == "FAIL"]
        rows.append(
            {
                "parameter": name,
                "decision": "REJECTED",
                "first_pass_rows": int(len(block)),
                "retest_rows_excluded": int((retest["parameter_name"].astype(str) == name).sum()),
                "limit_fail_rows": int(len(limit_fail)),
                "limit_fail_and_first_pass_fail": int(limit_fail["attempt_id"].isin(die_fail).sum()),
                "accepted_into_matrix": False,
                "reason": (
                    "The numeric measurement is recorded on the first-pass attempt and the generator "
                    "sets that attempt to FAIL when the value is outside its limit. It is an in-test "
                    "result, not an input available before the first-pass outcome. The parametric "
                    "pass_fail column is the limit result and is rejected. Retest rows are excluded. "
                    "A generator shift that correlates a measurement with failure is not the reason "
                    "for this rejection."
                ),
            }
        )
    return rows


def _factory(grid_border: bool, relative_time: bool) -> Callable:
    def build(frame: pd.DataFrame, y: pd.Series):
        return fit_experiment_builder(frame, y, grid_border=grid_border, relative_time=relative_time)

    return build


def _train_spec(data, cfg, *, name: str, grid_border: bool, relative_time: bool) -> dict[str, Any]:
    factory = _factory(grid_border, relative_time)
    bench = run_lolo_models(
        data,
        model_names=["logistic"],
        cfg=cfg,
        with_importance=False,
        builder_factory=factory,
    )
    block = bench["models"]["logistic"]
    pooled = dict(block["calibrated"])
    per_lot = [{"lot": row["lot"], **_slim(row)} for row in block["per_lot_calibrated"]]
    status = ml_support_status(pooled, per_lot, float(pooled.get("positive_rate") or 0.1004))
    return {
        "name": name,
        "grid_border": grid_border,
        "relative_time": relative_time,
        "pooled": _slim(pooled) | {"ece": pooled.get("ece"), "positive_rate": pooled.get("positive_rate")},
        "per_lot": per_lot,
        "feature_names": list(block["feature_names"]),
        "ml_support_status": status,
        "_oof_raw": bench["_oof"]["logistic"]["raw"],
        "_oof_cal": bench["_oof"]["logistic"]["cal"],
    }


def _lots_improved(candidate: dict[str, Any], baseline: dict[str, Any]) -> int:
    base = {row["lot"]: row for row in baseline["per_lot"]}
    wins = 0
    for row in candidate["per_lot"]:
        other = base.get(row["lot"])
        if other is None or row.get("pr_auc") is None or other.get("pr_auc") is None:
            continue
        if float(row["pr_auc"]) > float(other["pr_auc"]) and float(row.get("roc_auc") or 0) >= float(other.get("roc_auc") or 0):
            wins += 1
    return wins


def _choose(specs: list[dict[str, Any]], baseline: dict[str, Any]) -> dict[str, Any]:
    """Prefer a spec that beats the baseline on at least three lots. Otherwise keep the temporal spec."""
    ranked = sorted(specs, key=lambda spec: (_lots_improved(spec, baseline), spec["pooled"].get("pr_auc") or 0), reverse=True)
    best = ranked[0]
    if _lots_improved(best, baseline) >= 3 and best["ml_support_status"] == "RELIABLE":
        return best
    temporal = next(spec for spec in specs if spec["name"] == "baseline_plus_temporal")
    return temporal


def _register(meta: dict[str, Any], hashes: dict[str, str]) -> str:
    paths = default_paths()
    before = champion_hashes(paths)
    registry = load_registry(paths)
    if registry.get("active_version") != CHAMPION_VERSION:
        raise V2BuildError("refusing to register while the active model is not yi_ml_v1")
    if MODEL_ID in registry.get("models", {}):
        raise V2BuildError(f"{MODEL_ID} is already in the registry")
    for name in PROTECTED:
        if name not in registry.get("models", {}):
            raise V2BuildError(f"{name} is missing from the registry")
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
            "Experimental candidate for parametric, spatial, and lot-relative time features. "
            "Not approved. Not active. ML support stays NEEDS_MORE_DATA unless reliability checks pass."
        ),
        seed=meta["seed"],
        python_version=meta["python_version"],
        sklearn_version=meta["sklearn_version"],
        feature_contract=list(meta["feature_names"]),
        feature_contract_version=meta["feature_set_version"],
    )
    record["source_model"] = None
    record["parent_model_version"] = None
    record["experiment"] = meta["experiment"]
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
            "reason": "yi_ml_v4 feature experiment. Not activated.",
            "artifact_hashes": hashes,
            "parent_version": None,
        },
    )
    assert_champion_unchanged(paths, before)
    return "CANDIDATE"


def build_yi_ml_v4() -> dict[str, Any]:
    paths = default_paths()
    before_champion = champion_hashes(paths)
    dest = artifact_dir()
    if dest.exists():
        raise V2BuildError(f"refusing to overwrite {dest}")
    data_hashes = {name: sha256_file(dataset_dir() / name) for name in DATASET_FILES}
    protected_before = {
        name: hash_files(repo_root() / "artifacts" / "ml" / name, CHAMPION_FILES) for name in PROTECTED
    }
    cfg = load_ml_config()
    app = load_config()
    data = load_ml_dataset(dataset_dir(), config=app)
    contract = assert_training_contract(data, cfg)
    audit = audit_parametrics()
    if any(row["accepted_into_matrix"] for row in audit):
        raise V2BuildError("parametric audit accepted a column; the trainer does not yet have that path")
    baseline = _saved_report("yi_ml_v2")
    spatial = _saved_report("yi_ml_v3_spatial")
    temporal = _train_spec(data, cfg, name="baseline_plus_temporal", grid_border=False, relative_time=True)
    combined = _train_spec(
        data,
        cfg,
        name="baseline_plus_spatial_plus_temporal",
        grid_border=True,
        relative_time=True,
    )
    chosen = _choose([temporal, combined], baseline)
    public_specs = []
    for spec in (
        {"name": "baseline", "model_id": "yi_ml_v2", "retrained": False, **baseline},
        {"name": "baseline_plus_spatial", "model_id": "yi_ml_v3_spatial", "retrained": False, **spatial},
        temporal,
        combined,
    ):
        public_specs.append(
            {
                "name": spec["name"],
                "model_id": spec.get("model_id"),
                "retrained": spec.get("retrained", True),
                "pooled": spec["pooled"],
                "per_lot": spec["per_lot"],
                "feature_names": spec.get("feature_names"),
                "ml_support_status": spec.get("ml_support_status")
                or ml_support_status(spec["pooled"], spec["per_lot"], float(spec["pooled"].get("positive_rate") or 0.1004)),
            }
        )
    builder = fit_experiment_builder(
        data.frame,
        data.y,
        grid_border=chosen["grid_border"],
        relative_time=chosen["relative_time"],
    )
    x_all = builder.transform(data.frame)
    if any(name in x_all.columns for name in PARAMS):
        raise V2BuildError("rejected parametric column entered the matrix")
    y = data.y.to_numpy()
    numeric = [c for c in builder.numeric_features_ if c in x_all.columns]
    categorical = [c for c in builder.categorical_features_ if c in x_all.columns]
    pipeline = make_model("logistic", cfg, cfg.seed, numeric, categorical)
    pipeline.fit(x_all, y)
    calibrator = ProbabilityCalibrator().fit(chosen["_oof_raw"], y)
    bundle = TrainedBundle(
        model_name="logistic",
        pipeline=pipeline,
        builder=builder,
        calibrator=calibrator,
        oof_raw=chosen["_oof_raw"],
        oof_cal=chosen["_oof_cal"],
        comparison=[],
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
    if not predictions or "root_cause" in predictions[0].model_dump():
        raise V2BuildError("inference smoke check failed")
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
    support = chosen["ml_support_status"]
    meta = {
        "model_id": MODEL_ID,
        "model_version": MODEL_ID,
        "model_name": "logistic",
        "architecture": "logistic_regression",
        "model_family": "logistic_regression",
        "dataset_id": DATASET_ID,
        "dataset_path": f"data/synthetic/agent_visible/{DATASET_ID}/",
        "sample_count": EXPECTED_ROWS,
        "positive_count": EXPECTED_POS,
        "negative_count": EXPECTED_NEG,
        "target": "first_pass_fail",
        "feature_count": len(x_all.columns),
        "feature_names": list(x_all.columns),
        "feature_contract": list(ACTIVE_FEATURE_CONTRACT),
        "experiment": chosen["name"],
        "grid_border": chosen["grid_border"],
        "relative_time": chosen["relative_time"],
        "parametric_join": False,
        "parametric_audit": "all_eight_rejected",
        "ml_support_status": support,
        "suitable_for_lifecycle_validation": support == "RELIABLE",
        "promoted": False,
        "feature_set_version": cfg.feature_set_version,
        "split_strategy": "leave_one_lot_out",
        "n_folds": 5,
        "state": "CANDIDATE",
        "production_authorized": False,
        "automatic_activation": False,
        "training_date": trained_at,
        "trained_at": trained_at,
        "calibration_method": cfg.calibration.method,
        "seed": cfg.seed,
        "decision_threshold": 0.5,
        "threshold_fit_on_test_fold": False,
        "git_revision": _git_revision(),
        "python_version": sys.version.split()[0],
        "sklearn_version": sklearn_version,
        "training_config_hash": config_hash,
        "disclaimer": DISCLAIMER,
        "not_a_root_cause": True,
        "selected_metrics": chosen["pooled"],
    }
    evaluation = {
        "experiment": chosen["name"],
        "parametric_audit": audit,
        "experiments": public_specs,
        "aggregate_calibrated": chosen["pooled"],
        "per_lot_calibrated": chosen["per_lot"],
        "ece_calibrated": chosen["pooled"].get("ece"),
        "ml_support_status": support,
        "promoted": False,
        "folds": contract["folds"],
        "disclaimer": DISCLAIMER,
        "constant_positive_rate": 0.1004,
        "constant_brier": 0.1004 * 0.8996,
        "roc_reference": 0.5,
    }
    dest.mkdir(parents=True, exist_ok=False)
    blob = pickle.dumps(
        {
            "pipeline": pipeline,
            "builder": builder,
            "calibrator": calibrator,
            "model_name": "logistic",
            "feature_names": list(x_all.columns),
            "split_strategy": "leave_one_lot_out",
        },
        protocol=4,
    )
    (dest / "model.pkl").write_bytes(blob)
    (dest / "metadata.json").write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (dest / "feature_list.json").write_text(json.dumps(list(x_all.columns), indent=2) + "\n", encoding="utf-8")
    (dest / "metrics.json").write_text(
        dumps(json_safe({"model_name": "logistic", "metrics": chosen["pooled"], "per_lot": chosen["per_lot"], "disclaimer": DISCLAIMER})),
        encoding="utf-8",
    )
    (dest / "evaluation.json").write_text(dumps(json_safe(evaluation)), encoding="utf-8")
    (dest / "parametric_audit.json").write_text(dumps(json_safe(audit)), encoding="utf-8")
    hashes = hash_files(dest, CHAMPION_FILES)
    (dest / "hashes.json").write_text(dumps(hashes), encoding="utf-8")
    state = _register(meta, hashes)
    for name, before in protected_before.items():
        if hash_files(repo_root() / "artifacts" / "ml" / name, CHAMPION_FILES) != before:
            raise V2BuildError(f"{name} artifacts changed")
    if {name: sha256_file(dataset_dir() / name) for name in DATASET_FILES} != data_hashes:
        raise V2BuildError("dataset files changed")
    attempts = load_die_attempts(dataset_dir() / "die_attempts.csv", app).attempts
    tests = load_test_results(dataset_dir() / "test_results.csv", app).test_results
    fpy = calculate_fpy(attempts, app, test_results=tests)
    if (
        fpy.eligible_die_count != EXPECTED_ROWS
        or fpy.first_pass_fail_count != EXPECTED_POS
        or fpy.first_pass_pass_count != EXPECTED_NEG
        or abs(float(fpy.fpy) - 0.8996) > 1e-9
        or sum(row.n_dies for row in fpy.primary_fail_pareto) != EXPECTED_POS
    ):
        raise V2BuildError("FPY or Pareto totals changed")
    assert_champion_unchanged(paths, before_champion)
    # Default builder must still be the 16-column contract.
    default_names = list(fit_feature_builder(data.frame, data.y).feature_names_)
    if default_names != list(ACTIVE_FEATURE_CONTRACT):
        raise V2BuildError(f"default feature builder changed: {default_names}")
    summary = {
        "state": state,
        "chosen": chosen["name"],
        "ml_support_status": support,
        "experiments": public_specs,
        "audit_rejected": [row["parameter"] for row in audit],
    }
    print(json.dumps(json_safe(summary), indent=2))
    return summary


def main() -> int:
    build_yi_ml_v4()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
