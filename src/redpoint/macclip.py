"""macOS helpers: simulated Cmd+C through Quartz and the pasteboard change counter."""

from __future__ import annotations

import ctypes
import ctypes.util
import time

_q = ctypes.CDLL(
    ctypes.util.find_library("ApplicationServices")
    or "/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices"
)
_objc = ctypes.CDLL(ctypes.util.find_library("objc") or "/usr/lib/libobjc.dylib")
ctypes.CDLL(ctypes.util.find_library("AppKit") or "/System/Library/Frameworks/AppKit.framework/AppKit")

kCGEventFlagMaskCommand = 1 << 20
kCGHIDEventTap = 0
kCGEventSourceStateHIDSystemState = 1
MODIFIER_MASK = (1 << 16) | (1 << 17) | (1 << 18) | (1 << 19) | (1 << 20)
KVK_C = 0x08

_q.CGEventCreateKeyboardEvent.restype = ctypes.c_void_p
_q.CGEventCreateKeyboardEvent.argtypes = [ctypes.c_void_p, ctypes.c_uint16, ctypes.c_bool]
_q.CGEventSetFlags.argtypes = [ctypes.c_void_p, ctypes.c_uint64]
_q.CGEventPost.argtypes = [ctypes.c_uint32, ctypes.c_void_p]
_q.CGEventSourceFlagsState.argtypes = [ctypes.c_int32]
_q.CGEventSourceFlagsState.restype = ctypes.c_uint64
_q.AXIsProcessTrusted.restype = ctypes.c_bool
_q.CFRelease.argtypes = [ctypes.c_void_p]
_objc.objc_getClass.restype = ctypes.c_void_p
_objc.objc_getClass.argtypes = [ctypes.c_char_p]
_objc.sel_registerName.restype = ctypes.c_void_p
_objc.sel_registerName.argtypes = [ctypes.c_char_p]
_msg = _objc.objc_msgSend
_msg.restype = ctypes.c_void_p
_msg.argtypes = [ctypes.c_void_p, ctypes.c_void_p]


def accessibility_trusted() -> bool:
    try:
        return bool(_q.AXIsProcessTrusted())
    except Exception:  # noqa: BLE001
        return False


def change_count() -> int:
    pb = _msg(_objc.objc_getClass(b"NSPasteboard"), _objc.sel_registerName(b"generalPasteboard"))
    return int(_msg(pb, _objc.sel_registerName(b"changeCount")) or 0)


def wait_modifiers_released(timeout: float) -> None:
    end = time.monotonic() + timeout
    while time.monotonic() < end and _q.CGEventSourceFlagsState(kCGEventSourceStateHIDSystemState) & MODIFIER_MASK:
        time.sleep(0.01)


def send_copy() -> bool:
    if not accessibility_trusted():
        return False
    for down in (True, False):
        ev = _q.CGEventCreateKeyboardEvent(None, KVK_C, down)
        _q.CGEventSetFlags(ev, kCGEventFlagMaskCommand)
        _q.CGEventPost(kCGHIDEventTap, ev)
        _q.CFRelease(ev)
    return True
