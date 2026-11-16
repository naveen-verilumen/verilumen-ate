"""Agent-level errors. Data-quality problems use structured issues, not these."""


class YieldImprovementError(Exception):
    """Base error for programming / configuration failures."""


class ConfigError(YieldImprovementError):
    """Malformed or missing configuration."""


class LoadError(YieldImprovementError):
    """Unreadable source file (I/O), not a row-level data-quality issue."""
