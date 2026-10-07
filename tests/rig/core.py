"""Shared rig state and helpers: paths, result collection, subprocess runner, fake-HOME helpers, browser driver."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "render"))   # hvfmt, report
import hvfmt  # noqa: E402

REPO = Path(__file__).resolve().parent.parent.parent


HOME = Path.home()


OUT = REPO / "tests" / "out"


GT = json.loads((REPO / "tests" / "ground_truth.json").read_text(encoding="utf-8"))


RESULTS: list[tuple[str, bool, str]] = []


_GROUP = [""]


GROUPS: list[str] = []


_SECTION: list[str | None] = [None]


def group_of(name: str) -> str:
    return re.split(r"[ :\[]", name, maxsplit=1)[0]


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, ok, detail))
    GROUPS.append(_SECTION[0] or group_of(name))
    if not hvfmt.is_pretty():
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
        return
    g = GROUPS[-1]
    if g != _GROUP[0]:
        _GROUP[0] = g
        print(hvfmt.style(f"  {g}", "bold"))
    m = None if _SECTION[0] else re.match(rf"{re.escape(g)}( \[[^\]]+\])?: (.*)$", name)
    label = f"{m.group(1).strip() + ' ' if m.group(1) else ''}{m.group(2)}" if m else name
    line = f"    {hvfmt.symbol('PASS' if ok else 'FAIL')} {label}"
    if not ok:  # passing checks stay quiet; their detail is in the md output / failures table
        first = next((l.strip() for l in detail.splitlines() if l.strip()), "")
        room = hvfmt.term_cols() - hvfmt.width(line) - 4
        if first and room > 12:
            line += "  " + hvfmt.style(first if len(first) <= room else first[: room - 1] + "…", "red")
    print(line)


def sh(cmd: list[str], timeout: int = 120, cwd: Path = REPO, **kw) -> subprocess.CompletedProcess:
    exe = shutil.which(cmd[0])  # Windows: npm is npm.cmd, node-installed CLIs need resolving
    if exe:
        cmd = [exe, *cmd[1:]]
    try:
        return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=timeout, **kw)
    except subprocess.TimeoutExpired as e:
        out = ((e.stdout or b"").decode("utf-8", "replace") if isinstance(e.stdout, bytes) else (e.stdout or ""))
        return subprocess.CompletedProcess(cmd, 124, "", f"TIMEOUT after {timeout}s; partial stdout: {out[-300:]}")


def templated_copy(src: Path, dst: Path) -> None:
    """Copy a fixture tree, rendering {{REPO}} into the absolute repo path."""
    repo_abs = str(REPO.resolve()).replace("\\", "/")
    for f in sorted(src.rglob("*")):
        if f.is_file():
            d = dst / f.relative_to(src)
            d.parent.mkdir(parents=True, exist_ok=True)
            d.write_text(f.read_text(encoding="utf-8").replace("{{REPO}}", repo_abs), encoding="utf-8")


HARNESS_ENV = ("CLAUDE_CONFIG_DIR", "CODEX_HOME", "PI_CODING_AGENT_DIR", "XDG_CONFIG_HOME",
               "HIVIZ_HARNESS", "CLAUDECODE")


def home_env(home: Path, **extra: str) -> dict:
    """Environment of a fake machine: HOME/USERPROFILE point at `home`, no inherited harness overrides."""
    env = {k: v for k, v in os.environ.items() if k not in HARNESS_ENV}
    env.update(HOME=str(home), USERPROFILE=str(home), **extra)
    return env


def fresh_home(name: str) -> Path:
    home = OUT / "homes" / name
    shutil.rmtree(home, ignore_errors=True)
    home.mkdir(parents=True)
    return home


def engine_dirs() -> list[str]:
    """The engine directories the installer ships — one source of truth: ENGINE_DIRS in bin/hiviz.js."""
    m = re.search(r"const ENGINE_DIRS = \[([^\]]*)\]", (REPO / "bin/hiviz.js").read_text(encoding="utf-8"))
    return re.findall(r'"([^"]+)"', m.group(1)) if m else []


def find_browser() -> str | None:
    cands = ["google-chrome", "chromium", "chromium-browser", "chrome", "msedge"]
    for var in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
        root = os.environ.get(var)
        if root:
            cands += [str(Path(root) / "Google/Chrome/Application/chrome.exe"),
                      str(Path(root) / "Microsoft/Edge/Application/msedge.exe")]
    return next((b for b in cands if shutil.which(b)), None)


def browser_export(page: str, drive_js: str) -> str | None:
    """Open the report page headless, run `drive_js` (clicks), return the decisions.md preview the page built.
    None = no browser or no DOM. A fresh localStorage key per run (the page persists decisions)."""
    import html as _h
    browser = find_browser()
    if not browser:
        return None
    fresh = re.sub(r'"key": "[0-9a-f]+"', f'"key": "t{time.time_ns()}"', page, count=1)
    drv = OUT / "report_drive.html"
    drv.write_text(fresh.replace("</body>", drive_js + "</body>"), encoding="utf-8")
    # no --user-data-dir: a custom profile dir hangs headless Chrome in some sandboxes
    dom = sh([browser, "--headless=new", "--no-sandbox", "--disable-gpu", "--virtual-time-budget=4000",
              "--dump-dom", drv.as_uri()], timeout=60)
    if dom.returncode == 124 or not (dom.stdout or "").strip():
        return None
    m = re.search(r"<pre id=\"prev\">(.*?)</pre>", dom.stdout, re.S)
    return _h.unescape(m.group(1)) if m else ""


def summary(elapsed: float = 0.0) -> int:
    failed = [r for r in RESULTS if not r[1]]
    if not hvfmt.is_pretty():
        print(f"\n== {len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed ==")
        return 1 if failed else 0
    groups: dict[str, list[bool]] = {}
    for (_name, ok, _), g in zip(RESULTS, GROUPS, strict=True):
        groups.setdefault(g, []).append(ok)
    rows = [["PASS" if all(v) else "FAIL", g, f"{sum(v)}/{len(v)}",
             hvfmt.bar(sum(v), len(v))] for g, v in groups.items()]
    print(hvfmt.heading("results"))
    print(hvfmt.table(["", "group", "passed", "progress"], rows, status_col=0, align=["l", "l", "r", "l"]))
    if failed:
        print(hvfmt.heading("failures"))
        print(hvfmt.table(["check", "detail"], [[n, " ".join(d.split()) or "—"] for n, _, d in failed]))
    total = len(RESULTS)
    print("\n" + hvfmt.rule(f"{total - len(failed)}/{total} checks passed · {hvfmt.duration(elapsed)}",
                           "FAIL" if failed else "PASS"))
    return 1 if failed else 0
