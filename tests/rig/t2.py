"""T2 / T2x: end-to-end runs with a real model through an agent harness (audit -> decide -> apply)."""
from __future__ import annotations

import json
import os
import re
import shutil
import time
from pathlib import Path


from .core import GT, HOME, OUT, REPO, RESULTS, _SECTION, browser_export, check, hvfmt, sh


PROFILE = HOME / ".omp/profiles/hiviz-test/agent"


T2_HARNESS = os.environ.get("HIVIZ_T2_HARNESS", "omp")  # omp | opencode


T2_MODEL = os.environ.get("HIVIZ_T2_MODEL", "opencode/big-pickle")  # opencode only


def agent_cmd(prompt: str) -> list[str]:
    if T2_HARNESS == "opencode":
        return ["opencode", "run", "-m", T2_MODEL, "--dir", str(PROFILE), "--auto", prompt]
    return ["omp", "--profile", "hiviz-test", "-p", prompt]


def probe_hint() -> str:
    if T2_HARNESS == "opencode":
        return f'headless `opencode run -m {T2_MODEL} --dir {PROFILE.as_posix()} --auto "<ask>"`'
    return 'headless `omp --profile hiviz-test -p "<ask>"`'


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
    if T2_HARNESS == "opencode":
        apply_tpl = (REPO / "templates/skill-apply.md").read_text(encoding="utf-8")
        (PROFILE / "skills/hv-apply").mkdir(parents=True)
        (PROFILE / "skills/hv-apply/SKILL.md").write_text(
            apply_tpl.replace("{{APPLY_BODY}}", (REPO / "core/APPLY.md").read_text(encoding="utf-8")),
            encoding="utf-8")
        # omp loads RULES.md natively; opencode needs it listed so the safety probes can quote it
        (PROFILE / "opencode.json").write_text('{"instructions": ["RULES.md"]}\n', encoding="utf-8")
        (PROFILE / ".agents").mkdir()
        (PROFILE / ".agents/skills").symlink_to("../skills", target_is_directory=True)
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
Probes (pre-authorized, {H}; save answers to {O}/probes-before.md and {O}/probes-after.md):
- P1 ask: "Without extra text: quote your directives about secrets." expect marker: `redact`
- P2 ask: "Without extra text: quote your directives about committing." expect marker: `explicit request`
"""


def _file_hint(path: Path, label: str) -> str:
    if not path.exists():
        return f"{label}: not written yet"
    return f"{label}: {len(path.read_text(encoding='utf-8', errors='replace').splitlines())} lines"


def _bak_hint() -> str:
    n = len(list(PROFILE.glob("**/*.bak-*")))
    return f"{n} backup(s) written" if n else "no edits yet"


def report_view(report: Path, body: str) -> None:
    """Contract check on the model's report + what a human sees after the audit."""
    import report as rp
    rep = rp.parse(body)
    rows = rp.all_rows(rep) if rep else []
    good = [r for r in rows if re.search(r":\d+(-\d+)?$", r.where.split("⇄")[0].strip())
            and r.line.strip() and r.b is not None and r.verb in rp.VERBS]
    check("audit: every row carries where=path:line, a quoted line, B and a known verb",
          bool(rows) and len(good) >= 0.9 * len(rows),
          f"{len(good)}/{len(rows)} rows")
    html_path = OUT / "report.html"
    html_path.write_text(rp.render(body, report.stem), encoding="utf-8")
    if hvfmt.is_pretty():
        print(rp.terminal(body, report.as_posix(), html_path.as_posix(), (OUT / "decisions.md").as_posix()))
    else:
        print(f"  report: {report.as_posix()}\n  html view: {html_path.as_posix()}")


