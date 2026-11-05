# Offline policy evaluation

Synthetic model results are not real monitoring accuracy, reclamation savings, or host/eBPF overhead.

Source: synthetic; seed: 43 (development).
Configuration SHA-256: 2934d9eeb23384fd46526e8fa71da0036cc8aa2d02110f8209785e1c180d3816
Bundle manifest SHA-256: 8e6fe0a55c7c0b3d2aa7dd8ffa7fea06843d1088428cda8298cec2f79edc05dd

global 5000ms ticks, start < tick < end; half-open truth joins.
micro sums counts; macro equal scenario, undefined omitted with contributing count; latency mean over detected intervals only; undetected censored. Zero denominators: N/A.

| Policy | TP | FP | TN | FN | Unknown predictions | Unknown truth | Precision | Recall | F1 | Coverage | Idle capture | Undetected intervals |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| no-reclaim | 0 | 0 | 300 | 290 | 0 | 0 | N/A | 0.000000 | 0.000000 | 1.000000 | 0.000000 | 11 |
| interaction-timeout | 272 | 144 | 156 | 8 | 10 | 0 | 0.653846 | 0.971429 | 0.781609 | 0.983051 | 0.937931 | 0 |
| cpu-only | 242 | 151 | 149 | 41 | 7 | 0 | 0.615776 | 0.855124 | 0.715976 | 0.988136 | 0.834483 | 0 |
| resource-multi | 220 | 87 | 213 | 63 | 7 | 0 | 0.716612 | 0.777385 | 0.745763 | 0.988136 | 0.758621 | 0 |
| interaction-aware | 201 | 23 | 277 | 72 | 17 | 0 | 0.897321 | 0.736264 | 0.808853 | 0.971186 | 0.693103 | 0 |

## Formulas

- precision: `tp/(tp+fp)`
- recall: `tp/(tp+fn)`
- f1: `2*tp/(2*tp+fp+fn)`
- false_idle_rate: `fp/(fp+tn)`
- false_active_rate: `fn/(fn+tp)`
- coverage: `(tp+fp+tn+fn)/(tp+fp+tn+fn+abstain_eligible+abstain_retain)`
- idle_capture: `tp/(tp+fn+abstain_eligible)`

## no-reclaim: scenario / seed 43

| Scenario | Precision | Recall | F1 | False idle | False active | Coverage | Idle capture | Mean detected latency ms | Censored |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| bursty | N/A | 0.000000 | 0.000000 | 0.000000 | 1.000000 | 1.000000 | 0.000000 | N/A | 1 |
| cpu-background | N/A | 0.000000 | 0.000000 | 0.000000 | 1.000000 | 1.000000 | 0.000000 | N/A | 1 |
| disk-wait | N/A | 0.000000 | 0.000000 | 0.000000 | 1.000000 | 1.000000 | 0.000000 | N/A | 1 |
| editing-only | N/A | 0.000000 | 0.000000 | 0.000000 | 1.000000 | 1.000000 | 0.000000 | N/A | 1 |
| low-use | N/A | 0.000000 | 0.000000 | 0.000000 | 1.000000 | 1.000000 | 0.000000 | N/A | 1 |
| mixed | N/A | 0.000000 | 0.000000 | 0.000000 | 1.000000 | 1.000000 | 0.000000 | N/A | 1 |
| network-wait | N/A | 0.000000 | 0.000000 | 0.000000 | 1.000000 | 1.000000 | 0.000000 | N/A | 1 |
| pure-idle | N/A | 0.000000 | 0.000000 | 0.000000 | 1.000000 | 1.000000 | 0.000000 | N/A | 1 |
| reconnect | N/A | 0.000000 | 0.000000 | 0.000000 | 1.000000 | 1.000000 | 0.000000 | N/A | 2 |
| signal-loss | N/A | 0.000000 | 0.000000 | 0.000000 | 1.000000 | 1.000000 | 0.000000 | N/A | 1 |

Equal-scenario macro (contributing groups): precision=N/A (0), recall=0.000000 (10), f1=0.000000 (10), false_idle_rate=0.000000 (10), false_active_rate=1.000000 (10), coverage=1.000000 (10), idle_capture=0.000000 (10).

## interaction-timeout: scenario / seed 43

