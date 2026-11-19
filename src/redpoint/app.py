"""The resident Qt application: IPC server, global shortcut, tray, reader and settings."""

from __future__ import annotations

import json
import os
import platform
import sys
import threading
import time
from pathlib import Path

from PyQt6.QtCore import QCoreApplication, QObject, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtNetwork import QLocalServer, QLocalSocket
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon

from . import __version__, autostart, ipc
from . import hotkeys as H
from .config import APP_ID, Config
from .i18n import set_language, tr
from .reader import ReaderWindow
from .selection import SelectionGrabber
from .ui import SettingsWindow, Tray, app_icon, icon_png


def make_qapp() -> QApplication:
    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_MacDontSwapCtrlAndMeta, True)
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setApplicationName("Redpoint")
    app.setApplicationVersion(__version__)
    app.setDesktopFileName(APP_ID)
    app.setQuitOnLastWindowClosed(False)
    app.setWindowIcon(app_icon())
    return app


class Signals(QObject):
    hotkey = pyqtSignal()
    registered = pyqtSignal(str, str, str)  # spec, result, detail


class Redpoint(QObject):
    def __init__(self, app: QApplication):
        super().__init__()
        self.app = app
        self.cfg = Config()
        set_language(self.cfg["language"])
        self.platform_name = app.platformName()
        self.sig = Signals()
        self.reader = ReaderWindow(self.cfg)
        self.reader.winId()  # create the native window now so showing it later is instant
        self.grabber = SelectionGrabber(self.platform_name)
        self.grabber.ready.connect(self.reader.start)
        self.grabber.ready.connect(lambda t, src: log(f"text from {src}: {len(t)} chars {t[:60]!r}"))
        self.grabber.needs_focus.connect(self.reader.wait_for_text)
        self.reader.activated.connect(self.grabber.read_focused)
        self.settings: SettingsWindow | None = None
        self.hotkey_result = (H.Result.ERROR, "")
        self.registering = False

        autostart.install_linux_desktop_file(icon_png())
        self.backend = self._make_backend()
        self.sig.hotkey.connect(self.on_hotkey)
        self.sig.registered.connect(self._on_registered)
        self.register_hotkey(self.cfg["hotkey"])

        self.tray = None
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = Tray(self.read_selection, self.read_clipboard, self.show_settings, self.quit)
            self.tray.show()

    # --- shortcut
    def _make_backend(self) -> H.Backend:
        try:
            backend = H.create_backend(self.sig.hotkey.emit, self.platform_name)
        except Exception:  # noqa: BLE001 - e.g. libX11 missing: fall back to manual binding
            backend = H.Backend(self.sig.hotkey.emit)
        if backend.name == "portal":
            backend.app_id = APP_ID
            backend.description = tr("Read selection")
        elif backend.name == "kde":
            backend.action_id[3] = tr("Read selection")
        return backend

    def register_hotkey(self, spec: str) -> None:
        try:
            hk = H.parse(spec)
        except ValueError:
            self.sig.registered.emit(spec, H.Result.ERROR, "")
            return

        def work():
            result = self.backend.register(hk)
            detail = getattr(self.backend, "trigger_description", "") or ""
            self.sig.registered.emit(spec, result, detail)

        self.registering = True
        if sys.platform == "darwin":  # Carbon must be called on the main thread
            work()
        else:
            threading.Thread(target=work, daemon=True).start()

    def _on_registered(self, spec: str, result: str, detail: str) -> None:
        self.registering = False
        if result in (H.Result.OK, H.Result.PORTAL) and spec != self.cfg["hotkey"]:
            self.cfg["hotkey"] = spec
            self.cfg.save()
        elif result == H.Result.TAKEN and spec != self.cfg["hotkey"]:
            # keep the previous, working shortcut but leave the "taken" message visible
            self._keep_status = True
            QTimer.singleShot(0, lambda: self.register_hotkey(self.cfg["hotkey"]))
        elif getattr(self, "_keep_status", False):
            self._keep_status = False
            log(f"shortcut {spec}: {result} (restored)")
            return
        self.hotkey_result = (result, detail)
        if self.settings is not None:
            self.settings.load()
            self.settings.set_status(result, detail)
        log(f"shortcut {spec}: {result} {detail}".strip())

    def on_hotkey(self) -> None:
        log("shortcut pressed")
        if self.reader.isVisible():
            self.reader.dismiss()
        else:
            self.read_selection()

    # --- actions
    def read_selection(self) -> None:
        self.grabber.request()

    def read_clipboard(self) -> None:
        self.reader.start(self.grabber.clipboard_text(), "clipboard")

    def show_settings(self) -> None:
        if self.settings is None:
            self.settings = SettingsWindow(self.cfg)
            self.settings.try_it.connect(lambda: self.reader.start(tr("sample")))
            self.settings.hotkey_changed.connect(self.register_hotkey)
            self.settings.config_changed.connect(self._config_changed)
            self.settings.quit_requested.connect(self.quit)
        self.settings.set_status(*self.hotkey_result)
        self.settings.present()
        if not self.cfg["welcome_shown"]:
            self.cfg["welcome_shown"] = True
            self.cfg.save()

    def _config_changed(self) -> None:
        old = tr("Speed")
        set_language(self.cfg["language"])
        self.reader.apply_config()
        if tr("Speed") != old and self.settings is not None:  # language switched: rebuild window
            self.settings.close()
            self.settings.deleteLater()
            self.settings = None
            QTimer.singleShot(0, self.show_settings)

    def handle(self, msg: dict) -> None:
        cmd = msg.get("cmd")
        if cmd == "read":
            self.on_hotkey()
        elif cmd == "clipboard":
            self.read_clipboard()
        elif cmd == "text":
            self.reader.start(str(msg.get("text", "")), "text")
        elif cmd == "settings":
            self.show_settings()
        elif cmd == "quit":
            self.quit()

    def quit(self) -> None:
        try:
            self.backend.unregister()
        except Exception:  # noqa: BLE001
            pass
        if self.tray is not None:
            self.tray.hide()
        self.app.quit()


