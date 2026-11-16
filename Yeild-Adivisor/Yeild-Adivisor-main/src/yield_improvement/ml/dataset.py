"""Build ML rows from Phase 1 eligible first-pass dies. No ground-truth files."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from yield_improvement.config.loader import AppConfig, load_config
from yield_improvement.ingestion.loader import (
    load_die_attempts,
    load_parametric_measurements,
    load_test_results,
)
from yield_improvement.ml.config import FeaturePolicy, LeakageError, load_feature_policy
from yield_improvement.models.canonical import DieAttempt, ParametricMeasurement
from yield_improvement.yield_analysis.fpy import calculate_fpy

PARAM_NAMES = ("IR_DROP_MV", "THERMAL_C", "SETUP_SLACK_PS", "HOLD_SLACK_PS", "TEST_TIME_MS")


@dataclass
class MLDataset:
    frame: pd.DataFrame
    y: pd.Series
    groups: pd.Series
    analysis_id: str


SOURCE_FORBIDDEN = {
    "true_root_cause",
    "true_cause",
    "true_causes",
    "planted_cause",
    "planted_causes",
    "latent_quality",
    "scenario_id",
    "expected_hypothesis",
    "expected_signal",
    "generator_seed",
    "injected_effect",
    "injected_parameters",
    "difficulty",
    "ground_truth",
    "recoverable_fraction",
}


def assert_no_forbidden_columns(columns: list[str], policy: FeaturePolicy) -> None:
    denied = {c.lower() for c in policy.denied_columns}
    hits = [c for c in columns if c.lower() in denied]
    if hits:
        raise LeakageError(f"Forbidden ML columns: {hits}")


def assert_source_has_no_hidden_labels(columns: list[str]) -> None:
    hits = [c for c in columns if c.lower() in SOURCE_FORBIDDEN]
    if hits:
        raise LeakageError(f"Hidden/evaluation columns on agent-visible table: {hits}")


def _parametric_map(rows: list[ParametricMeasurement]) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    for row in rows:
        if row.parameter_name not in PARAM_NAMES:
            continue
        out.setdefault(row.attempt_id, {})[row.parameter_name] = float(row.measurement)
    return out


def build_dataset(
    attempts: list[DieAttempt],
    config: AppConfig,
    *,
    parametric: list[ParametricMeasurement] | None = None,
    analysis_id: str = "unknown",
    policy: FeaturePolicy | None = None,
) -> MLDataset:
    """One row per Phase 1 eligible die. Target = first-pass fail from frozen FPY rules."""
    policy = policy or load_feature_policy()
    fpy = calculate_fpy(attempts, config, test_results=None)
    by_id = {a.attempt_id: a for a in attempts}
    params = _parametric_map(list(parametric or []))
    records: list[dict[str, object]] = []
    y: list[int] = []
    groups: list[str] = []
    for outcome in fpy.per_die:
        attempt = by_id.get(outcome.attempt_id)
        if attempt is None:
            continue
        rec: dict[str, object] = {
            "lot_id": outcome.lot_id,
            "wafer_id": outcome.wafer_id,
            "die_id": outcome.die_id,
            "attempt_id": outcome.attempt_id,
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
        rec.update(params.get(attempt.attempt_id, {}))
        records.append(rec)
        y.append(1 if outcome.first_pass_disposition == "FAIL" else 0)
        groups.append(outcome.lot_id)
    frame = pd.DataFrame.from_records(records)
    assert_no_forbidden_columns(list(frame.columns), policy)
    return MLDataset(
        frame=frame,
        y=pd.Series(y, name="first_pass_fail"),
        groups=pd.Series(groups, name="lot_id"),
        analysis_id=analysis_id,
    )


def load_ml_dataset(dataset_dir: str | Path, config: AppConfig | None = None) -> MLDataset:
    folder = Path(dataset_dir)
    cfg = config or load_config()
    policy = load_feature_policy()
    loaded = load_die_attempts(folder / "die_attempts.csv", cfg)
    source_cols = list(pd.read_csv(folder / "die_attempts.csv", nrows=0).columns)
    assert_source_has_no_hidden_labels(source_cols)
    parametric: list[ParametricMeasurement] = []
    pm = folder / "parametric_measurements.csv"
    if pm.is_file():
        parametric = load_parametric_measurements(pm, cfg).parametric
        pcols = list(pd.read_csv(pm, nrows=0).columns)
        assert_source_has_no_hidden_labels(pcols)
    tests_path = folder / "test_results.csv"
    if tests_path.is_file():
        # Load only to ensure we do not train on test outcomes. Sequence is not used.
        _ = load_test_results(tests_path, cfg)
    return build_dataset(
        loaded.attempts,
        cfg,
        parametric=parametric,
        analysis_id=folder.name,
        policy=policy,
    )
