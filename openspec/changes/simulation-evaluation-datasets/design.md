# Design

## Context

See proposal.md for motivation. The project currently contains a five-page assignment PDF and four CSV samples, not an executable simulation system. Inspection found 38 sessions, 502 events, 3,665 metric rows, and 440 truth intervals. Actual timestamps are abbreviated minute/second strings, while the README describes complete dates. Existing traces have unknown durations and UNKNOWN intervals that must not be interpreted as inactivity.

Design is needed because this introduces a data model shared by generation, future replay/collection, and evaluation. Initial users are simulated clients; execution starts locally, with future single-host EC2 load experiments.

## Goals / Non-Goals

**Goals:** A human-readable, small dataset with enough detail to reproduce interaction/resource corner cases and compare policies without labels leaking into predictions. The contract must accommodate real observations later without changing time or identity semantics.

**Non-Goals:** This change does not execute Docker workloads or collect kernel events. It generates executable schedules and modeled observations for offline development. It does not validate eBPF effectiveness, implement distributed orchestration, estimate actual savings, or enforce reclamation. Those require later implementation and measured experiments.

## Decisions

### 1. Use JSON configuration and manifest, CSV tables, Python standard library

Proposed implementation: a `simulation/` Python package with `generate`, `validate`, and `evaluate` subcommands; documentation and small example outputs under `data/simulation-v1/`. JSON avoids adding a YAML dependency; CSV stays compatible with existing data and spreadsheet inspection. A database or notebook-only workflow would complicate replay and automated checking.

The bundle has these files. All table rows carry `run_id`; all session rows carry `session_id`. IDs are opaque and never encode scenario labels. CSV empty numeric cells mean missing, never zero. Enumerations and JSON parameter objects are documented in a field dictionary.

| File | Minimum columns / content | Consumer |
|---|---|---|
| `manifest.json` | schema_version, generator_version, seed, effective config, run duration, sample_ms=5000, clock=elapsed_ms, origin_utc=null or explicit UTC, source_mode, file hashes, optional host metadata | Validator/evaluator; policies get only timing and source metadata |
| `sessions.csv` | session_id, user_id, container_instance_id, scenario_id, start_ms, end_ms, cpu_limit_cores, memory_limit_mb | Generator/replay/evaluator; policies get opaque identity and lifetime only |
| `events.csv` | event_id, session_id, at_ms, action, job_id (optional), parameters_json | Future simulated clients; never detector input |
| `phases.csv` | phase_id, session_id, job_id (optional), start_ms, end_ms, workload, parameters_json | Future workload runner; never detector input |
| `observations.csv` | session_id, container_instance_id, kind, at_ms, available_at_ms, window_start_ms/end_ms (resource only), source, status, payload_json | Detector input |
| `truth.csv` | session_id, start_ms, end_ms, interaction, connection, workload, eligibility, reason, label_source | Scorer only |

`observations.kind` is interaction, connection, interaction_health, or resource. Interaction payload holds action only (EDIT, EXECUTE_REQUEST, CONNECT, DISCONNECT, RECONNECT, LOGOUT); execution requests omit command parameters and planned duration. A server acknowledgement or independently healthy session service supplies intentional disconnect observations. A disconnected client is not expected to send heartbeats. Interaction health describes the reporting service, not whether a user remains connected. Resource payload contains CPU percent of configured quota, memory bytes, disk/network byte deltas, process/I/O/socket event counts, loss count, and mapping validity; provenance is explicit per group (`synthetic_cgroup_v2`, `synthetic_ebpf`, or real equivalents). Missing groups have null fields and degraded status. Counts are evidence of activity, not proof of useful work.

All elapsed times are integer milliseconds from one coordinator origin; intervals are `[start_ms,end_ms)`. Decisions occur at 5,000 ms increments after origin, excluding session end. A resource window becomes available only at/after its end. Point events are available at/after occurrence. Final short windows are retained but not extended to five seconds. Future same-host runners map host monotonic timestamps to this origin and record UTC only for display; a restart creates a new container instance ID.

### 2. Generate two independent timelines per session

