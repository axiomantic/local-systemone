"""launchd (macOS) LaunchAgent management for the Laya service.

The HTTP service holds the resident model; the MCP server is per-session and
cheap. To make the model truly "hot and ready" across reboots, keep the service
alive with a user LaunchAgent. Only macOS (Darwin) is supported — on other
platforms use Docker instead.
"""
from __future__ import annotations

import os
import plistlib
import subprocess
import sys
from pathlib import Path

LABEL = "com.laya.service"


def plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def _log_dir() -> Path:
    return Path.home() / "Library" / "Logs" / "laya-service"


def _env() -> dict:
    env = {
        "LAYA_PRELOAD": "1",
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin:" + str(Path(sys.executable).parent),
    }
    for key in ("LAYA_DEVICE", "LAYA_PRELOAD_MODELS", "LAYA_AUTO_TASK_DETECTION", "HF_TOKEN"):
        val = os.environ.get(key, "")
        if val:
            env[key] = val
    return env


def build_plist(host: str, port: int) -> dict:
    log_dir = _log_dir()
    return {
        "Label": LABEL,
        "ProgramArguments": [
            sys.executable, "-m", "laya_service.server", "--host", host, "--port", str(port),
        ],
        "RunAtLoad": True,
        "KeepAlive": True,
        "WorkingDirectory": str(Path(__file__).resolve().parent.parent),
        "EnvironmentVariables": _env(),
        "StandardOutPath": str(log_dir / "laya-service.log"),
        "StandardErrorPath": str(log_dir / "laya-service.err.log"),
        "ProcessType": "Background",
    }


def _require_darwin() -> None:
    if sys.platform != "darwin":
        raise SystemExit("launchd LaunchAgent support is macOS-only. Use Docker instead.")


def install_daemon(host: str, port: int) -> None:
    _require_darwin()
    _log_dir().mkdir(parents=True, exist_ok=True)
    target = plist_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(plistlib.dumps(build_plist(host, port)))
    subprocess.run(["launchctl", "unload", str(target)], check=False)
    subprocess.run(["launchctl", "load", "-w", str(target)], check=True)
    print(f"installed and loaded {target} (see `launchctl list {LABEL}`)")


def uninstall_daemon() -> None:
    _require_darwin()
    target = plist_path()
    if target.exists():
        subprocess.run(["launchctl", "unload", "-w", str(target)], check=False)
        target.unlink()
        print(f"unloaded and removed {target}")
    else:
        print(f"no LaunchAgent at {target}")