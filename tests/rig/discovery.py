"""T1: do the real harness CLIs see what `hiviz init` installs? No model, no credentials, no network.

A CLI that is not installed is skipped (the check says so) — unless HIVIZ_REQUIRE_HARNESSES=codex,pi,... names it,
which is what CI does after installing them.
"""
from __future__ import annotations

import os
import shutil

from .core import _SECTION, check, fresh_home, home_env, sh
from .harness import HARNESSES, cli_version
from .installer import CMD_NAMES, HARNESS_MARKERS, SKILL_NAMES
from .t2 import profile_setup


def discovery_checks() -> None:
    required = {x for x in os.environ.get("HIVIZ_REQUIRE_HARNESSES", "").replace(" ", "").split(",") if x}
    _SECTION[0] = "harness discovery"
    for name, h in HARNESSES.items():
        if h.discover is None:
            continue
        if not shutil.which(h.cli):
            check(f"harness [{name}]: CLI not installed — discovery skipped", name not in required,
                  "required (HIVIZ_REQUIRE_HARNESSES) but missing" if name in required else "")
            continue
        ver = cli_version(h)
        what, want = ("commands", {f"hv-{n}" for n in CMD_NAMES}) if h.commands else ("skills", {f"hv-{n}" for n in SKILL_NAMES})
        home = fresh_home(f"discover-{name}")
        (home / HARNESS_MARKERS[name]).mkdir(parents=True)
        init = sh(["node", "bin/hiviz.js", "init"], env=home_env(home))
        try:
            seen, err = h.discover(home, home, None), ""
        except Exception as e:   # a CLI change must fail loudly, with the reason
            seen, err = set(), f"{type(e).__name__}: {e}"
        check(f"harness [{name}]: after `hiviz init` the real CLI lists all {len(want)} hiviz {what} ({ver}, no model)",
              init.returncode == 0 and want <= seen, err or f"missing={sorted(want - seen)}")
        if not (h.skills_dir or h.profile):
            continue
        # the sandbox T2 really builds (profile_setup), placed in a fresh fake machine, asked of the real CLI
        box = fresh_home(f"discover-{name}-sandbox")
        project = box / "project"
        project.mkdir()
        target = h.sandbox_dir(box, project) if h.sandbox_dir else project
        profile_setup(profile=target, h=h)
        layout = h.skills_dir or f"--profile {h.profile}"
        try:
            seen, err = h.discover(box, project, h.profile), ""
        except Exception as e:
            seen, err = set(), f"{type(e).__name__}: {e}"
        check(f"harness [{name}]: skills in the T2 sandbox as profile_setup builds it ({layout}) are discovered",
              {"hv-audit", "hv-apply"} <= seen, err or f"missing={sorted({'hv-audit', 'hv-apply'} - seen)}")
    _SECTION[0] = None
