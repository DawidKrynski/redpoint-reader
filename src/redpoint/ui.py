"""Settings window, tray icon and the app icon (drawn in code, no image files needed)."""

from __future__ import annotations

import shlex
import subprocess
import sys

from PyQt6.QtCore import QBuffer, QByteArray, QIODevice, QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QAction, QColor, QFont, QGuiApplication, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QSpinBox,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from . import __version__, autostart
from . import hotkeys as H
from .config import Config
from .i18n import tr


def draw_icon(size: int) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    r = size * 0.2
    p.setBrush(QColor("#111111"))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRoundedRect(QRectF(0, 0, size, size), r, r)
    p.setPen(QColor(255, 255, 255, 70))
    y1, y2 = size * 0.26, size * 0.74
    p.drawLine(QPointF(size * 0.14, y1), QPointF(size * 0.86, y1))
    p.drawLine(QPointF(size * 0.14, y2), QPointF(size * 0.86, y2))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#eb2d2d"))
    d = size * 0.3
    p.drawEllipse(QRectF((size - d) / 2, (size - d) / 2, d, d))
    p.end()
    return pm


def app_icon() -> QIcon:
    icon = QIcon()
    for s in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(draw_icon(s))
    return icon


def icon_png(size: int = 256) -> bytes:
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    draw_icon(size).save(buf, "PNG")
    return bytes(ba)


QT_KEYS = {
    Qt.Key.Key_Space: "space",
    Qt.Key.Key_Return: "enter",
    Qt.Key.Key_Enter: "enter",
    Qt.Key.Key_Tab: "tab",
    Qt.Key.Key_Insert: "insert",
    Qt.Key.Key_Pause: "pause",
    **{getattr(Qt.Key, f"Key_F{i}"): f"f{i}" for i in range(1, 13)},
}


def hotkey_from_event(e) -> str | None:
    key = e.key()
    name = QT_KEYS.get(key)
    if name is None:
        if Qt.Key.Key_A.value <= key <= Qt.Key.Key_Z.value or Qt.Key.Key_0.value <= key <= Qt.Key.Key_9.value:
            name = chr(key).lower()
        else:
            return None
    m = e.modifiers()
    mods = []
    # With AA_MacDontSwapCtrlAndMeta, Control is Control and Command is Meta on macOS too.
    if m & Qt.KeyboardModifier.ControlModifier:
        mods.append("ctrl")
    if m & Qt.KeyboardModifier.AltModifier:
        mods.append("alt")
    if m & Qt.KeyboardModifier.ShiftModifier:
        mods.append("shift")
    if m & Qt.KeyboardModifier.MetaModifier:
        mods.append("super")
    if not mods:
        return None
    return "+".join(mods + [name])


class ShortcutButton(QPushButton):
    captured = pyqtSignal(str)

    def __init__(self, text: str):
        super().__init__(text)
        self.capturing = False
        self.clicked.connect(self.begin)

    def begin(self):
        self.capturing = True
        self.setText(tr("Press the new shortcut… (Esc cancels)"))
        self.grabKeyboard()

    def end(self, text: str):
        self.capturing = False
        self.releaseKeyboard()
        self.setText(text)

    def keyPressEvent(self, e):
        if not self.capturing:
            return super().keyPressEvent(e)
        if e.key() == Qt.Key.Key_Escape:
            self.end(tr("Change…"))
            return
        spec = hotkey_from_event(e)
        if spec:
            self.end(tr("Change…"))
            self.captured.emit(spec)


