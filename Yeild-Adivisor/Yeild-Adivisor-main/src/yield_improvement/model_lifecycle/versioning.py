"""Deterministic model version names. Versions are never reused."""

from __future__ import annotations

import re

from yield_improvement.model_lifecycle.states import LifecycleError

CHAMPION_RE = re.compile(r"^yi_ml_v(\d+)$")
CANDIDATE_RE = re.compile(r"^yi_ml_v(\d+)_candidate_(\d{3})$")
ANY_VERSION_RE = re.compile(
    r"^yi_ml_v(\d+)(?:_(?!candidate(?:_|$))([a-z0-9]+))?(?:_candidate_(\d{3}))?$"
)

CHAMPION_ARCHITECTURE = "logistic_regression"
APPROVED_ARCHITECTURE = "logistic"


def parse_version(version: str) -> dict[str, int | str | bool | None]:
    match = ANY_VERSION_RE.fullmatch(version)
    if not match:
        raise LifecycleError(
            f"invalid model_version {version!r}. Expected yi_ml_vN, yi_ml_vN_<label>, or yi_ml_vN_candidate_NNN"
        )
    major = int(match.group(1))
    label = match.group(2)
    seq = int(match.group(3)) if match.group(3) is not None else None
    return {
        "major": major,
        "seq": seq,
        "label": label,
        "is_candidate": seq is not None,
    }


def next_candidate_version(existing: list[str], *, champion_version: str) -> str:
    champ = parse_version(champion_version)
    if champ["is_candidate"]:
        raise LifecycleError("champion_version must be yi_ml_vN, not a candidate id")
    next_major = int(champ["major"]) + 1
    used = []
    for version in existing:
        parsed = parse_version(version)
        if parsed["is_candidate"] and parsed["major"] == next_major:
            used.append(int(parsed["seq"]))
    seq = (max(used) + 1) if used else 1
    if seq > 999:
        raise LifecycleError("candidate sequence overflow")
    return f"yi_ml_v{next_major}_candidate_{seq:03d}"


def assert_unused(version: str, existing: list[str]) -> None:
    if version in existing:
        raise LifecycleError(f"duplicate model version: {version}")
