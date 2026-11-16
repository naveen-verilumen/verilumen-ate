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


def test_api_health():
    response = _client().get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["production_action"] == "FORBIDDEN"
    assert body["production_authorized"] is False


def test_api_lists_datasets():
    response = _client().get("/api/datasets")
    assert response.status_code == 200
    rows = response.json()["datasets"]
    ids = {row["dataset_id"] for row in rows}
    assert ids == {"yi_synthetic_v2"}
    assert "case_01" not in ids
    assert not any(item.startswith("ds_") for item in ids)
    assert not any(item.startswith("ds_mon_") for item in ids)
    v2 = rows[0]
    assert v2["display_name"] == "Yield Improvement V2"
    assert v2["n_lots"] == 5
    assert v2["n_wafers"] == 25
    assert v2["n_dies"] == 2500
    assert [lot["lot_id"] for lot in v2["lots"]] == ["L001", "L002", "L003", "L004", "L005"]
    assert [lot["display_name"] for lot in v2["lots"]] == ["LOT 001", "LOT 002", "LOT 003", "LOT 004", "LOT 005"]


def test_api_missing_dataset_404():
    response = _client().get("/api/datasets/does_not_exist/dashboard")
    assert response.status_code == 404


def test_api_is_get_only():
    client = _client()
    for path in (
        "/api/health",
        "/api/datasets",
        "/api/ml/active",
        "/api/test-catalog",
        "/api/datasets/case_01/dashboard",
        "/api/datasets/yi_synthetic_v2/wafer-map",
    ):
        assert client.post(path).status_code == 405


def test_dashboard_copies_fpy_from_report():
    client = _client()
    response = client.get("/api/datasets/case_01/dashboard")
    assert response.status_code == 200
    body = response.json()
    report = body["report"]
    assert body["dataset_id"] == "case_01"
    assert report["fpy_summary"]["fpy"] == 0.9
    assert report["fpy_summary"]["fpy_loss"] == 0.1
    assert report["fpy_summary"]["eligible_die_count"] == 10
    assert report["production_action"] == "FORBIDDEN"
    assert report["production_authorized"] is False
    assert report["safety_eligible_production_count"] == 0
    assert report["safety_eligible_production_rate"] == 0.0
    assert body["production_action"] == "FORBIDDEN"
    assert body["invoked_agents"] == []
    assert body["ml"]["evidence_role"] == "SECONDARY_SUPPORT"
    assert body["ml"]["independence"] is False
    catalog = {row["test_id"]: row for row in body["test_catalog"]["tests"]}
    assert catalog["T004"]["test_name"] == "CONTACT"
    assert catalog["T004"]["test_type"] == "CONTACT"


def test_test_catalog_endpoint():
    response = _client().get("/api/test-catalog")
    assert response.status_code == 200
    body = response.json()
    by_id = {row["test_id"]: row for row in body["tests"]}
    expected = {
        "T001": "CONTINUITY",
        "T002": "OPENS",
        "T003": "SHORTS",
        "T004": "CONTACT",
        "T005": "IDDQ",
        "T006": "VMIN",
        "T007": "VMAX",
        "T008": "LEAKAGE",
        "T009": "FUNCTIONAL",
        "T010": "SCAN",
    }
    assert list(by_id) == list(expected)
    for test_id, name in expected.items():
        assert by_id[test_id]["test_name"] == name
        assert by_id[test_id]["test_type"] == name
        assert by_id[test_id]["display_label"] == f"{test_id} — {name}"
        assert by_id[test_id]["test_name"] != "UNCLASSIFIED"
    assert "Unclassified V2 Test" not in {row["test_name"] for row in body["tests"]}
    assert "test_id" in by_id["T004"]


def test_dashboard_cache_returns_same_payload():
    client = _client()
    first = client.get("/api/datasets/case_01/dashboard").json()
    second = client.get("/api/datasets/case_01/dashboard").json()
    assert first["generated_at"] == second["generated_at"]
    assert first["report"]["fpy_summary"] == second["report"]["fpy_summary"]


def test_ml_snapshot_copies_champion_artifacts_without_modification():
    before = hash_files(default_paths().version_dir("yi_ml_v1"))
    response = _client().get("/api/ml/active")
    after = hash_files(default_paths().version_dir("yi_ml_v1"))
    assert response.status_code == 200
    body = response.json()
    assert body["available"] is True
    assert body["model_version"] == "yi_ml_v1"
    assert body["model_name"] == "logistic"
    assert body["metrics"]["roc_auc"] == 0.7153149306340475
    assert before == after == CHAMPION_HASHES


