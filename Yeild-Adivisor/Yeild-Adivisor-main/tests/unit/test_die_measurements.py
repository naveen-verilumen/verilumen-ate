"""Tests for actual first-pass parametric measurements on wafer map dies."""

from __future__ import annotations
import pytest
from fastapi.testclient import TestClient

from yield_improvement.api.app import create_app
from yield_improvement.api.wafer_map import build_wafer_map


def _client() -> TestClient:
    return TestClient(create_app())


def test_die_measurements_exact_match_source():
    wm = build_wafer_map("yi_synthetic_v2")
    by_key = {(d["lot_id"], d["wafer_id"], d["die_id"]): d for d in wm["dies"]}
    
    # Check D066 on L001 W01 (known IDDQ fail)
    d066 = by_key[("L001", "W01", "D066")]
    assert "measurements" in d066
    m = d066["measurements"]
    assert isinstance(m, dict)
    assert "IDDQ" in m
    assert pytest.approx(m["IDDQ"], 1e-4) == 50.203395
    assert pytest.approx(m["VMIN"], 1e-4) == 0.592479
    assert pytest.approx(m["VMAX"], 1e-4) == 1.17092
    assert d066["failure_code"] == "IDDQ"
    assert d066["failed_test_id"] == "T005"
    assert d066["first_pass_result"] == "FAIL"


def test_die_measurements_physical_identity_no_cross_lot_leak():
    wm = build_wafer_map("yi_synthetic_v2")
    by_key = {(d["lot_id"], d["wafer_id"], d["die_id"]): d for d in wm["dies"]}
    
    # Dies with same die_id across different lots must have different physical measurements
    d_l1 = by_key[("L001", "W01", "D066")]
    d_l2 = by_key[("L002", "W01", "D066")]
    assert d_l1["measurements"]["IDDQ"] != d_l2["measurements"]["IDDQ"]


def test_die_measurements_missing_file_safety(tmp_path):
    attempts_csv = tmp_path / "die_attempts.csv"
    attempts_csv.write_text("attempt_id,lot_id,wafer_id,die_id,attempt_number,pass_fail\natt1,L001,W01,D001,1,PASS\n", encoding="utf-8")
    from yield_improvement.api import wafer_map
    orig_find = wafer_map.find_dataset_dir
    try:
        wafer_map.find_dataset_dir = lambda ds: tmp_path if ds == "test_dummy" else orig_find(ds)
        res = wafer_map.build_wafer_map("test_dummy")
        assert len(res["dies"]) == 1
        assert res["dies"][0]["measurements"] == {}
    finally:
        wafer_map.find_dataset_dir = orig_find


def test_die_measurements_api_route_iddq():
    client = _client()
    res = client.get("/api/datasets/yi_synthetic_v2/wafer-map")
    assert res.status_code == 200
    body = res.json()
    d066 = next(d for d in body["dies"] if d["lot_id"] == "L001" and d["wafer_id"] == "W01" and d["die_id"] == "D066")
    assert d066["failure_code"] == "IDDQ"
    assert "measurements" in d066
    assert isinstance(d066["measurements"]["IDDQ"], (int, float))
    assert pytest.approx(d066["measurements"]["IDDQ"], 1e-4) == 50.203395


def test_die_measurements_duplicate_or_ambiguous_attempts(tmp_path):
    attempts_csv = tmp_path / "die_attempts.csv"
    # D001 has two attempts: 1 (first-pass) and 2 (retest)
    attempts_csv.write_text(
        "attempt_id,lot_id,wafer_id,die_id,attempt_number,pass_fail,timestamp\n"
        "att1,L001,W01,D001,1,FAIL,2026-01-01T00:00:00Z\n"
        "att2,L001,W01,D001,2,PASS,2026-01-01T01:00:00Z\n",
        encoding="utf-8"
    )
    params_csv = tmp_path / "parametric_measurements.csv"
    params_csv.write_text(
        "attempt_id,lot_id,wafer_id,die_id,parameter_name,measurement\n"
        "att1,L001,W01,D001,IDDQ,49.5\n"
        "att2,L001,W01,D001,IDDQ,30.2\n",
        encoding="utf-8"
    )
    from yield_improvement.api import wafer_map
    orig_find = wafer_map.find_dataset_dir
    try:
        wafer_map.find_dataset_dir = lambda ds: tmp_path if ds == "test_dummy_dup" else orig_find(ds)
        res = wafer_map.build_wafer_map("test_dummy_dup")
        assert len(res["dies"]) == 1
        die = res["dies"][0]
        assert die["first_pass_result"] == "FAIL"
        assert die["retest_available"] is True
        # Must strictly select attempt 1 (first-pass: 49.5), never retest attempt 2 (30.2)
        assert die["measurements"]["IDDQ"] == pytest.approx(49.5)
    finally:
        wafer_map.find_dataset_dir = orig_find


def test_die_measurements_missing_first_pass_or_null_measurement(tmp_path):
    attempts_csv = tmp_path / "die_attempts.csv"
    attempts_csv.write_text(
        "attempt_id,lot_id,wafer_id,die_id,attempt_number,pass_fail\n"
        "att1,L001,W01,D001,1,FAIL\n"
        "att2,L001,W01,D002,2,FAIL\n",  # D002 only has retest attempt
        encoding="utf-8"
    )
    params_csv = tmp_path / "parametric_measurements.csv"
    params_csv.write_text(
        "attempt_id,lot_id,wafer_id,die_id,parameter_name,measurement\n"
        "att1,L001,W01,D001,IDDQ,invalid_nan\n",
        encoding="utf-8"
    )
    from yield_improvement.api import wafer_map
    orig_find = wafer_map.find_dataset_dir
    try:
        wafer_map.find_dataset_dir = lambda ds: tmp_path if ds == "test_dummy_null" else orig_find(ds)
        res = wafer_map.build_wafer_map("test_dummy_null")
        by_die = {d["die_id"]: d for d in res["dies"]}
        # D002 was not first pass, excluded from first-pass dies
        assert "D002" not in by_die
        # D001 has invalid_nan -> parsed as None
        assert by_die["D001"]["measurements"]["IDDQ"] is None
    finally:
        wafer_map.find_dataset_dir = orig_find

