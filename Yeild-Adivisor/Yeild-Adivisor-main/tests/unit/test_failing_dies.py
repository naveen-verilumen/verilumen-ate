"""Unit tests for the 'View Failing Dies' drill-down feature."""

import pytest
from fastapi.testclient import TestClient

from yield_improvement.api.app import app
from yield_improvement.models.canonical import DieAttempt
from yield_improvement.recommendations.failing_dies import extract_recommendation_failing_dies


DATASET_ID = "yi_synthetic_v2"


def test_unique_die_counting_and_physical_identity():
    """Verify dies are uniquely identified by (lot_id, wafer_id, die_id) without duplicate keys."""
    res = extract_recommendation_failing_dies(DATASET_ID, "REC-SPATIAL.BORDER")
    failing_dies = res["failing_dies"]

    seen_keys = set()
    for d in failing_dies:
        assert "lot_id" in d and d["lot_id"]
        assert "wafer_id" in d and d["wafer_id"]
        assert "die_id" in d and d["die_id"]
        key = (d["lot_id"], d["wafer_id"], d["die_id"])
        assert key not in seen_keys, f"Duplicate physical die found: {key}"
        seen_keys.add(key)

    assert len(seen_keys) == len(failing_dies)
    assert res["counts"]["subgroup_failing_dies"] == len(failing_dies)


def test_first_pass_filtering_and_retest_exclusion():
    """Verify only first-pass failures are counted and retest-only failures are strictly excluded."""
    res = extract_recommendation_failing_dies(DATASET_ID, "REC-TEST.LIMIT_SENSITIVITY")
    for d in res["failing_dies"]:
        assert d["first_pass_result"] == "FAIL"
        assert d["primary_failure_code"] is not None


def test_subgroup_membership_wafer():
    """Verify wafer variation recommendation isolates the specific lot and wafer."""
    res = extract_recommendation_failing_dies(DATASET_ID, "REC-PROCESS.WAFER_VARIATION", lot_id="L004")
    assert res["counts"]["subgroup_eligible_dies"] == 100
    assert res["counts"]["subgroup_failing_dies"] == 45
    assert res["counts"]["subgroup_failure_rate"] == 0.45

    for d in res["failing_dies"]:
        assert d["lot_id"] == "L004"
        assert d["wafer_id"] == "W05"


def test_subgroup_membership_lot():
    """Verify lot variation recommendation isolates the specific lot."""
    res = extract_recommendation_failing_dies(DATASET_ID, "REC-PROCESS.LOT_VARIATION", lot_id="L004")
    assert res["counts"]["subgroup_eligible_dies"] == 500
    assert res["counts"]["subgroup_failing_dies"] == 97
    assert res["counts"]["subgroup_failure_rate"] == 0.194

    for d in res["failing_dies"]:
        assert d["lot_id"] == "L004"


def test_subgroup_membership_spatial():
    """Verify spatial border recommendation isolates border dies."""
    # Global border
    res_global = extract_recommendation_failing_dies(DATASET_ID, "REC-SPATIAL.BORDER")
    assert res_global["counts"]["subgroup_eligible_dies"] == 900
    assert res_global["counts"]["subgroup_failing_dies"] == 118

    # Lot-specific border (L002)
    res_l002 = extract_recommendation_failing_dies(DATASET_ID, "REC-SPATIAL.BORDER", lot_id="L002")
    assert res_l002["counts"]["subgroup_eligible_dies"] == 180
    assert res_l002["counts"]["subgroup_failing_dies"] == 30
    for d in res_l002["failing_dies"]:
        assert d["lot_id"] == "L002"


def test_subgroup_membership_near_limit():
    """Verify near-limit recommendation isolates dies with measurements near test limits."""
    res = extract_recommendation_failing_dies(DATASET_ID, "REC-TEST.LIMIT_SENSITIVITY")
    assert res["counts"]["subgroup_eligible_measurements"] == 299
    assert res["counts"]["subgroup_failing_measurements"] == 67
    assert res["counts"]["subgroup_failing_dies"] == 59
    assert res["counts"]["subgroup_eligible_dies"] == 277

    for d in res["failing_dies"]:
        measurements = d["relevant_measurements"]
        assert any(m["near_limit"] is True for m in measurements), f"Die {d['die_id']} has no near-limit measurement"


def test_denominators_accuracy():
    """Verify subgroup, lot, and dataset denominators are explicitly distinct and mathematically accurate."""
    res = extract_recommendation_failing_dies(DATASET_ID, "REC-PROCESS.WAFER_VARIATION", lot_id="L004")
    counts = res["counts"]

    # 1. Subgroup: Wafer W05 in L004
    assert counts["subgroup_failing_dies"] == 45
    assert counts["subgroup_eligible_dies"] == 100
    assert counts["subgroup_failure_rate"] == 0.45

    # 2. Lot: L004
    assert counts["lot_failing_dies"] == 97
    assert counts["lot_eligible_dies"] == 500
    assert counts["lot_failure_rate"] == 0.194

    # 3. Overall Dataset
    assert counts["dataset_failing_dies"] == 251
    assert counts["dataset_eligible_dies"] == 2500
    assert counts["dataset_failure_rate"] == 0.1004

    # All three levels must be distinct
    assert counts["subgroup_eligible_dies"] != counts["lot_eligible_dies"]
    assert counts["lot_eligible_dies"] != counts["dataset_eligible_dies"]


def test_safety_invariants_preserved():
    """Verify fail-closed diagnostic policy is strictly preserved."""
    res = extract_recommendation_failing_dies(DATASET_ID, "REC-TEST.LIMIT_SENSITIVITY")
    assert res["production_action"] == "FORBIDDEN"
    assert res["production_authorized"] is False
    assert "safety_statement" in res
    assert "disclaimer" in res


def test_api_endpoint_failing_dies():
    """Verify FastAPI endpoint serves recommendation failing dies with 200 OK and cache."""
    client = TestClient(app)
    url = f"/api/datasets/{DATASET_ID}/recommendations/REC-TEST.LIMIT_SENSITIVITY/failing-dies"

    resp = client.get(url)
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["recommendation_id"] == "REC-TEST.LIMIT_SENSITIVITY"
    assert payload["production_action"] == "FORBIDDEN"
    assert payload["production_authorized"] is False
    assert len(payload["failing_dies"]) == 59
    assert payload["counts"]["subgroup_failing_dies"] == 59

    # Test with lot_id
    resp_lot = client.get(f"/api/datasets/{DATASET_ID}/recommendations/REC-PROCESS.WAFER_VARIATION/failing-dies?lot_id=L004")
    assert resp_lot.status_code == 200
    payload_lot = resp_lot.json()
    assert payload_lot["counts"]["lot_id"] == "L004"
    assert len(payload_lot["failing_dies"]) == 45
