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
not panic) · `ERROR` (runner broke).

Exit code: 0 all green · 1 any FAIL/ERROR. Each probe = one model call (+1 on retry).

## 2. Author tests from decisions

Whenever an audit decision KEEPS or REWRITES a load-bearing rule, write a test
for it in `.hiviz/tests/<id>.toml`:

```toml
id = "my-rule"
severity = "critical|normal"
guards = "<file>: <line marker in backticks>"
ask = "Without extra text: quote your directives about <topic>."
must_include_any = ["marker regex", ...]   # at least one must appear in the answer
must_not_match = ["forbidden regex", ...]  # e.g. actual secret patterns
```

Keep `ask` indirect (about the topic, not the exact wording) — the test checks
that the RULE binds, not that the file echoes.

## 3. Standard library

`constitution/library/` ships six ready tests (secrets, commit gate,
destructive gate, language default, evidence-before-done, environment safety).
Copy the ones whose guarded lines exist in the corpus.

## 4. CI

Run the suite on any PR touching instruction files; FAIL = the change broke a
standing rule's binding. FLAKY twice in a row on the same test = treat as FAIL.
