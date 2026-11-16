"""Load configs/synthetic.yaml. Separate from agent AppConfig."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from yield_improvement.utils.errors import ConfigError
from yield_improvement.utils.paths import configs_dir


class Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Profile(Frozen):
    n_lots: int
    n_wafers_per_lot: int
    grid_side: int
    n_dies_per_wafer: int
    wafer_radius: float

    @field_validator("n_lots", "n_wafers_per_lot", "grid_side", "n_dies_per_wafer")
    @classmethod
    def _positive(cls, value: int) -> int:
        if value < 1:
            raise ValueError("profile counts must be >= 1")
        return value


class Baseline(Frozen):
    p_fail: float
    lot_effect_sd: float
    wafer_effect_sd: float
    die_noise_sd: float
    tester_effect_sd: float
    measurement_noise_sd: float
    expected_fpy_min: float
    expected_fpy_max: float
    abort_rate: float = 0.0
    assumptions: list[str] = Field(default_factory=list)


class ProgramTest(Frozen):
    """ATE program step. __test__ False so pytest does not collect this model."""

    __test__ = False
    test_id: str
    sequence_index: int
    failure_code: str
    sbin: int


class ParamDef(Frozen):
    unit: str
    lower_limit: float | None = None
    upper_limit: float | None = None
    pass_mean: float
    pass_sd: float


class TimeCfg(Frozen):
    start: str
    seconds_per_die: int
    hours_per_wafer: int
    days_per_lot: int


class SanityCfg(Frozen):
    min_rate_delta: float = 0.05


class HardOptions(Frozen):
    """Optional harder experiments. Default off; not applied unless enabled."""

    enabled: bool = False
    weak_signal: bool = False
    strong_noise: bool = False
    small_affected_population: bool = False
    unequal_lot_sizes: bool = False
    unequal_equipment_utilization: bool = False
    missing_optional_fields: bool = False
    confounded_variables: bool = False
    multiple_simultaneous_effects: bool = False


class SyntheticConfig(Frozen):
    generator_version: str
    active_profile: str
    seed: int
    product_id: str
    step_id: str
    profiles: dict[str, Profile]
    testers: list[str]
    tester_weights: list[float]
    probe_cards: list[str]
    temperatures_c: list[float]
    sites: list[int]
    baseline: Baseline
    tests: list[ProgramTest]
    parametric: dict[str, ParamDef]
    hbin_pass: int
    hbin_fail: int
    sbin_pass: int
    time: TimeCfg
    scenarios: dict[str, dict[str, Any]]
    sanity: SanityCfg
    hard_options: HardOptions = Field(default_factory=HardOptions)

    @field_validator("tester_weights")
    @classmethod
    def _weights(cls, value: list[float]) -> list[float]:
        if abs(sum(value) - 1.0) > 1e-6:
            raise ValueError("tester_weights must sum to 1")
        return value

    @model_validator(mode="after")
    def _testers_match_weights(self) -> SyntheticConfig:
        if len(self.testers) != len(self.tester_weights):
            raise ValueError("testers and tester_weights must have the same length")
        return self

    def profile(self, name: str | None = None) -> Profile:
        key = name or self.active_profile
        if key not in self.profiles:
            raise ConfigError(f"Unknown synthetic profile {key!r}")
        return self.profiles[key]


def load_synthetic_config(path: Path | None = None) -> SyntheticConfig:
    file_path = path or (configs_dir() / "synthetic.yaml")
    if not file_path.is_file():
        raise ConfigError(f"Missing {file_path}")
    payload = yaml.safe_load(file_path.read_text(encoding="utf-8"))
    try:
        return SyntheticConfig.model_validate(payload)
    except Exception as exc:  # noqa: BLE001
        raise ConfigError(f"Invalid synthetic.yaml: {exc}") from exc
