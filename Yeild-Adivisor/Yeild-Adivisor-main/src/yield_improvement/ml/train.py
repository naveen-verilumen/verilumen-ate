"""Group-aware training. Preprocessing is fit on training lots only."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from yield_improvement.ml.calibration import ProbabilityCalibrator
from yield_improvement.ml.config import MLAppConfig
from yield_improvement.ml.dataset import MLDataset
from yield_improvement.ml.evaluation import compute_metrics
from yield_improvement.ml.features import FeatureBuilder, fit_feature_builder
from yield_improvement.ml.models import MODEL_ORDER, SIMPLICITY, make_model
from yield_improvement.ml.split import make_splits


def _align(train: pd.DataFrame, test: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    cols = list(train.columns)
    for col in cols:
        if col not in test.columns:
            test[col] = np.nan
    return train[cols], test[cols]


def _weights(y: np.ndarray) -> np.ndarray:
    n = len(y)
    n1 = float(y.sum())
    n0 = float(n - n1)
    w = np.ones(n, dtype=float)
    if n1 > 0 and n0 > 0:
        w[y == 1] = n / (2.0 * n1)
        w[y == 0] = n / (2.0 * n0)
    return w


@dataclass
class TrainedBundle:
    model_name: str
    pipeline: object
    builder: FeatureBuilder
    calibrator: ProbabilityCalibrator
    oof_raw: np.ndarray
    oof_cal: np.ndarray
    comparison: list[dict]
    split_strategy: str
    n_train: int
    n_test: int
    feature_names: list[str] = field(default_factory=list)


def _cv_oof(name: str, data: MLDataset, cfg: MLAppConfig, splits) -> np.ndarray:
    y = data.y.to_numpy()
    groups = data.groups.to_numpy()
    oof = np.full(len(y), np.nan)
    for train_idx, test_idx in splits:
        builder = fit_feature_builder(data.frame.iloc[train_idx], data.y.iloc[train_idx])
        x_train = builder.transform(data.frame.iloc[train_idx])
        x_test = builder.transform(data.frame.iloc[test_idx])
        x_train, x_test = _align(x_train, x_test)
        numeric = [c for c in builder.numeric_features_ if c in x_train.columns]
        categorical = [c for c in builder.categorical_features_ if c in x_train.columns]
        model = make_model(name, cfg, cfg.seed, numeric, categorical)
        y_train = y[train_idx]
        if name == "hist_gbm":
            model.fit(x_train, y_train, clf__sample_weight=_weights(y_train))
        else:
            model.fit(x_train, y_train)
        oof[test_idx] = model.predict_proba(x_test)[:, 1]
    missing = np.isnan(oof)
    if missing.any():
        oof[missing] = float(np.nanmean(oof[~missing])) if (~missing).any() else 0.5
    return np.clip(oof, 0.0, 1.0)


def select_and_train(data: MLDataset, cfg: MLAppConfig) -> TrainedBundle:
    groups = data.groups.to_numpy()
    y = data.y.to_numpy()
    strategy, splits = make_splits(groups, cfg)
    comparison = []
    oof_by_name: dict[str, np.ndarray] = {}
    for name in MODEL_ORDER:
        oof = _cv_oof(name, data, cfg, splits)
        oof_by_name[name] = oof
        metrics = compute_metrics(y, oof)
        comparison.append(
            {
                "model": name,
                "roc_auc": metrics.roc_auc,
                "pr_auc": metrics.pr_auc,
                "f1": metrics.f1,
                "recall": metrics.recall,
                "brier": metrics.brier,
                "failure_capture_at_top_10_percent": metrics.failure_capture_at_top_10_percent,
                "failure_capture_at_top_20_percent": metrics.failure_capture_at_top_20_percent,
            }
        )
    def _key(row: dict) -> tuple:
        pr = row["pr_auc"] if row["pr_auc"] is not None else -1.0
        brier = row["brier"] if row["brier"] is not None else 1.0
        return (-pr, brier, SIMPLICITY[row["model"]])

    ranked = sorted(comparison, key=_key)
    if cfg.selection.prefer_simpler_if_close and len(ranked) > 1:
        best_pr = ranked[0]["pr_auc"] or -1.0
        close = [r for r in ranked if (r["pr_auc"] or -1.0) >= best_pr - cfg.selection.close_tolerance]
        ranked = sorted(close, key=lambda r: (SIMPLICITY[r["model"]], r["brier"] or 1.0))
    selected = ranked[0]["model"]
    oof_raw = oof_by_name[selected]
    # Nested calibration: each held-out lot is transformed by a calibrator
    # fit only on the other lots. The deployed calibrator is fit on all OOF.
    oof_cal = np.full(len(y), np.nan)
    for train_idx, test_idx in splits:
        fold_cal = ProbabilityCalibrator().fit(oof_raw[train_idx], y[train_idx])
        oof_cal[test_idx] = fold_cal.transform(oof_raw[test_idx])
    missing = np.isnan(oof_cal)
    if missing.any():
        oof_cal[missing] = oof_raw[missing]
    oof_cal = np.clip(oof_cal, 0.0, 1.0)
    calibrator = ProbabilityCalibrator().fit(oof_raw, y)
    builder = fit_feature_builder(data.frame, data.y)
    x_all = builder.transform(data.frame)
    numeric = [c for c in builder.numeric_features_ if c in x_all.columns]
    categorical = [c for c in builder.categorical_features_ if c in x_all.columns]
    pipeline = make_model(selected, cfg, cfg.seed, numeric, categorical)
    if selected == "hist_gbm":
        pipeline.fit(x_all, y, clf__sample_weight=_weights(y))
    else:
        pipeline.fit(x_all, y)
    n_test = int(np.mean([len(test) for _, test in splits]))
    return TrainedBundle(
        model_name=selected,
        pipeline=pipeline,
        builder=builder,
        calibrator=calibrator,
        oof_raw=oof_raw,
        oof_cal=oof_cal,
        comparison=comparison,
        split_strategy=strategy,
        n_train=int(len(y) - n_test),
        n_test=n_test,
        feature_names=list(x_all.columns),
    )
