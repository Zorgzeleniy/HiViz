# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/). Versions follow semver; below 1.0 a minor bump may change behavior.

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

### Changed
- **Audit report rows have six columns** — `| id | where | line | why | B | → verb |`: `where` is the absolute
  `path:line` (a conflict names both sides, `A ⇄ B`), `B` the bytes the verb touches, `why` starts with a category from
  a closed set. `core/AUDIT.md` carries the contract; `core/APPLY.md` now says how `DECISION` values are read.
  Reports in the old four-column form still render.
- **Behavior change:** drift `shell` and `port_open` facts are **not run** for pull requests from forks and under
  `pull_request_target` (they show as `UNVERIFIABLE`). Everywhere else they run as before. Force with
  `active-checks: "on"`.
- The installer prints symbols and a status table on a terminal. Piped output is unchanged.

### Fixed
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
