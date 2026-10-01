# Shed-Bench Results

| arm | task | pass | score | wall (med) | tok in (incl cache) | tok out | cache | cost $ | turns |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| a | bug-hunt | 0% | 6.0 (6-6) | 495s (373-507) | 1,020,974 | 22,642 | 968,704 | 0.4512 | 25 |
| b | bug-hunt | 0% | 6.0 (4-6) | 683s (448-1056) | 1,104,193 | 30,118 | 1,037,504 | 0.4956 | 25 |

## Deltas (A → B)

| task | wall | tok in | tok out | cost |
|---|---:|---:|---:|---:|
| bug-hunt | +38% | +8% | +33% | +9.9% |

## Standing instructions (A → B)

| arm | standing file | skills | skill bytes | total payload |
|---|---:|---:|---:|---:|
| A | 15,245 B | 17 | 456,823 B | 472,068 B |
| B | 3,638 B | 17 | 456,823 B | 460,461 B |

standing file -76% · skill bytes +0% · total payload -2%

_Generated 2026-10-01 18:04 · 6 runs total · model zai/glm-5.3:max · tok in = fresh input + cache reads_
