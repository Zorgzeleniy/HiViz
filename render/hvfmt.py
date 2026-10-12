#!/usr/bin/env python3
"""hiviz terminal formatting — shared by the engines and the test rig. Stdlib only.

Two output modes:
  md      the legacy markdown tables — what agents and CI logs get (stdout is not a TTY)
  pretty  box-drawing tables, status symbols, color — for a human at a terminal
  json    one JSON document on stdout, nothing else (diagnostics stay on stderr)
Resolution: --format > $HIVIZ_FORMAT > pretty when stdout is a TTY, else md.
Color only in pretty mode on a TTY; NO_COLOR turns it off, FORCE_COLOR forces it.
Symbols fall back to ASCII when the stream encoding cannot carry them; HIVIZ_ASCII=1 forces that
(a console font without ✔ ◐ ⠋ …).
"""
from __future__ import annotations

import atexit
import json
import os
import re
import shutil
import sys
import textwrap
import threading
import time
import unicodedata

_ANSI = re.compile(r"\x1b\[[0-9;]*m")
_STATE = {"pretty": False, "color": False, "unicode": True, "ansi": False, "json": False}

_CODES = {"bold": "1", "dim": "2", "red": "31", "green": "32", "yellow": "33",
          "cyan": "36", "gray": "90"}

# status -> (unicode, ascii, color)
STATUS = {
    "OK": ("✔", "+", "green"), "PASS": ("✔", "+", "green"),
    "FAIL": ("✘", "x", "red"), "STALE": ("✘", "x", "red"),
    "ERROR": ("!", "!", "red"),
    "FLAKY": ("◐", "~", "yellow"),
    "UNVERIFIABLE": ("○", "?", "yellow"), "ORPHANED": ("○", "?", "yellow"),
    "SKIP": ("–", "-", "gray"),
    "REVIEW": ("✎", "~", "yellow"),
    "UNPROVEN": ("○", "?", "yellow"),
    # audit-report verbs (→ verb column)
    "delete": ("✘", "x", "red"), "disable": ("⊘", "x", "red"),
    "rewrite": ("✎", "~", "yellow"), "merge": ("⇄", "=", "cyan"),
    "verify": ("?", "?", "yellow"), "keep": ("✔", "+", "green"),
}
_BOX_U = dict(tl="╭", tr="╮", bl="╰", br="╯", h="─", v="│", t="┬", b="┴", l="├", r="┤", x="┼")
_BOX_A = dict(tl="+", tr="+", bl="+", br="+", h="-", v="|", t="+", b="+", l="+", r="+", x="+")


def add_format_arg(ap, allow_json: bool = True) -> None:
    """--format for an engine. allow_json=False for engines that print no JSON: the flag is refused (exit 2) rather
    than answered with text a script would then fail to parse. HIVIZ_FORMAT=json is only a preference: such an
    engine falls back to md."""
    ap.add_argument("--format", choices=("auto", "pretty", "md") + (("json",) if allow_json else ()), default="auto",
                    help="human output (pretty), markdown for agents/CI (md)"
                         + (" or one JSON document on stdout (json)" if allow_json else "")
                         + "; auto = pretty on a terminal, else md ($HIVIZ_FORMAT overrides auto)")


def _isatty(stream) -> bool:
    try:
        return bool(stream.isatty())
    except Exception:
        return False


# Glyphs the engines print besides STATUS/box/bar symbols; folded to ASCII when the stream can't carry them.
_FOLD = str.maketrans({"·": "-", "→": "->", "…": "...", "“": '"', "”": '"', "—": "-", "–": "-", "━": "=",
                       "•": "*", "●": "*", "⇄": "<>", "−": "-"})
_GLYPHS = "╭✔✘◐○⠋█░━·→“”…—✎⊘⇄●"


class _Folded:
    """Text stream that folds our glyphs to ASCII and never raises UnicodeEncodeError."""

    def __init__(self, stream):
        self._s = stream

    def write(self, text: str) -> int:
        enc = getattr(self._s, "encoding", None) or "ascii"
        return self._s.write(text.translate(_FOLD).encode(enc, "replace").decode(enc))

    def __getattr__(self, name):
        return getattr(self._s, name)


def _enable_vt(stream) -> bool:
    """Windows consoles need VT processing switched on before they honor ANSI codes."""
    if os.name != "nt":
        return True
    try:
        import ctypes
        import msvcrt
        k32 = ctypes.windll.kernel32
        k32.GetConsoleMode.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
        k32.SetConsoleMode.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        handle = msvcrt.get_osfhandle(stream.fileno())
        mode = ctypes.c_ulong()
        if not k32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False   # not a console (redirected)
        if mode.value & 0x0004:
            return True
        if not k32.SetConsoleMode(handle, mode.value | 0x0004):  # ENABLE_VIRTUAL_TERMINAL_PROCESSING
            return False   # legacy console
        atexit.register(k32.SetConsoleMode, handle, mode.value)  # leave the console as we found it
        return True
    except Exception:
        return False


