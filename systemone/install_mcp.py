"""Register the laya MCP server with supported code assistants.

This writes (or merges into) each assistant's MCP config so a stdio `laya-mcp`
server starts automatically and forwards `laya_choice` / `laya_score` /
`laya_noul` / `laya_system_one` tool calls to the running Laya HTTP service.

Run it from inside the laya-service venv so ``sys.executable`` resolves to the
interpreter that has ``laya_service`` (and the pinned ``mcp``) installed:

    laya-install-mcp
    laya-install-mcp --clients opencode,codex,claude,cursor,antigravity --dry-run
    laya-install-mcp --base-url https://laya.internal.example.com

It never deletes other servers: JSON targets are merged, the Codex TOML block is
appended only when absent, and Claude Code is configured through its own CLI.
Run with ``--dry-run`` first to see every path that would change.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable, Dict, List

DEFAULT_BASE_URL = os.environ.get("LAYA_BASE_URL", "http://127.0.0.1:8000").rstrip("/")


def _server(argv: List[str], base_url: str) -> Dict[str, object]:
    return {
        "command": argv[0],
        "args": argv[1:],
        "env": {"LAYA_BASE_URL": base_url},
    }


def _opencode_command(argv: List[str]) -> List[str]:
    return argv


def _merge_json(path: Path, updater: Callable[[Dict], None], dry_run: bool) -> None:
    if path.exists():
        try:
            data = json.loads(path.read_text())
        except json.JSONDecodeError:
            print(f"  ! {path} is not valid JSON (JSONC?) — skipped; edit it by hand")
            return
    else:
        data = {}
    updater(data)
    if dry_run:
        print(f"  would write {path}")
        print(f"    {json.dumps(data, indent=2)}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")
    print(f"  wrote {path}")


def _append_unique(path: Path, header: str, block: str, dry_run: bool) -> None:
    if path.exists() and header in path.read_text():
        print(f"  {path} already has {header} — untouched")
        return
    if dry_run:
        print(f"  would append to {path}:\n{block}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as fh:
        if path.exists() and not path.read_text().endswith("\n"):
            fh.write("\n")
        fh.write(block)
    print(f"  appended {header} to {path}")


def install_opencode(argv: List[str], base_url: str, dry_run: bool) -> None:
    cfg_home = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    path = cfg_home / "opencode" / "opencode.json"

    def updater(cfg: Dict) -> None:
        cfg.setdefault("mcp", {})["laya"] = {
            "type": "local",
            "command": _opencode_command(argv),
            "environment": {"LAYA_BASE_URL": base_url},
            "enabled": True,
        }

    _merge_json(path, updater, dry_run)


def install_codex(argv: List[str], base_url: str, dry_run: bool) -> None:
    codex = shutil.which("codex")
    if codex and not dry_run:
        subprocess.run(
            [
                codex,
                "mcp", "add", "laya",
                "--env", f"LAYA_BASE_URL={base_url}",
                "--", *argv,
            ],
            check=False,
        )
        print(f"  `codex mcp add laya` invoked")
        return

    path = Path.home() / ".codex" / "config.toml"
    header = "[mcp_servers.laya]"
    env_header = "[mcp_servers.laya.env]"
    block = (
        "\n"
        f"{header}\n"
        f'command = {json.dumps(argv[0])}\n'
        f"args = {json.dumps(argv[1:])}\n"
        "\n"
        f"{env_header}\n"
        f'LAYA_BASE_URL = {json.dumps(base_url)}\n'
    )
    _append_unique(path, header, block, dry_run)


def install_claude(argv: List[str], base_url: str, dry_run: bool) -> None:
    claude = shutil.which("claude")
    if not claude:
        print("  ! `claude` CLI not found; add by hand with `claude mcp add --scope user`")
        return
    cmd = [
        claude, "mcp", "add",
        "--env", f"LAYA_BASE_URL={base_url}",
        "--transport", "stdio",
        "laya",
        "--", *argv,
    ]
    if dry_run:
        print(f"  would run: {' '.join(cmd)}")
        return
    subprocess.run(cmd, check=False)
    print("  `claude mcp add laya` invoked (user scope)")


def install_cursor(argv: List[str], base_url: str, dry_run: bool) -> None:
    path = Path.home() / ".cursor" / "mcp.json"

    def updater(cfg: Dict) -> None:
        cfg.setdefault("mcpServers", {})["laya"] = _server(argv, base_url)

    _merge_json(path, updater, dry_run)
    print("  (if Cursor does not pick this up, add it in Settings > MCP: "
          f"command `{' '.join(argv)}` with LAYA_BASE_URL={base_url})")


def install_antigravity(argv: List[str], base_url: str, dry_run: bool) -> None:
    path = Path.home() / ".gemini" / "config" / "mcp_config.json"

    def updater(cfg: Dict) -> None:
        cfg.setdefault("mcpServers", {})["laya"] = _server(argv, base_url)

    _merge_json(path, updater, dry_run)


CLIENTS: Dict[str, Callable[[List[str], str, bool], None]] = {
    "opencode": install_opencode,
    "codex": install_codex,
    "claude": install_claude,
    "cursor": install_cursor,
    "antigravity": install_antigravity,
}


def main() -> None:
    parser = argparse.ArgumentParser(prog="laya-install-mcp")
    parser.add_argument(
        "--clients",
        default=",".join(CLIENTS),
        help="comma list of clients to install: " + ", ".join(CLIENTS),
    )
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Laya service URL")
    parser.add_argument("--dry-run", action="store_true", help="print changes without writing")
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    argv = [sys.executable, "-m", "laya_service.mcp_server"]

    selected = [c.strip() for c in args.clients.split(",") if c.strip()]
    unknown = [c for c in selected if c not in CLIENTS]
    if unknown:
        parser.error(f"unknown client(s): {', '.join(unknown)}")

    print(f"laya MCP entry: {argv[0]} {' '.join(argv[1:])}")
    print(f"LAYA_BASE_URL = {base_url}")
    print(f"mode: {'dry-run' if args.dry_run else 'write'}\n")
    for name in selected:
        print(f"[{name}]")
        CLIENTS[name](argv, base_url, args.dry_run)
        print()


if __name__ == "__main__":
    main()