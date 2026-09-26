#!/usr/bin/env python3
"""Verifier: checks artifacts against conventions.json in the working dir.
Scoring: binary checks scaled to 10 (one decimal); prints 'SCORE: n/10'; exit 0 iff score >= 8."""
import json
import re
import sys
from pathlib import Path

CONV = json.loads(Path("conventions.json").read_text(encoding="utf-8"))


def main() -> int:
    checks = []  # (ok, label)

    msg = Path("COMMIT_MSG.txt").read_text(encoding="utf-8", errors="replace").strip() \
        if Path("COMMIT_MSG.txt").exists() else ""
    checks.append((bool(re.match(CONV["commit_regex"], msg)), "commit format"))

    notes_p = Path("NOTES.md")
    if not notes_p.exists():
        print("SCORE: 0/10 — NOTES.md missing"); return 1
    notes = notes_p.read_text(encoding="utf-8", errors="replace")
    lines = notes.splitlines()

    n = len([l for l in lines if l.strip()])
    checks.append((10 <= n <= 25, "length 10-25"))
    checks.append((notes.endswith("\n") if "eof_newline" in CONV.get("file_rules", []) else True, "EOF newline"))
    checks.append((all(l == l.rstrip() for l in lines) if "no_trailing_ws" in CONV.get("file_rules", []) else True,
                   "no trailing ws"))
    if "fences_declare_language" in CONV.get("file_rules", []):
        ok, in_fence = True, False
        for line in lines:
            s = line.strip()
            if s.startswith("```"):
                if in_fence:
                    in_fence = False
                else:
                    in_fence = True
                    if s == "```":
                        ok = False; break
        checks.append((ok, "fences declare language"))
    if CONV.get("must_mention"):
        checks.append((CONV["must_mention"] in notes, f"mentions {CONV['must_mention']!r}"))

    ok_count = sum(1 for ok, _ in checks if ok)
    score = round(10 * ok_count / len(checks), 1)
    fails = [label for ok, label in checks if not ok]
    print(f"SCORE: {score}/10" + (f" — fails: {', '.join(fails[:4])}" if fails else " — conventions followed"))
    return 0 if score >= 8 else 1


if __name__ == "__main__":
    sys.exit(main())
