"""Linux: a tiny virtual keyboard through /dev/uinput (no dependencies, no dialogs).

Works under X11 and every Wayland compositor, because the compositor sees it as a real
keyboard. Needs write access to /dev/uinput, which most desktops grant to the logged-in
user (systemd "uaccess", e.g. via the steam-devices / game controller rules). When it is not
available, the RemoteDesktop portal is used instead.

Key codes are evdev codes, i.e. physical positions; Ctrl and Insert are the same on every
layout, which is one more reason to copy with Ctrl+Insert.
"""

from __future__ import annotations

import fcntl
import os
import struct
import threading
import time

UINPUT = "/dev/uinput"
EV_SYN, EV_KEY = 0x00, 0x01
SYN_REPORT = 0
KEY_LEFTCTRL, KEY_INSERT, KEY_C, KEY_LEFTSHIFT = 29, 110, 46, 42
KEYS = {"ctrl": KEY_LEFTCTRL, "insert": KEY_INSERT, "c": KEY_C, "shift": KEY_LEFTSHIFT}

UI_SET_EVBIT = 0x40045564
UI_SET_KEYBIT = 0x40045565
UI_DEV_CREATE = 0x5501
UI_DEV_DESTROY = 0x5502
UI_DEV_SETUP = 0x405C5503  # _IOW('U', 3, struct uinput_setup)
BUS_VIRTUAL = 0x06


def available() -> bool:
    return os.path.exists(UINPUT) and os.access(UINPUT, os.W_OK)


class VirtualKeyboard:
    """Created once and kept: compositors take a moment to adopt a new device."""

    def __init__(self, name: str = "Redpoint virtual keyboard"):
        self._lock = threading.Lock()
        self.fd = os.open(UINPUT, os.O_WRONLY | os.O_NONBLOCK)
        try:
            fcntl.ioctl(self.fd, UI_SET_EVBIT, EV_KEY)
            for code in KEYS.values():
                fcntl.ioctl(self.fd, UI_SET_KEYBIT, code)
            # struct uinput_setup { struct input_id {u16 bustype, vendor, product, version}; char name[80]; u32 ff }
            setup = struct.pack("HHHH80sI", BUS_VIRTUAL, 0x5250, 0x0001, 1, name.encode()[:79], 0)
            fcntl.ioctl(self.fd, UI_DEV_SETUP, setup)
            fcntl.ioctl(self.fd, UI_DEV_CREATE)
        except OSError:
            os.close(self.fd)
            raise
        self.created = time.monotonic()

    def _emit(self, etype: int, code: int, value: int) -> None:
        now = time.time()
        sec = int(now)
        os.write(self.fd, struct.pack("llHHi", sec, int((now - sec) * 1e6), etype, code, value))

    def press(self, combo: list[str]) -> bool:
        with self._lock:
            wait = 0.4 - (time.monotonic() - self.created)  # first use right after creation
            if wait > 0:
                time.sleep(wait)
            codes = [KEYS[k] for k in combo]
            try:
                for c in codes:
                    self._emit(EV_KEY, c, 1)
                    self._emit(EV_SYN, SYN_REPORT, 0)
                    time.sleep(0.015)
                for c in reversed(codes):
                    self._emit(EV_KEY, c, 0)
                    self._emit(EV_SYN, SYN_REPORT, 0)
                    time.sleep(0.015)
                return True
            except OSError:
                return False

    def close(self) -> None:
        try:
            fcntl.ioctl(self.fd, UI_DEV_DESTROY)
        except OSError:
            pass
        os.close(self.fd)
