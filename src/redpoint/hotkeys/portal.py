"""Wayland: org.freedesktop.portal.GlobalShortcuts (KDE Plasma 6, GNOME 48+, Hyprland, ...).

Runs on its own thread with a blocking jeepney connection. The session lives as long as
that connection, so the connection is kept open for the life of the app.
"""

from __future__ import annotations

import secrets
import threading

from . import Backend, Hotkey, Result

PORTAL = "org.freedesktop.portal.Desktop"
PORTAL_PATH = "/org/freedesktop/portal/desktop"
IFACE = "org.freedesktop.portal.GlobalShortcuts"
SHORTCUT_ID = "read-selection"

XDG_KEYS = {
    "space": "space",
    "enter": "Return",
    "tab": "Tab",
    "insert": "Insert",
    "pause": "Pause",
    **{f"f{i}": f"F{i}" for i in range(1, 13)},
}
XDG_MODS = {"ctrl": "CTRL", "alt": "ALT", "shift": "SHIFT", "super": "LOGO"}


def xdg_trigger(hotkey: Hotkey) -> str:
    mods = [XDG_MODS[m] for m in ("ctrl", "alt", "shift", "super") if m in hotkey.modifiers]
    return "+".join(mods + [XDG_KEYS.get(hotkey.key, hotkey.key)])


class PortalBackend(Backend):
    name = "portal"

    def __init__(self, callback, app_id: str = "", description: str = "Read selected text"):
        super().__init__(callback)
        self.app_id = app_id
        self.description = description
        self._conn = None
        self._session = None
        self._lock = threading.Lock()
        self.trigger_description = ""

    # --- helpers
    def _connect(self):
        from jeepney.io.blocking import open_dbus_connection

        conn = open_dbus_connection(bus="SESSION")
        if self.app_id:
            try:  # lets the portal know our app id when we are not sandboxed (portal >= 1.19)
                from jeepney import DBusAddress, new_method_call

                reg = DBusAddress(PORTAL_PATH, bus_name=PORTAL, interface="org.freedesktop.host.portal.Registry")
                conn.send_and_get_reply(new_method_call(reg, "Register", "sa{sv}", (self.app_id, {})), timeout=3)
            except Exception:  # noqa: BLE001 - older portals do not have the registry
                pass
        return conn

    def _request(self, conn, method: str, signature: str, args_builder):
        """Call a portal method that answers with a Request/Response pair."""
        from jeepney import DBusAddress, MatchRule, new_method_call
        from jeepney.bus_messages import message_bus

        token = "redpoint" + secrets.token_hex(6)
        sender = conn.unique_name.lstrip(":").replace(".", "_")
        req_path = f"{PORTAL_PATH}/request/{sender}/{token}"
        rule = MatchRule(type="signal", interface="org.freedesktop.portal.Request", member="Response", path=req_path)
        conn.send_and_get_reply(message_bus.AddMatch(rule), timeout=3)
        addr = DBusAddress(PORTAL_PATH, bus_name=PORTAL, interface=IFACE)
        with conn.filter(rule) as queue:
            reply = conn.send_and_get_reply(new_method_call(addr, method, signature, args_builder(token)), timeout=5)
            if reply.header.message_type.name == "error":
                raise RuntimeError(f"{method}: {reply.body}")
            # The user may need to confirm a dialog, so wait generously.
            sig = conn.recv_until_filtered(queue, timeout=120)
        code, results = sig.body
        return code, results

    # --- Backend API
    def register(self, hotkey: Hotkey) -> str:
        with self._lock:
            try:
                if self._conn is None:
                    self._conn = self._connect()
                    code, results = self._request(
                        self._conn,
                        "CreateSession",
                        "a{sv}",
                        lambda token: (
                            {
                                "handle_token": ("s", token),
                                "session_handle_token": ("s", "redpoint" + secrets.token_hex(4)),
                            },
                        ),
                    )
                    if code != 0:
                        return Result.MANUAL
                    self._session = results["session_handle"][1]
                shortcut = [
                    (
                        SHORTCUT_ID,
                        {
                            "description": ("s", self.description),
                            "preferred_trigger": ("s", xdg_trigger(hotkey)),
                        },
                    )
                ]
                code, results = self._request(
                    self._conn,
                    "BindShortcuts",
                    "oa(sa{sv})sa{sv}",
                    lambda token: (self._session, shortcut, "", {"handle_token": ("s", token)}),
                )
                if code != 0:
                    return Result.MANUAL
                for sid, props in results.get("shortcuts", ("", []))[1]:
                    if sid == SHORTCUT_ID:
                        self.trigger_description = props.get("trigger_description", ("s", ""))[1]
                threading.Thread(target=self._listen, name="redpoint-portal", daemon=True).start()
                return Result.PORTAL
            except Exception:  # noqa: BLE001 - no portal, no interface, timeout...
                self._conn = None
                return Result.MANUAL

    def _listen(self) -> None:
        from jeepney import MatchRule
        from jeepney.bus_messages import message_bus

        conn = self._conn
        from jeepney import HeaderFields

        rule = MatchRule(type="signal", interface=IFACE, path=PORTAL_PATH)
        conn.send_and_get_reply(message_bus.AddMatch(rule), timeout=3)
        self.reports_release = True
        with conn.filter(rule) as queue:
            while True:
                try:
                    sig = conn.recv_until_filtered(queue)
                except Exception:  # noqa: BLE001 - connection closed
                    return
                if len(sig.body) < 2 or sig.body[0] != self._session or sig.body[1] != SHORTCUT_ID:
                    continue
                member = sig.header.fields.get(HeaderFields.member)
                if member == "Activated":
                    self._pressed()
                elif member == "Deactivated":
                    self.released.set()
