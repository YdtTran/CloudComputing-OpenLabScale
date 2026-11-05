# Spec Delta

## Purpose

Collect attributable host-kernel and cgroup measurements for selected workload containers while exposing unsupported signals and degraded observation quality.

## ADDED Requirements

### Requirement: Observable host readiness
The system SHALL check Docker access, cgroup v2, BTF, tracefs and collector permissions, and verify actual attachment of the selected process tracepoint before workloads execute. It SHALL record host/kernel, images, selected probe, capabilities and mounts. An attachment failure SHALL abort the measured experiment with diagnostics, without synthetic fallback or host permission changes.

#### Scenario: Probe attachment denied
- **WHEN** required kernel access is denied or the selected tracepoint cannot attach
- **THEN** preflight reports the failing prerequisite and the measured experiment does not start workloads

### Requirement: Separate collector privileges
Build and collection tools SHALL be packaged separately from workload containers. Collector host access SHALL be explicitly documented and limited to what collection requires; workload containers SHALL NOT inherit those permissions. Collection SHALL NOT use Docker resource statistics as activity features.

#### Scenario: Inspect deployment permissions
- **WHEN** the operator inspects the deployment configuration
- **THEN** collector capabilities and mounts are explicit, workloads remain unprivileged, and no runtime Docker socket is exposed to the collector

### Requirement: Measured cgroup and process evidence
The collector SHALL measure quota-normalized CPU, memory bytes and events from one process tracepoint for the two selected containers. Process events SHALL carry monotonic timestamp, PID/TGID and cgroup identity. Event transport failures SHALL be counted; unavailable loss accounting SHALL remain unknown rather than zero.

#### Scenario: Observe an acknowledged CPU job
- **WHEN** a CPU job starts after the collector is ready
- **THEN** raw evidence records attributable process events and real cgroup samples with source labels
- **AND** CPU normalization uses actual quota and measured elapsed time

### Requirement: Instance attribution and invalidation
Telemetry SHALL map selected cgroup identities to full Docker IDs and lifecycle metadata. Mapping changes or ambiguous identity SHALL invalidate attribution and reset resource baselines; old-instance events SHALL NOT be relabeled as belonging to a replacement. Docker metadata SHALL be used only for identity, limits and lifecycle, never as activity evidence.

#### Scenario: Container restarts during collection
- **WHEN** lifecycle metadata changes for a selected container
- **THEN** affected windows are marked invalid or missing, the experiment aborts with diagnostics, and the replacement is not joined to the old instance

### Requirement: Causal five-second windows
The exporter SHALL use one host monotonic origin and nonoverlapping resource windows of at most five seconds. Each window SHALL carry actual bounds and availability time. Delivered-late events SHALL NOT retroactively create evidence available to earlier decisions. Missing samples, failed mappings and positive loss SHALL be represented explicitly.

#### Scenario: Delayed or partial window
- **WHEN** a resource window ends early or its measurements arrive late
- **THEN** exported bounds preserve its actual duration and availability is no earlier than delivery
- **AND** prediction cannot consume the window before its availability time

### Requirement: Honest partial coverage
Uncollected I/O/socket events and disk/network counters SHALL be null in the existing measured resource payload; no synthetic values or assumed zeros SHALL fill them. Incomplete windows SHALL be DEGRADED or UNHEALTHY. Reports SHALL identify the selected probe and omitted signals and SHALL NOT claim full process-event coverage, real-world detector accuracy or monitoring overhead results.

#### Scenario: Multi-signal policy lacks required counters
- **WHEN** the first-slice measured bundle is evaluated by resource-multi or interaction-aware
- **THEN** missing required counters produce UNKNOWN predictions and reported abstentions
- **AND** validation accepts the explicitly incomplete payload without changing the existing schema
