"""Windows: RegisterHotKey on a dedicated thread with its own message loop."""

from __future__ import annotations

import ctypes
import threading
from ctypes import wintypes

from . import Backend, Hotkey, Result

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, MOD_NOREPEAT = 0x1, 0x2, 0x4, 0x8, 0x4000
WM_HOTKEY, WM_USER = 0x0312, 0x0400
WM_APP_REGISTER, WM_APP_STOP = WM_USER + 1, WM_USER + 2
ERROR_HOTKEY_ALREADY_REGISTERED = 1409
HOTKEY_ID = 0x5250

VK_NAMED = {
    "space": 0x20,
    "enter": 0x0D,
    "tab": 0x09,
    "insert": 0x2D,
    "pause": 0x13,
    **{f"f{i}": 0x6F + i for i in range(1, 13)},
}

user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.PeekMessageW.argtypes = [
    ctypes.POINTER(wintypes.MSG),
    wintypes.HWND,
    wintypes.UINT,
    wintypes.UINT,
    wintypes.UINT,
]


def vk_code(key: str) -> int:
    if key in VK_NAMED:
        return VK_NAMED[key]
    return ord(key.upper())  # letters and digits share ASCII codes with VK codes


def modifier_flags(hotkey: Hotkey) -> int:
    flags = MOD_NOREPEAT
    for name, flag in (("ctrl", MOD_CONTROL), ("alt", MOD_ALT), ("shift", MOD_SHIFT), ("super", MOD_WIN)):
        if name in hotkey.modifiers:
            flags |= flag
    return flags


class WindowsBackend(Backend):
    name = "windows"

    def __init__(self, callback):
        super().__init__(callback)
        self._thread_id = 0
        self._ready = threading.Event()
        self._reply = threading.Event()
        self._result = Result.ERROR
        self._pending: Hotkey | None = None
        threading.Thread(target=self._loop, name="redpoint-hotkey", daemon=True).start()
        self._ready.wait(2)

    def _loop(self) -> None:
        msg = wintypes.MSG()
        # Create the thread's message queue before announcing the thread id.
        user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 0)
        self._thread_id = kernel32.GetCurrentThreadId()
        self._ready.set()
        registered = False
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
                self._pressed()
            elif msg.message == WM_APP_REGISTER:
                if registered:
                    user32.UnregisterHotKey(None, HOTKEY_ID)
                    registered = False
                hk = self._pending
                if hk is None:
                    self._result = Result.OK
                elif user32.RegisterHotKey(None, HOTKEY_ID, modifier_flags(hk), vk_code(hk.key)):
                    registered = True
                    self._result = Result.OK
                else:
                    err = ctypes.get_last_error()
                    self._result = Result.TAKEN if err == ERROR_HOTKEY_ALREADY_REGISTERED else Result.ERROR
                self._reply.set()
            elif msg.message == WM_APP_STOP:
                break
        if registered:
            user32.UnregisterHotKey(None, HOTKEY_ID)

    def _request(self, hotkey: Hotkey | None) -> str:
        if not self._thread_id:
            return Result.ERROR
        self._pending = hotkey
        self._reply.clear()
        user32.PostThreadMessageW(self._thread_id, WM_APP_REGISTER, 0, 0)
        return self._result if self._reply.wait(2) else Result.ERROR

    def register(self, hotkey: Hotkey) -> str:
        return self._request(hotkey)

    def unregister(self) -> None:
        self._request(None)
