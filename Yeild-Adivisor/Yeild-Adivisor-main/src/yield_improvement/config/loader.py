"""Load and validate YAML configuration from configs/."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from yield_improvement.config.schemas import (
    AllowlistConfig,
    BinMapConfig,
    CalibrationConfig,
    FpyPolicy,
    SafetyConfig,
    TaxonomyConfig,
)
from yield_improvement.utils.errors import ConfigError
from yield_improvement.utils.paths import configs_dir

_FILE_MODELS: dict[str, type] = {
    "fpy_policy.yaml": FpyPolicy,
    "taxonomy.yaml": TaxonomyConfig,
    "bin_map.yaml": BinMapConfig,
    "safety_policy.yaml": SafetyConfig,
    "calibration.yaml": CalibrationConfig,
    "allowlist.yaml": AllowlistConfig,
}


class AppConfig:
    """Validated configuration bundle. Policy values live in YAML, not code defaults."""

    def __init__(
        self,
        *,
        fpy: FpyPolicy,
        taxonomy: TaxonomyConfig,
        bin_map: BinMapConfig,
        safety: SafetyConfig,
        calibration: CalibrationConfig,
        allowlist: AllowlistConfig,
        config_dir: Path,
    ) -> None:
        self.fpy = fpy
        self.taxonomy = taxonomy
        self.bin_map = bin_map
        self.safety = safety
        self.calibration = calibration
        self.allowlist = allowlist
        self.config_dir = config_dir
        self._cross_validate()

    def _cross_validate(self) -> None:
        allowed = self.taxonomy.allowed_codes()
        for code in self.bin_map.failure_code_map.values():
            if code not in allowed:
                raise ConfigError(f"bin_map failure_code_map taxonomy {code!r} not in taxonomy")
        unknown_sbin = self.bin_map.unmapped_behavior.unknown_sbin
        if unknown_sbin not in allowed:
            raise ConfigError(f"unmapped sbin taxonomy {unknown_sbin!r} not in taxonomy")
        if self.fpy.insertion != "WAFER_SORT":
            raise ConfigError("V1 insertion must be WAFER_SORT")
        if self.safety.safety_eligible_production.value != 0.0:
            raise ConfigError("safety_eligible_production must be 0")
        invoked = self.allowlist.potential_specialist_investigation or {}
        if invoked.get("invoked") is True:
            raise ConfigError("allowlist invoked must be false")


# AppConfig defined as class above — cannot also be in schemas as pydantic model
# with same name. schemas.AppConfig was referenced; keep only this class.

def _read_yaml(path: Path) -> Any:
    if not path.is_file():
        raise ConfigError(f"Missing configuration file: {path}")
    try:
        with path.open(encoding="utf-8") as handle:
            payload = yaml.safe_load(handle)
    except yaml.YAMLError as exc:
        raise ConfigError(f"Malformed YAML {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ConfigError(f"Configuration {path} must be a mapping")
    return payload


def load_yaml_model(path: Path, model: type) -> Any:
    payload = _read_yaml(path)
    try:
        return model.model_validate(payload)
    except ValidationError as exc:
        raise ConfigError(f"Invalid configuration {path.name}: {exc}") from exc


def load_config(config_dir: Path | None = None) -> AppConfig:
    directory = Path(config_dir) if config_dir is not None else configs_dir()
    if not directory.is_dir():
        raise ConfigError(f"Config directory does not exist: {directory}")
    loaded: dict[str, Any] = {}
    for filename, model in _FILE_MODELS.items():
        loaded[filename] = load_yaml_model(directory / filename, model)
    return AppConfig(
        fpy=loaded["fpy_policy.yaml"],
        taxonomy=loaded["taxonomy.yaml"],
        bin_map=loaded["bin_map.yaml"],
        safety=loaded["safety_policy.yaml"],
        calibration=loaded["calibration.yaml"],
        allowlist=loaded["allowlist.yaml"],
        config_dir=directory,
    )