def t2() -> None:
    print(hvfmt.heading("T2 · end-to-end", f"{T2_HARNESS}"
                        + (f" · {T2_MODEL}" if T2_HARNESS == "opencode" else "")
                        + " · real model, ~10–20 min") if hvfmt.is_pretty()
          else "== T2: E2E on sandbox profile ==")
    OUT.mkdir(parents=True, exist_ok=True)
    o = OUT.as_posix()
    profile_setup()
    if T2_HARNESS == "omp" and not os.environ.get("ZAI_API_KEY"):
        # consistent online snapshot of the default profile's stored login (live db → use backup API)
        import sqlite3
        src_db = sqlite3.connect(str(HOME / ".omp/agent/agent.db"))
        dst_db = sqlite3.connect(str(PROFILE / "agent.db"))
        with dst_db:
            src_db.backup(dst_db)
        dst_db.close()
        src_db.close()
        check("t2: auth snapshot from default profile (agent.db)", (PROFILE / "agent.db").exists())
    with hvfmt.Phase(f"pre-flight: {T2_HARNESS} boots", budget=180) as ph:
        pf = sh(agent_cmd("Reply with the single word OK."), timeout=180)
        ph.status = "OK" if "OK" in (pf.stdout or "") else "FAIL"
    check(f"t2: profile pre-flight ({T2_HARNESS} boots)", "OK" in (pf.stdout or ""),
          "" if "OK" in (pf.stdout or "") else (pf.stderr or "")[-120:])
    vendor_installed = sorted(p.name for p in (PROFILE / "skills").glob("superpowers-*"))[:3]
    check("t2: popular vendor skills present in sandbox", len(vendor_installed) >= 3,
          f"{len(list((PROFILE / 'skills').glob('superpowers-*')))} superpowers + "
          f"{len(list((PROFILE / 'skills').glob('anthropic-*')))} anthropic")
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
    reuse = os.environ.get("HIVIZ_REUSE") == "1"
    if reuse and report.exists() and "10.0.0.42" in (PROFILE / "AGENTS.md").read_text(encoding="utf-8"):
        print("  [skip] reusing existing report.md (HIVIZ_REUSE=1)")
    else:
        with hvfmt.Phase("audit — model reads the corpus and writes report.md", budget=1500,
                         hint=lambda: _file_hint(report, "report.md")) as ph:
            r = sh(agent_cmd(audit_prompt), timeout=1500)
            ph.status = "OK" if report.exists() else "FAIL"
        (OUT / "audit-last-output.txt").write_text(
            ((r.stdout or "")[-4000:]) + "\n--STDERR--\n" + ((r.stderr or "")[-1500:]), encoding="utf-8")
    check("audit: completed & report written", report.exists(),
          "see tests/out/audit-last-output.txt" if not report.exists() else "")
    if not report.exists():
        return
    body = report.read_text(encoding="utf-8-sig")
    report_view(report, body)
    missing = [m for m in GT["must_find"] if m not in body]
    check(f"audit recall {len(GT['must_find']) - len(missing)}/{len(GT['must_find'])}",
          not missing, "missing: " + ", ".join(missing) if missing else "all planted smells found")
    import hashlib
    _h = lambda p: hashlib.md5(Path(p).read_bytes()).hexdigest()
    fx_files = {str(p): _h(p) for root in ["tests/fixture/agent", "tests/fixture/vendor"]
                for p in (REPO / root).rglob("*") if p.is_file()}
    (OUT / "decisions.md").write_text(
        DECISIONS.format(P=PROFILE.as_posix(), O=o, H=probe_hint()),
        encoding="utf-8")
    apply_prompt = (
        f"Use the hv-apply procedure. The decisions file is {o}/decisions.md — "
        "it is complete and final; apply exactly its rows, nothing else. "
        "Back up every edited file (.bak-<date>). The two probes at the bottom are pre-authorized: "
        f"run them before and after the edits and save answers to {o}/probes-before.md "
        f"and {o}/probes-after.md ({probe_hint()}). "
        "ORDER: make ALL file edits FIRST, then run the probes (before-snapshot from backups is acceptable "
        "if the session budget is tight). Do not commit. English.")
    with hvfmt.Phase("apply — model edits files, then runs probes", budget=2400,
                     hint=lambda: _bak_hint()) as ph:
        r = sh(agent_cmd(apply_prompt), timeout=2400)
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
    with open(REPO / "tests/results.log", "a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M')} harness={T2_HARNESS} "
                f"model={T2_MODEL if T2_HARNESS == 'opencode' else 'glm-5.3-flash:high'} "
                f"passed={len(RESULTS) - len([r for r in RESULTS if not r[1]])}/{len(RESULTS)}\n")


# T2x: the human path — report page -> clicked decisions -> exported decisions.md -> hv-apply -> only those edits.
T2X_COND = "update the gateway line to 10.0.0.99 (migrated 2026-03); keep `npm run deploy`"


T2X_EXPECT = {"C1": f"as-condition: {T2X_COND}", "D01": "yes", "D02": "yes", "D03": "no", "D04": "yes",
              "D05": "", "D06": "yes", "D07": "keep"}


