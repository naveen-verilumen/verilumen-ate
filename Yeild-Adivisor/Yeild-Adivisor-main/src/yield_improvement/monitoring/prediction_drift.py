"""Compare reference vs current predicted-probability distributions. Not model failure."""

from __future__ import annotations

import numpy as np

from yield_improvement.monitoring.contracts import DimensionSummary, MonitoringMetric
from yield_improvement.monitoring.feature_drift import _band, _ks, _psi
from yield_improvement.monitoring.thresholds import MonitoringConfig, dimension_from_metrics


def prediction_stats(proba: np.ndarray) -> dict[str, float]:
    p = np.clip(np.asarray(proba, dtype=float), 0.0, 1.0)
    p = p[np.isfinite(p)]
    if p.size == 0:
        return {"mean": float("nan"), "median": float("nan"), "q10": float("nan"), "q90": float("nan"), "positive_rate": float("nan")}
    return {
        "mean": float(np.mean(p)),
        "median": float(np.median(p)),
        "q10": float(np.quantile(p, 0.10)),
        "q90": float(np.quantile(p, 0.90)),
        "positive_rate": float((p >= 0.5).mean()),
    }


def prediction_drift(
    ref: np.ndarray,
    cur: np.ndarray,
    cfg: MonitoringConfig,
) -> DimensionSummary:
    note = "Prediction distribution change is not automatically model failure."
    if cur.size < cfg.min_current_samples:
        return DimensionSummary(
            dimension="prediction_drift",
            status="INSUFFICIENT_DATA",
            availability="INSUFFICIENT_DATA",
            notes="Too few current predictions to compare distributions.",
        )
    ref_s = prediction_stats(ref)
    cur_s = prediction_stats(cur)
    mean_delta = abs(cur_s["mean"] - ref_s["mean"])
    pos_delta = abs(cur_s["positive_rate"] - ref_s["positive_rate"])
    psi = _psi(np.asarray(ref, dtype=float), np.asarray(cur, dtype=float), cfg.psi_bins)
    ks = _ks(np.asarray(ref, dtype=float), np.asarray(cur, dtype=float))
    metrics = [
        MonitoringMetric(
            metric_name="mean_probability_abs_delta",
            dimension="prediction_drift",
            reference_value=ref_s["mean"],
            current_value=cur_s["mean"],
            delta=mean_delta,
            threshold=cfg.prediction_drift.mean_abs_warning,
            status=_band(mean_delta, cfg.prediction_drift.mean_abs_warning, cfg.prediction_drift.mean_abs_review),
            sample_size=int(cur.size),
            notes=note,
        ),
        MonitoringMetric(
            metric_name="positive_prediction_rate_abs_delta",
            dimension="prediction_drift",
            reference_value=ref_s["positive_rate"],
            current_value=cur_s["positive_rate"],
            delta=pos_delta,
            threshold=cfg.prediction_drift.positive_rate_abs_warning,
            status=_band(pos_delta, cfg.prediction_drift.positive_rate_abs_warning, cfg.prediction_drift.positive_rate_abs_review),
            sample_size=int(cur.size),
            notes=note,
        ),
        MonitoringMetric(
            metric_name="prediction_psi",
            dimension="prediction_drift",
            reference_value=0.0,
            current_value=psi,
            delta=psi,
            threshold=cfg.prediction_drift.psi_warning,
            status=_band(psi, cfg.prediction_drift.psi_warning, cfg.prediction_drift.psi_review),
            sample_size=int(cur.size),
            notes=note,
        ),
        MonitoringMetric(
            metric_name="prediction_ks",
            dimension="prediction_drift",
            reference_value=0.0,
            current_value=ks,
            delta=ks,
            threshold=cfg.prediction_drift.ks_warning,
            status=_band(ks, cfg.prediction_drift.ks_warning, cfg.prediction_drift.ks_review),
            sample_size=int(cur.size),
            notes=note,
        ),
    ]
    availability = "AVAILABLE"
    status = dimension_from_metrics([m.status for m in metrics], availability=availability)
    return DimensionSummary(
        dimension="prediction_drift",
        status=status,  # type: ignore[arg-type]
        availability=availability,
        metrics=metrics,
        notes=note,
    )
