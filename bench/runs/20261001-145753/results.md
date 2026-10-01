# Shed-Bench Results

| arm | task | pass | score | wall (med) | tok in (incl cache) | tok out | cache | cost $ | turns |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| a | harden-client | 100% | 10.0 (10-10) | 144s (110-214) | 98,750 | 7,131 | 80,896 | 0.0774 | 6 |
| b | harden-client | 100% | 10.0 (10-10) | 133s (104-156) | 113,075 | 8,018 | 94,848 | 0.0935 | 7 |

## Deltas (A → B)

| task | wall | tok in | tok out | cost |
|---|---:|---:|---:|---:|
| harden-client | -8% | +15% | +12% | +20.8% |

## Standing instructions (A → B)

| arm | standing file | skills | skill bytes | total payload |
|---|---:|---:|---:|---:|
| A | 15,245 B | 17 | 456,823 B | 472,068 B |
| B | 3,638 B | 17 | 436,297 B | 439,935 B |

standing file -76% · skill bytes -4% · total payload -7% — the audit cut skills too, not only the standing file

_Generated 2026-10-01 15:12 · 6 runs total · model zai/glm-5.3:max · tok in = fresh input + cache reads_