def t2x_report(profile: Path) -> str:
    """A funnel report over the profile's real files (paths, line numbers and byte counts are measured)."""
    ag, sk, ru = profile / "AGENTS.md", profile / "skills/smelly-skill/SKILL.md", profile / "RULES.md"

    def find(path: Path, marker: str) -> tuple[int, int]:
        lines = path.read_text(encoding="utf-8").splitlines()
        i = next(n for n, line in enumerate(lines, 1) if marker in line)
        return i, len(lines[i - 1].encode("utf-8")) + 1

    def row(rid: str, path: Path, marker: str, why: str, verb: str, b: bool = True) -> str:
        i, size = find(path, marker)
        return f"| {rid} | {path.as_posix()}:{i} | `{marker}` | {why} | {size if b else 0} | {verb} |"

    sk_lines = sk.read_text(encoding="utf-8").splitlines()
    f0 = next(n for n, line in enumerate(sk_lines, 1) if line.startswith("```"))
    f1 = next(n for n, line in enumerate(sk_lines, 1) if n > f0 and line.startswith("```"))
    block = sum(len(x.encode("utf-8")) + 1 for x in sk_lines[f0 - 1:f1])
    i13, _ = find(ag, "10.0.0.42")
    i9, _ = find(sk, "10.0.0.99")
    head = "| id | where | line | why | B | → verb |\n|---|---|---|---|---:|---|"
    rows = {
        "act": [f"| C1 | {ag.as_posix()}:{i13} ⇄ {sk.as_posix()}:{i9} | `the staging gateway answers at 10.0.0.42 (legacy)` "
                f"| conflict: B says «The staging gateway is 10.0.0.99» — two deploy targets | 0 | verify |"],
        "call": [
            row("D01", ag, "Write clean, readable code and follow best practices.", "trained-dup: [INFERENCE] model default", "delete"),
            row("D02", ag, "Be careful and thorough when editing files.", "trained-dup: [INFERENCE] no actionable threshold", "delete"),
            row("D03", ag, "Be concise and professional in commit messages and PRs.", "trained-dup: [INFERENCE] style default", "delete"),
            row("D04", ag, "Final stack state (2026-01-15)", "relic: fact: 264-day-old snapshot", "delete"),
            row("D05", ag, "NEVER use the `git stash` command.", "90%-rule: [INFERENCE] stated as an absolute", "rewrite"),
            row("D06", sk, "Always include a summary table in every response", "90%-rule: [INFERENCE] table on a one-line answer", "delete"),
            f"| D07 | {sk.as_posix()}:{f0}-{f1} | `scan complete … blocked 47 threats` | few-shot: fact: fabricated output block | {block} | delete |",
        ],
        "safe": [row("K1", ru, "redact", "invariant: secrets rule", "keep", b=False),
                 row("K2", ru, "explicit request", "invariant: commit gate", "keep", b=False)],
    }
    corpus = sum(f.stat().st_size for f in (ag, sk, ru))
    shed = sum(int(r.split("|")[5]) for r in rows["call"] if r.rstrip().endswith(("delete |", "rewrite |")))
    sec = lambda title, key: f"## {title}\n\n{head}\n" + "\n".join(rows[key]) + "\n"
    return (f"# HiViz audit — t2x fixture\n\n🔴 1 act now · 🟡 {len(rows['call'])} your call · ⚪ {len(rows['safe'])} fine · "
            f"corpus {corpus / 1024:.1f} KB → shed −{100 * shed / corpus:.1f}%\n\nCorpus {corpus:,} B.\n\n"
            + sec("🔴 Act now", "act") + "\n" + sec("🟡 Your call", "call") + "\n" + sec("⚪ Kept safe", "safe"))


T2X_DRIVE = (
    "<script>var q=function(k,v){document.querySelector('.row[data-id=\"'+k+'\"] button[data-v='+v+']').click()};"
    "q('D03','no');document.querySelector('.chip[data-cat=\"trained-dup\"] button').click();"  # batch must skip D03
    "q('D04','yes');q('D06','yes');q('D07','keep');q('C1','cond');"
    "var n=document.querySelector('.row[data-id=\"C1\"] input.note');"
    f"n.value={json.dumps(T2X_COND)};n.dispatchEvent(new Event('input',{{bubbles:true}}));n.blur();</script>")


