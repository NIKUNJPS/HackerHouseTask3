"""Tiny, dependency-free console logger with step/status formatting.

ANSI colours are used only when stdout is a TTY that understands them, so piping
to a file or an unsupported terminal degrades gracefully to plain text.
"""
from __future__ import annotations

import os
import sys
import time

# Windows consoles often default to cp1252, which cannot encode box-drawing /
# emoji glyphs. Force UTF-8 where possible; otherwise fall back to ASCII art.
for _stream in ("stdout", "stderr"):
    try:
        getattr(sys, _stream).reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def _supports_unicode() -> bool:
    enc = (getattr(sys.stdout, "encoding", "") or "").lower()
    return "utf" in enc


_UNI = _supports_unicode()
_USE_COLOR = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None

# glyph set chosen by capability
_G = {
    "tl": "╔" if _UNI else "+", "tr": "╗" if _UNI else "+",
    "bl": "╚" if _UNI else "+", "br": "╝" if _UNI else "+",
    "h": "═" if _UNI else "=", "v": "║" if _UNI else "|",
    "arrow": "▸" if _UNI else ">", "hr": "─" if _UNI else "-",
    "ok": "✔" if _UNI else "[OK]", "warn": "!" if _UNI else "[!]",
    "fail": "✗" if _UNI else "[X]",
}


def _c(code: str, text: str) -> str:
    if not _USE_COLOR:
        return text
    return f"\033[{code}m{text}\033[0m"


def bold(t: str) -> str:   return _c("1", t)
def dim(t: str) -> str:    return _c("2", t)
def cyan(t: str) -> str:   return _c("36", t)
def green(t: str) -> str:  return _c("32", t)
def yellow(t: str) -> str: return _c("33", t)
def red(t: str) -> str:    return _c("31", t)
def blue(t: str) -> str:   return _c("34", t)

_STEP = 0


def step(title: str) -> None:
    """Print a numbered pipeline stage header."""
    global _STEP
    _STEP += 1
    line = _G["hr"] * max(4, 60 - len(title))
    print()
    print(bold(cyan(f"{_G['arrow']} STEP {_STEP}  {title} ")) + dim(line))


def info(msg: str) -> None:
    print(f"  {msg}")


def kv(key: str, value: object) -> None:
    print(f"    {dim(key + ':'):<28} {value}")


def ok(msg: str) -> None:
    print(green(f"  {_G['ok']} {msg}"))


def warn(msg: str) -> None:
    print(yellow(f"  {_G['warn']} {msg}"))


def fail(msg: str) -> None:
    print(red(f"  {_G['fail']} {msg}"))


def banner(title: str, subtitle: str = "") -> None:
    width = 64
    inner = width - 2
    print()
    print(bold(blue(_G["tl"] + _G["h"] * inner + _G["tr"])))
    print(bold(blue(_G["v"])) + bold(f" {title}".ljust(inner)) + bold(blue(_G["v"])))
    if subtitle:
        print(bold(blue(_G["v"])) + dim(f" {subtitle}".ljust(inner)) + bold(blue(_G["v"])))
    print(bold(blue(_G["bl"] + _G["h"] * inner + _G["br"])))


class timed:
    """Context manager that reports how long a block took."""

    def __init__(self, label: str):
        self.label = label

    def __enter__(self):
        self.t0 = time.perf_counter()
        return self

    def __exit__(self, *exc):
        dt = time.perf_counter() - self.t0
        print(dim(f"    ({self.label} took {dt:.2f}s)"))
        return False
