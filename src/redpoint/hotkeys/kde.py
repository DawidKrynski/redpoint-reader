"""KDE Plasma (X11 and Wayland): register directly with kglobalaccel over D-Bus.

No confirmation dialog, the shortcut can be changed from the app and it shows up in
System Settings → Shortcuts like any other application's.
"""

from __future__ import annotations

import os
import threading

from . import Backend, Hotkey, Result

COMPONENT = "redpoint"
ACTION = "read-selection"
QT_MODS = {"shift": 0x02000000, "ctrl": 0x04000000, "alt": 0x08000000, "super": 0x10000000}
QT_KEYS = {
    "space": 0x20,
    "enter": 0x01000004,
    "tab": 0x01000001,
    "insert": 0x01000006,
    "pause": 0x01000008,
    **{f"f{i}": 0x01000030 + i - 1 for i in range(1, 13)},
}
SET_PRESENT, NO_AUTOLOADING = 2, 4


def qt_key(hotkey: Hotkey) -> int:
    code = QT_KEYS.get(hotkey.key) or ord(hotkey.key.upper())
    for m in hotkey.modifiers:
        code |= QT_MODS[m]
    return code


def available() -> bool:
    if "KDE" not in os.environ.get("XDG_CURRENT_DESKTOP", "").upper():
        return False
    try:
        from jeepney import DBusAddress, new_method_call
        from jeepney.io.blocking import open_dbus_connection

        with open_dbus_connection(bus="SESSION") as conn:
            dbus = DBusAddress(
                "/org/freedesktop/DBus", bus_name="org.freedesktop.DBus", interface="org.freedesktop.DBus"
            )
            reply = conn.send_and_get_reply(
                new_method_call(dbus, "NameHasOwner", "s", ("org.kde.kglobalaccel",)), timeout=2
            )
            return bool(reply.body[0])
    except Exception:  # noqa: BLE001
        return False


class KdeBackend(Backend):
    name = "kde"

    def __init__(self, callback, friendly: str = "Redpoint", action_name: str = "Read selection"):
        super().__init__(callback)
        from jeepney import DBusAddress
        from jeepney.io.blocking import open_dbus_connection

        self.conn = open_dbus_connection(bus="SESSION")
        self.listen_conn = open_dbus_connection(bus="SESSION")
        self.kga = DBusAddress("/kglobalaccel", bus_name="org.kde.kglobalaccel", interface="org.kde.KGlobalAccel")
        self.action_id = [COMPONENT, ACTION, friendly, action_name]
        self._lock = threading.Lock()
        self._listening = False

    def _call(self, method: str, sig: str, args):
        from jeepney import new_method_call

        reply = self.conn.send_and_get_reply(new_method_call(self.kga, method, sig, args), timeout=3)
        if reply.header.message_type.name == "error":
            raise RuntimeError(f"{method}: {reply.body}")
        return reply.body

    def register(self, hotkey: Hotkey) -> str:
        key = qt_key(hotkey)
        with self._lock:
            try:
                owners = self._call("getGlobalShortcutsByKey", "i", (key,))[0]
                # entries: (action, action name, component, component name, context, ..., keys, default keys)
                others = [o for o in owners if o[2] != COMPONENT]
                if others:
                    return Result.TAKEN
                self._call("doRegister", "as", (self.action_id,))
                # NoAutoloading: our choice wins over a value kglobalaccel remembered earlier.
                self._call(
                    "setShortcutKeys", "asa(ai)u", (self.action_id, [([key, 0, 0, 0],)], SET_PRESENT | NO_AUTOLOADING)
                )
            except Exception:  # noqa: BLE001
                return Result.ERROR
        if not self._listening:
            self._listening = True
            threading.Thread(target=self._listen, name="redpoint-kglobalaccel", daemon=True).start()
        return Result.OK

    def unregister(self) -> None:
        with self._lock:
            try:
                self._call("setInactive", "as", (self.action_id,))
            except Exception:  # noqa: BLE001
                pass

    def _listen(self) -> None:
        from jeepney import MatchRule
        from jeepney.bus_messages import message_bus

        conn = self.listen_conn
        rule = MatchRule(
            type="signal",
            interface="org.kde.kglobalaccel.Component",
            member="globalShortcutPressed",
            path=f"/component/{COMPONENT}",
        )
        conn.send_and_get_reply(message_bus.AddMatch(rule), timeout=3)
        with conn.filter(rule) as queue:
            while True:
                try:
                    sig = conn.recv_until_filtered(queue)
                except Exception:  # noqa: BLE001
                    return
                if sig.body[0] == COMPONENT and sig.body[1] == ACTION:
                    self.callback()
