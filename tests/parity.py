#!/usr/bin/env python3
"""T-key parity check for bin/hiviz.js: every render(T.x) must have a defined x (and vice versa).
Guards against anchored-insert edits eating a template line (bit us three times)."""
import json
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

# The meter speaks MCP as a client and cannot read package.json when deployed to ~/.hiviz/engines, so its version
# string is hard-coded: it must follow the release version (the plugin tree is checked by build-plugin --check).
root = Path(__file__).resolve().parent.parent
release = json.loads((root / "package.json").read_text(encoding="utf-8"))["version"]
meter = re.search(r'"hiviz-meter", "version": "([^"]+)"', (root / "meters" / "mcp_footprint.py").read_text(encoding="utf-8"))
if not meter or meter.group(1) != release:
    print(f"version MISMATCH: package.json {release} vs meters/mcp_footprint.py {meter.group(1) if meter else '?'}", file=sys.stderr)
    sys.exit(1)
print(f"version OK ({release}): package.json = meter clientInfo")
