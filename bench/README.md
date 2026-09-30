# Bench — the popular A/B benchmark ("shed bench")

**Question it answers:** take a real popular agent config (a few dozen skills + a real AGENTS.md/CLAUDE.md); run the same deterministic tasks before and after a hiviz cleanup — what happens to tokens, time, and quality?

## Protocol

```
for config C (real, permissive-license, popular):
    arm A = C as-is            (frozen copy)
    arm B = C after ONE hiviz audit+apply (diff frozen once, reused forever)
    for task T in the real-project tasks:
        N repeats × both arms, cold sessions, one model, one harness
        metrics: tokens_in (fresh input + cache reads) · tokens_out · wall_clock · turns · pass/fail
aggregate medians → table (md + html view via render/report.py)
```

- No fake MCP anywhere. No shared memory: bench profiles get `memory: {backend: local}` and their own `agent.db`.
- The cleanup (arm B) is frozen — run-to-run variance of the CLEANER never leaks into task numbers.
- Quality is 100% deterministic (verifiers are stdlib python; no LLM judges).

## Tasks (all REAL-project tasks; deterministically verified)

| task | agent does | verifier |
|---|---|---|
| `harden-client` | hardens a naive API client (`client.py`) to a production contract: retry/backoff, typed exceptions, cursor pagination | 10 behavioral scenarios with a scripted fake transport (exact call counts, sleep sequences, error mapping) |
| `bug-hunt` | the real PyJWT source tree (vendored, MIT) ships with **three real historical bugfixes reverted** — find and fix them by behavior | 10 checks ported from the upstream fixes' own tests (#670, #1039, #1186) |
| `tx-kv` | implements a transactional in-memory KV store (`store.py`): TTL, nested savepoints, WAL with exact bytes, conflict detection | 10 scenarios with an injected clock + a seeded 50-op random script replayed against a reference model |
| `real-jwt` *(archived)* | implements a PyJWT-compatible JWT subset from scratch (single `jwt.py`, HS256, full claim/exception taxonomy) | 10 checks **ported from pyjwt 2.10.1's real test suite** (canonical interop token byte-exact, leeway, aud/iss, alg-confusion); site-packages stripped so an installed PyJWT cannot satisfy it |

Default rounds (`TASKS` in run_ab.py): `harden-client`, `bug-hunt`. `real-jwt` is
archived — both arms saturate 10/10, it measures cost only. `conventions`/`qa`
(corpus-labeling tasks) existed in earlier rounds; their labeling files remain
in configs/ for the frozen historical runs.

## Honest limitations (kept on purpose)

- This is a field version: 4 tasks × 2 configs × n=3 on one model and one harness is a pilot scale, not science; report medians and say so. Cells where a run came back without provider cost data are reported as n/a, not estimated.
- Corpus facts in `qa` could in principle be answered from training data if the repo is famous; markers are chosen to require the local file.
- Token accounting: `tokens_in` is the total input the model saw — fresh input + cache reads merged; `tokens_out` reported separately. Usage comes from `--mode=json`; model and repeat count are recorded in `results.json`.

## Layout

```
bench/
  tasks/<name>/{task.md, verify.py, fixtures/}
  configs/<name>/{corpus/ (AGENTS.md/CLAUDE.md + skills/), meta.toml, qa.json, conventions.json}
  run_ab.py   # profile setup + headless runs + verification + metrics + table
```