| Scenario | Precision | Recall | F1 | False idle | False active | Coverage | Idle capture | Mean detected latency ms | Censored |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| bursty | 0.500000 | 1.000000 | 0.666667 | 0.685714 | 0.000000 | 1.000000 | 1.000000 | 0.000000 | 0 |
| cpu-background | 0.500000 | 1.000000 | 0.666667 | 0.685714 | 0.000000 | 1.000000 | 1.000000 | 0.000000 | 0 |
| disk-wait | 0.500000 | 1.000000 | 0.666667 | 0.685714 | 0.000000 | 1.000000 | 1.000000 | 0.000000 | 0 |
| editing-only | 1.000000 | 0.888889 | 0.941176 | 0.000000 | 0.111111 | 1.000000 | 0.888889 | 10000.000000 | 0 |
| low-use | 0.500000 | 1.000000 | 0.666667 | 0.685714 | 0.000000 | 1.000000 | 1.000000 | 0.000000 | 0 |
| mixed | 0.500000 | 1.000000 | 0.666667 | 0.685714 | 0.000000 | 1.000000 | 1.000000 | 0.000000 | 0 |
| network-wait | 0.500000 | 1.000000 | 0.666667 | 0.685714 | 0.000000 | 1.000000 | 1.000000 | 0.000000 | 0 |
| pure-idle | 1.000000 | 0.962963 | 0.981132 | 0.000000 | 0.037037 | 1.000000 | 0.962963 | 10000.000000 | 0 |
| reconnect | 1.000000 | 0.833333 | 0.909091 | 0.000000 | 0.166667 | 1.000000 | 0.833333 | 10000.000000 | 0 |
| signal-loss | 1.000000 | 1.000000 | 1.000000 | 0.000000 | 0.000000 | 0.830508 | 0.800000 | 50000.000000 | 0 |

Equal-scenario macro (contributing groups): precision=0.700000 (10), recall=0.968519 (10), f1=0.783140 (10), false_idle_rate=0.411429 (10), false_active_rate=0.031481 (10), coverage=0.983051 (10), idle_capture=0.948519 (10).

## cpu-only: scenario / seed 43

| Scenario | Precision | Recall | F1 | False idle | False active | Coverage | Idle capture | Mean detected latency ms | Censored |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| bursty | 1.000000 | 0.708333 | 0.829268 | 0.000000 | 0.291667 | 1.000000 | 0.708333 | 35000.000000 | 0 |
| cpu-background | 1.000000 | 0.666667 | 0.800000 | 0.000000 | 0.333333 | 1.000000 | 0.666667 | 40000.000000 | 0 |
| disk-wait | 0.461538 | 1.000000 | 0.631579 | 0.800000 | 0.000000 | 1.000000 | 1.000000 | 0.000000 | 0 |
| editing-only | 0.346154 | 1.000000 | 0.514286 | 0.829268 | 0.000000 | 1.000000 | 1.000000 | 0.000000 | 0 |
| low-use | 0.461538 | 1.000000 | 0.631579 | 0.800000 | 0.000000 | 1.000000 | 1.000000 | 0.000000 | 0 |
| mixed | 0.850000 | 0.708333 | 0.772727 | 0.085714 | 0.291667 | 1.000000 | 0.708333 | 35000.000000 | 0 |
| network-wait | 0.461538 | 1.000000 | 0.631579 | 0.800000 | 0.000000 | 1.000000 | 1.000000 | 0.000000 | 0 |
| pure-idle | 1.000000 | 0.962963 | 0.981132 | 0.000000 | 0.037037 | 1.000000 | 0.962963 | 10000.000000 | 0 |
| reconnect | 0.461538 | 1.000000 | 0.631579 | 0.800000 | 0.000000 | 1.000000 | 1.000000 | 0.000000 | 0 |
| signal-loss | 0.928571 | 0.604651 | 0.732394 | 0.222222 | 0.395349 | 0.881356 | 0.520000 | 0.000000 | 0 |

Equal-scenario macro (contributing groups): precision=0.697088 (10), recall=0.865095 (10), f1=0.715612 (10), false_idle_rate=0.433720 (10), false_active_rate=0.134905 (10), coverage=0.988136 (10), idle_capture=0.856630 (10).

## resource-multi: scenario / seed 43

