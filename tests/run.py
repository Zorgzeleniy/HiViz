#!/usr/bin/env python3
"""hiviz test rig.

T1 (deterministic, free, hermetic — every harness gets its own fake $HOME under tests/out):
   installer per harness, meters vs fake stdio/HTTP MCP, drift, constitution, blame, translate.
T2 (E2E, LLM): audit -> ground-truth check -> deterministic decisions -> apply -> post-asserts.

Usage: python tests/run.py [--t1|--t2|--all]   (default: --all)
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HOME = Path.home()
OUT = REPO / "tests" / "out"
GT = json.loads((REPO / "tests" / "ground_truth.json").read_text(encoding="utf-8"))
PROFILE = HOME / ".omp/profiles/hiviz-test/agent"
RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, ok, detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))

def sh(cmd: list[str], timeout: int = 120, cwd: Path = REPO, **kw) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=timeout, **kw)
    except subprocess.TimeoutExpired as e:
        out = ((e.stdout or b"").decode("utf-8", "replace") if isinstance(e.stdout, bytes) else (e.stdout or ""))
        return subprocess.CompletedProcess(cmd, 124, "", f"TIMEOUT after {timeout}s; partial stdout: {out[-300:]}")


def templated_copy(src: Path, dst: Path) -> None:
    """Copy a fixture tree, rendering {{REPO}} into the absolute repo path."""
    repo_abs = str(REPO.resolve()).replace("\\", "/")
    for f in sorted(src.rglob("*")):
        if f.is_file():
            d = dst / f.relative_to(src)
            d.parent.mkdir(parents=True, exist_ok=True)
            d.write_text(f.read_text(encoding="utf-8").replace("{{REPO}}", repo_abs), encoding="utf-8")


HARNESS_ENV = ("CLAUDE_CONFIG_DIR", "CODEX_HOME", "PI_CODING_AGENT_DIR", "XDG_CONFIG_HOME",
               "HIVIZ_HARNESS", "CLAUDECODE")


def home_env(home: Path, **extra: str) -> dict:
    """Environment of a fake machine: HOME/USERPROFILE point at `home`, no inherited harness overrides."""
    env = {k: v for k, v in os.environ.items() if k not in HARNESS_ENV}
    env.update(HOME=str(home), USERPROFILE=str(home), **extra)
    return env


def fresh_home(name: str) -> Path:
    home = OUT / "homes" / name
    shutil.rmtree(home, ignore_errors=True)
    home.mkdir(parents=True)
    return home


SKILL_NAMES = ["audit", "apply", "drift", "constitution", "blame", "translate"]
CMD_NAMES = ["audit", "apply", "drift", "test", "blame", "translate"]
SHARED_SKILLS = [f".agents/skills/hv-{n}/SKILL.md" for n in SKILL_NAMES]
HARNESS_MARKERS = {"claude": ".claude", "codex": ".codex", "omp": ".omp/agent", "pi": ".pi/agent",
                   "cursor": ".cursor", "windsurf": ".codeium/windsurf", "opencode": ".config/opencode"}
EXPECTED = {
    "claude": [f".claude/commands/hv-{n}.md" for n in CMD_NAMES],
    "codex": SHARED_SKILLS,
    "omp": [f".omp/agent/skills/hv-{n}/SKILL.md" for n in SKILL_NAMES],
    "pi": SHARED_SKILLS,
    "cursor": SHARED_SKILLS,
    "windsurf": SHARED_SKILLS,
    "opencode": SHARED_SKILLS + [f".config/opencode/commands/hv-{n}.md" for n in CMD_NAMES],
}


def adapter_files(home: Path) -> set[str]:
    roots = [".claude", ".agents", ".omp/agent/skills", ".config/opencode/commands", ".codex", ".cursor/rules"]
    return {f.relative_to(home).as_posix() for r in roots if (home / r).exists()
            for f in (home / r).rglob("*") if f.is_file()}


def installer_checks() -> None:
    audit_src = (REPO / "core/AUDIT.md").read_text(encoding="utf-8")
    for h, marker in HARNESS_MARKERS.items():
        home = fresh_home(f"only-{h}")
        (home / marker).mkdir(parents=True)
        env = home_env(home)
        first = sh(["node", "bin/hiviz.js", "init"], env=env)
        second = sh(["node", "bin/hiviz.js", "init"], env=env)
        want = set(EXPECTED[h])
        got = adapter_files(home)
        missing, extra = sorted(want - got), sorted(got - want)
        unrendered = [w for w in want & got if "{{" in (home / w).read_text(encoding="utf-8")]
        eng = home / ".hiviz/engines/core/AUDIT.md"
        idem = " + " not in second.stdout and " - removed" not in second.stdout
        ok = (first.returncode == 0 and second.returncode == 0 and not missing and not extra
              and not unrendered and idem and eng.exists() and eng.read_text(encoding="utf-8") == audit_src)
        detail = (f"{len(want)} adapters + engines, idempotent" if ok else
                  f"rc={first.returncode}/{second.returncode} missing={missing[:3]} extra={extra[:3]} "
                  f"unrendered={unrendered[:2]} idempotent={idem} engines={eng.exists()} {first.stderr[-80:]}")
        check(f"installer [{h}]: adapters + engines", ok, detail)
        u = sh(["node", "bin/hiviz.js", "uninstall"], env=env)
        left = adapter_files(home)
        check(f"installer [{h}]: uninstall removes everything", u.returncode == 0 and not left
              and not (home / ".hiviz").exists(), f"left: {sorted(left)[:3]}" if left else "")

    # env overrides: the harness lives outside ~ and must be found there
    home = fresh_home("env-overrides")
    for d in ("cc", "cx", "pi-agent"):
        (home / d).mkdir()
    env = home_env(home, CLAUDE_CONFIG_DIR=str(home / "cc"), CODEX_HOME=str(home / "cx"),
                   PI_CODING_AGENT_DIR=str(home / "pi-agent"))
    r = sh(["node", "bin/hiviz.js", "init"], env=env)
    ok = (r.returncode == 0 and (home / "cc/commands/hv-audit.md").exists()
          and not (home / ".claude").exists() and "Codex/pi: wrote .agents/skills/hv-audit" in r.stdout)
    check("installer: CLAUDE_CONFIG_DIR / CODEX_HOME / PI_CODING_AGENT_DIR respected", ok,
          "" if ok else r.stdout[-200:])

    # no harness at all: engines still land (the GitHub Action and CI rely on them)
    home = fresh_home("bare")
    r = sh(["node", "bin/hiviz.js", "init"], env=home_env(home))
    check("installer: engines without any harness", r.returncode == 0
          and (home / ".hiviz/engines/drift/check.py").exists(), r.stdout.strip().splitlines()[0][:80])

    # migration from <=0.7 adapters; user-owned Windsurf rules are never touched
    home = fresh_home("legacy")
    user_rules = "# my own rules\n- keep answers short\n"
    legacy = {".codex/prompts/hv-audit.md": "old", ".codex/skills/hv-audit/SKILL.md": "old",
              ".cursor/rules/hiviz.mdc": "old", ".config/opencode/command/hiviz.md": "old",
              ".codeium/windsurf/memories/global_rules.md":
                  "Audit standing instructions for prompt debt (stale facts, duplicates, relics, conflicts). old"}
    for rel, txt in legacy.items():
        (home / rel).parent.mkdir(parents=True, exist_ok=True)
        (home / rel).write_text(txt, encoding="utf-8")
    user_home = fresh_home("windsurf-user-rules")
    (user_home / ".codeium/windsurf/memories").mkdir(parents=True)
    (user_home / ".codeium/windsurf/memories/global_rules.md").write_text(user_rules, encoding="utf-8")
    r1 = sh(["node", "bin/hiviz.js", "init"], env=home_env(home))
    r2 = sh(["node", "bin/hiviz.js", "init"], env=home_env(user_home))
    r3 = sh(["node", "bin/hiviz.js", "uninstall"], env=home_env(user_home))
    leftovers = [rel for rel in legacy if (home / rel).exists()]
    kept = (user_home / ".codeium/windsurf/memories/global_rules.md").read_text(encoding="utf-8")
    ok = r1.returncode == r2.returncode == r3.returncode == 0 and not leftovers and kept == user_rules
    check("installer: legacy adapters migrated, user Windsurf rules untouched", ok,
          "" if ok else f"leftovers={leftovers} user_rules_intact={kept == user_rules}")


def meters_discovery_check() -> None:
    """Auto-discovery across Claude/Codex/Cursor/Windsurf/OpenCode configs + usage from Claude/Codex logs."""
    sys.path.insert(0, str(REPO / "tests"))
    import fake_mcp_http
    srv, url = fake_mcp_http.start(tools=2, token="t0ken")
    try:
        home = fresh_home("meters")
        proj = home / "proj"
        proj.mkdir()
        py, fake = sys.executable, str(REPO / "tests/fake_mcp_server.py")
        stdio = {"command": py, "args": [fake, "--tools", "3", "--desc-bytes", "300"]}
        (home / ".claude.json").write_text(json.dumps({
            "mcpServers": {"cl-user": {"type": "stdio", **stdio}},
            "projects": {str(proj): {"mcpServers": {"cl-local": stdio}},
                         str(home / "elsewhere"): {"mcpServers": {"cl-other": stdio}}}}), encoding="utf-8")
        (home / ".codex").mkdir()
        (home / ".codex/config.toml").write_text(
            f"[mcp_servers.cx-stdio]\ncommand = {json.dumps(py)}\nargs = {json.dumps(stdio['args'])}\n\n"
            f"[mcp_servers.cx-http]\nurl = {json.dumps(url)}\nbearer_token_env_var = \"HV_TEST_TOKEN\"\n\n"
            f"[mcp_servers.cx-off]\ncommand = \"definitely-not-a-binary\"\nenabled = false\n", encoding="utf-8")
        (home / ".cursor").mkdir()
        (home / ".cursor/mcp.json").write_text(json.dumps({"mcpServers": {"cur": stdio}}), encoding="utf-8")
        (home / ".codeium/windsurf").mkdir(parents=True)
        (home / ".codeium/windsurf/mcp_config.json").write_text(
            json.dumps({"mcpServers": {"wind": stdio}}), encoding="utf-8")
        (home / ".config/opencode").mkdir(parents=True)
        (home / ".config/opencode/opencode.jsonc").write_text(
            '{\n  // opencode keeps comments and trailing commas\n  "mcp": {\n    "oc": {"type": "local", '
            f'"command": {json.dumps([py, *stdio["args"]])}, /* inline */ }},\n  }},\n}}\n', encoding="utf-8")
        shutil.copytree(REPO / "tests/fixture/usage/claude", home / ".claude")
        shutil.copytree(REPO / "tests/fixture/usage/codex", home / ".codex", dirs_exist_ok=True)
        r = sh([sys.executable, str(REPO / "meters/mcp_footprint.py"), "--out", str(home / "fp.json"),
                "--timeout", "3"], cwd=proj, env=home_env(home, HV_TEST_TOKEN="t0ken"), timeout=60)
        rows = {}
        if (home / "fp.json").exists():
            rows = {row["server"]: row for row in json.loads((home / "fp.json").read_text(encoding="utf-8"))["rows"]}
        errs = {n: row["error"][:60] for n, row in rows.items() if "error" in row}
        want = {"cl-user", "cl-local", "cx-stdio", "cx-http", "cur", "wind", "oc"}
        check("meters: configs of every MCP harness discovered + measured (stdio, streamable HTTP, jsonc)",
              r.returncode == 0 and set(rows) == want and not errs,
              f"servers={sorted(rows)}" + (f" errors={errs}" if errs else ""))
        calls = {n: rows[n].get("calls") for n in rows}
        ok = (calls.get("cl-user") == 1 and calls.get("cx-stdio") == 1 and calls.get("cx-http") == 1
              and calls.get("cl-local") == 0 and all(calls.get(n) is None for n in ("cur", "wind", "oc"))
              and rows.get("cx-stdio", {}).get("last_used") == "2026-09-26")
        check("meters: usage from Claude + Codex logs, unknown (not 0) where no logs exist", ok, f"calls={calls}")
    finally:
        srv.shutdown()


def t1() -> None:
    print("== T1: deterministic ==")
    installer_checks()

    mcp_cfg = OUT / "mcp_rendered.json"
    _mcp = json.loads((REPO / "tests/fixture/agent/mcp.json").read_text(encoding="utf-8"))
    _mcp["mcpServers"]["fake-bloated"]["command"] = sys.executable
    mcp_cfg.write_text(json.dumps(_mcp), encoding="utf-8")
    r = sh([sys.executable, "meters/mcp_footprint.py", "--config", str(mcp_cfg),
            "--sessions", "tests/fixture/blame/sessions",
            "--out", "tests/out/fake_mcp.json"])
    ok = r.returncode == 0
    row = {}
    if ok:
        data = json.loads((OUT / "fake_mcp.json").read_text(encoding="utf-8"))
        rows = [x for x in data["rows"] if "error" not in x]
        row = rows[0] if rows else {}
    check("meters: fake MCP measured", ok and bool(row), r.stderr.strip()[-120:] if not ok else "")
    if row:
        check("meters: weight + tokens + usage telemetry",
              row.get("tools") == 3 and 1200 <= row.get("bytes", 0) <= 4000
              and row.get("calls", 0) >= 2 and row.get("last_used") == "2026-09-03",
              f"tools={row.get('tools')} bytes={row.get('bytes')} tokens={row.get('tokens')} "
              f"calls={row.get('calls')} last={row.get('last_used')}")
    meters_discovery_check()

    d = sh([sys.executable, "drift/check.py", "--facts", "tests/fixture/hiviz/facts.toml",
            "--base", "tests/fixture",
            "--mcp-footprint", "tests/fixture/hiviz/mcp_footprint.json",
            "--out", "tests/out/drift.json"])
    d_ok = d.returncode == 1
    detail = (d.stderr or "")[-120:]
    if d_ok:
        drows = json.loads((OUT / "drift.json").read_text(encoding="utf-8"))
        stales = sorted(r["id"] for r in drows if r["status"] == "STALE")
        n_unv = len([r for r in drows if r["status"] == "UNVERIFIABLE"])
        n_ok = len([r for r in drows if r["status"] == "OK"])
        d_ok = (stales == ["legacy-runner-doc", "mcp:heavy-unused", "v3-migration-done"]
                and n_unv == 2 and n_ok == 6)
        detail = f"OK={n_ok} STALE={stales} UNVERIFIABLE={n_unv}"
    check("drift: planted statuses + MCP pay-vs-use detected", d_ok, detail)
    fp = OUT / "fp_unknown.json"
    fp.write_text(json.dumps({"rows": [
        {"server": "no-logs", "harnesses": "cursor/global", "tokens": 900, "calls": None, "last_used": None},
        {"server": "bad-date", "harnesses": "explicit", "tokens": 900, "calls": 3, "last_used": "never"}]}),
        encoding="utf-8")
    (OUT / "empty_facts.toml").write_text("[facts]\n", encoding="utf-8")
    d2 = sh([sys.executable, "drift/check.py", "--facts", str(OUT / "empty_facts.toml"), "--base", str(OUT),
             "--mcp-footprint", str(fp), "--out", str(OUT / "drift_unknown.json")])
    st = {}
    if (OUT / "drift_unknown.json").exists() and d2.returncode == 0:
        st = {r["id"]: r["status"] for r in json.loads((OUT / "drift_unknown.json").read_text(encoding="utf-8"))}
    check("drift: unknown usage / bad dates are UNVERIFIABLE, never STALE or a crash",
          st == {"mcp:no-logs": "UNVERIFIABLE", "mcp:bad-date": "UNVERIFIABLE"},
          f"rc={d2.returncode} {st or d2.stderr[-100:]}")

    fake_harness = f'"{sys.executable}" tests/fake_harness.py "{{ask}}"'
    (REPO / "tests/fake_harness.py").with_suffix(".state").unlink(missing_ok=True)
    c = sh([sys.executable, "constitution/run.py", "--tests", "tests/const_fixture",
           "--harness", fake_harness,
           "--corpus", "tests/fixture", "--out", "tests/out/constitution.json"])
    c_ok = c.returncode == 1
    cdetail = (c.stderr or "")[-140:]
    if c_ok:
        crows = json.loads((OUT / "constitution.json").read_text(encoding="utf-8"))
        v = {r["id"]: r["verdict"] for r in crows}
        c_ok = (v.get("pass-secrets") == "PASS" and v.get("pass-commit") == "PASS"
                and v.get("pass-language") == "PASS" and v.get("fail-offtopic") == "FAIL"
                and v.get("flaky-once") == "FLAKY" and v.get("orphaned-gone") == "ORPHANED")
        cdetail = f"verdicts: {v}"
    check("constitution: all verdict classes produced", c_ok, cdetail)
    for f in ("PWNED", "PWNED2"):
        (OUT / f).unlink(missing_ok=True)
    c2 = sh([sys.executable, "constitution/run.py", "--tests", "tests/const_fixture_edge",
             "--harness", fake_harness, "--corpus", "tests/fixture", "--out", "tests/out/constitution_edge.json"])
    v2 = {}
    if (OUT / "constitution_edge.json").exists():
        v2 = {r["id"]: r["verdict"] for r in json.loads((OUT / "constitution_edge.json").read_text(encoding="utf-8"))}
    pwned = [f for f in ("PWNED", "PWNED2") if (OUT / f).exists()]
    check("constitution: ask never shell-executed, harness failure = ERROR, guards_needle honored",
          c2.returncode == 1 and not pwned and v2 == {"injection": "PASS", "harness-broken": "ERROR",
                                                      "needle-gone": "ORPHANED"},
          f"verdicts={v2} executed={pwned}")

    fx = OUT / "blame_fx"
    shutil.rmtree(fx, ignore_errors=True)
    templated_copy(REPO / "tests/fixture/blame/sessions", fx / "sessions")
    templated_copy(REPO / "tests/fixture/blame", fx / "meta")
    b = sh([sys.executable, "blame/blame.py", "--file", "tests/fixture/agent/AGENTS.md",
           "--marker", "10.0.0.42", "--sessions", str(fx / "sessions"),
           "--ledger", str(fx / "meta/ledger.jsonl"),
           "--constitution", "tests/fixture/blame/constitution.json"])
    b_ok = b.returncode == 0 and all(s in (b.stdout or "") for s in
                                     ["zai/glm-test-model", "TOUCHED THIS LINE", "fixture plant"])
    check("blame: ledger + mined history + line-touch flag", b_ok,
          ((b.stdout or "").splitlines() or [""])[0][:100])
    for h, model, session in [("claude", "claude-test-model", "claude: move gateway note"),
                              ("codex", "codex-test-model", "rollout-2026-09-05T10-00"),
                              ("pi", "testprov/pi-test-model", "pi: gateway fix")]:
        templated_copy(REPO / "tests/fixture/blame/harnesses" / h, fx / h)
        bh = sh([sys.executable, "blame/blame.py", "--file", "tests/fixture/agent/AGENTS.md",
                 "--marker", "10.0.0.42", "--sessions", str(fx / h)])
        lines = [x for x in (bh.stdout or "").splitlines() if x.strip().startswith("- ")]
        ok = (bh.returncode == 0 and len(lines) == 1 and model in lines[0] and session in lines[0]
              and "TOUCHED THIS LINE" in lines[0])
        check(f"blame [{h}]: session log mined (model, session, touched line)", ok,
              lines[0].strip()[:110] if lines else (bh.stdout or bh.stderr).strip()[-110:])

    shutil.rmtree(OUT / "tr", ignore_errors=True)
    emitted, tr_err = {}, ""
    for t in ["omp", "claude", "codex", "pi", "opencode", "cursor", "windsurf"]:
        e = sh([sys.executable, "translate/emit.py", "--ir", "tests/fixture/ir.jsonl", "--target", t,
                "--out", f"tests/out/tr/{t}"])
        chk = sh([sys.executable, "translate/emit.py", "--ir", "tests/fixture/ir.jsonl", "--target", t,
                  "--out", f"tests/out/tr/{t}", "--check"])
        if e.returncode or chk.returncode:
            tr_err += f"{t}: {(e.stderr or chk.stdout)[-80:]} "
        emitted[t] = {f.relative_to(OUT / "tr" / t).as_posix(): f.read_text(encoding="utf-8")
                      for f in (OUT / "tr" / t).rglob("*") if f.is_file()}
    tr_ok = not tr_err
    if tr_ok:
        om, cl = emitted["omp"], emitted["claude"]
        single = {"claude": "CLAUDE.md", "codex": "AGENTS.md", "pi": "AGENTS.md", "opencode": "AGENTS.md",
                  "cursor": ".cursor/rules/hiviz.mdc", "windsurf": ".windsurf/rules/hiviz.md"}
        tr_ok = ("redact" in om["RULES.md"] and "explicit request" in om["RULES.md"]
                 and "redact" not in om["AGENTS.md"] and "10.0.0.99" in om["AGENTS.md"]
                 and "best practices" not in om["AGENTS.md"]
                 and "dedup" in om["translation-report.md"].lower() and om["translation-report.md"].count("| r") >= 5
                 and all(f in emitted[t] and "10.0.0.99" in emitted[t][f]
                         and emitted[t][f].find("redact") < emitted[t][f].find("10.0.0.99")
                         for t, f in single.items())
                 and emitted["cursor"][single["cursor"]].startswith("---\n")
                 and "alwaysApply: true" in emitted["cursor"][single["cursor"]]
                 and "trigger: always_on" in emitted["windsurf"][single["windsurf"]])
    check("translate: every target placed (omp split, safety first, cursor/windsurf rule frontmatter) + --check",
          tr_ok, f"7 targets, claude CLAUDE({len(cl['CLAUDE.md'].splitlines())}L)" if tr_ok
          else (tr_err or "content mismatch")[-160:])

# ---------------------------------------------------------------- T2
def profile_setup() -> None:
    if PROFILE.parent.exists():
        shutil.rmtree(PROFILE.parent)
    PROFILE.mkdir(parents=True)
    src = REPO / "tests/fixture/agent"
    for item in ["AGENTS.md", "RULES.md", "mcp.json", "skills"]:
        s = src / item
        d = PROFILE / item
        (shutil.copytree if s.is_dir() else shutil.copy2)(s, d)
    # render from the checkout — T1 no longer installs into the real ~/.omp
    tpl = (REPO / "templates/skill.md").read_text(encoding="utf-8")
    (PROFILE / "skills/hv-audit").mkdir(parents=True)
    (PROFILE / "skills/hv-audit/SKILL.md").write_text(
        tpl.replace("{{AUDIT_BODY}}", (REPO / "core/AUDIT.md").read_text(encoding="utf-8")), encoding="utf-8")
    for name, sub in [("superpowers", "superpowers/skills"), ("anthropic", "anthropic-skills/skills")]:
        vendor = REPO / "tests/fixture/vendor" / sub
        for d in sorted(vendor.iterdir()):
            if d.is_dir():
                shutil.copytree(d, PROFILE / "skills" / f"{name}-{d.name}")
    (PROFILE / "config.yml").write_text(
        "modelRoles:\n  default: zai/glm-5.3-flash:high\nmemory:\n  backend: local\n"
        "skills:\n  customDirectories:\n    - " + str(PROFILE / "skills").replace("\\", "/") + "\n",
        encoding="utf-8")


DECISIONS = """# HiViz decisions (final — authored by the test operator)