def configure(fmt: str | None = "auto", stream=None) -> bool:
    """Resolve the mode once at startup; returns True for pretty."""
    for name in ("stdout", "stderr"):   # a redirected cp866/cp437 stream must degrade to '?', never crash
        try:
            getattr(sys, name).reconfigure(errors="replace")
        except Exception:
            pass
    stream = stream or sys.stdout
    tty = _isatty(stream)
    if not fmt or fmt == "auto":
        fmt = os.environ.get("HIVIZ_FORMAT", "").strip().lower()
    as_json = fmt == "json"
    pretty = (fmt == "pretty") if fmt in ("pretty", "md", "json") else tty
    ansi = tty and os.environ.get("TERM") != "dumb" and _enable_vt(stream)
    color = False
    if pretty:
        if os.environ.get("NO_COLOR"):
            color = False
        elif os.environ.get("FORCE_COLOR"):
            color = True
        else:
            color = ansi
    try:
        _GLYPHS.encode(getattr(stream, "encoding", None) or "ascii")
        uni = True
    except (UnicodeEncodeError, LookupError):
        uni = False
    if os.environ.get("HIVIZ_ASCII"):
        uni = False
    if pretty and not uni:
        for name in ("stdout", "stderr"):
            cur = getattr(sys, name)
            if not isinstance(cur, _Folded):
                setattr(sys, name, _Folded(cur))
    _STATE.update(pretty=pretty, color=color, unicode=uni, ansi=ansi, json=as_json)
    return pretty


def is_pretty() -> bool:
    return _STATE["pretty"]


def is_json() -> bool:
    return _STATE["json"]


def dumps(obj) -> str:
    """The --format json document: ASCII-only (valid on any stream encoding), one object, indented."""
    return json.dumps(obj, indent=2, ensure_ascii=True, default=str)


def style(text: str, *names: str) -> str:
    if not _STATE["color"] or not names or not text:
        return text
    return "".join(f"\x1b[{_CODES[n]}m" for n in names) + text + "\x1b[0m"


def width(text: str) -> int:
    w = 0
    for ch in _ANSI.sub("", text):
        if unicodedata.combining(ch):
            continue
        w += 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
    return w


def term_cols() -> int:
    return max(40, shutil.get_terminal_size((100, 24)).columns)


def symbol(status: str) -> str:
    u, a, color = STATUS.get(status, ("•", "*", "gray"))
    return style(u if _STATE["unicode"] else a, color, "bold")


def badge(status: str) -> str:
    color = STATUS.get(status, ("", "", "gray"))[2]
    return f"{symbol(status)} {style(status, color)}"


def duration(sec: float) -> str:
    if sec < 1:
        return f"{sec * 1000:.0f}ms"
    if sec < 60:
        return f"{sec:.1f}s"
    m, s = divmod(int(round(sec)), 60)
    if m < 60:
        return f"{m}m{s:02d}s"
    h, m = divmod(m, 60)
    return f"{h}h{m:02d}m"


def bar(value: float, maximum: float, size: int = 10) -> str:
    full, empty = ("█", "░") if _STATE["unicode"] else ("#", ".")
    n = 0 if maximum <= 0 else min(size, max(1 if value > 0 else 0, round(size * value / maximum)))
    return style(full * n, "cyan") + style(empty * (size - n), "gray")


def heading(text: str, sub: str = "") -> str:
    return "\n" + style(text, "bold") + (style(f"  {sub}", "gray") if sub else "")


def rule(text: str = "", status: str | None = None) -> str:
    h = "━" if _STATE["unicode"] else "="
    lead = f"{symbol(status)} " if status else ""
    body = f" {lead}{style(text, 'bold')} " if text else ""
    fill = max(4, min(term_cols(), 72) - width(body) - 2)
    return style(h * 2, "gray") + body + style(h * fill, "gray")


def summary(counts: dict[str, int], order: list[str] | None = None) -> str:
    keys = order or list(counts)
    parts = [f"{symbol(k)} {counts[k]} {style(k.lower(), STATUS.get(k, ('', '', 'gray'))[2])}"
             for k in keys if counts.get(k)]
    return "   ".join(parts) or style("nothing to report", "gray")


def _pad(text: str, w: int, align: str) -> str:
    gap = max(0, w - width(text))
    return " " * gap + text if align == "r" else text + " " * gap


