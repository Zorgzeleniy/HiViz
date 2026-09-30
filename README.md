<div align="center">

# 🦺 HIVIZ

**Nothing gets cut in the dark.**

**Your agent's instruction files (`CLAUDE.md`, `AGENTS.md`, skills, MCP configs) rot. HiViz traces every rule to its outlet before anyone cuts it — and proves the cleanup lost nothing.**

<a href="https://www.npmjs.com/package/@zorgzeleniy/hiviz"><img src="https://img.shields.io/npm/v/@zorgzeleniy/hiviz?style=flat-square&color=orange&label=npm" alt="hiviz on npm"></a>
<a href="https://github.com/Zorgzeleniy/HiViz/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-MIT-green?style=flat-square" alt="MIT"></a>
<a href="#-quick-start"><img src="https://img.shields.io/badge/works_with-Claude_Code_·_Codex_·_omp_·_pi_·_Cursor_·_Windsurf_·_OpenCode-blue?style=flat-square" alt="7 harnesses"></a>
<img src="https://img.shields.io/badge/engines-python_stdlib-teal?style=flat-square" alt="stdlib only">
<img src="https://img.shields.io/badge/LLM_judgment-optional__and_separated-purple?style=flat-square" alt="human decides">

**One command, no account, no extra API key.** `npx @zorgzeleniy/hiviz init` [**→ Quick Start**](#-quick-start)

</div>

---

<div align="center">

**[Quick Start](#-quick-start) · [How it works](#-how-it-works) · [See it](#-see-it) · [What it catches](#-what-it-catches) · [Commands](#commands) · [The Numbers](#-the-numbers) · [Why](#-why-this-exists) · [CI](#run-it-in-ci) · [What it never does](#-what-it-never-does)**

</div>

---

## ⚡ Quick Start

```bash
npx @zorgzeleniy/hiviz init
```

Detects every supported agent on your machine, installs the commands and skills each one reads, and deploys the python engines to `~/.hiviz/engines`. Safe to re-run; `npx @zorgzeleniy/hiviz uninstall` removes only what it wrote (preview with `--dry`).

**Requirements:** Node ≥ 16 (installer) · Python ≥ 3.11 (engines). The audit and apply run inside YOUR agent session on your existing plan — no extra API keys; the deterministic engines (drift, meters, blame) call no model at all.

**Or through your agent's own plugin manager** — same skills, engines bundled:

| Harness     | Install                                                                      |
| ----------- | ---------------------------------------------------------------------------- |
| Claude Code | `/plugin marketplace add Zorgzeleniy/hiviz` → `/plugin install hiviz@hiviz`  |
| omp         | `/marketplace add Zorgzeleniy/hiviz` → `/marketplace install hiviz@hiviz`    |
| Codex       | `codex plugin marketplace add Zorgzeleniy/hiviz` → `codex plugin add hiviz@hiviz` |
| pi          | `pi install npm:@zorgzeleniy/hiviz`                                          |

Cursor, Windsurf and OpenCode: use `npx`. Where each harness gets what, env overrides and uninstall details: [docs/install.md](./docs/install.md).

## 🕐 How it works

1. **Run the audit.** `/hv-audit` (Claude Code, OpenCode), the `hv-audit` skill (Codex, omp, pi, Cursor, Windsurf) or just ask *"audit my prompt debt"*. You get a report: every line categorized — invariant / trained-duplicate / relic / 90%-rule — conflicts flagged, a recommendation for each.
2. **Decide.** Fill the DECISION column in `.hiviz/decisions.md`: yes / no / as-condition / keep. HiViz never decides for you — analysis and action are separate sessions, on purpose.
3. **Apply.** `/hv-apply` executes exactly your decisions: `.bak` backups first, then edits, then fresh headless probes quoting each surviving rule. A probe that fails restores the line from backup.
4. **Check drift.** `/hv-drift` diffs your facts registry against the live machine — milliseconds, no LLM.
5. **Test your constitution.** `/hv-test` runs probe tests for your load-bearing rules. Run it before merging changes to instruction files — a FAIL means the change broke a rule's binding. Probes need an agent CLI, so they run locally or in a CI job that has one (the bundled GitHub Action runs drift only).

---

## 🦺 See it

Every agent accumulates instructions that outlived the truth. Here is a real `AGENTS.md` from an open-source repo — julep-ai/julep, one of the 100 popular configs in the first academic AGENTS.md smells corpus ([arXiv 2606.15828](https://arxiv.org/abs/2606.15828)) — before and after one hiviz audit + apply.

**19,013 → 4,308 bytes (−77%), and every rule that mattered still binds:**

```
P1 generated   → alive — "Never manually edit generated files (`autogen/`) — they get overwritten" quoted
P2 big changes → alive — ">300 LOC or >3 files — ask for confirmation before starting" quoted
P3 AIDEV       → alive — "AIDEV-NOTE / AIDEV-TODO / AIDEV-QUESTION, ≤120 chars" quoted
```

<details>
<summary><b>Before</b> — 19,013 bytes, verbatim excerpts</summary>

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

</details>

<details>
<summary><b>After</b> — 4,308 bytes, verbatim excerpts</summary>

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

</details>

> **What's a probe?** The whole proof mechanism, in three sentences. HiViz opens a brand-new agent session in the background — no chat, just a question — and asks it to quote a rule ("what are your directives about secrets?"). If the fresh session still quotes the rule, the rule is alive, no matter which file it lives in. That's a probe; every "alive" above is one.

This very file then ran as the corpus arm in the field [A/B benchmark](#-the-numbers): the cleaned arm cost −13% to −29% on three of four tasks (tx-kv, hardening, bug-hunt) with no quality drop; on the fourth (real-jwt, a from-scratch implementation) it came out +43%, inside the run-to-run noise of n=3.

### It also catches things linters can't even see

**Drift** — instructions contradicting the live machine (deterministic, no LLM):

```
| status       | fact                | detail                                |
|--------------|---------------------|---------------------------------------|
| STALE        | v3-migration-done   | pattern not found                     |
| STALE        | legacy-runner-doc   | missing: docs/legacy-runner.md        |
| UNVERIFIABLE | staging-credentials | no check defined                      |
| OK           | deploy-command      | pattern found                         |
```

**MCP footprint + usage** — what your MCP servers cost every session, and whether anything ever calls them:

```
| server     | harnesses     | tools | bytes | tokens | calls | last used  |
|------------|---------------|------:|------:|-------:|------:|------------|
| code-index | claude/global |    14 | 6,510 |  1,430 |     0 | never      |
| crawler    | claude/global |     4 | 4,881 |  1,125 |    91 | 2026-09-17 |
| context7   | claude/global |     2 | 4,596 |    989 |    48 | 2026-09-20 |
```

Fourteen tools, 1,430 tokens, every single session, zero invocations ever. That number is the case for disabling it — and drift picks it up as a STALE `mcp:code-index` fact.

**Constitution tests** — rules that exist in the file but stopped *binding* the model:

```
PASS   commit-gate        "NEVER commit… without an explicit request" — quoted by a fresh session
PASS   secrets-verbatim   "redact them" — quoted
FLAKY  language-default   failed once, passed on retry — reported, not hidden
```

---

## 🧩 What it catches

| Smell                 | Example from the wild                                            | Caught by                                          |
| --------------------- | ---------------------------------------------------------------- | -------------------------------------------------- |
| **Trained duplicate** | "Write clean code, follow best practices"                        | audit (trained-duplicate)                          |
| **Relic**             | "Final stack state (2026-01-15): toolchain v2.1" when v3 shipped | audit (relic) + drift STALE                        |
| **Context tax**       | 2 MCP servers costing 2,400 tokens every session                 | meters (internal engine, runs inside audit)        |
| **Conflict**          | Gateway `10.0.0.42` in AGENTS.md vs `10.0.0.99` in a skill       | audit (conflict) + blame (fresher provenance wins) |
| **Stale fact**        | "curl cannot write to disk" — a one-line `shell` checker disagrees | drift                                              |
| **Dead rule**         | safety line still in the file, overridden by a newer skill       | constitution FAIL (deleted line → ORPHANED)        |
| **Lost origin**       | "who wrote this rule and why?"                                   | blame: ledger + session-log mining                 |

---

## Commands

| Command / skill               | What it does                                                                                    |
| ----------------------------- | ----------------------------------------------------------------------------------------------- |
| `/hv-audit`                   | sorts every line (invariant / trained-duplicate / relic / 90%-rule), flags conflicts → report + decisions file (you decide) |
| `/hv-apply`                   | executes exactly your decisions: backups, edits, ledger, probes that quote every surviving rule |
| `/hv-drift`                   | facts-vs-environment diff: which standing facts are STALE                                       |
| `/hv-test` (`hv-constitution`) | constitution tests: prove rules are LIVE in fresh sessions                                     |
| `/hv-translate`               | migrate the corpus between harnesses (any of the 7 ↔ any), probe-checked equivalence            |
| `/hv-blame`                   | provenance for any instruction line: ledger + session-log mining — who wrote it, when, why      |

Claude Code and OpenCode get them as slash commands; Codex, omp, pi, Cursor and Windsurf as skills that wake when you ask (*"audit my prompt debt"*), never on their own. Blame and MCP usage mine the session logs of omp, pi, Claude Code and Codex. Details: [docs/install.md](./docs/install.md).

### Where things live

In your project, `.hiviz/`: `report.md` + `decisions.md` (audit), `probes-*.md` (apply proof), `ledger.jsonl` (change log), `facts.toml` (drift checklist), `tests/*.toml` (constitution), `mcp_footprint.json` (meters) — plus the reports each engine emits (`drift-report.md`, `constitution.json`, `report.html`, `ir.jsonl` — the intermediate format), all in the same place. On your machine: npm installs put commands in each agent's config dir, shared skills in `~/.agents/skills` and engines in `~/.hiviz/engines`; plugin installs live in the harness's own plugin cache. Apply leaves `<file>.bak-<date>` next to every file it edits. Nothing lands anywhere else.

---

## 📊 The Numbers

An A/B shed-bench: arm A carries the full instruction corpus, arm B the cleaned one, same tasks, same model. **This is a field version of the bench — n=3 per cell, one model, one harness — so read it as an approximate direction, not a measurement.** Negative = cheaper for the cleaned arm.

```
field bench — glm-5.3 max effort, 48 runs: 4 tasks × 2 configs × 2 arms × n=3
tasks ported from real projects: PyJWT suite subset, vendored real historical fixes
cost of the cleaned arm B vs the corpus arm A, median of 3 runs

bug-hunt     popular ███████ −36%    julep ███ −14%
tx-kv        popular n/a †           julep ███ −13%
real-jwt     popular n/a †           julep +43% ‡
harden       popular +13% ‡          julep ██████ −29%

4 of 6 measured cells cheaper · median cell −13.5% · █ ≈ 5%
† one arm-B run came back without provider cost data — withheld until re-run
‡ runs of the same arm differ up to 4× at n=3 — not separable from noise at this scale
quality: the corpus arm never scored higher in any cell; cleaning caused 0 quality regressions.
  bug-hunt: clean arm reached 8/10 (popular) and 7/10 (julep); corpus arm flat 6/10 — never passed.
  tx-kv: in both configs the corpus arm dropped a point on the same exact-bytes WAL check; clean 10/10.
```

**A floor, not a ceiling.** The bench harness is bare on purpose: fresh profiles, no session memory, none of the surrounding system prompts and workflow context a real desk carries — which hold the very material HiViz cuts (rotting rules, duplicated standing instructions, stale MCP surfaces). Real setups start from a bigger pile, so the deltas above are more likely an underestimate than an overestimate of what a cleanup saves.

Full tables: max-effort real tasks — [popular: jwt/bugfix](./bench/runs/20260927-202620/results.md) · [popular: tx-kv](./bench/runs/20260928-122436/results.md) · [popular: harden](./bench/runs/20260928-113743/results.md) · [julep: jwt/bugfix](./bench/runs/20260927-225617/results.md) · [julep: tx-kv](./bench/runs/20260928-140558/results.md) · [julep: harden](./bench/runs/20260928-115634/results.md) · protocol and limitations: [bench/README.md](./bench/README.md)

Reproduce (needs the omp CLI and access to the model): `python bench/run_ab.py --arm-a bench/configs/popular-v2 --arm-b bench/configs/popular-v2-clean --repeats 3`. The tool's own deterministic test suite is separate: `python tests/run.py --t1` (free, seconds).

| What                     | Measured on                                            | Result                                                                                         |
| ------------------------ | ------------------------------------------------------ | ---------------------------------------------------------------------------------------------- |
| **Translator roundtrip** | omp → neutral intermediate format → omp, probe-checked | first run **caught a line genuinely lost in migration** (2/3 → FAIL); after the fix, 3/3 green |

<sub>A private case, not a benchmark — the maintainer's own desk after one cleanup: AGENTS.md −65% (3,362 → 1,180 B) · 17 low-quality skills removed · MCP surface 6 servers → 2, i.e. 4.0k → 2.4k tokens/session.</sub>

---

## 🌍 Why this exists

In July 2026, Anthropic engineers reported removing over 80% of Claude Code's system prompt for the newest models — coding evals didn't move. [OpenAI's current prompt guidance](https://developers.openai.com/api/docs/guides/prompt-guidance) says the same: don't carry over every instruction from an older prompt stack — legacy prompts over-specify the process, and with new models that **adds noise and narrows the solution path**.

Meanwhile your `CLAUDE.md`, skills, subagents and MCP configs keep growing. Every "add a line to fix it" is a loan. The interest compounds as duplicates diverge and facts rot.

Linters see file structure. HiViz sees the loop: **what the instructions claim vs what the machine says vs what the model actually does** — and closes all three gaps with evidence, not vibes. The taxonomy maps onto the first academic catalog of AGENTS.md smells ([arXiv 2606.15828](https://arxiv.org/abs/2606.15828)).

A preregistered 4,643-run study put numbers on the mechanism ([arXiv 2608.01347](https://arxiv.org/abs/2608.01347)): prompt **length** is nearly free — verbose repetition measures \~1.0× — while phrases that **order extra work** are not. "Compare several approaches" multiplies reasoning 2.4–7.4× at zero correctness gain; certainty language ("make absolutely sure") inflates output up to 4.1×, buying re-verification loops, not success. The most dangerous line in your config isn't the verbose one — it's the *plausible wrong hint*: misleading architectural hints raised reasoning 2.61× — the costliest input defect measured — while irrelevant noise measured nearly free (1.03×). And the harness amplifies all of it: a heavy standing prefix replays those consequences every single turn.

### It compounds

Everything hiviz does leaves working material behind — and nothing gets lost between runs:

- After an audit you keep the report, your decisions file, a facts checklist, and a change log. The next audit starts from them, not from zero.
- Each audit mines your harness session logs for which MCP tools actually get called, and the ledger records where every instruction line came from. The longer you've been running agents, the better it can answer "is this instruction earning its tokens?"
- When you switch tools (Claude Code → Codex → Cursor), it carries your instructions over and checks nothing got lost on the way.

It starts as a linter. It grows into the history of every rule you approved, tested, and shed.

---

## Run it in CI

After an audit leaves `.hiviz/facts.toml` in your repo, the deterministic drift gate runs keyless in any CI — zero-config as a GitHub Action:

```yaml
- uses: Zorgzeleniy/hiviz@main
```

That's the whole step: it runs the drift engine bundled in the action (no npm, no network) and fails the build when a standing fact goes STALE (path moved, command gone, MCP server unused for 30 days). MCP pay-vs-use rows appear when `.hiviz/mcp_footprint.json` is committed (the audit writes it). Constitution probes need an agent CLI and its credentials, so the action does not run them — add `python <hiviz>/constitution/run.py --harness <name>` as your own step if your CI has one.

---

## 🚫 What it never does

The five invariants are the product. Breaking any of them is a semver-major decision.

1. **Never rewrites during audit.** Analysis and action are separate sessions; decisions are yours.
2. **Never deletes safety lines.** Secrets, access, prod, commit/push gates are marked invariants — dedup/move only.
3. **Never edits without a `.bak-<date>` backup** next to the file.
4. **Never adds anything of its own.** Apply performs exactly the approved decisions, word for word.
5. **Never claims a rule survived without a probe.** Verification = a fresh headless session quoting the rule.

---

## 🦺 Who is HiViz

The one everybody calls by the vest. Comes in at 6:15, after the lazy senior left at 6:00 — working code, and a nest of wires under the desk that's been "temporary" for two years. He doesn't rewrite what the senior built. He traces what's still live, tags everything `live` / `dead` (the tags are yours to place, not his), and never throws anything out on the day he finds it. *The mess isn't stupid. It's just unmapped.*

---

## 📄 License

MIT — see [LICENSE](./LICENSE). Vendored fixtures keep their own licenses: superpowers and anthropics/skills (`tests/fixture/vendor/`), PyJWT (`bench/tasks/`, MIT), and the benchmark corpora in `bench/configs/` (julep-ai/julep `AGENTS.md`, Apache-2.0; the others as listed in each `meta.toml`).
