"""Schema, missingness, unseen categories, duplicates. Do not silently repair."""

from __future__ import annotations

from typing import Any

import pandas as pd

from yield_improvement.ml.config import FeaturePolicy
from yield_improvement.monitoring.contracts import DimensionSummary, MonitoringMetric
from yield_improvement.monitoring.feature_drift import CATEGORICAL
from yield_improvement.monitoring.thresholds import dimension_from_metrics


def data_quality_report(
    *,
    source_columns: list[str],
    expected_features: list[str],
    current_features: list[str],
    current_x: pd.DataFrame,
    reference_categories: dict[str, list[str]],
    policy: FeaturePolicy,
    n_source_rows: int,
    n_unique_keys: int,
) -> tuple[DimensionSummary, dict[str, Any]]:
    allowed = {c.lower() for c in policy.allowed_input_columns}
    denied = {c.lower() for c in policy.denied_columns}
    unexpected = [c for c in source_columns if c.lower() not in allowed and c.lower() not in denied]
    missing_expected = [c for c in expected_features if c not in current_features]
    extra_features = [c for c in current_features if c not in expected_features]
    missingness = {}
    for col in expected_features:
        if col not in current_x:
            missingness[col] = 1.0
            continue
        series = current_x[col]
        if col in CATEGORICAL or str(series.dtype) in {"object", "string", "category", "str"}:
            missingness[col] = float(series.isna().mean())
        else:
            missingness[col] = float(pd.to_numeric(series, errors="coerce").isna().mean())
    high_missing = [c for c, rate in missingness.items() if rate >= 0.5]
    unseen = {}
    for col, ref_cats in reference_categories.items():
        if col not in current_x.columns:
            continue
        cur = current_x[col].fillna("__missing__").astype(str)
        unseen[col] = sorted(set(cur.unique()) - set(ref_cats))
    unseen_any = any(unseen.values())
    duplicates = max(0, n_source_rows - n_unique_keys)
    critical = bool(missing_expected) or bool(high_missing)
    metrics = [
        MonitoringMetric(
            metric_name="missing_expected_feature_count",
            dimension="data_quality",
            current_value=float(len(missing_expected)),
            status="REVIEW" if missing_expected else "HEALTHY",
            sample_size=n_source_rows,
            notes=f"missing={missing_expected}" if missing_expected else "All expected model features present.",
        ),
        MonitoringMetric(
            metric_name="unexpected_source_column_count",
            dimension="data_quality",
            current_value=float(len(unexpected)),
            status="WARNING" if unexpected else "HEALTHY",
            sample_size=n_source_rows,
            notes=f"unexpected={unexpected}" if unexpected else "No unexpected source columns.",
        ),
        MonitoringMetric(
            metric_name="duplicate_key_count",
            dimension="data_quality",
            current_value=float(duplicates),
            status="WARNING" if duplicates else "HEALTHY",
            sample_size=n_source_rows,
            notes="Duplicate lot/wafer/die keys are recorded, not silently dropped.",
        ),
        MonitoringMetric(
            metric_name="high_missingness_feature_count",
            dimension="data_quality",
            current_value=float(len(high_missing)),
            status="REVIEW" if high_missing else "HEALTHY",
            sample_size=n_source_rows,
            notes=f"high_missing={high_missing}" if high_missing else "Missingness within tolerance.",
        ),
        MonitoringMetric(
            metric_name="unseen_category_features",
            dimension="data_quality",
            current_value=float(sum(1 for v in unseen.values() if v)),
            status="WARNING" if unseen_any else "HEALTHY",
            sample_size=n_source_rows,
            notes="Unseen categories are scored with training global means; they are still reported.",
        ),
    ]
    availability = "AVAILABLE"
    status = dimension_from_metrics([m.status for m in metrics], availability=availability)
    if critical:
        status = "REVIEW"
    payload = {
        "feature_missing": bool(missing_expected),
        "missing_expected_features": missing_expected,
        "unexpected_feature": bool(unexpected) or bool(extra_features),
        "unexpected_source_columns": unexpected,
        "high_missingness": high_missing,
        "unseen_categories": unseen,
        "duplicate_keys": duplicates,
        "critical": critical,
    }
    summary = DimensionSummary(
        dimension="data_quality",
        status=status,  # type: ignore[arg-type]
        availability=availability,
        metrics=metrics,
        notes="Broken fields are flagged. Values are not silently imputed beyond the frozen training preprocessor.",
    )
    return summary, payload
