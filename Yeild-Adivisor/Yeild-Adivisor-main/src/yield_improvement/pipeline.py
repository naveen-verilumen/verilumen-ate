"""Phase 1 pipeline: load → validate → FPY → structured result."""

from __future__ import annotations

import logging
from pathlib import Path

from yield_improvement.config.loader import AppConfig, load_config
from yield_improvement.ingestion.loader import load_die_attempts, load_test_results
from yield_improvement.models.results import DataQualityIssue, FpyResult
from yield_improvement.utils.errors import LoadError
from yield_improvement.validation.quality import collect_quality_issues
from yield_improvement.yield_analysis.fpy import calculate_fpy

logger = logging.getLogger("yield_improvement")


def run_pipeline(
    die_attempts_path: str | Path,
    test_results_path: str | Path | None = None,
    config: AppConfig | None = None,
    config_dir: str | Path | None = None,
) -> FpyResult:
    cfg = config or load_config(Path(config_dir) if config_dir else None)
    attempts_file = Path(die_attempts_path)
    logger.info("Input die_attempts=%s", attempts_file)

    loaded = load_die_attempts(attempts_file, cfg)
    issues = list(loaded.issues)
    logger.info("Loaded %s attempt rows", len(loaded.attempts))

    tests = []
    if test_results_path is not None:
        tr_path = Path(test_results_path)
        if tr_path.is_file():
            logger.info("Input test_results=%s", tr_path)
            tr_loaded = load_test_results(tr_path, cfg)
            tests = tr_loaded.test_results
            issues.extend(tr_loaded.issues)
            logger.info("Loaded %s test_result rows", len(tests))

    if any(i.code in {"FORBIDDEN_COLUMN", "MISSING_REQUIRED_COLUMNS"} for i in issues):
        logger.info("Validation: fatal schema error")
        return calculate_fpy([], cfg, extra_issues=issues)

    issues.extend(collect_quality_issues(loaded.attempts, tests, cfg))
    n_err = sum(1 for i in issues if i.severity == "ERROR")
    n_warn = sum(1 for i in issues if i.severity == "WARNING")
    n_asm = sum(1 for i in issues if i.severity == "ASSUMPTION")
    logger.info("Validation: errors=%s warnings=%s assumptions=%s", n_err, n_warn, n_asm)

    result = calculate_fpy(loaded.attempts, cfg, test_results=tests, extra_issues=issues)
    logger.info(
        "Eligible dies=%s first-pass pass=%s fail=%s excluded=%s FPY=%s",
        result.eligible_die_count,
        result.first_pass_pass_count,
        result.first_pass_fail_count,
        result.excluded_count,
        result.fpy,
    )
    return result


def run_fixture_dir(case_dir: str | Path, config: AppConfig | None = None) -> FpyResult:
    folder = Path(case_dir)
    attempts = folder / "die_attempts.csv"
    if not attempts.is_file():
        raise LoadError(f"No die_attempts.csv in {folder}")
    tests = folder / "test_results.csv"
    return run_pipeline(
        attempts,
        tests if tests.is_file() else None,
        config=config,
    )
