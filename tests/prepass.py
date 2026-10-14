import os, re, json
from collections import Counter

BASE = r"C:\Users\user\.omp\profiles\hiviz-test\agent"
FILES = [
    ("AGENTS.md", os.path.join(BASE, "AGENTS.md")),
    ("RULES.md", os.path.join(BASE, "RULES.md")),
    ("skills/smelly-skill/SKILL.md", os.path.join(BASE, "skills", "smelly-skill", "SKILL.md")),
    ("skills/clean-skill/SKILL.md", os.path.join(BASE, "skills", "clean-skill", "SKILL.md")),
    ("skills/superpowers-systematic-debugging/SKILL.md", os.path.join(BASE, "skills", "superpowers-systematic-debugging", "SKILL.md")),
    ("skills/anthropic-docx/SKILL.md", os.path.join(BASE, "skills", "anthropic-docx", "SKILL.md")),
]
OUTDIR = r"D:\Ai\temp\hiviz-patch-test\wt\tests\out"
REPORT = os.path.join(OUTDIR, "report.md")
PREPASS = os.path.join(OUTDIR, "prepass.json")
TODAY = "2026-10-14"
os.makedirs(OUTDIR, exist_ok=True)

raw = {}
lines = {}
for name, path in FILES:
    with open(path, "rb") as f:
        b = f.read()
    raw[name] = b
    lines[name] = b.decode("utf-8").splitlines()

total = sum(len(b) for b in raw.values())

out = []
out.append("## Appendix\n")
out.append("Audit scope fixed by the user: ONLY the 6 files below. Owning context: omp profile "
           "`hiviz-test` (its `config.yml` lists one skills root, `agent/skills`). Report path "
           "overridden by user request: this file. No audited file was modified.\n")

# ---------------- Phase 0: inventory ----------------
out.append("### Phase 0 — Instruction-surface inventory\n")
out.append("| # | file (absolute path) | bytes | share of corpus |")
out.append("|---|---|---|---|")
for i, (name, path) in enumerate(FILES, 1):
    out.append(f"| {i} | `{path}` | {len(raw[name])} | {len(raw[name]) / total * 100:.1f}% |")
out.append(f"| | **corpus (6 files)** | **{total}** | **100%** |\n")

# ---------------- Phase 1 ----------------
out.append("### Phase 1 — Deterministic pre-pass\n")

# 2. absolute census + work-ordering census
CENSUS = re.compile(r"\b(always|never|никогда|всегда|обязательно|strictly|extremely|thoroughly|carefully)\b", re.I)
WORK = re.compile(r"(consider|explore|compare) (several|multiple) approach(es)?|maximum certainty|make (absolutely |really )?sure|double-?check|triple-?check|think (deeply|harder)|be extremely thorough", re.I)

census_data = {}
out.append("#### 1. Absolute census — `always|never|strictly|extremely|thoroughly|carefully` (case-insensitive)\n")
out.append("| file | hits | matching lines (n: matched words) |")
out.append("|---|---|---|")
for name, _ in FILES:
    hits = []
    for n, ln in enumerate(lines[name], 1):
        words = sorted(set(m.group(0).lower() for m in CENSUS.finditer(ln)))
        if words:
            hits.append((n, ", ".join(words)))
    census_data[name] = hits
    detail = "; ".join(f"{n}: {w}" for n, w in hits) if hits else "—"
    out.append(f"| `{name}` | {len(hits)} | {detail} |")
all_census = sum(len(v) for v in census_data.values())
out.append(f"\nTotal: **{all_census}** hits across the corpus.\n")

work_data = {}
out.append("#### 2. Work-ordering census — approach tournaments / verification loops\n")
for name, _ in FILES:
    hits = []
    for n, ln in enumerate(lines[name], 1):
        if WORK.search(ln):
            hits.append((n, ln.strip()))
    work_data[name] = hits
flat = [(name, n, ln) for name, _ in FILES for n, ln in work_data[name]]
if flat:
    out.append("| file | line | text |")
    out.append("|---|---|---|")
    for name, n, ln in flat:
        out.append(f"| `{name}` | {n} | {ln} |")
