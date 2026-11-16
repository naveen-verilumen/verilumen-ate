"""Numeric PSI/KS and categorical frequency shift. Target and hidden labels are excluded."""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import ks_2samp

from yield_improvement.monitoring.contracts import FeatureDriftResult, MetricStatus
from yield_improvement.monitoring.thresholds import MonitoringConfig, worst_metric_status

NUMERIC_SKIP = {
    "first_pass_fail",
    "y",
    "predicted_probability",
    "raw_probability",
    "calibrated_probability",
}
CATEGORICAL = {"spatial_region", "tester_id", "probe_card_id", "prober_id"}


def _psi(ref: np.ndarray, cur: np.ndarray, n_bins: int) -> float | None:
    ref = ref[np.isfinite(ref)]
    cur = cur[np.isfinite(cur)]
    if ref.size < 8 or cur.size < 8:
        return None
    lo = float(np.min(ref))
    hi = float(np.max(ref))
    if hi <= lo:
        return 0.0
    edges = np.linspace(lo, hi, n_bins + 1)
    ref_c, _ = np.histogram(np.clip(ref, lo, hi), bins=edges)
    cur_c, _ = np.histogram(np.clip(cur, lo, hi), bins=edges)
    ref_p = ref_c / max(ref_c.sum(), 1)
    cur_p = cur_c / max(cur_c.sum(), 1)
    ref_p = np.clip(ref_p, 1e-6, 1.0)
    cur_p = np.clip(cur_p, 1e-6, 1.0)
    return float(np.sum((cur_p - ref_p) * np.log(cur_p / ref_p)))


def _ks(ref: np.ndarray, cur: np.ndarray) -> float | None:
    ref = ref[np.isfinite(ref)]
    cur = cur[np.isfinite(cur)]
    if ref.size < 8 or cur.size < 8:
        return None
    return float(ks_2samp(ref, cur, alternative="two-sided").statistic)


def _band(value: float | None, warn: float, review: float, *, higher_is_worse: bool = True) -> MetricStatus:
    if value is None:
        return "INSUFFICIENT_DATA"
    if higher_is_worse:
        if value >= review:
            return "REVIEW"
        if value >= warn:
            return "WARNING"
        return "HEALTHY"
    if value <= review:
        return "REVIEW"
    if value <= warn:
        return "WARNING"
    return "HEALTHY"


def compare_numeric(
    name: str,
    ref: np.ndarray,
    cur: np.ndarray,
    cfg: MonitoringConfig,
) -> list[FeatureDriftResult]:
    psi = _psi(ref, cur, cfg.psi_bins)
    ks = _ks(ref, cur)
    n_ref = int(np.isfinite(ref).sum())
    n_cur = int(np.isfinite(cur).sum())
    return [
        FeatureDriftResult(
            feature_name=name,
            data_type="numeric",
            metric="psi",
            reference_value=0.0,
            current_value=psi,
            status=_band(psi, cfg.feature_drift.psi_warning, cfg.feature_drift.psi_review),
            reference_sample_size=n_ref,
            current_sample_size=n_cur,
            notes="PSI thresholds are TO_BE_CALIBRATED and not universally valid.",
        ),
        FeatureDriftResult(
            feature_name=name,
            data_type="numeric",
            metric="ks",
            reference_value=0.0,
            current_value=ks,
            status=_band(ks, cfg.feature_drift.ks_warning, cfg.feature_drift.ks_review),
            reference_sample_size=n_ref,
            current_sample_size=n_cur,
            notes="KS statistic. Not a causal test.",
        ),
    ]


def compare_categorical(name: str, ref: pd.Series, cur: pd.Series, cfg: MonitoringConfig) -> list[FeatureDriftResult]:
    ref_c = ref.fillna("__missing__").astype(str)
    cur_c = cur.fillna("__missing__").astype(str)
    ref_freq = ref_c.value_counts(normalize=True)
    cur_freq = cur_c.value_counts(normalize=True)
    keys = sorted(set(ref_freq.index) | set(cur_freq.index))
    l1 = 0.5 * sum(abs(float(cur_freq.get(k, 0.0)) - float(ref_freq.get(k, 0.0))) for k in keys)
    unseen = set(cur_c.unique()) - set(ref_c.unique())
    unseen_rate = float(cur_c.isin(unseen).mean()) if len(cur_c) else 0.0
    n_ref, n_cur = int(len(ref_c)), int(len(cur_c))
    return [
        FeatureDriftResult(
            feature_name=name,
            data_type="categorical",
            metric="category_frequency_l1",
            reference_value=0.0,
            current_value=float(l1),
            status=_band(float(l1), cfg.feature_drift.category_shift_warning, cfg.feature_drift.category_shift_review),
            reference_sample_size=n_ref,
            current_sample_size=n_cur,
            notes="Half L1 frequency shift.",
        ),
        FeatureDriftResult(
            feature_name=name,
            data_type="categorical",
            metric="unseen_category_rate",
            reference_value=0.0,
            current_value=unseen_rate,
            status=_band(unseen_rate, cfg.feature_drift.unseen_category_warning, cfg.feature_drift.unseen_category_review),
            reference_sample_size=n_ref,
            current_sample_size=n_cur,
            notes="Share of current rows with a category absent from the reference.",
        ),
    ]


def feature_drift_table(
    ref_x: pd.DataFrame,
    cur_x: pd.DataFrame,
    cfg: MonitoringConfig,
) -> list[FeatureDriftResult]:
    rows: list[FeatureDriftResult] = []
    columns = [c for c in ref_x.columns if c not in NUMERIC_SKIP]
    for name in columns:
        if name not in cur_x.columns:
            rows.append(
                FeatureDriftResult(
                    feature_name=name,
                    data_type="categorical" if name in CATEGORICAL else "numeric",
                    metric="missing_on_current",
                    reference_value=1.0,
                    current_value=0.0,
                    status="REVIEW",
                    reference_sample_size=len(ref_x),
                    current_sample_size=len(cur_x),
                    notes="Expected feature missing on current population.",
                )
            )
            continue
        if name in CATEGORICAL or str(ref_x[name].dtype) in {"object", "string", "category"}:
            rows.extend(compare_categorical(name, ref_x[name], cur_x[name], cfg))
        else:
            rows.extend(
                compare_numeric(
                    name,
                    pd.to_numeric(ref_x[name], errors="coerce").to_numpy(dtype=float),
                    pd.to_numeric(cur_x[name], errors="coerce").to_numpy(dtype=float),
                    cfg,
                )
            )
    return rows


def feature_dimension_status(details: list[FeatureDriftResult], cfg: MonitoringConfig) -> tuple[str, str]:
    statuses = [d.status for d in details]
    if not details:
        return "INSUFFICIENT_DATA", "INSUFFICIENT_DATA"
    review_features = {d.feature_name for d in details if d.status == "REVIEW"}
    if len(review_features) >= cfg.feature_drift.n_features_review_for_multi:
        return "REVIEW", "AVAILABLE"
    worst = worst_metric_status(*statuses)
    if worst == "REVIEW":
        return "REVIEW", "AVAILABLE"
    if worst == "WARNING":
        return "MONITOR", "AVAILABLE"
    if worst == "INSUFFICIENT_DATA":
        return "INSUFFICIENT_DATA", "INSUFFICIENT_DATA"
    return "HEALTHY", "AVAILABLE"
