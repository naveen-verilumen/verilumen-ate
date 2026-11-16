"""Calibration of P(first-pass-fail) vs observed rate. Ranking can remain useful."""

from __future__ import annotations

import numpy as np

from yield_improvement.monitoring.contracts import CalibrationBin, CalibrationResult
from yield_improvement.monitoring.feature_drift import _band
from yield_improvement.monitoring.thresholds import MonitoringConfig, worst_metric_status
from sklearn.metrics import brier_score_loss


def expected_calibration_error(y: np.ndarray, proba: np.ndarray, n_bins: int, min_count: int) -> tuple[float | None, list[CalibrationBin]]:
    p = np.clip(np.asarray(proba, dtype=float), 0.0, 1.0)
    y = np.asarray(y, dtype=float)
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    bins: list[CalibrationBin] = []
    ece = 0.0
    used = 0
    n = len(y)
    for i in range(n_bins):
        lo, hi = edges[i], edges[i + 1]
        if i == n_bins - 1:
            mask = (p >= lo) & (p <= hi)
        else:
            mask = (p >= lo) & (p < hi)
        count = int(mask.sum())
        label = f"{lo:.1f}-{hi:.1f}"
        if count < min_count:
            bins.append(
                CalibrationBin(
                    bin=label,
                    sample_count=count,
                    insufficient_sample_size=True,
                )
            )
            continue
        mean_p = float(p[mask].mean())
        obs = float(y[mask].mean())
        bins.append(
            CalibrationBin(
                bin=label,
                mean_prediction=mean_p,
                observed_failure_rate=obs,
                sample_count=count,
                insufficient_sample_size=False,
            )
        )
        ece += (count / n) * abs(mean_p - obs)
        used += count
    if used < min_count * 2:
        return None, bins
    return float(ece), bins


def calibration_drift(
    y: np.ndarray | None,
    proba: np.ndarray,
    reference_brier: float | None,
    cfg: MonitoringConfig,
    *,
    labeled: bool,
) -> CalibrationResult:
    if not labeled or y is None:
        return CalibrationResult(
            status="UNAVAILABLE",
            availability="UNAVAILABLE",
            notes="Calibration requires first-pass outcomes. Labels were not fabricated.",
        )
    if y.size < cfg.min_current_samples:
        return CalibrationResult(
            status="INSUFFICIENT_DATA",
            availability="INSUFFICIENT_DATA",
            notes="Too few labeled current samples for a reliable reliability curve.",
        )
    brier = float(brier_score_loss(y, np.clip(proba, 0.0, 1.0)))
    delta = None if reference_brier is None else brier - float(reference_brier)
    ece, bins = expected_calibration_error(y, proba, cfg.calibration_bins, cfg.min_bin_count)
    brier_status = _band(delta if delta is not None else 0.0, cfg.calibration.brier_increase_warning, cfg.calibration.brier_increase_review)
    if delta is None:
        brier_status = "INSUFFICIENT_DATA"
    ece_status = _band(ece, cfg.calibration.ece_warning, cfg.calibration.ece_review)
    worst = worst_metric_status(brier_status, ece_status)
    dim = "REVIEW" if worst == "REVIEW" else ("MONITOR" if worst == "WARNING" else ("INSUFFICIENT_DATA" if worst == "INSUFFICIENT_DATA" else "HEALTHY"))
    return CalibrationResult(
        status=dim,  # type: ignore[arg-type]
        availability="AVAILABLE",
        brier_reference=reference_brier,
        brier_current=brier,
        brier_delta=delta,
        ece_current=ece,
        bins=bins,
        notes="Poor calibration is not the same as 'no predictive value'. Ranking may still be useful.",
    )
