"""Real agent CLIs the rig can talk to — one entry per harness.

Two independent jobs, so a harness can be covered even when nobody can run a model through it:
  discover  ask the REAL CLI which skills/commands it sees (no model, no credentials) -> T1 "harness discovery"
  argv      headless one-shot command for T2 model runs — only where the author actually ran it

Adding a harness to T2: give its entry an `argv` (and `skills_dir` / `extras` if it needs them) and run
`python tests/run.py --t2x` with HIVIZ_T2_HARNESS=<name>. Things a new adapter has to get right (RUNBOOK):
the CLI must edit files without asking, the apply step starts nested headless probes (needs network and
process spawning from inside the CLI's own sandbox), and RULES.md must reach the model (omp and opencode
load it, pi/codex read only AGENTS.md).
"""
from __future__ import annotations

import json
import os
import queue
import shutil
import subprocess
import tempfile
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .core import home_env

OMP_PROFILE = "hiviz-test"   # the isolated omp profile the T2 sandbox lives in
_KEYS = ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "OPENROUTER_API_KEY", "ZAI_API_KEY", "OPENCODE_API_KEY")


def harness_env(home: Path) -> dict:
    """Environment of a fake machine for ANY harness CLI: every config/data dir inside `home`, no credentials."""
    # Only XDG dirs are pinned. CODEX_HOME / PI_CODING_AGENT_DIR / CLAUDE_CONFIG_DIR are REMOVED (home_env), not set:
    # omp also honors PI_CODING_AGENT_DIR as its agent dir, so setting it for pi hid omp's skills.
    env = home_env(home, XDG_CONFIG_HOME=str(home / ".config"), XDG_DATA_HOME=str(home / ".local/share"),
                   XDG_CACHE_HOME=str(home / ".cache"))
    for k in _KEYS:
        env.pop(k, None)
    (home / ".codex").mkdir(parents=True, exist_ok=True)   # codex insists on its home directory existing
    return env


class _Jsonl:
    """A child process speaking one JSON object per line (reader thread: select() does not work on Windows pipes)."""

    def __init__(self, argv: list[str], env: dict, cwd: Path):
        exe = shutil.which(argv[0]) or argv[0]
        self._err = tempfile.TemporaryFile()   # a file, not a pipe: nobody drains it, and it explains an early exit
        self.p = subprocess.Popen([exe, *argv[1:]], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=self._err, text=True, encoding="utf-8", errors="replace",
                                  env=env, cwd=cwd)
        self.q: queue.Queue = queue.Queue()
        threading.Thread(target=self._pump, daemon=True).start()

    def _pump(self) -> None:
        for line in self.p.stdout:
            try:
                self.q.put(json.loads(line))
            except ValueError:
                continue
        self.q.put(None)

    def send(self, obj: dict) -> None:
        self.p.stdin.write(json.dumps(obj) + "\n")
        self.p.stdin.flush()

    def recv(self, match: Callable[[dict], bool], timeout: float) -> dict:
        import time
        end = time.monotonic() + timeout
        while True:
            try:
                msg = self.q.get(timeout=max(0.1, end - time.monotonic()))
            except queue.Empty:
                raise TimeoutError("no matching message from the CLI") from None
            if msg is None:
                self._err.seek(0)
                tail = " ".join(self._err.read().decode("utf-8", "replace").split())[-220:]
                raise RuntimeError("the CLI exited before answering" + (f": {tail}" if tail else ""))
            if match(msg):
                return msg
            if time.monotonic() > end:
                raise TimeoutError("no matching message from the CLI")

    def close(self) -> None:
        self.p.kill()
        self.p.wait()
        self._err.close()


# ---- discovery: names the real CLI lists (skills, plus slash commands for Claude Code)
def _opencode(home: Path, cwd: Path, profile: str | None = None) -> set[str]:
    # `opencode debug skill` truncates its output at exactly 64 KiB when stdout is a pipe (the T2 sandbox lists 20+
    # skills = 260 KB), so it writes to a file, which is complete.
    out = home / "opencode-skills.json"
    with open(out, "wb") as fh:
        r = subprocess.run([shutil.which("opencode") or "opencode", "debug", "skill"], stdout=fh, stderr=subprocess.PIPE,
                           env=harness_env(home), cwd=cwd, timeout=120)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.decode("utf-8", "replace")[-200:] or f"exit {r.returncode}")
    return {s["name"] for s in json.loads(out.read_text(encoding="utf-8"))}


def _pi(home: Path, cwd: Path, profile: str | None = None) -> set[str]:
    j = _Jsonl(["pi", "--mode", "rpc", "--no-session"], harness_env(home), cwd)
    try:
        j.send({"id": "1", "type": "get_commands"})
        r = j.recv(lambda m: m.get("type") == "response" and m.get("command") == "get_commands", 60)
        return {c["name"].removeprefix("skill:") for c in r["data"]["commands"] if c.get("source") == "skill"}
    finally:
        j.close()


