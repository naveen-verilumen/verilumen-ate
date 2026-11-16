"""Physical-die identity and V2 grid-border classification. Does not retrain or rewrite data."""

from __future__ import annotations

from datetime import datetime, timezone
from math import hypot

from yield_improvement.config.loader import load_config
from yield_improvement.detectors.population import DetectorContext, DieView
from yield_improvement.detectors.spatial import detect_spatial
from yield_improvement.ingestion.loader import load_die_attempts, load_test_results
from yield_improvement.models.canonical import DieAttempt, TestResult
from yield_improvement.utils.paths import repo_root
from yield_improvement.yield_analysis.fpy import calculate_fpy
from yield_improvement.yield_analysis.grid_region import grid_bounds, is_grid_border

DATASET = repo_root() / "data" / "synthetic" / "agent_visible" / "yi_synthetic_v2"


def _v2():
    app = load_config()
    attempts = load_die_attempts(DATASET / "die_attempts.csv", app).attempts
    tests = load_test_results(DATASET / "test_results.csv", app).test_results
    fpy = calculate_fpy(attempts, app, test_results=tests)
    return app, attempts, fpy


def _attempt(lot: str, wafer: str, die: str) -> DieAttempt:
    return DieAttempt(
        attempt_id=f"E-{lot}-{wafer}-{die}-1",
        lot_id=lot,
        wafer_id=wafer,
        die_id=die,
        product_id="P",
        step_id="S",
        attempt_number=1,
        is_first_attempt=True,
        is_retest=False,
        abort_flag=False,
        pass_fail="FAIL",
        x=1,
        y=1,
        timestamp=datetime(2026, 11, 1, tzinfo=timezone.utc),
    )


def _fail(attempt_id: str, test_id: str, code: str) -> TestResult:
    return TestResult(
        attempt_id=attempt_id,
        test_id=test_id,
        test_pass_fail="FAIL",
        sequence_index=1,
        is_first_fail=True,
        failure_code=code,
    )


def test_primary_failure_uses_physical_die_key():
    _, _, fpy = _v2()
    assert fpy.eligible_die_count == 2500
    assert fpy.first_pass_pass_count == 2249
    assert fpy.first_pass_fail_count == 251
    assert fpy.fpy == 0.8996
    assert fpy.fpy_loss == 0.1004
    assert sum(row.n_dies for row in fpy.primary_fail_pareto) == 251

    by_physical = {
        (row.lot_id, row.wafer_id, row.die_id): row for row in fpy.primary_failures
    }
    assert len(by_physical) == 251
    legacy: dict[str, object] = {}
    for row in fpy.primary_failures:
        legacy[row.die_id] = row
    mismatches = 0
    for outcome in fpy.per_die:
        if outcome.first_pass_disposition != "FAIL":
            assert outcome.primary_failure_code is None
            continue
        true = by_physical[(outcome.lot_id, outcome.wafer_id, outcome.die_id)]
        assert outcome.primary_failure_key == true.primary_failure_key
        assert outcome.primary_failure_code == true.primary_failure_code
        old = legacy[outcome.die_id]
        if (old.primary_failure_key, old.primary_failure_code) != (
            true.primary_failure_key,
            true.primary_failure_code,
        ):
            mismatches += 1
    assert mismatches == 137


def test_duplicate_die_ids_across_wafers_are_distinct():
    app = load_config()
    attempts = [
        _attempt("L001", "W01", "D001"),
        _attempt("L001", "W02", "D001"),
    ]
    tests = [
        _fail(attempts[0].attempt_id, "T001", "CONTINUITY"),
        _fail(attempts[1].attempt_id, "T004", "CONTACT"),
    ]
    fpy = calculate_fpy(attempts, app, test_results=tests)
    by_wafer = {row.wafer_id: row for row in fpy.per_die}
    assert by_wafer["W01"].primary_failure_code == "CONTINUITY"
    assert by_wafer["W02"].primary_failure_code == "CONTACT"
    assert by_wafer["W01"].die_id == by_wafer["W02"].die_id == "D001"


def test_duplicate_die_ids_across_lots_are_distinct():
    app = load_config()
    attempts = [
        _attempt("L001", "W01", "D001"),
        _attempt("L002", "W01", "D001"),
    ]
    tests = [
        _fail(attempts[0].attempt_id, "T001", "CONTINUITY"),
        _fail(attempts[1].attempt_id, "T006", "VMIN"),
    ]
    fpy = calculate_fpy(attempts, app, test_results=tests)
    by_lot = {row.lot_id: row for row in fpy.per_die}
    assert by_lot["L001"].primary_failure_code == "CONTINUITY"
    assert by_lot["L002"].primary_failure_code == "VMIN"
    assert by_lot["L001"].die_id == by_lot["L002"].die_id == "D001"


