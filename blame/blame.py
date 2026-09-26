#!/usr/bin/env python3
"""hiviz blame — provenance for standing-instruction lines.

Answers: when was this line written, by which model, in which session, why
(ledger), and is it still verified (constitution). Sources, in order of trust:
  1. .hiviz/ledger.jsonl — entries written by hiviz ingest/apply
  2. harness session logs  — mined edit/write tool calls (omp: ~/.omp/agent/sessions)

Stdlib only. Read-only.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

EDIT_TOOLS = {"edit", "write", "Edit", "Write"}


def norm(p: str) -> str:
    return p.replace("\\", "/").lower()


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
        title, model = "", ""
        try:
            fh = jf.open(encoding="utf-8", errors="replace")
        except OSError:
            continue
        with fh:
            for line in fh:
                if '"toolCall"' not in line:
                    if '"type": "session"' in line or '"type":"session"' in line:
                        try:
                            h = json.loads(line)
                            title = h.get("title", "")
                        except json.JSONDecodeError:
                            pass
                    elif '"model_change"' in line:
                        try:
                            m = json.loads(line)
                            model = m.get("model", model)
                        except json.JSONDecodeError:
                            pass
                    continue
                if path_frag not in line.lower():
                    continue
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    continue
                msg = d.get("message") or {}
                for item in (msg.get("content") or []):
                    if not isinstance(item, dict) or item.get("type") != "toolCall":
                        continue
                    if item.get("name") not in EDIT_TOOLS:
                        continue
                    payload = json.dumps(item.get("arguments") or {}, ensure_ascii=False)
                    if norm(file_key) not in norm(payload):
                        continue
                    events.append({
                        "ts": d.get("timestamp", ""),
                        "model": model or "?",
                        "tool": item.get("name"),
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
    ap.add_argument("--sessions", action="append", default=None)
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

    sessions = [Path(p) for p in (a.sessions or [str(Path.home() / ".omp/agent/sessions")])]
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
