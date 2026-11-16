from __future__ import annotations

from datetime import datetime, timezone

from yield_improvement.models.canonical import DieAttempt, TestResult
from yield_improvement.yield_analysis.attribution import select_primary


def _attempt(**kwargs) -> DieAttempt:
    defaults = dict(
        attempt_id="E1",
        lot_id="L",
        wafer_id="W",
        die_id="D",
        product_id="DEV_A",
        step_id="WS_SORT",
        timestamp=datetime(2026, 3, 1, tzinfo=timezone.utc),
        attempt_number=1,
        is_first_attempt=True,
        is_retest=False,
        abort_flag=False,
        pass_fail="FAIL",
        sbin=8,
        failure_code="IDDQ",
    )
    defaults.update(kwargs)
    return DieAttempt(**defaults)


def test_is_first_fail_wins(config):
    tests = [
        TestResult(attempt_id="E1", test_id="T_A", test_pass_fail="FAIL", sequence_index=9, is_first_fail=True, failure_code="CONTINUITY"),
        TestResult(attempt_id="E1", test_id="T_B", test_pass_fail="FAIL", sequence_index=1, is_first_fail=False, failure_code="IDDQ"),
    ]
    key, code, method, tax, cofail = select_primary(_attempt(), tests, config)
    assert key == "T_A"
    assert method == "is_first_fail"
    assert code == "CONTINUITY"
    assert [t.test_id for t in cofail] == ["T_B"]


def test_two_is_first_fail_is_unknown(config):
    tests = [
        TestResult(attempt_id="E1", test_id="T_A", test_pass_fail="FAIL", is_first_fail=True),
        TestResult(attempt_id="E1", test_id="T_B", test_pass_fail="FAIL", is_first_fail=True),
    ]
    key, _, method, tax, cofail = select_primary(_attempt(), tests, config)
    assert key == "UNKNOWN_PRIMARY_FAILURE"
    assert method == "UNKNOWN_PRIMARY_FAILURE"
    assert tax == "UNKNOWN.PRIMARY_UNORDERED"
    assert len(cofail) == 2


def test_min_sequence_index(config):
    tests = [
        TestResult(attempt_id="E1", test_id="T_LATE", test_pass_fail="FAIL", sequence_index=8, is_first_fail=False),
        TestResult(attempt_id="E1", test_id="T_EARLY", test_pass_fail="FAIL", sequence_index=2, is_first_fail=False),
    ]
    key, _, method, _, cofail = select_primary(_attempt(), tests, config)
    assert key == "T_EARLY"
    assert method == "sequence_index"
    assert [t.test_id for t in cofail] == ["T_LATE"]


def test_tied_sequence_is_unknown(config):
    tests = [
        TestResult(attempt_id="E1", test_id="T_A", test_pass_fail="FAIL", sequence_index=3),
        TestResult(attempt_id="E1", test_id="T_B", test_pass_fail="FAIL", sequence_index=3),
    ]
    key, _, method, _, _ = select_primary(_attempt(), tests, config)
    assert key == "UNKNOWN_PRIMARY_FAILURE"
    assert method == "UNKNOWN_PRIMARY_FAILURE"


def test_no_order_two_fails_unknown(config):
    tests = [
        TestResult(attempt_id="E1", test_id="T_A", test_pass_fail="FAIL"),
        TestResult(attempt_id="E1", test_id="T_B", test_pass_fail="FAIL"),
    ]
    key, _, method, tax, _ = select_primary(_attempt(), tests, config)
    assert key == "UNKNOWN_PRIMARY_FAILURE"
    assert tax == "UNKNOWN.PRIMARY_UNORDERED"


def test_abort_without_tests(config):
    key, code, method, tax, _ = select_primary(_attempt(abort_flag=True, failure_code=None), [], config)
    assert key == "ABORT"
    assert method == "abort"
    assert tax == "UNKNOWN.UNSPECIFIED"


def test_unmapped_failure_code_stays_unknown(config):
    from yield_improvement.yield_analysis.taxonomy import map_taxonomy

    code = map_taxonomy(config, failure_code="NOT_A_REAL_CODE")
    assert code == "UNKNOWN.UNMAPPED_CODE"
    family, detail = config.taxonomy.split(code)
    assert family == "UNKNOWN"
    assert detail == "UNMAPPED_CODE"


def test_does_not_guess_family_from_similar_string(config):
    from yield_improvement.yield_analysis.taxonomy import map_taxonomy

    # Must not become CONTACT just because the string contains 'CONT'
    assert map_taxonomy(config, failure_code="CONTAMINATION_XYZ") == "UNKNOWN.UNMAPPED_CODE"
