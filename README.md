<div align="center">

# 🦺 HIVIZ

**Nothing gets cut in the dark.**

**Your agent's instruction files (`CLAUDE.md`, `AGENTS.md`, skills, MCP configs) rot. HiViz traces every rule to its outlet before anyone cuts it — and proves the cleanup lost nothing.**

<a href="https://www.npmjs.com/package/hiviz"><img src="https://img.shields.io/npm/v/hiviz?style=flat-square&color=orange&label=npm" alt="hiviz on npm">

</a>

<a href="https://github.com/Zorgzeleniy/hiviz/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-MIT-green?style=flat-square" alt="MIT">

</a>

<a href="#-quick-start"><img src="https://img.shields.io/badge/works_with-Claude_Code_·_Codex_·_omp_·_Cursor_·_Windsurf_·_OpenCode-blue?style=flat-square" alt="6 harnesses">

</a>

<img src="https://img.shields.io/badge/engines-python_stdlib-teal?style=flat-square" alt="stdlib only">

<img src="https://img.shields.io/badge/LLM_judgment-optional__and_separated-purple?style=flat-square" alt="human decides">

**One command, no account, no extra API key.** `npx hiviz init` [**→ Quick Start**](#-quick-start)

</div>

---

<div align="center">

**[See it](#-see-it) · [Quick Start](#-quick-start) · [What it catches](#-what-it-catches) · [The Numbers](#-the-numbers) · [Commands](#commands) · [What it never does](#-what-it-never-does) · [License](#-license)**

</div>

---

## 🦺 See it

Every agent accumulates instructions that outlived the truth. Here is a real `AGENTS.md` from an open-source repo — one of the 100 popular configs in the first academic AGENTS.md smells corpus ([arXiv 2606.15828](https://arxiv.org/abs/2606.15828)) — before and after hiviz, verbatim excerpts of what the apply actually produced:

**Before** — 19,342 bytes, verbatim excerpts:

```
# AGENTS.md. Julep AI
*Last updated 2025-05-09*

## AI Assistant Workflow: Step-by-Step Methodology

When responding to user instructions, the AI assistant (Claude, Cursor, GPT, etc.)
should follow this process to ensure clarity, correctness, and maintainability:

1. **Consult Relevant Guidance**: When the user gives an instruction, consult the
   relevant instructions from `AGENTS.md` files (both root and directory-specific).
2. **Clarify Ambiguities**: Based on what you could gather, see if there's any need
   for clarifications. If so, ask the user targeted questions before proceeding.
3. **Break Down & Plan**: Break down the task at hand and chalk out a rough plan
   for carrying it out, referencing project conventions and best practices.
6. **Track Progress**: Use a to-do list (internally, or optionally in a `TODOS.md`
   file) to keep track of your progress on multi-step or complex tasks.
9. **User Review**: After completing the task, ask the user to review what you
   have done, and repeat the process as needed.

## 15. Meta: Guidelines for updating AGENTS.md

1. **Decision flowchart**: A simple decision tree for "when to use X vs Y" for key
   architectural choices would guide my recommendations.
3. **Tabular format for key facts**: The tables are very helpful - more structured
   data in tabular format would be valuable.

## 3. Coding standards

*   **Naming**: `snake_case` (functions/variables), `PascalCase` (classes),
    `SCREAMING_SNAKE` (constants).
*   **Error Handling**: Typed exceptions; context managers for resources.

## 0. Project overview
- **src/ts-api**: Core service for agent definitions and task execution
```

The step-by-step workflow the model runs anyway, meta-advice the file gives to its own authors, naming conventions any model knows — and `src/ts-api`, a component the rest of the file calls `agents-api`.

**After** — 4,288 bytes, verbatim excerpts:

```
# AGENTS.md — Julep AI

## Golden rules

- When unsure about implementation details or requirements — ask the developer
  before making changes. Never guess project-specific decisions.
- Generate code only inside the relevant component's source directories (or
  explicitly pointed files). Never touch `tests/`, `SPEC.md`, `*_spec.py`, `*.ward`
  — humans own tests & specs.
- For changes >300 LOC or >3 files, ask for confirmation before starting.
- Never modify `.agentignore` / `.agentindexignore` without explicit permission.

## Commands

poe format    # ruff format
poe test      # ward test --exclude .venv (pytest for integrations-service)
…

## AIDEV anchors

- Add `AIDEV-NOTE:` / `AIDEV-TODO:` / `AIDEV-QUESTION:` comments (≤120 chars)
  near non-trivial code: long, complex, important, confusing, or bug-adjacent.
- Never remove `AIDEV-NOTE`s without explicit human instruction.
```

Every golden rule, every safety gate, every working command, the TypeSpec and ward specifics, the AIDEV ritual — all still there, deduplicated.

**19,342 → 4,288 bytes (−78%).** This very file then ran as an arm in the [A/B benchmark](#-the-numbers): quality 100% in both arms, cost −14% on the bugfix task, −8% on the coding task — and +80% on the conventions task, because after the cleanup the rules actually bind and the agent works them properly.

```
P1 generated   → alive — "Never manually edit generated files (`autogen/`) — they get overwritten" quoted
P2 big changes → alive — ">300 LOC or >3 files — ask for confirmation before starting" quoted
P3 AIDEV       → alive — "AIDEV-NOTE / AIDEV-TODO / AIDEV-QUESTION, ≤120 chars" quoted
```

> **What's a probe?** The whole proof mechanism, in three sentences. HiViz opens a brand-new agent session in the background — no chat, just a question — and asks it to quote a rule ("what are your directives about secrets?"). If the fresh session still quotes the rule, the rule is alive, no matter which file it lives in. That's a probe; every "alive" above is one.

> **Who is HiViz?** The one everybody calls by the vest. Comes in at 6:15, after the lazy senior left at 6:00 — working code, and a nest of wires under the desk that's been "temporary" for two years. He doesn't rewrite what the senior built. He traces what's still live, tags everything `live` / `dead` (the tags are yours to place, not his), and never throws anything out on the day he finds it. *The mess isn't stupid. It's just unmapped.*

### It also catches things linters can't even see

**Drift** — instructions contradicting the live machine (deterministic, no LLM):

```
| status       | fact                | detail                                |
|--------------|---------------------|---------------------------------------|
| STALE        | v3-migration-done   | pattern not found                     |
| STALE        | mcp:code-index      | 1,430 tokens/session, 0 calls ever    |
| STALE        | legacy-runner-doc   | missing: docs/legacy-runner.md        |
| UNVERIFIABLE | staging-credentials | no check defined                      |
| OK           | deploy-command      | pattern found                         |
```

**Constitution tests** — rules that exist in the file but stopped *binding* the model:

```
PASS   commit-gate        "NEVER commit… without an explicit request" — quoted by a fresh session
PASS   secrets-verbatim   "redact them" — quoted
FLAKY  language-default   failed once, passed on retry — reported, not hidden
```

**MCP footprint + usage** — what your MCP servers cost every session, and whether anything ever calls them:

```
| server     | harnesses             | tools |  bytes | tokens | calls | last used  |
|------------|-----------------------|------:|-------:|-------:|------:|------------|
| code-index | claude code            |    14 |  6,510 |  1,430 |     0 | never      |
| crawler    | claude code            |     4 |  4,881 |  1,125 |    91 | 2026-09-17 |
| context7   | claude code            |     2 |  4,596 |    989 |    48 | 2026-09-20 |
```

Fourteen tools, 1,430 tokens, every single session, zero invocations ever. That number is the case for disabling it.

## 🌍 Why this exists

In July 2026, Anthropic engineers reported removing over 80% of Claude Code's system prompt for the newest models — coding evals didn't move. OpenAI's guidance now says overloaded prompts **hurt more than help**: new models follow instructions literally, so two conflicting rules destabilize behavior more than no rule at all.

Meanwhile your `CLAUDE.md`, skills, subagents and MCP configs keep growing. Every "add a line to fix it" is a loan. The interest compounds as duplicates diverge and facts rot.

Linters see file structure. HiViz sees the loop: **what the instructions claim vs what the machine says vs what the model actually does** — and closes all three gaps with evidence, not vibes. The taxonomy matches the first academic catalog of AGENTS.md smells ([arXiv 2606.15828](https://arxiv.org/abs/2606.15828)).

A preregistered 4,643-run study put numbers on the mechanism ([arXiv 2608.01347](https://arxiv.org/abs/2608.01347)): prompt **length** is nearly free — verbose repetition measures \~1.0× — while phrases that **order extra work** are not. "Compare several approaches" multiplies reasoning 2.4–7.4× at zero correctness gain; certainty language ("make absolutely sure") inflates output up to 4.1×, buying re-verification loops, not success. The most dangerous line in your config isn't the verbose one — it's the *plausible wrong hint*: misleading architectural hints raised reasoning 2.61× — the costliest input defect measured — while irrelevant noise measured nearly free (1.03×). And the harness amplifies all of it: a heavy standing prefix replays those consequences every single turn.

---

## 📈 It compounds

Everything hiviz does leaves working material behind — and nothing gets lost between runs:

- After an audit you keep the report, your decisions file, a facts checklist, and a change log. The next audit starts from them, not from zero.
- While you work, hiviz counts which MCP tools actually get called and remembers where every instruction line came from. The longer you've been running agents, the better it can answer "is this instruction earning its tokens?"
- When you switch tools (Claude Code → Codex → Cursor), it carries your instructions over and checks nothing got lost on the way.

It starts as a linter. It grows into the history of every rule you approved, tested, and shed.

---

## ⚡ Quick Start

Detects every supported agent on your machine, installs the right adapter into each, deploys the python engines to `~/.hiviz/engines`. Safe to re-run.

**Requirements:** Node ≥ 16 (installer) · Python ≥ 3.11 (engines). The audit and apply run inside YOUR agent session on your existing plan — no extra API keys; the deterministic engines (drift, meters, blame) call no model at all. Changed your mind: `npx hiviz uninstall`. Windows gotchas live in the [RUNBOOK](./RUNBOOK.md).

```bash
npx hiviz init
```

### 🕐 The first five minutes

1. **Run the audit.** `/hv-audit` (Claude Code, Codex) or just ask *"audit my prompt debt"*. You get a report: every line categorized — invariant / trained-duplicate / relic / 90%-rule / conflict — with a recommendation each.
2. **Decide.** Fill the DECISION column in `.hiviz/decisions.md`: yes / no / as-condition / merge. HiViz never decides for you — analysis and action are separate sessions, on purpose.
3. **Apply.** `/hv-apply` executes exactly your decisions: `.bak` backups first, then edits, then fresh headless probes quoting each surviving rule. A probe that fails restores the line from backup.
4. **Check drift.** `/hv-drift` diffs your facts registry against the live machine — milliseconds, no LLM, and half of real-world findings.
5. **Test your constitution.** `/hv-test` runs probe tests for your load-bearing rules. Wire it into CI: a PR that breaks a standing rule's binding goes red.

---

## 🧩 What it catches


| Smell                 | Example from the wild                                            | Caught by                                          |
| --------------------- | ---------------------------------------------------------------- | -------------------------------------------------- |
| **Trained duplicate** | "Write clean code, follow best practices"                        | audit (trained-duplicate)                          |
| **Relic**             | "Final stack state (2026-01-15): toolchain v2.1" when v3 shipped | audit (relic) + drift STALE                        |
| **Context tax**       | 2 MCP servers costing 2,400 tokens every session                 | meters (internal engine, runs inside audit)        |
| **Conflict**          | Gateway `10.0.0.42` in AGENTS.md vs `10.0.0.99` in a skill       | audit (conflict) + blame (fresher provenance wins) |
| **Stale fact**        | "curl cannot write to disk" — refuted by three other files       | drift                                              |
| **Dead rule**         | safety line deleted by a "cleanup" PR                            | constitution FAIL                                  |
| **Lost origin**       | "who wrote this rule and why?"                                   | blame: ledger + session-log mining                 |


---

## 📊 The Numbers

Pilot scale (4 tasks × 5 repeats × 2 arms, one model) — read the deltas as a pattern, not a coefficient. Reproduce: `python bench/run_ab.py` (LLM, \~30 min) · `python tests/run.py --t1` (free, seconds). One block ≈ 4% cost change; the cleaned arm is arm B.

```
cost delta per task — cleaned corpus vs bloated arm

popular config (41.6k★ CLAUDE.md + 23 skills)        single file (julep AGENTS.md 19.3k→4.3k, no skills)
bugfix       ███████ −29%                            bugfix       ████ −14%
cli-todo     ████████ −33%                           cli-todo     ██ −8%
qa           █ −4%                                   qa           █ −3%
conventions  ███ +12%                                conventions  ████████████████████ +80%

▲ negative = cheaper · the conventions bar grows on purpose: after cleanup the rules
  actually bind, and the agent spends turns obeying them (grounding +23% / +10%)
quality: 100% in both arms on every task, both configs
```

The conventions bar is the product thesis upside-down: a cleaned corpus makes rules bind, and binding costs turns. Full tables: [popular](./bench/runs/20260924-174948/results.md) · [single-file](./bench/runs/20260924-190543/results.md) · [rules-inventory](./bench/rules_inventory.py)


| What                     | Measured on                                            | Result                                                                                         |
| ------------------------ | ------------------------------------------------------ | ---------------------------------------------------------------------------------------------- |
| **Translator roundtrip** | omp → neutral intermediate format → omp, probe-checked | first run **caught a line genuinely lost in migration** (2/3 → FAIL); after the fix, 3/3 green |


<sub>A private case, not a benchmark — the maintainer's own desk after one cleanup: AGENTS.md −65% (3,362 → 1,180 B) · 17 low-quality skills removed · MCP surface 6 servers → 2, i.e. 4.0k → 2.4k tokens/session.</sub>

---

## Commands


| Command (Claude Code / Codex) | What it does                                                                                    |
| ----------------------------- | ----------------------------------------------------------------------------------------------- |
| `/hv-audit`                   | 5-category revision of your instruction corpus → report + decisions file (you decide)           |
| `/hv-apply`                   | executes exactly your decisions: backups, edits, ledger, probes that quote every surviving rule |
| `/hv-drift`                   | facts-vs-environment diff: which standing facts are STALE                                       |
| `/hv-test`                    | constitution tests: prove rules are LIVE in fresh sessions                                      |
| `/hv-translate`               | migrate the corpus between harnesses (omp↔Claude↔Codex↔Cursor), probe-checked equivalence       |
| `/hv-blame`                   | provenance for any instruction line: ledger + session-log mining — who wrote it, when, why      |


omp: all five install as skills and auto-trigger on plain asks (*"audit my prompt debt"*) — they wake when you ask, never on their own. Cursor / Windsurf / OpenCode: a single audit adapter (audit + apply). Engines: `~/.hiviz/engines` (python stdlib, zero dependencies).

### Where things live

In your project, `.hiviz/`: `report.md` + `decisions.md` (audit), `probes-*.md` (apply proof), `ledger.jsonl` (change log), `facts.toml` (drift checklist), `tests/*.toml` (constitution), `mcp_footprint.json` (meters) — plus the reports each engine emits (`drift-report.md`, `constitution.json`, `report.html`, `ir.jsonl` — the intermediate format), all in the same place. On your machine: adapters inside each agent's config dir, engines in `~/.hiviz/engines`. Nothing lands anywhere else.

---

### Run it in CI

After an audit leaves `.hiviz/facts.toml` in your repo, the deterministic drift gate runs keyless in any CI — zero-config as a GitHub Action:

```yaml
- uses: Zorgzeleniy/hiviz@main
```

That's the whole step: it installs the engines and fails the build when a standing fact goes STALE (path moved, command gone, MCP server unused for 30 days). Constitution probes need a live agent, so those stay a local/agent-CLI concern, not CI.

---

## 🚫 What it never does

The five invariants are the product. Breaking any of them is a semver-major decision.

1. **Never rewrites during audit.** Analysis and action are separate sessions; decisions are yours.
2. **Never deletes safety lines.** Secrets, access, prod, commit/push gates are marked invariants — dedup/move only.
3. **Never edits without a `.bak-<date>` backup** next to the file.
4. **Never adds anything of its own.** Apply performs exactly the approved decisions, word for word.
5. **Never claims a rule survived without a probe.** Verification = a fresh headless session quoting the rule.

---

## 📄 License

MIT — see [LICENSE](./LICENSE). Vendored test fixtures (superpowers, anthropics/skills) keep their own licenses.

