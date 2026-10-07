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
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .core import home_env, sh

_KEYS = ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "OPENROUTER_API_KEY", "ZAI_API_KEY", "OPENCODE_API_KEY")


def harness_env(home: Path) -> dict:
    """Environment of a fake machine for ANY harness CLI: every config/data dir inside `home`, no credentials."""
    env = home_env(home, XDG_CONFIG_HOME=str(home / ".config"), XDG_DATA_HOME=str(home / ".local/share"),
                   XDG_CACHE_HOME=str(home / ".cache"), CODEX_HOME=str(home / ".codex"),
                   PI_CODING_AGENT_DIR=str(home / ".pi/agent"), CLAUDE_CONFIG_DIR=str(home / ".claude"))
    for k in _KEYS:
        env.pop(k, None)
    (home / ".codex").mkdir(parents=True, exist_ok=True)   # codex refuses to start when CODEX_HOME does not exist
    return env


class _Jsonl:
    """A child process speaking one JSON object per line (reader thread: select() does not work on Windows pipes)."""

    def __init__(self, argv: list[str], env: dict, cwd: Path):
        exe = shutil.which(argv[0]) or argv[0]
        self.p = subprocess.Popen([exe, *argv[1:]], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace",
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
                raise RuntimeError("the CLI exited before answering")
            if match(msg):
                return msg
            if time.monotonic() > end:
                raise TimeoutError("no matching message from the CLI")

    def close(self) -> None:
        self.p.kill()
        self.p.wait()


# ---- discovery: names the real CLI lists (skills, plus slash commands for Claude Code)
def _opencode(home: Path, cwd: Path) -> set[str]:
    r = sh(["opencode", "debug", "skill"], env=harness_env(home), cwd=cwd, timeout=120)
    return {s["name"] for s in json.loads(r.stdout)}


def _pi(home: Path, cwd: Path) -> set[str]:
    j = _Jsonl(["pi", "--mode", "rpc", "--no-session"], harness_env(home), cwd)
    try:
        j.send({"id": "1", "type": "get_commands"})
        r = j.recv(lambda m: m.get("type") == "response" and m.get("command") == "get_commands", 60)
        return {c["name"].removeprefix("skill:") for c in r["data"]["commands"] if c.get("source") == "skill"}
    finally:
        j.close()


def _codex(home: Path, cwd: Path) -> set[str]:
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


def _claude(home: Path, cwd: Path) -> set[str]:
    """The stream-json `init` event lists commands and skills BEFORE the first model call; kill right after it."""
    j = _Jsonl(["claude", "-p", "hi", "--output-format", "stream-json", "--verbose", "--no-session-persistence"],
               harness_env(home), cwd)
    try:
        r = j.recv(lambda m: m.get("type") == "system" and m.get("subtype") == "init", 90)
        return set(r.get("slash_commands") or []) | set(r.get("skills") or [])
    finally:
        j.close()


# ---- model runs (only what has been run end to end)
def _omp(prompt: str, sandbox: Path, model: str) -> list[str]:
    return ["omp", "--profile", "hiviz-test", "-p", prompt]


def _opencode_run(prompt: str, sandbox: Path, model: str) -> list[str]:
    return ["opencode", "run", "-m", model, "--dir", str(sandbox), "--auto", prompt]


@dataclass(frozen=True)
class Harness:
    name: str
    cli: str
    discover: Callable[[Path, Path], set[str]] | None = None   # (fake home, cwd) -> names the CLI lists
    commands: bool = False                                     # hiviz installs slash COMMANDS for it (Claude Code)
    argv: Callable[[str, Path, str], list[str]] | None = None  # (prompt, sandbox, model) -> command
    skills_dir: str | None = None                              # project-local skills dir the T2 sandbox fills
    extras: dict[str, str] = field(default_factory=dict)       # extra sandbox files the harness needs


HARNESSES: dict[str, Harness] = {h.name: h for h in (
    Harness("omp", "omp", argv=_omp),
    Harness("opencode", "opencode", discover=_opencode, argv=_opencode_run, skills_dir=".agents/skills",
            extras={"opencode.json": '{"instructions": ["RULES.md"]}\n'}),
    Harness("claude", "claude", discover=_claude, commands=True, skills_dir=".claude/skills"),
    Harness("codex", "codex", discover=_codex, skills_dir=".agents/skills"),
    Harness("pi", "pi", discover=_pi, skills_dir=".agents/skills"),
    Harness("cursor", "cursor-agent"),
    Harness("windsurf", "windsurf"),
)}


def cli_version(h: Harness) -> str:
    exe = shutil.which(h.cli)
    if not exe:
        return ""
    r = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=60, env={**os.environ})
    return " ".join((r.stdout or r.stderr).split())[:40]
