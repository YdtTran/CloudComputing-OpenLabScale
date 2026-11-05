# Offline policy evaluation

Synthetic model results are not real monitoring accuracy, reclamation savings, or host/eBPF overhead.

Source: synthetic; seed: 42 (development).
Configuration SHA-256: 2934d9eeb23384fd46526e8fa71da0036cc8aa2d02110f8209785e1c180d3816
Bundle manifest SHA-256: cb75abd4ef0c603571d34c64d2a9ee686a46275b954d6903cc5eca87e1f310ea

global 5000ms ticks, start < tick < end; half-open truth joins.
micro sums counts; macro equal scenario, undefined omitted with contributing count; latency mean over detected intervals only; undetected censored. Zero denominators: N/A.

| Policy | TP | FP | TN | FN | Unknown predictions | Unknown truth | Precision | Recall | F1 | Coverage | Idle capture | Undetected intervals |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| no-reclaim | 0 | 0 | 3696 | 3480 | 0 | 0 | N/A | 0.000000 | 0.000000 | 1.000000 | 0.000000 | 132 |
| interaction-timeout | 3264 | 1728 | 1968 | 96 | 120 | 0 | 0.653846 | 0.971429 | 0.781609 | 0.983278 | 0.937931 | 0 |
| cpu-only | 2904 | 1740 | 1860 | 480 | 192 | 0 | 0.625323 | 0.858156 | 0.723468 | 0.973244 | 0.834483 | 0 |
| resource-multi | 2640 | 1008 | 2592 | 744 | 192 | 0 | 0.723684 | 0.780142 | 0.750853 | 0.973244 | 0.758621 | 0 |
| interaction-aware | 2412 | 276 | 3324 | 852 | 312 | 0 | 0.897321 | 0.738971 | 0.810484 | 0.956522 | 0.693103 | 0 |

## Formulas

- precision: `tp/(tp+fp)`
- recall: `tp/(tp+fn)`
- f1: `2*tp/(2*tp+fp+fn)`
- false_idle_rate: `fp/(fp+tn)`
- false_active_rate: `fn/(fn+tp)`
- coverage: `(tp+fp+tn+fn)/(tp+fp+tn+fn+abstain_eligible+abstain_retain)`
- idle_capture: `tp/(tp+fn+abstain_eligible)`

## no-reclaim: scenario / seed 42

| Scenario | Precision | Recall | F1 | False idle | False active | Coverage | Idle capture | Mean detected latency ms | Censored |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| bursty | N/A | 0.000000 | 0.000000 | 0.000000 | 1.000000 | 1.000000 | 0.000000 | N/A | 12 |
| cpu-background | N/A | 0.000000 | 0.000000 | 0.000000 | 1.000000 | 1.000000 | 0.000000 | N/A | 12 |
| disk-wait | N/A | 0.000000 | 0.000000 | 0.000000 | 1.000000 | 1.000000 | 0.000000 | N/A | 12 |
| editing-only | N/A | 0.000000 | 0.000000 | 0.000000 | 1.000000 | 1.000000 | 0.000000 | N/A | 12 |
| low-use | N/A | 0.000000 | 0.000000 | 0.000000 | 1.000000 | 1.000000 | 0.000000 | N/A | 12 |
| mixed | N/A | 0.000000 | 0.000000 | 0.000000 | 1.000000 | 1.000000 | 0.000000 | N/A | 12 |
| network-wait | N/A | 0.000000 | 0.000000 | 0.000000 | 1.000000 | 1.000000 | 0.000000 | N/A | 12 |
| pure-idle | N/A | 0.000000 | 0.000000 | 0.000000 | 1.000000 | 1.000000 | 0.000000 | N/A | 12 |
| reconnect | N/A | 0.000000 | 0.000000 | 0.000000 | 1.000000 | 1.000000 | 0.000000 | N/A | 24 |
| signal-loss | N/A | 0.000000 | 0.000000 | 0.000000 | 1.000000 | 1.000000 | 0.000000 | N/A | 12 |

Equal-scenario macro (contributing groups): precision=N/A (0), recall=0.000000 (10), f1=0.000000 (10), false_idle_rate=0.000000 (10), false_active_rate=1.000000 (10), coverage=1.000000 (10), idle_capture=0.000000 (10).

## interaction-timeout: scenario / seed 42

