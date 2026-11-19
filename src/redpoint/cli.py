"""Command line entry point. Talks to a running instance without importing Qt."""

from __future__ import annotations

import argparse
import sys

from . import __version__, ipc

USAGE = """\
redpoint                 start in the background (or open settings if already running)
redpoint --read          read the current selection (bind this to a desktop shortcut if needed)
redpoint --clipboard     read the clipboard
redpoint FILE | -        read a text file or standard input
redpoint --settings      open the settings window
redpoint --quit          stop the background app
"""


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="redpoint", description="Speed reading of selected text.", usage=USAGE)
    g = p.add_mutually_exclusive_group()
    g.add_argument("--read", action="store_true", help=argparse.SUPPRESS)
    g.add_argument("--clipboard", action="store_true", help=argparse.SUPPRESS)
    g.add_argument("--settings", action="store_true", help=argparse.SUPPRESS)
    g.add_argument("--quit", action="store_true", help=argparse.SUPPRESS)
    g.add_argument("--background", action="store_true", help=argparse.SUPPRESS)
    g.add_argument("--self-test", metavar="DIR", help=argparse.SUPPRESS)
    p.add_argument("--version", action="version", version=f"Redpoint {__version__}")
    p.add_argument("file", nargs="?", help=argparse.SUPPRESS)
    return p.parse_args(argv)


def build_message(a: argparse.Namespace) -> dict:
    if a.read:
        return {"cmd": "read"}
    if a.clipboard:
        return {"cmd": "clipboard"}
    if a.quit:
        return {"cmd": "quit"}
    if a.background:
        return {"cmd": "noop"}
    if a.file:
        if a.file == "-":
            content = sys.stdin.read()
        else:
            with open(a.file, encoding="utf-8", errors="replace") as f:
                content = f.read()
        return {"cmd": "text", "text": content}
    return {"cmd": "settings"}


def main(argv: list[str] | None = None) -> int:
    a = parse_args(sys.argv[1:] if argv is None else argv)
    if a.self_test:
        from .app import self_test

        return self_test(a.self_test)
    message = build_message(a)
    if ipc.send(message):
        return 0
    if message["cmd"] == "quit":
        return 0
    from .app import run

    return run(message)
