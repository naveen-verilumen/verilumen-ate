"""Evaluation-only architecture benchmark. Never writes artifacts/ml/yi_ml_v1."""

from __future__ import annotations

import pickle
import time
from typing import Any, Iterable

import numpy as np
import pandas as pd

from yield_improvement.ml.calibration import ProbabilityCalibrator
from yield_improvement.ml.config import MLAppConfig, load_ml_config
from yield_improvement.ml.dataset import MLDataset
from yield_improvement.ml.evaluation import compute_metrics, failure_capture_at_fraction
from yield_improvement.ml.explain import permutation_ranks
from yield_improvement.ml.features import fit_feature_builder
from yield_improvement.ml.models import make_model, make_preprocessor
from yield_improvement.ml.split import make_splits
from yield_improvement.ml.train import _align, _weights
from sklearn.pipeline import Pipeline

CORE_MODELS = ("logistic", "random_forest", "hist_gbm")
EXTRA_CANDIDATES = ("xgboost", "lightgbm", "catboost")
FORBIDDEN_FEATURES = {
    "lot_id",
    "wafer_id",
    "die_id",
    "scenario_id",
    "true_cause",
    "injected_effect",
    "generator_seed",
    "ground_truth",
}
ACTIVE_FEATURE_CONTRACT = [
    "die_x",
    "die_y",
    "normalized_x",
    "normalized_y",
    "radial_distance",
    "edge_distance",
    "spatial_region",
    "timestamp_epoch",
    "temperature_c",
    "voltage_v",
    "site",
    "tester_id",
    "probe_card_id",
    "prober_id",
    "tester_fail_rate",
    "probe_fail_rate",
]


def probe_extra_models() -> tuple[list[str], dict[str, str]]:
    available: list[str] = []
    unavailable: dict[str, str] = {}
    try:
        import xgboost  # noqa: F401

        available.append("xgboost")
    except Exception as exc:  # noqa: BLE001
        unavailable["xgboost"] = f"unavailable_due_to_environment:{type(exc).__name__}"
    try:
        import lightgbm  # noqa: F401

        available.append("lightgbm")
    except Exception as expected:  # noqa: BLE001
        unavailable["lightgbm"] = f"unavailable_due_to_environment:{type(expected).__name__}"
    try:
        import catboost  # noqa: F401

        available.append("catboost")
    except Exception as expected:  # noqa: BLE001
        unavailable["catboost"] = f"unavailable_due_to_environment:{type(expected).__name__}"
    return available, unavailable


def make_benchmark_model(name: str, cfg: MLAppConfig, seed: int, numeric: list[str], categorical: list[str], y_train: np.ndarray) -> Pipeline:
    if name in CORE_MODELS:
        return make_model(name, cfg, seed, numeric, categorical)
    pre = make_preprocessor(numeric, categorical)
    n1 = float(y_train.sum())
    n0 = float(len(y_train) - n1)
    spw = (n0 / n1) if n1 > 0 else 1.0
    if name == "extra_trees":
        from sklearn.ensemble import ExtraTreesClassifier

        clf = ExtraTreesClassifier(
            n_estimators=cfg.models.random_forest.n_estimators,
            min_samples_leaf=cfg.models.random_forest.min_samples_leaf,
            class_weight=cfg.models.random_forest.class_weight,
            max_depth=cfg.models.random_forest.max_depth,
            random_state=seed,
            n_jobs=1,
        )
    elif name == "mlp":
        from sklearn.neural_network import MLPClassifier

        clf = MLPClassifier(
            hidden_layer_sizes=(16,),
            activation="relu",
            solver="adam",
            alpha=1e-4,
            batch_size=64,
            learning_rate_init=1e-3,
            max_iter=80,
            shuffle=True,
            early_stopping=False,
            random_state=seed,
        )
    elif name == "xgboost":
        from xgboost import XGBClassifier

        clf = XGBClassifier(
            n_estimators=50,
            max_depth=4,
            learning_rate=0.08,
            subsample=0.9,
            colsample_bytree=0.9,
            random_state=seed,
            n_jobs=1,
            eval_metric="logloss",
            scale_pos_weight=spw,
        )
    elif name == "lightgbm":
        from lightgbm import LGBMClassifier

        clf = LGBMClassifier(
            n_estimators=50,
            max_depth=4,
            learning_rate=0.08,
            random_state=seed,
            n_jobs=1,
            verbose=-1,
            scale_pos_weight=spw,
        )
    elif name == "catboost":
        from catboost import CatBoostClassifier

        clf = CatBoostClassifier(
            iterations=50,
            depth=4,
            learning_rate=0.08,
            random_seed=seed,
            verbose=False,
            allow_writing_files=False,
            auto_class_weights="Balanced",
        )
    else:
        raise ValueError(name)
    return Pipeline([("pre", pre), ("clf", clf)])


