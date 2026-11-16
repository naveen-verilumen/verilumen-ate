"""Artifact hashing. Champion directory is never rewritten by lifecycle writes."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

from yield_improvement.model_lifecycle.states import LifecycleError

CHAMPION_FILES = ("model.pkl", "metadata.json", "feature_list.json", "metrics.json")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def hash_files(folder: Path, names: Iterable[str] = CHAMPION_FILES) -> dict[str, str]:
    out: dict[str, str] = {}
    for name in names:
        path = folder / name
        if not path.is_file():
            raise LifecycleError(f"artifact missing: {path}")
        out[name] = sha256_file(path)
    return out


def hash_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def json_safe(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {str(k): json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [json_safe(v) for v in obj]
    if isinstance(obj, float) and (obj != obj or obj in {float("inf"), float("-inf")}):
        return None
    try:
        import numpy as np

        if isinstance(obj, np.ndarray):
            return json_safe(obj.tolist())
        if isinstance(obj, (np.floating, np.integer, np.bool_)):
            val = obj.item()
            return json_safe(val) if isinstance(val, float) else val
    except ImportError:
        pass
    return obj


def dumps(payload: dict[str, Any]) -> str:
    return json.dumps(json_safe(payload), indent=2, sort_keys=True) + "\n"


def assert_hashes_match(expected: dict[str, str], actual: dict[str, str], *, label: str) -> None:
    if expected != actual:
        raise LifecycleError(f"artifact hash mismatch for {label}: expected {expected} vs actual {actual}")
