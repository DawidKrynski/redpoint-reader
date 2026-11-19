"""Start at login: registry Run key (Windows), LaunchAgent (macOS), XDG autostart (Linux)."""

from __future__ import annotations

import os
import plistlib
import shlex
import sys
from pathlib import Path

from .config import APP_ID, APP_NAME


def launch_command() -> list[str]:
    """Command that starts this installation again, in the background."""
    appimage = os.environ.get("APPIMAGE")
    if appimage:
        return [appimage, "--background"]
    if getattr(sys, "frozen", False):
        return [sys.executable, "--background"]
    return [sys.executable, "-m", "redpoint", "--background"]


def read_command() -> list[str]:
    cmd = launch_command()
    return cmd[:-1] + ["--read"]


def _xdg_file() -> Path:
    base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / "autostart" / f"{APP_ID}.desktop"


def _plist_file() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{APP_ID}.plist"


def desktop_entry(exec_cmd: list[str], extra: str = "") -> str:
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        f"Name={APP_NAME}\n"
        "Comment=Read selected text word by word\n"
        f"Exec={shlex.join(exec_cmd)}\n"
        f"Icon={APP_ID}\n"
        "Terminal=false\n"
        "Categories=Utility;Accessibility;\n"
        "StartupNotify=false\n" + extra
    )


def is_enabled() -> bool:
    if sys.platform == "win32":
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run") as k:
                winreg.QueryValueEx(k, APP_NAME)
            return True
        except OSError:
            return False
    if sys.platform == "darwin":
        return _plist_file().exists()
    return _xdg_file().exists()


def set_enabled(enabled: bool) -> None:
    cmd = launch_command()
    if sys.platform == "win32":
        import subprocess
        import winreg

        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run") as k:
            if enabled:
                winreg.SetValueEx(k, APP_NAME, 0, winreg.REG_SZ, subprocess.list2cmdline(cmd))
            else:
                try:
                    winreg.DeleteValue(k, APP_NAME)
                except OSError:
                    pass
        return
    path = _plist_file() if sys.platform == "darwin" else _xdg_file()
    if not enabled:
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    if sys.platform == "darwin":
        with open(path, "wb") as f:
            plistlib.dump({"Label": APP_ID, "ProgramArguments": cmd, "RunAtLoad": True}, f)
    else:
        path.write_text(desktop_entry(cmd, "X-GNOME-Autostart-enabled=true\n"), encoding="utf-8")


def install_linux_desktop_file(icon_png: bytes | None) -> None:
    """Menu entry + icon so desktops (and the shortcut portal) know the app id."""
    if sys.platform in ("win32", "darwin"):
        return
    data = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    entry = data / "applications" / f"{APP_ID}.desktop"
    content = desktop_entry(launch_command()[:-1])
    try:
        if not entry.exists() or entry.read_text(encoding="utf-8") != content:
            entry.parent.mkdir(parents=True, exist_ok=True)
            entry.write_text(content, encoding="utf-8")
        if icon_png:
            icon = data / "icons" / "hicolor" / "256x256" / "apps" / f"{APP_ID}.png"
            if not icon.exists():
                icon.parent.mkdir(parents=True, exist_ok=True)
                icon.write_bytes(icon_png)
    except OSError:
        pass
    if is_enabled():  # keep the autostart entry pointing at the current binary (AppImage moved etc.)
        set_enabled(True)
