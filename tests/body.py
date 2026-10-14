import os, json

BASE = r"C:\Users\user\.omp\profiles\hiviz-test\agent"
P = {
    "AGENTS": os.path.join(BASE, "AGENTS.md"),
    "RULES": os.path.join(BASE, "RULES.md"),
    "SMELLY": os.path.join(BASE, "skills", "smelly-skill", "SKILL.md"),
    "CLEAN": os.path.join(BASE, "skills", "clean-skill", "SKILL.md"),
    "SYSDBG": os.path.join(BASE, "skills", "superpowers-systematic-debugging", "SKILL.md"),
    "DOCX": os.path.join(BASE, "skills", "anthropic-docx", "SKILL.md"),
}
OUTDIR = r"D:\Ai\temp\hiviz-patch-test\wt\tests\out"
REPORT = os.path.join(OUTDIR, "report.md")
DECISIONS = os.path.join(OUTDIR, "decisions.md")
STALE = os.path.join(OUTDIR, "report.pre-existing-20261013.md")

raw = {k: open(v, "rb").read() for k, v in P.items()}
text = {k: v.decode("utf-8") for k, v in raw.items()}
binlines = {k: v.splitlines(keepends=True) for k, v in raw.items()}
TOTAL = sum(len(v) for v in raw.values())

def span_b(fkey, a, b):  # bytes of lines a..b inclusive (with line terminators)
    return sum(len(x) for x in binlines[fkey][a - 1:b])

def sub_b(fkey, needle):
    assert needle in text[fkey], f"quote not verbatim in {fkey}: {needle!r}"
    return len(needle.encode("utf-8"))

