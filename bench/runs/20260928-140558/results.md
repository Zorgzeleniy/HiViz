# Shed-Bench Results

| arm | task | pass | score | wall (med) | tok in (incl cache) | tok out | cache | cost $ | turns |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| a | tx-kv | 100% | 10.0 (9-10) | 775s (727-837) | 918,719 | 41,564 | 878,912 | 0.4348 | 16 |
| b | tx-kv | 100% | 10.0 (10-10) | 616s (609-651) | 715,046 | 34,087 | 678,592 | 0.3775 | 14 |

## Deltas (A → B)

| task | wall | tok in | tok out | cost |
|---|---:|---:|---:|---:|
| tx-kv | -21% | -22% | -18% | -13.2% |

_Generated 2026-09-28 15:16 · 6 runs total · model zai/glm-5.3:max · tok in = fresh input + cache reads_
