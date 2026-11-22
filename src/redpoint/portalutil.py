"""Small helpers for xdg-desktop-portal calls over jeepney (blocking, use from a thread)."""

from __future__ import annotations

import secrets

PORTAL = "org.freedesktop.portal.Desktop"
PORTAL_PATH = "/org/freedesktop/portal/desktop"


def connect(app_id: str = ""):
    from jeepney import DBusAddress, new_method_call
    from jeepney.io.blocking import open_dbus_connection

    conn = open_dbus_connection(bus="SESSION")
    if app_id:
        try:  # tells the portal our app id when we are not sandboxed (portal >= 1.19)
            reg = DBusAddress(PORTAL_PATH, bus_name=PORTAL, interface="org.freedesktop.host.portal.Registry")
            conn.send_and_get_reply(new_method_call(reg, "Register", "sa{sv}", (app_id, {})), timeout=3)
        except Exception:  # noqa: BLE001 - older portals do not have the registry
            pass
    return conn


def token() -> str:
    return "redpoint" + secrets.token_hex(6)


def request(conn, interface: str, method: str, signature: str, args_builder, timeout: float = 120):
    """Call a portal method that answers with a Request/Response pair; returns (code, results)."""
    from jeepney import DBusAddress, MatchRule, new_method_call
    from jeepney.bus_messages import message_bus

    tok = token()
    sender = conn.unique_name.lstrip(":").replace(".", "_")
    req_path = f"{PORTAL_PATH}/request/{sender}/{tok}"
    rule = MatchRule(type="signal", interface="org.freedesktop.portal.Request", member="Response", path=req_path)
    conn.send_and_get_reply(message_bus.AddMatch(rule), timeout=3)
    addr = DBusAddress(PORTAL_PATH, bus_name=PORTAL, interface=interface)
    with conn.filter(rule) as queue:
        reply = conn.send_and_get_reply(new_method_call(addr, method, signature, args_builder(tok)), timeout=5)
        if reply.header.message_type.name == "error":
            raise RuntimeError(f"{method}: {reply.body}")
        sig = conn.recv_until_filtered(queue, timeout=timeout)  # a dialog may be waiting for the user
    code, results = sig.body
    return code, results


def call(conn, interface: str, method: str, signature: str, args):
    from jeepney import DBusAddress, new_method_call

    addr = DBusAddress(PORTAL_PATH, bus_name=PORTAL, interface=interface)
    reply = conn.send_and_get_reply(new_method_call(addr, method, signature, args), timeout=3)
    if reply.header.message_type.name == "error":
        raise RuntimeError(f"{method}: {reply.body}")
    return reply.body


def close_session(conn, session_path: str) -> None:
    from jeepney import DBusAddress, new_method_call

    try:
        addr = DBusAddress(session_path, bus_name=PORTAL, interface="org.freedesktop.portal.Session")
        conn.send_and_get_reply(new_method_call(addr, "Close"), timeout=2)
    except Exception:  # noqa: BLE001
        pass
