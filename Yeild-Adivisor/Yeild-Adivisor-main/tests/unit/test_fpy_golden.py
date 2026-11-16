"""Golden FPY fixtures CASE_01–14. Expected values come only from expected.json."""

from __future__ import annotations

import json

import pytest

from pathlib import Path

from yield_improvement.pipeline import run_fixture_dir
from yield_improvement.utils.paths import fixtures_fpy_dir, repo_root


def load_expected(case_dir: Path) -> dict:
    return json.loads((case_dir / "expected.json").read_text(encoding="utf-8"))


def case_dirs() -> list[Path]:
    root = repo_root() / "tests" / "fixtures" / "fpy"
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    return [root / item["dir"] for item in manifest["cases"]]


def _approx_or_none(actual, expected):
    if expected is None:
        assert actual is None
        return
    assert actual == pytest.approx(expected)


@pytest.mark.parametrize("case_dir", case_dirs(), ids=lambda p: p.name)
def test_golden_fpy_counts(case_dir, config):
    expected = load_expected(case_dir)
    result = run_fixture_dir(case_dir, config=config)
    assert result.status == "OK"
    assert result.n_eligible == expected["n_eligible"]
    assert result.n_first_pass_pass == expected["n_first_pass_pass"]
    assert result.n_first_pass_fail == expected["n_first_pass_fail"]
    if "n_excluded" in expected:
        assert result.n_excluded == expected["n_excluded"]
    _approx_or_none(result.fpy, expected["fpy"])
    assert result.invariant_ok is True
    assert result.n_eligible == result.n_first_pass_pass + result.n_first_pass_fail
    assert result.escape_status == "unavailable"
    assert result.escape_rate is None
    assert result.abort_policy == config.fpy.abort_policy
    assert result.fpy_policy_version == config.fpy.fpy_policy_version


@pytest.mark.parametrize("case_dir", case_dirs(), ids=lambda p: p.name)
def test_golden_optional_fields(case_dir, config):
    expected = load_expected(case_dir)
    result = run_fixture_dir(case_dir, config=config)
    if "fpy_loss" in expected:
        _approx_or_none(result.fpy_loss, expected["fpy_loss"])
    if "final_yield" in expected:
        _approx_or_none(result.final_yield, expected["final_yield"])
    if "retest_rate_of_eligible" in expected:
        _approx_or_none(result.retest_rate_of_eligible, expected["retest_rate_of_eligible"])
    if "retest_recovery" in expected:
        _approx_or_none(result.retest_recovery, expected["retest_recovery"])
    if "n_retested" in expected:
        assert result.n_retested == expected["n_retested"]
    if "part_class_assumed_production" in expected:
        assert result.part_class_assumed_production is expected["part_class_assumed_production"]
    if "assumed_production_dies" in expected:
        assert result.assumed_production_dies == expected["assumed_production_dies"]


def test_case_01_fpy_is_90_percent(config, fpy_fixtures):
    expected = load_expected(fpy_fixtures / "case_01")
    result = run_fixture_dir(fpy_fixtures / "case_01", config=config)
    assert expected["fpy"] == 0.9
    assert result.eligible_die_count == 10
    assert result.first_pass_pass_count == 9
    assert result.first_pass_fail_count == 1
    assert result.fpy == pytest.approx(0.90)
    assert result.errors == []
    assert result.primary_fail_pareto[0].failure_key == expected["primary_fail_pareto"][0]["failure_key"]
    assert result.primary_fail_pareto[0].n_dies == 1
    assert result.primary_fail_pareto[0].contribution == pytest.approx(0.1)


def test_case_02_retest_pass_does_not_improve_fpy(config, fpy_fixtures):
    expected = load_expected(fpy_fixtures / "case_02")
    result = run_fixture_dir(fpy_fixtures / "case_02", config=config)
    d01 = next(d for d in result.per_die if d.die_id == "D01")
    assert d01.fpy_counts_as == "FAIL"
    assert d01.first_pass_disposition == expected["per_die"][0]["first_pass_disposition"]
    assert d01.final_disposition == "PASS"
    assert result.fpy == pytest.approx(0.5)


def test_case_03_first_pass_pass_remains_pass(config, fpy_fixtures):
    expected = load_expected(fpy_fixtures / "case_03")
    result = run_fixture_dir(fpy_fixtures / "case_03", config=config)
    d01 = next(d for d in result.per_die if d.die_id == "D01")
    assert d01.fpy_counts_as == expected["per_die"][0]["fpy_counts_as"]
    assert result.fpy == pytest.approx(1.0)
    assert result.final_yield == pytest.approx(0.5)


def test_case_04_abort_is_fail(config, fpy_fixtures):
    assert config.fpy.abort_is_first_pass_fail is True
    expected = load_expected(fpy_fixtures / "case_04")
    result = run_fixture_dir(fpy_fixtures / "case_04", config=config)
    d01 = next(d for d in result.per_die if d.die_id == "D01")
    assert d01.fpy_counts_as == "FAIL"
    assert d01.abort_flag is True
    assert d01.primary_failure_key == expected["per_die"][0]["primary_failure_key"]
    assert result.fpy == pytest.approx(0.5)


