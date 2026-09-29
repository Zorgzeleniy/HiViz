#!/usr/bin/env python3
"""hiviz blame — provenance for standing-instruction lines.

Answers: when was this line written, by which model, in which session, why
(ledger), and is it still verified (constitution). Sources, in order of trust:
  1. .hiviz/ledger.jsonl — entries written by hiviz ingest/apply
  2. harness session logs — mined edit/write tool calls from omp, pi, Claude Code
     and Codex JSONL histories (default dirs below, or --sessions)

Stdlib only. Read-only.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

EDIT_TOOLS = {"edit", "write", "Edit", "Write", "MultiEdit", "NotebookEdit", "apply_patch", "multi_edit"}
SHELL_TOOLS = {"shell", "local_shell", "exec_command", "bash", "Bash"}  # count only when running a patch
META_KEYS = ('"model_change"', '"session_info"', '"turn_context"', '"session_meta"',
             '"type":"session"', '"type": "session"', '"type":"summary"', '"type": "summary"')


def _env_dir(var: str, default: Path) -> Path:
    v = os.environ.get(var, "").strip()
    return Path(v).expanduser() if v else default


def default_sessions() -> list[Path]:
    home = Path.home()
    codex = _env_dir("CODEX_HOME", home / ".codex")
    return [home / ".omp/agent/sessions", *sorted(home.glob(".omp/profiles/*/agent/sessions")),
            _env_dir("PI_CODING_AGENT_DIR", home / ".pi/agent") / "sessions",
            _env_dir("CLAUDE_CONFIG_DIR", home / ".claude") / "projects",
            codex / "sessions", codex / "archived_sessions"]


def norm(p: str) -> str:
    # collapses JSON-escaped Windows separators too (C:\\Users -> c:/users)
    return re.sub(r"\\+", "/", p).lower()


def load_ledger(path: Path | None, file_key: str, marker: str) -> list[dict]:
    if not (path and path.exists()):
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        if norm(e.get("file", "")) != file_key:
            continue
        if marker and marker not in e.get("marker", e.get("text", "")):
            continue
        out.append(e)
    return out


def _as_text(v) -> str:
    return v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)


def tool_calls(d: dict):
    """Yield (tool name, payload text) for every tool call in one log entry.
    Shapes: omp/pi message.content[toolCall].arguments · Claude Code
    message.content[tool_use].input · Codex payload function_call/custom_tool_call."""
    msg = d.get("message")
    content = msg.get("content") if isinstance(msg, dict) else None
    for it in content if isinstance(content, list) else []:
        if isinstance(it, dict) and it.get("type") in ("toolCall", "tool_use"):
            yield str(it.get("name", "")), _as_text(it.get("arguments", it.get("input")) or {})
    p = d.get("payload")
    if d.get("type") == "response_item" and isinstance(p, dict) and \
            p.get("type") in ("function_call", "custom_tool_call", "local_shell_call"):
        args = p.get("arguments", p.get("input", p.get("action")))
        if isinstance(args, str):
            try:
                args = json.loads(args)  # function_call arguments are a JSON string
            except json.JSONDecodeError:
                pass
        yield str(p.get("name") or "shell"), _as_text(args or {})


def _mentions(payload_norm: str, file_key: str, cwd: str) -> bool:
    if file_key in payload_norm:
        return True
    base = norm(cwd).rstrip("/") if cwd else ""
    if not base or not file_key.startswith(base + "/"):
        return False
    rel = file_key[len(base) + 1:]  # Codex patches name files relative to the session cwd
    return re.search(r"(?<![\w./-])" + re.escape(rel) + r"(?![\w.-])", payload_norm) is not None


def mine_sessions(sessions_dirs: list[Path], file_key: str, marker: str,
                  max_events: int = 50) -> list[dict]:
    """Return edit/write events touching the file (marker-flagged when payload
    contains the line text), newest last."""
    events: list[dict] = []
    files: list[Path] = []
    for d in sessions_dirs:
        if d.exists():
            files.extend(sorted(d.rglob("*.jsonl"), key=lambda p: p.stat().st_mtime,
                                reverse=True))
    path_frag = file_key.rsplit("/", 1)[-1]  # basename prefilter keeps scan cheap
    for jf in files:
        title, model, cwd = "", "", ""
        try:
            fh = jf.open(encoding="utf-8", errors="replace")
        except OSError:
            continue
        with fh:
            for line in fh:
                hit = path_frag in line.lower()
                if not hit and not any(k in line for k in META_KEYS):
                    continue
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(d, dict):
                    continue
                t = d.get("type")
                p = d.get("payload") if isinstance(d.get("payload"), dict) else {}
                if t == "session":  # omp/pi header
                    title, cwd = d.get("title") or title, d.get("cwd") or cwd
                elif t == "session_info":  # pi /name
                    title = d.get("name") or title
                elif t == "summary":  # Claude Code
                    title = d.get("summary") or title
                elif t == "model_change":  # omp: model · pi: provider + modelId
                    model = d.get("model") or "/".join(
                        str(x) for x in (d.get("provider"), d.get("modelId")) if x) or model
                elif t in ("session_meta", "turn_context"):  # Codex
                    model, cwd = p.get("model") or model, p.get("cwd") or cwd
                if not hit:
                    continue
                msg = d.get("message") if isinstance(d.get("message"), dict) else {}
                line_model = msg.get("model")
                if line_model and msg.get("provider"):
                    line_model = f"{msg['provider']}/{line_model}"
                line_cwd = d.get("cwd") or cwd  # Claude Code stamps cwd on every entry
                for name, payload in tool_calls(d):
                    if name not in EDIT_TOOLS and not (name in SHELL_TOOLS and "*** Begin Patch" in payload):
                        continue
                    if not _mentions(norm(payload), file_key, line_cwd):
                        continue
                    events.append({
                        "ts": d.get("timestamp", ""),
                        "model": line_model or model or "?",
                        "tool": name,
                        "session": title or jf.stem[:24],
                        "touched_line": bool(marker) and marker in payload,
                    })
                    if len(events) >= max_events:
                        events.sort(key=lambda e: e["ts"])
                        return events
    events.sort(key=lambda e: e["ts"])
    return events


def verified_from(constitution_json: Path | None, marker: str) -> list[dict]:
    if not (constitution_json and constitution_json.exists() and marker):
        return []
    try:
        rows = json.loads(constitution_json.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    return [r for r in rows if marker.lower() in (r.get("guards") or "").lower()]


def main() -> int:
    ap = argparse.ArgumentParser(description="hiviz blame")
    ap.add_argument("--file", required=True)
    ap.add_argument("--line", type=int, default=None)
    ap.add_argument("--marker", default=None, help="text fragment identifying the line")
    ap.add_argument("--sessions", action="append", default=None,
                    help="session-log dir (repeatable; replaces the omp/pi/Claude/Codex defaults)")
    ap.add_argument("--ledger", default=None)
    ap.add_argument("--constitution", default=None)
    a = ap.parse_args()

    target = Path(a.file)
    if not target.exists():
        print(f"file not found: {target}", file=sys.stderr)
        return 2
    file_key = norm(str(target.resolve()))

    marker = a.marker or ""
    if not marker and a.line:
        lines = target.read_text(encoding="utf-8").splitlines()
        if 0 < a.line <= len(lines):
            marker = lines[a.line - 1].strip()

    sessions = [Path(p) for p in a.sessions] if a.sessions else default_sessions()
    events = mine_sessions(sessions, file_key, marker)
    ledger = load_ledger(Path(a.ledger) if a.ledger else None, file_key, marker)
    verified = verified_from(Path(a.constitution) if a.constitution else None, marker)

    loc = f"{target.name}:{a.line}" if a.line else target.name
    print(f"## {loc}")
    if marker:
        print(f"> {marker[:160]}")
    if ledger:
        for e in ledger:
            print(f"  ledger:    {e.get('written_at', '?')} · {e.get('model', '?')} · "
                  f"reason: {e.get('reason', '?')} · action: {e.get('action', '?')}")
    else:
        print("  ledger:    (no entry — pre-tool history only)")
    if events:
        print(f"  history:   {len(events)} edit/write event(s) in session logs")
        for e in events[-5:]:
            star = " · TOUCHED THIS LINE" if e["touched_line"] else ""
            print(f"    - {e['ts']} · {e['model']} · {e['tool']} · session \"{e['session']}\"{star}")
    else:
        print("  history:   no edit/write events found in the given session logs")
    if verified:
        for v in verified:
            print(f"  verified:  {v.get('verdict')} by constitution test `{v.get('id')}`")
    return 0


if __name__ == "__main__":
    sys.exit(main())
