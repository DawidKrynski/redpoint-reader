"""Test helper: press a key combination (e.g. ctrl+alt+r or ctrl+a) with synthetic input.

Windows: SendInput. Linux X11: xdotool. Used by the end-to-end tests only.
"""

import sys
import time

COMBO = sys.argv[1]

if sys.platform == "win32":
    import ctypes

    sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1] / "src"))
    from redpoint import winclip as W

    VK = {"ctrl": 0x11, "alt": 0x12, "shift": 0x10, "super": 0x5B, "space": 0x20, "enter": 0x0D, "escape": 0x1B}
    keys = [VK.get(k) or ord(k.upper()) for k in COMBO.lower().split("+")]
    seq = [W._key(k, False) for k in keys] + [W._key(k, True) for k in reversed(keys)]
    arr = (W.INPUT * len(seq))(*seq)
    W.user32.SendInput(len(seq), arr, ctypes.sizeof(W.INPUT))
    time.sleep(0.1)
else:
    import subprocess

    subprocess.run(["xdotool", "key", COMBO], check=True)
