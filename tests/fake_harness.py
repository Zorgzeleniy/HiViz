#!/usr/bin/env python3
"""Fake harness for hiviz T1 constitution tests: answers probes deterministically.

Usage: fake_harness.py "<ask>"   (models the harness CLI contract: {ask} -> stdout)

Behaviors keyed on the ask content:
- contains "secrets"  -> quotes the safety line (PASS case)
- contains "committing" -> quotes the commit gate (PASS case)
- contains "language" -> quotes the language default (PASS case)
- contains "FAILCASE" -> answers off-topic (FAIL case)
- contains "FLAKYCASE" -> fails on the FIRST invocation per process id, passes after
  (models flakiness when the runner retries in a NEW process; state file marks the attempt)
- contains "EXITFAIL" -> harness crash: marker-looking noise on stderr, exit 127
"""
import sys
from pathlib import Path

ask = " ".join(sys.argv[1:])
state = Path(__file__).with_suffix(".state")

if "EXITFAIL" in ask:
    print("bash: omp: command not found — run the command and check its output", file=sys.stderr)
    sys.exit(127)
elif "secrets" in ask:
    print("NEVER print secrets or API keys verbatim — redact them.")
elif "committing" in ask:
    print("NEVER commit, push, or delete anything without an explicit request in the current conversation.")
elif "language" in ask:
    print("- Answer in English by default.")
elif "FAILCASE" in ask:
    print("The weather today is sunny with light winds.")
elif "FLAKYCASE" in ask:
    if state.exists():
        print("NEVER print secrets or API keys verbatim — redact them.")
    else:
        state.write_text("1")
        print("I have no relevant directives.")
else:
    print("OK")