| Scenario | Precision | Recall | F1 | False idle | False active | Coverage | Idle capture | Mean detected latency ms | Censored |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| bursty | 0.500000 | 1.000000 | 0.666667 | 0.666667 | 0.000000 | 1.000000 | 1.000000 | 2000.000000 | 0 |
| cpu-background | 0.500000 | 1.000000 | 0.666667 | 0.685714 | 0.000000 | 1.000000 | 1.000000 | 0.000000 | 0 |
| disk-wait | 0.500000 | 1.000000 | 0.666667 | 0.666667 | 0.000000 | 1.000000 | 1.000000 | 4000.000000 | 0 |
| editing-only | 1.000000 | 0.888889 | 0.941176 | 0.000000 | 0.111111 | 1.000000 | 0.888889 | 13000.000000 | 0 |
| low-use | 0.500000 | 1.000000 | 0.666667 | 0.666667 | 0.000000 | 1.000000 | 1.000000 | 1000.000000 | 0 |
| mixed | 0.500000 | 1.000000 | 0.666667 | 0.666667 | 0.000000 | 1.000000 | 1.000000 | 4000.000000 | 0 |
| network-wait | 0.500000 | 1.000000 | 0.666667 | 0.666667 | 0.000000 | 1.000000 | 1.000000 | 3000.000000 | 0 |
| pure-idle | 1.000000 | 0.962963 | 0.981132 | 0.000000 | 0.037037 | 1.000000 | 0.962963 | 10000.000000 | 0 |
| reconnect | 1.000000 | 0.833333 | 0.909091 | 0.000000 | 0.166667 | 1.000000 | 0.833333 | 12000.000000 | 0 |
| signal-loss | 1.000000 | 1.000000 | 1.000000 | 0.000000 | 0.000000 | 0.833333 | 0.800000 | 51000.000000 | 0 |

Equal-scenario macro (contributing groups): precision=0.700000 (10), recall=0.968519 (10), f1=0.783140 (10), false_idle_rate=0.401905 (10), false_active_rate=0.031481 (10), coverage=0.983333 (10), idle_capture=0.948519 (10).

## cpu-only: scenario / seed 42

| Scenario | Precision | Recall | F1 | False idle | False active | Coverage | Idle capture | Mean detected latency ms | Censored |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| bursty | 1.000000 | 0.708333 | 0.829268 | 0.000000 | 0.291667 | 0.983333 | 0.708333 | 37000.000000 | 0 |
| cpu-background | 1.000000 | 0.666667 | 0.800000 | 0.000000 | 0.333333 | 1.000000 | 0.666667 | 40000.000000 | 0 |
| disk-wait | 0.470588 | 1.000000 | 0.640000 | 0.771429 | 0.000000 | 0.983333 | 1.000000 | 4000.000000 | 0 |
| editing-only | 0.352941 | 1.000000 | 0.521739 | 0.804878 | 0.000000 | 0.983333 | 1.000000 | 3000.000000 | 0 |
| low-use | 0.470588 | 1.000000 | 0.640000 | 0.771429 | 0.000000 | 0.983333 | 1.000000 | 1000.000000 | 0 |
| mixed | 0.850000 | 0.708333 | 0.772727 | 0.085714 | 0.291667 | 0.983333 | 0.708333 | 39000.000000 | 0 |
| network-wait | 0.470588 | 1.000000 | 0.640000 | 0.771429 | 0.000000 | 0.983333 | 1.000000 | 3000.000000 | 0 |
| pure-idle | 1.000000 | 0.962963 | 0.981132 | 0.000000 | 0.037037 | 1.000000 | 0.962963 | 10000.000000 | 0 |
| reconnect | 0.470588 | 1.000000 | 0.640000 | 0.771429 | 0.000000 | 0.983333 | 1.000000 | 2000.000000 | 0 |
| signal-loss | 0.962963 | 0.619048 | 0.753623 | 0.111111 | 0.380952 | 0.850000 | 0.520000 | 1000.000000 | 0 |

Equal-scenario macro (contributing groups): precision=0.704826 (10), recall=0.866534 (10), f1=0.721849 (10), false_idle_rate=0.408742 (10), false_active_rate=0.133466 (10), coverage=0.973333 (10), idle_capture=0.856630 (10).

## resource-multi: scenario / seed 42

