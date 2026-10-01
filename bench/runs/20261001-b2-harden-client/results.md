# Shed-Bench Results

| arm | task | pass | score | wall (med) | tok in (incl cache) | tok out | cache | cost $ | turns |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| a | harden-client | 100% | 10.0 (10-10) | 131s (129-134) | 186,327 | 7,751 | 172,224 | 0.1002 | 11 |
| b | harden-client | 100% | 10.0 (10-10) | 130s (110-158) | 53,749 | 8,613 | 43,072 | 0.0661 | 4 |

## Deltas (A → B)

| task | wall | tok in | tok out | cost |
|---|---:|---:|---:|---:|
| harden-client | -1% | -71% | +11% | -34.1% |

## Standing instructions (A → B)

| arm | standing file | skills | skill bytes | total payload |
|---|---:|---:|---:|---:|
| A | 15,245 B | 17 | 456,823 B | 472,068 B |
| B | 3,638 B | 17 | 456,823 B | 460,461 B |

standing file -76% · skill bytes +0% · total payload -2%

_Generated 2026-10-01 17:04 · 6 runs total · model zai/glm-5.3:max · tok in = fresh input + cache reads_