def test_health_snapshot_copies_persisted_degraded_status():
    response = _client().get("/api/datasets/ds_mon_06/health")
    assert response.status_code == 200
    body = response.json()
    assert body["available"] is True
    assert body["overall_status"] == "DEGRADED"
    assert body["reduced_ml_evidence"] is True
    assert body["retrained"] is False
    assert body["production_authorized"] is False


def test_health_unavailable_when_no_persisted_report():
    response = _client().get("/api/datasets/case_01/health")
    assert response.status_code == 200
    body = response.json()
    assert body["available"] is False
    assert body["overall_status"] is None
    assert body["reduced_ml_evidence"] is False


def test_champion_hashes_match_registry_after_api_use():
    path = repo_root() / "artifacts" / "ml" / "yi_ml_v1"
    assert hash_files(path) == CHAMPION_HASHES


EXPECTED_PRIMARY_PARETO = [
    ("T004", 92),
    ("T006", 39),
    ("T005", 38),
    ("T001", 17),
    ("T002", 13),
    ("T007", 12),
    ("T009", 12),
    ("T003", 10),
    ("T008", 9),
    ("T010", 9),
]


def test_v2_dashboard_catalog_does_not_change_analytics():
    response = _client().get("/api/datasets/yi_synthetic_v2/dashboard")
    assert response.status_code == 200
    body = response.json()
    fpy = body["report"]["fpy_summary"]
    assert fpy["eligible_die_count"] == 2500
    assert fpy["fpy"] == pytest.approx(0.8996, abs=1e-6)
    assert fpy["fpy_loss"] == pytest.approx(0.1004, abs=1e-6)
    primary = body["report"]["loss_summary"]["primary_failure"]
    assert [(row["failure_key"], row["affected_die_count"]) for row in primary] == EXPECTED_PRIMARY_PARETO
    catalog = {row["test_id"]: row for row in body["test_catalog"]["tests"]}
    expected_labels = {
        "T001": "T001 — CONTINUITY",
        "T002": "T002 — OPENS",
        "T003": "T003 — SHORTS",
        "T004": "T004 — CONTACT",
        "T005": "T005 — IDDQ",
        "T006": "T006 — VMIN",
        "T007": "T007 — VMAX",
        "T008": "T008 — LEAKAGE",
        "T009": "T009 — FUNCTIONAL",
        "T010": "T010 — SCAN",
    }
    assert {row["test_id"] for row in body["test_catalog"]["tests"]} == set(expected_labels)
    for test_id, label in expected_labels.items():
        assert catalog[test_id]["display_label"] == label
        assert catalog[test_id]["test_name"] == label.split(" — ", 1)[1]
        assert catalog[test_id]["test_type"] == catalog[test_id]["test_name"]
        assert "Unclassified V2 Test" not in catalog[test_id]["test_name"]
        assert catalog[test_id]["test_name"] != "UNCLASSIFIED"
        assert "UNCLASSIFIED" not in catalog[test_id]["test_type"]
    assert fpy["first_pass_fail_count"] == 251
    assert sum(row["affected_die_count"] for row in primary) == 251
    assert hash_files(repo_root() / "artifacts" / "ml" / "yi_ml_v1") == CHAMPION_HASHES


def test_population_lot_ids_extracts_lot_from_group_and_comparison():
    from yield_improvement.api.service import population_lot_ids

    assert "L004" in population_lot_ids({"group": "L004", "n": 500})
    assert "L004" in population_lot_ids({"group": "L004/W05", "n": 100})
    assert "L004" in population_lot_ids({"comparison": "VMIN:L004", "n": 500})
    assert population_lot_ids({"grain": "edge", "n": 120}) == set()


def _named_lots(hyp: dict) -> set[str]:
    from yield_improvement.api.service import population_lot_ids

    return {
        token
        for token in population_lot_ids(hyp.get("affected_population"))
        if len(token) >= 2 and token[0] in {"L", "l"} and token[1:].isdigit()
    }