def _ece(y: np.ndarray, proba: np.ndarray, n_bins: int = 10, min_count: int = 8) -> tuple[float | None, list[dict[str, Any]]]:
    p = np.clip(np.asarray(proba, dtype=float), 0.0, 1.0)
    y = np.asarray(y, dtype=float)
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    bins: list[dict[str, Any]] = []
    ece = 0.0
    used = 0
    n = len(y)
    if n == 0:
        return None, bins
    for i in range(n_bins):
        lo, hi = edges[i], edges[i + 1]
        mask = (p >= lo) & (p <= hi) if i == n_bins - 1 else (p >= lo) & (p < hi)
        count = int(mask.sum())
        label = f"{lo:.1f}-{hi:.1f}"
        if count < min_count:
            bins.append({"bin": label, "sample_count": count, "insufficient_sample_size": True})
            continue
        mean_p = float(p[mask].mean())
        obs = float(y[mask].mean())
        bins.append(
            {
                "bin": label,
                "mean_prediction": mean_p,
                "observed_failure_rate": obs,
                "sample_count": count,
                "insufficient_sample_size": False,
            }
        )
        ece += (count / n) * abs(mean_p - obs)
        used += count
    if used < min_count * 2:
        return None, bins
    return float(ece), bins


def metrics_bundle(y: np.ndarray, proba: np.ndarray) -> dict[str, Any]:
    if y.size == 0:
        return {"n_samples": 0, "n_positives": 0}
    m = compute_metrics(y, proba)
    payload = m.model_dump()
    payload["failure_capture_at_top_5_percent"] = failure_capture_at_fraction(y, proba, 0.05)
    ece, bins = _ece(y, proba)
    payload["ece"] = ece
    payload["calibration_error"] = ece
    payload["reliability_bins"] = bins
    return payload


def _summarize(values: list[float | None]) -> dict[str, float | None]:
    clean = [float(v) for v in values if v is not None and np.isfinite(v)]
    if not clean:
        return {"mean": None, "std": None, "min": None, "max": None, "n": 0}
    arr = np.array(clean, dtype=float)
    return {
        "mean": float(arr.mean()),
        "std": float(arr.std(ddof=1)) if arr.size > 1 else 0.0,
        "min": float(arr.min()),
        "max": float(arr.max()),
        "n": int(arr.size),
    }


def fold_assignments(data: MLDataset, cfg: MLAppConfig | None = None) -> tuple[str, list[tuple[np.ndarray, np.ndarray]], list[dict[str, Any]]]:
    cfg = cfg or load_ml_config()
    groups = data.groups.to_numpy()
    strategy, splits = make_splits(groups, cfg)
    rows = []
    wafers = data.frame["wafer_id"].astype(str).to_numpy() if "wafer_id" in data.frame else np.array(["?"] * len(groups))
    lots = groups.astype(str)
    for train_idx, test_idx in splits:
        train_lots = set(lots[train_idx])
        test_lots = set(lots[test_idx])
        if train_lots & test_lots:
            raise ValueError("lot leakage across train/test")
        train_w = set(zip(lots[train_idx], wafers[train_idx]))
        test_w = set(zip(lots[test_idx], wafers[test_idx]))
        if train_w & test_w:
            raise ValueError("wafer leakage across train/test")
        held = sorted(test_lots)
        if len(held) != 1:
            raise ValueError("expected a single held-out lot for LOLO")
        rows.append(
            {
                "held_out_lot": held[0],
                "train_lots": sorted(train_lots),
                "n_train": int(len(train_idx)),
                "n_test": int(len(test_idx)),
            }
        )
    return strategy, splits, rows


IDENTITY_KEYS = {"lot_id", "wafer_id", "die_id", "attempt_id"}


def _assert_feature_contract(columns: Iterable[str], *, allow_identity_keys: bool = False) -> None:
    cols = list(columns)
    denied = set(FORBIDDEN_FEATURES)
    if allow_identity_keys:
        denied -= IDENTITY_KEYS
    hits = []
    for col in cols:
        low = col.lower()
        if low in denied:
            hits.append(col)
            continue
        if any(low == name or low.startswith(name + "_") for name in denied):
            hits.append(col)
    if hits:
        raise ValueError(f"forbidden benchmark features: {hits}")


