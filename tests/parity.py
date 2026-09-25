#!/usr/bin/env python3
"""T-key parity check for bin/hiviz.js: every render(T.x) must have a defined x (and vice versa).
Guards against anchored-insert edits eating a template line (bit us three times)."""
import re
import sys
from pathlib import Path

src = (Path(__file__).resolve().parent.parent / "bin" / "hiviz.js").read_text(encoding="utf-8")
defined = set(re.findall(r"^\s{4}(\w+): read\(", src, re.M))
used = set(re.findall(r"render\(T\.(\w+)\)", src))
if defined != used:
    print(f"T-key parity MISMATCH: {used ^ defined}", file=sys.stderr)
    sys.exit(1)
print(f"T-key parity OK ({len(defined)} keys):", ", ".join(sorted(defined)))