| Scenario | Precision | Recall | F1 | False idle | False active | Coverage | Idle capture | Mean detected latency ms | Censored |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| bursty | 1.000000 | 0.708333 | 0.829268 | 0.000000 | 0.291667 | 1.000000 | 0.708333 | 35000.000000 | 0 |
| cpu-background | 1.000000 | 0.666667 | 0.800000 | 0.000000 | 0.333333 | 1.000000 | 0.666667 | 40000.000000 | 0 |
| disk-wait | 1.000000 | 0.750000 | 0.857143 | 0.000000 | 0.250000 | 1.000000 | 0.750000 | 30000.000000 | 0 |
| editing-only | 0.346154 | 1.000000 | 0.514286 | 0.829268 | 0.000000 | 1.000000 | 1.000000 | 0.000000 | 0 |
| low-use | 1.000000 | 0.666667 | 0.800000 | 0.000000 | 0.333333 | 1.000000 | 0.666667 | 40000.000000 | 0 |
| mixed | 1.000000 | 0.708333 | 0.829268 | 0.000000 | 0.291667 | 1.000000 | 0.708333 | 35000.000000 | 0 |
| network-wait | 0.410256 | 0.666667 | 0.507937 | 0.657143 | 0.333333 | 1.000000 | 0.666667 | 40000.000000 | 0 |
| pure-idle | 1.000000 | 0.962963 | 0.981132 | 0.000000 | 0.037037 | 1.000000 | 0.962963 | 10000.000000 | 0 |
| reconnect | 0.461538 | 1.000000 | 0.631579 | 0.800000 | 0.000000 | 1.000000 | 1.000000 | 0.000000 | 0 |
| signal-loss | 0.928571 | 0.604651 | 0.732394 | 0.222222 | 0.395349 | 0.881356 | 0.520000 | 0.000000 | 0 |

Equal-scenario macro (contributing groups): precision=0.814652 (10), recall=0.773428 (10), f1=0.748301 (10), false_idle_rate=0.250863 (10), false_active_rate=0.226572 (10), coverage=0.988136 (10), idle_capture=0.764963 (10).

## interaction-aware: scenario / seed 43

| Scenario | Precision | Recall | F1 | False idle | False active | Coverage | Idle capture | Mean detected latency ms | Censored |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| bursty | 1.000000 | 0.708333 | 0.829268 | 0.000000 | 0.291667 | 1.000000 | 0.708333 | 35000.000000 | 0 |
| cpu-background | 1.000000 | 0.666667 | 0.800000 | 0.000000 | 0.333333 | 1.000000 | 0.666667 | 40000.000000 | 0 |
| disk-wait | 1.000000 | 0.750000 | 0.857143 | 0.000000 | 0.250000 | 1.000000 | 0.750000 | 30000.000000 | 0 |
| editing-only | 1.000000 | 0.888889 | 0.941176 | 0.000000 | 0.111111 | 1.000000 | 0.888889 | 10000.000000 | 0 |
| low-use | 1.000000 | 0.666667 | 0.800000 | 0.000000 | 0.333333 | 1.000000 | 0.666667 | 40000.000000 | 0 |
| mixed | 1.000000 | 0.708333 | 0.829268 | 0.000000 | 0.291667 | 1.000000 | 0.708333 | 35000.000000 | 0 |
| network-wait | 0.410256 | 0.666667 | 0.507937 | 0.657143 | 0.333333 | 1.000000 | 0.666667 | 40000.000000 | 0 |
| pure-idle | 1.000000 | 0.962963 | 0.981132 | 0.000000 | 0.037037 | 1.000000 | 0.962963 | 10000.000000 | 0 |
| reconnect | 1.000000 | 0.833333 | 0.909091 | 0.000000 | 0.166667 | 1.000000 | 0.833333 | 10000.000000 | 0 |
| signal-loss | 1.000000 | 0.393939 | 0.565217 | 0.000000 | 0.606061 | 0.711864 | 0.260000 | 185000.000000 | 0 |

Equal-scenario macro (contributing groups): precision=0.941026 (10), recall=0.724579 (10), f1=0.802023 (10), false_idle_rate=0.065714 (10), false_active_rate=0.275421 (10), coverage=0.971186 (10), idle_capture=0.711185 (10).

Counts, all numerators/denominators, per-interval latency, seed groups, hashes and effective configuration are in metrics.json.
