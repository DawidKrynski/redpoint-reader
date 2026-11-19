"""Getting the currently selected text from other applications.

* Linux X11: the PRIMARY selection, no key simulation needed.
* Linux Wayland: ``wl-paste --primary`` when available, otherwise Qt reads PRIMARY
  once the reader window has keyboard focus (compositors only hand it to the focused app).
* Windows: simulated Ctrl+C; the previous clipboard content is restored afterwards.
* macOS: simulated Cmd+C (needs the Accessibility permission); previous text restored.

Every path falls back to the regular clipboard, so copy + shortcut always works.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import threading
import time

from PyQt6.QtCore import QObject, QTimer, pyqtSignal
from PyQt6.QtGui import QClipboard, QGuiApplication


def wl_paste_path() -> str | None:
    """Bundled wl-paste (AppImage / PyInstaller build) first, then the system one."""
    import os

    for base in (os.environ.get("APPDIR"), getattr(sys, "_MEIPASS", None)):
        if base:
            for rel in ("usr/bin/wl-paste", "bin/wl-paste"):
                cand = os.path.join(base, rel)
                if os.access(cand, os.X_OK):
                    return cand
    return shutil.which("wl-paste")


def _run_wl_paste(primary: bool) -> str | None:
    exe = wl_paste_path()
    if not exe:
        return None
    args = [exe, "--no-newline", "--type", "text"]
    if primary:
        args.insert(1, "--primary")
    try:
        r = subprocess.run(args, capture_output=True, timeout=1.5)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if r.returncode != 0:
        return ""
    return r.stdout.decode("utf-8", errors="replace")


class SelectionGrabber(QObject):
    """``request()`` → later ``ready(text, source)``; source is 'selection' or 'clipboard'."""

    ready = pyqtSignal(str, str)
    needs_focus = pyqtSignal()  # Wayland without wl-paste: show the window, then call read_focused()
    _from_thread = pyqtSignal(str, str)

    def __init__(self, platform_name: str):
        super().__init__()
        self.platform_name = platform_name
        self._from_thread.connect(self.ready)

    @property
    def wayland(self) -> bool:
        return self.platform_name.startswith("wayland")

    def clipboard_text(self) -> str:
        return QGuiApplication.clipboard().text(QClipboard.Mode.Clipboard)

    def request(self) -> None:
        if sys.platform == "win32":
            threading.Thread(target=self._windows, daemon=True).start()
        elif sys.platform == "darwin":
            self._mac_start()
        elif self.wayland:
            text = _run_wl_paste(primary=True)
            if text and text.strip():
                self.ready.emit(text, "selection")
                return
            # Without focus Qt sees neither PRIMARY nor CLIPBOARD on Wayland.
            self.needs_focus.emit()
        else:
            self._finish(QGuiApplication.clipboard().text(QClipboard.Mode.Selection))

    def read_focused(self, attempts: int = 10) -> None:
        """Called once our window is active; the compositor's selection offer may lag a bit."""
        cb = QGuiApplication.clipboard()
        text = cb.text(QClipboard.Mode.Selection) if cb.supportsSelection() else ""
        if not text.strip() and attempts > 0:
            QTimer.singleShot(40, lambda: self.read_focused(attempts - 1))
            return
        self._finish(text)

    def _finish(self, text: str) -> None:
        if text.strip():
            self.ready.emit(text, "selection")
        else:
            self.ready.emit(self.clipboard_text(), "clipboard")

    # --- Windows
    def _windows(self) -> None:
        from . import winclip

        try:
            text = winclip.copy_selection()
        except Exception:  # noqa: BLE001 - never crash the background app on clipboard races
            text = None
        if text and text.strip():
            self._from_thread.emit(text, "selection")
        else:
            self._from_thread.emit(winclip.read_text() or "", "clipboard")

    # --- macOS
    def _mac_start(self) -> None:
        from . import macclip

        self._mac_old = self.clipboard_text()
        self._mac_count = macclip.change_count()
        macclip.wait_modifiers_released(1.0)
        if not macclip.send_copy():
            self._finish("")
            return
        self._mac_deadline = time.monotonic() + 0.5
        QTimer.singleShot(30, self._mac_poll)

    def _mac_poll(self) -> None:
        from . import macclip

        if macclip.change_count() == self._mac_count and time.monotonic() < self._mac_deadline:
            QTimer.singleShot(30, self._mac_poll)
            return
        if macclip.change_count() == self._mac_count:
            self._finish("")
            return
        text = self.clipboard_text()
        QGuiApplication.clipboard().setText(self._mac_old, QClipboard.Mode.Clipboard)
        self.ready.emit(text, "selection") if text.strip() else self._finish("")
