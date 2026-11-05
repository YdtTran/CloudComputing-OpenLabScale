# Spec Delta

## Purpose

Provide reproducible synthetic user-session and workload datasets with separate observations and evaluation labels for OpenLab-Scale experiments.

## ADDED Requirements

### Requirement: Versioned experimental bundle
The system SHALL export a versioned manifest, sessions, scheduled events, workload phases, observations, and evaluator-only truth. The manifest SHALL identify seed, generator version, timing, resource bounds, provenance, and file checksums. Scenario inputs and truth MUST be excluded from detector input.

#### Scenario: Inspect a generated bundle
- **WHEN** a user generates a bundle
- **THEN** its manifest identifies every file and the observation source as synthetic
- **AND** each observation joins unambiguously to one session and container instance

### Requirement: Deterministic generation and scaling
Generation SHALL reproduce identical content for identical generator version, configuration, and seed. Session count SHALL be configurable with stable per-session seeds. Existing outputs MUST NOT be overwritten without explicit overwrite selection.

#### Scenario: Repeat and expand a run
- **WHEN** the same configuration and seed are generated twice and then expanded to additional sessions
- **THEN** both original outputs match byte for byte and the original sessions retain their schedules in the expanded bundle

### Requirement: Independent interaction and workload schedules
Each session SHALL support connection, editing, execution, intentional disconnect, reconnect, and abandonment schedules independently of workload phases. Disconnect SHALL NOT end a job. Lost interaction reporting SHALL be distinguishable from an observed intentional disconnect. Connected status alone MUST NOT imply user activity.

#### Scenario: Disconnected background job
- **WHEN** a client disconnects before its scheduled job finishes
- **THEN** workload activity continues until job completion and the interval is labeled as requiring retention

#### Scenario: Editing without resource activity
- **WHEN** a client sends editing interactions while application resources remain quiet
- **THEN** observations contain those interactions and truth labels the recent-interaction interval as requiring retention

### Requirement: Scenario coverage
The default suite SHALL contain CPU-steady, disk-I/O-heavy, network-wait, bursty, low-utilization-active, pure-idle, and mixed workload families. It SHALL also cover editing-only, connected-abandoned, long-job-disconnect, reconnect, and missing interaction or resource observations. Each case SHALL include a documented expected retention timeline.

#### Scenario: Generate the default suite
- **WHEN** the user selects the default suite
- **THEN** the bundle contains every required workload family and interaction case, including both retain and idle-eligible intervals

### Requirement: Explicit time and missingness
Time SHALL use integer elapsed milliseconds from a shared run origin with half-open intervals. Five-second resource windows SHALL identify their actual end, including partial final windows. Missing values SHALL remain unknown rather than becoming zero. Health, source, and observation availability times SHALL be explicit.

#### Scenario: Delayed partial observation
- **WHEN** a final resource window is shorter than five seconds and arrives late with a missing counter
- **THEN** its bounds and availability preserve that delay and the counter remains missing

### Requirement: Ground-truth isolation and provenance
Truth SHALL distinguish interaction, workload, connection, and retention eligibility, including UNKNOWN. Synthetic labels SHALL derive from scenario execution semantics independently of generated metric values. Future measured bundles SHALL use actual execution acknowledgements and identify execution failures or gaps as unknown rather than copying planned success.

#### Scenario: Missing execution acknowledgement
- **WHEN** a measured job start cannot be confirmed
- **THEN** the affected workload truth is UNKNOWN and the plan is not treated as proof of execution

### Requirement: Dataset validation and legacy preservation
Validation SHALL reject unsupported versions, duplicate identities, broken references, invalid times, overlapping or uncovered truth intervals, impossible job lifecycles, negative counters, and provenance mismatches with actionable errors. Existing sample CSVs SHALL remain unchanged and SHALL NOT be silently converted.

#### Scenario: Reject an ambiguous legacy file
- **WHEN** abbreviated legacy timestamps are supplied as a versioned bundle without an explicit conversion
- **THEN** validation fails with a timing or schema explanation rather than guessing dates or durations
