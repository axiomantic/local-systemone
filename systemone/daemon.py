"""Daemon & Service management for local-systemone (macOS launchd & Linux systemd).

The HTTP service holds the resident model; the MCP server is per-session and
cheap. To make the model truly "hot and ready" across reboots, keep the service
alive with a background user daemon.
"""
from __future__ import annotations

import os
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, Optional

LABEL = "com.axiomantic.local-systemone"
LEGACY_LABEL = "com.laya.service"
SYSTEMD_SERVICE_NAME = "local-systemone.service"
LEGACY_SYSTEMD_SERVICE = "laya-service.service"


# --- macOS launchd helpers ---

def plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def legacy_plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{LEGACY_LABEL}.plist"


def _launchd_log_dir() -> Path:
    return Path.home() / "Library" / "Logs" / "local-systemone"


def _env() -> Dict[str, str]:
    env = {
        "SYSTEMONE_PRELOAD": "1",
        "LAYA_PRELOAD": "1",
        "PATH": "/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:" + str(Path(sys.executable).parent),
    }
    for key in (
        "SYSTEMONE_ENGINE",
        "LAYA_ENGINE",
        "LAYA_DEVICE",
        "LAYA_PRELOAD_MODELS",
        "LAYA_AUTO_TASK_DETECTION",
        "OLLAMA_URL",
        "OLLAMA_MODEL",
        "OPENAI_BASE_URL",
        "OPENAI_MODEL",
        "UPSTREAM_URL",
        "UPSTREAM_API_KEY",
        "JEV_API_KEY",
        "HF_TOKEN",
        "PYTHONPATH",
    ):
        val = os.environ.get(key, "")
        if val:
            env[key] = val
    return env


def build_plist(host: str = "127.0.0.1", port: int = 8000, engine: Optional[str] = None) -> dict:
    log_dir = _launchd_log_dir()
    work_dir = Path(__file__).resolve().parent.parent

    args = [
        sys.executable,
        "-m",
        "systemone.server",
        "--host",
        host,
        "--port",
        str(port),
    ]
    if engine:
        args.extend(["--engine", engine])

    return {
        "Label": LABEL,
        "ProgramArguments": args,
        "RunAtLoad": True,
        "KeepAlive": True,
        "WorkingDirectory": str(work_dir),
        "EnvironmentVariables": _env(),
        "StandardOutPath": str(log_dir / "systemone.log"),
        "StandardErrorPath": str(log_dir / "systemone.err.log"),
        "ProcessType": "Background",
    }


def install_launchd(host: str = "127.0.0.1", port: int = 8000, engine: Optional[str] = None) -> None:
    if sys.platform != "darwin":
        raise SystemExit("launchd LaunchAgent support is macOS-only. Use systemd on Linux.")
    _launchd_log_dir().mkdir(parents=True, exist_ok=True)

    # Clean up legacy plist if present
    leg = legacy_plist_path()
    if leg.exists():
        subprocess.run(["launchctl", "unload", "-w", str(leg)], check=False, capture_output=True)

    target = plist_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(plistlib.dumps(build_plist(host, port, engine=engine)))
    subprocess.run(["launchctl", "unload", str(target)], check=False, capture_output=True)
    subprocess.run(["launchctl", "load", "-w", str(target)], check=True)
    print(f"✓ Installed and loaded launchd agent: {target}")
    print(f"  Check status: launchctl list {LABEL}")
    print(f"  Logs: {_launchd_log_dir()}/systemone.log")


def uninstall_launchd() -> None:
    if sys.platform != "darwin":
        raise SystemExit("launchd LaunchAgent support is macOS-only.")
    
    for path, lbl in ((plist_path(), LABEL), (legacy_plist_path(), LEGACY_LABEL)):
        if path.exists():
            subprocess.run(["launchctl", "unload", "-w", str(path)], check=False, capture_output=True)
            path.unlink()
            print(f"✓ Unloaded and removed launchd agent: {path}")


def status_launchd() -> bool:
    if sys.platform != "darwin":
        return False
    
    found = False
    for lbl in (LABEL, LEGACY_LABEL):
        res = subprocess.run(["launchctl", "list", lbl], capture_output=True, text=True)
        if res.returncode == 0:
            print(f"✓ {lbl} is loaded in launchd:")
            print(res.stdout.strip())
            found = True

    if not found:
        print(f"✗ Neither {LABEL} nor {LEGACY_LABEL} is loaded in launchd.")
    return found


# --- Linux systemd helpers ---

def systemd_user_unit_path() -> Path:
    return Path.home() / ".config" / "systemd" / "user" / SYSTEMD_SERVICE_NAME