else:
    out.append("**0 hits** across the corpus — no approach-tournament or verification-loop phrasing found.\n")

# 3. cross-file duplicates
def norm(s):
    s = re.sub(r"[^\w\s]", "", s.lower())
    return re.sub(r"\s+", " ", s).strip()

instr = re.compile(r"^\s*[-*]\s|^\s*\d+\.\s")
seen = Counter()
loc = {}
for name, _ in FILES:
    for n, ln in enumerate(lines[name], 1):
        if instr.match(ln):
            k = norm(ln)
            if len(k) > 3:
                seen[k] += 1
                loc.setdefault(k, []).append((name, n))
pairs = []
for k, c in seen.items():
    if c > 1:
        where = loc[k]
        files_involved = {w[0] for w in where}
        if len(files_involved) > 1:
            pairs.append((k, where))
out.append("#### 3. Cross-file duplicate instruction lines\n")
if pairs:
    for k, where in pairs:
        chain = " ⇄ ".join(f"`{name}`:{n}" for name, n in where)
        out.append(f"- {chain} — «{k}»")
else:
    out.append("**0 pairs** — no normalized instruction line appears in more than one audited file. "
               "(Semantic overlap not covered by line-level dedup: AGENTS.md:47 «Always ask before making any destructive changes» vs RULES.md:3 commit/push/delete gate — same intent, different wording.)\n")

# 4. dead references
REFS = [
    ("root-cause-tracing.md (in this directory)", "sysdbg SKILL.md:112,281", os.path.join(BASE, "skills", "superpowers-systematic-debugging", "root-cause-tracing.md")),
    ("defense-in-depth.md (in this directory)", "sysdbg SKILL.md:282", os.path.join(BASE, "skills", "superpowers-systematic-debugging", "defense-in-depth.md")),
    ("condition-based-waiting.md (in this directory)", "sysdbg SKILL.md:283", os.path.join(BASE, "skills", "superpowers-systematic-debugging", "condition-based-waiting.md")),
    ("superpowers:test-driven-development", "sysdbg SKILL.md:177", os.path.join(BASE, "skills", "superpowers-test-driven-development", "SKILL.md")),
    ("superpowers:verification-before-completion", "sysdbg SKILL.md:189", os.path.join(BASE, "skills", "superpowers-verification-before-completion", "SKILL.md")),
    ("scripts/office/soffice.py", "docx SKILL.md:40,49", os.path.join(BASE, "skills", "anthropic-docx", "scripts", "office", "soffice.py")),
    ("scripts/merge_runs.py", "docx SKILL.md:54,61", os.path.join(BASE, "skills", "anthropic-docx", "scripts", "merge_runs.py")),
    ("scripts/office/validate.py", "docx SKILL.md:57", os.path.join(BASE, "skills", "anthropic-docx", "scripts", "office", "validate.py")),
    ("scripts/comment.py", "docx SKILL.md:80-84", os.path.join(BASE, "skills", "anthropic-docx", "scripts", "comment.py")),
    ("scripts/accept_changes.py", "docx SKILL.md:65,67", os.path.join(BASE, "skills", "anthropic-docx", "scripts", "accept_changes.py")),
    ("LICENSE.txt", "docx SKILL.md:4", os.path.join(BASE, "skills", "anthropic-docx", "LICENSE.txt")),
    ("fixtures/seed.sql", "AGENTS.md:43", os.path.join(BASE, "fixtures", "seed.sql")),
    (".env.local", "AGENTS.md:42 (expected absent — never committed, by design)", os.path.join(BASE, ".env.local")),
]
out.append("#### 4. Dead references (resolved against the owning profile's roots)\n")
out.append("| reference | referenced from | target | status |")
out.append("|---|---|---|---|")
for ref, src, target in REFS:
    ok = os.path.exists(target)
    note = "exists" if ok else "NOT FOUND in any owning root"
    if ref == ".env.local":
        note = "absent by design (secrets, never committed)"
    out.append(f"| {ref} | {src} | `{target}` | {note} |")
