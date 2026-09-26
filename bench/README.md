# Bench — the popular A/B benchmark ("shed bench")

**Question it answers:** take a real popular agent config (a few dozen skills + a real AGENTS.md/CLAUDE.md); run the same deterministic tasks before and after a hiviz cleanup — what happens to tokens, time, and quality?

## Protocol

```
for config C (real, permissive-license, popular):
    arm A = C as-is            (frozen copy)
    arm B = C after ONE hiviz audit+apply (diff frozen once, reused forever)
    for task T in 2 real-project tasks:
        N repeats × both arms, cold sessions, one model, one harness
        metrics: tokens_in (fresh input + cache reads) · tokens_out · wall_clock · turns · pass/fail
aggregate medians → table (md + html view via render/report.py)
```

- No fake MCP anywhere. No shared memory: bench profiles get `memory: {backend: local}` and their own `agent.db`.
- The cleanup (arm B) is frozen — run-to-run variance of the CLEANER never leaks into task numbers.
- Quality is 100% deterministic (verifiers are stdlib python; no LLM judges).

## Tasks (both are REAL-project tasks; deterministically verified)

| task | agent does | verifier |
|---|---|---|
| `real-jwt` | implements a PyJWT-compatible JWT subset from scratch (single `jwt.py`, HS256, full claim/exception taxonomy) | 10 checks **ported from pyjwt 2.10.1's real test suite** (canonical interop token byte-exact, leeway, aud/iss, alg-confusion); site-packages stripped so an installed PyJWT cannot satisfy it |
| `bug-hunt` | the real PyJWT source tree (vendored, MIT) ships with **three real historical bugfixes reverted** — find and fix them by behavior | 10 checks ported from the upstream fixes' own tests (#670, #1039, #1186) |

`conventions`/`qa` (corpus-labeling tasks) existed in earlier rounds; their
labeling files remain in configs/ for the frozen historical runs.

## Honest limitations (kept on purpose)

- 2 tasks × N repeats (default 5) is a pilot scale, not science; report medians and say so.
- Corpus facts in `qa` could in principle be answered from training data if the repo is famous; markers are chosen to require the local file.
- Token accounting: `tokens_in` is the total input the model saw — fresh input + cache reads merged; `tokens_out` reported separately. Usage comes from `--mode=json`; model and repeat count are recorded in `results.json`.

## Layout

```
bench/
  tasks/<name>/{task.md, verify.py, fixtures/}
  configs/<name>/{corpus/ (AGENTS.md/CLAUDE.md + skills/), meta.toml, qa.json, conventions.json}
  run_ab.py   # profile setup + headless runs + verification + metrics + table
```
