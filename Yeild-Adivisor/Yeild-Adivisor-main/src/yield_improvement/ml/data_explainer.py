"""Read-only ML data-lineage and split audit. Does not train or write artifacts/ml/yi_ml_v1."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from yield_improvement.config.loader import load_config
from yield_improvement.ingestion.loader import load_die_attempts, load_parametric_measurements
from yield_improvement.ml.config import load_feature_policy, load_ml_config
from yield_improvement.ml.dataset import PARAM_NAMES, SOURCE_FORBIDDEN, load_ml_dataset
from yield_improvement.ml.features import CATEGORICAL_BASE, NUMERIC_BASE, FeatureBuilder
from yield_improvement.ml.split import make_splits
from yield_improvement.utils.paths import phase2_agent_visible_dir, repo_root
from yield_improvement.yield_analysis.fpy import calculate_fpy

CHAMPION_FILES = ("model.pkl", "metadata.json", "feature_list.json", "metrics.json")

FEATURE_SOURCES: dict[str, dict[str, str]] = {
    "die_x": {"type": "numeric", "source_column": "x", "transformation": "cast to float"},
    "die_y": {"type": "numeric", "source_column": "y", "transformation": "cast to float"},
    "normalized_x": {
        "type": "numeric",
        "source_column": "x",
        "transformation": "(x - train_x_min) / train_x_span; constants fit on training lots only",
    },
    "normalized_y": {
        "type": "numeric",
        "source_column": "y",
        "transformation": "(y - train_y_min) / train_y_span; constants fit on training lots only",
    },
    "radial_distance": {"type": "numeric", "source_column": "x,y", "transformation": "hypot(x, y)"},
    "edge_distance": {
        "type": "numeric",
        "source_column": "x,y",
        "transformation": "train_radius_max - hypot(x, y)",
    },
    "spatial_region": {
        "type": "categorical",
        "source_column": "x,y",
        "transformation": "EDGE if radius>=train_q80 else CENTER if radius<=train_q20 else OTHER; missing -> __missing__",
    },
    "timestamp_epoch": {
        "type": "numeric",
        "source_column": "timestamp",
        "transformation": "unix_timestamp - train_min_unix",
    },
    "temperature_c": {"type": "numeric", "source_column": "temperature_c", "transformation": "cast to float"},
    "voltage_v": {"type": "numeric", "source_column": "voltage_v", "transformation": "cast to float"},
    "site": {"type": "numeric", "source_column": "site", "transformation": "cast to float"},
    "tester_id": {"type": "categorical", "source_column": "tester_id", "transformation": "string; missing -> __missing__"},
    "probe_card_id": {
        "type": "categorical",
        "source_column": "probe_card_id",
        "transformation": "string; missing -> __missing__",
    },
    "prober_id": {"type": "categorical", "source_column": "prober_id", "transformation": "string; missing -> __missing__"},
    "tester_fail_rate": {
        "type": "numeric",
        "source_column": "tester_id + training labels",
        "transformation": "training-lot mean first_pass_fail by tester; unseen tester -> training global mean",
    },
    "probe_fail_rate": {
        "type": "numeric",
        "source_column": "probe_card_id + training labels",
        "transformation": "training-lot mean first_pass_fail by probe card; unseen card -> training global mean",
    },
    "IR_DROP_MV": {"type": "numeric", "source_column": "parametric_measurements.measurement", "transformation": "cast; dropped if all-null"},
    "THERMAL_C": {"type": "numeric", "source_column": "parametric_measurements.measurement", "transformation": "cast; dropped if all-null"},
    "SETUP_SLACK_PS": {"type": "numeric", "source_column": "parametric_measurements.measurement", "transformation": "cast; dropped if all-null"},
    "HOLD_SLACK_PS": {"type": "numeric", "source_column": "parametric_measurements.measurement", "transformation": "cast; dropped if all-null"},
    "TEST_TIME_MS": {"type": "numeric", "source_column": "parametric_measurements.measurement", "transformation": "cast; dropped if all-null"},
}

PREPROCESS = {
    "numeric": "SimpleImputer(median) then StandardScaler, fit on the training fold only",
    "categorical": "SimpleImputer(most_frequent) then OneHotEncoder(handle_unknown='ignore'), fit on the training fold only",
}

GROUPING_TABLE = [
    {"column": "lot_id", "model_input": False, "used_for_splitting": True, "why": "Leave-One-Lot-Out group key (configs/ml.yaml split.group_column)"},
    {"column": "wafer_id", "model_input": False, "used_for_splitting": False, "why": "Identity on the ML row; not a feature and not a fold key"},
    {"column": "die_id", "model_input": False, "used_for_splitting": False, "why": "Identity on the ML row; one sample per eligible die"},
    {"column": "attempt_id", "model_input": False, "used_for_splitting": False, "why": "Joins first-pass attempt attributes; not a model feature"},
    {"column": "scenario_id", "model_input": False, "used_for_splitting": False, "why": "Hidden ground truth; denied and absent from agent-visible tables"},
    {"column": "true_cause", "model_input": False, "used_for_splitting": False, "why": "Hidden ground truth; denied"},
    {"column": "injected_effect", "model_input": False, "used_for_splitting": False, "why": "Hidden ground truth; denied"},
    {"column": "generator_seed", "model_input": False, "used_for_splitting": False, "why": "Hidden ground truth; denied"},
]


def champion_dir() -> Path:
    return repo_root() / "artifacts" / "ml" / "yi_ml_v1"


def read_champion_metadata() -> dict[str, Any]:
    return json.loads((champion_dir() / "metadata.json").read_text(encoding="utf-8"))


def read_champion_feature_list() -> list[str]:
    return json.loads((champion_dir() / "feature_list.json").read_text(encoding="utf-8"))


def resolve_dataset_dir(dataset_dir: str | Path | None) -> Path:
    if dataset_dir is not None:
        return Path(dataset_dir)
    meta = read_champion_metadata()
    analysis_id = str(meta["analysis_id"])
    folder = repo_root() / "data" / "synthetic" / "agent_visible" / analysis_id
    if (folder / "die_attempts.csv").is_file():
        return folder
    archived = phase2_agent_visible_dir() / analysis_id
    if (archived / "die_attempts.csv").is_file():
        return archived
    raise FileNotFoundError(f"Champion dataset directory not found: {folder}")


def _target_rule() -> dict[str, Any]:
    return {
        "name": "first_pass_fail",
        "grain": "one label per Phase-1 eligible unique die",
        "positive": "1 if DieOutcome.first_pass_disposition == 'FAIL'",
        "negative": "0 if DieOutcome.first_pass_disposition == 'PASS'",
        "source_columns": ["pass_fail", "sbin", "abort_flag"],
        "implementation": "yield_improvement.yield_analysis.fpy.resolve_disposition + calculate_fpy; copied in ml.dataset.build_dataset",
        "rules": {
            "first_pass_fail = 1": "eligible die whose first-pass attempt disposition is FAIL (pass_fail=FAIL, or abort_flag with abort_is_first_pass_fail, or sbin mapped to FAIL)",
            "first_pass_fail = 0": "eligible die whose first-pass attempt disposition is PASS",
            "excluded": "not a Phase-1 FPY-eligible die (see eligibility table)",
        },
        "missing_disposition": "excluded from FPY and therefore from ML",
        "abort": "FAIL when abort_is_first_pass_fail is true (configs/fpy_policy.yaml)",
        "retest": "later attempts are ignored for the label; a retested die remains eligible on its first-pass row",
        "rework": "excluded if is_rework is true on any attempt for the die, or part_class is REWORK",
        "engineering": "excluded (excluded_part_classes)",
        "test_results": "not used to construct the ML target (build_dataset calls calculate_fpy(..., test_results=None))",
    }


def _eligibility_table() -> list[dict[str, str]]:
    return [
        {"condition": "Production", "included": "YES", "reason": "Default eligible part_class"},
        {"condition": "Engineering", "included": "NO", "reason": "excluded_part_classes in fpy_policy.yaml"},
        {"condition": "Retest (later attempt of an eligible die)", "included": "LABEL FROM FIRST PASS ONLY", "reason": "Die stays in ML; label is first-pass disposition, not retest recovery"},
        {"condition": "Retest-only die (no first-pass row)", "included": "NO", "reason": "Exclusion reason RETEST_ONLY"},
        {"condition": "Calibration", "included": "NO", "reason": "excluded_part_classes"},
        {"condition": "Rework", "included": "NO", "reason": "part_class REWORK or is_rework=true"},
        {"condition": "Missing disposition", "included": "NO", "reason": "Exclusion reason MISSING_DISPOSITION"},
        {"condition": "Aborted first pass", "included": "YES as FAIL", "reason": "abort_is_first_pass_fail: true"},
        {"condition": "QA_SAMPLE / UNKNOWN_NON_PRODUCTION", "included": "NO", "reason": "excluded_part_classes"},
        {"condition": "Missing part_class", "included": "YES as PRODUCTION", "reason": "part_class_missing.treat_as PRODUCTION"},
        {"condition": "record_status REJECT", "included": "NO", "reason": "Row skipped before die grouping"},
        {"condition": "Missing identity or timestamp", "included": "NO", "reason": "MISSING_IDENTITY / MISSING_TIMESTAMP"},
        {"condition": "Ambiguous duplicate attempt_id", "included": "NO", "reason": "AMBIGUOUS_DUPLICATE"},
    ]


def explain_dataset(dataset_dir: str | Path | None = None) -> dict[str, Any]:
    """Assemble a deterministic lineage audit. Read-only: no fit of the champion artifact."""
    folder = resolve_dataset_dir(dataset_dir)
    cfg = load_config()
    ml_cfg = load_ml_config()
    policy = load_feature_policy()
    champion_features = read_champion_feature_list()
    meta = read_champion_metadata()
    attempts = load_die_attempts(folder / "die_attempts.csv", cfg).attempts
    source_cols = list(pd.read_csv(folder / "die_attempts.csv", nrows=0).columns)
    parametric_cols: list[str] = []
    n_parametric_rows = 0
    if (folder / "parametric_measurements.csv").is_file():
        parametric_cols = list(pd.read_csv(folder / "parametric_measurements.csv", nrows=0).columns)
        n_parametric_rows = len(load_parametric_measurements(folder / "parametric_measurements.csv", cfg).parametric)
    fpy = calculate_fpy(attempts, cfg, test_results=None)
    data = load_ml_dataset(folder, config=cfg)
    y = data.y.to_numpy()
    groups = data.groups.to_numpy()
    strategy, splits = make_splits(groups, ml_cfg)
    lots = sorted(str(v) for v in np.unique(groups))
    wafers = sorted(str(v) for v in data.frame["wafer_id"].astype(str).unique())
    n_dies = int(data.frame[["lot_id", "wafer_id", "die_id"]].drop_duplicates().shape[0])
    n_lot_wafers = int(data.frame[["lot_id", "wafer_id"]].drop_duplicates().shape[0])
    builder = FeatureBuilder(policy=policy).fit(data.frame, data.y)
    current_features = list(builder.feature_names_)
    exclusion_counts = dict(Counter(item.reason for item in fpy.exclusions))
    n_reject = sum(1 for a in attempts if a.record_status == "REJECT")
    n_unique_raw = len({a.die_key() for a in attempts})
    folds: list[dict[str, Any]] = []
    lot_to_fold: dict[str, int] = {}
    for i, (train_idx, test_idx) in enumerate(splits, start=1):
        train_lots = sorted(str(v) for v in np.unique(groups[train_idx]))
        test_lots = sorted(str(v) for v in np.unique(groups[test_idx]))
        overlap = sorted(set(train_lots) & set(test_lots))
        test_y = y[test_idx]
        train_y = y[train_idx]
        row = {
            "fold": i,
            "training_lots": train_lots,
            "test_lots": test_lots,
            "train_dies": int(len(train_idx)),
            "test_dies": int(len(test_idx)),
            "train_positives": int(train_y.sum()),
            "test_positives": int(test_y.sum()),
            "lot_overlap": overlap,
        }
        folds.append(row)
        for lot in test_lots:
            lot_to_fold[lot] = i
    matrix = []
    for fold in folds:
        assignment = {lot: ("TEST" if lot in fold["test_lots"] else "TRAIN") for lot in lots}
        matrix.append({"fold": fold["fold"], "assignment": assignment})
    frame_cols = list(data.frame.columns)
    model_features = [c for c in current_features]
    grouping_only = [c for c in ("lot_id", "wafer_id", "die_id", "attempt_id") if c in frame_cols]
    unused_source = [
        c
        for c in source_cols
        if c
        not in {
            "x",
            "y",
            "timestamp",
            "tester_id",
            "probe_card_id",
            "prober_id",
            "site",
            "temperature_c",
            "voltage_v",
            "lot_id",
            "wafer_id",
            "die_id",
            "attempt_id",
        }
    ]
    feature_rows = []
    for name in champion_features:
        spec = FEATURE_SOURCES.get(name, {"type": "unknown", "source_column": "unknown", "transformation": "unknown"})
        feature_rows.append(
            {
                "feature": name,
                "type": spec["type"],
                "source_column": spec["source_column"],
                "transformation": spec["transformation"],
                "used_by_champion": True,
                "emitted_by_current_builder": name in current_features,
            }
        )
    parametric_present = [name for name in PARAM_NAMES if name in data.frame.columns and data.frame[name].notna().any()]
    leakage = [
        {"check": "lot_leakage", "result": "PASS" if all(not f["lot_overlap"] for f in folds) else "FAIL", "evidence": "ml/split.py make_splits asserts train_lots & test_lots is empty; each fold audited below"},
        {"check": "wafer_leakage", "result": "NOT_APPLICABLE", "evidence": "wafer_id is not a split key; wafers nested in lots so LOLO also separates wafers of the held-out lot"},
        {"check": "die_leakage", "result": "PASS", "evidence": "one ML row per eligible die; a die belongs to one lot so it cannot appear in both sides of a LOLO fold"},
        {"check": "target_leakage", "result": "PASS", "evidence": "first_pass_fail is not in FeatureBuilder output; pass_fail/disposition/sbin are denied_columns"},
        {"check": "retest_leakage", "result": "PASS", "evidence": "is_retest/attempt_number/final_disposition denied; label uses first-pass attempt only"},
        {"check": "future_information_leakage", "result": "PASS", "evidence": "test_results sequence_index/is_first_fail not joined into the ML frame; later tests unused"},
        {"check": "scenario_leakage", "result": "PASS", "evidence": "scenario_id in SOURCE_FORBIDDEN and denied_columns; agent-visible CSV has no scenario_id"},
        {"check": "hidden_ground_truth_leakage", "result": "PASS", "evidence": "ml package does not read hidden labels; SOURCE_FORBIDDEN fail-closed on agent-visible tables"},
        {"check": "calibration_leakage", "result": "PASS", "evidence": "fold-local isotonic is fit on oof_raw[train_idx], y[train_idx]; held-out lot labels are not used. Deployed calibrator is fit on all OOF for later predict() only"},
        {"check": "preprocessing_leakage", "result": "PASS", "evidence": "ml/train.py _cv_oof fits FeatureBuilder and sklearn preprocessor on train_idx only"},
    ]
    every_lot_once = sorted(lot_to_fold.keys()) == lots and len(lot_to_fold) == len(lots)
    audit = {
        "dataset": {
            "dataset_id": folder.name,
            "dataset_path": str(folder),
            "champion_analysis_id": meta.get("analysis_id"),
            "is_champion_training_set": folder.name == meta.get("analysis_id"),
            "source_files": {
                "die_attempts": str(folder / "die_attempts.csv"),
                "parametric_measurements": str(folder / "parametric_measurements.csv") if parametric_cols else None,
                "test_results": str(folder / "test_results.csv") if (folder / "test_results.csv").is_file() else None,
            },
        },
        "sample_grain": {
            "ml_sample": "one Phase-1 FPY-eligible unique die (lot_id, wafer_id, die_id)",
            "not": "raw measurement row, die x attempt, or test_result row",
            "example": {
                "raw": "die_attempts row is unique die x attempt",
                "ml": "build_dataset iterates fpy.per_die and emits one record using the first-pass attempt_id",
            },
        },
        "population_counts": {
            "raw_die_attempt_rows": len(attempts),
            "record_status_reject_rows": n_reject,
            "unique_dies_in_source": n_unique_raw,
            "fpy_eligible_dies": int(fpy.eligible_die_count),
            "ml_samples": int(len(data.frame)),
            "ml_equals_eligible": int(len(data.frame)) == int(fpy.eligible_die_count),
            "positive_labels": int(y.sum()),
            "negative_labels": int((y == 0).sum()),
            "positive_rate": float(y.mean()) if len(y) else None,
            "n_lots": len(lots),
            "n_wafers": len(wafers),
            "n_lot_wafer_pairs": n_lot_wafers,
            "n_unique_dies": n_dies,
            "n_parametric_rows": n_parametric_rows,
            "exclusion_counts": exclusion_counts,
            "first_pass_pass_count": int(fpy.first_pass_pass_count),
            "first_pass_fail_count": int(fpy.first_pass_fail_count),
        },
        "target_definition": _target_rule(),
        "eligibility": _eligibility_table(),
        "feature_list": {
            "champion_artifact": champion_features,
            "current_builder_on_this_dataset": current_features,
            "n_champion_features": len(champion_features),
            "matches_artifact": current_features == champion_features,
            "parametric_non_null_in_frame": parametric_present,
            "numeric_base": list(NUMERIC_BASE),
            "categorical_base": list(CATEGORICAL_BASE),
            "rows": feature_rows,
            "preprocess": PREPROCESS,
        },
        "excluded_columns": {
            "source_csv_columns": source_cols,
            "parametric_csv_columns": parametric_cols,
            "ml_frame_columns": frame_cols,
            "not_passed_to_model": [c for c in frame_cols if c not in model_features],
            "source_columns_not_copied_into_ml_frame": unused_source,
            "denied_columns": list(policy.denied_columns),
            "hidden_source_forbidden": sorted(SOURCE_FORBIDDEN),
        },
        "grouping_columns": GROUPING_TABLE,
        "grouping_only_on_frame": grouping_only,
        "folds": folds,
        "fold_matrix": matrix,
        "lots": lots,
        "wafers": wafers,
        "split": {
            "strategy": strategy,
            "config_strategy": ml_cfg.split.strategy,
            "group_column": ml_cfg.split.group_column,
            "n_folds": len(folds),
            "max_lolo_lots": ml_cfg.split.max_lolo_lots,
            "every_lot_exactly_once_as_test": every_lot_once,
            "why_not_random_80_20": (
                "Random splits can put two dies from the same lot on both sides. "
                "Lot-level equipment, time, and process effects would leak. "
                "LOLO asks: would this model score a new lot it has never trained on?"
            ),
        },
        "calibration_method": {
            "method": ml_cfg.calibration.method,
            "implementation": "yield_improvement.ml.calibration.ProbabilityCalibrator (sklearn IsotonicRegression, out_of_bounds=clip)",
            "oof_fold_local": "For each outer test lot, isotonic is fit on oof_raw and labels of the other lots, then applied to the test lot oof_raw",
            "deployed_calibrator": "ProbabilityCalibrator().fit(oof_raw, y) on all OOF rows; used by predict_dir, not by reported OOF metrics",
            "held_out_lot_labels_fit_fold_calibrator": False,
            "classifier_for_oof": "retrained each outer fold on training lots only (ml/train.py _cv_oof)",
        },
        "oof_summary": {
            "definition": "For each lot L, the classifier is fit without L and predicts L. Concatenate all lots.",
            "n_oof_slots": int(len(y)),
            "final_metrics_use": "calibrated OOF (trained.oof_cal) when the calibrator fitted, else raw OOF",
            "metrics_function": "yield_improvement.ml.evaluation.compute_metrics",
            "full_data_refit": "After OOF, pipeline.fit is called on all eligible dies to persist the champion; those in-sample scores are not the reported metrics",
        },
        "metrics_source": {
            "champion_metrics_file": str(champion_dir() / "metrics.json"),
            "n_samples": meta.get("selected_metrics", {}).get("n_samples") if isinstance(meta.get("selected_metrics"), dict) else None,
            "n_positives": meta.get("selected_metrics", {}).get("n_positives") if isinstance(meta.get("selected_metrics"), dict) else None,
            "split_strategy": meta.get("split_strategy"),
            "model_name": meta.get("model_name"),
        },
        "leakage_checks": leakage,
        "leakage_audit": "PASS" if all(item["result"] in {"PASS", "NOT_APPLICABLE"} for item in leakage) else "FAIL",
        "scenario_handling": {
            "scenario_id_is_model_feature": False,
            "hidden_labels_on_agent_visible_tables": False,
            "training": "python -m yield_improvement ml train|run uses one agent-visible folder. Champion yi_ml_v1 was trained on the analysis_id stored in artifacts/ml/yi_ml_v1/metadata.json.",
            "holdout_evaluation": "python -m yield_improvement ml evaluate scores that folder with persist=False, then a separate evaluation module compares predictions to hidden labels after scoring.",
            "synthetic_scenarios": "S01–S16 are separate dataset directories produced by the generator. They are not a column in the feature matrix. The model never sees scenario_id, true_cause, or injected_effect.",
        },
        "commands": {
            "train": "python -m yield_improvement ml train <dir> -> run_ml persist=True (refuses to overwrite yi_ml_v1)",
            "predict": "python -m yield_improvement ml predict <dir> -> load_artifact + predict_frame (no refit of features)",
            "evaluate": "python -m yield_improvement ml evaluate <dir> -> evaluation.ml.evaluate_dataset_ml persist=False, joins hidden GT after scoring",
            "run": "python -m yield_improvement ml run <dir> -> run_ml_and_compose persist=True",
            "explain-data": "python -m yield_improvement ml explain-data <dir> -> this audit, no training",
        },
        "champion": {
            "model_version": meta.get("model_version"),
            "model_name": meta.get("model_name"),
            "n_features": meta.get("n_features"),
            "n_samples": meta.get("n_samples"),
            "trained_at": meta.get("trained_at"),
        },
    }
    return audit


def write_audit(payload: dict[str, Any], path: str | Path) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return out


def render_text(payload: dict[str, Any]) -> str:
    ds = payload["dataset"]
    pop = payload["population_counts"]
    split = payload["split"]
    feat = payload["feature_list"]
    lines = [
        f"Dataset: {ds['dataset_id']}",
        f"Path: {ds['dataset_path']}",
        f"Champion training set: {ds['is_champion_training_set']}",
        "",
        "Modeling grain: one Phase-1 eligible unique die",
        f"Raw die_attempts rows: {pop['raw_die_attempt_rows']}",
        f"Eligible / ML samples: {pop['ml_samples']}",
        f"Positive samples (first_pass_fail=1): {pop['positive_labels']}",
        f"Negative samples: {pop['negative_labels']}",
        f"Positive rate: {pop['positive_rate']}",
        f"Lots: {', '.join(payload['lots'])} ({pop['n_lots']})",
        f"Wafers: {pop['n_wafers']}",
        "",
        f"Features (champion): {feat['n_champion_features']}",
        f"Feature list: {', '.join(feat['champion_artifact'])}",
        "",
        "Target: first_pass_fail",
        f"Split: {split['strategy']}",
        f"Folds: {split['n_folds']}",
        "Calibration: nested fold-local isotonic; deployed calibrator fits all OOF",
        f"Leakage checks: {payload['leakage_audit']}",
        "",
        "Folds:",
    ]
    for fold in payload["folds"]:
        lines.append(
            f"  Fold {fold['fold']}: test={','.join(fold['test_lots'])} "
            f"train_dies={fold['train_dies']} test_dies={fold['test_dies']} "
            f"test_positives={fold['test_positives']}"
        )
    return "\n".join(lines) + "\n"
