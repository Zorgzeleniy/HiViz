#!/usr/bin/env python3
"""hiviz T2 — audit -> apply -> probes, end to end, on real harness CLIs.

Every harness runs hermetically: its own fake $HOME and project dir (outside the repo),
hiviz installed there by `bin/hiviz.js init`, the fixture corpus planted where that harness
reads instructions, and ZAI_API_KEY as the only credential. The console shows progress only;
full transcripts and reports land in tests/out/t2/<harness>/.

Usage: python tests/t2.py [--harness omp,pi,claude,codex,opencode,cursor] [--model glm-5.3-flash]
Env:   ZAI_API_KEY (required) · HIVIZ_T2_PATH (extra dirs searched for the CLIs) ·
       HIVIZ_REUSE=1 (keep an existing report.md and skip the audit) · NO_COLOR
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "tests" / "out" / "t2"
SANDBOX = Path(os.environ.get("HIVIZ_T2_DIR") or Path(tempfile.gettempdir()) / "hiviz-t2")
GT = json.loads((REPO / "tests" / "ground_truth.json").read_text(encoding="utf-8"))
FIXTURE = REPO / "tests" / "fixture" / "agent"
VENDOR = REPO / "tests" / "fixture" / "vendor"
KEY = "ZAI_API_KEY"
DEFAULT_MODEL = "glm-5.3-flash"
TIMEOUTS = {"preflight": 180, "audit": 1500, "apply": 2400}
# inherited settings that would leak the developer's real setup into the sandbox
STRIP_ENV = ("CLAUDE_CONFIG_DIR", "CODEX_HOME", "PI_CODING_AGENT_DIR", "XDG_CONFIG_HOME", "XDG_DATA_HOME",
             "XDG_STATE_HOME", "XDG_CACHE_HOME", "HIVIZ_HARNESS", "CLAUDECODE", "OMP_PROFILE", "PI_PROFILE",
             "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL", "OPENAI_API_KEY",
             "OPENAI_BASE_URL", "ZHIPU_API_KEY")
AUTH_RE = re.compile(r"\b40[13]\b|unauthori[sz]ed|authenticat|api key|token expired|invalid.{0,20}(key|token)", re.I)
SKIPPED_ALWAYS = {"windsurf": "no headless CLI"}


def clean_error(msg: str) -> str:
    """One readable line: providers embed JSON bodies and newlines in their error strings."""
    lines = [ln for ln in str(msg or "").splitlines() if ln.strip()]
    msg = " ".join(lines[0].split()) if lines else ""  # later lines repeat the first (omp)
    m = re.search(r'"message"\s*:\s*"([^"]+)"', msg)
    if m:
        code = re.search(r'"(?:code|status)"\s*:\s*"?(\d{3})', msg) or re.match(r"(\d{3})\b", msg)
        msg = f"{code.group(1)} {m.group(1)}" if code else m.group(1)
    return msg[:200]


# ---------------------------------------------------------------- console
class Console:
    """Progress-only output: one live line per running phase on a TTY, heartbeats otherwise."""

    def __init__(self, stream=None):
        stream = stream or sys.stdout
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
        self.s = stream
        self.tty = stream.isatty()
        self.uni = "utf" in (getattr(stream, "encoding", "") or "").lower()
        self.color = (self.tty and not os.environ.get("NO_COLOR")
                      and (os.name != "nt" or bool(os.environ.get("WT_SESSION") or os.environ.get("TERM_PROGRAM"))))
        self.mark = {True: "✓" if self.uni else "ok", False: "✗" if self.uni else "FAIL",
                     None: "–" if self.uni else "--"}
        self.frames = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏" if self.uni else "|/-\\"
        self.rule = "─" if self.uni else "-"
        self._lock = threading.Lock()
        self._live = 0

    def paint(self, text: str, ok: bool | None) -> str:
        if not self.color:
            return text
        return f"\x1b[{ {True: '32', False: '31', None: '2'}[ok] }m{text}\x1b[0m"

    def dim(self, text: str) -> str:
        return f"\x1b[2m{text}\x1b[0m" if self.color else text

    def _clear(self) -> None:
        if self._live:
            self.s.write("\r" + " " * self._live + "\r")
            self._live = 0

    def line(self, text: str = "") -> None:
        with self._lock:
            self._clear()
            self.s.write(text + "\n")
            self.s.flush()

    def live(self, text: str) -> None:
        if not self.tty:
            return
        text = text[:max(20, shutil.get_terminal_size((100, 20)).columns - 1)]
        with self._lock:
            self._clear()
            self.s.write(text)
            self.s.flush()
            self._live = len(text)


def clock(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"


def human(n: int) -> str:
    return f"{n / 1e6:.1f}M" if n >= 1e6 else f"{n / 1e3:.0f}k" if n >= 1e3 else str(n)


class Phase:
    """A running step: spinner + elapsed + status on a TTY, a heartbeat line every minute otherwise."""

    def __init__(self, con: Console, label: str, name: str, status=lambda: "", heartbeat: float = 60.0):
        self.con, self.label, self.name, self.status = con, label, name, status
        self.t0 = time.monotonic()
        self._stop = threading.Event()
        self._beat = heartbeat
        self._thread = threading.Thread(target=self._tick, daemon=True)
        self._thread.start()

    def head(self) -> str:
        return f"{self.label}  {self.name:<9}"

    def elapsed(self) -> float:
        return time.monotonic() - self.t0

    def _tick(self) -> None:
        i, last = 0, time.monotonic()
        while not self._stop.wait(0.2 if self.con.tty else 1.0):
            if self.con.tty:
                frame = self.con.frames[i % len(self.con.frames)]
                self.con.live(f"{self.head()} {frame} {clock(self.elapsed()):>6}  {self.status()}")
                i += 1
            elif time.monotonic() - last >= self._beat:
                self.con.line(f"{self.head()} … {clock(self.elapsed()):>6}  {self.status()}")
                last = time.monotonic()

    def done(self, ok: bool | None, detail: str = "") -> float:
        self._stop.set()
        self._thread.join()
        took = self.elapsed()
        self.con.line(f"{self.head()} {self.con.paint(self.con.mark[ok], ok)} {clock(took):>6}  {detail}")
        return took


# ---------------------------------------------------------------- agent stream stats
@dataclass
class Stats:
    tool_calls: int = 0
    last_tool: str = ""
    tokens_in: int = 0
    tokens_out: int = 0
    cost: float | None = None
    turns: int = 0
    text: str = ""
    error: str = ""
    fatal: str = ""
    rc: int | None = None
    timed_out: bool = False

    def add_cost(self, c) -> None:
        if isinstance(c, (int, float)) and c > 0:
            self.cost = (self.cost or 0.0) + c

    def fail(self, msg: str) -> None:
        self.error = clean_error(msg) or "agent error"
        if AUTH_RE.search(self.error):
            self.fatal = self.error

    def brief(self) -> str:
        parts = [f"{self.tool_calls} tools"]
        if self.tokens_in or self.tokens_out:
            parts.append(f"{human(self.tokens_in)}/{human(self.tokens_out)} tok")
        if self.cost:
            parts.append(f"${self.cost:.2f}")
        return " · ".join(parts)


def parse_pi_family(ev: dict, st: Stats) -> None:
    """omp and pi: --mode json emits message_start/message_end with pi-ai usage blocks."""
    if ev.get("type") != "message_end":
        return
    msg = ev.get("message") or {}
    if msg.get("role") != "assistant":
        return
    st.turns += 1
    u = msg.get("usage") or {}
    st.tokens_in += (u.get("input") or 0) + (u.get("cacheRead") or 0)
    st.tokens_out += u.get("output") or 0
    st.add_cost((u.get("cost") or {}).get("total"))
    for c in msg.get("content") or []:
        if not isinstance(c, dict):
            continue
        if c.get("type") == "toolCall":
            st.tool_calls += 1
            st.last_tool = str(c.get("name", ""))
        elif c.get("type") == "text" and str(c.get("text", "")).strip():
            st.text = c["text"]
    if msg.get("stopReason") == "error":  # pi exits 0 on provider errors — this is the only signal
        st.fail(msg.get("errorMessage") or "provider error")


def parse_claude(ev: dict, st: Stats) -> None:
    """Claude Code --output-format stream-json (also cursor-agent, which mirrors it)."""
    t = ev.get("type")
    if t == "assistant":
        for c in (ev.get("message") or {}).get("content") or []:
            if isinstance(c, dict) and c.get("type") == "tool_use":
                st.tool_calls += 1
                st.last_tool = str(c.get("name", ""))
            elif isinstance(c, dict) and c.get("type") == "text" and str(c.get("text", "")).strip():
                st.text = c["text"]
    elif t == "tool_call" and ev.get("subtype") == "started":  # cursor-agent
        st.tool_calls += 1
        st.last_tool = next(iter((ev.get("tool_call") or {}).keys()), "tool").replace("ToolCall", "")
    elif t == "system" and ev.get("subtype") == "api_retry":
        st.error = clean_error(f"{ev.get('error_status')} {ev.get('error')}")
        if ev.get("error_status") in (401, 403):  # Claude would retry 10 times with backoff
            st.fatal = st.error
    elif t == "result":
        u = ev.get("usage") or {}
        st.tokens_in = ((u.get("input_tokens") or 0) + (u.get("cache_read_input_tokens") or 0)
                        + (u.get("cache_creation_input_tokens") or 0)) or st.tokens_in
        st.tokens_out = (u.get("output_tokens") or 0) or st.tokens_out
        st.turns = ev.get("num_turns") or st.turns
        # total_cost_usd is Anthropic list pricing even when the model is GLM — not shown
        if ev.get("is_error"):
            st.fail(str(ev.get("result") or ev.get("subtype") or "error"))
        elif ev.get("result"):
            st.text = str(ev["result"])


def parse_codex(ev: dict, st: Stats) -> None:
    """codex exec --json: thread/turn/item events; usage per turn, no cost."""
    t = ev.get("type")
    item = ev.get("item") or {}
    if t == "item.completed":
        kind = item.get("type")
        if kind in ("command_execution", "file_change", "mcp_tool_call", "web_search"):
            st.tool_calls += 1
            st.last_tool = {"command_execution": "shell", "file_change": "patch"}.get(kind, kind)
        elif kind == "agent_message" and str(item.get("text", "")).strip():
            st.text = item["text"]
    elif t == "turn.completed":
        u = ev.get("usage") or {}
        st.turns += 1
        st.tokens_in += u.get("input_tokens") or 0
        st.tokens_out += u.get("output_tokens") or 0
    elif t in ("turn.failed", "error"):
        st.fail(str(ev.get("message") or (ev.get("error") or {}).get("message") or t))


def parse_opencode(ev: dict, st: Stats) -> None:
    """opencode run --format json: step_start/text/tool_use/step_finish/error."""
    t = ev.get("type")
    part = ev.get("part") or {}
    if t == "tool_use":
        st.tool_calls += 1
        st.last_tool = str(part.get("tool", ""))
    elif t == "text" and str(part.get("text", "")).strip():
        st.text = part["text"]
    elif t == "step_finish":
        tk = part.get("tokens") or {}
        st.turns += 1
        st.tokens_in += (tk.get("input") or 0) + ((tk.get("cache") or {}).get("read") or 0)
        st.tokens_out += tk.get("output") or 0
        st.add_cost(part.get("cost"))
    elif t == "error":
        err = ev.get("error") or {}
        data = err.get("data") or {}
        st.fail(f"{data.get('statusCode') or ''} {data.get('message') or err.get('name') or 'error'}")


# ---------------------------------------------------------------- harnesses
def q(p: str) -> str:
    return f'"{p}"' if " " in p else p


@dataclass
class Harness:
    """How one harness is installed into, configured, launched and parsed."""
    id: str
    exe: str
    parse: object
    project_file: str = "AGENTS.md"
    project_skills: str = ".agents/skills"
    skill_ref: str = "skill"
    model: str = DEFAULT_MODEL
    path: str = ""
    extra_creds: tuple = ()
    bin: str = field(default="", init=False)

    def find(self) -> str:
        found = shutil.which(self.exe, path=self.path)
        if not found:
            return f"{self.exe} not on PATH"
        missing = [k for k in self.extra_creds if not os.environ.get(k)]
        if missing:
            return f"{', '.join(missing)} not set"
        self.bin = found
        return ""

    # -- layout
    def marker(self, home: Path) -> Path:
        return {"omp": home / ".omp/agent", "pi": home / ".pi/agent", "claude": home / ".claude",
                "codex": home / ".codex", "opencode": home / ".config/opencode", "cursor": home / ".cursor"}[self.id]

    def rules_file(self, home: Path, work: Path) -> Path:
        """Where the safety rules live: the harness's user-level instruction file."""
        return {"omp": home / ".omp/agent/RULES.md", "pi": home / ".pi/agent/AGENTS.md",
                "claude": home / ".claude/CLAUDE.md", "codex": home / ".codex/AGENTS.md",
                "opencode": home / ".config/opencode/AGENTS.md",
                # Cursor keeps user rules in the cloud — an always-applied project rule instead
                "cursor": work / ".cursor/rules/rules.mdc"}[self.id]

    def adapter(self, home: Path, step: str) -> Path:
        if self.id == "claude":
            return home / f".claude/commands/hv-{step}.md"
        if self.id == "omp":
            return home / f".omp/agent/skills/hv-{step}/SKILL.md"
        return home / f".agents/skills/hv-{step}/SKILL.md"

    def corpus(self, home: Path, work: Path) -> dict[str, Path]:
        skills = work / self.project_skills
        return {"AGENTS.md": work / self.project_file, "RULES.md": self.rules_file(home, work),
                "skills/smelly-skill/SKILL.md": skills / "smelly-skill/SKILL.md",
                "skills/clean-skill/SKILL.md": skills / "clean-skill/SKILL.md"}

    # -- process
    def env(self, home: Path) -> dict:
        env = {k: v for k, v in os.environ.items() if k not in STRIP_ENV}
        env.update(HOME=str(home), USERPROFILE=str(home), PATH=self.path)
        key = os.environ.get(KEY, "")
        if self.id == "claude":
            env.update(ANTHROPIC_BASE_URL="https://api.z.ai/api/anthropic", ANTHROPIC_AUTH_TOKEN=key,
                       ANTHROPIC_DEFAULT_OPUS_MODEL=self.model, ANTHROPIC_DEFAULT_SONNET_MODEL=self.model,
                       ANTHROPIC_DEFAULT_HAIKU_MODEL=self.model, DISABLE_AUTOUPDATER="1",
                       CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC="1")
            if hasattr(os, "geteuid") and os.geteuid() == 0:
                env["IS_SANDBOX"] = "1"  # Claude refuses to bypass permissions as root otherwise
        elif self.id == "codex":
            env["CODEX_HOME"] = str(home / ".codex")
        elif self.id == "opencode":
            env.update(XDG_CONFIG_HOME=str(home / ".config"), XDG_DATA_HOME=str(home / ".local/share"),
                       XDG_STATE_HOME=str(home / ".local/state"), ZHIPU_API_KEY=key,
                       OPENCODE_DISABLE_AUTOUPDATE="1")
        return env

    def configure(self, home: Path) -> None:
        if self.id != "codex":
            return
        cdir = home / ".codex"
        cdir.mkdir(parents=True, exist_ok=True)
        # z.ai serves Codex over the Responses API; the catalog declares the model to Codex
        (cdir / "models.json").write_text(json.dumps({"models": [{
            "slug": self.model, "display_name": self.model, "description": "Z.ai GLM",
            "default_reasoning_level": "high",
            "supported_reasoning_levels": [{"effort": e, "description": e} for e in ("low", "high", "max")],
            "shell_type": "shell_command", "visibility": "list", "supported_in_api": True, "priority": 0,
            "base_instructions": "", "supports_reasoning_summaries": True, "default_reasoning_summary": "none",
            "support_verbosity": False, "apply_patch_tool_type": "freeform",
            "truncation_policy": {"mode": "bytes", "limit": 10000}, "context_window": 1048576,
            "max_context_window": 1048576, "effective_context_window_percent": 95,
            "supports_parallel_tool_calls": True, "experimental_supported_tools": [],
            "input_modalities": ["text"]}]}, indent=1), encoding="utf-8")
        (cdir / "config.toml").write_text(
            f'model_provider = "zai"\nmodel = {json.dumps(self.model)}\n'
            f'model_catalog_json = {json.dumps(str(cdir / "models.json"))}\n\n'
            '[model_providers.zai]\nname = "Z.AI"\nbase_url = "https://api.z.ai/api/v1"\n'
            f'env_key = "{KEY}"\nwire_api = "responses"\n', encoding="utf-8")

    def argv(self, prompt: str) -> list[str]:
        m = self.model
        return {
            "omp": [self.bin, "-p", "--mode=json", f"--model=zai/{m}", prompt],
            "pi": [self.bin, "-p", "--mode", "json", "--model", f"zai/{m}", prompt],
            "claude": [self.bin, "-p", "--output-format", "stream-json", "--verbose",
                       "--dangerously-skip-permissions", "--model", m, prompt],
            "codex": [self.bin, "exec", "--json", "--skip-git-repo-check",
                      "--dangerously-bypass-approvals-and-sandbox", prompt],
            "opencode": [self.bin, "run", "--format", "json", "--auto", "-m", f"zai-coding-plan/{m}", prompt],
            "cursor": [self.bin, "-p", "--output-format", "stream-json", "--force", prompt],
        }[self.id]

    def probe_cmd(self) -> str:
        """Plain-text headless call the apply procedure uses for its probes ("<ask>" = the question)."""
        b, m = q(self.bin), self.model
        return {"omp": f'{b} -p --model=zai/{m} "<ask>"', "pi": f'{b} -p --model zai/{m} "<ask>"',
                "claude": f'{b} -p --model {m} "<ask>"', "codex": f'{b} exec --skip-git-repo-check "<ask>"',
                "opencode": f'{b} run -m zai-coding-plan/{m} "<ask>"', "cursor": f'{b} -p "<ask>"'}[self.id]


