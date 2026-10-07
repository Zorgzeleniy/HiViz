"""Negative control for constitution probes — does the answer depend on the rule's line at all?

A probe PASSes when a fresh session quotes the rule. That alone proves little: the session may say it from its own
system prompt, a global config, or because the markers are generic words. The control asks the SAME question in a copy
of the project WITHOUT the guarded line (or, for tests with no line to remove, in an empty project). If that session
meets the markers too, the probe cannot show the rule binds.

Soundness rests on three things this module takes care of:
  * the control runs in a COPY made of instruction-like files only — never `.git`, never `.hiviz/` (it holds the test
    itself) and never `*.bak-*` (they hold the very line that was removed);
  * a canary proves the harness really reads the copied file from its working directory; if it does not (the rule
    lives in a harness config dir, as with `omp --profile`), no verdict is drawn;
  * the harness is started with PWD set to the copy — tools built on Bun/Node take their cwd from $PWD, not from
    getcwd(), so `cwd=` alone silently runs the probe in the caller's directory.
Stdlib only.
"""
from __future__ import annotations

import os
import re
import secrets
import shutil
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

SKIP_DIRS = {".git", ".hg", ".svn", ".hiviz", "node_modules", "dist", "build", "target", ".venv", "venv", "__pycache__",
             ".next", ".nuxt", ".cache", ".tox", ".mypy_cache", ".pytest_cache", ".gradle", ".idea", ".vscode"}
TEXT_SUFFIX = {".md", ".mdc", ".markdown", ".txt", ".json", ".jsonc", ".toml", ".yml", ".yaml"}
TEXT_NAMES = {".cursorrules", ".windsurfrules", ".clinerules", ".aiderrc"}
APPENDABLE = {".md", ".mdc", ".markdown", ".txt"}      # a canary line can be added without breaking the format
MAX_FILE = 512 * 1024
MAX_FILES = 3000
MAX_BYTES = 24 * 1024 * 1024
NO_TOOLS = " Answer from your standing instructions only — do not read files, search, or run commands."
_BACKUP = re.compile(r"\.(bak|orig|rej)(-[\w.-]+)?$|~$|\.sw[po]$")


class Unavailable(Exception):
    """The control cannot be run soundly; the message says why and goes into the report."""


@dataclass
class Control:
    status: str            # absent | present | unavailable
    kind: str = ""         # line | project
    detail: str = ""
    excerpt: str = ""
    runs: int = 0


def is_instruction_file(p: Path) -> bool:
    return (p.suffix.lower() in TEXT_SUFFIX or p.name in TEXT_NAMES) and not _BACKUP.search(p.name)


def ablate_text(text: str, needle: str) -> tuple[str, int]:
    """Remove every line containing `needle` (case-insensitive) plus its indented continuation lines. A bare list item
    that follows is a different rule and stays. -> (new text, number of removed rules)."""
    lines, out, i, hits = text.split("\n"), [], 0, 0
    low = needle.lower()
    while i < len(lines):
        if low in lines[i].lower():
            hits += 1
            i += 1
            while (i < len(lines) and lines[i][:1] in (" ", "\t") and lines[i].strip()
                   and not re.match(r"\s*([-*+]|\d+[.)])\s", lines[i])):
                i += 1
            continue
        out.append(lines[i])
        i += 1
    return "\n".join(out), hits


def _walk(corpus: Path):
    n = total = 0
    for root, dirs, files in os.walk(corpus, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not os.path.islink(os.path.join(root, d)))
        for name in sorted(files):
            p = Path(root, name)
            if p.is_symlink() or not is_instruction_file(p):
                continue
            try:
                size = p.stat().st_size
            except OSError:
                continue
            if size > MAX_FILE:
                continue
            n += 1
            total += size
            if n > MAX_FILES or total > MAX_BYTES:
                raise Unavailable(f"more than {MAX_FILES} instruction-like files ({total // 1024 // 1024} MB) — "
                                  "point --corpus at the directory that holds the instruction files")
            yield p


def _git_init(dst: Path, like: Path) -> None:
    """The copy must look like the project to the harness: tools find their project root through git."""
    if not (like / ".git").exists() or not shutil.which("git"):
        return
    q = {"cwd": dst, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL, "timeout": 60}
    try:
        subprocess.run(["git", "init", "-q"], check=True, **q)
        subprocess.run(["git", "add", "-A"], check=True, **q)
        subprocess.run(["git", "-c", "user.name=hiviz", "-c", "user.email=hiviz@localhost", "commit", "-qm", "control",
                        "--allow-empty"], check=True, **q)
    except (OSError, subprocess.SubprocessError):
        pass


def build(corpus: Path, dst: Path, needle: str | None, mode: str, canary: str = "") -> tuple[list[str], list[str]]:
    """Fill `dst` from `corpus`. mode: ablate (needle lines removed) | canary (intact, canary line appended to every
    text file holding the needle) | empty (nothing copied). -> (text files that hold the needle, structured files that
    mention it). Structured files (json / toml / yaml) are copied untouched: cutting a line out of a config can break
    it, and a canary cannot be added; if the harness does read one as instructions the control then says "present"."""
    held: list[str] = []
    left: list[str] = []
    if mode != "empty":
        for p in _walk(corpus):
            rel = p.relative_to(corpus)
            try:
                text = p.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            if bool(needle) and needle.lower() in text.lower():
                if p.suffix.lower() in APPENDABLE or p.name in TEXT_NAMES:
                    held.append(rel.as_posix())
                    if mode == "ablate":
                        text, _ = ablate_text(text, needle)
                    else:
                        text = text.rstrip("\n") + f"\n\n- Reference token for this session: {canary}\n"
                else:
                    left.append(rel.as_posix())
            out = dst / rel
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(text, encoding="utf-8", newline="")
        if mode in ("ablate", "canary") and not held:
            raise Unavailable(f"the guarded phrase appears only in structured files ({', '.join(left)}): a canary line cannot be planted there"
                              if left else "the guarded line was not found in any instruction-like text file under --corpus")
    _git_init(dst, corpus)
    return held, left