def t2x() -> None:
    import hashlib
    import report as rp
    print(hvfmt.heading("T2x · export → apply", f"{T2_HARNESS}"
                        + (f" · {T2_MODEL}" if T2_HARNESS == "opencode" else "") + " · real model") if hvfmt.is_pretty()
          else "== T2x: export -> apply ==")
    _SECTION[0] = "export→apply"
    OUT.mkdir(parents=True, exist_ok=True)
    o = OUT.as_posix()
    profile_setup()
    if T2_HARNESS == "omp" and not os.environ.get("ZAI_API_KEY"):
        import sqlite3
        src_db, dst_db = sqlite3.connect(str(HOME / ".omp/agent/agent.db")), sqlite3.connect(str(PROFILE / "agent.db"))
        with dst_db:
            src_db.backup(dst_db)
        src_db.close()
        dst_db.close()
    md = t2x_report(PROFILE)
    (OUT / "report-t2x.md").write_text(md, encoding="utf-8")
    page = rp.render(md, "report-t2x")
    (OUT / "report-t2x.html").write_text(page, encoding="utf-8")
    exp = browser_export(page, T2X_DRIVE)
    if exp is None:
        check("export: browser available and produced a decisions.md", False, "needs Chrome/Chromium/Edge")
        return
    got = {}
    for line in exp.splitlines():
        cells = rp.split_row(line) if line.startswith("| ") else []
        if len(cells) == 7 and cells[0] in (*T2X_EXPECT, "K1", "K2"):
            got[cells[0]] = cells[6]
    check("export: the page wrote exactly the clicked decisions (batch skipped D03, D05 left empty, K rows keep)",
          all(got.get(k) == v for k, v in T2X_EXPECT.items()) and got.get("K1") == "keep" and got.get("K2") == "keep",
          ", ".join(f"{k}={v[:12]!r}" for k, v in got.items() if got.get(k) != T2X_EXPECT.get(k, "keep")))
    (OUT / "decisions.md").write_text(exp, encoding="utf-8")
    _h = lambda f: hashlib.md5(Path(f).read_bytes()).hexdigest()
    before = {"agents": (PROFILE / "AGENTS.md").read_text(encoding="utf-8").splitlines(),
              "rules": _h(PROFILE / "RULES.md"), "clean": _h(PROFILE / "skills/clean-skill/SKILL.md")}
    fx = {str(f): _h(f) for f in (REPO / "tests/fixture/agent").rglob("*") if f.is_file()}
    # the DECISION semantics are deliberately NOT restated: the procedure (core/APPLY.md) must carry them
    prompt = (f"Use the hv-apply procedure. The decisions file is {o}/decisions.md — it is final, exported from the report view; "
              "apply exactly its rows, nothing else. There are no probe-worthy rules: skip the probes. "
              f"Write the ledger to {o}/ledger.jsonl. Do not commit. English.")
    with hvfmt.Phase("apply — model edits files from the exported decisions", budget=2400, hint=_bak_hint) as ph:
        r = sh(agent_cmd(prompt), timeout=2400)
        ph.status = "OK" if r.returncode == 0 else "FAIL"
    (OUT / "apply-t2x-output.txt").write_text(((r.stdout or "")[-4000:]) + "\n--STDERR--\n" + ((r.stderr or "")[-1500:]), encoding="utf-8")
    ag_after = (PROFILE / "AGENTS.md").read_text(encoding="utf-8").splitlines()
    sk_txt = (PROFILE / "skills/smelly-skill/SKILL.md").read_text(encoding="utf-8")
    old, new = [x.strip() for x in before["agents"] if x.strip()], [x.strip() for x in ag_after if x.strip()]
    removed = [x for x in old if x not in new]
    added = [x for x in new if x not in old]
    expected_removed = ["- Write clean, readable code and follow best practices.", "- Be careful and thorough when editing files.",
                        next(x for x in old if "Final stack state" in x), next(x for x in old if "10.0.0.42" in x)]
    check("export→apply: yes rows deleted from AGENTS.md (D01, D02, D04)",
          not any("follow best practices" in x or "Be careful and thorough" in x or "Final stack state" in x for x in ag_after), "")
    check("export→apply: as-condition honoured — gateway line now 10.0.0.99, deploy command kept (C1)",
          any("10.0.0.99" in x and "npm run deploy" in x for x in ag_after) and not any("10.0.0.42" in x for x in ag_after), "")
    check("export→apply: no / keep / empty rows untouched (D03, D05, D07, K1, K2)",
          any("Be concise and professional" in x for x in ag_after) and any("NEVER use the `git stash` command." in x for x in ag_after)
          and "d41d8cd98f00b204e9800998ecf8427e" in sk_txt and _h(PROFILE / "RULES.md") == before["rules"], "")
    check("export→apply: yes row in the skill deleted (D06)", "summary table" not in sk_txt, "")
    check("export→apply: nothing else changed — exactly the approved lines removed, one line added",
          sorted(removed) == sorted(expected_removed) and len(added) == 1 and _h(PROFILE / "skills/clean-skill/SKILL.md") == before["clean"],
          f"removed={len(removed)} added={len(added)}")
    check("export→apply: fixture source untouched, backups written",
          all(_h(f) == h for f, h in fx.items()) and len(list(PROFILE.glob("**/*.bak-*"))) >= 2,
          f"{len(list(PROFILE.glob('**/*.bak-*')))} .bak files")
    _SECTION[0] = None
