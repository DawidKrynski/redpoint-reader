"""X11: XGrabKey on the root window through libX11 (ctypes), on a dedicated thread."""

from __future__ import annotations

import ctypes
import ctypes.util
import os
import select
import threading

from . import Backend, Hotkey, Result

ShiftMask, LockMask, ControlMask, Mod1Mask, Mod2Mask, Mod4Mask = 1, 2, 4, 8, 16, 64
KeyPress = 2
GrabModeAsync = 1
BadAccess = 10

KEYSYMS = {
    "space": "space",
    "enter": "Return",
    "tab": "Tab",
    "insert": "Insert",
    "pause": "Pause",
    **{f"f{i}": f"F{i}" for i in range(1, 13)},
}


class XErrorEvent(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_int),
        ("display", ctypes.c_void_p),
        ("resourceid", ctypes.c_ulong),
        ("serial", ctypes.c_ulong),
        ("error_code", ctypes.c_ubyte),
        ("request_code", ctypes.c_ubyte),
        ("minor_code", ctypes.c_ubyte),
    ]


class XKeyEvent(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_int),
        ("serial", ctypes.c_ulong),
        ("send_event", ctypes.c_int),
        ("display", ctypes.c_void_p),
        ("window", ctypes.c_ulong),
        ("root", ctypes.c_ulong),
        ("subwindow", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("x", ctypes.c_int),
        ("y", ctypes.c_int),
        ("x_root", ctypes.c_int),
        ("y_root", ctypes.c_int),
        ("state", ctypes.c_uint),
        ("keycode", ctypes.c_uint),
        ("same_screen", ctypes.c_int),
    ]


class XEvent(ctypes.Union):
    _fields_ = [("type", ctypes.c_int), ("xkey", XKeyEvent), ("pad", ctypes.c_long * 24)]


ERROR_HANDLER = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.POINTER(XErrorEvent))


class X11Backend(Backend):
    name = "x11"

    def __init__(self, callback):
        super().__init__(callback)
        path = ctypes.util.find_library("X11") or "libX11.so.6"
        self.x = ctypes.CDLL(path)
        x = self.x
        x.XOpenDisplay.restype = ctypes.c_void_p
        x.XOpenDisplay.argtypes = [ctypes.c_char_p]
        x.XDefaultRootWindow.restype = ctypes.c_ulong
        x.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
        x.XStringToKeysym.restype = ctypes.c_ulong
        x.XStringToKeysym.argtypes = [ctypes.c_char_p]
        x.XKeysymToKeycode.restype = ctypes.c_ubyte
        x.XKeysymToKeycode.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        x.XGrabKey.argtypes = [
            ctypes.c_void_p,
            ctypes.c_int,
            ctypes.c_uint,
            ctypes.c_ulong,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
        ]
        x.XUngrabKey.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_uint, ctypes.c_ulong]
        x.XSync.argtypes = [ctypes.c_void_p, ctypes.c_int]
        x.XPending.argtypes = [ctypes.c_void_p]
        x.XNextEvent.argtypes = [ctypes.c_void_p, ctypes.POINTER(XEvent)]
        x.XConnectionNumber.argtypes = [ctypes.c_void_p]
        x.XSetErrorHandler.restype = ctypes.c_void_p
        x.XSetErrorHandler.argtypes = [ERROR_HANDLER]
        x.XFlush.argtypes = [ctypes.c_void_p]
        self.dpy = x.XOpenDisplay(None)
        if not self.dpy:
            raise OSError("cannot open X display")
        self.root = x.XDefaultRootWindow(self.dpy)
        self._error = False
        self._handler = ERROR_HANDLER(self._on_error)  # keep a reference
        x.XSetErrorHandler(self._handler)
        self._lock = threading.Lock()
        self._grabbed: tuple[int, int] | None = None
        self._wake_r, self._wake_w = os.pipe()
        threading.Thread(target=self._loop, name="redpoint-hotkey", daemon=True).start()

    def _on_error(self, _dpy, event) -> int:
        if event.contents.error_code == BadAccess:
            self._error = True
        return 0

    @staticmethod
    def _variants(mask: int) -> list[int]:
        return [mask, mask | LockMask, mask | Mod2Mask, mask | LockMask | Mod2Mask]

    def _ungrab(self) -> None:
        if self._grabbed:
            keycode, mask = self._grabbed
            for m in self._variants(mask):
                self.x.XUngrabKey(self.dpy, keycode, m, self.root)
            self.x.XSync(self.dpy, 0)
            self._grabbed = None

    def register(self, hotkey: Hotkey) -> str:
        name = KEYSYMS.get(hotkey.key, hotkey.key)
        keysym = self.x.XStringToKeysym(name.encode())
        keycode = self.x.XKeysymToKeycode(self.dpy, keysym) if keysym else 0
        if not keycode:
            return Result.ERROR
        mask = 0
        for mod, bit in (("ctrl", ControlMask), ("alt", Mod1Mask), ("shift", ShiftMask), ("super", Mod4Mask)):
            if mod in hotkey.modifiers:
                mask |= bit
        with self._lock:
            self._ungrab()
            self._error = False
            for m in self._variants(mask):
                self.x.XGrabKey(self.dpy, keycode, m, self.root, 0, GrabModeAsync, GrabModeAsync)
            self.x.XSync(self.dpy, 0)
            if self._error:
                for m in self._variants(mask):
                    self.x.XUngrabKey(self.dpy, keycode, m, self.root)
                self.x.XSync(self.dpy, 0)
                return Result.TAKEN
            self._grabbed = (keycode, mask)
        os.write(self._wake_w, b"x")
        return Result.OK

    def unregister(self) -> None:
        with self._lock:
            self._ungrab()

    def _loop(self) -> None:
        fd = self.x.XConnectionNumber(self.dpy)
        ev = XEvent()
        while True:
            ready, _, _ = select.select([fd, self._wake_r], [], [])
            if self._wake_r in ready:
                os.read(self._wake_r, 64)
            with self._lock:
                fire = False
                while self.x.XPending(self.dpy):
                    self.x.XNextEvent(self.dpy, ctypes.byref(ev))
                    if ev.type == KeyPress and self._grabbed and ev.xkey.keycode == self._grabbed[0]:
                        fire = True
            if fire:
                self._pressed()
