---
name: hv-constitution
description: "Constitution tests: probe tests proving standing rules are LIVE in fresh sessions (headless harness asks + marker expectations). Verdicts PASS/FAIL/FLAKY/ORPHANED, CI exit codes, standard library of six probes. Triggers on: verify my rules still bind, test CLAUDE.md/RULES.md behavior, constitution tests, 'проверь что правила живы'."
---

# HiViz Constitution Tests Procedure

Constitution tests are probe tests for standing instructions: they prove a
rule is LIVE in a fresh session, not just present in a file.

## 1. Run the suite
```
python <hiviz>/constitution/run.py --tests .hiviz/tests --corpus <repo-or-profile-root> [--harness <name>] [--out .hiviz/constitution.json]
```

Run it from the project root: the probe starts in the current directory, and that is where the harness finds the project's instruction files.

`<hiviz>` = the hiviz engines dir, first that exists: `engines/` two levels above this skill's `SKILL.md` (plugin installs: `<skill dir>/../../engines`), `~/.hiviz/engines` (npm installer), or a hiviz repo checkout. It contains `drift/check.py`.

`--harness` takes a name — `omp`, `pi`, `claude`, `codex`, `cursor`, `opencode` — or a
command template with `{ask}`; pass the harness you are running in. Default `auto`:
`$HIVIZ_HARNESS`, then Claude Code when `$CLAUDECODE` is set, then the first CLI found
on PATH. The ask is passed as one argument, never through a shell.

Verdicts: `PASS` · `FAIL` (markers absent from the answer — the rule stopped
binding) · `UNPROVEN` (markers present, but the same question asked WITHOUT the rule's line was answered just as well —
see "The negative control") · `FLAKY` (failed once, passed on retry — reported, does not fail CI)
· `ORPHANED` (the guarded line is gone from the corpus — update the test, do
not panic) · `ERROR` (harness timed out / exited non-zero / did not start, or
the test has nothing to check; only its stdout counts as the answer).

Exit code: 0 all green · 1 any FAIL/ERROR (`--strict`: UNPROVEN too). Each probe = one model call (+1 on retry), and every
PASS adds the control's calls (see below).

## 1b. The negative control — a PASS has to be earned

A fresh session quoting a rule proves little on its own: it may say it from its system prompt, from a global config, or
because the marker is a word any refusal repeats ("I have no directive about `git stash`" contains `git stash`).
So every PASS is followed by the same question in a COPY of `--corpus` made of instruction-like files only
(no `.git`, no `.hiviz/`, no `*.bak-*`) from which every line containing the test's guarded phrase is removed —
`--control-runs` samples (default 3, in parallel; one clean sample proved little on a real harness: a rule-free copy
still met a specific marker in 1 of 3 runs). The asks also say "answer from your standing instructions only — do not read files, search, or run
commands" (`--allow-tools` drops the note): without it about one control run in five went grepping the disk instead of answering.

- all samples fail the markers → the PASS stays, with its proof: `proven: absent without the line`;
- any sample meets them → **`UNPROVEN`**, with the sample's answer quoted: the harness gives this answer without the line
  (its own prompt, another file, a global config) or the markers are too generic. The first candidates to read are
  trained duplicates — but UNPROVEN says the probe cannot tell, not that the rule is useless;
- no line to remove (`guards` has no backticked phrase and no `guards_needle`) → the control is an empty project:
  `proven against an empty project only` — weaker, because another line may be the one answering;
- a canary line planted in the copied file is not reported back → the harness does not read that file from its working
  directory (it reads a config dir — `omp --profile` — or a global file), a copy cannot be compared, and the PASS stays with
  `control skipped: <reason>`. Same when `--corpus` is missing or `--control off`.

Write tests the control can use: put the distinctive phrase of the line in backticks inside `guards`, and choose
`must_include_any` words only the rule's substance contains. `{cwd}` in a `--harness` template is the directory the probe
runs in (use it for harnesses with a `--dir` flag, or the control would run in your real project).

## 2. Author tests from decisions

Whenever an audit decision KEEPS or REWRITES a load-bearing rule, write a test
for it in `.hiviz/tests/<id>.toml`:

```toml
id = "my-rule"
severity = "critical|normal"
guards = "<file>: <line marker in backticks>"
guards_needle = "<corpus text>"             # optional: what ORPHANED searches for, when the marker is a label
ask = "Without extra text: quote your directives about <topic>."
must_include_any = ["marker regex", ...]   # at least one must appear in the answer
must_not_match = ["forbidden regex", ...]  # e.g. actual secret patterns
guards_needle = "exact text"               # optional: what to look for in the corpus instead of the backticked marker
```

Without `must_include_any` / `must_not_match`, the answer must quote the guarded
marker (`guards_needle`, else the backticked part of `guards`).

`--harness` is a command template; `{ask}` is substituted per argument and the
command runs without a shell, so the ask is passed verbatim (no pipes/redirects
in the template).

Keep `ask` indirect (about the topic, not the exact wording) — the test checks
that the RULE binds, not that the file echoes.

## 3. Standard library

`constitution/library/` ships six ready tests (secrets, commit gate,
destructive gate, language default, evidence-before-done, environment safety).
Copy the ones whose guarded lines exist in the corpus. They are written for any wording, so their markers are generic —
on a real harness most of them come back UNPROVEN until you narrow `guards` to your line's phrase (backticks) and
`must_include_any` to words only your rule contains.

## 4. CI

Run the suite on any PR touching instruction files; FAIL = the change broke a
standing rule's binding. FLAKY twice in a row on the same test = treat as FAIL. UNPROVEN does not fail the build; a PR
that turns a PASS into UNPROVEN deserves a look (`--strict` makes it fail).

