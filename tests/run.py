#!/usr/bin/env python3
"""hiviz test rig — entry point (the checks live in tests/rig/).

T1 (deterministic, free, hermetic — every harness gets its own fake $HOME under tests/out):
   installer per harness, meters vs fake stdio/HTTP MCP, drift, constitution via a fake harness, blame, translate,
   human output, report page.
T2 (E2E, LLM): audit -> ground-truth check -> deterministic decisions -> apply -> post-asserts.
T2x (E2E, LLM): report page -> clicked decisions -> exported decisions.md -> hv-apply -> only those edits.

Usage: python tests/run.py [--t1|--t2|--t2x|--all]   (default: --t1)
"""
from __future__ import annotations

import argparse
import os
import sys
import time

from rig.core import OUT, _SECTION, hvfmt, summary
from rig.discovery import discovery_checks
from rig.engines import engine_checks
from rig.installer import installer_checks, plugin_checks, plugin_install_checks, uninstall_checks, uninstall_edge_checks
from rig.output import format_checks, report_checks
from rig.t2 import t2, t2x


def t1() -> None:
    print(hvfmt.heading("T1 · deterministic", "hermetic fake $HOME per harness · no model calls") if hvfmt.is_pretty()
          else "== T1: deterministic ==")
    _SECTION[0] = "installer / uninstall"
    installer_checks()
    uninstall_checks()
    uninstall_edge_checks()
    plugin_install_checks()
    _SECTION[0] = None
    engine_checks()
    format_checks()
    report_checks()
    plugin_checks()
    discovery_checks()


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for var in ("GITHUB_EVENT_NAME", "GITHUB_EVENT_PATH", "HIVIZ_ACTIVE_CHECKS"):
        os.environ.pop(var, None)   # hermetic: CI's own event must not steer the engines under test
    ap = argparse.ArgumentParser()
    ap.add_argument("--t1", action="store_true")
    ap.add_argument("--t2", action="store_true")
    ap.add_argument("--t2x", action="store_true", help="export a decisions.md from the report page and apply it with a real model")
    ap.add_argument("--all", action="store_true")
    hvfmt.add_format_arg(ap)
    a = ap.parse_args()
    hvfmt.configure(a.format)
    t0 = time.monotonic()
    if a.t1 or a.all or not (a.t1 or a.t2 or a.t2x):
        t1()
    if a.t2 or a.all:
        t2()
    if a.t2x:
        t2x()
    return summary(time.monotonic() - t0)


if __name__ == "__main__":
    sys.exit(main())
