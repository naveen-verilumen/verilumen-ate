"""Monitoring holdout on M01–M10. Hidden GT is joined only here."""

from __future__ import annotations

import json

from yield_improvement.evaluation.monitoring import evaluate_all_monitoring, write_monitoring_evaluation
from yield_improvement.utils.paths import repo_root


def test_monitoring_package_isolation():
    src = repo_root() / "src" / "yield_improvement" / "monitoring"
    for path in src.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "ground_truth" not in text
        assert "monitoring_scenarios" not in text
        assert "EXPECTED" not in text or path.name == "contracts.py"


def test_monitoring_holdout_table(config):
    report = evaluate_all_monitoring(config=config, regenerate=True)
    write_monitoring_evaluation(config=config)
    assert report["n_scenarios"] == 10
    assert report["all_unauthorized"] is True
    assert report["none_retrained"] is True
    by = {r["scenario"]: r for r in report["rows"]}
    assert by["M01_NO_DRIFT"]["status"] == "PASS"
    assert by["M02_FEATURE_DRIFT"]["feature_drift"] in {"MONITOR", "REVIEW"}
    assert by["M02_FEATURE_DRIFT"]["performance"] != "DEGRADED"
    assert by["M09_SMALL_SAMPLE"]["predicted_state"] == "INSUFFICIENT_DATA"
    assert by["M10_NO_LABELS"]["target_drift"] == "UNAVAILABLE"
    assert by["M10_NO_LABELS"]["calibration"] == "UNAVAILABLE"
    assert by["M10_NO_LABELS"]["performance"] == "UNAVAILABLE"
    assert by["M08_SCHEMA_DEGRADATION"]["data_quality"] == "REVIEW"
    blob = json.dumps(report).lower()
    assert "increase limit" not in blob
    assert "deploy_new_model_automatically" not in blob