Configuration describes user events and workload phases separately. Actions include CONNECT, EDIT, EXECUTE, DISCONNECT, RECONNECT, LOGOUT; abandonment means no further user events, not an observable ABANDON event. Workloads are CPU, DISK_IO, NETWORK_WAIT, BURST, LOW_CPU, IDLE, or MIXED (expanded into concrete phases). Job-linked EXECUTE events reference matching phase groups. Execution error, interrupt, and completion outcomes are explicit lifecycle events where needed. Disconnect never cancels a job.

Workload parameters include bounded CPU duty cycle, memory bytes, disk file size/rate, network bytes and response delay, and burst width/period. Network waits assume an eventual controlled peer in the future runner; no public endpoints. A validation contract requires execution adapters to enforce resource and duration limits later.

The default suite uses seed 42, ten independent 300-second sessions, sample interval 5 seconds, and declared future limits of 0.5 CPU / 256 MiB per container. This generates roughly 600 resource rows, not ten containers launched by this change. Single-host scale profiles select session counts and start offsets; actual concurrency is future runner configuration.

| Case | User behavior | Workload / point of comparison |
|---|---|---|
| cpu-background | Execute at 20s, disconnect at 40s | CPU job 20–180s; retain after disconnect |
| disk-wait | Execute then stop interacting | Disk job with low-CPU waits 20–180s |
| network-wait | Execute then disconnect | Waiting network job 20–180s; delay is not idle |
| bursty | Execute a long burst sequence | 200ms pulses every 10s during 20–180s |
| low-use | Execute then stop interacting | Useful low-duty job 20–180s |
| pure-idle | Connect at 0s; remain connected without edits | No job; eventual idle eligibility |
| mixed | Edit, execute, later abandon | CPU, disk wait, burst, then true quiet |
| editing-only | Edit every 10s through 180s | Resources quiet; recent interaction protects session |
| reconnect | Edit, disconnect at 40s, reconnect at 90s and edit through 180s | Quiet resources; explicit connection transitions |
| signal-loss | Stop editing at 20s | Quiet; interaction reporting outage 50–100s, resource outage 150–175s, delayed window and excessive-loss window |

Exact nonlisted timings are fixed in the checked-in templates. Every case includes sufficient trailing quiet for a candidate after recovery. Additional seeds jitter bounded start times and amplitudes while preserving scenario assertions. Per-session streams derive from SHA-256 of seed + template ID + repetition index + generator version, rather than process-randomized hashes; appending sessions does not alter earlier sessions. Resource-noise and schedule streams are separate. Stable IDs, key/row order, float formatting, and no generation wall-clock timestamp make repeated bundles byte-identical. Do not allow blind output overwrite.

### 3. Generate truth from behavior, not from metrics or policies

Truth partitions every session into nonoverlapping complete intervals. Interaction is RECENT, ABSENT, or UNKNOWN; connection is CONNECTED, DISCONNECTED, or UNKNOWN; workload is ACTIVE, IDLE, or UNKNOWN. Memory occupancy alone does not establish active work. An explicit idle phase has no application job; waiting inside a known unfinished job remains ACTIVE. Observation outages affect policy certainty, not omniscient synthetic truth.

Eligibility is RETAIN if any job is unfinished or user interaction is recent; UNKNOWN if neither retention nor inactivity can be established; otherwise IDLE_ELIGIBLE. The dataset's interaction recency definition is fixed at 30 seconds, stored in the manifest, and remains fixed during policy threshold sweeps. A successful job request counts as interaction; connects/reconnects also reset recency. Eligibility begins when these semantics hold, independent of a policy's additional grace/hysteresis. An idle candidate still requires approval in the later real controller.

Offline truth uses `label_source=synthetic_scenario`; observation models add bounded noise, delayed deliveries, missing records, and event loss separately. Real bundles later require `label_source=execution_ack` and actual start/end records; failed/unconfirmed execution is UNKNOWN. Synthetic and measured modes cannot be merged into one score group. Model limitations are displayed in every report. Legacy JuNE traces stay separate: they are not strong truth for silent intervals.

### 4. Evaluate policies causally with one compact interface

Policies receive opaque identity, elapsed decision time, resource limits, and only allowlisted observations with `available_at_ms <= decision_ms`. They cannot read session scenarios, phase plans, job durations, truth, or future events. Prediction files are finalized before a separate scoring stage opens truth. Each prediction contains policy/version/config hash, run/session/instance, decision_ms, decision, and reason codes. Config and bundle hashes accompany reports.

