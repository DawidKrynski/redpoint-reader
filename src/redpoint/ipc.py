"""Single-instance IPC. The client side has no Qt import so `redpoint --read` starts fast."""

from __future__ import annotations

import getpass
import json
import os
import re
import socket
import sys
import tempfile


def _user() -> str:
    try:
        name = getpass.getuser()
    except Exception:  # noqa: BLE001 - any failure falls back to a fixed name
        name = "user"
    return re.sub(r"[^A-Za-z0-9_.-]", "_", name) or "user"


def server_name() -> str:
    """Name passed to QLocalServer.listen()."""
    override = os.environ.get("REDPOINT_SOCKET")
    if override:
        return override
    if sys.platform == "win32":
        return f"redpoint-{_user()}"
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    if runtime and os.path.isdir(runtime):
        return os.path.join(runtime, "redpoint.sock")
    return os.path.join(tempfile.gettempdir(), f"redpoint-{_user()}.sock")


def send(message: dict, timeout: float = 2.0) -> bool:
    data = json.dumps(message).encode("utf-8") + b"\n"
    name = server_name()
    if sys.platform == "win32":
        try:
            with open(rf"\\.\pipe\{name}", "wb", buffering=0) as pipe:
                pipe.write(data)
            return True
        except OSError:
            return False
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            s.connect(name)
            s.sendall(data)
        return True
    except OSError:
        return False