class Server(QObject):
    message = pyqtSignal(dict)

    def __init__(self):
        super().__init__()
        self.server = QLocalServer(self)
        self.server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        self.server.newConnection.connect(self._connection)

    def listen(self) -> bool:
        name = ipc.server_name()
        if self.server.listen(name):
            return True
        QLocalServer.removeServer(name)  # stale socket from a crashed instance
        return self.server.listen(name)

    def _connection(self):
        while self.server.hasPendingConnections():
            sock: QLocalSocket = self.server.nextPendingConnection()
            buf = bytearray()

            def read(sock=sock, buf=buf):
                buf.extend(bytes(sock.readAll()))
                if buf.endswith(b"\n"):
                    sock.disconnectFromServer()
                    try:
                        msg = json.loads(buf.decode("utf-8"))
                    except ValueError:
                        return
                    if isinstance(msg, dict):
                        self.message.emit(msg)

            sock.readyRead.connect(read)
            sock.disconnected.connect(sock.deleteLater)


def log(line: str) -> None:
    """Debug log: REDPOINT_DEBUG=1 prints to stderr, REDPOINT_LOG=path appends to a file."""
    path = os.environ.get("REDPOINT_LOG")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%H:%M:%S')} {line}\n")
    if os.environ.get("REDPOINT_DEBUG") and sys.stderr:
        print(f"[redpoint] {line}", file=sys.stderr, flush=True)


def run(first: dict) -> int:
    # Before QApplication: Qt registers the app id with the host portal at startup,
    # which needs the .desktop file to exist.
    autostart.install_linux_desktop_file(None)
    app = make_qapp()
    server = Server()
    if not server.listen():
        # Another instance won the race; hand the request over.
        for _ in range(20):
            if ipc.send(first):
                return 0
            time.sleep(0.05)
        print("Redpoint: cannot create the instance socket", file=sys.stderr)
        return 1
    rp = Redpoint(app)
    server.message.connect(rp.handle)
    if first.get("cmd") in ("settings", "noop") and (first["cmd"] == "settings" or not rp.cfg["welcome_shown"]):
        QTimer.singleShot(0, rp.show_settings)
    elif first.get("cmd") not in ("noop", None):
        QTimer.singleShot(0, lambda: rp.handle(first))
    return app.exec()