def _codex(home: Path, cwd: Path, profile: str | None = None) -> set[str]:
    j = _Jsonl(["codex", "app-server"], harness_env(home), cwd)
    try:
        j.send({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                "params": {"clientInfo": {"name": "hiviz-rig", "version": "0"}}})
        j.recv(lambda m: m.get("id") == 1, 60)
        j.send({"jsonrpc": "2.0", "method": "initialized"})
        j.send({"jsonrpc": "2.0", "id": 2, "method": "skills/list",
                "params": {"cwds": [str(cwd)], "forceReload": True}})
        r = j.recv(lambda m: m.get("id") == 2, 60)
        return {s["name"] for d in r["result"]["data"] for s in d["skills"] if s.get("enabled", True)}
    finally:
        j.close()


def _claude(home: Path, cwd: Path, profile: str | None = None) -> set[str]:
    """The stream-json `init` event lists commands and skills BEFORE the first model call; kill right after it."""
    j = _Jsonl(["claude", "-p", "hi", "--output-format", "stream-json", "--verbose", "--no-session-persistence"],
               harness_env(home), cwd)
    try:
        r = j.recv(lambda m: m.get("type") == "system" and m.get("subtype") == "init", 90)
        return set(r.get("slash_commands") or []) | set(r.get("skills") or [])
    finally:
        j.close()


def _omp(home: Path, cwd: Path, profile: str | None = None) -> set[str]:
    """omp's RPC `get_available_commands` lists skills as `skill:<name>`. omp refuses to start without a default
    model, so it gets a placeholder key; nothing is sent to a provider because no prompt is ever submitted."""
    env = harness_env(home)
    env["ANTHROPIC_API_KEY"] = "sk-ant-placeholder-never-sent"
    argv = ["omp", *(["--profile", profile] if profile else []), "--mode", "rpc", "--no-session"]
    j = _Jsonl(argv, env, cwd)
    try:
        j.send({"id": "1", "type": "get_available_commands"})
        r = j.recv(lambda m: m.get("id") == "1" and m.get("type") == "response", 90)
        if not r.get("success"):
            raise RuntimeError(r.get("error", "get_available_commands failed"))
        return {c["name"].removeprefix("skill:") for c in r["data"]["commands"] if c.get("source") == "skill"}
    finally:
        j.close()


# ---- model runs (only what has been run end to end)
def _omp_run(prompt: str, sandbox: Path, model: str) -> list[str]:
    return ["omp", "--profile", OMP_PROFILE, "-p", prompt]


def _opencode_run(prompt: str, sandbox: Path, model: str) -> list[str]:
    return ["opencode", "run", "-m", model, "--dir", str(sandbox), "--auto", prompt]


@dataclass(frozen=True)
class Harness:
    name: str
    cli: str
    discover: Callable[[Path, Path, str | None], set[str]] | None = None   # (fake home, cwd, profile) -> names the CLI lists
    commands: bool = False                                     # hiviz installs slash COMMANDS for it (Claude Code)
    argv: Callable[[str, Path, str], list[str]] | None = None  # (prompt, sandbox, model) -> command
    skills_dir: str | None = None                              # project-local skills dir the T2 sandbox fills
    profile: str | None = None                                 # isolated profile the T2 sandbox lives in (omp)
    sandbox_dir: Callable[[Path, Path], Path] | None = None    # (fake home, project) -> where the T2 sandbox is built
    extras: dict[str, str] = field(default_factory=dict)       # extra sandbox files the harness needs


HARNESSES: dict[str, Harness] = {h.name: h for h in (
    Harness("omp", "omp", discover=_omp, argv=_omp_run, profile=OMP_PROFILE,
            sandbox_dir=lambda home, project: home / ".omp/profiles" / OMP_PROFILE / "agent"),
    Harness("opencode", "opencode", discover=_opencode, argv=_opencode_run, skills_dir=".agents/skills",
            extras={"opencode.json": '{"instructions": ["RULES.md"]}\n'}),
    Harness("claude", "claude", discover=_claude, commands=True, skills_dir=".claude/skills"),
    Harness("codex", "codex", discover=_codex, skills_dir=".agents/skills"),
    Harness("pi", "pi", discover=_pi, skills_dir=".agents/skills"),
)}


def cli_version(h: Harness) -> str:
    exe = shutil.which(h.cli)
    if not exe:
        return ""
    r = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=60, env={**os.environ})
    return " ".join((r.stdout or r.stderr).split())[:40]
