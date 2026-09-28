# Shed-Bench Results

| arm | task | pass | score | wall (med) | tok in (incl cache) | tok out | cache | cost $ | turns |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| a | harden-client | 100% | 10.0 (10-10) | 194s (146-222) | 249,235 | 9,513 | 238,144 | 0.1283 | 8 |
| b | harden-client | 100% | 10.0 (10-10) | 209s (143-217) | 333,014 | 9,965 | 320,320 | 0.1449 | 11 |

## Deltas (A → B)

| task | wall | tok in | tok out | cost |
|---|---:|---:|---:|---:|
| harden-client | +8% | +34% | +5% | +13.0% |

_Generated 2026-09-28 11:56 · 6 runs total · model zai/glm-5.3:max · tok in = fresh input + cache reads_
