#!/usr/bin/env python3
"""hiviz test rig.

T1 (deterministic, free): adapter render, installer idempotency, meters vs fake MCP.
T2 (E2E, LLM): audit -> ground-truth check -> deterministic decisions -> apply -> post-asserts.

Usage: python tests/run.py [--t1|--t2|--all]   (default: --all)
"""
from __future__ import annotations

import argparse
import json
import os
import re
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

def sh(cmd: list[str], timeout: int = 120, **kw) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(cmd, cwd=REPO, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=timeout, **kw)
    except subprocess.TimeoutExpired as e:
        out = ((e.stdout or b"").decode("utf-8", "replace") if isinstance(e.stdout, bytes) else (e.stdout or ""))
        return subprocess.CompletedProcess(cmd, 124, "", f"TIMEOUT after {timeout}s; partial stdout: {out[-300:]}")


# ---------------------------------------------------------------- T1
def t1() -> None:
    print("== T1: deterministic ==")

    first = sh(["node", "bin/hiviz.js", "init"])
    second = sh(["node", "bin/hiviz.js", "init"])
    check("installer idempotent", first.returncode == 0 and second.returncode == 0
          and " + " not in second.stdout, "second run adds nothing")

    installed = [HOME / ".claude/skills/hv-audit/SKILL.md",
                 HOME / ".omp/agent/skills/hv-audit/SKILL.md"]
    installed = [p for p in installed if p.exists()]
    bad = [str(p) for p in installed if "{{" in p.read_text(encoding="utf-8")]
    check("adapters rendered (no placeholders)", bool(installed) and not bad,
          f"{len(installed)} adapters" + (f", unrendered: {bad}" if bad else ""))
    eng = HOME / ".hiviz/engines/core/AUDIT.md"
    check("installer deploys engines", eng.exists() and
          eng.read_text(encoding="utf-8") == (REPO / "core/AUDIT.md").read_text(encoding="utf-8"),
          str(eng) if eng.exists() else "~/.hiviz/engines missing")

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

    (REPO / "tests/fake_harness.py").with_suffix(".state").unlink(missing_ok=True)
    c = sh([sys.executable, "constitution/run.py", "--tests", "tests/const_fixture",
           "--harness", sys.executable + ' tests/fake_harness.py "{ask}"',
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
    fx = OUT / "blame_fx"
    shutil.rmtree(fx, ignore_errors=True)
    (fx / "sessions").mkdir(parents=True, exist_ok=True)
    repo_abs = str(REPO.resolve()).replace("\\", "/")
    src = REPO / "tests/fixture/blame/sessions"
    for jf in sorted(src.rglob("*.jsonl")):
        dst = fx / "sessions" / jf.relative_to(src)
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(jf.read_text(encoding="utf-8").replace("{{REPO}}", repo_abs), encoding="utf-8")
    led_path = fx / "ledger.jsonl"
    led_path.write_text((REPO / "tests/fixture/blame/ledger.jsonl").read_text(encoding="utf-8")
                        .replace("{{REPO}}", repo_abs), encoding="utf-8")
    b = sh([sys.executable, "blame/blame.py", "--file", "tests/fixture/agent/AGENTS.md",
           "--marker", "10.0.0.42", "--sessions", str(fx / "sessions"),
           "--ledger", str(led_path),
           "--constitution", "tests/fixture/blame/constitution.json"])
    b_ok = b.returncode == 0 and all(s in (b.stdout or "") for s in
                                     ["zai/glm-test-model", "TOUCHED THIS LINE", "fixture plant"])
    check("blame: ledger + mined history + line-touch flag", b_ok,
          ((b.stdout or "").splitlines() or [""])[0][:100])

    for sub in ["tr-omp", "tr-claude"]:
        shutil.rmtree(OUT / sub, ignore_errors=True)
    e1 = sh([sys.executable, "translate/emit.py", "--ir", "tests/fixture/ir.jsonl", "--target", "omp", "--out", "tests/out/tr-omp"])
    e2 = sh([sys.executable, "translate/emit.py", "--ir", "tests/fixture/ir.jsonl", "--target", "claude", "--out", "tests/out/tr-claude"])
    tr_ok = e1.returncode == 0 and e2.returncode == 0
    if tr_ok:
        r_txt = (OUT / "tr-omp/RULES.md").read_text(encoding="utf-8")
        a_txt = (OUT / "tr-omp/AGENTS.md").read_text(encoding="utf-8")
        c_txt = (OUT / "tr-claude/CLAUDE.md").read_text(encoding="utf-8")
        rep = (OUT / "tr-omp/translation-report.md").read_text(encoding="utf-8")
        tr_ok = ("redact" in r_txt and "explicit request" in r_txt
                 and "redact" not in a_txt and "10.0.0.99" in a_txt
                 and "best practices" not in a_txt
                 and "redact" in c_txt and "10.0.0.99" in c_txt
                 and "dedup" in rep.lower() and rep.count("| r") >= 5)
    check("translate: omp/claude placement + dedup drop + report", tr_ok,
          f"omp RULES+AGENTS, claude CLAUDE({len(c_txt.splitlines())}L)" if tr_ok
          else ((e1.stderr or e2.stderr) or "content mismatch")[-120:])

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
    audit_skill = HOME / ".omp/agent/skills/hv-audit"
    shutil.copytree(audit_skill, PROFILE / "skills/hv-audit")
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
