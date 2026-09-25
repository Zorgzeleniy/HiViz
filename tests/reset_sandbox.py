#!/usr/bin/env python3
"""Reset the hiviz sandbox profile (~/.omp/profiles/hiviz-test) for MANUAL play.

Plants the realistic corpus (AGENTS.md with smells, safety RULES.md, smelly/clean
skills, 21 vendored popular skills, fake MCP, current hiviz skills) and snapshots
auth from the default profile. Run this before each manual walkthrough.
"""
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import run  # noqa: E402  (profile_setup lives in the rig)

run.profile_setup()

# funnel-format skill: render straight from core/ (the global ~/.omp copy may
# lag while the format is under user testing — do not deploy outside the sandbox)
REPO = Path(__file__).resolve().parent.parent
tpl = (REPO / "templates/skill.md").read_text(encoding="utf-8")
body = (tpl.replace("{{AUDIT_BODY}}", (REPO / "core/AUDIT.md").read_text(encoding="utf-8"))
           .replace("{{APPLY_BODY}}", (REPO / "core/APPLY.md").read_text(encoding="utf-8")))
(run.PROFILE / "skills/hv-audit/SKILL.md").write_text(body, encoding="utf-8")
src = sqlite3.connect(str(run.HOME / ".omp/agent/agent.db"))
dst = sqlite3.connect(str(run.PROFILE / "agent.db"))
with dst:
    src.backup(dst)
src.close()
dst.close()

ag = (run.PROFILE / "AGENTS.md").read_text(encoding="utf-8")
print("sandbox ready:", run.PROFILE)
print("  AGENTS.md:", len(ag), "bytes | planted smells:",
      sum(m in ag for m in ["best practices", "Be careful", "2026-01-15", "git stash", "10.0.0.42"]), "/5")
print("  skills:", len(list((run.PROFILE / "skills").glob("*/"))),
      "| auth: ok | model: glm-5.3-flash:high")
print("\nStart playing:  cd D:/Ai/hiviz && omp --profile hiviz-test")
