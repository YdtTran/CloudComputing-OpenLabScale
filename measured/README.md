# Measured first run

From the repository root, build and validate the deployment:

```sh
export MEASURED_PROJECT=measured-build-check
docker compose -f compose.measured.yaml config --quiet
docker compose -f compose.measured.yaml build collector cpu
python3 -m measured preflight
python3 -m unittest tests.test_measured_deployment tests.test_measured_preflight -v
```

Preflight creates only a uniquely named collector, waits for actual
`sched:sched_process_exec` attachment, and removes its project with bounded
timeouts. It does not start CPU/idle workloads or alter host permissions,
packages, mounts, groups or sysctls. A failed check exits nonzero and prints
JSON evidence, including cleanup failures. No synthetic or privileged fallback
exists.

Generate a fresh default source and run the two selected sessions (about five
minutes plus setup/cleanup):

```sh
python3 -m simulation generate data/measured-v1/source-42 --seed 42
python3 -m measured run data/measured-v1/source-42 data/measured-v1/debian-first-run
python3 -m simulation validate data/measured-v1/debian-first-run
```

The generator's `--count 2` selects CPU and disk, not CPU and idle. Use the
default ten-session source; selection requires exactly one `cpu-background`
and one `pure-idle`, preserving the original 300-second plans and seeded CPU
duty/memory parameters. Unsupported phases and bounds fail before startup.
Source hashes and the selected source events/phases are retained separately;
synthetic observations and labels never feed measured collection or truth.

The run invokes separate `predict` and `score` commands, in that order. To
repeat evaluation into a fresh directory:

```sh
python3 -m simulation predict data/measured-v1/debian-first-run data/measured-v1/debian-first-run/evaluation-review
python3 -m simulation score data/measured-v1/debian-first-run data/measured-v1/debian-first-run/evaluation-review
```

Each experiment needs a fresh output directory. `run-status.json` stays
`incomplete` until export validation, prediction, scoring and owned cleanup
all succeed. Interrupt with Ctrl-C or SIGTERM; retained raw evidence includes
the error and bounded cleanup diagnostics. Cleanup uses the unique run-owned
Compose project, independently of all policy recommendations. It never reclaims
an unrelated container or acts on an idle recommendation.

Workers acknowledge readiness, start and terminal events. Host, worker and
collector monotonic clocks are checked before replay; elapsed occurrence and
receipt times are retained. Client disconnect changes connection state without
cancelling the independent CPU process. Per-job wall alarms and the container's
330-second lifetime bound runaway work.

Resource acquisition uses cgroup `cpu.stat`, `cpu.max`, and `memory.current`,
not Docker statistics. Sampling targets a 4.9-second cadence so actual windows
usually fit the <=5000ms contract. Bounds and availability retain actual
monotonic times. Overruns split into <=5000ms windows with missing CPU, rather
than presenting an averaged long sample as on-time evidence. Delayed exec
events retain late availability; missing/lost/unmapped evidence is explicit.
Raw counters and CPU normalization diagnostics remain in `raw-cgroup.json`.

`sched:sched_process_exec` is the sole probe; it does not observe all useful
process activity. I/O/socket counts and disk/network counters remain null.
Every resource window is at least DEGRADED, and multi-signal policies abstain.
Executed client actions and successful coordinator heartbeats are the only
interaction/health observations. Truth uses actual acknowledgements and the
existing 30-second interaction grace; planned completion never implies success.
Original phases stay verbatim in `source-plan.json`; exported job phase bounds
shift by actual request lag to preserve the existing request-before-phase join.
This does not change measured truth, which ignores phase bounds entirely.

The collector requires a cgroup-v2 Linux host with BPF, ring-buffer and perf
tracepoint support, readable BTF at `/sys/kernel/btf/vmlinux`, and mounted
tracefs containing `events/sched/sched_process_exec/id`. Docker access and
Compose are required. Clang, bpftool and development headers stay in the build
stage; the runtime contains the native reader and libbpf runtime dependencies.

The verified Debian runtime access set is:

- Drop all capabilities, add only SYS_ADMIN. This broad capability is required by the observed host/container perf access path; BPF/PERFMON alone failed, including with an explicit perf syscall allowlist and AppArmor separately disabled. Workloads never receive it.
- Host PID and cgroup namespaces; no network; read-only root filesystem.
- Read-only bind mounts of `/sys/kernel/tracing`, `/sys/kernel/btf` and
  `/sys/fs/cgroup`; no Docker socket.
- Default Docker seccomp/AppArmor confinement and `no-new-privileges` retained.

Both workload services run as UID/GID 65534 with no capabilities or host
mounts, 0.5 CPU, 256 MiB memory and 16 PIDs. The worker rejects jobs exceeding
300 seconds, duty outside [0,1], or allocations exceeding 128 MiB. CPU duty is
relative to the 0.5-CPU quota. Idle containers have an independent 330-second
lifetime. These checks do not establish coordinator/deadline acceptance.

## Debian attachment blocker

The retained [preflight evidence](evidence/debian-preflight-blocked.json) records
Debian 13, kernel `6.12.115+deb13.1-amd64`, image identity and the full resolved
configuration. BPF loading succeeded but actual tracepoint attachment failed:

```text
libbpf: tracepoint 'sched/sched_process_exec' perf_event_open() failed: Permission denied
```

No collector readiness was emitted, workloads were not started, and owned
cleanup succeeded. The initial BPF/PERFMON capability set was not sufficient. The subsequent
[successful attachment evidence](evidence/debian-preflight-attached.json) records
actual readiness using SYS_ADMIN alone, default seccomp/AppArmor, and the mounts
and namespaces listed above. No host setting was changed. This proves attachment,
not measured experiment acceptance.

The probe covers exec events only, with timestamp/PID/TGID/cgroup identity and
an independently read loss map. Failed loss reads remain unknown. Attribution
is checked against the full Docker ID, start time, host PID, restart count and
cgroup inode; a change aborts the run and invalidates the old baseline.

Measured timing is not byte-deterministic. Fresh run/session/instance identities
and actual acknowledgement/measurement times intentionally differ across runs.
Ubuntu, all workload families, full I/O/socket coverage and overhead validation
are deferred; this experiment makes no broader accuracy claim.

## Retained acceptance and repeat checks

See [the measured evidence index](../data/measured-v1/README.md). Run the
assert-based real-host acceptance tools explicitly (fault trials take about a
minute and create their own fresh experiments and unrelated sentinel):

```sh
python3 -m tests.live_measured verify data/measured-v1/debian-first-run
python3 -m tests.live_measured data/measured-v1/source-42 data/measured-v1/fault-checks-new
python3 -m measured run data/measured-v1/source-42 data/measured-v1/debian-repeat-new
python3 -m tests.live_measured verify data/measured-v1/debian-repeat-new
python3 -m unittest discover -v
```

Never reuse an evidence destination. Repeating into a nonempty directory is
rejected without changing earlier bytes. The original dataset hash inventory
and final test log are retained under `measured/evidence/`.

Confinement references: [Docker seccomp documentation](https://docs.docker.com/engine/security/seccomp/) and [Moby default profile](https://github.com/moby/profiles/blob/main/seccomp/default.json).
