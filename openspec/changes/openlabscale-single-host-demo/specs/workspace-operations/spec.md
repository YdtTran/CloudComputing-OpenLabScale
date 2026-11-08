## Purpose

Make the demo observable and reproducible using real telemetry, bounded load and documented host setup.

## ADDED Requirements

### Requirement: Administrator telemetry
The service SHALL expose queue state, lifecycle counts, configured and reserved capacity, and sampled host and owned-container CPU and memory to authorized administrators.

#### Scenario: Metric collection fails
- **WHEN** a counter is unavailable or its sample has expired
- **THEN** the dashboard identifies it as unavailable or stale with the applicable sample timestamp

### Requirement: Reproducible concurrent request evidence
The load workflow SHALL support a 5–10 client smoke run and 100 concurrent submissions with bounded wait and execution, collecting measured timing, outcomes and peak running count as CSV and JSON.

#### Scenario: Load exceeds running capacity
- **WHEN** the 100-client run queues requests under a lower running cap
- **THEN** the results report submitted requests separately from peak running containers and include timing, failure and timeout outcomes

### Requirement: Reproducible host deployment
The demo SHALL document setup, restricted access, verification, teardown, and cost considerations for local Linux and single-host EC2.

#### Scenario: Operator completes a demonstration
- **WHEN** the operator follows the deployment and teardown procedure
- **THEN** the student and administrator flows can be verified and demo-owned resources can be cleaned up
