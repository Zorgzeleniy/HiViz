#!/usr/bin/env python3
"""Verifier: hidden assertions on the fixed calc.py (edge cases + API preserved).
Runs against the CURRENT working directory (the agent's workdir).
Scoring: 10 binary checks, prints 'SCORE: n/10'; exit 0 iff score >= 8."""
import inspect
import os
import sys

sys.path.insert(0, os.getcwd())


def main() -> int:
    score = 0
    fails = []

    try:
        import calc
        if list(inspect.signature(calc.running_sum).parameters) == ["nums"]:
            score += 1
        else:
            fails.append("signature changed")
        doc = (inspect.getdoc(calc.running_sum) or "").lower()
        if "prefix" in doc: score += 1
        else: fails.append("docstring lost the prefix-sum contract")
    except Exception as e:
        print(f"SCORE: 0/10 — import/signature: {e}")
        return 1

    cases = [([], []), ([1], [1]), ([1, 2], [1, 3]), ([1, 2, 3], [1, 3, 6]),
             ([-1, 5], [-1, 4]), ([0, 0, 0], [0, 0, 0]), ([2.5, 2.5], [2.5, 5.0]),
             (list(range(1, 101)), [n * (n + 1) // 2 for n in range(1, 101)])]
    for inp, want in cases:
        try:
            got = calc.running_sum(list(inp))
            if got == want: score += 1
            else: fails.append(f"{inp[:3]}… -> {str(got)[:12]} != {str(want)[:12]}")
        except Exception as e:
            fails.append(f"{inp[:3]}… raised {type(e).__name__}")

    print(f"SCORE: {score}/10" + (f" — fails: {'; '.join(fails[:4])}" if fails else " — all checks green"))
    return 0 if score >= 8 else 1


if __name__ == "__main__":
    sys.exit(main())
