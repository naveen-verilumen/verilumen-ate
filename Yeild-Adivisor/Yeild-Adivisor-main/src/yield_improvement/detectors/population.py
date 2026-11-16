"""First-pass eligible dies for detectors. Uses the FPY engine; does not invent fields."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import hypot

from yield_improvement.config.loader import AppConfig
from yield_improvement.models.canonical import DieAttempt, ParametricMeasurement, TestResult
from yield_improvement.yield_analysis.fpy import calculate_fpy


@dataclass(frozen=True)
class DieView:
    lot_id: str
    wafer_id: str
    die_id: str
    attempt_id: str
    failed: bool
    x: float | None
    y: float | None
    r: float | None
    tester_id: str | None
    probe_card_id: str | None
    temperature_c: float | None
    timestamp: datetime | None
    failure_code: str | None
    primary_failure_code: str | None
    primary_failure_family: str | None
    primary_failure_detail: str | None


@dataclass
class DetectorContext:
    dies: list[DieView]
    attempts: list[DieAttempt]
    test_results: list[TestResult]
    parametric: list[ParametricMeasurement]
    config: AppConfig
    n_eligible: int

    def tests_by_attempt(self) -> dict[str, list[TestResult]]:
        grouped: dict[str, list[TestResult]] = {}
        for row in self.test_results:
            grouped.setdefault(row.attempt_id, []).append(row)
        return grouped

    def parametric_by_attempt(self) -> dict[str, list[ParametricMeasurement]]:
        grouped: dict[str, list[ParametricMeasurement]] = {}
        for row in self.parametric:
            grouped.setdefault(row.attempt_id, []).append(row)
        return grouped


def build_context(
    attempts: list[DieAttempt],
    config: AppConfig,
    test_results: list[TestResult] | None = None,
    parametric: list[ParametricMeasurement] | None = None,
) -> DetectorContext:
    tests = test_results or []
    fpy = calculate_fpy(attempts, config, test_results=tests)
    by_id = {a.attempt_id: a for a in attempts}
    dies: list[DieView] = []
    for outcome in fpy.per_die:
        attempt = by_id.get(outcome.attempt_id)
        if attempt is None:
            continue
        x, y = attempt.x, attempt.y
        radius = hypot(x, y) if x is not None and y is not None else None
        dies.append(
            DieView(
                lot_id=outcome.lot_id,
                wafer_id=outcome.wafer_id,
                die_id=outcome.die_id,
                attempt_id=outcome.attempt_id,
                failed=outcome.first_pass_disposition == "FAIL",
                x=x,
                y=y,
                r=radius,
                tester_id=attempt.tester_id,
                probe_card_id=attempt.probe_card_id,
                temperature_c=attempt.temperature_c,
                timestamp=attempt.timestamp,
                failure_code=attempt.failure_code,
                primary_failure_code=outcome.primary_failure_code,
                primary_failure_family=outcome.primary_failure_family,
                primary_failure_detail=outcome.primary_failure_detail,
            )
        )
    return DetectorContext(
        dies=dies,
        attempts=attempts,
        test_results=tests,
        parametric=list(parametric or []),
        config=config,
        n_eligible=len(dies),
    )
