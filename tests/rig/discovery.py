"""T1: do the real harness CLIs see what `hiviz init` installs? No model, no credentials, no network.

A CLI that is not installed is skipped (the check says so) — unless HIVIZ_REQUIRE_HARNESSES=codex,pi,... names it,
which is what CI does after installing them.
"""
from __future__ import annotations

import os
import shutil

from .core import REPO, _SECTION, check, fresh_home, home_env, sh
from .harness import HARNESSES, cli_version
from .installer import CMD_NAMES, HARNESS_MARKERS, SKILL_NAMES


def _render_skills(project, skills_dir: str) -> None:
    for name, tpl, key, core in (("hv-audit", "skill.md", "{{AUDIT_BODY}}", "AUDIT.md"),
                                 ("hv-apply", "skill-apply.md", "{{APPLY_BODY}}", "APPLY.md")):
        d = project / skills_dir / name
        d.mkdir(parents=True, exist_ok=True)
        text = (REPO / "templates" / tpl).read_text(encoding="utf-8")
        (d / "SKILL.md").write_text(text.replace(key, (REPO / "core" / core).read_text(encoding="utf-8")), encoding="utf-8")


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
            seen, err = h.discover(home, home), ""
        except Exception as e:   # a CLI change must fail loudly, with the reason
            seen, err = set(), f"{type(e).__name__}: {e}"
        check(f"harness [{name}]: after `hiviz init` the real CLI lists all {len(want)} hiviz {what} ({ver}, no model)",
              init.returncode == 0 and want <= seen, err or f"missing={sorted(want - seen)}")
        if not h.skills_dir:
            continue
        project, empty = fresh_home(f"discover-{name}-sandbox"), fresh_home(f"discover-{name}-empty-home")
        _render_skills(project, h.skills_dir)
        try:
            seen, err = h.discover(empty, project), ""
        except Exception as e:
            seen, err = set(), f"{type(e).__name__}: {e}"
        check(f"harness [{name}]: skills in the T2 sandbox layout ({h.skills_dir}) are discovered",
              {"hv-audit", "hv-apply"} <= seen, err or f"missing={sorted({'hv-audit', 'hv-apply'} - seen)}")
    _SECTION[0] = None