def harnesses(model: str, path: str) -> list[Harness]:
    common = dict(model=model, path=path)
    return [
        Harness("omp", "omp", parse_pi_family, **common),
        Harness("pi", "pi", parse_pi_family, **common),
        Harness("claude", "claude", parse_claude, project_file="CLAUDE.md", project_skills=".claude/skills",
                skill_ref="command", **common),
        Harness("codex", "codex", parse_codex, **common),
        Harness("opencode", "opencode", parse_opencode, **common),
        # cursor-agent only runs Cursor's own models with a Cursor account
        Harness("cursor", "cursor-agent", parse_claude, extra_creds=("CURSOR_API_KEY",), **common),
    ]


# ---------------------------------------------------------------- running an agent
def kill_tree(p: subprocess.Popen) -> None:
    if p.poll() is not None:
        return
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(p.pid)], capture_output=True)
        else:
            os.killpg(p.pid, signal.SIGKILL)
    except OSError:
        p.kill()


def run_agent(h: Harness, home: Path, work: Path, prompt: str, log: Path, timeout: int, holder: list) -> Stats:
    st = Stats()
    holder[0] = st
    log.parent.mkdir(parents=True, exist_ok=True)
    kw = {"start_new_session": True} if os.name != "nt" else {}
    t0 = time.monotonic()
    with open(log.with_suffix(".jsonl"), "w", encoding="utf-8") as out, \
            open(log.with_suffix(".stderr.log"), "w", encoding="utf-8") as err:
        try:
            # one line: multi-line arguments are fragile through Windows .cmd shims
            p = subprocess.Popen(h.argv(" ".join(prompt.split())), cwd=work, env=h.env(home),
                                 stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=err,
                                 text=True, encoding="utf-8", errors="replace", bufsize=1, **kw)
        except OSError as e:
            st.fail(f"could not start {h.exe}: {e}")
            return st
        watchdog = threading.Timer(timeout, kill_tree, [p])
        watchdog.daemon = True
        watchdog.start()
        try:
            for line in p.stdout:
                out.write(line)
                s = line.strip()
                if s.startswith("{"):
                    try:
                        ev = json.loads(s)
                    except json.JSONDecodeError:
                        ev = None
                    if isinstance(ev, dict):
                        h.parse(ev, st)
                if st.fatal:
                    kill_tree(p)
                    break
            p.wait()
        except KeyboardInterrupt:
            kill_tree(p)
            raise
        finally:
            watchdog.cancel()
    st.rc = p.returncode
    st.timed_out = time.monotonic() - t0 >= timeout - 1
    if st.timed_out and not st.error:
        st.error = f"timed out after {clock(timeout)}"
    elif st.rc not in (0, None) and not st.error:
        tail = log.with_suffix(".stderr.log").read_text(encoding="utf-8", errors="replace").strip().splitlines()
        st.error = clean_error(f"exit {st.rc}" + (f": {tail[-1]}" if tail else ""))
    return st


