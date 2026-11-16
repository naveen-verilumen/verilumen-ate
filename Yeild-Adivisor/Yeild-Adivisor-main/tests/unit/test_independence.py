"""No executable dependency on other semiconductor agents."""

from __future__ import annotations

from pathlib import Path

from yield_improvement.utils.paths import repo_root

FORBIDDEN_IMPORTS = (
    "dtl_agent",
    "import dtl\n",
    "from dtl ",
    "false_failure",
    "retest_reduction",
    "escape_prevention",
)


def test_no_forbidden_imports_in_src():
    src = repo_root() / "src"
    hits: list[str] = []
    for path in src.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for token in FORBIDDEN_IMPORTS:
            if token in text:
                hits.append(f"{path}: {token}")
    assert hits == []


def test_allowlist_invoked_false(config):
    spec = config.allowlist.potential_specialist_investigation or {}
    assert spec.get("invoked") is False
    assert config.safety.potential_specialist_investigation.invoked is False