| Scenario | Precision | Recall | F1 | False idle | False active | Coverage | Idle capture | Mean detected latency ms | Censored |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| bursty | 1.000000 | 0.708333 | 0.829268 | 0.000000 | 0.291667 | 0.983333 | 0.708333 | 37000.000000 | 0 |
| cpu-background | 1.000000 | 0.666667 | 0.800000 | 0.000000 | 0.333333 | 1.000000 | 0.666667 | 40000.000000 | 0 |
| disk-wait | 1.000000 | 0.750000 | 0.857143 | 0.000000 | 0.250000 | 0.983333 | 0.750000 | 34000.000000 | 0 |
| editing-only | 0.352941 | 1.000000 | 0.521739 | 0.804878 | 0.000000 | 0.983333 | 1.000000 | 3000.000000 | 0 |
| low-use | 1.000000 | 0.666667 | 0.800000 | 0.000000 | 0.333333 | 0.983333 | 0.666667 | 41000.000000 | 0 |
| mixed | 1.000000 | 0.708333 | 0.829268 | 0.000000 | 0.291667 | 0.983333 | 0.708333 | 39000.000000 | 0 |
| network-wait | 0.410256 | 0.666667 | 0.507937 | 0.657143 | 0.333333 | 0.983333 | 0.666667 | 43000.000000 | 0 |
| pure-idle | 1.000000 | 0.962963 | 0.981132 | 0.000000 | 0.037037 | 1.000000 | 0.962963 | 10000.000000 | 0 |
| reconnect | 0.470588 | 1.000000 | 0.640000 | 0.771429 | 0.000000 | 0.983333 | 1.000000 | 2000.000000 | 0 |
| signal-loss | 0.962963 | 0.619048 | 0.753623 | 0.111111 | 0.380952 | 0.850000 | 0.520000 | 1000.000000 | 0 |

Equal-scenario macro (contributing groups): precision=0.819675 (10), recall=0.774868 (10), f1=0.752011 (10), false_idle_rate=0.234456 (10), false_active_rate=0.225132 (10), coverage=0.973333 (10), idle_capture=0.764963 (10).

## interaction-aware: scenario / seed 42

| Scenario | Precision | Recall | F1 | False idle | False active | Coverage | Idle capture | Mean detected latency ms | Censored |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| bursty | 1.000000 | 0.708333 | 0.829268 | 0.000000 | 0.291667 | 0.983333 | 0.708333 | 37000.000000 | 0 |
| cpu-background | 1.000000 | 0.666667 | 0.800000 | 0.000000 | 0.333333 | 1.000000 | 0.666667 | 40000.000000 | 0 |
| disk-wait | 1.000000 | 0.750000 | 0.857143 | 0.000000 | 0.250000 | 0.983333 | 0.750000 | 34000.000000 | 0 |
| editing-only | 1.000000 | 0.888889 | 0.941176 | 0.000000 | 0.111111 | 0.983333 | 0.888889 | 13000.000000 | 0 |
| low-use | 1.000000 | 0.666667 | 0.800000 | 0.000000 | 0.333333 | 0.983333 | 0.666667 | 41000.000000 | 0 |
| mixed | 1.000000 | 0.708333 | 0.829268 | 0.000000 | 0.291667 | 0.983333 | 0.708333 | 39000.000000 | 0 |
| network-wait | 0.410256 | 0.666667 | 0.507937 | 0.657143 | 0.333333 | 0.983333 | 0.666667 | 43000.000000 | 0 |
| pure-idle | 1.000000 | 0.962963 | 0.981132 | 0.000000 | 0.037037 | 1.000000 | 0.962963 | 10000.000000 | 0 |
| reconnect | 1.000000 | 0.833333 | 0.909091 | 0.000000 | 0.166667 | 0.983333 | 0.833333 | 12000.000000 | 0 |
| signal-loss | 1.000000 | 0.406250 | 0.577778 | 0.000000 | 0.593750 | 0.683333 | 0.260000 | 186000.000000 | 0 |

Equal-scenario macro (contributing groups): precision=0.941026 (10), recall=0.725810 (10), f1=0.803279 (10), false_idle_rate=0.065714 (10), false_active_rate=0.274190 (10), coverage=0.956667 (10), idle_capture=0.711185 (10).

Counts, all numerators/denominators, per-interval latency, seed groups, hashes and effective configuration are in metrics.json.
