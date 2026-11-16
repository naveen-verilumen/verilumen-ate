"""Deterministic cell parsing. Empty / NA → None. No silent numeric invention."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

_MISSING_STRINGS = {"", "nan", "none", "null", "na", "<na>"}


def is_missing(value: Any) -> bool:
    if value is None:
        return True
    try:
        import math

        if isinstance(value, float) and math.isnan(value):
            return True
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    return text.lower() in _MISSING_STRINGS


def as_optional_str(value: Any) -> str | None:
    if is_missing(value):
        return None
    text = str(value).strip()
    return text if text else None


def as_optional_bool(value: Any) -> bool | None:
    if is_missing(value):
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "y"}:
        return True
    if text in {"false", "0", "no", "n"}:
        return False
    return None  # invalid, caller flags


def as_optional_int(value: Any) -> int | None:
    if is_missing(value):
        return None
    if isinstance(value, bool):
        return None
    try:
        if isinstance(value, float):
            if value != int(value):
                return None
            return int(value)
        text = str(value).strip()
        return int(float(text)) if "." in text else int(text)
    except (TypeError, ValueError):
        return None


def as_optional_float(value: Any) -> float | None:
    if is_missing(value):
        return None
    if isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def as_optional_datetime(value: Any) -> datetime | None:
    if is_missing(value):
        return None
    if isinstance(value, datetime):
        ts = value
        if ts.tzinfo is None:
            return ts.replace(tzinfo=timezone.utc)
        return ts.astimezone(timezone.utc)
    text = str(value).strip()
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        ts = datetime.fromisoformat(text)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return ts.astimezone(timezone.utc)
    except ValueError:
        return None