def _first_pass(attempts):
    return [row for row in attempts if row.attempt_number == 1]


def test_v2_border_region_uses_grid_boundary():
    _, attempts, fpy = _v2()
    first = _first_pass(attempts)
    points = [(float(row.x), float(row.y)) for row in first]
    bounds = grid_bounds(points)
    assert bounds == (1.0, 10.0, 1.0, 10.0)
    border = [row for row in first if is_grid_border(float(row.x), float(row.y), bounds)]
    assert len(first) == 2500
    assert len(border) == 900
    assert is_grid_border(1, 1, bounds)
    assert is_grid_border(1, 5, bounds)
    assert is_grid_border(10, 10, bounds)
    failed = {
        (row.lot_id, row.wafer_id, row.die_id)
        for row in fpy.per_die
        if row.first_pass_disposition == "FAIL"
    }
    border_fail = sum(1 for row in border if (row.lot_id, row.wafer_id, row.die_id) in failed)
    assert border_fail / len(border) > 0.12


def test_v2_inner_region_excludes_boundary():
    _, attempts, fpy = _v2()
    first = _first_pass(attempts)
    bounds = grid_bounds([(float(row.x), float(row.y)) for row in first])
    inner = [row for row in first if not is_grid_border(float(row.x), float(row.y), bounds)]
    assert len(inner) == 1600
    assert all(row.x not in {1, 10} and row.y not in {1, 10} for row in inner)
    assert not is_grid_border(5, 5, bounds)
    failed = {
        (row.lot_id, row.wafer_id, row.die_id)
        for row in fpy.per_die
        if row.first_pass_disposition == "FAIL"
    }

    def rate(lot: str, members) -> float:
        group = [row for row in members if row.lot_id == lot]
        return sum(1 for row in group if (row.lot_id, row.wafer_id, row.die_id) in failed) / len(group)

    border = [row for row in first if is_grid_border(float(row.x), float(row.y), bounds)]
    assert abs(rate("L002", border) - (30 / 180)) < 1e-9
    assert abs(rate("L002", inner) - (19 / 320)) < 1e-9
    assert rate("L002", border) > rate("L002", inner) + 0.05
    assert rate("L005", border) > rate("L005", inner) + 0.05
    l004 = [row for row in fpy.per_die if row.lot_id == "L004"]
    by_wafer = {}
    for row in l004:
        by_wafer.setdefault(row.wafer_id, []).append(row)
    w01 = sum(row.first_pass_disposition == "FAIL" for row in by_wafer["W01"]) / 100
    w05 = sum(row.first_pass_disposition == "FAIL" for row in by_wafer["W05"]) / 100
    assert w01 == 0.06
    assert w05 == 0.45


def _grid_die(x: int, y: int, failed: bool) -> DieView:
    return DieView(
        lot_id="L001",
        wafer_id="W01",
        die_id=f"D{y:02d}{x:02d}",
        attempt_id=f"E-{x}-{y}",
        failed=failed,
        x=float(x),
        y=float(y),
        r=hypot(x, y),
        tester_id=None,
        probe_card_id=None,
        temperature_c=None,
        timestamp=None,
        failure_code=None,
        primary_failure_code=None,
        primary_failure_family=None,
        primary_failure_detail=None,
    )


def test_spatial_detector_uses_v2_border_definition():
    app = load_config()
    dies = []
    for y in range(1, 11):
        for x in range(1, 11):
            border = x in {1, 10} or y in {1, 10}
            dies.append(_grid_die(x, y, failed=border))
    result = detect_spatial(
        DetectorContext(
            dies=dies,
            attempts=[],
            test_results=[],
            parametric=[],
            config=app,
            n_eligible=len(dies),
        )
    )
    assert result.status == "SIGNAL"
    assert result.hypothesis_detail == "BORDER"
    assert result.not_a_root_cause is True
    boundary = next(item for item in result.evidence if item.name == "grid_boundary")
    assert boundary.value["x_min"] == 1.0
    assert boundary.value["x_max"] == 10.0
    border = next(item for item in result.hypotheses if item.detail == "BORDER")
    inner = next(item for item in result.hypotheses if item.detail == "INNER")
    assert border.n_affected == 36
    assert inner.n_affected == 64
    assert border.effect_size == 1.0