def test_lot_scoped_dashboard_uses_lot_specific_metrics_and_pareto():
    client = _client()
    global_body = client.get("/api/datasets/yi_synthetic_v2/dashboard").json()
    l001 = client.get("/api/datasets/yi_synthetic_v2/dashboard", params={"lot_id": "L001"}).json()
    l004 = client.get("/api/datasets/yi_synthetic_v2/dashboard", params={"lot_id": "L004"}).json()

    # 1. Global (All Lots) assertions
    fpy_global = global_body["report"]["fpy_summary"]
    assert fpy_global["eligible_die_count"] == 2500
    assert fpy_global["first_pass_pass_count"] == 2249
    assert fpy_global["first_pass_fail_count"] == 251
    assert fpy_global["fpy"] == pytest.approx(0.8996, abs=1e-6)
    assert fpy_global["fpy_loss"] == pytest.approx(0.1004, abs=1e-6)
    expected_pareto = [(row["failure_key"], row["affected_die_count"]) for row in global_body["report"]["loss_summary"]["primary_failure"]]
    assert expected_pareto == EXPECTED_PRIMARY_PARETO
    assert sum(row["affected_die_count"] for row in global_body["report"]["loss_summary"]["primary_failure"]) == 251

    # 2. LOT 001 assertions (500 dies, 467 passes, 33 fails, 93.40% FPY, 6.60% loss, Pareto sum 33)
    assert l001["selected_lot_id"] == "L001"
    assert l001["selected_lot_display"] == "LOT 001"
    fpy_1 = l001["report"]["fpy_summary"]
    assert fpy_1["eligible_die_count"] == 500
    assert fpy_1["first_pass_pass_count"] == 467
    assert fpy_1["first_pass_fail_count"] == 33
    assert fpy_1["fpy"] == pytest.approx(0.9340, abs=1e-6)
    assert fpy_1["fpy_loss"] == pytest.approx(0.0660, abs=1e-6)
    pareto_1 = l001["report"]["loss_summary"]["primary_failure"]
    assert sum(row["affected_die_count"] for row in pareto_1) == 33
    assert "93.40%" in l001["report"]["executive_summary"]["text"]
    assert "500 eligible dies" in l001["report"]["executive_summary"]["text"]
    assert all(f["sample_size"] == 500 for f in l001["report"]["evidence_findings"] if f["detector"] != "near_limit")
    assert next(f for f in l001["report"]["evidence_findings"] if f["detector"] == "near_limit")["sample_size"] == 4000
    assert l001["report"]["data_gaps"] is not None

    # 3. LOT 004 assertions (500 dies, 403 passes, 97 fails, 80.60% FPY, 19.40% loss, Pareto sum 97)
    assert l004["selected_lot_id"] == "L004"
    assert l004["selected_lot_display"] == "LOT 004"
    fpy_4 = l004["report"]["fpy_summary"]
    assert fpy_4["eligible_die_count"] == 500
    assert fpy_4["first_pass_pass_count"] == 403
    assert fpy_4["first_pass_fail_count"] == 97
    assert fpy_4["fpy"] == pytest.approx(0.8060, abs=1e-6)
    assert fpy_4["fpy_loss"] == pytest.approx(0.1940, abs=1e-6)
    pareto_4 = l004["report"]["loss_summary"]["primary_failure"]
    assert sum(row["affected_die_count"] for row in pareto_4) == 97
    assert "80.60%" in l004["report"]["executive_summary"]["text"]
    assert "500 eligible dies" in l004["report"]["executive_summary"]["text"]
    assert all(f["sample_size"] == 500 for f in l004["report"]["evidence_findings"] if f["detector"] != "near_limit")
    assert next(f for f in l004["report"]["evidence_findings"] if f["detector"] == "near_limit")["sample_size"] == 4000

    # 4. Scoped findings and validation consistency
    for body, lot_id in ((l001, "L001"), (l004, "L004")):
        for hyp in body["report"]["hypotheses"]:
            assert hyp["evidence_tier"] != "INSUFFICIENT_EVIDENCE"
            assert hyp["association_class"] != "INSUFFICIENT_EVIDENCE"
            named = _named_lots(hyp)
            assert not (named - {lot_id})
        opp_ids = {row["hypothesis_id"] for row in body["report"]["opportunities"] if row.get("family") != "UNION"}
        hyp_ids = {row["hypothesis_id"] for row in body["report"]["hypotheses"]}
        assert opp_ids <= hyp_ids
        val_hyp_ids = {row["hypothesis_id"] for row in body["report"]["validation"] if row.get("hypothesis_id")}
        assert val_hyp_ids <= hyp_ids

    # 5. Switching from selected lot back to All Lots restores global response
    restored = client.get("/api/datasets/yi_synthetic_v2/dashboard").json()
    assert restored["selected_lot_id"] is None
    fpy_restored = restored["report"]["fpy_summary"]
    assert fpy_restored["eligible_die_count"] == 2500
    assert fpy_restored["first_pass_pass_count"] == 2249
    assert fpy_restored["first_pass_fail_count"] == 251
    assert fpy_restored["fpy"] == pytest.approx(0.8996, abs=1e-6)
    assert fpy_restored["fpy_loss"] == pytest.approx(0.1004, abs=1e-6)
    assert sum(row["affected_die_count"] for row in restored["report"]["loss_summary"]["primary_failure"]) == 251

    assert hash_files(repo_root() / "artifacts" / "ml" / "yi_ml_v1") == CHAMPION_HASHES