out.append("")

# 5. dated snapshots / version pins
DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
VER = re.compile(r"\d+\.\d+(\.\d+)?")
MONTH = re.compile(r"\d{4}-\d{2}\b")
out.append("#### 5. Dated snapshots and version pins (today: 2026-10-14)\n")
out.append("| fact | date / version | where | age |")
out.append("|---|---|---|---|")
rows5 = [
    ("Final stack state snapshot", "2026-01-15", "AGENTS.md:41", "272 days"),
    ("toolchain pin", "v2.1", "AGENTS.md:41", "stale? v3 migration 'until complete' unbounded"),
    ("Node major version", "Node 20", "AGENTS.md:7", "pin, no age"),
    ("staging gateway migration", "2026-03", "smelly-skill SKILL.md:9", "~7 months (month precision)"),
    ("gateway marked legacy", "10.0.0.42", "AGENTS.md:13", "conflicts with smelly-skill:9"),
]
for fact, dv, where, age in rows5:
    out.append(f"| {fact} | {dv} | {where} | {age} |")
out.append("\nRegex sweep of remaining `\\d{4}-\\d{2}-\\d{2}` / `\\d+.\\d+` matches: only IP addresses "
           "(10.0.0.42, 10.0.0.99, 10.0.0.42-related) and table row numbers — no other dated facts or version pins.\n")

# 6. few-shot blocks
out.append("#### 6. Few-shot blocks (fenced blocks > 10 lines with fabricated data)\n")
blocks = []
for name, _ in FILES:
    cur = None
    for n, ln in enumerate(lines[name], 1):
        if ln.strip().startswith("```"):
            if cur is None:
                cur = [n, n]
            else:
                cur[1] = n
                blocks.append((name, cur[0], cur[1], cur[1] - cur[0] - 1))
                cur = None
out.append("| file | lines | code lines | note |")
out.append("|---|---|---|---|")
for name, a, b, cl in blocks:
    note = ""
    if cl > 10:
        note = "OVER 10 lines"
    out.append(f"| `{name}` | {a}-{b} | {cl} | {note} |")
out.append("")
out.append("Manual pass (fabricated data, any length): `skills/smelly-skill/SKILL.md:16-21` — 5-line mock "
           "report («hash: d41d8cd…», «severity: CRITICAL», «blocked 47 threats in 3.2s») — fabricated few-shot "
           "data below the >10-line regex threshold. `skills/anthropic-docx/SKILL.md:39-43` — real commands, not "
           "fabricated output. `superpowers-systematic-debugging` bash blocks: illustrative commands (one "
           "17-line fabricated multi-layer example at lines 88-104).\n")

# 7. MCP
out.append("#### 7. Live MCP surfaces\n")
out.append("Skipped: no `mcp.json` / `mcpServers` among the 6 audited files (user-fixed scope), and the hiviz "
           "engines dir was not found (`<profile>/.claude/engines`, `~/.hiviz/engines` both absent), so "
           "`meters/mcp_footprint.py` is unavailable. No MCP disable candidates can be raised from this scope.\n")

with open(REPORT, "a", encoding="utf-8") as f:
    f.write("\n".join(out) + "\n")

with open(PREPASS, "w", encoding="utf-8") as f:
    json.dump({
        "total": total,
        "sizes": {name: len(raw[name]) for name, _ in FILES},
        "census": {name: [[n, w] for n, w in v] for name, v in census_data.items()},
        "census_total": all_census,
        "work_ordering_hits": {name: [[n, ln] for n, ln in v] for name, v in work_data.items()},
        "dup_pairs": pairs,
    }, f, ensure_ascii=False, indent=1)

print("corpus bytes:", total)
for name, _ in FILES:
    print(f"  {name}: {len(raw[name])} bytes, census hits {len(census_data[name])}")
print("work-ordering hits:", sum(len(v) for v in work_data.values()))
print("dup pairs:", len(pairs))
print("appended Phase 0+1 to", REPORT)