# ---- row specs: (filekey, line-or-(a,b), quote, why, verb, bcalc) ----
# bcalc: ("span", a, b) -> span_b; ("sub", needle) -> sub_b; 0 -> 0
ACT = [
    dict(f="AGENTS", where=lambda: f"{P['AGENTS']}:13 ⇄ {P['SMELLY']}:9",
         quote="the staging gateway answers at 10.0.0.42 (legacy)",
         why="conflict: B: «10.0.0.99 (migrated 2026-03; supersedes older notes)» — B newer",
         verb="rewrite", b=("sub", "AGENTS", "10.0.0.42 (legacy)"), top=1),
]
YOUR = [
    dict(f="SMELLY", lines=(14, 21), quote="blocked 47 threats in 3.2s",
         why="few-shot: fact: 5-line mock report with fabricated hash/threats/timing",
         verb="delete", b=("span", "SMELLY", 14, 21), fewshot=1),
    dict(f="SYSDBG", lines=(244, 255), quote="Common Rationalizations",
         why="trained-dup: fact: same excuses restated as Red Flags (L214-229); merge lists",
         verb="merge", b=("span", "SYSDBG", 244, 255)),
    dict(f="SYSDBG", lines=(87, 104), quote="Example (multi-layer system):",
         why="few-shot: [INFERENCE] 17-line fabricated example; pseudocode above suffices",
         verb="delete", b=("span", "SYSDBG", 87, 104)),
    dict(f="SYSDBG", lines=(14, 20), quote="NO FIXES WITHOUT ROOT CAUSE INVESTIGATION FIRST",
         why="trained-dup: fact: duplicates the Overview principle (L10) in code-block form",
         verb="merge", b=("span", "SYSDBG", 14, 20)),
    dict(f="SYSDBG", lines=(275, 275), quote='95% of "no root cause" cases are incomplete investigation.',
         why="few-shot: [INFERENCE] fabricated 95% statistic; unverifiable, adds no action",
         verb="delete", b=("span", "SYSDBG", 275, 275)),
    dict(f="SYSDBG", lines=(231, 231), quote="Question the architecture (see Phase 4.5)",
         why="dead-ref: fact: no «Phase 4.5» heading exists — target is Phase 4 step 5",
         verb="rewrite", b=("sub", "SYSDBG", "(see Phase 4.5)")),
    dict(f="AGENTS", lines=(49, 49), quote="always ask for clarification rather than guessing",
         why="90%-rule: [INFERENCE] always-ask stalls work; ask when costly to reverse",
         verb="rewrite", b=("span", "AGENTS", 49, 49)),
    dict(f="AGENTS", lines=(36, 36), quote="Always write tests first, then implementation",
         why="90%-rule: [INFERENCE] strict TDD, no exceptions — bound to bug fixes/features",
         verb="rewrite", b=("span", "AGENTS", 36, 36)),
    dict(f="SMELLY", lines=(12, 12), quote="Always include a summary table in every response",
         why="90%-rule: [INFERENCE] table on one-line answers is pure overhead",
         verb="delete", b=("span", "SMELLY", 12, 12)),
    dict(f="AGENTS", lines=(22, 22), quote="Every function must have a JSDoc comment",
         why="90%-rule: [INFERENCE] JSDoc on every fn incl. trivial; scope to public API",
         verb="rewrite", b=("span", "AGENTS", 22, 22)),
    dict(f="AGENTS", lines=(20, 20), quote="Always prefer functional, immutable patterns",
         why="90%-rule: [INFERENCE] always-immutable hurts hot paths; make it conditional",
         verb="rewrite", b=("span", "AGENTS", 20, 20)),
    dict(f="AGENTS", lines=(23, 23), quote="Always handle errors explicitly — never swallow exceptions.",
         why="trained-dup: [INFERENCE] explicit error handling is default behavior",
         verb="delete", b=("span", "AGENTS", 23, 23)),
    dict(f="AGENTS", lines=(19, 19), quote="Be careful and thorough when editing files.",
         why="trained-dup: [INFERENCE] vibe line; no observable behavior to verify",
         verb="delete", b=("span", "AGENTS", 19, 19)),
    dict(f="SYSDBG", lines=(12, 12), quote="Violating the letter of this process",
         why="trained-dup: [INFERENCE] rhetorical guilt line; zero operational content",
         verb="delete", b=("span", "SYSDBG", 12, 12)),
    dict(f="AGENTS", lines=(18, 18), quote="Write clean, readable code and follow best practices.",
         why="trained-dup: [INFERENCE] default model behavior; no checkable criterion",
         verb="delete", b=("span", "AGENTS", 18, 18)),
    dict(f="AGENTS", lines=(48, 48), quote="Be concise and professional in commit messages and PRs.",
         why="trained-dup: [INFERENCE] commit-message style the model does unprompted",
         verb="delete", b=("span", "AGENTS", 48, 48)),
    dict(f="AGENTS", lines=(3, 3), quote="Read fully before making changes.",
         why="trained-dup: [INFERENCE] auto-injected file; the line changes no behavior",
         verb="delete", b=("span", "AGENTS", 3, 3)),
    dict(f="AGENTS", lines=(41, 41), quote="Final stack state (2026-01-15): toolchain v2.1 pinned",
         why="relic: fact: snapshot 2026-01-15, 272 days old; v3 migration state unknown",
         verb="verify", b=0),
    dict(f="AGENTS", lines=(43, 43), quote="seeded from `fixtures/seed.sql`",
         why="dead-ref: fact: path resolves in no owning root (profile has no fixtures/)",
         verb="verify", b=0),
]
KEEP = [
    ("RULES", 1, "Answer in English by default.",
     "invariant: fact: session language default; not derivable elsewhere"),
    ("RULES", 2, "NEVER print secrets or API keys verbatim — redact them.",
     "invariant: safety — secrets redaction gate"),
    ("RULES", 3, "NEVER commit, push, or delete anything",
     "invariant: safety — commit/push/delete gate"),
    ("AGENTS", (7, 7), "staging-deployment tooling for the release pipeline",
     "invariant: fact: stack + deploy target, env-specific"),
    ("AGENTS", (11, 14), "`npm run deploy -- --profile=staging`",
     "invariant: fact: build/test/deploy commands, env-specific"),
    ("AGENTS", 21, "NEVER use `any` in TypeScript files.",
     "invariant: fact: repo lint policy (no any, no inline disables)"),
    ("AGENTS", 27, "NEVER use the `git stash` command.",
     "invariant: fact: team workflow rule (git stash)"),
    ("AGENTS", 28, "Always run the full test suite before every commit.",
     "invariant: safety — pre-commit full-test gate"),
    ("AGENTS", (29, 30), "Always create a new branch before starting any work.",
     "invariant: fact: commit format + branch workflow"),
    ("AGENTS", (34, 35), "Aim for at least 80% coverage on all new code.",
     "invariant: fact: test location + coverage target"),
    ("AGENTS", 37, "NEVER mock what you don't own.",
     "invariant: fact: testing boundary rule"),
    ("AGENTS", 42, "Secrets come from `.env.local` (never committed)",
     "invariant: safety — secrets source, never committed"),
    ("AGENTS", 47, "Always ask before making any destructive changes.",
     "invariant: safety — destructive-change confirmation gate"),
    ("SMELLY", 9, "The staging gateway is 10.0.0.99 (migrated 2026-03",
     "invariant: fact: current gateway IP — newer side of R1"),
    ("CLEAN", 8, "the R: RAM disk does not survive reboots",
     "invariant: fact: artifact path + RAM-disk volatility"),
    ("CLEAN", 9, "injected via env `SIGN_KEY`, never inlined",
     "invariant: safety — signing key via env, never inlined"),
    ("CLEAN", 10, "`make release` requires the MSVC environment",
     "invariant: fact: MSVC env requirement (LNK2019 otherwise)"),
    ("SYSDBG", 10, "ALWAYS find root cause before attempting fixes",
     "invariant: fact: core discipline the skill exists to enforce"),
    ("SYSDBG", (279, 283), "available in this directory",
     "invariant: fact: all 3 referenced technique files exist"),
    ("DOCX", (23, 33), "Page size defaults to A4.",
     "invariant: fact: docx-js footguns; model can't know reliably"),
    ("DOCX", 63, "Inside `<w:del>`, the text element is `<w:delText>`",
     "invariant: fact: tracked-changes OOXML schema rules"),
    ("DOCX", 91, "preinstalled — install only if `require('docx')` fails",
     "invariant: fact: dependency availability in this env"),
]