def table(headers: list[str], rows: list[list], align: list[str] | None = None,
          status_col: int | None = None, dim_cols: tuple[int, ...] = ()) -> str:
    """Box table; cells are plain strings (styled here). Wide columns wrap to fit the terminal."""
    n = len(headers)
    align = align or ["l"] * n
    box = _BOX_U if _STATE["unicode"] else _BOX_A
    body = [[str(c) for c in r] for r in rows]
    natural = [max([width(headers[i])] + [width(r[i]) + (2 if i == status_col else 0) for r in body])
               for i in range(n)]
    avail = term_cols() - (3 * n + 1)
    widths = natural[:]
    floor = [max(width(headers[i]), 10) for i in range(n)]
    if status_col is not None:
        floor[status_col] = natural[status_col]
    while sum(widths) > avail:
        cand = [i for i in range(n) if widths[i] > floor[i]]
        if not cand:
            break
        widths[max(cand, key=lambda i: widths[i])] -= 1

    def cell_lines(i: int, text: str) -> list[str]:
        if i == status_col:
            return [badge(text)]
        if width(text) <= widths[i]:
            lines = [text]
        else:
            lines = textwrap.wrap(text, widths[i], break_long_words=True, break_on_hyphens=False) or [""]
        return [style(l, "dim") if i in dim_cols else l for l in lines]

    def rule_line(l: str, m: str, r: str) -> str:
        return style(l + m.join(box["h"] * (w + 2) for w in widths) + r, "gray")

    v = style(box["v"], "gray")
    out = [rule_line(box["tl"], box["t"], box["tr"]),
           v + v.join(f" {_pad(style(h, 'bold'), widths[i], 'l')} " for i, h in enumerate(headers)) + v,
           rule_line(box["l"], box["x"], box["r"])]
    for r in body:
        cols = [cell_lines(i, r[i]) for i in range(n)]
        for k in range(max(len(c) for c in cols)):
            parts = [cols[i][k] if k < len(cols[i]) else "" for i in range(n)]
            out.append(v + v.join(f" {_pad(parts[i], widths[i], align[i])} " for i in range(n)) + v)
    out.append(rule_line(box["bl"], box["b"], box["br"]))
    return "\n".join(out)


class Phase:
    """One long step. On a terminal: spinner, elapsed time and an optional live hint; always
    ends with a status line. `transient` erases the spinner line instead of leaving a record."""
    FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

    def __init__(self, label: str, hint=None, budget: float | None = None,
                 transient: bool = False, stream=None):
        self.label, self.hint, self.budget, self.transient = label, hint, budget, transient
        self.stream = stream or sys.stdout
        self.status, self.note = "OK", ""
        self._live = _STATE["pretty"] and _STATE["ansi"] and _isatty(self.stream)
        self._stop = threading.Event()
        self._thread = None
        self.elapsed = 0.0

    def _line(self, frame: str) -> str:
        bits = [duration(time.monotonic() - self._t0) + (f" / {duration(self.budget)}" if self.budget else "")]
        if self.hint:
            try:
                h = self.hint()
                if h:
                    bits.append(h)
            except Exception:
                pass
        text = f"{self.label}  {' · '.join(bits)}"
        room = term_cols() - 3
        if len(text) > room:
            text = text[: room - 1] + "…"
        label, _, rest = text.partition("  ")
        return f"{style(frame, 'cyan')} {label}  {style(rest, 'gray')}"

    def _spin(self) -> None:
        frames = self.FRAMES if _STATE["unicode"] else "|/-\\"
        i = 0
        while True:
            self.stream.write("\r\x1b[K" + self._line(frames[i % len(frames)]))
            self.stream.flush()
            i += 1
            if self._stop.wait(0.1):
                return

    def __enter__(self) -> "Phase":
        self._t0 = time.monotonic()
        if self._live:
            self._thread = threading.Thread(target=self._spin, daemon=True)
            self._thread.start()
        elif not self.transient:
            print(f"  … {self.label}" + (f"  (budget {duration(self.budget)})" if self.budget else ""),
                  file=self.stream, flush=True)
        return self

    def __exit__(self, et, ev, tb) -> bool:
        self.elapsed = time.monotonic() - self._t0
        if et is not None:
            self.status, self.note = "ERROR", self.note or f"{et.__name__}: {ev}"
        if self._thread:
            self._stop.set()
            self._thread.join()
            self.stream.write("\r\x1b[K")
        if not (self.transient and self._live):
            note = f"  {style(self.note, 'gray')}" if self.note else ""
            print(f"{badge(self.status)}  {self.label}{note}  {style(duration(self.elapsed), 'gray')}",
                  file=self.stream, flush=True)
        return False
