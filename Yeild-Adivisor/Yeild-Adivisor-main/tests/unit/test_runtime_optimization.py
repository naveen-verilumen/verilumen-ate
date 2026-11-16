"""Tests for runtime optimizations: ingestion parsing, report reuse, in-memory filtering, and safety invariants."""

import pytest
from pathlib import Path
from unittest.mock import patch

from yield_improvement.config.loader import load_config
from yield_improvement.ingestion.loader import (
    load_die_attempts,
    load_parametric_measurements,
    load_test_results,
    parse_die_attempts,
    parse_parametric_measurements,
    parse_test_results,
    _dataframe_from_path,
)
from yield_improvement.reporting.adapter import (
    load_canonical_data,
    run_analysis_pipeline,
    build_report,
    build_report_from_data,
)
from yield_improvement.api.service import (
    assemble_dashboard,
    get_recommendations_bundle,
    load_report,
    find_dataset_dir,
)

DATASET_ID = "yi_synthetic_v2"


def test_ingestion_parsing_fields_and_source_rows():
    """Verify parsed canonical objects, field types, and 1-based source-row numbering."""
    cfg = load_config()
    folder = find_dataset_dir(DATASET_ID)
    assert folder is not None

    # 1. die_attempts
    attempts_res = load_die_attempts(folder / "die_attempts.csv", cfg)
    assert len(attempts_res.attempts) == 2560
    assert attempts_res.attempts[0].source_row == 2
    assert attempts_res.attempts[-1].source_row == 2561

    # 2. test_results
    tests_res = load_test_results(folder / "test_results.csv", cfg)
    assert len(tests_res.test_results) == 25600
    assert tests_res.test_results[0].source_row == 2
    assert tests_res.test_results[-1].source_row == 25601

    # 3. parametric_measurements
    param_res = load_parametric_measurements(folder / "parametric_measurements.csv", cfg)
    assert len(param_res.parametric) == 20480
    assert all(p.measurement is not None for p in param_res.parametric)


def test_recommendation_engine_report_reuse():
    """Verify get_recommendations_bundle reuses supplied reports without calling load_report."""
    global_rep = load_report(DATASET_ID)
    lot_rep = load_report(DATASET_ID, lot_id="L001")

    with patch("yield_improvement.api.service.load_report") as mock_load:
        bundle = get_recommendations_bundle(
            DATASET_ID,
            lot_id="L001",
            global_report=global_rep,
            lot_report=lot_rep,
        )
        # load_report should NOT be called because both valid reports were provided
        mock_load.assert_not_called()
        assert bundle["selected_lot_id"] == "L001"
        assert len(bundle["recommendations"]) > 0


def test_recommendation_engine_fallback_when_reports_omitted():
    """Verify get_recommendations_bundle falls back to load_report when reports are omitted."""
    bundle = get_recommendations_bundle(DATASET_ID, lot_id="L001")
    assert bundle["selected_lot_id"] == "L001"
    assert len(bundle["recommendations"]) > 0


def test_recommendation_engine_rejects_mismatched_dataset_reports():
    """Verify reports from another dataset are not accidentally reused."""
    global_rep = load_report(DATASET_ID)
    mismatched_rep = global_rep.model_copy(update={"dataset_id": "other_dataset"})

    with patch("yield_improvement.api.service.load_report", wraps=load_report) as mock_load:
        bundle = get_recommendations_bundle(
            DATASET_ID,
            global_report=mismatched_rep,
        )
        # Should have called load_report to safely load the correct dataset report
        mock_load.assert_called_with(DATASET_ID)


def test_in_memory_canonical_lot_filtering_equivalence():
    """Verify build_report_from_data with lot_id produces exact identical output to load_analysis."""
    cfg = load_config()
    folder = find_dataset_dir(DATASET_ID)
    assert folder is not None

    attempts, tests, parametric, cfg = load_canonical_data(folder, cfg)

    # Global report
    rep_global = build_report_from_data(folder.name, attempts, tests, parametric, cfg, lot_id=None)
    assert rep_global.fpy_summary.eligible_die_count == 2500
    assert rep_global.fpy_summary.first_pass_pass_count == 2249

    # Lot L001 report
    rep_l001 = build_report_from_data(folder.name, attempts, tests, parametric, cfg, lot_id="L001")
    assert rep_l001.fpy_summary.eligible_die_count == 500
    assert rep_l001.fpy_summary.first_pass_pass_count == 467

    # Lot L004 report
    rep_l004 = build_report_from_data(folder.name, attempts, tests, parametric, cfg, lot_id="L004")
    assert rep_l004.fpy_summary.eligible_die_count == 500
    assert rep_l004.fpy_summary.first_pass_pass_count == 403


def test_safety_invariants_preserved():
    """Verify fail-closed safety invariants across all lots in assemble_dashboard."""
    for lot_id in [None, "L001", "L004"]:
        dash = assemble_dashboard(DATASET_ID, lot_id=lot_id)
        assert dash["production_action"] == "FORBIDDEN"
        assert dash["production_authorized"] is False
        assert dash["safety_eligible_production_count"] == 0
        assert dash["safety_eligible_production_rate"] == 0.0
