"""ML run: dataset → CV train → predict → evidence. Hidden labels are never read."""

from __future__ import annotations

import json
import pickle
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from yield_improvement.config.loader import AppConfig, load_config
from yield_improvement.ml.calibration import calibration_record
from yield_improvement.ml.config import MLAppConfig, load_ml_config
from yield_improvement.ml.contracts import DISCLAIMER, MLResult
from yield_improvement.ml.dataset import MLDataset, load_ml_dataset
from yield_improvement.ml.evaluation import compute_metrics
from yield_improvement.ml.evidence import build_ml_evidence
from yield_improvement.ml.explain import permutation_ranks
from yield_improvement.ml.predict import predict_frame
from yield_improvement.ml.train import TrainedBundle, select_and_train
from yield_improvement.utils.paths import repo_root


def artifact_dir(cfg: MLAppConfig) -> Path:
    return repo_root() / "artifacts" / "ml" / cfg.ml_version


def save_artifact(bundle: TrainedBundle, cfg: MLAppConfig, extra: dict[str, Any] | None = None) -> Path:
    folder = artifact_dir(cfg)
    if (folder / "model.pkl").is_file():
        raise RuntimeError(
            f"Refusing to overwrite existing model version at {folder}. "
            "Use `yield_improvement retrain prepare/train` to create a candidate. "
            "The active champion is immutable."
        )
    folder.mkdir(parents=True, exist_ok=True)
    payload = {
        "pipeline": bundle.pipeline,
        "builder": bundle.builder,
        "calibrator": bundle.calibrator,
        "model_name": bundle.model_name,
        "feature_names": bundle.feature_names,
        "split_strategy": bundle.split_strategy,
    }
    (folder / "model.pkl").write_bytes(pickle.dumps(payload, protocol=4))
    meta = {
        "model_version": cfg.ml_version,
        "model_name": bundle.model_name,
        "feature_set_version": cfg.feature_set_version,
        "calibration_version": cfg.calibration_version,
        "split_strategy": bundle.split_strategy,
        "seed": cfg.seed,
        "feature_names": bundle.feature_names,
        "trained_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "n_features": len(bundle.feature_names),
        "disclaimer": DISCLAIMER,
        **(extra or {}),
    }
    (folder / "metadata.json").write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (folder / "feature_list.json").write_text(json.dumps(bundle.feature_names, indent=2) + "\n", encoding="utf-8")
    return folder


def load_artifact(path: Path | None, cfg: MLAppConfig) -> TrainedBundle:
    folder = path
    if folder is None:
        try:
            from yield_improvement.model_lifecycle.registry import default_paths, load_registry

            paths = default_paths()
            if paths.registry_path.is_file():
                registry = load_registry(paths)
                version = registry.get("active_version") or cfg.ml_version
                folder = paths.version_dir(version)
            else:
                folder = artifact_dir(cfg)
        except Exception:  # noqa: BLE001
            folder = artifact_dir(cfg)
    payload = pickle.loads((folder / "model.pkl").read_bytes())
    return TrainedBundle(
        model_name=payload["model_name"],
        pipeline=payload["pipeline"],
        builder=payload["builder"],
        calibrator=payload["calibrator"],
        oof_raw=np.array([]),
        oof_cal=np.array([]),
        comparison=[],
        split_strategy=payload["split_strategy"],
        n_train=0,
        n_test=0,
        feature_names=list(payload["feature_names"]),
    )