Default policy definitions are deliberately simple and configurable; they are experiments, not performance claims:

- **No-reclaim reference:** RETAIN at every tick; report idle opportunities it misses.
- **Fixed interaction timeout:** candidate after 40 seconds without observed user interaction, ignoring resource activity. Unknown/stale interaction service health yields UNKNOWN. This explicitly defines the timeout baseline rather than implying a fixed absolute session lifetime.
- **CPU-only:** resource candidate after CPU stays below 1% of quota for 30 seconds plus 10 seconds hysteresis; ignores interaction and other counters.
- **Resource multi-signal:** candidate only when CPU is below threshold and process/I/O/socket counts and disk/network deltas are zero for 30+10 seconds. Does not consume interaction evidence.
- **Interaction-aware multi-signal:** same resource checks plus no user interaction within 30 seconds and healthy interaction reporting. Fresh interaction resets quiet timing; connected-but-abandoned can qualify. Explicitly disconnected does not protect an idle session or cancel background work.

For resource policies, quiet evidence covers complete consecutive windows: 30 seconds quiet enters pending state, another 10 seconds quiet permits a candidate. Recent activity yields RETAIN. Required resource source age >10 seconds, missing fields, invalid mapping, or positive event loss produces UNKNOWN; interaction health age >10 seconds or unhealthy state produces UNKNOWN where required. Healthy interaction service heartbeats are modeled every five seconds independently of clients. Unknown resets the relevant quiet timer; a new valid window is needed to begin recovery. Resource multi-signal may miss a silent pending I/O wait, which is an intentional challenging case; synthetic outputs must not guarantee its superiority.

### 5. Score eligibility and expose abstention

At each five-second tick, use truth covering that instant; exclude UNKNOWN truth and count it. IDLE_ELIGIBLE is the positive class. On known truth and definite predictions: TP=candidate on eligible; FP=candidate on retain; TN=retain on retain; FN=retain on eligible. UNKNOWN predictions yield separate abstention counts by truth class.

- Precision = TP/(TP+FP); recall = TP/(TP+FN); F1 uses these definite-prediction counts.
- Conditional false-idle = FP/(FP+TN); false-active = FN/(FN+TP).
- Coverage = definite predictions / all known-truth ticks; expose overall idle capture = TP / all eligible ticks, including abstentions, to prevent selective coverage from hiding misses.
- Also report unsafe recommendation count, unknown-truth exclusions, unknown-prediction counts, and all denominators. A zero denominator produces JSON null and displayed N/A.
- Eligibility latency is time from each eligible interval start to its first candidate within that interval. Intervals without a candidate are undetected/censored and never assigned zero delay. Do not score interval starts at session end.
- Report micro counts and derived metrics overall and per scenario/seed; give equal-scenario macro metrics separately, ignoring undefined values with contributing-group counts. All policies use the identical timeline with no policy-driven truncation. No-reclaim is a retention reference, not a measured savings baseline.

Use tiny hand-calculated fixtures to validate boundary joins and arithmetic; do not assert that a chosen approach must win. Threshold tuning uses development seeds 42/43; report seed 44 as a held-out synthetic check, without presenting that as real-world generalization.

## Risks / Trade-offs

- Synthetic signals reflect modeling assumptions → publish parameter ranges and model provenance; require separate real-run evidence for conclusions about eBPF or overhead.
- Silence during waiting work is difficult to infer → include silent-wait intervals, expose false-idle errors, and keep real stopping outside this change.
- A short interaction grace may inconvenience real users → it is an accelerated simulation parameter, fixed in ground truth and clearly disclosed, not a production default.
- Payload JSON is less spreadsheet-friendly than wide CSVs → retain simple typed envelopes and document payload fields, units, and validation errors precisely.
- Default session count is not host capacity evidence → profiles describe demand; future runners must enforce concurrency/resource limits.

## Migration Plan

Add the new package, templates, and versioned dataset directory without changing existing CSV content. Document the timestamp mismatch and the absence of a reliable automatic legacy conversion. Generate and validate default/dev/held-out bundles, run offline evaluation, and publish reproducible commands and sample reports. Rollback removes only new tooling/generated bundles; no live container state or external infrastructure is changed. Future real collectors must pass the same validator before evaluation and supply actual execution acknowledgements.
