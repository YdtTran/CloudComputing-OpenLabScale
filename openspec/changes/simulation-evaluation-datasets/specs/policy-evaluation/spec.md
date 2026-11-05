# Spec Delta

## Purpose

Compare inactivity policies fairly using identical observations and independently scored retention labels, including missing evidence and uncertainty.

## ADDED Requirements

### Requirement: Comparable policies and recorded configuration
The evaluator SHALL run fixed interaction timeout, CPU-only, resource multi-signal, and interaction-aware multi-signal policies on the same observation timeline. It SHALL record thresholds, grace periods, policy versions, and input identity. A no-reclaim reference SHALL always retain containers. Evaluation MUST NOT perform container control.

#### Scenario: Compare a disconnected job
- **WHEN** all policies evaluate a session containing a disconnected background job
- **THEN** each policy produces its own timestamped decision and evidence using the same observations without stopping the job

### Requirement: Causal observation access
Policies SHALL receive only an allowlisted observation projection available by decision time and opaque instance identity. They MUST NOT read scenario names, future events, planned durations, workload commands, or truth. Predictions SHALL be completed before the scorer reads truth.

#### Scenario: Labels change without observations changing
- **WHEN** truth and planned schedules are altered while observation inputs and policy configuration stay fixed
- **THEN** policy predictions remain identical

### Requirement: Explicit unknown and freshness behavior
Policies SHALL output RETAIN, IDLE_CANDIDATE, or UNKNOWN with evidence. Missing or stale required signals SHALL produce UNKNOWN and reset quiet timers. Interaction-aware evaluation SHALL distinguish intentional disconnect from lost reporting, protect recent interaction and active jobs, and require healthy quiet evidence before proposing reclamation.

#### Scenario: Interaction reporting fails
- **WHEN** resource observations remain quiet but the interaction reporting channel becomes unhealthy
- **THEN** the interaction-aware policy returns UNKNOWN and requires a new complete quiet period after recovery

### Requirement: Independent eligibility scoring
The scorer SHALL compare decisions with independent RETAIN, IDLE_ELIGIBLE, or UNKNOWN truth at five-second decision points. UNKNOWN truth SHALL be excluded and counted. Prediction abstentions SHALL be reported separately from classification errors, with coverage and denominators. Interval joins SHALL use half-open bounds without future observations.

#### Scenario: Unknown evidence is not success
- **WHEN** a policy predicts UNKNOWN for every known-truth decision point
- **THEN** its coverage is zero, its abstentions are counted, and undefined precision or recall is reported as null rather than perfect accuracy

### Requirement: Reproducible reports
Reports SHALL include confusion counts, idle precision/recall/F1, false-idle and false-active rates, eligibility detection latency, coverage, and excluded counts per policy, scenario, seed, and overall. They SHALL state formulas, aggregation weights, timing, and provenance. Synthetic results MUST NOT be presented as real monitoring accuracy, reclamation savings, or overhead.

#### Scenario: Policy never discovers eligible idle
- **WHEN** an eligible interval ends without an idle-candidate decision
- **THEN** the report records an undetected interval rather than assigning zero latency

#### Scenario: Reproduce an evaluation
- **WHEN** the same bundle and policy configuration are evaluated twice
- **THEN** prediction and score content matches, including null metrics and excluded counts
