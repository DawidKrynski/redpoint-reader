"""Global shortcut backends.

A shortcut is stored as a portable lowercase string such as ``ctrl+alt+space`` or
``super+alt+c``. ``super`` is the Windows / Command / Super key; ``ctrl`` is always the
physical Control key (also on macOS).
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from dataclasses import dataclass, field

MODIFIERS = ("ctrl", "alt", "shift", "super")
NAMED_KEYS = {"space", "enter", "tab", "insert", "pause"} | {f"f{i}" for i in range(1, 13)}
ALIASES = {
    "control": "ctrl",
    "option": "alt",
    "opt": "alt",
    "meta": "super",
    "win": "super",
    "cmd": "super",
    "command": "super",
    "logo": "super",
    "return": "enter",
}


@dataclass(frozen=True)
class Hotkey:
    key: str
    modifiers: frozenset = field(default_factory=frozenset)

    def __str__(self) -> str:
        mods = [m for m in MODIFIERS if m in self.modifiers]
        return "+".join(mods + [self.key])

    def label(self) -> str:
        names = {"ctrl": "Ctrl", "alt": "Alt", "shift": "Shift", "super": "Super"}
        if sys.platform == "win32":
            names["super"] = "Win"
        elif sys.platform == "darwin":
            names.update(ctrl="⌃", alt="⌥", shift="⇧", super="⌘")
        mods = [names[m] for m in MODIFIERS if m in self.modifiers]
        key = self.key.upper() if len(self.key) == 1 else self.key.capitalize()
        return "+".join(mods + [key])


def parse(spec: str) -> Hotkey:
    parts = [p.strip().lower() for p in spec.replace(" ", "").split("+") if p.strip()]
    if not parts:
        raise ValueError("empty shortcut")
    parts = [ALIASES.get(p, p) for p in parts]
    *mods, key = parts
    bad = [m for m in mods if m not in MODIFIERS]
    if bad:
        raise ValueError(f"unknown modifier: {bad[0]}")
    if not (len(key) == 1 and key.isascii() and key.isalnum()) and key not in NAMED_KEYS:
        raise ValueError(f"unsupported key: {key}")
    if not mods:
        raise ValueError("a global shortcut needs at least one modifier")
    return Hotkey(key, frozenset(mods))


class Result:
    OK = "ok"
    TAKEN = "taken"
    PORTAL = "portal"  # registered, but the desktop owns the actual key binding
    MANUAL = "manual"  # user has to bind a command in desktop settings
    ERROR = "error"


class Backend:
    """Base class. ``callback`` may be called from any thread; the app marshals it."""

    name = "none"

    def __init__(self, callback: Callable[[], None]):
        self.callback = callback

    def register(self, hotkey: Hotkey) -> str:
        return Result.MANUAL

    def unregister(self) -> None:
        pass


def create_backend(callback: Callable[[], None], platform_name: str) -> Backend:
    """Pick the backend for this OS / Qt platform plugin."""
    if sys.platform == "win32":
        from .windows import WindowsBackend

        return WindowsBackend(callback)
    if sys.platform == "darwin":
        from .macos import MacBackend

        return MacBackend(callback)
    from . import kde

    if kde.available():
        return kde.KdeBackend(callback)
    if platform_name == "xcb":
        from .x11 import X11Backend

        return X11Backend(callback)
    if platform_name.startswith("wayland"):
        from .portal import PortalBackend

        return PortalBackend(callback)
    return Backend(callback)
