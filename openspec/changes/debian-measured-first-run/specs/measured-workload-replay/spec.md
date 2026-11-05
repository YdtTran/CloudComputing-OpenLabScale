# Spec Delta

## Purpose

Execute selected reproducible workload schedules in real containers and produce measured experimental bundles whose truth follows actual execution evidence.

## ADDED Requirements

### Requirement: Replay selected existing schedules
The system SHALL select exactly one cpu-background and one pure-idle session from a validated synthetic bundle and replay their events and CPU/IDLE phases. It SHALL preserve seed, schedule and parameter provenance, exclude synthetic observations and truth from measured outputs, and reject unsupported selections before launching workloads.

#### Scenario: Select the two supported scenarios
- **WHEN** a valid bundle contains the two supported scenarios and other workload families
- **THEN** only the selected two sessions are launched and the source bundle remains unchanged
- **AND** the run records the source bundle hashes and selected identities

#### Scenario: Reject an unsupported workload
- **WHEN** a selected session contains an unsupported phase or invalid replay parameter
- **THEN** replay fails before any workload starts with an actionable error

### Requirement: Bounded and isolated execution
Workloads SHALL run with enforced CPU, memory and duration limits and without collector privileges or host monitoring mounts. Disconnect SHALL NOT cancel an executing job. CPU duty SHALL be interpreted relative to the configured quota; declared memory demand SHALL be bounded by the container limit.

#### Scenario: Background CPU after disconnect
- **WHEN** the CPU-background session disconnects during acknowledged execution
- **THEN** the job continues until actual completion, failure or its enforced deadline
- **AND** resource limits remain in effect

### Requirement: Actual lifecycle evidence
The system SHALL record actual requests, job start and terminal acknowledgements on one run-relative monotonic timeline. Successful actual start/completion intervals SHALL establish ACTIVE truth, including runtime timing deviations. Failed or unconfirmed execution SHALL remain UNKNOWN over the affected interval. Planned completion SHALL NOT establish measured success.

#### Scenario: Completion differs from plan
- **WHEN** a CPU job completes later than its scheduled phase end
- **THEN** measured truth follows the acknowledged interval and does not switch to IDLE at the planned end

#### Scenario: Missing completion
- **WHEN** execution has no confirmed terminal acknowledgement
- **THEN** affected workload truth is UNKNOWN through observation end, rather than inferred successful completion

### Requirement: Independent measured export and evaluation
The system SHALL export the existing versioned tables with measured provenance, fresh run/instance identities and checksums. Truth SHALL derive only from actual lifecycle and executed interaction records, retaining the existing 30-second eligibility grace. Policies SHALL receive only the existing allowlisted detector inputs. Predictions SHALL be finalized before scoring opens truth.

#### Scenario: Evaluate a measured run
- **WHEN** a completed run is exported
- **THEN** the bundle passes the existing validator and separate prediction and scoring commands
- **AND** results identify measured mode, source limitations, coverage and abstentions

#### Scenario: Labels do not influence predictions
- **WHEN** evaluator-only truth changes without changing detector inputs
- **THEN** predictions remain unchanged

### Requirement: Owned cleanup and output preservation
The system SHALL clean up only containers and temporary resources created by the run after success, failure or interruption. Cleanup SHALL be independent of policy recommendations. Existing source bundles and nonempty destination directories SHALL NOT be overwritten; partial outputs SHALL be identifiable as incomplete and SHALL NOT be presented as successful runs.

#### Scenario: Interrupted experiment
- **WHEN** the operator interrupts an active run
- **THEN** owned workloads and collector are stopped with bounded cleanup and unrelated containers remain untouched
- **AND** retained diagnostics identify the interruption and any cleanup failure
