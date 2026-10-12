# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/). Versions follow semver; below 1.0 a minor bump may change behavior.


## Unreleased

### Added
- `hiviz status` shows a **probe CLI** column (`probesReady` in JSON): whether a headless agent CLI is on
  PATH, so /hv-test's constitution probes are known to work (or known to ERROR) before you run them.
  Windsurf reports `no headless CLI` — its successor CLI (Devin) reads `AGENTS.md`, not `.windsurf/rules/`,
  so probing through it would fail live rules; documented in `core/TESTS.md`.
- `hiviz init` ends with a **first-step hint**: run /hv-audit in a project — report.md and report.html
  land in `.hiviz/`, you decide, then /hv-apply; plus a note when no probe CLI is on PATH.

### Changed
- npm tarball ships the engines once (inside `plugin/`), not twice — `hiviz init` syncs
  `~/.hiviz/engines` from `plugin/engines` (tarball) or the top-level dirs (a checkout). Tarball −46%.
- Bench configs share the vendored skill trees via `meta.toml` `skills = [...]` instead of one frozen
  copy per config (identical bytes; run records keep the byte counts). Working tree of `bench/configs` −95%.
- Windows fixes in the probe control: `$PWD` now points at the control copy on every OS (a Git Bash /
  test-rig `PWD` inherited by the probe made it read the real project instead of the ablated copy —
  verdicts were wrongly UNPROVEN); temp copies are actually removed (`git init` makes loose objects
  read-only; Windows refuses to unlink them).

## 0.8.0 — 2026-10-07

### Added
- **Readable output.** Every engine and the installer print for people on a terminal — tables, status symbols
  (✔ ✘ ◐ ○), color — and the same plain markdown as before when piped (agents, CI, the skill procedures).
  `--format auto|pretty|md` everywhere; `--format json` (one ASCII-only document on stdout) for `drift`, `constitution`,
  `blame`, `meters`, `render/report.py --summary` and `hiviz status`. `NO_COLOR`, `FORCE_COLOR`, `HIVIZ_FORMAT` and
  `HIVIZ_ASCII=1` are honored; cp866/cp1251 pipes degrade to `?` instead of crashing; the Windows console gets VT mode
  switched on and restored. Shared code: `render/hvfmt.py`.
- **Decide in the report.** `.hiviz/report.html` is now a working view: sort by effect / file, batch “yes” by category,
  per-row yes / no / keep / as-condition, conflicts shown side by side, kept-safe folded, and an **Export
  decisions.md** button (nothing is pre-filled — undecided stays empty and apply leaves that line alone).
  `render/report.py --summary` prints the same view for a terminal.
- **`drift --active-checks auto|on|off`** (`HIVIZ_ACTIVE_CHECKS`, Action input `active-checks`).
- Clear “needs Python >= 3.11” message instead of a `tomllib` traceback on older interpreters.
- **A probe PASS has to be earned (negative control).** After a PASS, `constitution/run.py` asks the same question in a copy of
  `--corpus` — instruction-like files only, no `.git` / `.hiviz` / backups — **without the rule's line** (or in an empty
  project when the test names no line), 3 samples in parallel. If any sample meets the markers too, the verdict is the new
  **`UNPROVEN`** (the answer is quoted; a refusal that repeats the marker, like “I have no directives about git stash”, is
  called out) instead of a PASS that proved nothing. A canary planted in the copied file checks that the harness really
  reads it from its working directory; if not (a profile / config dir), the PASS stays with `control skipped: <reason>`.
  `--control off`, `--control-runs N`, `--allow-tools`, `--strict` (UNPROVEN fails), `{cwd}` in `--harness` templates.
  Measured on OpenCode, 189 runs in git projects: with the rule in AGENTS.md the probe passed 53 of 54 times, without it
  generic markers still passed (`git stash` 6 of 6, library `destructive-gate` 6 of 6) — and the questions asked WITHOUT the
  no-tools note went grepping the disk in 10 of 54 control runs, with it in 0 of 108.
- **`apply/verify.py` — a deterministic check that apply changed only what was approved** (no model). New step 6 of the
  apply procedure: rows decided no / keep / empty and every kept-safe line unchanged, `yes` rows applied, no other line
  removed, changed or added, a backup for every edited file and none for a file no decision names, a ledger entry per
  approved decision. Rewrites and `as-condition` edits are listed for a human. Every FAIL says `restore` or `apply`.
  It replaces trust in the model's word with a diff.

### Changed
- **`hv-apply` runs its probes through the constitution engine** (steps 1 and 4): tests in `.hiviz/tests/`, verdicts
  PASS / UNPROVEN / FAIL in `.hiviz/probes-before.json` / `probes-after.json` — the model no longer hand-runs a harness and
  judges the answer. About 4 model calls per probed rule. Library tests are generic (most come back UNPROVEN on a real
  harness until you narrow `guards` and the markers); with `--corpus` given, a PASS now costs the control's calls too
  (`--control off` restores the old behavior).
- Probes start the harness with `$PWD` set to its directory: Bun / Node harnesses (OpenCode) take their working directory
  from `$PWD`, so `subprocess(cwd=…)` alone ran the probe in the caller's directory.
- **Audit report rows have six columns** — `| id | where | line | why | B | → verb |`: `where` is the absolute
  `path:line` (a conflict names both sides, `A ⇄ B`), `B` the bytes the verb touches, `why` starts with a category from
  a closed set. `core/AUDIT.md` carries the contract; `core/APPLY.md` now says how `DECISION` values are read.
  Reports in the old four-column form still render.
- **Behavior change:** drift `shell` and `port_open` facts are **not run** for pull requests from forks and under
  `pull_request_target` (they show as `UNVERIFIABLE`). Everywhere else they run as before. Force with
  `active-checks: "on"`.
- The installer prints symbols and a status table on a terminal. Piped output is unchanged.

### Fixed
- Audit reports whose models wrap paths in backticks or bold (`` `/a/AGENTS.md:13` ``) lost every row in the HTML view,
  the terminal summary and `apply/verify.py` (2 of 37 rows were read in a real run).
- `uninstall` on **Node 16** reported files as removed and exited 0 while they stayed (`fs.rmSync` swallows `EACCES` there).
- Windows: `C:\…` paths in reports, BOM-prefixed reports, UTF-8 output on legacy code pages.
- `translate --format json` was accepted and silently printed text; it is now refused.

### Development
- `tests/run.py` split into `tests/rig/`. New: T1 asks the **real** Claude Code, Codex, pi, OpenCode and omp CLIs
  whether they see the hiviz skills (no model, no credentials); `--t2x` exports decisions from the report page and applies
  them with a real model; CI gets lint, a Python 3.10 guard, an OS × Python × Node matrix and a harness-discovery job.
- The T2 sandbox now renders `hv-apply` for every harness (omp's `--profile` does not see the global install).
- Known gaps: Cursor and Windsurf are checked for file placement only (Cursor validates its API key online before
  listing anything; Windsurf has no agent CLI). T2 model runs are wired for omp and OpenCode.