@pytest.mark.parametrize(
    "folder,reason",
    [
        ("case_05", "ENGINEERING"),
        ("case_06", "CALIBRATION"),
        ("case_07", "REWORK"),
        ("case_08", "RETEST_ONLY"),
        ("case_09", "MISSING_DISPOSITION"),
        ("case_11", "AMBIGUOUS_DUPLICATE"),
    ],
)
def test_exclusion_reasons_match_fixture(folder, reason, config, fpy_fixtures):
    expected = load_expected(fpy_fixtures / folder)
    result = run_fixture_dir(fpy_fixtures / folder, config=config)
    exp_reasons = {row["reason"] for row in expected["exclusions"]}
    got_reasons = {row.reason for row in result.exclusions}
    assert reason in exp_reasons
    assert got_reasons == exp_reasons
    assert {row["die_id"] for row in expected["exclusions"]} == {row.die_id for row in result.exclusions}


def test_case_10_missing_part_class_assumption(config, fpy_fixtures):
    expected = load_expected(fpy_fixtures / "case_10")
    result = run_fixture_dir(fpy_fixtures / "case_10", config=config)
    assert result.part_class_assumed_production is True
    assert result.assumed_production_dies == expected["assumed_production_dies"]
    flags = [i.code for i in result.assumptions]
    assert config.fpy.part_class_missing.flag in flags
    d01 = next(d for d in result.per_die if d.die_id == "D01")
    assert d01.part_class == config.fpy.part_class_missing.treat_as
    assert d01.fpy_counts_as == "PASS"


def test_case_12_multi_fail_counted_once(config, fpy_fixtures):
    expected = load_expected(fpy_fixtures / "case_12")
    result = run_fixture_dir(fpy_fixtures / "case_12", config=config)
    assert result.n_first_pass_fail == 1
    assert len(result.primary_failures) == 1
    assert result.primary_fail_pareto[0].failure_key == expected["primary_fail_pareto"][0]["failure_key"]
    assert result.primary_fail_pareto[0].n_dies == 1
    assert result.primary_failures[0].selection_method == "is_first_fail"
    assert {c.failure_key for c in result.cofail} == {row["failure_key"] for row in expected["cofail"]}
    primary_sum = sum(row.n_dies for row in result.primary_fail_pareto)
    assert primary_sum == result.n_first_pass_fail


def test_case_13_additive_primary_contribution(config, fpy_fixtures):
    expected = load_expected(fpy_fixtures / "case_13")
    result = run_fixture_dir(fpy_fixtures / "case_13", config=config)
    row = result.primary_fail_pareto[0]
    exp = expected["primary_fail_pareto"][0]
    assert row.failure_key == exp["failure_key"]
    assert row.n_dies == exp["n_dies"]
    assert row.contribution == pytest.approx(exp["contribution"])
    assert row.share_of_fails == pytest.approx(exp["share_of_fails"])
    assert row.overlap_allowed is False
    assert sum(r.n_dies for r in result.primary_fail_pareto) == result.n_first_pass_fail


def test_case_14_any_fail_overlaps_primary_does_not(config, fpy_fixtures):
    expected = load_expected(fpy_fixtures / "case_14")
    result = run_fixture_dir(fpy_fixtures / "case_14", config=config)
    assert sum(r.n_dies for r in result.primary_fail_pareto) == expected["sum_primary_n_dies"]
    assert sum(r.n_dies for r in result.primary_fail_pareto) == result.n_first_pass_fail
    any_sum = sum(r.n_dies for r in result.any_fail_pareto)
    assert any_sum == expected["sum_any_fail_n_dies"]
    assert any_sum > result.n_first_pass_fail
    assert all(r.overlap_allowed for r in result.any_fail_pareto)
    keys = {r.failure_key: r.n_dies for r in result.any_fail_pareto}
    for exp in expected["any_fail_pareto"]:
        assert keys[exp["failure_key"]] == exp["n_dies"]
        assert result.any_fail_pareto[0].overlap_allowed is True
    assert result.primary_fail_pareto[0].overlap_allowed is False
    assert {c.failure_key for c in result.cofail} == {"T_FUNC"}


def test_same_input_same_output(config, fpy_fixtures):
    a = run_fixture_dir(fpy_fixtures / "case_01", config=config).to_public_dict()
    b = run_fixture_dir(fpy_fixtures / "case_01", config=config).to_public_dict()
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_engineering_excluded_from_policy_yaml_not_hardcoded(config, fpy_fixtures):
    assert "ENGINEERING" in config.fpy.excluded_part_classes
    result = run_fixture_dir(fpy_fixtures / "case_05", config=config)
    assert any(e.reason == "ENGINEERING" for e in result.exclusions)
