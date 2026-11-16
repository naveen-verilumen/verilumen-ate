"""Path helpers. Never read evaluation/ground_truth from agent code."""

from __future__ import annotations

from pathlib import Path

from yield_improvement.utils.errors import ConfigError


def repo_root() -> Path:
    """Locate the repository root by finding configs/fpy_policy.yaml."""
    here = Path(__file__).resolve()
    for candidate in [here, *here.parents]:
        if (candidate / "configs" / "fpy_policy.yaml").exists():
            return candidate
    cwd = Path.cwd().resolve()
    for candidate in [cwd, *cwd.parents]:
        if (candidate / "configs" / "fpy_policy.yaml").exists():
            return candidate
    raise ConfigError("Cannot find configs/fpy_policy.yaml from package or cwd.")


def configs_dir() -> Path:
    return repo_root() / "configs"


def fixtures_fpy_dir() -> Path:
    return repo_root() / "tests" / "fixtures" / "fpy"


def active_synthetic_dir() -> Path:
    """Current production synthetic dataset root (V2 only after Phase 11A)."""
    return repo_root() / "data" / "synthetic" / "agent_visible"


def phase2_agent_visible_dir() -> Path:
    """Archived S01–S16 agent-visible data. Not listed in the production selector."""
    archived = repo_root() / "tests" / "fixtures" / "synthetic_v1" / "agent_visible"
    if archived.is_dir():
        return archived
    return repo_root() / "data" / "synthetic" / "agent_visible"


def phase2_monitoring_dir() -> Path:
    """Archived monitoring currents. Not listed in the production selector."""
    archived = repo_root() / "tests" / "fixtures" / "synthetic_v1" / "monitoring" / "agent_visible"
    if archived.is_dir():
        return archived
    return repo_root() / "data" / "synthetic" / "monitoring" / "agent_visible"


def v1_dataset_dir(dataset_id: str) -> Path:
    return phase2_agent_visible_dir() / dataset_id


def v1_monitoring_dir(dataset_id: str) -> Path:
    return phase2_monitoring_dir() / dataset_id