| target file (ABSOLUTE path — edit exactly this file, no other copy) | marker | action |
|---|---|---|
| {P}/AGENTS.md | `10.0.0.42 (legacy)` | rewrite: update the gateway line to 10.0.0.99 (migrated 2026-03); keep `npm run deploy` |
| {P}/AGENTS.md | `Write clean, readable code and follow best practices.` | delete the line |
| {P}/AGENTS.md | `Be careful and thorough when editing files.` | delete the line |
| {P}/AGENTS.md | `Final stack state (2026-01-15)` | delete the line |
| {P}/AGENTS.md | ``NEVER use the `git stash` command.`` | rewrite as: `Prefer explicit branches over `git stash`; use stash only to rescue uncommitted noise.` |
| {P}/skills/smelly-skill/SKILL.md | `Always include a summary table in every response` | delete the line |
| {P}/skills/smelly-skill/SKILL.md | the `Example output` block (hash d41d8cd…) | delete the whole fenced block |
| {P}/RULES.md | every line | KEEP (safety) |
| {P}/skills/clean-skill/SKILL.md | every line | KEEP |

Backups: next to each edited file, as `<name>.bak-<YYYYMMDD>`.
Probes (pre-authorized, headless `omp --profile hiviz-test -p "<ask>"`; save answers to {O}/probes-before.md and {O}/probes-after.md):
- P1 ask: "Without extra text: quote your directives about secrets." expect marker: `redact`
- P2 ask: "Without extra text: quote your directives about committing." expect marker: `explicit request`
"""


def t2() -> None:
    print("== T2: E2E on sandbox profile ==")
    OUT.mkdir(parents=True, exist_ok=True)
    o = OUT.as_posix()
    profile_setup()
    if not os.environ.get("ZAI_API_KEY"):
        # consistent online snapshot of the default profile's stored login (live db → use backup API)
        import sqlite3
        src_db = sqlite3.connect(str(HOME / ".omp/agent/agent.db"))
        dst_db = sqlite3.connect(str(PROFILE / "agent.db"))
        with dst_db:
            src_db.backup(dst_db)
        dst_db.close()
        src_db.close()
        check("t2: auth snapshot from default profile (agent.db)", (PROFILE / "agent.db").exists())
    pf = sh(["omp", "--profile", "hiviz-test", "-p", "Reply with the single word OK."], timeout=180)
    check("t2: profile pre-flight (omp boots)", "OK" in (pf.stdout or ""), (pf.stderr or "")[-120:])
    surfaces = [PROFILE / "AGENTS.md", PROFILE / "RULES.md",
                PROFILE / "skills/smelly-skill/SKILL.md", PROFILE / "skills/clean-skill/SKILL.md",
                PROFILE / "skills/superpowers-systematic-debugging/SKILL.md",
                PROFILE / "skills/anthropic-docx/SKILL.md"]
    audit_prompt = (
        "Use the hv-audit skill. Audit ONLY these instruction surfaces:\n"
        + "\n".join(str(p) for p in surfaces)
        + f"\nWrite {o}/report.md INCREMENTALLY — append each phase's table as soon as "
          "it is computed, do not hold the report in chat. Also write the decisions template to "
          f"{o}/decisions.md (DECISION column empty). Do NOT modify any audited file. "
          "Your final chat reply: one summary line only. English.")
    report = OUT / "report.md"
    reuse = os.environ.get("EXUVIA_REUSE") == "1"
    if reuse and report.exists() and "10.0.0.42" in (PROFILE / "AGENTS.md").read_text(encoding="utf-8"):
        print("  [skip] reusing existing report.md (EXUVIA_REUSE=1)")
    else:
        r = sh(["omp", "--profile", "hiviz-test", "-p", audit_prompt], timeout=1500)
        (OUT / "audit-last-output.txt").write_text(
            ((r.stdout or "")[-4000:]) + "\n--STDERR--\n" + ((r.stderr or "")[-1500:]), encoding="utf-8")
    check("audit: completed & report written", report.exists(),
          "see tests/out/audit-last-output.txt" if not report.exists() else "")
    if not report.exists():
        return
    body = report.read_text(encoding="utf-8")
    missing = [m for m in GT["must_find"] if m not in body]
    check(f"audit recall {len(GT['must_find']) - len(missing)}/{len(GT['must_find'])}",
          not missing, "missing: " + ", ".join(missing) if missing else "all planted smells found")
    import hashlib
    _h = lambda p: hashlib.md5(Path(p).read_bytes()).hexdigest()
    fx_files = {str(p): _h(p) for root in ["tests/fixture/agent", "tests/fixture/vendor"]
                for p in (REPO / root).rglob("*") if p.is_file()}
    (OUT / "decisions.md").write_text(
        DECISIONS.format(P=PROFILE.as_posix(), O=o),
        encoding="utf-8")
    apply_prompt = (
        f"Use the hv-apply procedure. The decisions file is {o}/decisions.md — "
        "it is complete and final; apply exactly its rows, nothing else. "
        "Back up every edited file (.bak-<date>). The two probes at the bottom are pre-authorized: "
        f"run them before and after the edits and save answers to {o}/probes-before.md "
        f"and {o}/probes-after.md (headless `omp --profile hiviz-test -p \"<ask>\"`). "
        "ORDER: make ALL file edits FIRST, then run the probes (before-snapshot from backups is acceptable "
        "if the session budget is tight). Do not commit. English.")
    r = sh(["omp", "--profile", "hiviz-test", "-p", apply_prompt], timeout=2400)
    (OUT / "apply-last-output.txt").write_text(
        ((r.stdout or "")[-4000:]) + "\n--STDERR--\n" + ((r.stderr or "")[-1500:]), encoding="utf-8")
    changed_fx = [p for p, h in fx_files.items() if _h(p) != h]
    check("fixture source untouched by apply", not changed_fx,
          "edited: " + ", ".join(Path(p).name for p in changed_fx) if changed_fx else "")

    for rel, markers in GT["post_apply_absent"].items():
        f = PROFILE / rel
        txt = f.read_text(encoding="utf-8") if f.exists() else ""
        left = [m for m in markers if m in txt]
        check(f"apply: {rel} cleaned", not left, "still present: " + ", ".join(left) if left else "")
    for rel, markers in GT["post_apply_present"].items():
        f = PROFILE / rel
        txt = f.read_text(encoding="utf-8") if f.exists() else ""
        gone = [m for m in markers if m not in txt]
        check(f"apply: {rel} keeps invariants", not gone, "LOST: " + ", ".join(gone) if gone else "")
    baks = list(PROFILE.glob("**/*.bak-*")) + list((PROFILE / "skills").glob("**/*.bak-*"))
    check("apply: backups created", len(baks) >= 2, f"{len(baks)} .bak files")
    pa = OUT / "probes-after.md"
    check("apply: probes ran", pa.exists() and "redact" in pa.read_text(encoding="utf-8").lower(),
          "probes-after.md with safety quote" if pa.exists() else "no probes-after.md")
    vendor_installed = sorted(p.name for p in (PROFILE / "skills").glob("superpowers-*"))[:3]
    check("t2: popular vendor skills present in sandbox", len(vendor_installed) >= 3,
          f"{len(list((PROFILE / 'skills').glob('superpowers-*')))} superpowers + "
          f"{len(list((PROFILE / 'skills').glob('anthropic-*')))} anthropic")
    with open(REPO / "tests/results.log", "a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M')} model=glm-5.3-flash:high "
                f"passed={len(RESULTS) - len([r for r in RESULTS if not r[1]])}/{len(RESULTS)}\n")


def summary() -> int:
    failed = [r for r in RESULTS if not r[1]]
    print(f"\n== {len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed ==")
    return 1 if failed else 0


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    ap = argparse.ArgumentParser()
    ap.add_argument("--t1", action="store_true")
    ap.add_argument("--t2", action="store_true")
    ap.add_argument("--all", action="store_true")
    a = ap.parse_args()
    if a.t1 or a.all or not (a.t1 or a.t2):
        t1()
    if a.t2 or a.all:
        t2()
    return summary()


if __name__ == "__main__":
    sys.exit(main())
