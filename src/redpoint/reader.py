"""Full-screen RSVP reader window."""

from __future__ import annotations

import time

from PyQt6.QtCore import QEvent, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QCursor, QFont, QFontMetricsF, QGuiApplication, QPainter
from PyQt6.QtWidgets import QWidget

from . import text as T
from .config import Config, clamp_wpm
from .i18n import tr


def kwin_active_output() -> str:
    """Name of the active output on KDE Wayland, where clients cannot see the cursor."""
    try:
        from jeepney import DBusAddress, new_method_call
        from jeepney.io.blocking import open_dbus_connection

        with open_dbus_connection(bus="SESSION") as conn:
            addr = DBusAddress("/KWin", bus_name="org.kde.KWin", interface="org.kde.KWin")
            reply = conn.send_and_get_reply(new_method_call(addr, "activeOutputName"), timeout=0.5)
            return reply.body[0] if reply.body else ""
    except Exception:  # noqa: BLE001 - not KDE, no jeepney, no bus
        return ""


def target_screen():
    app = QGuiApplication.instance()
    if app.platformName().startswith("wayland"):
        name = kwin_active_output()
        for s in QGuiApplication.screens():
            if s.name() == name:
                return s
        return QGuiApplication.primaryScreen()
    return QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()


class ReaderWindow(QWidget):
    activated = pyqtSignal()  # active while waiting for text (Wayland focus read)
    focused = pyqtSignal()  # every time the window becomes active
    closed = pyqtSignal()

    def __init__(self, config: Config):
        super().__init__()
        self.cfg = config
        self.setWindowTitle("Redpoint")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.tokens: list[T.Token] = []
        self.i = 0
        self.paused = False
        self.ramp = 0
        self.message = ""
        self.waiting = False
        self.info_until = 0.0
        self.timer = QTimer(self, singleShot=True, timeout=self._advance)
        self.info_timer = QTimer(self, singleShot=True, timeout=self.update)
        self.close_timer = QTimer(self, singleShot=True, timeout=self.dismiss)
        self.apply_config()

    def apply_config(self) -> None:
        family = self.cfg.get("font_family") or QFont().defaultFamily()
        self.word_font = QFont(family)
        self.word_font.setPixelSize(int(self.cfg["font_size"]))
        self.info_font = QFont(family)
        self.info_font.setPixelSize(max(13, int(self.cfg["font_size"]) // 5))
        self.c_bg = QColor(self.cfg["background"])
        self.c_text = QColor(self.cfg["text_color"])
        self.c_focus = QColor(self.cfg["focus_color"])
        self.update()

    # --- control
    def present(self) -> None:
        screen = target_screen()
        if self.windowHandle() is None:
            self.winId()
        if screen is not None:
            self.windowHandle().setScreen(screen)
            self.setGeometry(screen.geometry())
        self.showFullScreen()
        self.raise_()
        self.activateWindow()
        self.update()

    def wait_for_text(self) -> None:
        """Show an empty reader; Wayland hands us the selection only once we have focus."""
        self.timer.stop()
        self.close_timer.stop()
        self.tokens, self.message, self.waiting = [], "", True
        self.present()
        if self.isActiveWindow():
            QTimer.singleShot(60, self.activated.emit)

    def start(self, content: str, source: str = "selection") -> None:
        self.waiting = False
        self.timer.stop()
        self.close_timer.stop()
        self.tokens = T.tokenize(content)
        self.i = 0
        self.message = "" if self.tokens else tr("No selected text")
        self.paused = bool(self.cfg.get("start_paused"))
        self.ramp = 4
        if not self.isVisible():
            self.present()
        self.update()
        if not self.tokens:
            self.close_timer.start(1400)
        elif not self.paused:
            self.timer.start(450)  # a moment to settle the eyes on the red letter

    def dismiss(self) -> None:
        self.timer.stop()
        self.close_timer.stop()
        self.waiting = False
        self.tokens = []
        self.hide()
        self.closed.emit()

    def _word_time(self) -> int:
        ms = T.word_ms(self.tokens[self.i], self.cfg["wpm"])
        if self.ramp > 0:
            ms *= 1 + 0.25 * self.ramp
            self.ramp -= 1
        return int(ms)

    def _advance(self) -> None:
        if self.paused or not self.tokens:
            return
        if self.i >= len(self.tokens) - 1:
            self.close_timer.start(700)
            return
        self.i += 1
        self.update()
        self.timer.start(self._word_time())

    def toggle_pause(self) -> None:
        if not self.tokens:
            return
        self.paused = not self.paused
        if self.paused:
            self.timer.stop()
            self.close_timer.stop()
        else:
            if self.i >= len(self.tokens) - 1:
                self.i = 0
            self.ramp = 2
            self.timer.start(self._word_time())
        self.update()

    def jump(self, index: int) -> None:
        if not self.tokens:
            return
        self.i = max(0, min(len(self.tokens) - 1, index))
        self.close_timer.stop()
        self.ramp = 2
        self.update()
        if not self.paused:
            self.timer.start(self._word_time())

    def change_speed(self, delta: int) -> None:
        self.cfg["wpm"] = clamp_wpm(self.cfg["wpm"] + delta)
        self.cfg.save()
        self.info_until = time.monotonic() + 1.3
        self.info_timer.start(1350)
        self.update()

    # --- events
    def event(self, e):
        if e.type() == QEvent.Type.WindowActivate:
            QTimer.singleShot(0, self.focused.emit)
            if self.waiting:
                QTimer.singleShot(60, self.activated.emit)
        return super().event(e)

    def keyPressEvent(self, e):
        k = e.key()
        shift = bool(e.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        if k in (Qt.Key.Key_Escape, Qt.Key.Key_Q):
            self.dismiss()
        elif k in (Qt.Key.Key_Space, Qt.Key.Key_P, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.toggle_pause()
        elif k == Qt.Key.Key_Up:
            self.change_speed(25)
        elif k == Qt.Key.Key_Down:
            self.change_speed(-25)
        elif k == Qt.Key.Key_Left:
            self.jump(self.i - 1 if shift else T.previous_sentence(self.tokens, self.i))
        elif k == Qt.Key.Key_Right:
            self.jump(self.i + 1 if shift else T.next_sentence(self.tokens, self.i))
        elif k == Qt.Key.Key_Home:
            self.jump(0)
        else:
            super().keyPressEvent(e)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.RightButton:
            self.dismiss()
        else:
            self.toggle_pause()

    def wheelEvent(self, e):
        self.change_speed(25 if e.angleDelta().y() > 0 else -25)

    def focusOutEvent(self, e):
        if self.tokens and not self.paused and not self.waiting:
            self.toggle_pause()
        super().focusOutEvent(e)

    # --- painting
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), self.c_bg)
        w, h = self.width(), self.height()
        fm = QFontMetricsF(self.word_font)
        # The focus point sits a little left of centre: word endings get more room.
        px = w * 0.5 - fm.horizontalAdvance("ab")
        cy = h * 0.42
        half = fm.height() * 0.95
        span = min(w * 0.42, fm.horizontalAdvance("M") * 9)
        guide = QColor(self.c_text)
        guide.setAlphaF(0.18)
        p.setPen(guide)
        p.drawLine(int(w * 0.5 - span), int(cy - half), int(w * 0.5 + span), int(cy - half))
        p.drawLine(int(w * 0.5 - span), int(cy + half), int(w * 0.5 + span), int(cy + half))
        tick = max(10, int(half * 0.22))
        p.drawLine(int(px), int(cy - half), int(px), int(cy - half + tick))
        p.drawLine(int(px), int(cy + half - tick), int(px), int(cy + half))

        dim = QColor(self.c_text)
        dim.setAlphaF(0.45)
        base = cy + (fm.ascent() - fm.descent()) / 2
        top = base - fm.ascent()
        if self.message:
            p.setFont(self.info_font)
            p.setPen(dim)
            p.drawText(QRectF(0, cy - 30, w, 60), Qt.AlignmentFlag.AlignCenter, self.message)
        elif self.tokens:
            before, letter, after = T.split_word(self.tokens[self.i].word)
            lw = fm.horizontalAdvance(letter)
            x = px - lw / 2
            p.setFont(self.word_font)
            p.setPen(self.c_text)
            p.drawText(QRectF(0, top, x, fm.height()), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop, before)
            p.setPen(self.c_focus)
            p.drawText(
                QRectF(x, top, lw + 4, fm.height()), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, letter
            )
            p.setPen(self.c_text)
            p.drawText(
                QRectF(x + lw, top, w, fm.height()), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, after
            )
            bar = QColor(self.c_text)
            bar.setAlphaF(0.25)
            p.fillRect(QRectF(0, h - 3, w * (self.i + 1) / len(self.tokens), 3), bar)

        p.setFont(self.info_font)
        p.setPen(dim)
        info = QRectF(0, h * 0.72, w, fm.height())
        wpm = self.cfg["wpm"]
        if self.paused and self.tokens:
            left = T.remaining_seconds(self.tokens, self.i, wpm)
            p.drawText(
                info,
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap,
                f"{tr('paused')} · {wpm} {tr('words/min')} · {tr('left')} {int(left // 60)}:{int(left % 60):02d}"
                f"\n{tr('keys_help')}",
            )
        elif time.monotonic() < self.info_until:
            p.drawText(info, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, f"{wpm} {tr('words/min')}")
        p.end()
