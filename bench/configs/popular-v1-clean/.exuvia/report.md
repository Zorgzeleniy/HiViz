# Exuvia audit — popular-v1-clean corpus

Audit scope (explicit user request): `corpus/CLAUDE.md`, `corpus/viral-skills/caveman/SKILL.md`, `corpus/viral-skills/no-ai-slop/SKILL.md`. Third-party packs (`anthropic-skills/`, `superpowers-skills/`) inventoried for weight only, per owner decision. Phase 1 step 7 (MCP footprint) skipped: no MCP servers in this corpus.

```
🔴 1 act now · 🟡 4 your call · ⚪ 8 fine · corpus 2,034 KB → shed potential −0.2%
```

Top-3 actions:
- claude-env · CLAUDE.md repo map — 8/8 referenced paths dead in this corpus · 2.1 KB of the 3.5 KB file steers every task at an absent repo (−60% of the file)
- slop-principles · ~10 of 17 editorial bullets restate trained behavior · −2.1 KB, largest single shed; all candidates together = −24% of the 21.2 KB audited surface
- caveman-dup + caveman-examples · intensity table and 2nd example set repeat the Rules section · −1.0 KB internal repetition in a 7.2 KB skill

Shed potential note: −0.2% is against the full 2,034 KB corpus because 98.9% of it is owner-kept third-party packs. Against the 21.2 KB audited surface, the same candidates shed −24%.

## 🔴 Act now

| id | line | why | → |
|---|---|---|---|
| claude-env | L3-53 cluster: `L3-5, L9-25, L29-34, L44-45, L49-53` | relic: file describes a tutorial-EPUB repo; all 8 repo-relative references dead here (`scripts/`, `STYLE_GUIDE.md`, `.claude/CLAUDE.md`, `openspec/`, `02-memory/`, root `README.md`, `LEARNING-ROADMAP.md`, CI workflow) — commands can't run, architecture map points nowhere | verify |

2,132 B. Either mount the referenced repo into the corpus or strip to the portable subset (Hard rules L37-43, Workflow L47-62 survive). Keeping it as-is means every bench task in this corpus is prefaced with an environment description that contradicts the actual working tree — direct conflict with evidence.

## 🟡 Your call

| id | line | why | → |
|---|---|---|---|
| slop-principles | L26-42 `## Editing principles` (17 bullets) | trained-dup: ~10 bullets restate standard editorial craft (active voice, concrete beats abstract, verbs do work, show don't tell, cut qualifiers); distinctive ones are L26/27/36 (voice, minimum edit, portability test) | delete |
| slop-evalmd | L95 `check the edited draft against \`eval.md\` yourself` | relic: `eval.md` absent from the skill dir — the self-check loop (L95-96) references a file the model cannot read | rewrite |
| caveman-dup | L45-46 intensity rows `full`/`ultra` | trained-dup: rows restate L19/L23 rules near-verbatim (abbreviations, arrows, log dumps); table should differ levels, not repeat the base spec | merge |
| caveman-examples | L59-64 example "Explain database connection pooling" | trained-dup: second full example set; register per level already pinned by the React set L51-57 (wenyan variants are the least guessable — keep those, cut the redundant English second set) | delete |

Byte ledger: slop-principles ~2,100 B (of 3,456 B section) · caveman-dup 550 B · caveman-examples 416 B · slop-evalmd ~0 B (rewrite in place).

## ⚪ Kept safe

| id | line | why | → |
|---|---|---|---|
| claude-safety | L37-38 `MUST NOT commit or push… / no Co-Authored-By` | safety invariant — always category 1 | keep |
| claude-doc-hygiene | L40-42 relative links, fence languages, stable URLs | portable good practice; justification (pre-commit) is dead but the rule holds anywhere | keep |
| claude-tokens | L47-62 workflow prefs + token efficiency | already-bounded efficiency rules; L57 carries its own condition ("unless the outcome was uncertain") | keep |
| caveman-guards | L21-23 `Never drop not/never/no/only/except`, `Never ADD word` | correctness guards of the compression mode — prevent meaning-flip and output growth | keep |
| caveman-register | L25, L29, L31 STE100 mix, language preservation, article-less languages | invariant skill spec the model cannot infer | keep |
| caveman-clarity | L68-86 `## Auto-Clarity` | safety carve-outs: security warnings, irreversible actions, ambiguity — caveman drops there | keep |
| slop-contract | L10-24 two jobs, minimum effective edit, ask-for-draft flow | core differentiating spec of the skill | keep |
| slop-catalog | L44-88 `## Words to cut` + `## Patterns to cut` | the house list — specific banned vocabulary and pattern catalog is the skill's actual payload | keep |

## Appendix

### Phase 0 — Inventory

| surface | files | bytes | share of corpus | role |
|---|---|---|---|---|
| anthropic-skills/ | 110 | 1,617,104 | 77.6% | weight only (owner-kept) |
| superpowers-skills/ | 75 | 444,490 | 21.3% | weight only (owner-kept) |
| viral-skills/ (audited) | 2 | 18,100 | 0.9% | line-audited |
| CLAUDE.md (audited) | 1 | 3,577 | 0.2% | line-audited |
| **total** | **188** | **2,083,271 (2,034 KB)** | 100% | md+json subset: 620,020 B |

Audited surface: 3 files, 21,677 B = 1.0% of corpus.

### Phase 1 — Deterministic pre-pass

**Absolute census** (`always|never|никогда|всегда|обязательно|strictly|extremely|thoroughly|carefully`, case-insensitive):

- CLAUDE.md — 3 hits: L39 `Always activate .venv`, L56 `Never re-read files`, L57 `Never re-run commands`
- viral-skills/caveman/SKILL.md — 8 hits: L19, L21, L23, L25, L27, L29, L46, L66 (guards and register rules; individually assessed in Phase 2, kept)
- viral-skills/no-ai-slop/SKILL.md — 2 hits: L32 `Never let inanimate things…`, L37 `Always show, don't tell` (L37 folded into slop-principles)

**Work-ordering census**: 0 hits in all three files (no approach tournaments, no double/triple-check commissions).

**Cross-file duplicates** (normalized `-|*|N.` lines): none shared between any pair of the three audited files.

**Dead references**:
- CLAUDE.md → `.claude/CLAUDE.md`, `STYLE_GUIDE.md`, `LEARNING-ROADMAP.md`, `openspec/`, `scripts/`, `02-memory/`, root `README.md`, `.github/workflows/test.yml` (via CI mention) — all absent from the corpus (8/8 dead) → claude-env
- no-ai-slop → `eval.md` — absent from `viral-skills/no-ai-slop/` → slop-evalmd
- caveman → no external references

**Dated snapshots / version pins**: none in the three audited files.

**Few-shot blocks > 10 lines**: CLAUDE.md L9 block (13 lines) is real runnable commands, not fabricated output — not flagged. Caveman examples (L51-64) are short inline sets, below threshold; assessed as trained-dup on merit.

**MCP footprint**: skipped per instruction (no MCP servers in corpus).

### Method notes

- Severity inherited: 🔴 = conflict with direct evidence (instruction vs. actual environment); 🟡 = delete/rewrite candidate; ⚪ = keep.
- `corpus 2,034 KB` includes owner-kept third-party packs; shed potential is computed against it for comparability with the bench's context-weight metric. [INFERENCE] bench tasks run with `corpus/` as the working tree — the basis for calling CLAUDE.md's references dead rather than merely unverified.
