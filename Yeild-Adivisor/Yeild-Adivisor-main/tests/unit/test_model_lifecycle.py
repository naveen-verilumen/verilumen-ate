"""Phase 9 model lifecycle L01–L20. Candidates never become ACTIVE on the real registry."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from yield_improvement.model_lifecycle.activation import activate_candidate, approve_candidate
from yield_improvement.model_lifecycle.comparison import compare_candidate
from yield_improvement.model_lifecycle.evaluate import evaluate_version
from yield_improvement.model_lifecycle.hashes import hash_files
from yield_improvement.model_lifecycle.registry import (
    CHAMPION_VERSION,
    LifecyclePaths,
    bootstrap_champion,
    get_record,
    load_registry,
    put_record,
    save_registry,
)
from yield_improvement.model_lifecycle.rollback import rollback_to
from yield_improvement.model_lifecycle.states import LifecycleError
from yield_improvement.model_lifecycle.training import prepare_candidate, train_candidate
from yield_improvement.model_lifecycle.validation import validate_candidate
from yield_improvement.model_lifecycle.verify import verify_registry
from yield_improvement.model_lifecycle.versioning import assert_unused, next_candidate_version
from yield_improvement.utils.paths import repo_root


def _seed_paths(tmp_path: Path) -> LifecyclePaths:
    root = tmp_path / "ml"
    shutil.copytree(repo_root() / "artifacts" / "ml" / "yi_ml_v1", root / "yi_ml_v1")
    return LifecyclePaths(root=root)


def _tiny_dataset(folder: Path, *, n_per_lot: int = 16, n_lots: int = 3, seed: int = 7) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    rng = np.random.RandomState(seed)
    rows = []
    n = 0
    for lot_i in range(n_lots):
        lot = f"L{lot_i:03d}"
        for j in range(n_per_lot):
            n += 1
            x = float(rng.uniform(-1.0, 1.0))
            y = float(rng.uniform(-1.0, 1.0))
            fail = x > 0.15
            if rng.rand() < 0.12:
                fail = not fail
            pf = "FAIL" if fail else "PASS"
            rows.append(
                {
                    "lot_id": lot,
                    "wafer_id": f"W{j % 2}",
                    "die_id": f"D{n:04d}",
                    "product_id": "DEV_A",
                    "step_id": "WS_SORT",
                    "part_class": "PRODUCTION",
                    "x": x,
                    "y": y,
                    "attempt_id": f"E{n:04d}",
                    "timestamp": "2026-03-01T08:00:00Z",
                    "attempt_number": 1,
                    "is_first_attempt": "true",
                    "is_retest": "false",
                    "is_rework": "false",
                    "abort_flag": "false",
                    "pass_fail": pf,
                    "disposition": pf,
                    "sbin": "8" if fail else "1",
                    "tester_id": "T01" if rng.rand() > 0.5 else "T02",
                    "probe_card_id": "PC-1",
                    "prober_id": "PRB-1",
                    "site": str(j % 2),
                    "temperature_c": "25.0",
                    "voltage_v": "0.8",
                    "record_status": "VALID",
                }
            )
    pd.DataFrame(rows).to_csv(folder / "die_attempts.csv", index=False)
    return folder


def _prepared(tmp_path: Path):
    paths = _seed_paths(tmp_path)
    data = _tiny_dataset(tmp_path / "data")
    prep = prepare_candidate(data, paths=paths)
    return paths, data, prep["model_version"]


def test_l01_candidate_creation(tmp_path):
    paths, _, version = _prepared(tmp_path)
    rec = get_record(load_registry(paths), version)
    assert rec["state"] == "CANDIDATE"
    assert version == "yi_ml_v2_candidate_001"
    assert rec["parent_model_version"] == "yi_ml_v1"
    assert load_registry(paths)["active_version"] == "yi_ml_v1"
    assert not (paths.version_dir(version) / "model.pkl").is_file()


def test_l02_candidate_training_does_not_touch_champion(tmp_path):
    paths, _, version = _prepared(tmp_path)
    before = hash_files(paths.version_dir(CHAMPION_VERSION))
    out = train_candidate(version, paths=paths)
    after = hash_files(paths.version_dir(CHAMPION_VERSION))
    assert before == after
    assert out["state"] == "CANDIDATE"
    assert out["activated"] is False
    assert (paths.version_dir(version) / "model.pkl").is_file()
    assert load_registry(paths)["active_version"] == "yi_ml_v1"


def test_l03_candidate_evaluation(tmp_path):
    paths, data, version = _prepared(tmp_path)
    train_candidate(version, paths=paths)
    payload = evaluate_version(version, paths=paths)
    assert payload["split_strategy"] == "leave_one_lot_out"
    assert payload["n_lots"] == 3
    assert "pr_auc" in payload["raw_metrics"]
    assert "brier" in payload["calibrated_metrics"]
    assert payload["activated"] is False
    assert load_registry(paths)["active_version"] == "yi_ml_v1"


def test_l04_validation_pass(tmp_path):
    paths, _, version = _prepared(tmp_path)
    train_candidate(version, paths=paths)
    evaluate_version(version, paths=paths)
    result = validate_candidate(version, paths=paths)
    assert result["validated"] is True
    assert result["state"] == "VALIDATED"
    assert load_registry(paths)["active_version"] == "yi_ml_v1"


def test_l05_validation_failure_incomplete_stays_candidate(tmp_path):
    paths, _, version = _prepared(tmp_path)
    train_candidate(version, paths=paths)
    result = validate_candidate(version, paths=paths)
    assert result["validated"] is False
    assert get_record(load_registry(paths), version)["state"] == "CANDIDATE"


def test_l05_validation_failure_rejects_on_hash_mismatch(tmp_path):
    paths, _, version = _prepared(tmp_path)
    train_candidate(version, paths=paths)
    evaluate_version(version, paths=paths)
    blob = paths.version_dir(version) / "model.pkl"
    blob.write_bytes(blob.read_bytes() + b"x")
    result = validate_candidate(version, paths=paths)
    assert result["validated"] is False
    assert get_record(load_registry(paths), version)["state"] == "REJECTED"


def test_l06_approval(tmp_path):
    paths, _, version = _prepared(tmp_path)
    train_candidate(version, paths=paths)
    evaluate_version(version, paths=paths)
    validate_candidate(version, paths=paths)
    out = approve_candidate(version, approved_by="qa-engineer", paths=paths)
    rec = get_record(load_registry(paths), version)
    assert rec["state"] == "APPROVED"
    assert rec["approved_by"] == "qa-engineer"
    assert rec["approval_event_id"]
    assert out["activated"] is False
    assert load_registry(paths)["active_version"] == "yi_ml_v1"


def test_l07_l08_activation_retires_previous(tmp_path):
    paths, _, version = _prepared(tmp_path)
    train_candidate(version, paths=paths)
    evaluate_version(version, paths=paths)
    validate_candidate(version, paths=paths)
    approve_candidate(version, approved_by="qa-engineer", paths=paths)
    out = activate_candidate(version, activated_by="qa-engineer", paths=paths)
    registry = load_registry(paths)
    assert out["state"] == "ACTIVE"
    assert registry["active_version"] == version
    assert get_record(registry, CHAMPION_VERSION)["state"] == "RETIRED"
    assert get_record(registry, CHAMPION_VERSION).get("retired_at")
    assert (paths.version_dir(CHAMPION_VERSION) / "model.pkl").is_file()


def test_l09_rollback(tmp_path):
    paths, _, version = _prepared(tmp_path)
    train_candidate(version, paths=paths)
    evaluate_version(version, paths=paths)
    validate_candidate(version, paths=paths)
    approve_candidate(version, approved_by="qa-engineer", paths=paths)
    activate_candidate(version, activated_by="qa-engineer", paths=paths)
    out = rollback_to(CHAMPION_VERSION, rolled_back_by="qa-engineer", paths=paths)
    registry = load_registry(paths)
    assert out["state"] == "ACTIVE"
    assert registry["active_version"] == CHAMPION_VERSION
    assert get_record(registry, version)["state"] == "RETIRED"


def test_l10_duplicate_version_rejected():
    with pytest.raises(LifecycleError, match="duplicate"):
        assert_unused("yi_ml_v2_candidate_001", ["yi_ml_v1", "yi_ml_v2_candidate_001"])
    nxt = next_candidate_version(["yi_ml_v1", "yi_ml_v2_candidate_001"], champion_version="yi_ml_v1")
    assert nxt == "yi_ml_v2_candidate_002"


def test_l11_artifact_hash_mismatch_blocks_activate(tmp_path):
    paths, _, version = _prepared(tmp_path)
    train_candidate(version, paths=paths)
    evaluate_version(version, paths=paths)
    validate_candidate(version, paths=paths)
    approve_candidate(version, approved_by="qa-engineer", paths=paths)
    blob = paths.version_dir(version) / "model.pkl"
    blob.write_bytes(blob.read_bytes() + b"tamper")
    with pytest.raises(LifecycleError, match="hash"):
        activate_candidate(version, activated_by="qa-engineer", paths=paths)


def test_l12_feature_contract_mismatch(tmp_path):
    paths, _, version = _prepared(tmp_path)
    train_candidate(version, paths=paths)
    evaluate_version(version, paths=paths)
    meta_path = paths.version_dir(version) / "metadata.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["feature_contract"] = ["lot_id", "wafer_id"]
    meta["feature_names"] = ["lot_id", "wafer_id"]
    meta_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    from yield_improvement.model_lifecycle.training import CANDIDATE_FILES

    hashes = hash_files(paths.version_dir(version), CANDIDATE_FILES)
    registry = load_registry(paths)
    rec = dict(get_record(registry, version))
    rec["artifact_hashes"] = hashes
    rec["feature_contract"] = ["lot_id", "wafer_id"]
    put_record(registry, rec)
    save_registry(paths, registry)
    result = validate_candidate(version, paths=paths)
    assert result["validated"] is False
    assert get_record(load_registry(paths), version)["state"] == "REJECTED"


def test_l13_unauthorized_activation(tmp_path):
    paths, _, version = _prepared(tmp_path)
    train_candidate(version, paths=paths)
    with pytest.raises(LifecycleError, match="APPROVED"):
        activate_candidate(version, activated_by="qa-engineer", paths=paths)


def test_l14_approval_without_validation(tmp_path):
    paths, _, version = _prepared(tmp_path)
    train_candidate(version, paths=paths)
    evaluate_version(version, paths=paths)
    with pytest.raises(LifecycleError, match="VALIDATED"):
        approve_candidate(version, approved_by="qa-engineer", paths=paths)


def test_l15_activation_without_approval(tmp_path):
    paths, _, version = _prepared(tmp_path)
    train_candidate(version, paths=paths)
    evaluate_version(version, paths=paths)
    validate_candidate(version, paths=paths)
    with pytest.raises(LifecycleError, match="APPROVED"):
        activate_candidate(version, activated_by="qa-engineer", paths=paths)


def test_l16_automatic_activation_prevention(tmp_path):
    paths, _, version = _prepared(tmp_path)
    train_candidate(version, paths=paths)
    evaluate_version(version, paths=paths)
    validate_candidate(version, paths=paths)
    approve_candidate(version, approved_by="qa-engineer", paths=paths)
    assert load_registry(paths)["active_version"] == "yi_ml_v1"
    assert get_record(load_registry(paths), version)["state"] == "APPROVED"


def test_l17_registry_corruption_needs_review(tmp_path):
    paths = _seed_paths(tmp_path)
    bootstrap_champion(paths)
    registry = load_registry(paths)
    clone = dict(get_record(registry, CHAMPION_VERSION))
    clone["model_version"] = "yi_ml_v9"
    clone["state"] = "ACTIVE"
    put_record(registry, clone)
    save_registry(paths, registry)
    report = verify_registry(paths)
    assert report["status"] == "NEEDS_REVIEW"
    assert any("ACTIVE" in i for i in report["issues"])


def test_l18_audit_trail_integrity(tmp_path):
    paths, _, version = _prepared(tmp_path)
    train_candidate(version, paths=paths)
    audit = paths.audit_path.read_text(encoding="utf-8").strip().splitlines()
    assert audit
    first = json.loads(audit[0])
    paths.audit_path.write_text(paths.audit_path.read_text(encoding="utf-8") + json.dumps(first) + "\n", encoding="utf-8")
    report = verify_registry(paths)
    assert report["status"] == "NEEDS_REVIEW"
    assert any("duplicate event_id" in i for i in report["issues"])


def test_l19_monitoring_needs_retraining_does_not_retrain():
    src = repo_root() / "src" / "yield_improvement" / "monitoring"
    for path in src.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "prepare_candidate" not in text
        assert "train_candidate" not in text
        assert "activate_candidate" not in text
        assert "select_and_train" not in text


def test_l20_safety_invariants(tmp_path):
    paths, _, version = _prepared(tmp_path)
    out = train_candidate(version, paths=paths)
    assert out["production_action"] == "FORBIDDEN"
    assert out["production_authorized"] is False
    assert out["safety_eligible_production_count"] == 0
    assert out["safety_eligible_production_rate"] == 0.0
    assert out["invoked_agents"] == []
    ev = evaluate_version(version, paths=paths)
    assert ev["production_authorized"] is False
    cmp = compare_candidate(version, paths=paths)
    assert cmp["production_authorized"] is False
    assert cmp["candidate_status"] in {"SUPERIOR", "COMPARABLE", "INFERIOR", "INCONCLUSIVE"}


def test_approve_requires_human_id(tmp_path):
    paths, _, version = _prepared(tmp_path)
    train_candidate(version, paths=paths)
    evaluate_version(version, paths=paths)
    validate_candidate(version, paths=paths)
    with pytest.raises(LifecycleError, match="approved-by"):
        approve_candidate(version, approved_by="unavailable", paths=paths)


def test_arbitrary_path_activation_rejected(tmp_path):
    paths = _seed_paths(tmp_path)
    bootstrap_champion(paths)
    sneaky = tmp_path / "sneaky.pkl"
    sneaky.write_bytes(b"not-a-model")
    with pytest.raises(LifecycleError, match="arbitrary paths"):
        activate_candidate(str(sneaky), activated_by="qa-engineer", paths=paths)


def test_rollback_nonexistent(tmp_path):
    paths = _seed_paths(tmp_path)
    bootstrap_champion(paths)
    with pytest.raises(LifecycleError, match="unknown"):
        rollback_to("yi_ml_v9", rolled_back_by="qa-engineer", paths=paths)


def test_second_train_refused(tmp_path):
    paths, _, version = _prepared(tmp_path)
    train_candidate(version, paths=paths)
    with pytest.raises(LifecycleError, match="retrain existing"):
        train_candidate(version, paths=paths)


def test_reproducibility_same_seed_metrics(tmp_path):
    paths = _seed_paths(tmp_path)
    data = _tiny_dataset(tmp_path / "data")
    a = prepare_candidate(data, paths=paths)["model_version"]
    train_candidate(a, paths=paths)
    ea = evaluate_version(a, paths=paths)
    b = prepare_candidate(data, paths=paths)["model_version"]
    train_candidate(b, paths=paths)
    eb = evaluate_version(b, paths=paths)
    assert a != b
    assert ea["feature_names"] == eb["feature_names"]
    assert ea["raw_metrics"]["pr_auc"] == pytest.approx(eb["raw_metrics"]["pr_auc"], abs=1e-10)
    assert ea["raw_metrics"]["brier"] == pytest.approx(eb["raw_metrics"]["brier"], abs=1e-10)
    ha = json.loads((paths.version_dir(a) / "metadata.json").read_text(encoding="utf-8"))
    hb = json.loads((paths.version_dir(b) / "metadata.json").read_text(encoding="utf-8"))
    assert ha["seed"] == hb["seed"]
    assert ha["training_config_hash"] == hb["training_config_hash"]
