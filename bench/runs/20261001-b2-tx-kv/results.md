# Shed-Bench Results

| arm | task | pass | score | wall (med) | tok in (incl cache) | tok out | cache | cost $ | turns |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| a | tx-kv | 100% | 10.0 (10-10) | 694s (528-794) | 536,367 | 38,043 | 480,128 | 0.4413 | 12 |
| b | tx-kv | 100% | 10.0 (10-10) | 839s (602-1056) | 754,492 | 43,504 | 703,808 | 0.4448 | 15 |

## Deltas (A → B)

| task | wall | tok in | tok out | cost |
|---|---:|---:|---:|---:|
| tx-kv | +21% | +41% | +14% | +0.8% |

## Standing instructions (A → B)

| arm | standing file | skills | skill bytes | total payload |
|---|---:|---:|---:|---:|
| A | 15,245 B | 17 | 456,823 B | 472,068 B |
| B | 3,638 B | 17 | 456,823 B | 460,461 B |

standing file -76% · skill bytes +0% · total payload -2%

_Generated 2026-10-01 16:51 · 6 runs total · model zai/glm-5.3:max · tok in = fresh input + cache reads_