def probe_env(cwd: Path) -> dict:
    env = dict(os.environ)
    if os.name != "nt":
        env["PWD"] = str(cwd)   # Bun/Node-based harnesses read their working directory from here
    return env


def with_note(ask: str, on: bool) -> str:
    return ask + NO_TOOLS if on and NO_TOOLS.strip() not in ask else ask


def _names(files: list[str], n: int = 3) -> str:
    return ", ".join(files[:n]) + (f" (+{len(files) - n} more)" if len(files) > n else "")


class Controller:
    """Runs controls for one suite. Canary results are cached per set of files; temp dirs die with the object.

    The samples and the canary run IN PARALLEL (a real harness takes 10-40 s per call). One sample is not enough:
    measured on a real harness, a rule-free copy still met a specific marker in 1 of 3 runs, so a PASS needs `runs`
    clean samples. The canary decides whether the comparison is valid at all: a harness that does not read the copied
    file from its working directory (it reads a config dir, as `omp --profile` does) would answer the same with or
    without the line, so neither "present" nor "absent" would mean anything.
    """

    def __init__(self, corpus: Path | None, run_probe, evaluate, needle_of, runs: int = 3, notools: bool = True):
        self.corpus, self.run_probe, self.evaluate, self.needle_of = corpus, run_probe, evaluate, needle_of
        self.runs, self.notools = max(1, runs), notools
        self._tmp: list[Path] = []
        self._canary: dict[tuple, str] = {}

    def close(self) -> None:
        for d in self._tmp:
            shutil.rmtree(d, ignore_errors=True)
        self._tmp.clear()

    def _dir(self) -> Path:
        d = Path(tempfile.mkdtemp(prefix="hiviz-control-"))
        self._tmp.append(d)
        return d

    def _canary_ok(self, harness: str, needle: str, held: list[str], timeout: float) -> str:
        """'' when the harness reads the copied file from its working directory, else the reason it was not proven."""
        key = tuple(sorted(held))
        if key not in self._canary:
            token = "HIVIZCANARY" + secrets.token_hex(4).upper()
            d = self._dir()
            try:
                build(self.corpus, d, needle, "canary", token)
            except Unavailable as e:
                self._canary[key] = str(e)
                return self._canary[key]
            ask = with_note(f"Without extra text: quote the line of your standing instructions that contains the token {token}.", self.notools)
            reason = "the harness did not report a canary planted in the copied file"
            for _ in range(2):
                answer, err = self.run_probe(harness, ask, timeout, d)
                if err:
                    reason = f"harness error: {err}"
                    break
                if token in answer:
                    reason = ""
                    break
            self._canary[key] = ("" if not reason else
                                 f"{reason} — it does not read {', '.join(held)} from its working directory "
                                 "(a harness config dir, a profile?), so a copy cannot be compared")
        return self._canary[key]

    def check(self, t: dict, harness: str, timeout: float) -> Control:
        if self.corpus is None:
            return Control("unavailable", detail="no --corpus: nothing to copy")
        needle = self.needle_of(t)
        try:
            copies, held, left = [], [], []
            for _ in range(self.runs):   # one copy per sample: concurrent sessions never share a directory
                d = self._dir()
                held, left = build(self.corpus, d, needle, "ablate" if needle else "empty")
                copies.append(d)
        except Unavailable as e:
            return Control("unavailable", detail=str(e))
        except OSError as e:
            return Control("unavailable", detail=f"could not prepare the copy: {e}"[:160])
        kind, what = (("line", f"without the line in {_names(held)}"
                       + (f" (also mentioned in {_names(left)}, left as is)" if left else "")) if needle else ("project", "in an empty project"))
        ask = with_note(t["ask"], self.notools)
        with ThreadPoolExecutor(max_workers=len(copies) + 1) as pool:
            canary = pool.submit(self._canary_ok, harness, needle, held, timeout) if needle else None   # cached per file set
            samples = list(pool.map(lambda d: self.run_probe(harness, ask, timeout, d), copies))
            bad = canary.result() if canary else ""
        if bad:   # whatever the samples said, a harness that never read the copy cannot be compared with it
            return Control("unavailable", kind, bad, runs=len(samples))
        good = [(a, e) for a, e in samples if not e]
        for answer, _ in good:
            ok, _ = self.evaluate(answer, t)
            if ok:
                excerpt = " ".join(answer.split())[:140]
                return Control("present", kind, f"the same question {what} also met the markers", excerpt, len(samples))
        if not good:
            return Control("unavailable", kind, f"harness error in every control run: {samples[0][1]}", runs=len(samples))
        n = len(good)
        return Control("absent", kind, f"the same question {what} did not meet the markers ({n} run{'s' if n > 1 else ''})", runs=len(samples))
