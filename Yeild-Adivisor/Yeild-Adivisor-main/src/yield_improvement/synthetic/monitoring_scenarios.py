"""Controlled monitoring datasets. Does not modify Phase 2 S01–S16 or their ground truth."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd

from yield_improvement.utils.paths import phase2_agent_visible_dir, phase2_monitoring_dir, repo_root

SCENARIOS = (
    "M01_NO_DRIFT",
    "M02_FEATURE_DRIFT",
    "M03_PREDICTION_DRIFT",
    "M04_TARGET_DRIFT",
    "M05_CALIBRATION_DRIFT",
    "M06_PERFORMANCE_DEGRADATION",
    "M07_MULTIPLE_DRIFT",
    "M08_SCHEMA_DEGRADATION",
    "M09_SMALL_SAMPLE",
    "M10_NO_LABELS",
)

EXPECTED = {
    "M01_NO_DRIFT": {
        "overall": ["HEALTHY", "MONITOR"],
        "feature_drift": ["HEALTHY", "MONITOR"],
        "prediction_drift": ["HEALTHY", "MONITOR"],
        "alarm": False,
    },
    "M02_FEATURE_DRIFT": {
        "overall": ["MONITOR", "REVIEW", "NEEDS_RETRAINING"],
        "feature_drift": ["MONITOR", "REVIEW"],
        "performance_not_required_degraded": True,
        "alarm": True,
        "dimension": "feature_drift",
    },
    "M03_PREDICTION_DRIFT": {
        "overall": ["MONITOR", "REVIEW", "NEEDS_RETRAINING"],
        "prediction_drift": ["MONITOR", "REVIEW"],
        "alarm": True,
        "dimension": "prediction_drift",
    },
    "M04_TARGET_DRIFT": {
        "overall": ["MONITOR", "REVIEW", "DEGRADED", "NEEDS_RETRAINING"],
        "target_drift": ["MONITOR", "REVIEW"],
        "alarm": True,
        "dimension": "target_drift",
    },
    "M05_CALIBRATION_DRIFT": {
        "overall": ["REVIEW", "MONITOR", "DEGRADED", "NEEDS_RETRAINING"],
        "calibration": ["REVIEW", "MONITOR"],
        "alarm": True,
        "dimension": "calibration",
        "not_no_predictive_value": True,
    },
    "M06_PERFORMANCE_DEGRADATION": {
        "overall": ["DEGRADED", "NEEDS_RETRAINING", "REVIEW"],
        "performance": ["DEGRADED", "REVIEW", "MONITOR"],
        "alarm": True,
        "dimension": "performance",
    },
    "M07_MULTIPLE_DRIFT": {
        "overall": ["NEEDS_RETRAINING", "REVIEW", "DEGRADED", "MONITOR"],
        "alarm": True,
        "dimension": "multi",
    },
    "M08_SCHEMA_DEGRADATION": {
        "overall": ["REVIEW"],
        "data_quality": ["REVIEW"],
        "alarm": True,
        "dimension": "data_quality",
    },
    "M09_SMALL_SAMPLE": {
        "overall": ["INSUFFICIENT_DATA"],
        "alarm": False,
        "dimension": "sample",
    },
    "M10_NO_LABELS": {
        "overall": ["HEALTHY", "MONITOR", "REVIEW", "INSUFFICIENT_DATA"],
        "target_drift": ["UNAVAILABLE"],
        "calibration": ["UNAVAILABLE"],
        "performance": ["UNAVAILABLE"],
        "alarm": False,
        "dimension": "unlabeled",
    },
}


def _s02_dir() -> Path:
    summary = json.loads(
        (repo_root() / "evaluation" / "ground_truth" / "synthetic" / "RUN_SUMMARY.json").read_text(encoding="utf-8")
    )
    for item in summary["scenarios"]:
        if item["scenario_id"] == "S02":
            return phase2_agent_visible_dir() / item["dataset_id"]
    raise FileNotFoundError("S02 agent-visible dataset missing")


def _copy_sidecar(src: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    for name in ("lots.csv", "wafers.csv", "parts.csv", "equipment.csv", "test_results.csv", "parametric_measurements.csv", "manifest.json"):
        f = src / name
        if f.is_file():
            shutil.copy2(f, dest / name)


def _write_gt(scenario: str, dataset_id: str, notes: str) -> None:
    root = repo_root() / "evaluation" / "ground_truth" / "monitoring"
    root.mkdir(parents=True, exist_ok=True)
    payload = {
        "scenario_id": scenario,
        "dataset_id": dataset_id,
        "expected": EXPECTED[scenario],
        "notes": notes,
        "hidden": True,
    }
    (root / f"{dataset_id}.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def generate_monitoring_scenarios(*, seed: int = 7, source: Path | None = None) -> list[dict]:
    """Create M01–M10 under data/synthetic/monitoring/. Leaves Phase 2 data untouched."""
    rng = np.random.RandomState(seed)
    src = source or _s02_dir()
    base = pd.read_csv(src / "die_attempts.csv")
    agent_root = phase2_monitoring_dir()
    agent_root.mkdir(parents=True, exist_ok=True)
    summaries = []
    order = {name: f"ds_mon_{i:02d}" for i, name in enumerate(SCENARIOS, start=1)}

    def emit(scenario: str, frame: pd.DataFrame, notes: str) -> None:
        dataset_id = order[scenario]
        dest = agent_root / dataset_id
        if dest.exists():
            shutil.rmtree(dest)
        dest.mkdir(parents=True)
        frame.to_csv(dest / "die_attempts.csv", index=False)
        _copy_sidecar(src, dest)
        manifest = {"dataset_id": dataset_id, "kind": "monitoring_current", "source_reference_like": src.name}
        (dest / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        _write_gt(scenario, dataset_id, notes)
        summaries.append({"scenario_id": scenario, "dataset_id": dataset_id, "n": int(len(frame)), "agent_dir": str(dest)})

    emit("M01_NO_DRIFT", base.copy(), "Unmodified copy of the spatial-edge reference-like population.")

    m02 = base.copy()
    m02["temperature_c"] = pd.to_numeric(m02["temperature_c"], errors="coerce") + 45.0
    m02["voltage_v"] = pd.to_numeric(m02["voltage_v"], errors="coerce") + 0.25
    emit("M02_FEATURE_DRIFT", m02, "Shifted temperature and voltage. Labels unchanged.")

    m03 = base.copy()
    x = pd.to_numeric(m03["x"], errors="coerce")
    y = pd.to_numeric(m03["y"], errors="coerce")
    m03["x"] = x * 1.8
    m03["y"] = y * 1.8
    emit("M03_PREDICTION_DRIFT", m03, "Expanded wafer coordinates toward the edge so predicted risk shifts. Labels unchanged.")

    m04 = base.copy()
    pass_idx = m04.index[m04["pass_fail"].astype(str).str.upper() == "PASS"].to_numpy()
    flip = rng.choice(pass_idx, size=max(1, int(0.22 * len(pass_idx))), replace=False)
    m04.loc[flip, "pass_fail"] = "FAIL"
    m04.loc[flip, "disposition"] = "FAIL"
    m04.loc[flip, "sbin"] = 8
    m04.loc[flip, "hbin"] = 5
    m04.loc[flip, "failure_code"] = "IDDQ"
    emit("M04_TARGET_DRIFT", m04, "Uniform extra fails. Features unchanged so prediction distribution should stay similar.")

    m05 = base.copy()
    # Keep original fails (spatial concentration) and add uniform extra fails so ranking remains
    # informative but observed rates exceed predicted probabilities.
    pass_idx = m05.index[m05["pass_fail"].astype(str).str.upper() == "PASS"].to_numpy()
    flip = rng.choice(pass_idx, size=max(1, int(0.40 * len(pass_idx))), replace=False)
    m05.loc[flip, "pass_fail"] = "FAIL"
    m05.loc[flip, "disposition"] = "FAIL"
    m05.loc[flip, "sbin"] = 8
    m05.loc[flip, "hbin"] = 5
    m05.loc[flip, "failure_code"] = "IDDQ"
    emit("M05_CALIBRATION_DRIFT", m05, "Uniform extra fails on top of the original spatial pattern. Ranking should remain useful.")

    m06 = base.copy()
    shuffled = rng.permutation(m06["pass_fail"].to_numpy())
    m06["pass_fail"] = shuffled
    m06["disposition"] = shuffled
    emit("M06_PERFORMANCE_DEGRADATION", m06, "Shuffled labels destroy ranking. Features unchanged.")

    m07 = base.copy()
    m07["temperature_c"] = pd.to_numeric(m07["temperature_c"], errors="coerce") + 50.0
    m07["x"] = pd.to_numeric(m07["x"], errors="coerce") * 1.7
    m07["y"] = pd.to_numeric(m07["y"], errors="coerce") * 1.7
    pass_idx = m07.index[m07["pass_fail"].astype(str).str.upper() == "PASS"].to_numpy()
    flip = rng.choice(pass_idx, size=max(1, int(0.25 * len(pass_idx))), replace=False)
    m07.loc[flip, "pass_fail"] = "FAIL"
    m07.loc[flip, "disposition"] = "FAIL"
    m07.loc[flip, "sbin"] = 8
    emit("M07_MULTIPLE_DRIFT", m07, "Feature, prediction, and target shifts combined.")

    m08 = base.copy()
    m08["extra_sensor_reading"] = rng.normal(0, 1, size=len(m08))
    m08 = m08.drop(columns=["temperature_c"])
    m08.loc[m08.index[:20], "tester_id"] = ""
    m08 = pd.concat([m08, m08.iloc[[0]]], ignore_index=True)
    emit("M08_SCHEMA_DEGRADATION", m08, "Dropped temperature_c, added unexpected column, blank testers, duplicate row.")

    m09 = base.head(24).copy()
    emit("M09_SMALL_SAMPLE", m09, "Fewer rows than min_current_samples.")

    m10 = base.copy()
    for col in ("pass_fail", "disposition", "sbin", "hbin", "failure_code"):
        if col in m10.columns:
            m10 = m10.drop(columns=[col])
    emit("M10_NO_LABELS", m10, "Outcome columns removed. Feature and prediction monitoring only.")

    index = {"scenarios": summaries, "seed": seed, "source": src.name}
    gt_root = repo_root() / "evaluation" / "ground_truth" / "monitoring"
    (gt_root / "RUN_SUMMARY.json").write_text(json.dumps(index, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (agent_root / "INDEX.json").write_text(
        json.dumps({"n_datasets": len(summaries), "kind": "monitoring_current"}, indent=2) + "\n",
        encoding="utf-8",
    )
    return summaries
