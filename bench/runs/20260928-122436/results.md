# Shed-Bench Results

| arm | task | pass | score | wall (med) | tok in (incl cache) | tok out | cache | cost $ | turns |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| a | tx-kv | 100% | 10.0 (9-10) | 978s (903-987) | 1,337,121 | 49,079 | 1,288,960 | 0.5907 | 21 |
| b | tx-kv | 100% | 10.0 (10-10) | 1207s (784-1221) | 857,954 | 48,486 | 783,936 | 0.5208 | 33 |

## Deltas (A → B)

| task | wall | tok in | tok out | cost |
|---|---:|---:|---:|---:|
| tx-kv | +23% | -36% | -1% | -11.8% |

_Generated 2026-09-28 14:05 · 6 runs total · model zai/glm-5.3:max · tok in = fresh input + cache reads_
