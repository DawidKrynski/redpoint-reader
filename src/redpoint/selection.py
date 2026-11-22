"""Getting the currently selected text from other applications.

The goal everywhere: select text, press the shortcut, Redpoint copies it itself and puts the
previous clipboard back afterwards, with every format it had (images, rich text, files...).

* Windows: simulated Ctrl+C (Ctrl+Insert in terminals, where Ctrl+C would interrupt).
* macOS: simulated Cmd+C (needs the Accessibility permission).
* Linux Wayland: a fresh PRIMARY selection when the app sets one; otherwise a simulated
  Ctrl+Insert through the RemoteDesktop portal (the desktop asks for permission once).
  Ctrl+Insert is the CUA copy key: it copies in Qt, GTK, Chromium/Electron, Firefox and
  LibreOffice, and unlike Ctrl+C it never interrupts a program in a terminal.
* Linux X11: the PRIMARY selection, which every X11 app sets.

Without anything new, the regular clipboard is read, so copy + shortcut always works too.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
import time

from PyQt6.QtCore import QMimeData, QObject, QTimer, pyqtSignal
from PyQt6.QtGui import QClipboard, QGuiApplication

KLIPPER_REFILL = "application/x-kde-onlyReplaceEmpty"  # Klipper put back an old history entry
PRIMARY_FRESH_S = 120  # a PRIMARY selection younger than this counts as "just selected"
# X11 selection bookkeeping targets that XWayland lists but that are not data.
PSEUDO_TYPES = {"TARGETS", "MULTIPLE", "TIMESTAMP", "SAVE_TARGETS", "DELETE", "INSERT_SELECTION", "INSERT_PROPERTY"}
MAX_FORMAT_BYTES = 64 * 1024 * 1024
MAX_TOTAL_BYTES = 192 * 1024 * 1024


def wl_paste_path() -> str | None:
    """Bundled wl-paste (AppImage / PyInstaller build) first, then the system one."""
    for base in (os.environ.get("APPDIR"), getattr(sys, "_MEIPASS", None)):
        if base:
            for rel in ("usr/bin/wl-paste", "bin/wl-paste"):
                cand = os.path.join(base, rel)
                if os.access(cand, os.X_OK):
                    return cand
    return shutil.which("wl-paste")


def _wl(args: list[str], timeout: float = 1.5) -> bytes | None:
    exe = wl_paste_path()
    if not exe:
        return None
    try:
        r = subprocess.run([exe, *args], capture_output=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.stdout if r.returncode == 0 else b""


def wl_types(primary: bool) -> list[str]:
    out = _wl(["--list-types"] + (["--primary"] if primary else []))
    return out.decode("utf-8", errors="replace").split() if out else []


def wl_text(primary: bool) -> str | None:
    out = _wl(["--no-newline", "--type", "text"] + (["--primary"] if primary else []))
    return None if out is None else out.decode("utf-8", errors="replace")


def wl_snapshot() -> list[tuple[str, bytes]] | None:
    """Every format currently on the Wayland clipboard (None when wl-paste is missing)."""
    if wl_paste_path() is None:
        return None
    saved: list[tuple[str, bytes]] = []
    total = 0
    for mime in wl_types(primary=False):
        if mime in PSEUDO_TYPES or mime == KLIPPER_REFILL:
            continue
        data = _wl(["--no-newline", "--type", mime], timeout=3)
        if data is None or len(data) > MAX_FORMAT_BYTES or total + len(data) > MAX_TOTAL_BYTES:
            continue
        total += len(data)
        saved.append((mime, data))
    return saved


def qt_snapshot(mode=QClipboard.Mode.Clipboard) -> list[tuple[str, bytes]]:
    md = QGuiApplication.clipboard().mimeData(mode)
    if md is None:
        return []
    saved = []
    for f in md.formats():
        if f in PSEUDO_TYPES:
            continue
        data = bytes(md.data(f))
        if len(data) <= MAX_FORMAT_BYTES:
            saved.append((f, data))
    return saved


def qt_restore(saved: list[tuple[str, bytes]]) -> None:
    cb = QGuiApplication.clipboard()
    if not saved:
        cb.clear(QClipboard.Mode.Clipboard)
        return
    md = QMimeData()
    for mime, data in saved:
        md.setData(mime, data)
    cb.setMimeData(md, QClipboard.Mode.Clipboard)


class SelectionGrabber(QObject):
    """``request()`` → later ``ready(text, source)``; source is 'selection' or 'clipboard'."""

    ready = pyqtSignal(str, str)
    needs_focus = pyqtSignal()  # Wayland without wl-paste: show the window, then call read_focused()
    _from_thread = pyqtSignal(str, str)
    log = pyqtSignal(str)

    def __init__(self, platform_name: str):
        super().__init__()
        self.platform_name = platform_name
        self._from_thread.connect(self.ready)
        self.backend = None  # hotkey backend: tells when the shortcut keys are released
        self.keyboard = None  # wlinject.RemoteKeyboard on Wayland
        self.pending_restore: list[tuple[str, bytes]] | None = None
        self._busy = False
        # When PRIMARY and CLIPBOARD changed last (monotonic seconds).
        self.changed = {"primary": 0.0, "clipboard": 0.0}
        self.last_request = 0.0
        self._ignore_clipboard_until = 0.0
        self._watchers: list = []
        if sys.platform.startswith("linux"):
            self._start_watch()

    # ------------------------------------------------------------------ change tracking
    def _start_watch(self) -> None:
        if self.wayland:
            exe = wl_paste_path()
            if not exe:
                return
            from PyQt6.QtCore import QProcess

            for kind in ("primary", "clipboard"):
                proc = QProcess(self)
                args = (["--primary"] if kind == "primary" else []) + ["--watch", "echo"]
                first = [True]

                def on_output(kind=kind, proc=proc, first=first):
                    proc.readAllStandardOutput()
                    if first[0]:  # the watcher reports the current content once at start
                        first[0] = False
                        return
                    self._mark(kind)

                proc.readyReadStandardOutput.connect(on_output)
                proc.start(exe, args)
                self._watchers.append(proc)
        else:

            def on_change(mode):
                self._mark("primary" if mode == QClipboard.Mode.Selection else "clipboard")

            QGuiApplication.clipboard().changed.connect(on_change)

    def _mark(self, kind: str) -> None:
        now = time.monotonic()
        if kind == "clipboard" and now < self._ignore_clipboard_until:
            return  # our own restore

        def check():
            # Klipper refilling an emptied selection with an old history entry is not new.
            types = wl_types(kind == "primary") if self.wayland else []
            if not self.wayland:
                mode = QClipboard.Mode.Selection if kind == "primary" else QClipboard.Mode.Clipboard
                md = QGuiApplication.clipboard().mimeData(mode)
                types = md.formats() if md is not None else []
            if KLIPPER_REFILL not in types:
                self.changed[kind] = now

        if self.wayland:  # wl-paste can block on our own clipboard: never on the GUI thread
            threading.Thread(target=check, daemon=True).start()
        else:
            check()

    def stop(self) -> None:
        for proc in self._watchers:
            proc.kill()
            proc.waitForFinished(500)
        self._watchers.clear()

    def _primary_fresh(self) -> bool:
        t = self.changed["primary"]
        return t > self.last_request and time.monotonic() - t < PRIMARY_FRESH_S

    def _choose(self, primary: str, clipboard: str) -> tuple[str, str]:
        if clipboard.strip() and (self.changed["clipboard"] > self.changed["primary"] or not primary.strip()):
            return clipboard, "clipboard"
        if primary.strip():
            return primary, "selection"
        return "", "clipboard"

    def _pick(self, primary: str, clipboard: str) -> None:
        self.ready.emit(*self._choose(primary, clipboard))

    @property
    def wayland(self) -> bool:
        return self.platform_name.startswith("wayland")

    def clipboard_text(self) -> str:
        return QGuiApplication.clipboard().text(QClipboard.Mode.Clipboard)

    # ------------------------------------------------------------------ request
    def request(self) -> None:
        if self._busy:
            return
        if sys.platform == "win32":
            self._run_thread(self._windows)
        elif sys.platform == "darwin":
            self._mac_start()
        elif self.wayland:
            if wl_paste_path() is None:
                # No wl-paste: without focus Qt sees neither PRIMARY nor CLIPBOARD on Wayland.
                self.needs_focus.emit()
                return
            self._run_thread(self._wayland)
        else:
            cb = QGuiApplication.clipboard()
            primary = cb.text(QClipboard.Mode.Selection)
            md = cb.mimeData(QClipboard.Mode.Selection)
            if md is not None and KLIPPER_REFILL in md.formats():
                primary = ""
            self.last_request = time.monotonic()
            self._pick(primary, cb.text(QClipboard.Mode.Clipboard))

    def _run_thread(self, fn) -> None:
        self._busy = True

        def run():
            try:
                text, source = fn()
            except Exception as e:  # noqa: BLE001 - never crash the background app on clipboard races
                self.log.emit(f"selection error: {e!r}")
                text, source = "", "clipboard"
            self._busy = False
            self._from_thread.emit(text, source)

        threading.Thread(target=run, daemon=True).start()

    def _wait_release(self) -> None:
        b = self.backend
        if b is not None and b.reports_release:
            b.released.wait(1.5)
            time.sleep(0.08)
        else:
            time.sleep(0.35)

    # --- Wayland (worker thread)
    def _wayland(self) -> tuple[str, str]:
        primary = wl_text(primary=True) or ""
        if KLIPPER_REFILL in wl_types(primary=True):
            primary = ""
        fresh = self._primary_fresh() and primary.strip()
        self.last_request = time.monotonic()
        if fresh:
            self.log.emit("using fresh PRIMARY selection")
            return primary, "selection"
        if self.keyboard is not None:
            self._wait_release()
            saved = wl_snapshot()
            before = self.changed["clipboard"]
            started = time.monotonic()
            if self.keyboard.press(["ctrl", "insert"]):
                # The first time the desktop may show its permission dialog first.
                deadline = time.monotonic() + 0.8
                while self.changed["clipboard"] == before and time.monotonic() < deadline:
                    time.sleep(0.02)
                if self.changed["clipboard"] != before:
                    time.sleep(0.05)
                    text = wl_text(primary=False) or ""
                    self.pending_restore = saved
                    self.log.emit(f"copied with Ctrl+Insert in {time.monotonic() - started:.2f}s")
                    if text.strip():
                        return text, "selection"
                else:
                    self.log.emit("Ctrl+Insert copied nothing")
            else:
                self.log.emit("RemoteDesktop portal unavailable or denied")
        return self._choose(primary, wl_text(primary=False) or "")

    def restore_clipboard(self) -> None:
        """Put the previous clipboard back; on Wayland this needs our window to have focus."""
        saved, self.pending_restore = self.pending_restore, None
        if saved is None:
            return
        self._ignore_clipboard_until = time.monotonic() + 1.0
        qt_restore(saved)
        self.log.emit(f"clipboard restored ({len(saved)} formats)")

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

    # --- Windows (worker thread)
    def _windows(self) -> tuple[str, str]:
        from . import winclip

        text = winclip.copy_selection()  # waits for the shortcut's modifiers to be released
        if text and text.strip():
            return text, "selection"
        return winclip.read_text() or "", "clipboard"

    # --- macOS
    def _mac_start(self) -> None:
        from . import macclip

        self._mac_saved = qt_snapshot()
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
        qt_restore(self._mac_saved)
        self.ready.emit(text, "selection") if text.strip() else self._finish("")
