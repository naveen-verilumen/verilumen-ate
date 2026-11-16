"""ML configuration. Loaded separately from AppConfig so Phase 1–6 YAML stay frozen."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

from yield_improvement.utils.errors import ConfigError, YieldImprovementError
from yield_improvement.utils.paths import configs_dir


class LeakageError(YieldImprovementError):
    """Forbidden or unknown feature detected. Fail closed."""


class Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SplitCfg(Frozen):
    strategy: str
    group_column: str
    max_lolo_lots: int
    fallback_group_kfold_splits: int


class ModelLogistic(Frozen):
    class_weight: str
    max_iter: int


class ModelRF(Frozen):
    n_estimators: int
    min_samples_leaf: int
    class_weight: str
    max_depth: int


class ModelHGB(Frozen):
    max_depth: int
    learning_rate: float
    max_iter: int
    min_samples_leaf: int


class ModelsCfg(Frozen):
    logistic: ModelLogistic
    random_forest: ModelRF
    hist_gbm: ModelHGB


class SelectionCfg(Frozen):
    primary_metric: str
    tie_break_metric: str
    prefer_simpler_if_close: bool
    close_tolerance: float


class ImbalanceCfg(Frozen):
    method: str
    oversample: bool


class CalibrationCfg(Frozen):
    method: str
    min_train_lots: int


class EvidenceCfg(Frozen):
    role: str
    independent_of_matching_detector: bool
    min_importance_rank: int
    min_rate_delta: float
    top_risk_fraction: float
    do_not_create_hypothesis_without_statistical_signal: bool


class MLAppConfig(Frozen):
    ml_version: str
    feature_set_version: str
    calibration_version: str
    status: str
    seed: int
    split: SplitCfg
    models: ModelsCfg
    selection: SelectionCfg
    imbalance: ImbalanceCfg
    calibration: CalibrationCfg
    evidence: EvidenceCfg
    limitations: list[str] = Field(default_factory=list)


class FeaturePolicy(Frozen):
    allowlist_version: str
    allowed_input_columns: list[str]
    allowed_derived_features: list[str]
    denied_columns: list[str]


def _load(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ConfigError(f"Missing {path}")
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ConfigError(f"{path} must be a mapping")
    return payload


def load_ml_config(config_dir: Path | None = None) -> MLAppConfig:
    directory = Path(config_dir) if config_dir is not None else configs_dir()
    try:
        return MLAppConfig.model_validate(_load(directory / "ml.yaml"))
    except Exception as exc:  # noqa: BLE001
        raise ConfigError(f"Invalid ml.yaml: {exc}") from exc


def load_feature_policy(config_dir: Path | None = None) -> FeaturePolicy:
    directory = Path(config_dir) if config_dir is not None else configs_dir()
    try:
        return FeaturePolicy.model_validate(_load(directory / "ml_feature_allowlist.yaml"))
    except Exception as exc:  # noqa: BLE001
        raise ConfigError(f"Invalid ml_feature_allowlist.yaml: {exc}") from exc
