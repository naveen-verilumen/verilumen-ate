"""Join monitoring reports to hidden monitoring ground truth AFTER health is produced."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from yield_improvement.config.loader import AppConfig, load_config
from yield_improvement.monitoring.monitor import build_reference_snapshot, run_monitor
from yield_improvement.monitoring.report import write_health_outputs
from yield_improvement.synthetic.monitoring_scenarios import EXPECTED, generate_monitoring_scenarios
from yield_improvement.utils.paths import phase2_agent_visible_dir, phase2_monitoring_dir, repo_root


def _gt_root() -> Path:
    return repo_root() / "evaluation" / "ground_truth" / "monitoring"


def evaluate_one(dataset_id: str, scenario_id: str, current_dir: Path, reference_dir: Path, config: AppConfig) -> dict[str, Any]:
    report = run_monitor(current_dir, reference_dir, config=config, overwrite_reference=False)
    write_health_outputs(report)
    expected = EXPECTED[scenario_id]
    overall_ok = report.overall_status in expected["overall"]
    dim = expected.get("dimension")
    dim_ok = True
    if dim == "feature_drift":
        dim_ok = report.feature_drift.status in expected["feature_drift"]
    elif dim == "prediction_drift":
        dim_ok = report.prediction_drift.status in expected["prediction_drift"]
    elif dim == "target_drift":
        dim_ok = report.target_drift.status in expected["target_drift"]
    elif dim == "calibration":
        dim_ok = report.calibration.status in expected["calibration"]
    elif dim == "performance":
        dim_ok = report.performance.status in expected["performance"]
    elif dim == "data_quality":
        dim_ok = report.data_quality.status in expected["data_quality"]
    elif dim == "sample":
        dim_ok = report.overall_status == "INSUFFICIENT_DATA"
    elif dim == "unlabeled":
        dim_ok = (
            report.target_drift.status == "UNAVAILABLE"
            and report.calibration.status == "UNAVAILABLE"
            and report.performance.status == "UNAVAILABLE"
        )
    if expected.get("performance_not_required_degraded"):
        dim_ok = dim_ok and report.performance.status != "DEGRADED"
    binary_expected_alarm = bool(expected.get("alarm"))
    binary_predicted_alarm = report.overall_status not in {"HEALTHY", "INSUFFICIENT_DATA"}
    if scenario_id == "M09_SMALL_SAMPLE":
        binary_predicted_alarm = False
        binary_expected_alarm = False
    if overall_ok and dim_ok:
        kind = "TP" if binary_expected_alarm else "TN"
    elif binary_expected_alarm and not (overall_ok and dim_ok):
        kind = "FN"
    elif not binary_expected_alarm and not overall_ok:
        kind = "FP"
    else:
        kind = "FN" if binary_expected_alarm else "FP"
    blob = json.dumps(report.to_public_dict()).lower()
    return {
        "scenario": scenario_id,
        "dataset_id": dataset_id,
        "expected_state": expected["overall"],
        "predicted_state": report.overall_status,
        "status": "PASS" if overall_ok and dim_ok else "MISS",
        "binary": kind,
        "feature_drift": report.feature_drift.status,
        "prediction_drift": report.prediction_drift.status,
        "target_drift": report.target_drift.status,
        "calibration": report.calibration.status,
        "performance": report.performance.status,
        "data_quality": report.data_quality.status,
        "n_dies": report.n_dies,
        "label_mode": report.label_mode,
        "production_authorized": report.production_authorized,
        "retrained": report.retrained,
        "no_limit_verbs": "increase limit" not in blob,
        "triggers": report.triggers,
        "recommendations": list(report.recommendations),
    }


def evaluate_all_monitoring(config: AppConfig | None = None, *, regenerate: bool = True) -> dict[str, Any]:
    cfg = config or load_config()
    if regenerate:
        generate_monitoring_scenarios()
    summary = json.loads((_gt_root() / "RUN_SUMMARY.json").read_text(encoding="utf-8"))
    agent_root = phase2_monitoring_dir()
    ref = json.loads((repo_root() / "evaluation" / "ground_truth" / "synthetic" / "RUN_SUMMARY.json").read_text(encoding="utf-8"))
    ref_id = next(item["dataset_id"] for item in ref["scenarios"] if item["scenario_id"] == "S02")
    reference_dir = phase2_agent_visible_dir() / ref_id
    build_reference_snapshot(reference_dir, config=cfg, overwrite=False)
    rows = [
        evaluate_one(item["dataset_id"], item["scenario_id"], agent_root / item["dataset_id"], reference_dir, cfg)
        for item in summary["scenarios"]
    ]
    counts = {k: sum(1 for r in rows if r["binary"] == k) for k in ("TP", "FP", "TN", "FN")}
    return {
        "n_scenarios": len(rows),
        "counts": counts,
        "all_unauthorized": all(r["production_authorized"] is False for r in rows),
        "none_retrained": all(r["retrained"] is False for r in rows),
        "rows": rows,
    }


def write_monitoring_evaluation(path: Path | None = None, config: AppConfig | None = None) -> Path:
    result = evaluate_all_monitoring(config=config)
    out = path or (repo_root() / "evaluation" / "results" / "monitoring_phase8.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return out
