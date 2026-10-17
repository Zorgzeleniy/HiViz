"""T1: the apply verifier (apply/verify.py) — what it must accept, what it must refuse. No model."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import time

from .core import OUT, REPO, check, sh

OLD = [
    "# Project rules",                                        # 1
    "",                                                       # 2
    "- Write clean code and follow best practices.",          # 3  D1 delete
    "- Be careful and thorough when editing files.",          # 4  D2 delete
    "- NEVER use the git stash command.",                     # 5  D3 rewrite
    "- Always run the full test suite before every commit.",  # 6  D4 decided no
    "- The staging gateway answers at 10.0.0.42 (legacy).",   # 7  C1 as-condition (conflict with skill.md:9)
    "- Be concise in commit messages.",                       # 8  D5 undecided
    "- NEVER print secrets verbatim — redact them.",          # 9  K1 kept safe
    "- Answer in English by default.",                        # 10 nobody's row
    "## Env",                                                 # 11
    "- Final stack state (2026-01-15): toolchain v2.1.",      # 12 D6 delete
    "```",                                                    # 13 D7 delete (block 13-15)
    "scan complete",                                          # 14
    "```",                                                    # 15
]
SKILL_OLD = [f"filler {n}" for n in range(1, 9)] + ["- The staging gateway is 10.0.0.99 (migrated 2026-03)."]
CONDITION = "update the gateway line to 10.0.0.99"
HEAD = "| id | where | line | why | B | → verb | DECISION |\n|---|---|---|---|---:|---|---|"
SECTION = {"act": "🔴 Act now", "call": "🟡 Your call", "safe": "⚪ Kept safe"}


def row(rid, sec, line, quote, verb, decision, other=None):
    return {"id": rid, "sec": sec, "line": line, "quote": quote, "verb": verb, "decision": decision, "other": other}


def default_rows():
    return [
        row("C1", "act", 7, "the staging gateway answers at 10.0.0.42 (legacy)", "verify", f"as-condition: {CONDITION}",
            other=("skill.md", 9, "The staging gateway is 10.0.0.99")),
        row("D1", "call", 3, "Write clean code and follow best practices.", "delete", "yes"),
        row("D2", "call", 4, "Be careful and thorough when editing files.", "delete", "yes"),
        row("D3", "call", 5, "NEVER use the git stash command.", "rewrite", "yes"),
        row("D4", "call", 6, "Always run the full test suite before every commit.", "rewrite", "no"),
        row("D5", "call", 8, "Be concise in commit messages.", "delete", ""),
        row("D6", "call", 12, "Final stack state (2026-01-15)", "delete", "yes"),
        row("D7", "call", "13-15", "scan complete", "delete", "yes"),
        row("K1", "safe", 9, "NEVER print secrets verbatim — redact them.", "keep", "keep"),
    ]


def edit(lines, changes):
    out = []
    for i, line in enumerate(lines, 1):
        if i not in changes:
            out.append(line)
        elif changes[i] is not None:
            out += changes[i] if isinstance(changes[i], list) else [changes[i]]
    return out


PERFECT = {3: "", 4: None, 5: "- Prefer explicit branches over git stash.", 7: "- The staging gateway answers at 10.0.0.99.",
           12: None, 13: None, 14: None, 15: None}


def decisions_text(d, rows):
    out = ["# HiViz decisions — fixture", "", "DECISION: yes / no / keep / as-condition: <text>", ""]
    for sec in ("act", "call", "safe"):
        mine = [r for r in rows if r["sec"] == sec]
        if not mine:
            continue
        out += [f"## {SECTION[sec]}", "", HEAD]
        for r in mine:
            where = f"{d / 'AGENTS.md'}:{r['line']}"
            if r["other"]:
                where += f" ⇄ {d / r['other'][0]}:{r['other'][1]}"
            why = "conflict: B says «" + r["other"][2] + "» — two targets" if r["other"] else f"trained-dup: {r['id']}"
            out.append(f"| {r['id']} | {where} | `{r['quote']}` | {why} | 10 | {r['verb']} | {r['decision']} |")
        out.append("")
    return "\n".join(out)


def build(name, new=None, rows=None, *, backup=True, skill_new=None, ledger="full", extra=None, crlf_backup=False):
    """A fresh case dir: decisions first, then backups, then the files as apply left them."""
    d = OUT / "verify_fx" / name
    shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True)
    rows = rows if rows is not None else default_rows()
    dec = d / "decisions.md"
    dec.write_text(decisions_text(d, rows), encoding="utf-8")
    time.sleep(0.02)
    new = new if new is not None else edit(OLD, PERFECT)
    skill_new = skill_new if skill_new is not None else SKILL_OLD
    if backup:
        text = "\r\n".join(OLD) + "\r\n" if crlf_backup else "\n".join(OLD) + "\n"
        (d / "AGENTS.md.bak-20261007").write_bytes(("\ufeff" + text).encode("utf-8") if crlf_backup else text.encode("utf-8"))
        (d / "skill.md.bak-20261007").write_text("\n".join(SKILL_OLD) + "\n", encoding="utf-8")
    (d / "AGENTS.md").write_text("\n".join(new) + "\n", encoding="utf-8")
    (d / "skill.md").write_text("\n".join(skill_new) + "\n", encoding="utf-8")
    for fname, text in (extra or {}).items():
        (d / fname).write_text(text, encoding="utf-8")
    if ledger:
        entries = [{"file": str(d / "AGENTS.md"), "marker": r["quote"], "written_at": "2026-10-07T00:00:00Z", "model": "t",
                    "reason": r["id"], "action": "deleted"} for r in rows if r["decision"] in ("yes",) or r["decision"].startswith("as-")]
        if ledger == "full":
            (d / "ledger.jsonl").write_text("\n".join(json.dumps(e) for e in entries) + "\n", encoding="utf-8")
    return d


def verify(d, *args, fmt="json"):
    r = sh([sys.executable, "apply/verify.py", "--decisions", str(d / "decisions.md"), "--format", fmt, *args],
           env={k: v for k, v in os.environ.items() if not k.startswith("HIVIZ_") and k != "NO_COLOR"}
               | {"PYTHONIOENCODING": "utf-8"})   # the pretty check asserts unicode glyphs: a cp1252 pipe (windows CI) folds them by design
    if fmt != "json":
        return r.returncode, r.stdout
    try:
        doc = json.loads(r.stdout)
    except ValueError:
        return r.returncode, {"rows": [], "summary": {}, "verdict": "?", "_err": r.stderr[-200:]}
    doc["by"] = {x["id"]: x for x in doc["rows"]}
    return r.returncode, doc


def status(doc, rid):
    return doc["by"].get(rid, {}).get("status")


def file_fails(doc):
    return [x for x in doc["rows"] if x["id"].startswith(("file:", "stray:")) and x["status"] == "FAIL"]


def tree_hash(d):
    return {str(p): hashlib.md5(p.read_bytes()).hexdigest() for p in sorted(d.rglob("*")) if p.is_file()}


def verify_checks() -> None:
    sys.path.insert(0, str(REPO / "tests"))
    # 1. the exact apply: only REVIEW (a rewrite and a free-text condition), blank leftovers tolerated, side B untouched
    d = build("exact")
    rc, doc = verify(d)
    ok = (rc == 0 and doc["verdict"] == "REVIEW" and doc["summary"]["FAIL"] == 0
          and [status(doc, r) for r in ("D1", "D2", "D4", "D5", "D6", "D7", "K1")] == ["OK"] * 7
          and status(doc, "D3") == "REVIEW" and status(doc, "C1") == "REVIEW" and status(doc, "ledger") == "OK")
    check("verify: the exact apply passes — deletions OK, rewrite and condition left to a human, blank leftovers tolerated, ledger complete",
          ok, f"rc={rc} {doc['summary']} {doc.get('_err', '')}")

    # 2. rows that must stay: decided no / empty / kept-safe, edited anyway (the model-edited-a-no-row failure)
    bad = []
    for label, rid, changes in (("no", "D4", {6: None}), ("empty", "D5", {8: "- Be brief."}), ("kept-safe", "K1", {9: None})):
        d = build(f"hold-{label}", edit(OLD, {**PERFECT, **changes}))
        rc, doc = verify(d)
        r = doc["by"].get(rid, {})
        if not (rc == 1 and r.get("status") == "FAIL" and r.get("action") == "restore" and r.get("old")
                and (label != "kept-safe" or "invariant" in r.get("detail", ""))):
            bad.append(f"{label}: rc={rc} {r.get('status')}")
    check("verify: a row decided no / left empty / kept-safe that was changed → FAIL, action restore (kept-safe says invariant)",
          not bad, "; ".join(bad))

    # 3. nothing else may change
    cases = {
        "bystander removed": (edit(OLD, {**PERFECT, 10: None}), 1, True),
        "bystander edited": (edit(OLD, {**PERFECT, 10: "- Answer in Russian."}), 1, True),
        "text appended": (edit(OLD, PERFECT) + ["- Always celebrate."], 1, True),
        "delete replaced by text": (edit(OLD, {**PERFECT, 12: "- Be nice."}), 1, True),
        "only blank lines moved": (edit(OLD, {**PERFECT, 3: None, 2: ["", ""]}), 0, False),
        "rewrite grew to two lines": (edit(OLD, {**PERFECT, 5: ["- Prefer branches.", "- Use stash only to rescue noise."]}), 0, False),
    }
    bad = []
    for label, (new, want_rc, want_file_fail) in cases.items():
        d = build("else-" + label.replace(" ", "-"), new)
        rc, doc = verify(d)
        if rc != want_rc or bool(file_fails(doc)) != want_file_fail:
            bad.append(f"{label}: rc={rc} file_fails={len(file_fails(doc))}")
    d = build("else-mixed-hunk", edit(OLD, {**PERFECT, 3: "- Be nice."}))   # next to the rewrite on line 5: one hunk, cannot be told apart
    rc, doc = verify(d)
    mixed = rc == 0 and not file_fails(doc) and any(x["id"] == "file:AGENTS.md" and x["status"] == "REVIEW" for x in doc["rows"])
    if not mixed:
        bad.append("deletion next to a rewrite must be shown to a human")
    check("verify: no other line removed or changed, no added line without a decision (blank lines and a bigger rewrite are fine; "
          "a deletion's replacement next to a rewrite is shown for review)", not bad, "; ".join(bad))

    # 4. backups
    d = build("no-backup", backup=False)
    rc, doc = verify(d)
    nb = rc == 1 and status(doc, "D1") == "FAIL" and doc["by"]["D1"]["action"] == "report" and any(
        x["id"] == "file:AGENTS.md" for x in file_fails(doc))
    d = build("stray-backup", extra={"OTHER.md": "edited\n", "OTHER.md.bak-20261007": "original\n"})
    rc_s, doc_s = verify(d)
    stray = rc_s == 1 and any(x["id"].startswith("stray:OTHER.md.bak") for x in file_fails(doc_s))
    d = build("stale-backup", extra={"OTHER.md": "x\n", "OTHER.md.bak-20260101": "y\n"})
    future = time.time() + 120
    os.utime(d / "decisions.md", (future, future))   # the decisions are newer than every backup → they all belong to an earlier apply
    rc_t, doc_t = verify(d)
    stale = not any(x["id"].startswith("stray:") for x in doc_t["rows"]) and status(doc_t, "D1") == "FAIL" \
        and doc_t["by"]["D1"]["action"] == "report"
    d = build("crlf-bom", edit(OLD, {}), crlf_backup=True)
    rc_c, doc_c = verify(d, "--no-ledger")
    crlf = rc_c == 1 and status(doc_c, "D4") == "OK" and status(doc_c, "K1") == "OK" and not file_fails(doc_c)
    check("verify: an edit without a backup FAILs; a backup for an undecided file FAILs; an older apply's backup is ignored; "
          "CRLF + BOM backup of an unchanged file is neutral", nb and stray and stale and crlf,
          f"no-backup={nb} stray={stray} stale={stale} crlf-bom={crlf}")

    # 5. approved but not applied; rows that cannot be found
    d = build("not-applied", edit(OLD, {}))
    rc, doc = verify(d)
    na = rc == 1 and all(status(doc, r) == "FAIL" and doc["by"][r]["action"] == "apply" for r in ("D1", "D2", "D3", "D6", "D7")) \
        and status(doc, "C1") == "REVIEW" and "may not have applied" in doc["by"]["C1"]["detail"]
    rows = default_rows()
    rows[5] = row("D5", "call", 8, "A sentence that is not in the file at all", "delete", "")
    d = build("unanchored", rows=rows)
    rc_u, doc_u = verify(d)
    rc_strict, _ = verify(d, "--strict")
    rows = default_rows()
    rows[1] = row("D1", "call", 3, "A sentence that is not in the file at all", "delete", "yes")   # its deletion can no longer be proven approved
    d = build("unanchored-edit", rows=rows)
    rc_e, doc_e = verify(d)
    un = (rc_u == 0 and status(doc_u, "D5") == "UNVERIFIABLE" and rc_strict == 1
          and rc_e == 1 and status(doc_e, "D1") == "UNVERIFIABLE" and bool(file_fails(doc_e)))
    rows = default_rows()
    rows[1] = row("D1", "call", 5, "Write clean code and follow best practices.", "delete", "yes")   # stated line is wrong: 3 → 5
    d = build("off-by-two", rows=rows)
    rc_o, doc_o = verify(d)
    off = status(doc_o, "D1") == "OK" and "found at 3" in doc_o["by"]["D1"]["detail"]
    check("verify: approved-not-applied → FAIL (apply); an unlocatable quote → UNVERIFIABLE (exit 1 only with --strict), and an edit "
          "under it can no longer be proven approved → FAIL; a wrong line number is corrected by the quote", na and un and off, f"not-applied={na} unanchored={un} off-by-two={off}")

    # 6. ledger
    msgs = []
    d = build("ledger-missing-entry")
    lines = (d / "ledger.jsonl").read_text(encoding="utf-8").splitlines()
    (d / "ledger.jsonl").write_text("\n".join(x for x in lines if '"D6"' not in x) + "\n", encoding="utf-8")
    rc, doc = verify(d)
    if not (status(doc, "ledger") == "FAIL" and "D6" in doc["by"]["ledger"]["detail"] and rc == 1):
        msgs.append("missing entry")
    d = build("ledger-malformed")
    with open(d / "ledger.jsonl", "a", encoding="utf-8") as fh:
        fh.write('{"file": "x"}\nnot json\n')
    rc, doc = verify(d)
    if not (status(doc, "ledger") == "FAIL" and "lacks" in doc["by"]["ledger"]["detail"]):
        msgs.append("malformed")
    d = build("ledger-absent", ledger=None)
    rc, doc = verify(d)
    rc2, doc2 = verify(d, "--no-ledger")
    if not (status(doc, "ledger") == "FAIL" and "ledger" not in doc2["by"] and rc2 == 0):
        msgs.append("absent / --no-ledger")
    check("verify: the ledger needs one entry per approved decision — a missing entry, a malformed line and a missing file FAIL; --no-ledger skips",
          not msgs, "; ".join(msgs))

    # 7. outputs, exit codes, read-only
    d = build("outputs")
    before = tree_hash(d)
    rc_m, md = verify(d, fmt="md")
    rc_p, pretty = verify(d, "--out", str(d / "result.json"), fmt="pretty")
    after = tree_hash(d)
    wrote = (d / "result.json").exists()
    after.pop(str(d / "result.json"), None)
    rc_none, _ = verify(OUT / "verify_fx" / "does-not-exist")
    empty = OUT / "verify_fx" / "empty-decisions"
    empty.mkdir(parents=True, exist_ok=True)
    (empty / "decisions.md").write_text("# nothing here\n", encoding="utf-8")
    rc_empty, _ = verify(empty)
    ok = (rc_m == 0 and md.startswith("# apply verify — REVIEW") and "```diff" in md and "| status | row |" in md
          and rc_p == 0 and "╭" in pretty and "read these edits" in pretty and wrote
          and before == after and rc_none == 2 and rc_empty == 2)
    check("verify: md / pretty / json outputs, exit 2 on a missing or empty decisions file, audited files never touched",
          ok, f"md={rc_m} pretty={rc_p} none={rc_none} empty={rc_empty} read-only={before == after}")