def build_systemd_unit(host: str = "127.0.0.1", port: int = 8000, engine: Optional[str] = None, user_mode: bool = True) -> str:
    work_dir = Path(__file__).resolve().parent.parent
    env_lines = [
        "Environment=SYSTEMONE_PRELOAD=1",
        f'Environment="PATH=/usr/local/bin:/usr/bin:/bin:{Path(sys.executable).parent}"',
    ]
    for key in (
        "SYSTEMONE_ENGINE",
        "LAYA_ENGINE",
        "LAYA_DEVICE",
        "LAYA_PRELOAD_MODELS",
        "OLLAMA_URL",
        "OLLAMA_MODEL",
        "OPENAI_BASE_URL",
        "OPENAI_MODEL",
        "UPSTREAM_URL",
        "UPSTREAM_API_KEY",
        "JEV_API_KEY",
        "HF_TOKEN",
        "PYTHONPATH",
    ):
        val = os.environ.get(key, "")
        if val:
            env_lines.append(f'Environment="{key}={val}"')

    env_block = "\n".join(env_lines)
    working_dir_line = f"WorkingDirectory={work_dir}" if work_dir.exists() else ""
    target_target = "default.target" if user_mode else "multi-user.target"
    engine_flag = f" --engine {engine}" if engine else ""

    return f"""[Unit]
Description=Local System One Decision Service
Documentation=https://github.com/axiomantic/local-systemone
After=network.target

[Service]
Type=simple
{working_dir_line}
ExecStart={sys.executable} -m systemone.server --host {host} --port {port}{engine_flag}
Restart=always
RestartSec=3
{env_block}
StandardOutput=journal
StandardError=journal

[Install]
WantedBy={target_target}
"""


def install_systemd(host: str = "127.0.0.1", port: int = 8000, engine: Optional[str] = None) -> None:
    if sys.platform == "darwin":
        raise SystemExit("systemd is not available on macOS. Use launchd instead.")
    if not shutil.which("systemctl"):
        raise SystemExit("systemctl binary not found in PATH.")

    target = systemd_user_unit_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(build_systemd_unit(host, port, engine=engine, user_mode=True))

    subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
    subprocess.run(["systemctl", "--user", "enable", "--now", SYSTEMD_SERVICE_NAME], check=True)
    print(f"✓ Installed and enabled systemd user service: {target}")
    print(f"  Check status: systemctl --user status {SYSTEMD_SERVICE_NAME}")
    print(f"  Live logs: journalctl --user -u {SYSTEMD_SERVICE_NAME} -f")
    print("  Tip: Run `loginctl enable-linger $USER` to keep service active across logouts.")


def uninstall_systemd() -> None:
    target = systemd_user_unit_path()
    if shutil.which("systemctl"):
        for svc in (SYSTEMD_SERVICE_NAME, LEGACY_SYSTEMD_SERVICE):
            subprocess.run(["systemctl", "--user", "stop", svc], check=False, capture_output=True)
            subprocess.run(["systemctl", "--user", "disable", svc], check=False, capture_output=True)
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=False, capture_output=True)

    if target.exists():
        target.unlink()
        print(f"✓ Removed systemd user unit: {target}")
    else:
        print(f"No systemd unit found at {target}")


def status_systemd() -> bool:
    if not shutil.which("systemctl"):
        print("✗ systemctl not found.")
        return False
    res = subprocess.run(["systemctl", "--user", "status", SYSTEMD_SERVICE_NAME], capture_output=True, text=True)
    print(res.stdout.strip() if res.stdout else res.stderr.strip())
    return res.returncode == 0


# --- Unified cross-platform dispatchers ---

def install_daemon(host: str = "127.0.0.1", port: int = 8000, engine: Optional[str] = None) -> None:
    if sys.platform == "darwin":
        install_launchd(host, port, engine=engine)
    elif sys.platform.startswith("linux"):
        install_systemd(host, port, engine=engine)
    else:
        raise SystemExit(f"Unsupported operating system '{sys.platform}'. Please run via Docker or manual service.")


def uninstall_daemon() -> None:
    if sys.platform == "darwin":
        uninstall_launchd()
    elif sys.platform.startswith("linux"):
        uninstall_systemd()
    else:
        if plist_path().exists():
            uninstall_launchd()
        if systemd_user_unit_path().exists():
            uninstall_systemd()


def status_daemon() -> None:
    if sys.platform == "darwin":
        status_launchd()
    elif sys.platform.startswith("linux"):
        status_systemd()
    else:
        print(f"Unsupported operating system '{sys.platform}'.")