# --------------------------------------------------------------------------- self test


def self_test(outdir: str) -> int:
    """Non-interactive check used by CI and the multi-distro tests.

    Renders the reader, exercises IPC, the shortcut backend and (optionally) the selection.
    Environment: REDPOINT_EXPECT_SELECTION = text that should be selected right now.
    """
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("REDPOINT_CONFIG", str(out / "config.json"))
    os.environ.setdefault("REDPOINT_SOCKET", ipc.server_name() + ".selftest")
    report: dict = {"version": __version__, "python": sys.version.split()[0], "os": platform.platform()}
    app = make_qapp()
    report["qt_platform"] = app.platformName()
    from . import text as T

    sample = "Redpoint self-test: zażółć gęślą jaźń. Second sentence, with a comma!"
    tokens = T.tokenize(sample)
    report["tokens"] = len(tokens)
    cfg = Config()
    reader = ReaderWindow(cfg)
    reader.resize(1280, 720)
    reader.tokens = tokens
    for idx in (0, 3):
        reader.i = idx
        reader.grab().save(str(out / f"frame-{idx}.png"))
    reader.message = tr("No selected text")
    reader.tokens = []
    reader.grab().save(str(out / "frame-message.png"))
    icon_path = out / "icon.png"
    icon_path.write_bytes(icon_png())

    server = Server()
    got: list[dict] = []
    server.message.connect(got.append)
    report["ipc_listen"] = server.listen()
    threading.Thread(target=lambda: (time.sleep(0.2), ipc.send({"cmd": "noop", "x": "ąę"})), daemon=True).start()
    deadline = time.monotonic() + 3
    while not got and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.02)
    report["ipc_roundtrip"] = bool(got) and got[0].get("x") == "ąę"

    fired = threading.Event()
    try:
        backend = H.create_backend(fired.set, app.platformName())
        report["hotkey_backend"] = backend.name
        if backend.name in ("windows", "x11", "macos", "kde"):
            report["hotkey_register"] = backend.register(H.parse(os.environ.get("REDPOINT_TEST_HOTKEY", "ctrl+alt+r")))
            press = os.environ.get("REDPOINT_TEST_PRESS")  # command that presses the shortcut
            if press and report["hotkey_register"] == H.Result.OK:
                import subprocess

                subprocess.run(press, shell=True, timeout=10)
                end = time.monotonic() + 3
                while not fired.is_set() and time.monotonic() < end:
                    app.processEvents()
                    time.sleep(0.02)
                report["hotkey_fired"] = fired.is_set()
            backend.unregister()
    except Exception as e:  # noqa: BLE001
        report["hotkey_backend_error"] = repr(e)

    expected = os.environ.get("REDPOINT_EXPECT_SELECTION")
    if expected is not None:
        grabber = SelectionGrabber(app.platformName())
        result: list[tuple[str, str]] = []
        grabber.ready.connect(lambda t, s: result.append((t, s)))
        grabber.needs_focus.connect(reader.wait_for_text)
        reader.activated.connect(grabber.read_focused)
        grabber.request()
        end = time.monotonic() + 5
        while not result and time.monotonic() < end:
            app.processEvents()
            time.sleep(0.02)
        reader.dismiss()
        report["selection"] = result[0] if result else None
        report["selection_ok"] = bool(result) and result[0][0].strip() == expected.strip()

    checks = [report["tokens"] == 10, report["ipc_listen"], report["ipc_roundtrip"]]
    if "hotkey_register" in report:
        checks.append(report["hotkey_register"] == H.Result.OK)
    if "hotkey_fired" in report:
        checks.append(report["hotkey_fired"])
    if "selection_ok" in report:
        checks.append(report["selection_ok"])
    report["ok"] = all(checks)
    (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    QGuiApplication.processEvents()
    return 0 if report["ok"] else 1