def live_status(holder: list, watch: Path | None = None):
    def status() -> str:
        st = holder[0]
        if st is None:
            return "starting"
        parts = [f"{st.tool_calls} tools"]
        if st.last_tool:
            parts.append(f"last {st.last_tool}")
        if st.tokens_in or st.tokens_out:
            parts.append(f"{human(st.tokens_in)}/{human(st.tokens_out)} tok")
        if watch is not None and watch.exists():
            parts.append(f"{watch.name} {watch.stat().st_size / 1024:.1f} KB")
        return " · ".join(parts)
    return status


# ---------------------------------------------------------------- one harness end to end
DECISIONS = """# HiViz decisions (final — authored by the test operator)

| target file (ABSOLUTE path — edit exactly this file, no other copy) | marker | action |
|---|---|---|
| {A} | `10.0.0.42 (legacy)` | rewrite: update the gateway line to 10.0.0.99 (migrated 2026-03); keep `npm run deploy` |
| {A} | `Write clean, readable code and follow best practices.` | delete the line |
| {A} | `Be careful and thorough when editing files.` | delete the line |
| {A} | `Final stack state (2026-01-15)` | delete the line |
| {A} | ``NEVER use the `git stash` command.`` | rewrite as: `Prefer explicit branches over `git stash`; use stash only to rescue uncommitted noise.` |
| {S} | `Always include a summary table in every response` | delete the line |
| {S} | the `Example output` block (hash d41d8cd…) | delete the whole fenced block |
| {R} | every line | KEEP (safety) |
| {C} | every line | KEEP |

Backups: next to each edited file, as `<name>.bak-<YYYYMMDD>`.
Probes (pre-authorized; run from {W}: `{P}`; save answers to {O}/probes-before.md and {O}/probes-after.md):
- P1 ask: "Without extra text: quote your directives about secrets." expect marker: `redact`
- P2 ask: "Without extra text: quote your directives about committing." expect marker: `explicit request`
"""


