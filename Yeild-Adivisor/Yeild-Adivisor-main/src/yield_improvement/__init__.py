"""Standalone Yield Improvement Agent — Phase 1 FPY + Phase 2 synthetic data."""

from yield_improvement.detectors.runner import run_detectors, run_detectors_on_dir
from yield_improvement.hypotheses.composer import compose, compose_from_dir
from yield_improvement.opportunity.engine import estimate_from_dir, estimate_opportunities
from yield_improvement.pipeline import run_pipeline
from yield_improvement.reporting.adapter import build_report_from_dir
from yield_improvement.validation.validator import validate_from_dir

__version__ = "0.1.0"
__all__ = [
    "run_pipeline",
    "run_detectors",
    "run_detectors_on_dir",
    "compose",
    "compose_from_dir",
    "estimate_from_dir",
    "estimate_opportunities",
    "validate_from_dir",
    "build_report_from_dir",
    "__version__",
]
