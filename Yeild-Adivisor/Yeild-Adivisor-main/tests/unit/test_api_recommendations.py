from __future__ import annotations

from fastapi.testclient import TestClient
import pytest

from yield_improvement.api.app import create_app
from yield_improvement.model_lifecycle.hashes import hash_files
from yield_improvement.model_lifecycle.registry import default_paths
from yield_improvement.utils.paths import repo_root

CHAMPION_HASHES = {
    "feature_list.json": "3e4db1e3de47382f5533fe0e54d442f638f83e4bac7b0eeb2c7da6364462e0d7",
    "metadata.json": "6a3ffa163e808042c5cd08d270c0d7fe042e42d977a1b166e88ef2d7b37d71ad",
    "metrics.json": "16ea9d76745142efc8f2b61eee28ce614cd255fa36c42a4efe6aedfdabadddec",
    "model.pkl": "cab3a1b74560263b59b8d6c95f852b15fc91d7a0b91f311576a10aa11aeb2d70",
}


def _client() -> TestClient:
    return TestClient(create_app())


def test_get_recommendations_endpoint():
    client = _client()
    response = client.get("/api/datasets/yi_synthetic_v2/recommendations")
    assert response.status_code == 200
    body = response.json()

    assert body["dataset_id"] == "yi_synthetic_v2"
    assert body["recommendation_count"] > 0
    assert body["production_action"] == "FORBIDDEN"
    assert body["production_authorized"] is False
    assert body["safety_eligible_production_rate"] == 0.0
    assert body["ml_evidence_status"] == "NEEDS_MORE_DATA"

    recs = body["recommendations"]
    assert len(recs) == body["recommendation_count"]
    first = recs[0]
    assert first["priority_rank"] == 1
    assert "priority_tier" in first
    assert "confidence_tier" in first
    assert "recommended_action" in first
    assert "validation_protocol" in first
    assert first["production_action"] == "FORBIDDEN"
    assert first["production_authorized"] is False


def test_get_recommendation_detail_and_404():
    client = _client()
    list_res = client.get("/api/datasets/yi_synthetic_v2/recommendations").json()
    first_id = list_res["recommendations"][0]["recommendation_id"]

    # Valid ID
    detail_res = client.get(f"/api/datasets/yi_synthetic_v2/recommendations/{first_id}")
    assert detail_res.status_code == 200
    assert detail_res.json()["recommendation_id"] == first_id

    # Nonexistent ID
    bad_res = client.get("/api/datasets/yi_synthetic_v2/recommendations/REC-DOES_NOT_EXIST")
    assert bad_res.status_code == 404

    # Nonexistent Dataset
    bad_ds = client.get("/api/datasets/does_not_exist/recommendations")
    assert bad_ds.status_code == 404


def test_post_feedback_lifecycle_and_history():
    client = _client()
    list_res = client.get("/api/datasets/yi_synthetic_v2/recommendations").json()
    rec_id = list_res["recommendations"][0]["recommendation_id"]

    # 1. Accept for investigation
    payload1 = {
        "new_status": "ACCEPTED_FOR_INVESTIGATION",
        "engineer": "Test Engineer 1",
        "investigation_notes": "Accepted for test bench review.",
    }
    res1 = client.post(
        f"/api/datasets/yi_synthetic_v2/recommendations/{rec_id}/feedback",
        json=payload1,
    )
    assert res1.status_code == 200
    body1 = res1.json()
    assert body1["new_status"] == "ACCEPTED_FOR_INVESTIGATION"
    assert body1["production_action"] == "FORBIDDEN"
    assert body1["production_authorized"] is False

    # 2. Get history
    hist_res = client.get(f"/api/datasets/yi_synthetic_v2/recommendations/{rec_id}/feedback")
    assert hist_res.status_code == 200
    hist_body = hist_res.json()
    assert hist_body["current_status"] == "ACCEPTED_FOR_INVESTIGATION"
    assert len(hist_body["history"]) >= 1

    # 3. Invalid jump (ACCEPTED -> CLOSED without finishing)
    res_bad = client.post(
        f"/api/datasets/yi_synthetic_v2/recommendations/{rec_id}/feedback",
        json={
            "new_status": "CLOSED",
            "engineer": "Test Engineer 1",
            "investigation_notes": "Premature close",
        },
    )
    assert res_bad.status_code == 400


def test_champion_model_hashes_unmodified():
    before = hash_files(default_paths().version_dir("yi_ml_v1"))
    assert before == CHAMPION_HASHES
    # Run client calls
    _client().get("/api/datasets/yi_synthetic_v2/recommendations")
    after = hash_files(default_paths().version_dir("yi_ml_v1"))
    assert after == CHAMPION_HASHES
