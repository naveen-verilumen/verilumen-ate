"""Score new lots with the persisted model and emit ModelHealthReport. Never retrains."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from yield_improvement.config.loader import AppConfig, load_config
from yield_improvement.ingestion.loader import load_die_attempts
from yield_improvement.ml.config import load_feature_policy, load_ml_config
from yield_improvement.ml.dataset import (
    SOURCE_FORBIDDEN,
    assert_source_has_no_hidden_labels,
    build_dataset,
    load_ml_dataset,
)
from yield_improvement.ml.evaluation import compute_metrics
from yield_improvement.ml.pipeline import artifact_dir, load_artifact
from yield_improvement.ml.predict import predict_frame
from yield_improvement.monitoring.calibration_drift import calibration_drift, expected_calibration_error
from yield_improvement.monitoring.contracts import DISCLAIMER, ModelHealthReport
from yield_improvement.monitoring.data_quality import data_quality_report
from yield_improvement.monitoring.feature_drift import CATEGORICAL, feature_dimension_status, feature_drift_table
from yield_improvement.monitoring.health import decide_health
from yield_improvement.monitoring.performance import performance_drift
from yield_improvement.monitoring.prediction_drift import prediction_drift, prediction_stats
from yield_improvement.monitoring.target_drift import target_drift
from yield_improvement.monitoring.thresholds import MonitoringConfig, load_monitoring_config
from yield_improvement.utils.errors import YieldImprovementError
from yield_improvement.utils.paths import repo_root


class MonitoringError(YieldImprovementError):
    pass


@dataclass
class ScoredPopulation:
    analysis_id: str
    frame: pd.DataFrame
    features: pd.DataFrame
    proba: np.ndarray
    y: np.ndarray | None
    labeled: bool
    source_columns: list[str]
    n_source_rows: int


def reference_path(cfg_ml=None) -> Path:
    ml = cfg_ml or load_ml_config()
    return artifact_dir(ml) / "reference.json"


def _load_source_columns(folder: Path) -> list[str]:
    csv = folder / "die_attempts.csv"
    return list(pd.read_csv(csv, nrows=0).columns)


def _pass_fail_present(columns: list[str], folder: Path) -> bool:
    if "pass_fail" not in {c.lower() for c in columns}:
        return False
    series = pd.read_csv(folder / "die_attempts.csv", usecols=["pass_fail"], dtype=str)
    values = series["pass_fail"].fillna("").astype(str).str.strip().str.upper()
    return bool(values.isin(["PASS", "FAIL"]).any())


def score_dataset(dataset_dir: str | Path, *, config: AppConfig | None = None) -> ScoredPopulation:
    """Predict with the persisted artifact. Does not fit or retrain."""
    folder = Path(dataset_dir)
    app = config or load_config()
    ml_cfg = load_ml_config()
    source_columns = _load_source_columns(folder)
    assert_source_has_no_hidden_labels(source_columns)
    labeled = _pass_fail_present(source_columns, folder)
    n_source = len(pd.read_csv(folder / "die_attempts.csv"))
    bundle = load_artifact(None, ml_cfg)
    if labeled:
        data = load_ml_dataset(folder, config=app)
        frame = data.frame
        y = data.y.to_numpy()
        analysis_id = data.analysis_id
    else:
        loaded = load_die_attempts(folder / "die_attempts.csv", app)
        records = []
        for attempt in loaded.attempts:
            records.append(
                {
                    "lot_id": attempt.lot_id,
                    "wafer_id": attempt.wafer_id,
                    "die_id": attempt.die_id,
                    "attempt_id": attempt.attempt_id,
                    "x": attempt.x,
                    "y": attempt.y,
                    "timestamp": attempt.timestamp,
                    "tester_id": attempt.tester_id,
                    "probe_card_id": attempt.probe_card_id,
                    "prober_id": attempt.prober_id,
                    "site": attempt.site,
                    "temperature_c": attempt.temperature_c,
                    "voltage_v": attempt.voltage_v,
                }
            )
        frame = pd.DataFrame.from_records(records)
        y = None
        analysis_id = folder.name
    if frame.empty:
        raise MonitoringError(f"No rows to score in {folder}")
    preds = predict_frame(
        bundle,
        frame,
        model_version=ml_cfg.ml_version,
        feature_set_version=ml_cfg.feature_set_version,
        calibration_version=ml_cfg.calibration_version,
    )
    features = bundle.builder.transform(frame)
    for col in bundle.feature_names:
        if col not in features.columns:
            features[col] = np.nan
    features = features[bundle.feature_names]
    proba = np.array([p.predicted_probability for p in preds], dtype=float)
    return ScoredPopulation(
        analysis_id=analysis_id,
        frame=frame,
        features=features,
        proba=proba,
        y=None if not labeled else y,
        labeled=labeled,
        source_columns=source_columns,
        n_source_rows=n_source,
    )


def build_reference_snapshot(
    reference_dir: str | Path,
    *,
    config: AppConfig | None = None,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Fit-free snapshot of the persisted model on the frozen reference population."""
    path = reference_path()
    if path.is_file() and not overwrite:
        return json.loads(path.read_text(encoding="utf-8"))
    app = config or load_config()
    ml_cfg = load_ml_config()
    mon = load_monitoring_config()
    scored = score_dataset(reference_dir, config=app)
    if not scored.labeled or scored.y is None:
        raise MonitoringError("Reference population must include first-pass labels.")
    metrics = compute_metrics(scored.y, scored.proba)
    ece, bins = expected_calibration_error(scored.y, scored.proba, mon.calibration_bins, mon.min_bin_count)
    cats = {}
    for col in CATEGORICAL:
        if col in scored.features.columns:
            cats[col] = sorted(scored.features[col].fillna("__missing__").astype(str).unique().tolist())
    feature_stats: dict[str, Any] = {}
    for col in scored.features.columns:
        series = scored.features[col]
        if col in CATEGORICAL or str(series.dtype) in {"object", "string", "category"}:
            feature_stats[col] = {
                "dtype": "categorical",
                "frequencies": series.fillna("__missing__").astype(str).value_counts(normalize=True).to_dict(),
            }
        else:
            num = pd.to_numeric(series, errors="coerce")
            feature_stats[col] = {
                "dtype": "numeric",
                "mean": float(num.mean()) if num.notna().any() else None,
                "std": float(num.std()) if num.notna().any() else None,
                "q10": float(num.quantile(0.10)) if num.notna().any() else None,
                "q90": float(num.quantile(0.90)) if num.notna().any() else None,
            }
    from sklearn.metrics import brier_score_loss

    snapshot = {
        "reference_version": mon.reference_version,
        "model_version": ml_cfg.ml_version,
        "feature_set_version": ml_cfg.feature_set_version,
        "calibration_version": ml_cfg.calibration_version,
        "reference_dataset_id": Path(reference_dir).name,
        "reference_lot_ids": sorted(scored.frame["lot_id"].astype(str).unique().tolist()),
        "training_period": {
            "min": str(pd.to_datetime(scored.frame["timestamp"], utc=True, errors="coerce").min()),
            "max": str(pd.to_datetime(scored.frame["timestamp"], utc=True, errors="coerce").max()),
        },
        "n_samples": int(len(scored.y)),
        "target_rate": float(scored.y.mean()),
        "prediction_stats": prediction_stats(scored.proba),
        "predictions": [float(x) for x in scored.proba],
        "feature_frame": scored.features.to_dict(orient="list"),
        "feature_stats": feature_stats,
        "reference_categories": cats,
        "metrics": metrics.model_dump(),
        "brier": float(brier_score_loss(scored.y, scored.proba)),
        "ece": ece,
        "calibration_bins": [b.model_dump() for b in bins],
        "feature_names": list(scored.features.columns),
        "immutable": True,
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "disclaimer": DISCLAIMER,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return snapshot


def load_reference_snapshot() -> dict[str, Any]:
    path = reference_path()
    if not path.is_file():
        raise MonitoringError("Reference snapshot is missing. Build it once from the training population.")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not payload.get("immutable"):
        raise MonitoringError("Reference snapshot must be marked immutable.")
    return payload


def _lot_summaries(frame: pd.DataFrame, proba: np.ndarray, y: np.ndarray | None, cfg: MonitoringConfig) -> list[dict[str, Any]]:
    rows = []
    work = frame.copy()
    work["_p"] = proba
    if y is not None:
        work["_y"] = y
    for lot, grp in work.groupby("lot_id", sort=True):
        item: dict[str, Any] = {
            "lot_id": str(lot),
            "n": int(len(grp)),
            "mean_prediction": float(grp["_p"].mean()),
            "n_wafers": int(grp["wafer_id"].nunique()),
        }
        if "_y" in grp:
            item["fail_rate"] = float(grp["_y"].mean())
        if int(len(grp)) < cfg.min_lot_samples:
            item["status"] = "INSUFFICIENT_DATA"
        rows.append(item)
    return rows


def _temporal(frame: pd.DataFrame, proba: np.ndarray, y: np.ndarray | None) -> tuple[bool, list[dict[str, Any]]]:
    ts = pd.to_datetime(frame.get("timestamp"), utc=True, errors="coerce") if "timestamp" in frame else pd.Series([pd.NaT] * len(frame))
    if ts.notna().sum() < 8:
        return False, []
    work = frame.copy()
    work["_p"] = proba
    work["_ts"] = ts
    if y is not None:
        work["_y"] = y
    work = work.dropna(subset=["_ts"])
    rows = []
    for lot, grp in work.sort_values("_ts").groupby("lot_id", sort=False):
        item = {
            "lot_id": str(lot),
            "min_ts": str(grp["_ts"].min()),
            "mean_prediction": float(grp["_p"].mean()),
            "n": int(len(grp)),
        }
        if "_y" in grp:
            item["fail_rate"] = float(grp["_y"].mean())
        rows.append(item)
    return True, rows


def run_monitor(
    current_dir: str | Path,
    reference_dir: str | Path,
    *,
    config: AppConfig | None = None,
    overwrite_reference: bool = False,
) -> ModelHealthReport:
    """Monitor current lots against the immutable reference. Never retrains."""
    app = config or load_config()
    ml_cfg = load_ml_config()
    mon = load_monitoring_config()
    policy = load_feature_policy()
    snapshot = build_reference_snapshot(reference_dir, config=app, overwrite=overwrite_reference)
    if Path(reference_dir).name != snapshot["reference_dataset_id"] and not overwrite_reference:
        # Keep the frozen snapshot; do not redefine the baseline.
        pass
    current = score_dataset(current_dir, config=app)
    ref_x = pd.DataFrame(snapshot["feature_frame"])
    ref_p = np.array(snapshot["predictions"], dtype=float)
    details = feature_drift_table(ref_x, current.features, mon)
    feat_status, feat_avail = feature_dimension_status(details, mon)
    from yield_improvement.monitoring.contracts import DimensionSummary, MonitoringMetric

    n_review_features = len({d.feature_name for d in details if d.status == "REVIEW"})
    feature_summary = DimensionSummary(
        dimension="feature_drift",
        status=feat_status,  # type: ignore[arg-type]
        availability=feat_avail,  # type: ignore[arg-type]
        metrics=[
            MonitoringMetric(
                metric_name="n_features_at_review",
                dimension="feature_drift",
                current_value=float(n_review_features),
                status="REVIEW" if n_review_features >= mon.feature_drift.n_features_review_for_multi else "HEALTHY",
                sample_size=len(current.features),
                notes="Count of features with REVIEW-level PSI/KS/category shift.",
            )
        ],
        notes="Feature drift is not automatically model failure.",
    )
    pred_summary = prediction_drift(ref_p, current.proba, mon)
    current_rate = float(current.y.mean()) if current.labeled and current.y is not None and current.y.size else None
    tgt_summary = target_drift(snapshot["target_rate"], current_rate, int(current.y.size) if current.y is not None else 0, mon, labeled=current.labeled)
    cal = calibration_drift(current.y, current.proba, snapshot.get("brier"), mon, labeled=current.labeled)
    perf_summary, perf_details = performance_drift(
        current.y,
        current.proba,
        snapshot.get("metrics") or {},
        mon,
        labeled=current.labeled,
    )
    n_keys = int(current.frame[["lot_id", "wafer_id", "die_id"]].drop_duplicates().shape[0]) if not current.frame.empty else 0
    dq_summary, _dq = data_quality_report(
        source_columns=current.source_columns,
        expected_features=list(snapshot["feature_names"]),
        current_features=list(current.features.columns),
        current_x=current.features,
        reference_categories=snapshot.get("reference_categories") or {},
        policy=policy,
        n_source_rows=current.n_source_rows,
        n_unique_keys=n_keys,
    )
    lots = _lot_summaries(current.frame, current.proba, current.y, mon)
    temporal_ok, temporal = _temporal(current.frame, current.proba, current.y)
    overall, triggers, recs = decide_health(
        cfg=mon,
        n_current=len(current.features),
        labeled=current.labeled,
        feature=feature_summary,
        prediction=pred_summary,
        target=tgt_summary,
        calibration=cal,
        performance=perf_summary,
        data_quality=dq_summary,
        n_feature_review=n_review_features,
    )
    limitations = list(mon.limitations) + [DISCLAIMER]
    if snapshot["reference_dataset_id"] != Path(reference_dir).name:
        limitations.append(
            f"Requested reference {Path(reference_dir).name} differs from frozen snapshot "
            f"{snapshot['reference_dataset_id']}; the immutable snapshot was used."
        )
    if not temporal_ok:
        limitations.append("Temporal monitoring unavailable: insufficient valid timestamps.")
    if not current.labeled:
        limitations.append("Unlabeled mode: target drift, calibration, and performance are UNAVAILABLE.")
    if any(token.lower() in SOURCE_FORBIDDEN for token in current.source_columns):
        raise MonitoringError("Hidden evaluation columns reached monitoring.")
    active_version = ml_cfg.ml_version
    try:
        from yield_improvement.model_lifecycle.registry import default_paths, load_registry

        paths = default_paths()
        if paths.registry_path.is_file():
            active_version = load_registry(paths).get("active_version") or ml_cfg.ml_version
    except Exception:  # noqa: BLE001
        active_version = ml_cfg.ml_version
    return ModelHealthReport(
        analysis_id=current.analysis_id,
        model_version=ml_cfg.ml_version,
        active_model_version=active_version,
        feature_version=ml_cfg.feature_set_version,
        calibration_version=ml_cfg.calibration_version,
        reference_version=snapshot["reference_version"],
        reference_dataset_id=snapshot["reference_dataset_id"],
        current_dataset_id=Path(current_dir).name,
        label_mode="LABELED" if current.labeled else "UNLABELED",
        n_lots=int(current.frame["lot_id"].nunique()) if "lot_id" in current.frame else 0,
        n_wafers=int(current.frame["wafer_id"].nunique()) if "wafer_id" in current.frame else 0,
        n_dies=int(len(current.frame)),
        feature_drift=feature_summary,
        prediction_drift=pred_summary,
        target_drift=tgt_summary,
        calibration=cal,
        performance=perf_summary,
        data_quality=dq_summary,
        overall_status=overall,
        triggers=triggers,
        recommendations=recs,
        feature_drift_details=details,
        performance_details=perf_details,
        lot_summaries=lots,
        temporal=temporal,
        temporal_available=temporal_ok,
        limitations=limitations,
    )
