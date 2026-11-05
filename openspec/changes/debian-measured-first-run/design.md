# Design

## Context

See proposal.md for motivation and scope. `simulation/contract.py` already defines measured-compatible CSV tables; `validation.py` checks execution acknowledgements and allows degraded resource payloads with nulls. `policies.py` admits only causal observations; `scoring.py` requires predictions for all five policies on a common timeline. No live runner or collector exists. `generator.expand` selects templates by index: count=2 yields CPU and disk, not CPU and idle. `generator.build_truth` is plan-based even with mode='measured', so it must not generate real-run labels.

Debian is the confirmed first host; earlier checks found working Docker access, cgroup v2 and BTF. Actual probe access has not been tested. No durable specs exist yet; this change preserves the contract described by the completed simulation change.

## Goals / Non-Goals

**Goals:** One reproducible measured pipeline with independent truth and a small observation interface. Concentrate replay/lifecycle logic in `measured/`, kernel collection in `collector/`, and retain the current evaluator as the test surface.

**Non-Goals:** No generic execution adapter framework, database, live controller, detector redesign or complete kernel signal coverage. Do not reinterpret a successful partial run as assignment acceptance.

## Decisions

### 1. Replay a selected source bundle without changing the generator

Proposed interface: `python3 -m measured run SOURCE_BUNDLE OUTPUT_DIRECTORY`. Select exactly one session each by scenario_id `cpu-background` and `pure-idle`; reject absent/duplicate matches or unsupported phases. Use a generated default seed-42 bundle, not count=2. Retain original events/phases and parameter hashes as source provenance; write a distinct measured output with fresh run/session/instance identities and explicit mappings back to selected inputs. This avoids adding scenario-selection flexibility to synthetic generation.

Validate the source offline, then pass only selected sessions, actions and phases to replay; synthetic observations/truth never enter collection or measured truth. Preserve the 300-second source durations and seeded parameters. Provision two 0.5-CPU/256-MiB containers for the default source, enforcing the declared bounds. CPU duty is relative to quota, with bounded memory allocation and an independent deadline; pure idle uses no application job. Do not use planned terminal events as actual acknowledgements.

### 2. Separate build, collector and workload images

Use a multi-stage native collector build with Clang, bpftool and libbpf development dependencies; the runtime holds only collector/runtime dependencies. Choose a libbpf ring-buffer implementation rather than adding bpftrace as a second collection path. Attach `sched:sched_process_exec` as the sole initial process tracepoint. A command execution handshake supplies a known exec event after collector readiness; this measures exec events only, not every process activity.

Compose defines two unprivileged workload containers and the collector. The Python coordinator invokes Compose/Docker locally; the collector does not mount the Docker socket. Start from explicit BPF/PERFMON capabilities, required read-only BTF/tracefs/cgroup mounts and host identity visibility. Verify the actual minimal access set on Debian before committing the final configuration; if confinement blocks access, fail with diagnostics rather than silently using blanket privileged mode. Record exact successful capabilities, namespace settings, mounts, image identifiers and kernel metadata. No host group, sysctl or package changes are performed by preflight.

Host mount visibility, cgroup identity and actual attach support are implementation gate checks, not assumed capabilities. Prefer existing kernel tracepoint/BTF interfaces rather than per-kernel host tool installation.

### 3. One monotonic origin and stable attribution

Prepare idle workload containers and resolve Docker ID, start time, host PID and cgroup path/ID before defining the run origin. The collector acknowledges successful attach and initial baselines before replay begins. Host coordinator, container workers and eBPF timestamps use the host monotonic clock without a separate time namespace; verify compatibility and convert to elapsed milliseconds. UTC is display metadata only. Record actual container/session start and end bounds; never fabricate zero-time events for an action executed late.

Map cgroup identity to the selected Docker instance. Filter unrelated cgroups in kernel where supported; verify attribution on user-space ingestion as well. Process events retain timestamp, PID/TGID, cgroup ID and event type. Track ring-buffer reservation failures in a separately readable counter. Use conservatively attributed run-wide loss deltas if per-container attribution is unavailable. Failed counter reads mean unknown loss, not zero. A selected-container restart, exit or mapping change invalidates current evidence, resets baselines and aborts the first-slice run; automatic restart recovery is deferred. Preserve diagnostics and never transfer old events to a new instance.

