"""Settings stored as JSON in the platform's user config directory."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

APP_NAME = "Redpoint"
APP_ID = "io.github.dawidkrynski.Redpoint"


def default_hotkey() -> str:
    # Ctrl+Option+Space switches input sources on macOS.
    return "ctrl+alt+r" if sys.platform == "darwin" else "ctrl+alt+space"


DEFAULTS: dict = {
    "wpm": 350,
    "font_size": 76,
    "font_family": "",  # empty = system sans-serif
    "hotkey": None,  # None = platform default
    "language": "auto",  # auto, en, pl
    "start_paused": False,
    "background": "#000000",
    "text_color": "#ebebeb",
    "focus_color": "#eb2d2d",
    "welcome_shown": False,
}


def config_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
        return base / APP_NAME
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "redpoint"


def config_path() -> Path:
    override = os.environ.get("REDPOINT_CONFIG")
    return Path(override) if override else config_dir() / "config.json"


class Config(dict):
    def __init__(self, path: Path | None = None):
        super().__init__(DEFAULTS)
        self.path = path or config_path()
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                self.update({k: v for k, v in data.items() if k in DEFAULTS})
        except (OSError, ValueError):
            pass
        self["wpm"] = clamp_wpm(self["wpm"])
        if not self["hotkey"]:
            self["hotkey"] = default_hotkey()

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(dict(self), f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)


def clamp_wpm(v) -> int:
    try:
        v = int(v)
    except (TypeError, ValueError):
        v = DEFAULTS["wpm"]
    return max(100, min(1500, v))
