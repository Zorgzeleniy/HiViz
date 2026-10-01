# Shed-Bench Results

| arm | task | pass | score | wall (med) | tok in (incl cache) | tok out | cache | cost $ | turns |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| a | bug-hunt | 0% | 6.0 (6-6) | 450s (368-764) | 518,241 | 18,824 | 491,264 | 0.2468 | 22 |
| b | bug-hunt | 0% | 6.0 (6-7) | 290s (206-806) | 885,631 | 15,071 | 844,736 | 0.3432 | 28 |

## Deltas (A → B)

| task | wall | tok in | tok out | cost |
|---|---:|---:|---:|---:|
| bug-hunt | -36% | +71% | -20% | +39.1% |

## Standing instructions (A → B)

| arm | standing file | skills | skill bytes | total payload |
|---|---:|---:|---:|---:|
| A | 15,245 B | 17 | 456,823 B | 472,068 B |
| B | 3,638 B | 17 | 436,297 B | 439,935 B |

standing file -76% · skill bytes -4% · total payload -7% — the audit cut skills too, not only the standing file

_Generated 2026-10-01 16:09 · 6 runs total · model zai/glm-5.3:max · tok in = fresh input + cache reads_