### 4. Export partial observations honestly

Sample `cpu.stat`, `cpu.max` and `memory.current`; normalize CPU usage delta by actual monotonic sampling duration and configured quota. Keep raw samples and normalization diagnostics, including out-of-range values, rather than silently clipping to satisfy the schema. If a normalized value cannot be represented validly, export it as missing/degraded with a diagnostic. Retain actual acquisition timestamps; a delayed sampling window must not be silently relabeled as an on-time five-second window. Split or mark uncovered windows missing as necessary to preserve the existing <=5000ms contract.

Export process exec counts, loss and mapping validity. Set uncollected I/O/socket counts and disk/network deltas to null. Keep existing `measured_collector`, `cgroup_v2` and `ebpf` provenance labels and describe exact probe coverage in manifest configuration and report limitations. In this slice all resource windows are at least DEGRADED due to omitted fields. CPU-only may still run when its own required fields are valid; resource-multi and interaction-aware remain UNKNOWN under current policy rules. This is an intentional limit, not a reason to weaken missingness checks.

Record interaction/connection observations only for actions actually executed by the simulated client. Emit health only while that reporting path is genuinely functioning; do not copy synthetic health records. Availability time is when a record reaches the coordinator. Assign late events to their occurrence window only with appropriately late availability; never overwrite a previously exported window to suggest earlier knowledge. Preserve final partial windows and raw evidence.

### 5. Acknowledgement-derived truth, then existing evaluation

Implement measured truth assembly in the measured replay module using actual request/start/terminal records and executed connection/interaction events. A successful job is ACTIVE on its actual acknowledged interval, regardless of plan. Follow existing validator semantics for failed/unconfirmed jobs: UNKNOWN during affected unresolved execution, IDLE after a confirmed terminal event. Missing terminal acknowledgement remains UNKNOWN to observation end. Split truth at actual lifecycle events and interaction-grace expiries; retain existing 30-second interaction eligibility semantics without claiming these are pure resource-state labels.

Do not call `generator.build_truth` with measured mode; its implementation consults planned phases. Share serialization and existing validation, not synthetic truth inference. Preserve planned phase rows as replay provenance and use separate actual events as evidence. Write all five CSV tables and manifest hashes, validate, finalize predictions, then score. Preserve all five policies to satisfy the common-timeline scorer. Measured reports disclose partial collection, missing interaction data if applicable, UNKNOWN coverage, and that synthetic/real scores are never pooled. Update measured report wording only if the existing scorer incorrectly describes the partial evidence.

### 6. Ownership and failure handling

Create a unique Compose project/run label and record exact resource IDs. Refuse nonempty output destinations. Use a staging output with incomplete status until collection and validation finish; report success only after scoring succeeds. On attach failure, do not start scheduled work. On error/interruption, collect diagnostic evidence, stop/detach the collector and stop/remove only owned workloads with bounded timeouts; expose cleanup failures. End-of-experiment cleanup is authorized experimental lifecycle management, never a reclaim-policy action.

## Risks / Trade-offs

- Kernel capabilities or container confinement differ on Debian → prove actual attach before workloads, record failures and required access; no fake fallback.
- One exec probe cannot detect useful CPU work throughout a job → use it only to prove event plumbing and attribution; retain CPU-only baseline and explicit multi-signal abstention.
- Ring-buffer delivery races and delayed samples → raw timestamps, loss accounting, availability gates and conservative missingness tests.
- Worker failures can make planned success appear plausible → require actual acknowledgements and use UNKNOWN for unresolved execution.
- Collector observer privileges expose host state → keep privileges out of workload containers, omit Docker socket, document exact access.
- A single seeded two-container run cannot establish generalization or overhead → publish scope and raw evidence; full workloads, Ubuntu and benchmarks remain later work.

## Migration Plan

Add measured tooling/images/configuration beside the existing simulation package. Run fixture tests without Docker, build the images, execute preflight and the bounded live run, then inspect exported measured reports. Verify existing synthetic tests and dataset hashes remain unchanged. Rollback removes only new tooling and run-owned resources; retain the source bundle and diagnostics. No existing schema migration is needed.
