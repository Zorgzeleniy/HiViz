# Shed-Bench Results

| arm | task | pass | score | wall (med) | tok in (incl cache) | tok out | cache | cost $ | turns |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| a | harden-client | 100% | 10.0 (10-10) | 178s (149-297) | 334,010 | 11,375 | 300,736 | 0.1553 | 11 |
| b | harden-client | 100% | 10.0 (10-10) | 141s (89-151) | 263,101 | 6,891 | 252,736 | 0.1105 | 10 |

## Deltas (A → B)

| task | wall | tok in | tok out | cost |
|---|---:|---:|---:|---:|
| harden-client | -21% | -21% | -39% | -28.8% |

_Generated 2026-09-28 12:13 · 6 runs total · model zai/glm-5.3:max · tok in = fresh input + cache reads_