class SettingsWindow(QWidget):
    try_it = pyqtSignal()
    hotkey_changed = pyqtSignal(str)
    config_changed = pyqtSignal()
    quit_requested = pyqtSignal()

    def __init__(self, cfg: Config):
        super().__init__()
        self.cfg = cfg
        self.setWindowTitle(tr("Redpoint settings"))
        self.setWindowIcon(app_icon())
        self.setMinimumWidth(520)
        lay = QVBoxLayout(self)

        intro = QLabel(tr("welcome"))
        intro.setWordWrap(True)
        lay.addWidget(intro)

        form = QFormLayout()
        row = QHBoxLayout()
        self.hotkey_label = QLabel()
        f = QFont(self.hotkey_label.font())
        f.setBold(True)
        self.hotkey_label.setFont(f)
        self.change_btn = ShortcutButton(tr("Change…"))
        self.change_btn.captured.connect(self.hotkey_changed)
        row.addWidget(self.hotkey_label, 1)
        row.addWidget(self.change_btn)
        form.addRow(tr("Shortcut"), row)

        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        form.addRow("", self.status)
        self.copy_cmd = QPushButton(tr("Copy command"))
        self.copy_cmd.clicked.connect(lambda: QGuiApplication.clipboard().setText(shlex.join(autostart.read_command())))
        self.copy_cmd.hide()
        form.addRow("", self.copy_cmd)

        self.wpm = QSpinBox()
        self.wpm.setRange(100, 1500)
        self.wpm.setSingleStep(25)
        self.wpm.setSuffix(" " + tr("words/min"))
        self.wpm.valueChanged.connect(self._changed)
        form.addRow(tr("Speed"), self.wpm)

        self.size = QSpinBox()
        self.size.setRange(24, 240)
        self.size.setSuffix(" px")
        self.size.valueChanged.connect(self._changed)
        form.addRow(tr("Font size"), self.size)

        self.lang = QComboBox()
        self.lang.addItem(tr("Automatic"), "auto")
        self.lang.addItem("English", "en")
        self.lang.addItem("Polski", "pl")
        self.lang.currentIndexChanged.connect(self._changed)
        form.addRow(tr("Language"), self.lang)

        self.auto = QCheckBox(tr("Start at login"))
        self.auto.toggled.connect(self._autostart)
        form.addRow("", self.auto)
        lay.addLayout(form)

        buttons = QHBoxLayout()
        b = QPushButton(tr("Try it"))
        b.clicked.connect(self.try_it)
        buttons.addWidget(b)
        buttons.addStretch(1)
        q = QPushButton(tr("Quit Redpoint"))
        q.clicked.connect(self.quit_requested)
        buttons.addWidget(q)
        c = QPushButton(tr("Close"))
        c.setDefault(True)
        c.clicked.connect(self.close)
        buttons.addWidget(c)
        lay.addLayout(buttons)
        ver = QLabel(f"Redpoint {__version__}")
        ver.setStyleSheet("color: gray")
        lay.addWidget(ver)
        self.load()

    def load(self):
        for w in (self.wpm, self.size, self.lang, self.auto):
            w.blockSignals(True)
        self.wpm.setValue(int(self.cfg["wpm"]))
        self.size.setValue(int(self.cfg["font_size"]))
        self.lang.setCurrentIndex(max(0, self.lang.findData(self.cfg["language"])))
        self.auto.setChecked(autostart.is_enabled())
        for w in (self.wpm, self.size, self.lang, self.auto):
            w.blockSignals(False)
        try:
            self.hotkey_label.setText(H.parse(self.cfg["hotkey"]).label())
        except ValueError:
            self.hotkey_label.setText(self.cfg["hotkey"])

    def set_status(self, result: str, detail: str = ""):
        self.copy_cmd.setVisible(result == H.Result.MANUAL)
        self.change_btn.setEnabled(result != H.Result.PORTAL)
        if result == H.Result.OK:
            text = tr("shortcut_ok")
        elif result == H.Result.TAKEN:
            text = tr("shortcut_taken")
        elif result == H.Result.PORTAL:
            text = tr("shortcut_portal") + (f" ({detail})" if detail else "")
            if detail:
                self.hotkey_label.setText(detail)
        else:
            text = tr("shortcut_manual") + "\n" + shlex.join(autostart.read_command())
        if sys.platform == "darwin":
            from . import macclip

            if not macclip.accessibility_trusted():
                text += "\n" + tr("shortcut_mac_access")
        self.status.setText(text)

    def _changed(self, *_):
        self.cfg["wpm"] = self.wpm.value()
        self.cfg["font_size"] = self.size.value()
        self.cfg["language"] = self.lang.currentData()
        self.cfg.save()
        self.config_changed.emit()

    def _autostart(self, on: bool):
        try:
            autostart.set_enabled(on)
        except OSError:
            self.auto.blockSignals(True)
            self.auto.setChecked(autostart.is_enabled())
            self.auto.blockSignals(False)

    def present(self):
        self.load()
        self.show()
        self.raise_()
        self.activateWindow()


class Tray(QSystemTrayIcon):
    def __init__(self, on_read, on_clipboard, on_settings, on_quit):
        super().__init__(app_icon())
        self.setToolTip("Redpoint")
        menu = QMenu()
        self.read_action = QAction(tr("Read selection"), menu, triggered=on_read)
        menu.addAction(self.read_action)
        menu.addAction(QAction(tr("Read clipboard"), menu, triggered=on_clipboard))
        menu.addSeparator()
        menu.addAction(QAction(tr("Settings…"), menu, triggered=on_settings))
        menu.addAction(QAction(tr("Quit"), menu, triggered=on_quit))
        self._menu = menu
        self.setContextMenu(menu)
        self.activated.connect(
            lambda reason: on_settings() if reason == QSystemTrayIcon.ActivationReason.Trigger else None
        )


def open_url(url: str) -> None:
    opener = {"win32": ["cmd", "/c", "start", ""], "darwin": ["open"]}.get(sys.platform, ["xdg-open"])
    subprocess.Popen(opener + [url])


__all__ = ["SettingsWindow", "Tray", "app_icon", "icon_png", "QDialog"]
