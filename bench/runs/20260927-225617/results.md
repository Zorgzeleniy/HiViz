# Shed-Bench Results

| arm | task | pass | score | wall (med) | tok in (incl cache) | tok out | cache | cost $ | turns |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| a | bug-hunt | 0% | 6.0 (6-6) | 510s (236-633) | 1,680,170 | 32,728 | 1,613,760 | 0.6566 | 28 |
| a | real-jwt | 100% | 10.0 (10-10) | 1069s (898-1349) | 3,636,382 | 76,711 | 3,527,488 | 1.4041 | 35 |
| b | bug-hunt | 0% | 6.0 (6-7) | 523s (390-840) | 1,461,241 | 28,795 | 1,412,800 | 0.5618 | 27 |
| b | real-jwt | 100% | 10.0 (10-10) | 1344s (701-1614) | 5,236,548 | 107,853 | 5,091,136 | 2.0018 | 39 |

## Deltas (A → B)

| task | wall | tok in | tok out | cost |
|---|---:|---:|---:|---:|
| bug-hunt | +3% | -13% | -12% | -14.4% |
| real-jwt | +26% | +44% | +41% | +42.6% |

_Generated 2026-09-28 01:44 · 12 runs total · model zai/glm-5.3:max · tok in = fresh input + cache reads_
