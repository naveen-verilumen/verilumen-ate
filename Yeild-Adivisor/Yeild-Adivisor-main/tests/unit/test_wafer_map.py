"""First-pass wafer-map visualization payload. Does not retrain or change FPY."""

from __future__ import annotations

from fastapi.testclient import TestClient
import pytest

from yield_improvement.api.app import create_app
from yield_improvement.model_lifecycle.hashes import hash_files
from yield_improvement.model_lifecycle.registry import default_paths
from yield_improvement.utils.paths import repo_root

V1_HASHES = {
    "feature_list.json": "3e4db1e3de47382f5533fe0e54d442f638f83e4bac7b0eeb2c7da6364462e0d7",
    "metadata.json": "6a3ffa163e808042c5cd08d270c0d7fe042e42d977a1b166e88ef2d7b37d71ad",
    "metrics.json": "16ea9d76745142efc8f2b61eee28ce614cd255fa36c42a4efe6aedfdabadddec",
    "model.pkl": "cab3a1b74560263b59b8d6c95f852b15fc91d7a0b91f311576a10aa11aeb2d70",
}

V2_HASHES = {
    "feature_list.json": "3e4db1e3de47382f5533fe0e54d442f638f83e4bac7b0eeb2c7da6364462e0d7",
    "metadata.json": "1074dc10362a97b04e5e53414695a1c30ec12c367747d236f096f2f545552d92",
    "metrics.json": "1c8fd7666fa62646bf14894798ec0aae14654307726e148ce980f42128c4f938",
    "model.pkl": "784cc42525499e3a7b32a65a54aa33e23e4566d3ba3378fbf1bbb27956360aef",
}


def _client() -> TestClient:
    return TestClient(create_app())


def test_wafer_map_is_get_only():
    assert _client().post("/api/datasets/yi_synthetic_v2/wafer-map").status_code == 405


def test_wafer_map_missing_dataset_404():
    assert _client().get("/api/datasets/does_not_exist/wafer-map").status_code == 404


def test_v2_wafer_map_uses_physical_identity_and_first_pass():
    response = _client().get("/api/datasets/yi_synthetic_v2/wafer-map")
    assert response.status_code == 200
    body = response.json()
    assert body["production_action"] == "FORBIDDEN"
    assert body["production_authorized"] is False
    assert body["grain"] == "lot_id+wafer_id+die_id"
    assert body["n_dies"] == 2500
    assert body["n_pass"] == 2249
    assert body["n_fail"] == 251
    assert [lot["lot_id"] for lot in body["lots"]] == ["L001", "L002", "L003", "L004", "L005"]
    assert body["lots"][0]["wafers"] == ["W01", "W02", "W03", "W04", "W05"]

    by_key = {(row["lot_id"], row["wafer_id"], row["die_id"]): row for row in body["dies"]}
    assert len(by_key) == 2500
    fail = by_key[("L001", "W01", "D049")]
    assert fail["first_pass_result"] == "FAIL"
    assert fail["failed_test_id"] == "T001"
    assert fail["failure_code"] == "CONTINUITY"
    assert fail["is_first_fail"] is True
    assert fail["retest_available"] is True
    assert fail["x"] == 9
    assert fail["y"] == 5
    other = by_key[("L001", "W02", "D049")]
    assert other["first_pass_result"] == "PASS"
    assert other["failed_test_id"] is None
    assert other["failure_code"] is None
    passed = by_key[("L001", "W01", "D002")]
    assert passed["first_pass_result"] == "PASS"
    wafer = [row for row in body["dies"] if row["lot_id"] == "L001" and row["wafer_id"] == "W01"]
    assert len(wafer) == 100


def test_wafer_map_does_not_change_models_or_dashboard_fpy():
    client = _client()
    before_v1 = hash_files(default_paths().version_dir("yi_ml_v1"))
    before_v2 = hash_files(repo_root() / "artifacts" / "ml" / "yi_ml_v2")
    mapped = client.get("/api/datasets/yi_synthetic_v2/wafer-map")
    dash = client.get("/api/datasets/yi_synthetic_v2/dashboard")
    after_v1 = hash_files(default_paths().version_dir("yi_ml_v1"))
    after_v2 = hash_files(repo_root() / "artifacts" / "ml" / "yi_ml_v2")
    assert mapped.status_code == 200
    assert dash.status_code == 200
    fpy = dash.json()["report"]["fpy_summary"]
    assert fpy["eligible_die_count"] == 2500
    assert fpy["fpy"] == pytest.approx(0.8996, abs=1e-6)
    assert fpy["fpy_loss"] == pytest.approx(0.1004, abs=1e-6)
    assert fpy["first_pass_fail_count"] == 251
    assert fpy["first_pass_pass_count"] == 2249
    assert before_v1 == after_v1 == V1_HASHES
    assert before_v2 == after_v2 == V2_HASHES
