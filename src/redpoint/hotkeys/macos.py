"""macOS: Carbon RegisterEventHotKey through ctypes. Needs no special permission."""

from __future__ import annotations

import ctypes
import ctypes.util

from . import Backend, Hotkey, Result

carbon = ctypes.CDLL(ctypes.util.find_library("Carbon") or "/System/Library/Frameworks/Carbon.framework/Carbon")

cmdKey, shiftKey, optionKey, controlKey = 1 << 8, 1 << 9, 1 << 11, 1 << 12
kEventClassKeyboard = int.from_bytes(b"keyb", "big")
kEventHotKeyPressed = 5
eventHotKeyExistsErr = -9878

# ANSI virtual key codes (kVK_*)
KEYCODES = {
    "a": 0x00, "s": 0x01, "d": 0x02, "f": 0x03, "h": 0x04, "g": 0x05, "z": 0x06, "x": 0x07,
    "c": 0x08, "v": 0x09, "b": 0x0B, "q": 0x0C, "w": 0x0D, "e": 0x0E, "r": 0x0F, "y": 0x10,
    "t": 0x11, "1": 0x12, "2": 0x13, "3": 0x14, "4": 0x15, "6": 0x16, "5": 0x17, "9": 0x19,
    "7": 0x1A, "8": 0x1C, "0": 0x1D, "o": 0x1F, "u": 0x20, "i": 0x22, "p": 0x23, "l": 0x25,
    "j": 0x26, "k": 0x28, "n": 0x2D, "m": 0x2E, "enter": 0x24, "tab": 0x30, "space": 0x31,
    "f1": 0x7A, "f2": 0x78, "f3": 0x63, "f4": 0x76, "f5": 0x60, "f6": 0x61, "f7": 0x62,
    "f8": 0x64, "f9": 0x65, "f10": 0x6D, "f11": 0x67, "f12": 0x6F, "insert": 0x72,
}  # fmt: skip


class EventTypeSpec(ctypes.Structure):
    _fields_ = [("eventClass", ctypes.c_uint32), ("eventKind", ctypes.c_uint32)]


class EventHotKeyID(ctypes.Structure):
    _fields_ = [("signature", ctypes.c_uint32), ("id", ctypes.c_uint32)]


HANDLER = ctypes.CFUNCTYPE(ctypes.c_int32, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)

carbon.GetApplicationEventTarget.restype = ctypes.c_void_p
carbon.InstallEventHandler.argtypes = [
    ctypes.c_void_p,
    HANDLER,
    ctypes.c_uint32,
    ctypes.POINTER(EventTypeSpec),
    ctypes.c_void_p,
    ctypes.POINTER(ctypes.c_void_p),
]
carbon.RegisterEventHotKey.argtypes = [
    ctypes.c_uint32,
    ctypes.c_uint32,
    EventHotKeyID,
    ctypes.c_void_p,
    ctypes.c_uint32,
    ctypes.POINTER(ctypes.c_void_p),
]
carbon.UnregisterEventHotKey.argtypes = [ctypes.c_void_p]


class MacBackend(Backend):
    name = "macos"

    def __init__(self, callback):
        super().__init__(callback)
        self._ref = ctypes.c_void_p()
        self._handler = HANDLER(self._on_event)  # keep a reference
        spec = EventTypeSpec(kEventClassKeyboard, kEventHotKeyPressed)
        handler_ref = ctypes.c_void_p()
        self._installed = (
            carbon.InstallEventHandler(
                carbon.GetApplicationEventTarget(),
                self._handler,
                1,
                ctypes.byref(spec),
                None,
                ctypes.byref(handler_ref),
            )
            == 0
        )

    def _on_event(self, _call_ref, _event, _data) -> int:
        self.callback()
        return 0

    def register(self, hotkey: Hotkey) -> str:
        self.unregister()
        if not self._installed or hotkey.key not in KEYCODES:
            return Result.ERROR
        mods = 0
        for name, bit in (("ctrl", controlKey), ("alt", optionKey), ("shift", shiftKey), ("super", cmdKey)):
            if name in hotkey.modifiers:
                mods |= bit
        hk_id = EventHotKeyID(int.from_bytes(b"RdPt", "big"), 1)
        err = carbon.RegisterEventHotKey(
            KEYCODES[hotkey.key], mods, hk_id, carbon.GetApplicationEventTarget(), 0, ctypes.byref(self._ref)
        )
        if err == 0:
            return Result.OK
        return Result.TAKEN if err == eventHotKeyExistsErr else Result.ERROR

    def unregister(self) -> None:
        if self._ref.value:
            carbon.UnregisterEventHotKey(self._ref)
            self._ref = ctypes.c_void_p()
