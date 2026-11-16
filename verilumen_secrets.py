"""
Verilumen ATE Credential Manager Helper
=======================================
Stores and retrieves per-install API secrets (such as SHMOO_API_KEY) using
Windows Credential Manager via `keyring`, with environment variable precedence
for MCP adapter subprocesses launched from `mcp_config.json`.
"""

from __future__ import annotations

import json
import os
import secrets
from pathlib import Path
from typing import Iterable

KEYRING_SERVICE = "verilumen-ate"
SHMOO_KEYRING_USERNAME = "shmoo_api_key"


def get_shmoo_api_key(*, create_if_missing: bool = False) -> str:
    """
    Resolve SHMOO_API_KEY in strict order:
      1. `SHMOO_API_KEY` environment variable (injected via mcp_config.json `env`)
      2. `API_KEY` environment variable (Shmoo ML Flask service override)
      3. Windows Credential Manager entry (`verilumen-ate` / `shmoo_api_key`)
      4. If `create_if_missing=True`, generate a random 32-byte token and store it
         in Windows Credential Manager.
    """
    for env_name in ("SHMOO_API_KEY", "API_KEY"):
        val = os.environ.get(env_name, "").strip()
        if val:
            return val

    import keyring

    stored = keyring.get_password(KEYRING_SERVICE, SHMOO_KEYRING_USERNAME)
    if stored and stored.strip():
        return stored.strip()

    if not create_if_missing:
        raise RuntimeError(
            "SHMOO_API_KEY is not configured in environment or Windows Credential Manager. "
            "Run `python verilumen_secrets.py --init` or configure mcp_config.json env."
        )

    token = secrets.token_urlsafe(32)
    keyring.set_password(KEYRING_SERVICE, SHMOO_KEYRING_USERNAME, token)
    return token


def rotate_shmoo_api_key() -> str:
    """Generate a fresh random per-install token and overwrite Credential Manager."""
    import keyring

    token = secrets.token_urlsafe(32)
    keyring.set_password(KEYRING_SERVICE, SHMOO_KEYRING_USERNAME, token)
    return token


def sync_mcp_config_files(root_dir: Path, token: str, python_exe: str | None = None) -> list[Path]:
    """
    Write or update `mcp_config.json` and `.cursor/mcp.json` under `root_dir`
    so the `verilumen-ate` MCP adapter receives `SHMOO_API_KEY` in its `env` block.
    """
    root_dir = Path(root_dir).resolve()
    server_script = str(root_dir / "mcp_server.py")
    cmd = python_exe or os.environ.get("PYTHON") or os.sys.executable

    updated: list[Path] = []
    targets: Iterable[Path] = (
        root_dir / "mcp_config.json",
        root_dir / ".cursor" / "mcp.json",
    )
    for cfg_path in targets:
        cfg_path.parent.mkdir(parents=True, exist_ok=True)
        data: dict = {}
        if cfg_path.is_file():
            try:
                loaded = json.loads(cfg_path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    data = loaded
            except Exception:
                data = {}
        servers = data.setdefault("mcpServers", {})
        entry = servers.get("verilumen-ate", {}) if isinstance(servers, dict) else {}
        if not isinstance(entry, dict):
            entry = {}
        entry.setdefault("command", cmd)
        entry.setdefault("args", [server_script])
        env_block = entry.get("env")
        if not isinstance(env_block, dict):
            env_block = {}
        env_block["SHMOO_API_KEY"] = token
        entry["env"] = env_block
        servers["verilumen-ate"] = entry
        cfg_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        updated.append(cfg_path)
    return updated


def main() -> int:
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Provision Verilumen ATE secrets in Windows Credential Manager.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--init", action="store_true", help="Provision per-install SHMOO_API_KEY if absent and sync MCP config files.")
    group.add_argument("--rotate", action="store_true", help="Rotate SHMOO_API_KEY in Windows Credential Manager and re-sync MCP config files.")
    group.add_argument("--check", action="store_true", help="Verify secret presence (does not print secret).")
    args = parser.parse_args()

    root = Path(__file__).resolve().parent
    if args.check:
        try:
            tok = get_shmoo_api_key(create_if_missing=False)
            print(f"OK: SHMOO_API_KEY present (length={len(tok)}, backend=Windows Credential Manager / env)")
            return 0
        except Exception as exc:
            print(f"MISSING: {exc}", file=sys.stderr)
            return 1

    token = rotate_shmoo_api_key() if args.rotate else get_shmoo_api_key(create_if_missing=True)
    paths = sync_mcp_config_files(root, token)
    print(f"Provisioned SHMOO_API_KEY in Windows Credential Manager ({KEYRING_SERVICE}/{SHMOO_KEYRING_USERNAME}).")
    for p in paths:
        print(f"Updated MCP env block in: {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
