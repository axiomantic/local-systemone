from __future__ import annotations

import plistlib
from pathlib import Path

from systemone.daemon import LABEL, SYSTEMD_SERVICE_NAME, build_plist, build_systemd_unit


def test_build_plist_structure():
    plist = build_plist(host="127.0.0.1", port=8100, engine="laya")
    assert plist["Label"] == LABEL
    assert plist["RunAtLoad"] is True
    assert plist["KeepAlive"] is True
    assert "systemone.server" in plist["ProgramArguments"]
    assert "--host" in plist["ProgramArguments"]
    assert "127.0.0.1" in plist["ProgramArguments"]
    assert "--port" in plist["ProgramArguments"]
    assert "8100" in plist["ProgramArguments"]
    assert "--engine" in plist["ProgramArguments"]
    assert "laya" in plist["ProgramArguments"]
    assert "SYSTEMONE_PRELOAD" in plist["EnvironmentVariables"]

    # Verify plist serializability
    data = plistlib.dumps(plist)
    assert len(data) > 0
    loaded = plistlib.loads(data)
    assert loaded["Label"] == LABEL


def test_build_systemd_unit_structure():
    unit = build_systemd_unit(host="127.0.0.1", port=8100, engine="ollama", user_mode=True)
    assert "[Unit]" in unit
    assert "Description=Local System One Decision Service" in unit
    assert "[Service]" in unit
    assert "ExecStart=" in unit
    assert "-m systemone.server --host 127.0.0.1 --port 8100 --engine ollama" in unit
    assert "Restart=always" in unit
    assert "Environment=SYSTEMONE_PRELOAD=1" in unit
    assert "[Install]" in unit
    assert "WantedBy=default.target" in unit

    # System-wide variant
    sys_unit = build_systemd_unit(host="0.0.0.0", port=9000, user_mode=False)
    assert "--host 0.0.0.0 --port 9000" in sys_unit
    assert "WantedBy=multi-user.target" in sys_unit
