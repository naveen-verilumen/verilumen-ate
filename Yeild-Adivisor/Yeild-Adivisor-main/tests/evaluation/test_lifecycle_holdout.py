"""Phase 9 lifecycle on the real champion: yi_ml_v1 stays ACTIVE and unmodified."""

from __future__ import annotations

from yield_improvement.ml.pipeline import run_ml
from yield_improvement.model_lifecycle.commands import list_models, verify_registry
from yield_improvement.model_lifecycle.hashes import hash_files
from yield_improvement.model_lifecycle.registry import CHAMPION_VERSION, default_paths
from yield_improvement.utils.paths import repo_root


def test_lifecycle_package_isolation():
    src = repo_root() / "src" / "yield_improvement" / "model_lifecycle"
    for path in src.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "yield_improvement.evaluation" not in text
        assert "RUN_SUMMARY" not in text
        assert "evaluation/ground_truth" not in text


def test_real_champion_immutable_after_registry_bootstrap():
    paths = default_paths()
    before = hash_files(paths.version_dir(CHAMPION_VERSION))
    listed = list_models(paths)
    report = verify_registry(paths)
    after = hash_files(paths.version_dir(CHAMPION_VERSION))
    assert before == after
    assert listed["active_version"] == "yi_ml_v1"
    assert report["status"] == "OK"
    assert report["production_authorized"] is False
    states = {row["version"]: row["state"] for row in listed["models"]}
    assert states["yi_ml_v1"] == "ACTIVE"
    assert all(state != "ACTIVE" or version == "yi_ml_v1" for version, state in states.items())


def test_ml_persist_refuses_to_overwrite_champion(tmp_path, config):
    import numpy as np
    import pandas as pd
    import pytest

    paths = default_paths()
    before = hash_files(paths.version_dir(CHAMPION_VERSION))
    folder = tmp_path / "ds"
    folder.mkdir()
    rng = np.random.RandomState(0)
    rows = []
    n = 0
    for lot in ("L1", "L2", "L3"):
        for j in range(8):
            n += 1
            fail = rng.rand() > 0.6
            rows.append(
                {
                    "lot_id": lot,
                    "wafer_id": "W0",
                    "die_id": f"D{n}",
                    "product_id": "DEV_A",
                    "step_id": "WS_SORT",
                    "part_class": "PRODUCTION",
                    "x": float(rng.uniform(-1, 1)),
                    "y": float(rng.uniform(-1, 1)),
                    "attempt_id": f"E{n}",
                    "timestamp": "2026-03-01T08:00:00Z",
                    "attempt_number": 1,
                    "is_first_attempt": "true",
                    "is_retest": "false",
                    "abort_flag": "false",
                    "pass_fail": "FAIL" if fail else "PASS",
                    "disposition": "FAIL" if fail else "PASS",
                    "tester_id": "T01",
                    "probe_card_id": "PC-1",
                    "prober_id": "PRB-1",
                    "site": "0",
                    "temperature_c": "25",
                    "voltage_v": "0.8",
                    "record_status": "VALID",
                }
            )
    pd.DataFrame(rows).to_csv(folder / "die_attempts.csv", index=False)
    with pytest.raises(RuntimeError, match="Refusing to overwrite"):
        run_ml(folder, config=config, persist=True)
    assert hash_files(paths.version_dir(CHAMPION_VERSION)) == before
