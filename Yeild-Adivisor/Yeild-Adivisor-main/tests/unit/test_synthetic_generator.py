"""Synthetic generator: schema, reproducibility, leakage, scenario sanity."""

from __future__ import annotations

import json

import pytest

from yield_improvement.pipeline import run_pipeline
from yield_improvement.synthetic.config import load_synthetic_config
from yield_improvement.synthetic.generator import generate_dataset, persist_dataset, write_csv
from yield_improvement.synthetic.ground_truth import AGENT_MANIFEST_FORBIDDEN
from yield_improvement.synthetic.scenarios import CORE_SCENARIOS
from yield_improvement.synthetic.validation import assert_no_ground_truth_leakage


def test_synthetic_config_profiles_and_seed():
    cfg = load_synthetic_config()
    assert cfg.active_profile == "small"
    assert "small" in cfg.profiles and "medium" in cfg.profiles and "large" in cfg.profiles
    assert cfg.seed == 20260322
    small = cfg.profile("small")
    assert small.n_lots == 8
    assert small.n_dies_per_wafer == 49


@pytest.mark.parametrize("scenario_id", CORE_SCENARIOS)
def test_each_core_scenario_validates(scenario_id, config, tmp_path):
    bundle = generate_dataset(scenario_id, app_config=config, write=False)
    assert bundle.validation_report["status"] == "PASSED"
    assert bundle.validation_report["sanity_status"] == "PASSED"
    assert bundle.agent_manifest["canonical_validation"] == "passed"
    assert "scenario_id" not in bundle.agent_manifest
    for key in AGENT_MANIFEST_FORBIDDEN:
        assert key not in bundle.agent_manifest
        for table in bundle.tables.values():
            if table:
                assert key not in table[0]
    persist_dataset(bundle, agent_root=tmp_path / "agent", gt_root=tmp_path / "gt", app_config=config)
    assert (tmp_path / "gt" / bundle.dataset_id / "ground_truth.json").is_file()
    assert not (tmp_path / "agent" / bundle.dataset_id / "ground_truth.json").exists()
    gt = json.loads((tmp_path / "gt" / bundle.dataset_id / "ground_truth.json").read_text(encoding="utf-8"))
    assert gt["scenario_id"] == scenario_id
    assert gt["true_causes"]


def test_reproducibility_s02(config, tmp_path):
    a = generate_dataset("S02", seed=42, app_config=config, write=False)
    b = generate_dataset("S02", seed=42, app_config=config, write=False)
    c = generate_dataset("S02", seed=99, app_config=config, write=False)
    assert a.tables["die_attempts"] == b.tables["die_attempts"]
    assert a.tables["test_results"] == b.tables["test_results"]
    assert a.dataset_id == b.dataset_id
    assert a.tables["die_attempts"] != c.tables["die_attempts"]
    persist_dataset(a, agent_root=tmp_path / "a", gt_root=tmp_path / "gta", app_config=config)
    persist_dataset(b, agent_root=tmp_path / "b", gt_root=tmp_path / "gtb", app_config=config)
    da_a = (tmp_path / "a" / a.dataset_id / "die_attempts.csv").read_text(encoding="utf-8")
    da_b = (tmp_path / "b" / b.dataset_id / "die_attempts.csv").read_text(encoding="utf-8")
    assert da_a == da_b


def test_ground_truth_leakage_scan(config, tmp_path):
    bundle = generate_dataset("S02", app_config=config, write=False)
    persist_dataset(bundle, agent_root=tmp_path / "agent", gt_root=tmp_path / "gt", app_config=config)
    agent_dir = tmp_path / "agent" / bundle.dataset_id
    assert_no_ground_truth_leakage(agent_dir)
    leaked_rows = [{**row, "scenario_id": "S02"} for row in bundle.tables["die_attempts"]]
    write_csv(agent_dir / "die_attempts.csv", leaked_rows)
    with pytest.raises(Exception, match="leakage|scenario_id"):
        assert_no_ground_truth_leakage(agent_dir)


def test_generated_s02_loads_in_phase1_pipeline(config, tmp_path):
    bundle = generate_dataset("S02", app_config=config, write=False)
    persist_dataset(bundle, agent_root=tmp_path / "agent", gt_root=tmp_path / "gt", app_config=config)
    folder = tmp_path / "agent" / bundle.dataset_id
    result = run_pipeline(folder / "die_attempts.csv", folder / "test_results.csv", config=config)
    assert result.status == "OK"
    assert result.fpy is not None
    assert result.eligible_die_count == bundle.agent_manifest["die_count"]


def test_s09_does_not_modify_limits_or_leak_tight_flag(config):
    bundle = generate_dataset("S09", app_config=config, write=False)
    limit = bundle.ground_truth.injected_parameters["production_upper_limit"]
    for row in bundle.tables["parametric_measurements"]:
        if row["parameter_name"] == "IDDQ":
            assert row["upper_limit"] == limit
        assert "tight_limit" not in row
    for row in bundle.tables["die_attempts"]:
        assert "tight_limit" not in row


def test_s16_has_no_planted_cause(config):
    bundle = generate_dataset("S16", app_config=config, write=False)
    assert bundle.ground_truth.true_causes[0].detail == "NO_CONFIDENT_ROOT_CAUSE"
    assert bundle.ground_truth.injected_parameters == {}


def test_s15_dual_cause(config):
    bundle = generate_dataset("S15", app_config=config, write=False)
    codes = {c.code() for c in bundle.ground_truth.true_causes}
    assert codes == {"SPATIAL.EDGE", "PROCESS.DRIFT"}
