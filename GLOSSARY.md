# OpenLab-Scale

The domain of host-level kernel observability, quantitative container telemetry, and safe human-approved idle container reclamation.

## Language

**Session**:
A bounded lifecycle execution of an interactive or detached container workspace identified by a unique session identifier.
_Avoid_: Workspace, instance, job container

**Phase**:
A distinct temporal workload interval inside a session representing an active computation, an idle gap, or an interactive period.
_Avoid_: State, stage, sub-task

**Observation Window**:
A discretized interval of quantitative resource metrics and kernel event counts aggregated over a fixed duration (5000ms) with provenance tracking.
_Avoid_: Metric bucket, sample slice, time slice

**Causal Gate**:
The strict enforcement boundary ensuring policy decisions evaluate only telemetry that occurred and arrived before decision time, without future knowledge.
_Avoid_: Lookahead filter, causality filter

**Truth Acknowledgement**:
The definitive ground-truth status of a container determined by execution lifecycle signals, strictly isolated from policy evaluation.
_Avoid_: Ground truth label, actual status

**Idle Candidate**:
An observational recommendation emitted by a policy proposing a container for administrative reclamation review.
_Avoid_: Reclaim target, kill order, termination candidate

**Reclamation Policy**:
A deterministic decision function that consumes causally projected observation windows to emit either retain, idle candidate, or abstention recommendations.
_Avoid_: Reclaim algorithm, eviction strategy

**Degraded Telemetry**:
An observation window where required resource counters or tracepoint streams are uncollected, null, or corrupted, mandating policy abstention.
_Avoid_: Incomplete data, partial metrics, missing window