def calc(b):
    if b == 0:
        return 0
    if b[0] == "span":
        return span_b(b[1], b[2], b[3])
    return sub_b(b[1], b[2])

# verify quotes verbatim
for r in ACT + YOUR:
    assert r["quote"] in text[r["f"]], f"ACT/YOUR quote not verbatim: {r['quote']!r}"
for f, ln, q, w in KEEP:
    assert q in text[f], f"KEEP quote not verbatim: {q!r}"
for r in ACT + YOUR:
    assert len(r["why"]) <= 80, (r["why"], len(r["why"]))
    assert len(r["quote"]) <= 60, (r["quote"], len(r["quote"]))
for f, ln, q, w in KEEP:
    assert len(q) <= 60 and len(w) <= 80, (q, w)

# sort YOUR by bytes desc (most important first), stable
for r in YOUR:
    r["B"] = calc(r["b"])
YOUR_SORTED = sorted(YOUR, key=lambda r: -r["B"])

def where_of(fkey, lines):
    if isinstance(lines, tuple):
        return f"{P[fkey]}:{lines[0]}-{lines[1]}"
    return f"{P[fkey]}:{lines}"

# ids
act_rows = []
for i, r in enumerate(ACT, 1):
    act_rows.append((f"R{i}", r))
your_rows = []
for i, r in enumerate(YOUR_SORTED, 1):
    your_rows.append((f"Y{i}", r))
keep_rows = [(f"K{i}", f, ln, q, w) for i, (f, ln, q, w) in enumerate(KEEP, 1)]

n_act, n_y, n_k = len(act_rows), len(your_rows), len(keep_rows)
shed_b = sum(r["B"] for _, r in your_rows) + (calc(ACT[0]["b"]) if ACT[0]["verb"] in ("delete", "rewrite", "merge", "disable") else 0)
shed_pct = shed_b / TOTAL * 100
kb = TOTAL / 1024

HEADER = "| id | where | line | why | B | → action |"
SEP = "|---|---|---|---|---|---|"

def fmt_row(rid, where, quote, why, B, verb):
    return f"| {rid} | `{where}` | «{quote}» | {why} | {B} | {verb} |"

body = []
body.append("## 🔴 Act now\n")
body.append("Meter-backed disables and conflicts with direct evidence.\n")
body.append(HEADER)
body.append(SEP)
for rid, r in act_rows:
    body.append(fmt_row(rid, r["where"](), r["quote"], r["why"], calc(r["b"]), r["verb"]))
