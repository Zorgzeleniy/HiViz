#!/usr/bin/env python3
"""Fake agent harness for the negative-control tests: it behaves like the real ones in the ways that matter.

* The working directory comes from $PWD, not from getcwd() — Bun/Node harnesses do this, and it is what made
  `subprocess.run(cwd=...)` silently probe the WRONG directory.
* It loads ./AGENTS.md as standing instructions (unless FAKE_AGENT_LOADS_CWD=0: a harness that reads only its own
  config dir, like `omp --profile`) plus FAKE_AGENT_CONFIG_DIR/AGENTS.md (a global config, always loaded).
* It has built-in knowledge (BUILTIN) that no file can remove — a system prompt.
* Every call is appended to FAKE_AGENT_LOG: cwd, $PWD and the files visible in the working directory.

Usage: fake_agent.py "<ask>"      -> stdout answer, exit 0
"""
import os
import re
import sys
from pathlib import Path

ask = " ".join(sys.argv[1:])
pwd = Path(os.environ.get("PWD") or os.getcwd())
BUILTIN = {
    "committing": "Only commit when there is an explicit request from the user.",   # the harness default, like a real system prompt
    "language": "I answer in English by default.",
}


def instructions() -> list[str]:
    lines = []
    cfg = os.environ.get("FAKE_AGENT_CONFIG_DIR")
    if cfg and (Path(cfg) / "AGENTS.md").exists():
        lines += (Path(cfg) / "AGENTS.md").read_text(encoding="utf-8").splitlines()
    if os.environ.get("FAKE_AGENT_LOADS_CWD", "1") != "0" and (pwd / "AGENTS.md").exists():
        lines += (pwd / "AGENTS.md").read_text(encoding="utf-8").splitlines()
    return lines


def log() -> None:
    path = os.environ.get("FAKE_AGENT_LOG")
    if path:
        seen = sorted(str(p.relative_to(pwd)).replace("\\", "/") for p in pwd.rglob("*") if p.is_file()) if pwd.is_dir() else []
        with open(path, "a", encoding="utf-8") as fh:
            note = int("standing instructions only" in ask)
            fh.write(f"cwd={os.getcwd()}|pwd={pwd}|files={','.join(seen)}|note={note}|ask={ask[:60]}\n")


log()
lines = instructions()
token = re.search(r"HIVIZCANARY\w+", ask)
if token:
    hit = next((line for line in lines if token.group(0) in line), None)
    print(hit or "I have no such token in my instructions.")
    sys.exit(0)
topic = next((w for w in ("gateway", "committing", "language", "secrets") if w in ask.lower()), None)
if topic:
    hit = next((line for line in lines if topic.rstrip("s").rstrip("ing") in line.lower() or topic in line.lower()), None)
    if topic == "committing":
        hit = next((line for line in lines if "commit" in line.lower()), None)
    if hit:
        print(hit)
    elif topic in BUILTIN:
        print(BUILTIN[topic])
    else:
        print(f"No directive about {topic} exists in my instructions.")
else:
    print("OK")