def _complexity(name: str, pipeline: Pipeline) -> dict[str, Any]:
    clf = pipeline.named_steps.get("clf")
    info: dict[str, Any] = {"model": name}
    try:
        blob = pickle.dumps(pipeline, protocol=4)
        info["artifact_bytes"] = int(len(blob))
    except Exception:  # noqa: BLE001
        info["artifact_bytes"] = None
    if name == "logistic" and hasattr(clf, "coef_"):
        info["n_parameters"] = int(np.prod(clf.coef_.shape) + clf.intercept_.shape[0])
    elif hasattr(clf, "n_estimators"):
        info["n_estimators"] = int(getattr(clf, "n_estimators"))
        info["max_depth"] = getattr(clf, "max_depth", None)
    elif hasattr(clf, "max_iter"):
        info["max_iter"] = int(clf.max_iter)
        info["max_depth"] = getattr(clf, "max_depth", None)
    return info


def run_lolo_models(
    data: MLDataset,
    *,
    model_names: list[str],
    cfg: MLAppConfig | None = None,
    with_importance: bool = False,
    importance_max_rows: int = 80,
    builder_factory=fit_feature_builder,
) -> dict[str, Any]:
    """Same LOLO folds for every model. Does not write the active artifact."""
    cfg = cfg or load_ml_config()
    y = data.y.to_numpy()
    groups = data.groups.to_numpy()
    strategy, splits, assignments = fold_assignments(data, cfg)
    _assert_feature_contract(data.frame.columns, allow_identity_keys=True)
    per_model: dict[str, Any] = {}
    shared_splits = [(np.array(a, copy=True), np.array(b, copy=True)) for a, b in splits]
    for name in model_names:
        oof_raw = np.full(len(y), np.nan)
        oof_cal = np.full(len(y), np.nan)
        fold_raw: list[dict[str, Any]] = []
        fold_cal: list[dict[str, Any]] = []
        fold_imp: list[list[dict[str, Any]]] = []
        train_s = 0.0
        infer_s = 0.0
        last_pipe = None
        last_cols: list[str] = []
        for fold_i, (train_idx, test_idx) in enumerate(shared_splits):
            builder = builder_factory(data.frame.iloc[train_idx], data.y.iloc[train_idx])
            x_train = builder.transform(data.frame.iloc[train_idx])
            x_test = builder.transform(data.frame.iloc[test_idx])
            x_train, x_test = _align(x_train, x_test)
            _assert_feature_contract(x_train.columns, allow_identity_keys=False)
            numeric = [c for c in builder.numeric_features_ if c in x_train.columns]
            categorical = [c for c in builder.categorical_features_ if c in x_train.columns]
            y_train = y[train_idx]
            y_test = y[test_idx]
            model = make_benchmark_model(name, cfg, cfg.seed, numeric, categorical, y_train)
            t0 = time.perf_counter()
            if name in {"hist_gbm", "mlp"}:
                model.fit(x_train, y_train, clf__sample_weight=_weights(y_train))
            else:
                model.fit(x_train, y_train)
            train_s += time.perf_counter() - t0
            t1 = time.perf_counter()
            raw_test = np.clip(model.predict_proba(x_test)[:, 1], 0.0, 1.0)
            infer_s += time.perf_counter() - t1
            raw_train = np.clip(model.predict_proba(x_train)[:, 1], 0.0, 1.0)
            calibrator = ProbabilityCalibrator().fit(raw_train, y_train)
            cal_test = calibrator.transform(raw_test)
            oof_raw[test_idx] = raw_test
            oof_cal[test_idx] = cal_test
            lot = assignments[fold_i]["held_out_lot"]
            fold_raw.append({"lot": lot, **metrics_bundle(y_test, raw_test)})
            fold_cal.append({"lot": lot, **metrics_bundle(y_test, cal_test)})
            if with_importance and len(np.unique(y_test)) > 1:
                fold_imp.append(permutation_ranks(model, x_test, y_test, cfg.seed + fold_i, max_rows=importance_max_rows))
            last_pipe = model
            last_cols = list(x_train.columns)
        missing = np.isnan(oof_raw)
        if missing.any():
            fill = float(np.nanmean(oof_raw[~missing])) if (~missing).any() else 0.5
            oof_raw[missing] = fill
            oof_cal[missing] = np.where(np.isnan(oof_cal[missing]), fill, oof_cal[missing])
        oof_raw = np.clip(oof_raw, 0.0, 1.0)
        oof_cal = np.clip(np.where(np.isnan(oof_cal), oof_raw, oof_cal), 0.0, 1.0)
        stability = {}
        for key in ("roc_auc", "pr_auc", "brier", "failure_capture_at_top_10_percent", "failure_capture_at_top_20_percent"):
            stability[key] = _summarize([row.get(key) for row in fold_raw])
        imp_stable = _importance_stability(fold_imp, last_cols) if fold_imp else []
        per_model[name] = {
            "raw": metrics_bundle(y, oof_raw),
            "calibrated": metrics_bundle(y, oof_cal),
            "per_lot_raw": fold_raw,
            "per_lot_calibrated": fold_cal,
            "lot_stability_raw": stability,
            "feature_importance_stability": imp_stable,
            "train_seconds": round(train_s, 4),
            "inference_seconds": round(infer_s, 4),
            "complexity": _complexity(name, last_pipe) if last_pipe is not None else {},
            "n_features": len(last_cols),
            "feature_names": last_cols,
            "oof_raw": oof_raw,
            "oof_cal": oof_cal,
        }
    paired = _paired(per_model, [a["held_out_lot"] for a in assignments])
    return {
        "split_strategy": strategy,
        "n_lots": int(len(np.unique(groups))),
        "n_samples": int(len(y)),
        "n_positives": int(y.sum()),
        "positive_rate": float(y.mean()),
        "fold_assignments": assignments,
        "models": {k: {kk: vv for kk, vv in v.items() if kk not in {"oof_raw", "oof_cal"}} for k, v in per_model.items()},
        "paired_fold_comparisons": paired,
        "same_folds_all_models": True,
        "_oof": {k: {"raw": v["oof_raw"], "cal": v["oof_cal"]} for k, v in per_model.items()},
        "groups": groups,
        "y": y,
    }


