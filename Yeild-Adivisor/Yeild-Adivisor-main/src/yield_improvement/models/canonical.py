"""Canonical V1 row types. Grain of DieAttempt: unique die × attempt."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

PART_CLASSES = (
    "PRODUCTION",
    "ENGINEERING",
    "CALIBRATION",
    "QA_SAMPLE",
    "REWORK",
    "UNKNOWN",
)

PASS_FAIL = ("PASS", "FAIL")
TEST_PASS_FAIL = ("PASS", "FAIL", "NOT_EXECUTED", "INVALID")
ATTRIBUTION_ROLES = ("PRIMARY", "COFAIL")
EQUIPMENT_TYPES = (
    "TESTER",
    "PROBER",
    "PROBE_CARD",
    "HANDLER",
    "LOAD_BOARD",
    "PROCESS_TOOL",
    "OTHER",
)


class CanonicalModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Lot(CanonicalModel):
    lot_id: str
    product_id: str
    step_id: str
    start_ts: datetime | None = None
    quantity_declared: int | None = None
    hold_flag: bool | None = None


class Wafer(CanonicalModel):
    lot_id: str
    wafer_id: str
    slot: int | None = None
    process_tool_id: str | None = None
    process_chamber_id: str | None = None
    start_ts: datetime | None = None


class Part(CanonicalModel):
    lot_id: str
    wafer_id: str
    die_id: str
    product_id: str
    part_class: str | None = None
    x: float | None = None
    y: float | None = None
    site: int | None = None
    is_rework: bool | None = None
    is_engineering: bool | None = None
    is_calibration: bool | None = None


class DieAttempt(CanonicalModel):
    """Primary analytical fact: one physical die × one ATE attempt."""

    attempt_id: str
    lot_id: str
    wafer_id: str
    die_id: str
    product_id: str
    step_id: str
    part_class: str | None = None
    timestamp: datetime | None = None
    attempt_number: int | None = None
    is_first_attempt: bool | None = None
    is_retest: bool | None = None
    is_rework: bool | None = None
    abort_flag: bool = False
    disposition: str | None = None
    pass_fail: str | None = None
    sbin: int | None = None
    hbin: int | None = None
    failure_code: str | None = None
    tester_id: str | None = None
    probe_card_id: str | None = None
    prober_id: str | None = None
    site: int | None = None
    temperature_c: float | None = None
    voltage_v: float | None = None
    record_status: str | None = None
    x: float | None = None
    y: float | None = None
    source_row: int | None = None

    def die_key(self) -> tuple[str, str, str]:
        return (self.lot_id, self.wafer_id, self.die_id)


class TestResult(CanonicalModel):
    """Per-test result on one attempt. __test__ False: pytest must not collect this model."""

    __test__ = False
    attempt_id: str
    test_id: str
    test_pass_fail: str
    sequence_index: int | None = None
    is_first_fail: bool | None = None
    failure_code: str | None = None
    source_row: int | None = None


class Failure(CanonicalModel):
    lot_id: str
    wafer_id: str
    die_id: str
    attempt_id: str
    attribution_role: Literal["PRIMARY", "COFAIL"]
    failure_key: str
    taxonomy_code: str
    failure_code: str | None = None
    sbin: int | None = None
    test_id: str | None = None
    selection_method: str | None = None


class ParametricMeasurement(CanonicalModel):
    attempt_id: str
    parameter_name: str
    condition_id: str = "NONE"
    measurement: float
    lower_limit: float | None = None
    upper_limit: float | None = None
    unit: str | None = None
    pass_fail: str | None = None
    temperature_c: float | None = None
    voltage_v: float | None = None


class Equipment(CanonicalModel):
    equipment_id: str
    equipment_type: str
    parent_equipment_id: str | None = None
    vendor: str | None = None
    model: str | None = None
