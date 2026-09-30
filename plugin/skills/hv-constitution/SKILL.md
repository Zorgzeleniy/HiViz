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

`<hiviz>` = the hiviz engines dir, first that exists: `engines/` two levels above this skill's `SKILL.md` (plugin installs: `<skill dir>/../../engines`), `~/.hiviz/engines` (npm installer), or a hiviz repo checkout. It contains `drift/check.py`.

`--harness` takes a name — `omp`, `pi`, `claude`, `codex`, `cursor`, `opencode` — or a
command template with `{ask}`; pass the harness you are running in. Default `auto`:
`$HIVIZ_HARNESS`, then Claude Code when `$CLAUDECODE` is set, then the first CLI found
on PATH. The ask is passed as one argument, never through a shell.

Verdicts: `PASS` · `FAIL` (markers absent from the answer — the rule stopped
binding) · `FLAKY` (failed once, passed on retry — reported, does not fail CI)
· `ORPHANED` (the guarded line is gone from the corpus — update the test, do
not panic) · `ERROR` (harness timed out / exited non-zero / did not start, or
the test has nothing to check; only its stdout counts as the answer).

Exit code: 0 all green · 1 any FAIL/ERROR. Each probe = one model call (+1 on retry).

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
Copy the ones whose guarded lines exist in the corpus.

## 4. CI

Run the suite on any PR touching instruction files; FAIL = the change broke a
standing rule's binding. FLAKY twice in a row on the same test = treat as FAIL.

