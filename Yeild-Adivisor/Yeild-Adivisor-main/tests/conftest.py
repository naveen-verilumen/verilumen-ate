from __future__ import annotations

import json
from pathlib import Path

import pytest

from yield_improvement.config import load_config
from yield_improvement.pipeline import run_fixture_dir
from yield_improvement.utils.paths import fixtures_fpy_dir, repo_root


@pytest.fixture(scope="session")
def config():
    return load_config()


@pytest.fixture(scope="session")
def fpy_fixtures() -> Path:
    return fixtures_fpy_dir()


def load_expected(case_dir: Path) -> dict:
    path = case_dir / "expected.json"
    return json.loads(path.read_text(encoding="utf-8"))


def case_dirs() -> list[Path]:
    root = repo_root() / "tests" / "fixtures" / "fpy"
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    return [root / item["dir"] for item in manifest["cases"]]
