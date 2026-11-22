"""Wayland: press a key combination in the focused app through the RemoteDesktop portal.

Apps cannot send key presses to other apps on Wayland. The RemoteDesktop portal can, after
the user allows it once; with ``persist_mode = 2`` the desktop hands back a restore token
and later sessions start without asking again. The session is kept for a few minutes
after use, so the desktop does not announce a new remote control session on every press.
"""

from __future__ import annotations

import threading
import time

from . import portalutil as P

IFACE = "org.freedesktop.portal.RemoteDesktop"
KEYBOARD = 1
IDLE_CLOSE_S = 300
KEYSYMS = {"ctrl": 0xFFE3, "insert": 0xFF63, "c": 0x63, "shift": 0xFFE1}


class RemoteKeyboard:
    def __init__(self, app_id: str, get_token, save_token):
        self.app_id = app_id
        self.get_token = get_token
        self.save_token = save_token
        self._lock = threading.RLock()
        self._conn = None
        self._session = None
        self._idle: threading.Timer | None = None

    def available(self) -> bool:
        try:
            conn = P.connect()
            try:
                from jeepney import DBusAddress, Properties

                addr = DBusAddress(P.PORTAL_PATH, bus_name=P.PORTAL, interface=IFACE)
                reply = conn.send_and_get_reply(Properties(addr).get("version"), timeout=2)
                return reply.header.message_type.name != "error"
            finally:
                conn.close()
        except Exception:  # noqa: BLE001
            return False

    def _open(self, timeout: float):
        conn = P.connect(self.app_id)
        session = None
        try:
            code, res = P.request(
                conn,
                IFACE,
                "CreateSession",
                "a{sv}",
                lambda tok: ({"handle_token": ("s", tok), "session_handle_token": ("s", P.token())},),
                timeout=10,
            )
            if code != 0:
                raise RuntimeError("CreateSession refused")
            session = res["session_handle"][1]
            opts = {"types": ("u", KEYBOARD), "persist_mode": ("u", 2)}
            saved = self.get_token()
            if saved:
                opts["restore_token"] = ("s", saved)
            code, _ = P.request(
                conn, IFACE, "SelectDevices", "oa{sv}", lambda tok: (session, {**opts, "handle_token": ("s", tok)}), 10
            )
            if code != 0:
                raise RuntimeError("SelectDevices refused")
            code, res = P.request(
                conn, IFACE, "Start", "osa{sv}", lambda tok: (session, "", {"handle_token": ("s", tok)}), timeout
            )
            if code != 0:
                raise RuntimeError("Start refused")
            new_token = res.get("restore_token", ("s", ""))[1]
            if new_token and new_token != saved:
                self.save_token(new_token)
            time.sleep(0.1)  # the desktop creates its virtual keyboard on Start
            return conn, session
        except Exception:
            if session:
                P.close_session(conn, session)
            conn.close()
            raise

    def _close(self) -> None:
        with self._lock:
            if self._conn is not None:
                P.close_session(self._conn, self._session)
                self._conn.close()
            self._conn = self._session = None

    def press(self, combo: list[str], timeout: float = 120) -> bool:
        """Press and release the keys in order (modifiers first). Blocks; call from a thread.

        The session stays open for a few minutes so repeated use does not make the desktop
        announce a new remote control session every time.
        """
        with self._lock:
            if self._idle is not None:
                self._idle.cancel()
            for _attempt in (1, 2):
                try:
                    if self._conn is None:
                        self._conn, self._session = self._open(timeout)
                    for s in [KEYSYMS[k] for k in combo]:
                        P.call(self._conn, IFACE, "NotifyKeyboardKeysym", "oa{sv}iu", (self._session, {}, s, 1))
                        time.sleep(0.02)
                    for s in reversed([KEYSYMS[k] for k in combo]):
                        P.call(self._conn, IFACE, "NotifyKeyboardKeysym", "oa{sv}iu", (self._session, {}, s, 0))
                        time.sleep(0.02)
                    self._idle = threading.Timer(IDLE_CLOSE_S, self._close)
                    self._idle.daemon = True
                    self._idle.start()
                    return True
                except Exception:  # noqa: BLE001 - session closed by the desktop, denied, no portal
                    if self._conn is not None:
                        try:
                            self._conn.close()
                        except Exception:  # noqa: BLE001
                            pass
                    self._conn = self._session = None
            return False
