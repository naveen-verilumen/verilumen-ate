"""End-to-end fixture directory pipeline (no detectors)."""

from __future__ import annotations

from yield_improvement.pipeline import run_fixture_dir
from yield_improvement.utils.paths import fixtures_fpy_dir


def test_case_01_and_02_pipeline(config):
    one = run_fixture_dir(fixtures_fpy_dir() / "case_01", config=config)
    two = run_fixture_dir(fixtures_fpy_dir() / "case_02", config=config)
    assert one.fpy == 0.9
    assert two.per_die[0].fpy_counts_as == "FAIL"
    assert two.final_yield == 1.0
