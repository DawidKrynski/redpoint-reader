"""Windows clipboard helpers: copy the selection with a simulated Ctrl+C and restore
whatever the clipboard held before."""

from __future__ import annotations

import ctypes
import time
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002
# Handles that are not HGLOBAL memory; Windows synthesises most of them from other formats.
NON_MEMORY_FORMATS = {2, 3, 9, 14, 0x80, 0x82, 0x83, 0x8E}
VK_SHIFT, VK_CONTROL, VK_MENU, VK_LWIN, VK_RWIN, VK_C = 0x10, 0x11, 0x12, 0x5B, 0x5C, 0x43
KEYEVENTF_KEYUP = 0x0002
INPUT_KEYBOARD = 1

user32.OpenClipboard.argtypes = [wintypes.HWND]
user32.GetClipboardData.argtypes = [wintypes.UINT]
user32.GetClipboardData.restype = wintypes.HANDLE
user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
user32.SetClipboardData.restype = wintypes.HANDLE
user32.EnumClipboardFormats.argtypes = [wintypes.UINT]
user32.EnumClipboardFormats.restype = wintypes.UINT
user32.GetClipboardSequenceNumber.restype = wintypes.DWORD
user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
user32.GetAsyncKeyState.restype = ctypes.c_short
kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalLock.restype = ctypes.c_void_p
kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalSize.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalSize.restype = ctypes.c_size_t
kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]


def _open(retries: int = 20) -> bool:
    for _ in range(retries):
        if user32.OpenClipboard(None):
            return True
        time.sleep(0.02)
    return False


def snapshot() -> list[tuple[int, bytes]] | None:
    if not _open():
        return None
    saved: list[tuple[int, bytes]] = []
    try:
        fmt = 0
        while True:
            fmt = user32.EnumClipboardFormats(fmt)
            if not fmt:
                break
            if fmt in NON_MEMORY_FORMATS:
                continue
            h = user32.GetClipboardData(fmt)
            if not h:
                continue
            size = kernel32.GlobalSize(h)
            ptr = kernel32.GlobalLock(h)
            if not ptr:
                continue
            try:
                saved.append((fmt, ctypes.string_at(ptr, size)))
            finally:
                kernel32.GlobalUnlock(h)
    finally:
        user32.CloseClipboard()
    return saved


def restore(saved: list[tuple[int, bytes]]) -> None:
    if not _open():
        return
    try:
        user32.EmptyClipboard()
        for fmt, data in saved:
            h = kernel32.GlobalAlloc(GMEM_MOVEABLE, max(len(data), 1))
            if not h:
                continue
            ptr = kernel32.GlobalLock(h)
            ctypes.memmove(ptr, data, len(data))
            kernel32.GlobalUnlock(h)
            if not user32.SetClipboardData(fmt, h):
                kernel32.GlobalFree(h)
    finally:
        user32.CloseClipboard()


def read_text() -> str | None:
    if not _open():
        return None
    try:
        h = user32.GetClipboardData(CF_UNICODETEXT)
        if not h:
            return ""
        ptr = kernel32.GlobalLock(h)
        try:
            return ctypes.wstring_at(ptr) if ptr else ""
        finally:
            kernel32.GlobalUnlock(h)
    finally:
        user32.CloseClipboard()


def wait_modifiers_released(timeout: float) -> None:
    end = time.monotonic() + timeout
    keys = (VK_SHIFT, VK_CONTROL, VK_MENU, VK_LWIN, VK_RWIN)
    while time.monotonic() < end and any(user32.GetAsyncKeyState(k) & 0x8000 for k in keys):
        time.sleep(0.01)


def _key(vk: int, up: bool) -> INPUT:
    return INPUT(type=INPUT_KEYBOARD, u=_INPUTUNION(ki=KEYBDINPUT(wVk=vk, dwFlags=KEYEVENTF_KEYUP if up else 0)))


def send_ctrl_c() -> None:
    seq = (INPUT * 4)(_key(VK_CONTROL, False), _key(VK_C, False), _key(VK_C, True), _key(VK_CONTROL, True))
    user32.SendInput(4, seq, ctypes.sizeof(INPUT))


def copy_selection(timeout: float = 0.6) -> str | None:
    """Text selected in the foreground app, or None when nothing got copied."""
    wait_modifiers_released(1.5)
    saved = snapshot()
    before = user32.GetClipboardSequenceNumber()
    send_ctrl_c()
    end = time.monotonic() + timeout
    while time.monotonic() < end and user32.GetClipboardSequenceNumber() == before:
        time.sleep(0.015)
    if user32.GetClipboardSequenceNumber() == before:
        return None
    time.sleep(0.05)  # some apps set several formats one after another
    text = read_text()
    if saved is not None:
        restore(saved)
    return text
