"""Display formatting only. Does not calculate FPY, scores, or opportunity."""

from __future__ import annotations


def format_rate(value: float | None) -> str:
    if value is None:
        return "Unavailable"
    return f"{100.0 * value:.2f}%"


def format_count(value: int | None) -> str:
    if value is None:
        return "Unavailable"
    return str(value)


def format_plausible(rate: float | None, unavailable: bool) -> str:
    if unavailable or rate is None:
        return "Not estimable"
    return f"{format_rate(rate)} (PRELIMINARY / CALIBRATION-DEPENDENT)"


def format_bool(value: bool) -> str:
    return "YES" if value else "NO"
