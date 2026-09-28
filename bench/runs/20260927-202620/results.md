# Shed-Bench Results

| arm | task | pass | score | wall (med) | tok in (incl cache) | tok out | cache | cost $ | turns |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| a | bug-hunt | 0% | 6.0 (6-6) | 369s (314-421) | 1,381,895 | 19,280 | 1,331,904 | 0.5232 | 26 |
| a | real-jwt | 100% | 10.0 (10-10) | 1289s (773-1365) | 2,863,527 | 77,647 | 2,742,208 | 1.2821 | 37 |
| b | bug-hunt | 33% | 6.0 (6-8) | 254s (200-637) | 803,737 | 18,798 | 766,336 | 0.3343 | 20 |
| b | real-jwt | 100% | 10.0 (10-10) | 1203s (882-1287) | 2,819,888 | 65,355 | 2,692,096 | 1.1292 | 38 |

## Deltas (A → B)

| task | wall | tok in | tok out | cost |
|---|---:|---:|---:|---:|
| bug-hunt | -31% | -42% | -2% | -36.1% |
| real-jwt | -7% | -2% | -16% | -11.9% |

_Generated 2026-09-27 22:56 · 12 runs total · model zai/glm-5.3:max · tok in = fresh input + cache reads_