def run_ml(
    dataset_dir: str | Path,
    *,
    config: AppConfig | None = None,
    ml_config: MLAppConfig | None = None,
    persist: bool = True,
) -> MLResult:
    app = config or load_config()
    cfg = ml_config or load_ml_config()
    data = load_ml_dataset(dataset_dir, config=app)
    trained = select_and_train(data, cfg)
    y = data.y.to_numpy()
    metrics = compute_metrics(y, trained.oof_cal if trained.calibrator.fitted else trained.oof_raw)
    x_all = trained.builder.transform(data.frame)
    importances = permutation_ranks(trained.pipeline, x_all, y, cfg.seed)
    predictions = []
    for i, rec in enumerate(data.frame.to_dict(orient="records")):
        raw = float(trained.oof_raw[i])
        cal = float(trained.oof_cal[i])
        p = cal if trained.calibrator.fitted else raw
        from yield_improvement.ml.contracts import MLPrediction

        predictions.append(
            MLPrediction(
                die_id=str(rec["die_id"]),
                lot_id=str(rec["lot_id"]),
                wafer_id=str(rec["wafer_id"]),
                predicted_probability=p,
                raw_probability=raw,
                calibrated_probability=cal if trained.calibrator.fitted else None,
                predicted_class=1 if p >= 0.5 else 0,
                model_version=cfg.ml_version,
                feature_set_version=cfg.feature_set_version,
                calibration_version=cfg.calibration_version,
            )
        )
    feat_frame = trained.builder.transform(data.frame)
    evidence = build_ml_evidence(
        frame=feat_frame,
        y=y,
        predictions=predictions,
        importances=importances,
        cfg=cfg.evidence,
        model_version=cfg.ml_version,
    )
    from sklearn.metrics import brier_score_loss

    brier_raw = float(brier_score_loss(y, trained.oof_raw))
    brier_cal = float(brier_score_loss(y, trained.oof_cal))
    result = MLResult(
        analysis_id=data.analysis_id,
        model_name=trained.model_name,
        model_version=cfg.ml_version,
        feature_set_version=cfg.feature_set_version,
        calibration_version=cfg.calibration_version,
        split_strategy=trained.split_strategy,
        seed=cfg.seed,
        n_features=len(trained.feature_names),
        n_train=trained.n_train,
        n_validation=0,
        n_test=trained.n_test,
        metrics=metrics,
        comparison=trained.comparison,
        calibration=calibration_record(cfg.calibration.method, trained.calibrator.fitted, brier_raw, brier_cal),
        predictions=predictions,
        feature_importance=importances,
        evidence=evidence,
        feature_names=trained.feature_names,
        limitations=list(cfg.limitations) + [DISCLAIMER],
        not_a_root_cause=True,
        production_action="FORBIDDEN",
        production_authorized=False,
        safety_eligible_production_rate=0.0,
        invoked_agents=[],
        disclaimer=DISCLAIMER,
    )
    if persist:
        folder = save_artifact(
            trained,
            cfg,
            extra={
                "analysis_id": data.analysis_id,
                "n_samples": int(len(y)),
                "selected_metrics": metrics.model_dump(),
            },
        )
        (folder / "metrics.json").write_text(
            json.dumps(
                {
                    "model_name": trained.model_name,
                    "metrics": metrics.model_dump(),
                    "comparison": trained.comparison,
                    "disclaimer": DISCLAIMER,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    return result


def run_ml_and_compose(dataset_dir: str | Path, *, config: AppConfig | None = None, persist: bool = True):
    """Train/score ML then compose hypotheses with ML as secondary evidence."""
    from yield_improvement.detectors.runner import run_detectors_on_dir
    from yield_improvement.hypotheses.composer import compose
    from yield_improvement.pipeline import run_fixture_dir

    app = config or load_config()
    ml_result = run_ml(dataset_dir, config=app, persist=persist)
    folder = Path(dataset_dir)
    detectors = run_detectors_on_dir(folder, config=app)
    fpy_value = None
    if (folder / "die_attempts.csv").is_file():
        fpy_value = run_fixture_dir(folder, config=app).fpy
    from yield_improvement.ml.reliability import ml_support_status

    pooled = ml_result.metrics.model_dump()
    rate = pooled.get("positive_rate")
    support = ml_support_status(pooled, None, float(rate)) if rate is not None else "NEEDS_MORE_DATA"
    hyps = compose(
        detectors,
        app,
        fpy=fpy_value,
        analysis_id=folder.name,
        ml_evidence=list(ml_result.evidence),
        ml_support_status=support,
    )
    return ml_result, hyps


def predict_dir(dataset_dir: str | Path, *, config: AppConfig | None = None, ml_config: MLAppConfig | None = None) -> list:
    app = config or load_config()
    cfg = ml_config or load_ml_config()
    data = load_ml_dataset(dataset_dir, config=app)
    trained = load_artifact(None, cfg)
    return predict_frame(
        trained,
        data.frame,
        model_version=cfg.ml_version,
        feature_set_version=cfg.feature_set_version,
        calibration_version=cfg.calibration_version,
    )
