# Offline policy evaluation

Partial measured collection: sched:sched_process_exec covers exec only; I/O, socket, disk and network counters are uncollected/null. All resource windows are DEGRADED. Multi-signal policies abstain. These two sessions do not establish real-world accuracy or monitoring overhead; synthetic and measured scores are never pooled. Ubuntu and full workloads are deferred.

Source: measured; seed: 42 (development).
Configuration SHA-256: 2934d9eeb23384fd46526e8fa71da0036cc8aa2d02110f8209785e1c180d3816
Bundle manifest SHA-256: 6e18cdf558d06c128d8e82929a9a1677299ed93e02572486dbcf0734a9f9a440

global 5000ms ticks, start < tick < end; half-open truth joins.
micro sums counts; macro equal scenario, undefined omitted with contributing count; latency mean over detected intervals only; undetected censored. Zero denominators: N/A.

| Policy | TP | FP | TN | FN | Unknown predictions | Unknown truth | Precision | Recall | F1 | Coverage | Idle capture | Undetected intervals |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| no-reclaim | 0 | 0 | 41 | 79 | 0 | 0 | N/A | 0.000000 | 0.000000 | 1.000000 | 0.000000 | 2 |
| interaction-timeout | 77 | 24 | 17 | 2 | 0 | 0 | 0.762376 | 0.974684 | 0.855556 | 1.000000 | 0.974684 | 0 |
| cpu-only | 67 | 0 | 41 | 12 | 0 | 0 | 1.000000 | 0.848101 | 0.917808 | 1.000000 | 0.848101 | 0 |
| resource-multi | 0 | 0 | 0 | 0 | 120 | 0 | N/A | N/A | N/A | 0.000000 | 0.000000 | 2 |
| interaction-aware | 0 | 0 | 0 | 0 | 120 | 0 | N/A | N/A | N/A | 0.000000 | 0.000000 | 2 |

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
| cpu-background | N/A | 0.000000 | 0.000000 | 0.000000 | 1.000000 | 1.000000 | 0.000000 | N/A | 1 |
| pure-idle | N/A | 0.000000 | 0.000000 | 0.000000 | 1.000000 | 1.000000 | 0.000000 | N/A | 1 |

Equal-scenario macro (contributing groups): precision=N/A (0), recall=0.000000 (2), f1=0.000000 (2), false_idle_rate=0.000000 (2), false_active_rate=1.000000 (2), coverage=1.000000 (2), idle_capture=0.000000 (2).

## interaction-timeout: scenario / seed 42

| Scenario | Precision | Recall | F1 | False idle | False active | Coverage | Idle capture | Mean detected latency ms | Censored |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| cpu-background | 0.500000 | 1.000000 | 0.666667 | 0.666667 | 0.000000 | 1.000000 | 1.000000 | 4782.000000 | 0 |
| pure-idle | 1.000000 | 0.963636 | 0.981481 | 0.000000 | 0.036364 | 1.000000 | 0.963636 | 10000.000000 | 0 |

Equal-scenario macro (contributing groups): precision=0.750000 (2), recall=0.981818 (2), f1=0.824074 (2), false_idle_rate=0.333333 (2), false_active_rate=0.018182 (2), coverage=1.000000 (2), idle_capture=0.981818 (2).

## cpu-only: scenario / seed 42

| Scenario | Precision | Recall | F1 | False idle | False active | Coverage | Idle capture | Mean detected latency ms | Censored |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| cpu-background | 1.000000 | 0.625000 | 0.769231 | 0.000000 | 0.375000 | 1.000000 | 0.625000 | 49782.000000 | 0 |
| pure-idle | 1.000000 | 0.945455 | 0.971963 | 0.000000 | 0.054545 | 1.000000 | 0.945455 | 15000.000000 | 0 |

Equal-scenario macro (contributing groups): precision=1.000000 (2), recall=0.785227 (2), f1=0.870597 (2), false_idle_rate=0.000000 (2), false_active_rate=0.214773 (2), coverage=1.000000 (2), idle_capture=0.785227 (2).

## resource-multi: scenario / seed 42

| Scenario | Precision | Recall | F1 | False idle | False active | Coverage | Idle capture | Mean detected latency ms | Censored |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| cpu-background | N/A | N/A | N/A | N/A | N/A | 0.000000 | 0.000000 | N/A | 1 |
| pure-idle | N/A | N/A | N/A | N/A | N/A | 0.000000 | 0.000000 | N/A | 1 |

Equal-scenario macro (contributing groups): precision=N/A (0), recall=N/A (0), f1=N/A (0), false_idle_rate=N/A (0), false_active_rate=N/A (0), coverage=0.000000 (2), idle_capture=0.000000 (2).

## interaction-aware: scenario / seed 42

| Scenario | Precision | Recall | F1 | False idle | False active | Coverage | Idle capture | Mean detected latency ms | Censored |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| cpu-background | N/A | N/A | N/A | N/A | N/A | 0.000000 | 0.000000 | N/A | 1 |
| pure-idle | N/A | N/A | N/A | N/A | N/A | 0.000000 | 0.000000 | N/A | 1 |

Equal-scenario macro (contributing groups): precision=N/A (0), recall=N/A (0), f1=N/A (0), false_idle_rate=N/A (0), false_active_rate=N/A (0), coverage=0.000000 (2), idle_capture=0.000000 (2).

Counts, all numerators/denominators, per-interval latency, seed groups, hashes and effective configuration are in metrics.json.
