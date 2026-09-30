# HiViz Constitution Tests Procedure

Constitution tests are probe tests for standing instructions: they prove a
rule is LIVE in a fresh session, not just present in a file.

## 1. Run the suite
```
python <hiviz>/constitution/run.py --tests .hiviz/tests --corpus <repo-or-profile-root> [--out .hiviz/constitution.json]
```

`<hiviz>` = the repo checkout or the installed engines dir (`~/.hiviz/engines`).

Verdicts: `PASS` · `FAIL` (markers absent from the answer — the rule stopped
binding) · `FLAKY` (failed once, passed on retry — reported, does not fail CI)
· `ORPHANED` (the guarded line is gone from the corpus — update the test, do
not panic) · `ERROR` (harness timed out / exited non-zero / did not start, or
the test has nothing to check).

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
