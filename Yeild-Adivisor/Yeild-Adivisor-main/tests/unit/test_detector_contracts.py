"""Detector contracts, missing-data behavior, and stats helpers."""

from __future__ import annotations

from datetime import datetime, timezone

from yield_improvement.detectors.contract import DetectorResult
from yield_improvement.detectors.runner import run_detectors
from yield_improvement.detectors.stats import benjamini_hochberg, compare_proportions
from yield_improvement.models.canonical import DieAttempt, ParametricMeasurement, TestResult


def _ts():
    return datetime(2026, 3, 1, 8, 0, tzinfo=timezone.utc)


def _die(i: int, *, x=None, y=None, fail=False, tester="T01", probe="PC-1", temp=25.0, lot="L001", wafer="W01"):
    return DieAttempt(
        attempt_id=f"E{i}",
        lot_id=lot,
        wafer_id=wafer,
        die_id=f"D{i:03d}",
        product_id="DEV_A",
        step_id="WS_SORT",
        part_class="PRODUCTION",
        timestamp=_ts(),
        attempt_number=1,
        is_first_attempt=True,
        is_retest=False,
        is_rework=False,
        abort_flag=False,
        pass_fail="FAIL" if fail else "PASS",
        x=x,
        y=y,
        tester_id=tester,
        probe_card_id=probe,
        temperature_c=temp,
    )


def test_never_confirmed_root_cause(config):
    attempts = [_die(i, x=0, y=0) for i in range(60)]
    bundle = run_detectors(attempts, config)
    dumped = bundle.to_public_dict()
    assert "confirmed_root_cause" not in dumped
    for name, res in bundle.results.items():
        assert res.not_a_root_cause is True
        assert "confirmed_root_cause" not in res.model_dump()
        assert res.status in {"SIGNAL", "NO_SIGNAL", "INSUFFICIENT_DATA"}


def test_spatial_missing_xy_insufficient(config):
    attempts = [_die(i, fail=(i % 10 == 0)) for i in range(80)]
    bundle = run_detectors(attempts, config)
    assert bundle.results["spatial"].status == "INSUFFICIENT_DATA"
    assert "missing_x_y" in bundle.results["spatial"].data_gaps


def test_equipment_missing_tester_insufficient(config):
    attempts = [_die(i, x=0, y=0, tester=None) for i in range(120)]
    bundle = run_detectors(attempts, config)
    assert bundle.results["equipment"].status == "INSUFFICIENT_DATA"
    assert "missing_tester_id" in bundle.results["equipment"].data_gaps


def test_near_limit_missing_limits_insufficient(config):
    attempts = [_die(i, x=0, y=0) for i in range(80)]
    params = [
        ParametricMeasurement(attempt_id=f"E{i}", parameter_name="IDDQ", measurement=10.0 + i)
        for i in range(80)
    ]
    bundle = run_detectors(attempts, config, parametric=params)
    assert bundle.results["near_limit"].status == "INSUFFICIENT_DATA"
    assert "missing_limits" in bundle.results["near_limit"].data_gaps


def test_sequence_missing_index_insufficient(config):
    attempts = [_die(i, x=0, y=0) for i in range(80)]
    tests = [
        TestResult(attempt_id=f"E{i}", test_id="T_A", test_pass_fail="PASS")
        for i in range(80)
    ]
    bundle = run_detectors(attempts, config, test_results=tests)
    assert bundle.results["sequence"].status == "INSUFFICIENT_DATA"
    assert "missing_sequence_index" in bundle.results["sequence"].data_gaps


def test_contact_missing_probe_insufficient(config):
    attempts = [_die(i, x=0, y=0, probe=None) for i in range(120)]
    bundle = run_detectors(attempts, config)
    assert bundle.results["contact"].status == "INSUFFICIENT_DATA"
    assert "missing_probe_card_id" in bundle.results["contact"].data_gaps


def test_parametric_missing_table_insufficient(config):
    attempts = [_die(i, x=0, y=0) for i in range(80)]
    bundle = run_detectors(attempts, config, parametric=[])
    assert bundle.results["parametric"].status == "INSUFFICIENT_DATA"


def test_benjamini_hochberg_monotone():
    adj = benjamini_hochberg([0.001, 0.04, 0.20, None], 0.10)
    assert adj[0] <= adj[1] <= adj[2]
    assert adj[3] is None
    assert adj[0] <= 0.01


def test_two_proportion_detects_large_delta():
    cmp_ = compare_proportions(40, 100, 5, 100)
    assert abs(cmp_.rate_diff - 0.35) < 1e-9
    assert cmp_.p_value < 0.001


def test_detector_result_rejects_confirmed_field():
    payload = DetectorResult(
        detector="spatial",
        status="NO_SIGNAL",
        method="x",
    ).model_dump()
    assert "confirmed_root_cause" not in payload