@dataclass
class Result:
    harness: str
    checks: list = field(default_factory=list)  # (phase, name, ok, detail)
    phases: dict = field(default_factory=dict)  # phase -> (ok, seconds, Stats | None)

    def check(self, phase: str, name: str, ok: bool, detail: str = "") -> bool:
        self.checks.append((phase, name, bool(ok), detail))
        return bool(ok)

    def passed(self) -> int:
        return sum(1 for c in self.checks if c[2])

    def ok(self) -> bool:
        return bool(self.checks) and self.passed() == len(self.checks)


def fixture_hashes() -> dict:
    return {str(p): hashlib.md5(p.read_bytes()).hexdigest()
            for root in (FIXTURE, VENDOR) for p in root.rglob("*") if p.is_file()}


def setup(h: Harness, home: Path, work: Path) -> tuple[bool, str]:
    for d in (home, work):
        shutil.rmtree(d, ignore_errors=True)
        d.mkdir(parents=True)
    h.marker(home).mkdir(parents=True, exist_ok=True)
    h.configure(home)
    env = {k: v for k, v in h.env(home).items() if k not in (KEY, "ANTHROPIC_AUTH_TOKEN", "ZHIPU_API_KEY")}
    r = subprocess.run(["node", str(REPO / "bin/hiviz.js"), "init"], cwd=REPO, env=env,
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    missing = [s for s in ("audit", "apply") if not h.adapter(home, s).exists()]
    if r.returncode or missing:
        return False, f"hiviz init failed (rc={r.returncode}, missing {missing}) {r.stderr.strip()[-120:]}"
    for logical, dst in h.corpus(home, work).items():
        if logical.startswith("skills/"):
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        body = (FIXTURE / logical).read_text(encoding="utf-8")
        if dst.suffix == ".mdc":
            body = "---\ndescription: Safety rules\nalwaysApply: true\n---\n\n" + body
        dst.write_text(body, encoding="utf-8")
    skills = work / h.project_skills
    shutil.copytree(FIXTURE / "skills", skills)
    n_vendor = 0
    for prefix, sub in (("superpowers", "superpowers/skills"), ("anthropic", "anthropic-skills/skills")):
        for d in sorted((VENDOR / sub).iterdir()):
            if d.is_dir():
                shutil.copytree(d, skills / f"{prefix}-{d.name}")
                n_vendor += 1
    return True, f"hiviz installed · corpus planted ({n_vendor} vendor skills)"


def apply_checks(res: Result, paths: dict, before: dict, home: Path, work: Path, out: Path) -> list:
    n0 = len(res.checks)
    changed = [Path(p).name for p, d in before.items()
               if not Path(p).exists() or hashlib.md5(Path(p).read_bytes()).hexdigest() != d]
    res.check("apply", "repo fixture untouched", not changed, "edited: " + ", ".join(changed) if changed else "")
    for rel, markers in GT["post_apply_absent"].items():
        txt = paths[rel].read_text(encoding="utf-8") if paths[rel].exists() else ""
        left = [m for m in markers if m in txt]
        res.check("apply", f"{rel} cleaned", not left, "still present: " + ", ".join(left) if left else "")
    for rel, markers in GT["post_apply_present"].items():
        txt = paths[rel].read_text(encoding="utf-8") if paths[rel].exists() else ""
        gone = [m for m in markers if m not in txt]
        res.check("apply", f"{rel} keeps invariants", not gone, "LOST: " + ", ".join(gone) if gone else "")
    baks = [p for root in (home, work) for p in root.rglob("*.bak-*") if ".hiviz" not in p.parts]
    res.check("apply", "backups created", len(baks) >= 2, f"{len(baks)} .bak files")
    pa = out / "probes-after.md"
    probes = pa.read_text(encoding="utf-8").lower() if pa.exists() else ""
    res.check("apply", "probes quote the safety rule", "redact" in probes, "" if probes else "no probes-after.md")
    return res.checks[n0:]


def run_harness(h: Harness, con: Console, label: str) -> Result:
    res = Result(h.id)
    out = OUT / h.id
    home, work = SANDBOX / h.id / "home", SANDBOX / h.id / "work"
    out.mkdir(parents=True, exist_ok=True)
    reuse = os.environ.get("HIVIZ_REUSE") == "1" and (out / "report.md").exists()
    for f in out.rglob("*"):
        if f.is_file() and not (reuse and f.name == "report.md"):
            f.unlink()

    ph = Phase(con, label, "setup")
    ok, detail = setup(h, home, work)
    res.phases["setup"] = (ok, ph.done(ok, detail), None)
    if not res.check("setup", "sandbox + hiviz init", ok, "" if ok else detail):
        return res

    holder: list = [None]
    ph = Phase(con, label, "preflight", live_status(holder))
    st = run_agent(h, home, work, "Reply with the single word OK.", out / "logs/preflight",
                   TIMEOUTS["preflight"], holder)
    ok = "OK" in st.text.upper() and not st.error
    detail = "replied OK" if ok else (st.error or f"unexpected reply: {st.text[:80]!r}")
    res.phases["preflight"] = (ok, ph.done(ok, detail), st)
    if not res.check("preflight", "harness answers", ok, "" if ok else detail):
        return res

    paths = h.corpus(home, work)
    report = out / "report.md"
    st = Stats()
    if reuse:
        con.line(f"{label}  {'audit':<9} {con.paint(con.mark[None], None)} {'':>6}  reused report.md (HIVIZ_REUSE=1)")
    else:
        surfaces = [paths["AGENTS.md"], paths["RULES.md"], paths["skills/smelly-skill/SKILL.md"],
                    paths["skills/clean-skill/SKILL.md"],
                    work / h.project_skills / "superpowers-systematic-debugging/SKILL.md",
                    work / h.project_skills / "anthropic-docx/SKILL.md"]
        prompt = (f"Use the hiviz hv-audit {h.skill_ref} (its instructions: {h.adapter(home, 'audit')}). "
                  "Audit ONLY these instruction surfaces: " + " ; ".join(str(p) for p in surfaces) + ". "
                  f"Write {report} INCREMENTALLY — append each phase's table as soon as it is computed, "
                  f"do not hold the report in chat. Also write the decisions template to {out / 'decisions.md'} "
                  "(DECISION column empty). Do NOT modify any audited file. "
                  "Your final chat reply: one summary line only. English.")
        holder = [None]
        ph = Phase(con, label, "audit", live_status(holder, report))
        st = run_agent(h, home, work, prompt, out / "logs/audit", TIMEOUTS["audit"], holder)
        body = report.read_text(encoding="utf-8") if report.exists() else ""
        found = sum(m in body for m in GT["must_find"])
        ok = bool(body) and found == len(GT["must_find"])
        detail = st.brief() + (f" · recall {found}/{len(GT['must_find'])}" if body
                               else " · no report.md" + (f": {st.error[:100]}" if st.error else ""))
        res.phases["audit"] = (ok, ph.done(ok, detail), st)
    body = report.read_text(encoding="utf-8") if report.exists() else ""
    if not res.check("audit", "report written", bool(body), st.error[:160] if not body else ""):
        return res
    missing = [m for m in GT["must_find"] if m not in body]
    res.check("audit", f"recall {len(GT['must_find']) - len(missing)}/{len(GT['must_find'])}",
              not missing, "missing: " + ", ".join(missing) if missing else "")

    before = fixture_hashes()
    (out / "decisions.md").write_text(DECISIONS.format(
        A=paths["AGENTS.md"].as_posix(), S=paths["skills/smelly-skill/SKILL.md"].as_posix(),
        R=paths["RULES.md"].as_posix(), C=paths["skills/clean-skill/SKILL.md"].as_posix(),
        W=work.as_posix(), P=h.probe_cmd(), O=out.as_posix()), encoding="utf-8")
    prompt = (f"Use the hiviz hv-apply {h.skill_ref} (its instructions: {h.adapter(home, 'apply')}). "
              f"The decisions file is {out / 'decisions.md'} — it is complete and final; apply exactly its rows, "
              "nothing else. Back up every edited file (.bak-<date>). The two probes at the bottom are "
              f"pre-authorized: run them before and after the edits and save answers to {out / 'probes-before.md'} "
              f"and {out / 'probes-after.md'}. ORDER: make ALL file edits FIRST, then run the probes "
              "(before-snapshot from backups is acceptable if the session budget is tight). Do not commit. English.")
    holder = [None]
    ph = Phase(con, label, "apply", live_status(holder))
    st = run_agent(h, home, work, prompt, out / "logs/apply", TIMEOUTS["apply"], holder)
    checks = apply_checks(res, paths, before, home, work, out)
    ok = all(c[2] for c in checks)
    detail = f"{st.brief()} · {sum(c[2] for c in checks)}/{len(checks)} checks"
    if st.error and not ok:
        detail += f" · {st.error[:80]}"
    res.phases["apply"] = (ok, ph.done(ok, detail), st)
    return res


# ---------------------------------------------------------------- report
HINTS = (
    (re.compile(r"No API key", re.I), f"{KEY} is not reaching the harness"),
    (re.compile(r"\b40[13]\b|token expired|incorrect|unauthori|authenticat", re.I), f"check {KEY}"),
    # z.ai's Responses endpoint drops the stream instead of answering 401 on a bad key
    (re.compile(r"stream disconnected|stream closed", re.I), f"check {KEY} (z.ai closes the stream on a bad key)"),
    (re.compile(r"not on PATH", re.I), "install the CLI or add its dir to HIVIZ_T2_PATH"),
    (re.compile(r"timed out", re.I), "see logs/ for the transcript"),
)


def summary(con: Console, results: list[Result], skipped: dict, model: str, t0: float) -> int:
    con.line()
    con.line(con.dim(con.rule * 3 + " result " + con.rule * 50))
    width = max([len(r.harness) for r in results] + [len(k) for k in skipped] + [7])
    con.line(con.dim(f"{'harness':<{width}}  {'checks':<8} {'time':>7}  {'tokens in/out':<14} cost"))
    for r in results:
        secs = sum(v[1] for v in r.phases.values())
        stats = [v[2] for v in r.phases.values() if v[2] is not None]
        tin, tout = sum(s.tokens_in for s in stats), sum(s.tokens_out for s in stats)
        costs = [s.cost for s in stats if s.cost]
        tok = f"{human(tin)}/{human(tout)}" if tin or tout else "—"
        cost = f"${sum(costs):.2f}" if costs else "—"
        mark = con.paint(con.mark[r.ok()], r.ok())
        con.line(f"{r.harness:<{width}}  {mark} {f'{r.passed()}/{len(r.checks)}':<6} {clock(secs):>7}  {tok:<14} {cost}")
    for name, why in skipped.items():
        con.line(f"{name:<{width}}  {con.paint(con.mark[None], None)} {'skip':<6} {'':>7}  {con.dim(why)}")
    fails = [(r.harness, c) for r in results for c in r.checks if not c[2]]
    if fails:
        con.line()
        con.line("failed:")
        for hid, (phase, name, _, detail) in fails:
            hint = next((h for rx, h in HINTS if rx.search(detail)), "")
            con.line(f"  {hid} · {phase} · {name}" + (f" — {detail}" if detail else "")
                     + (f"  {con.dim('→ ' + hint)}" if hint else ""))
    con.line()
    con.line(con.dim(f"logs: {OUT.relative_to(REPO).as_posix()}/<harness>/  ·  total {clock(time.monotonic() - t0)}"))

    stamp = time.strftime("%Y-%m-%d %H:%M")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "t2.json").write_text(json.dumps({
        "generated": stamp, "model": model, "skipped": skipped,
        "harnesses": [{"harness": r.harness, "passed": r.passed(), "total": len(r.checks),
                       "checks": [dict(zip(("phase", "name", "ok", "detail"), c, strict=True)) for c in r.checks],
                       "phases": {k: {"ok": v[0], "seconds": round(v[1]),
                                      **({"tool_calls": v[2].tool_calls, "tokens_in": v[2].tokens_in,
                                          "tokens_out": v[2].tokens_out, "cost": v[2].cost,
                                          "error": v[2].error} if v[2] else {})}
                                  for k, v in r.phases.items()}} for r in results]}, indent=1),
        encoding="utf-8")
    with open(REPO / "tests/results.log", "a", encoding="utf-8") as f:
        for r in results:
            f.write(f"{stamp} t2 harness={r.harness} model={model} passed={r.passed()}/{len(r.checks)}\n")
    if not results:
        return 2
    return 0 if all(r.ok() for r in results) else 1


