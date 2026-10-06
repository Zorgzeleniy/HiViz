# HiViz prompt-debt audit — fixture profile

🔴 2 act now · 🟡 9 your call · ⚪ 3 fine · corpus 18.9 KB → shed −11.3%

- **C1 · resolve the staging-gateway contradiction** — `10.0.0.42 (legacy)` vs `10.0.0.99`: two deploy targets
- **D16+D13 · delete the two rationale tables** — 1,437 bytes, 7.4% of the corpus, restatement of earlier rules
- **D20 · drop the fabricated few-shot block** — 312 bytes with an invented hash

Scope: 4 surfaces. Corpus 19,377 B.

## 🔴 Act now

| id | where | line | why | B | → verb |
|---|---|---|---|---|---|
| C1 | /work/profile/AGENTS.md:13 ⇄ /work/profile/skills/smelly-skill/SKILL.md:9 | `the staging gateway answers at 10.0.0.42 (legacy)` | conflict: B says «10.0.0.99 … supersedes older notes» — two deploy targets | 0 | verify |
| C2 | /work/profile/AGENTS.md:7 | `Final stack state (2026-01-15): toolchain v2.1 pinned;` | relic: fact: dated snapshot, 264 d old; smelly-skill:9 claims a later 2026-03 migration | 96 | delete |

## 🟡 Your call

| id | where | line | why | B | → verb |
|---|---|---|---|---|---|
| D01 | /work/profile/AGENTS.md:3 | `- Write clean, readable code and follow best practices.` | trained-dup: [INFERENCE] the model does this unprompted | 58 | delete |
| D02 | /work/profile/AGENTS.md:4 | `- Be careful and thorough when editing files.` | trained-dup: [INFERENCE] no actionable threshold; costs tokens | 46 | delete |
| D04 | /work/profile/AGENTS.md:8 | `- Always handle errors explicitly — never swallow exceptions.` | trained-dup: [INFERENCE] baseline behaviour | 62 | delete |
| D05 | /work/profile/AGENTS.md:19 | `- Always run the full test suite before every commit.` | 90%-rule: full suite on a one-line docs change; run the relevant tests | 54 | rewrite |
| D06 | /work/profile/AGENTS.md:20 | `- Always create a new branch before starting any work.` | 90%-rule: invalid for hotfixes and read-only tasks | 55 | rewrite |
| D13 | /work/profile/skills/superpowers-systematic-debugging/SKILL.md:24-42 | `Use for ANY technical issue: … Don't skip when:` | trained-dup: fact: 573 B of persuasion to obey a method the model already follows | 573 | delete |
| D16 | /work/profile/skills/superpowers-systematic-debugging/SKILL.md:246-255 | `\| Excuse \| Reality \| rationale table` | trained-dup: fact: 864 B (4.5% of corpus) restating l.10 and l.24 | 864 | delete |
| D19 | /work/profile/skills/smelly-skill/SKILL.md:5 | `- Always include a summary table in every response, even one-line answers.` | 90%-rule: table on a one-line answer | 71 | delete |
| D20 | /work/profile/skills/smelly-skill/SKILL.md:16-21 | ``` fabricated `blocked 47 threats in 3.2s` block | few-shot: fact: fabricated output with an invented hash | 312 | delete |

## ⚪ Kept safe

| id | where | line | why | B | → verb |
|---|---|---|---|---|---|
| K04 | /work/profile/AGENTS.md:11 | `NEVER use the `git stash` command.` | invariant: repo policy the model would otherwise violate | 0 | keep |
| K12 | /work/profile/RULES.md:1 | `NEVER print secrets or API keys verbatim — redact them.` | invariant: safety rule, never deletable | 0 | keep |
| K13 | /work/profile/RULES.md:2 | `NEVER commit, push, or delete anything without an explicit request` | invariant: commit/delete gate, never deletable | 0 | keep |

## Appendix

### Phase 0 — Inventory

| # | surface | bytes | share |
|---|---|---:|---:|
| 1 | `AGENTS.md` | 1,787 | 9.2% |
| 2 | `RULES.md` | 190 | 1.0% |