def _importance_stability(fold_imp: list[list[dict[str, Any]]], columns: list[str]) -> list[dict[str, Any]]:
    if not fold_imp:
        return []
    names = columns or sorted({row["feature"] for fold in fold_imp for row in fold})
    out = []
    n_folds = len(fold_imp)
    for feat in names:
        scores = []
        ranks = []
        top5 = 0
        top10 = 0
        for fold in fold_imp:
            ordered = [r["feature"] for r in fold]
            lookup = {r["feature"]: r["importance"] for r in fold}
            scores.append(float(lookup.get(feat, 0.0)))
            rank = ordered.index(feat) + 1 if feat in ordered else len(ordered) + 1
            ranks.append(rank)
            if rank <= 5:
                top5 += 1
            if rank <= 10:
                top10 += 1
        arr = np.array(scores, dtype=float)
        rr = np.array(ranks, dtype=float)
        out.append(
            {
                "feature": feat,
                "mean_importance": float(arr.mean()),
                "std_importance": float(arr.std(ddof=1)) if arr.size > 1 else 0.0,
                "rank_mean": float(rr.mean()),
                "rank_std": float(rr.std(ddof=1)) if rr.size > 1 else 0.0,
                "n_folds_top5": int(top5),
                "n_folds_top10": int(top10),
                "n_folds": n_folds,
                "note": "Predictive permutation importance only. Not a causal effect.",
            }
        )
    out.sort(key=lambda r: r["rank_mean"])
    return out


def _paired(per_model: dict[str, Any], lots: list[str]) -> list[dict[str, Any]]:
    names = list(per_model)
    rows = []
    keys = ("pr_auc", "roc_auc", "brier", "failure_capture_at_top_10_percent", "failure_capture_at_top_20_percent")
    for i, a in enumerate(names):
        for b in names[i + 1 :]:
            by_a = {r["lot"]: r for r in per_model[a]["per_lot_raw"]}
            by_b = {r["lot"]: r for r in per_model[b]["per_lot_raw"]}
            for key in keys:
                diffs = []
                for lot in lots:
                    va = by_a.get(lot, {}).get(key)
                    vb = by_b.get(lot, {}).get(key)
                    if va is None or vb is None:
                        continue
                    diffs.append(float(va) - float(vb))
                if not diffs:
                    continue
                arr = np.array(diffs, dtype=float)
                higher_is_better = key != "brier"
                a_wins = int((arr > 0).sum()) if higher_is_better else int((arr < 0).sum())
                b_wins = int((arr < 0).sum()) if higher_is_better else int((arr > 0).sum())
                rows.append(
                    {
                        "model_a": a,
                        "model_b": b,
                        "metric": key,
                        "mean_paired_difference_a_minus_b": float(arr.mean()),
                        "std_paired_difference": float(arr.std(ddof=1)) if arr.size > 1 else 0.0,
                        "n_folds": int(arr.size),
                        "n_folds_a_better": a_wins,
                        "n_folds_b_better": b_wins,
                    }
                )
    return rows
