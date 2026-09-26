#!/usr/bin/env python3
"""Verifier: substring markers per question, from qa.json in the working dir.
Scoring: each of the 5 questions earns 2 points (1 for the marker, 1 for a
substantive answer line); prints 'SCORE: n/10'; exit 0 iff score >= 8."""
import json
import re
import sys
from pathlib import Path

QA = json.loads(Path("qa.json").read_text(encoding="utf-8"))


def main() -> int:
    ans_p = Path("answers.txt")
    if not ans_p.exists():
        cands = sorted(Path(".").glob("*.txt"))
        if not cands:
            print("SCORE: 0/10 — no answers file"); return 1
        ans_p = cands[0]
    text = ans_p.read_text(encoding="utf-8", errors="replace")
    score, fails = 0, []
    for q in QA:
        m = re.search(rf"^{q['n']}\.\s*(.+)$", text, re.M)
        if not m:
            fails.append(f"q{q['n']}: no numbered answer"); continue
        a = m.group(1)
        if any(marker.lower() in a.lower() for marker in q["any_of"]):
            score += 1
        else:
            fails.append(f"q{q['n']}: marker missing ({a[:40]!r})")
        if len(a.split()) >= 4 and not re.search(r"\b(not sure|don'?t know|no idea)\b", a, re.I):
            score += 1
        else:
            fails.append(f"q{q['n']}: answer too thin")
    print(f"SCORE: {score}/10" + (f" — {'; '.join(fails[:4])}" if fails else " — all answers carry corpus-fact markers"))
    return 0 if score >= 8 else 1


if __name__ == "__main__":
    sys.exit(main())
