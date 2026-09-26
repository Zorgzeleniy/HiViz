#!/usr/bin/env python3
"""Verifier: drive the CLI end-to-end in the working dir. Deterministic, stdlib only.
Scoring: 10 binary checks, prints 'SCORE: n/10'; exit 0 iff score >= 8."""
import json
import subprocess
import sys
from pathlib import Path


def run(*args):
    return subprocess.run([sys.executable, "todo.py", *args], capture_output=True,
                          text=True, timeout=30)


def main() -> int:
    score = 0
    fails = []

    # fresh-state list: no items -> empty output (or no numbered lines)
    r0 = run("list")
    if r0.returncode == 0 and not [l for l in r0.stdout.splitlines() if l.strip().startswith("1.")]:
        score += 1
    else:
        fails.append("empty list")

    r = run("add", "alpha")
    if r.returncode == 0: score += 1
    else: fails.append("add rc")
    run("add", "beta"); run("add", "gamma")

    data = []
    try:
        data = json.loads(Path("todo.json").read_text())
        if [d["text"] for d in data] == ["alpha", "beta", "gamma"]: score += 1
        else: fails.append("storage texts")
        if all(d.get("done") is False for d in data): score += 1
        else: fails.append("storage done flags")
    except Exception:
        fails.append("storage unreadable")

    r = run("list")
    lines = r.stdout.strip().splitlines()
    if len(lines) == 3 and lines[1].startswith("2. [ ]"): score += 1
    else: fails.append("list open format")
    if "2. [ ] beta" in r.stdout: score += 1
    else: fails.append("list exact line")

    run("done", "2")
    r = run("list")
    if "2. [x] beta" in r.stdout: score += 1
    else: fails.append("done marks [x]")
    try:
        if json.loads(Path("todo.json").read_text())[1]["done"] is True: score += 1
        else: fails.append("storage done flag")
    except Exception:
        fails.append("storage after done")

    run("remove", "1")
    try:
        if [d["text"] for d in json.loads(Path("todo.json").read_text())] == ["beta", "gamma"]: score += 1
        else: fails.append("remove")
    except Exception:
        fails.append("storage after remove")

    r = run("done", "9")
    if r.returncode != 0 or "no such item" in (r.stderr or "").lower() or "no such item" in r.stdout.lower():
        score += 1
    else:
        fails.append("out-of-range")

    print(f"SCORE: {score}/10" + (f" — fails: {', '.join(fails)}" if fails else " — all checks green"))
    return 0 if score >= 8 else 1


if __name__ == "__main__":
    sys.exit(main())
