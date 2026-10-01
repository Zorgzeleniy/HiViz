# Shed-Bench Results

| arm | task | pass | score | wall (med) | tok in (incl cache) | tok out | cache | cost $ | turns |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| a | tx-kv | 100% | 10.0 (10-10) | 694s (528-794) | 536,367 | 38,043 | 480,128 | 0.4413 | 12 |
| b | tx-kv | 100% | 10.0 (10-10) | 820s (636-976) | 1,556,852 | 48,483 | 1,484,032 | 0.7201 | 25 |

## Deltas (A → B)

| task | wall | tok in | tok out | cost |
|---|---:|---:|---:|---:|
| tx-kv | +18% | +190% | +27% | +63.2% |

## Standing instructions (A → B)

| arm | standing file | skills | skill bytes | total payload |
|---|---:|---:|---:|---:|
| A | 15,245 B | 17 | 456,823 B | 472,068 B |
| B | 3,638 B | 17 | 436,297 B | 439,935 B |

standing file -76% · skill bytes -4% · total payload -7% — the audit cut skills too, not only the standing file

_Generated 2026-10-01 14:57 · 6 runs total · model zai/glm-5.3:max · tok in = fresh input + cache reads_
