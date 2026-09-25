# Bench — the popular A/B benchmark ("shed bench")

**Question it answers:** take a real popular agent config (a few dozen skills + a real AGENTS.md/CLAUDE.md); run the same deterministic tasks before and after a hiviz cleanup — what happens to tokens, time, and quality?

## Protocol

```
for config C (real, permissive-license, popular):
    arm A = C as-is            (frozen copy)
    arm B = C after ONE hiviz audit+apply (diff frozen once, reused forever)
    for task T in 4 deterministic tasks:
        N repeats × both arms, cold sessions, one model, one harness
        metrics: tokens_in (fresh input + cache reads) · tokens_out · wall_clock · turns · pass/fail
aggregate medians → table (md + html view via render/report.py)
```

- No fake MCP anywhere. No shared memory: bench profiles get `memory: {backend: local}` and their own `agent.db`.
- The cleanup (arm B) is frozen — run-to-run variance of the CLEANER never leaks into task numbers.
- Quality is 100% deterministic (verifiers are stdlib python; no LLM judges).

## Tasks (all deterministic)

| task | agent does | verifier |
|---|---|---|
| `cli-todo` | build `todo.py` (add/list/done/remove, todo.json) | drives the CLI end-to-end, checks storage |
| `bugfix` | fix a planted off-by-one in `calc.py` | hidden assertions incl. edge cases + API signature preserved |
| `conventions` | create `NOTES.md` + `COMMIT_MSG.txt` following the corpus's own hard rules | regex/format checks **derived from the config itself** (measures binding of kept rules) |
| `qa` | answer 5 questions whose answers live in the corpus | substring markers |

`conventions` and `qa` are authored per-config against its real content (bench/configs/<name>/meta). This is the manual labeling step, done once per config at freeze time.

## Honest limitations (kept on purpose)

- 4 tasks × N repeats (default 5) is a pilot scale, not science; report medians and say so.
- Corpus facts in `qa` could in principle be answered from training data if the repo is famous; markers are chosen to require the local file.
- Token accounting: `tokens_in` is the total input the model saw — fresh input + cache reads merged; `tokens_out` reported separately. Usage comes from `--mode=json`; model and repeat count are recorded in `results.json`.

## Layout

```
bench/
  tasks/<name>/{task.md, verify.py, fixtures/}
  configs/<name>/{corpus/ (AGENTS.md/CLAUDE.md + skills/), meta.toml, qa.json, conventions.json}
  run_ab.py   # profile setup + headless runs + verification + metrics + table
```
