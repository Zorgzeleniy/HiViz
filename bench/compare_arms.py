#!/usr/bin/env python3
"""Compare bench arms across run dirs: A vs B (published + same-day) vs C (skills-audit).

Usage: python bench/compare_arms.py <run_dir_A_vs_B> [<run_dir_A_vs_B_today>] <run_dir_A_vs_C>
Each run dir is a run_ab.py output (results.json with aggregate medians per arm/task).
Prints one table: per task, cost medians per arm + deltas vs each run's own arm-a.
"""
import json
import sys
from pathlib import Path


def load(run_dir: Path) -> dict:
    data = json.loads((run_dir / "results.json").read_text(encoding="utf-8"))
    cells = {}
    for a in data["aggregate"]:
        cells[(a["arm"], a["task"])] = a
    return cells


def main() -> int:
    dirs = [Path(p) for p in sys.argv[1:]]
    tags = ["A/B (published)", "A/B (same-day)", "A/C (skills-audit)"]
    sets = []
    for d in dirs:
        if len(sets) >= len(tags):
            break
        tag = tags[len(sets)]
        sets.append((tag, load(d)))
    tasks = sorted({t for _, cells in sets for (_, t) in cells})
    hdr = f"| task | {' | '.join(f'{tag}: arm | Δcost | Δtok_in' for tag, _ in sets)} |"
    print(hdr)
    print("|" + "---|" * (1 + 2 * len(sets)))
    for t in tasks:
        row = [t]
        for tag, cells in sets:
            ra, rb = cells.get(("a", t)), cells.get(("b", t))
            if not (ra and rb):
                row.append("n/a | | ")
                continue
            def d(k):
                return f"{(rb[k] - ra[k]) / ra[k] * 100:+.0f}%" if ra[k] else "n/a"
            row.append(f"{ra['cost_med']:.3f}→{rb['cost_med']:.3f} | {d('cost_med')} | {d('tok_in_med')}")
        print("| " + " | ".join(row) + " |")
    print("\nquality (score med / pass rate):")
    for t in tasks:
        line = [t]
        for tag, cells in sets:
            ra, rb = cells.get(("a", t)), cells.get(("b", t))
            if ra and rb:
                line.append(f"{tag}: {ra['score_med']:.1f}/{ra['pass_rate']:.0%} → {rb['score_med']:.1f}/{rb['pass_rate']:.0%}")
        print("  " + " · ".join(line))
    return 0


if __name__ == "__main__":
    sys.exit(main())