body.append("")
body.append("## 🟡 Your call\n")
body.append("Delete and rewrite candidates, largest byte span first. B = bytes the verb removes or replaces.\n")
body.append(HEADER)
body.append(SEP)
for rid, r in your_rows:
    body.append(fmt_row(rid, where_of(r["f"], r["lines"]), r["quote"], r["why"], r["B"], r["verb"]))
body.append("")
body.append("## ⚪ Kept safe\n")
body.append("Invariants and safety lines — never proposed for deletion, only dedup or relocation.\n")
body.append(HEADER)
body.append(SEP)
for rid, f, ln, q, w in keep_rows:
    body.append(fmt_row(rid, where_of(f, ln), q, w, 0, "keep"))
body.append("")

# top-3
top3 = []
top3.append(("R1", "resolve staging-gateway IP conflict (AGENTS.md:13 ⇄ smelly-skill:9)",
             "2 live values: 10.0.0.42 «legacy» vs 10.0.0.99 «migrated 2026-03»"))
maxrow = max(your_rows, key=lambda x: x[1]["B"])
top3.append((maxrow[0], "merge/delete the largest your-call span", f"{maxrow[1]['B']} B in one section"))
fs = [x for x in your_rows if x[1].get("fewshot")]
if fs:
    top3.append((fs[0][0], "delete fabricated few-shot block in smelly-skill", "5-line mock report, invented hash/threats/timing"))

exec_line = f"🔴 {n_act} act now · 🟡 {n_y} your call · ⚪ {n_k} fine · corpus {kb:.1f} KB → shed −{shed_pct:.1f}%"

# assemble report: preserve existing appendix, replace everything before it
cur = open(REPORT, "r", encoding="utf-8").read()
marker = "## Appendix"
idx = cur.find(marker)
stale_part = cur[:idx]
appendix = cur[idx:]
with open(STALE, "w", encoding="utf-8") as f:
    f.write(stale_part)

head = []
head.append("# HiViz prompt-debt audit — omp profile hiviz-test — 2026-10-14\n")
head.append("_Note: this path held stale fragments from earlier (2026-10-13) audit runs — including an "
            "MCP-disable claim not reproducible in this scope (no mcp.json among the audited files, no hiviz "
            "engines dir) and pre-final numbers. Those fragments were preserved verbatim in "
            "`report.pre-existing-20261013.md` and are superseded by this report._\n")
head.append(exec_line + "\n")
head.append("Top-3 actions:\n")
for rid, what, num in top3:
    head.append(f"- {rid} · {what} · {num}")
head.append("")

with open(REPORT, "w", encoding="utf-8") as f:
    f.write("\n".join(head) + "\n" + "\n".join(body) + "\n" + appendix)

# decisions file: mirrors the body + empty DECISION column
dec = []
dec.append("# Decisions — hiviz prompt-debt audit 2026-10-14\n")
dec.append("Fill DECISION top-down (most important first) by hand, or via the HTML view. "
           "Allowed values: `yes` / `no` / `as-condition` / `keep`.\n")
dec.append(exec_line + "\n")
DHEADER = "| id | where | line | why | B | → action | DECISION |"
DSEP = "|---|---|---|---|---|---|---|"
dec.append("## 🔴 Act now\n")
dec.append(DHEADER)
dec.append(DSEP)
for rid, r in act_rows:
    dec.append(fmt_row(rid, r["where"](), r["quote"], r["why"], calc(r["b"]), r["verb"]).rstrip() + " | |")
dec.append("")
dec.append("## 🟡 Your call\n")
dec.append(DHEADER)
dec.append(DSEP)
for rid, r in your_rows:
    dec.append(fmt_row(rid, where_of(r["f"], r["lines"]), r["quote"], r["why"], r["B"], r["verb"]).rstrip() + " | |")
dec.append("")
dec.append("## ⚪ Kept safe\n")
dec.append(DHEADER)
dec.append(DSEP)
for rid, f, ln, q, w in keep_rows:
    dec.append(fmt_row(rid, where_of(f, ln), q, w, 0, "keep").rstrip() + " | |")
dec.append("")
with open(DECISIONS, "w", encoding="utf-8") as f:
    f.write("\n".join(dec) + "\n")

print(exec_line)
print("shed bytes:", shed_b, "of", TOTAL)
print("rows: act", n_act, "your", n_y, "keep", n_k)
print("top3:", [(r, w) for r, w, _ in top3])
print("wrote:", REPORT, DECISIONS, STALE)