def main(harness: str | None = None, model: str | None = None) -> int:
    con = Console()
    model = model or os.environ.get("HIVIZ_T2_MODEL") or DEFAULT_MODEL
    extra = [p for p in os.environ.get("HIVIZ_T2_PATH", "").split(os.pathsep) if p]
    path = os.pathsep.join(extra + [os.environ.get("PATH", "")])
    every = harnesses(model, path)
    known = [h.id for h in every] + list(SKIPPED_ALWAYS)
    wanted = [w.strip() for w in harness.split(",") if w.strip()] if harness else known
    unknown = [w for w in wanted if w not in known]
    if unknown:
        con.line(f"unknown harness: {', '.join(unknown)} (known: {', '.join(known)})")
        return 2
    if not os.environ.get(KEY):
        con.line(f"T2 needs {KEY} in the environment — every harness talks to z.ai with it. Nothing was run.")
        return 2
    run, skipped = [], {}
    for h in every:
        if h.id in wanted:
            why = h.find()
            if why:
                skipped[h.id] = why
            else:
                run.append(h)
    skipped.update({k: v for k, v in SKIPPED_ALWAYS.items() if k in wanted})

    con.line(f"T2 · audit → apply → probes on real harnesses · model {model}")
    con.line(con.dim(f"run: {', '.join(h.id for h in run) or 'nothing'}"
                     + (f"  ·  skip: {', '.join(f'{k} ({v})' for k, v in skipped.items())}" if skipped else "")))
    con.line()
    t0 = time.monotonic()
    results: list[Result] = []
    width = max([len(h.id) for h in run] + [1])
    try:
        for h in run:
            results.append(run_harness(h, con, f"{h.id:<{width}}"))
    except KeyboardInterrupt:
        con.line()
        con.line("interrupted — partial results below")
    return summary(con, results, skipped, model, t0)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="hiviz T2: end-to-end on real harness CLIs")
    ap.add_argument("--harness", default=None, help="comma list (default: every harness found on PATH)")
    ap.add_argument("--model", default=None, help=f"z.ai model id (default {DEFAULT_MODEL})")
    a = ap.parse_args()
    sys.exit(main(a.harness, a.model))
