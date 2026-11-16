"""Leakage: hidden labels, retest, post-failure fields, ground-truth isolation."""

from __future__ import annotations

import json

import pandas as pd
import pytest

from yield_improvement.ml.config import LeakageError
from yield_improvement.ml.dataset import assert_source_has_no_hidden_labels, load_ml_dataset
from yield_improvement.utils.paths import phase2_agent_visible_dir, repo_root


def test_hidden_label_on_source_rejected():
    with pytest.raises(LeakageError):
        assert_source_has_no_hidden_labels(["lot_id", "scenario_id", "x"])


def test_injected_effect_rejected():
    with pytest.raises(LeakageError):
        assert_source_has_no_hidden_labels(["injected_effect"])


def test_ml_package_does_not_read_ground_truth():
    src = repo_root() / "src" / "yield_improvement" / "ml"
    hits = []
    for path in src.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for token in ("RUN_SUMMARY", "yield_improvement.evaluation", "evaluation/ground_truth"):
            if token in text:
                hits.append(f"{path.name}: {token}")
    assert hits == []


def test_agent_visible_load_strips_outcome_fields(config):
    payload = json.loads(
        (repo_root() / "evaluation" / "ground_truth" / "synthetic" / "RUN_SUMMARY.json").read_text(encoding="utf-8")
    )
    ds = payload["scenarios"][0]["dataset_id"]
    data = load_ml_dataset(phase2_agent_visible_dir() / ds, config=config)
    for col in ("pass_fail", "sbin", "failure_code", "disposition", "is_retest"):
        assert col not in data.frame.columns
    assert data.y.isin([0, 1]).all()


def test_retest_and_post_failure_fields_are_not_features(config):
    payload = json.loads(
        (repo_root() / "evaluation" / "ground_truth" / "synthetic" / "RUN_SUMMARY.json").read_text(encoding="utf-8")
    )
    ds = payload["scenarios"][0]["dataset_id"]
    data = load_ml_dataset(phase2_agent_visible_dir() / ds, config=config)
    forbidden = {
        "pass_fail",
        "sbin",
        "hbin",
        "failure_code",
        "disposition",
        "is_retest",
        "attempt_number",
        "true_cause",
        "scenario_id",
        "injected_effect",
        "ground_truth",
        "final_disposition",
    }
    assert forbidden.isdisjoint(set(data.frame.columns))


def test_source_csv_with_ground_truth_column_fails_closed(tmp_path):
    csv = tmp_path / "die_attempts.csv"
    csv.write_text("lot_id,true_cause\nL1,EDGE\n", encoding="utf-8")
    with pytest.raises(LeakageError):
        assert_source_has_no_hidden_labels(list(pd.read_csv(csv).columns))


def test_persisted_artifact_has_no_hidden_labels():
    folder = repo_root() / "artifacts" / "ml" / "yi_ml_v1"
    assert (folder / "model.pkl").is_file()
    meta = json.loads((folder / "metadata.json").read_text(encoding="utf-8"))
    blob = json.dumps(meta).lower()
    for token in ("scenario_id", "true_cause", "injected_effect", "ground_truth", "generator_seed"):
        assert token not in blob
    assert "disclaimer" in meta
