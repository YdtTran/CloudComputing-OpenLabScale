# Cloud Workspace Idle Detection & Evaluation (`v1`)

A reproducible framework for evaluating idle-container reclamation policies across **offline deterministic simulations** and **real-host measured container experiments** using cgroup v2 resource counters and eBPF tracepoints.

---

## Overview

Cloud development workspaces and interactive containers frequently remain allocated while idle, or conversely run detached background jobs after a client disconnects. Relying solely on client interaction timeouts risks terminating active background computations, while relying solely on CPU thresholds can misclassify I/O-bound or bursty workloads.

This repository provides:
1. **`simulation/`** — A zero-dependency Python 3.9+ offline simulation engine that generates deterministic synthetic session bundles, validates schema contracts, executes causal idle-detection policies (`no-reclaim`, `interaction-timeout`, `cpu-only`, `resource-multi`, `interaction-aware`), and scores recommendations against ground truth.
2. **`measured/` & `collector/`** — A live Docker Compose + cgroup v2 + libbpf (`sched:sched_process_exec`) experiment runner that replays selected workload schedules in isolated containers, collects real kernel/cgroup telemetry, exports `v1`-compliant bundles, and evaluates the exact same policy and scoring pipeline.
3. **`data/`** — Versioned synthetic benchmark datasets (`data/simulation-v1/`), retained real-host Debian measured evidence (`data/measured-v1/`), and 100-client concurrent request-load measurements (`data/load-v1/`).
4. **`backend/` & `frontend/`** — Single-host **OpenLabScale workspace demonstration** combining a FastAPI + Docker SDK FIFO session scheduler (`backend/`), a React/Vite + `xterm.js` Student Portal (`/student`) and Administrator Dashboard (`/admin`) (`frontend/`), and an `asyncio` + `httpx` concurrent load generator (`backend/load.py`).

---

## OpenLabScale Single-Host Workspace Demo

The OpenLabScale workspace service (`backend/` + `frontend/`) provisions real, resource-bounded Linux containers (`65534:65534`, `cap_drop=["ALL"]`, `no-new-privileges`, `network_mode="none"`, `read_only=true`, bounded `/tmp` tmpfs, cgroup v2 CPU/memory/PID limits) on a single controlled Docker host:

- **Architecture & Data Flow**: A single Uvicorn worker owns the in-memory FIFO reservation ledger (`host_cpu_millis - headroom_cpu_millis`, `host_memory_mib - headroom_memory_mib`, global `max_sessions`, and `per_user` active limits) and serializes per-session Docker lifecycle transitions (`REQUESTED -> QUEUED -> PROVISIONING -> RUNNING -> RELEASING -> RELEASED | COMPLETED | FAILED | CANCELLED`). When `frontend/dist/index.html` is present, `backend/api.py` serves both the static UI and API/WebSocket routes on `127.0.0.1:8000`.
- **Reproducible 100-Request Load Evidence**: `python -m backend.load suite <output_dir>` runs a 10-client smoke test and 100 synchronized HTTP clients (`concurrent_http_clients = 100`, `active_terminals = 0`) against a bounded container cap (`peak_running_containers = 4` in `data/load-v1/concurrent-100`), exporting per-session latencies (`sessions.csv`) and reconciled server/Docker cleanup counts (`summary.json`).
- **Assumptions & Known Limitations**:
  - **Single-host, in-memory state**: Session history and queue state reside in memory (`--workers 1`) and reset on restart; startup `Engine.reconcile()` removes deployment-labeled leftovers before opening admission.
  - **Authentication & shared kernel**: SQLite-backed accounts use server-managed cookie sessions. Run the service on a trusted host and use loopback / SSH port forwarding or a trusted HTTPS proxy. Docker workspaces share the host kernel.
  - **AWS EC2 verification boundary**: Local Linux Docker (`Linux 6.18.54.1-microsoft-standard-WSL2`, Docker `29.9.2`, cgroup v2) is fully verified in `data/load-v1/` and `backend_tests/test_live.py`. Live AWS EC2 execution has not been run from this workstation (no cloud credentials attached) and is documented as unverified on cloud hardware alongside full Ubuntu 24.04 LTS + `t3.xlarge` (`4 vCPU`, `16 GiB`, burstable CPU-credit) sizing, security group, and teardown instructions in [`docs/06-openlabscale-backend.md`](docs/06-openlabscale-backend.md).

## Repository Structure

```text
.
├── backend/                 # FastAPI + Docker SDK single-host workspace service
│   ├── api.py               # REST endpoints, WebSocket PTY guard, and static UI mount
│   ├── engine.py            # Hardened Docker lifecycle, orphan reconciliation & /proc telemetry
│   ├── load.py              # 10-client smoke & 100-client concurrent request load runner
│   ├── models.py            # Settings, lifecycle states, and API schemas
│   ├── scheduler.py         # Atomic resource-aware FIFO admission & background worker
│   └── terminal.py          # Non-blocking Docker exec PTY <-> WebSocket bridge
├── backend_tests/           # Unit, load-workflow, and opt-in live Docker integration tests
├── collector/               # Native libbpf eBPF collector (sched:sched_process_exec)
│   ├── Dockerfile           # Multi-stage build (clang/bpftool build -> minimal runtime)
│   ├── exec.bpf.c           # Kernel tracepoint probe & ringbuf/loss counter maps
│   └── reader.c             # Userspace ring-buffer reader emitting JSONL events
├── compose.measured.yaml    # Hardened Docker Compose deployment for measured runs
├── data/
│   ├── load-v1/             # Retained 10-client smoke & 100-client concurrent load evidence
│   ├── simulation-v1/       # Versioned synthetic bundles (dev-43, heldout-44, scale-120)
│   └── measured-v1/         # Source bundle (source-42) & retained Debian measured runs
├── docs/                    # Technical specification & project documentation
│   ├── 01-tong-quan-va-pham-vi.md
│   ├── 02-kien-truc-he-thong.md
│   ├── 03-mo-hinh-du-lieu-va-chinh-sach.md
│   ├── 04-huong-dan-thuc-nghiem-va-ket-qua.md
│   ├── 05-huong-dan-thuc-hanh-ebpf-live.md
│   ├── 06-openlabscale-backend.md
│   └── adr/                 # Architecture Decision Records (Two-clock, Degraded abstention)
├── frontend/                # React + TypeScript + Vite + xterm.js Student & Admin UI
├── GLOSSARY.md              # Ubiquitous domain language & terminology boundaries
├── measured/                # Real-host coordinator, worker, cgroup sampler, and truth builder
│   ├── Dockerfile           # Unprivileged Python worker container image
│   ├── preflight.py         # Bounded eBPF attachment & cleanup verification
│   ├── run.py               # Live experiment coordinator and v1 bundle exporter
│   ├── source.py            # Source plan validation and session selection
│   ├── telemetry.py         # cgroup v2 sampling, attribution verification & windowing
│   ├── truth.py             # Acknowledgement-driven ground truth derivation
│   └── worker.py            # Containerized CPU/idle workload executor
├── openspec/                # OpenSpec change proposals, designs, specs, and tasks
├── simulation/              # Offline generator, validator, policy engine, and scorer
│   ├── contract.py          # v1 schema tables, field definitions, and canonical I/O
│   ├── generator.py         # Deterministic PRNG synthetic workload & signal generator
│   ├── observations.py      # Observation window integration and fault injection
│   ├── policies.py          # Causal projection gate and 5 idle-detection policies
│   ├── scenarios.py         # 10 scenario templates (interactive, background, bursts, faults)
│   ├── scoring.py           # Offline evaluation metrics and Markdown report generator
│   └── validation.py        # Schema, hash, ordering, and causal contract validator
└── tests/                   # Unit, contract, deployment, preflight, and live host tests
```

---

## Quick Start: Offline Simulation

The offline simulation requires **Python 3.9+** with **no third-party packages, containers, or special privileges**.

### 1. Generate, Validate, and Evaluate a Synthetic Bundle

```bash
# View CLI options
python3 -m simulation --help

# Generate a deterministic 10-session synthetic bundle (seed 42)
python3 -m simulation generate /tmp/dev42 --seed 42

# Validate schema, manifest digests, and invariants
python3 -m simulation validate /tmp/dev42

# Run causal policy prediction and score against ground truth
python3 -m simulation evaluate /tmp/dev42 /tmp/dev42/evaluation
```

You can also run prediction and scoring as separate steps:
```bash
python3 -m simulation predict /tmp/dev42 /tmp/dev42/separate-eval
python3 -m simulation score /tmp/dev42 /tmp/dev42/separate-eval
```

### 2. Customize Scale & Policy Thresholds

Scale session counts, stagger start times, or override policy parameters via `--policy-config`:

```bash
# Generate 30 sessions staggered by 10 seconds
python3 -m simulation generate /tmp/scale30 \
  --seed 42 \
  --count 30 \
  --start-offset-ms 10000 \
  --cpu-limit-cores 0.5 \
  --memory-limit-mb 256 \
  --overwrite

# Override policy thresholds (keys: cpu_threshold_pct, quiet_ms, hysteresis_ms,
# interaction_grace_ms, interaction_timeout_ms, freshness_ms)
cat << 'EOF' > /tmp/policy-overrides.json
{
  "cpu_threshold_pct": 2.0,
  "quiet_ms": 20000
}
EOF

python3 -m simulation evaluate /tmp/scale30 /tmp/scale30/evaluation \
  --policy-config /tmp/policy-overrides.json
```

---

## Live Measured Experiment (`measured`)

The measured runner executes real containerized workloads on a Linux host with **cgroup v2**, **BPF / perf tracepoints**, readable BTF (`/sys/kernel/btf/vmlinux`), mounted tracefs (`/sys/kernel/tracing`), and **Docker Compose**.

### 1. Build Images & Run Preflight

```bash
export MEASURED_PROJECT=measured-build-check
docker compose -f compose.measured.yaml config --quiet
docker compose -f compose.measured.yaml build collector cpu
python3 -m measured preflight
```

`preflight` starts only a uniquely named collector container, verifies `sched:sched_process_exec` tracepoint attachment, emits JSON evidence (`"status": "attached"`), and tears down its Compose project.

### 2. Run a Measured Experiment (~5 Minutes)

The measured coordinator selects the `cpu-background` and `pure-idle` sessions from a 10-session seed-42 source bundle (`data/measured-v1/source-42`) and replays them against isolated worker containers:

```bash
# Generate source-42 if not already present
python3 -m simulation generate data/measured-v1/source-42 --seed 42

# Execute the live measured run into a fresh output directory
python3 -m measured run data/measured-v1/source-42 /tmp/measured-run-01

# Validate the exported v1 bundle and verify live acceptance invariants
python3 -m simulation validate /tmp/measured-run-01
python3 -m tests.live_measured verify /tmp/measured-run-01
```

> **Note:** Never reuse an existing output directory for `python3 -m measured run`. The coordinator reserves a fresh directory and marks `run-status.json` as `incomplete` until validation, prediction, scoring, and container cleanup all succeed.

---

## Policies Evaluated

All five policies in `simulation/policies.py` operate strictly through a causal projection gate (`at_ms <= decision_ms` and `available_at_ms <= decision_ms`) without access to future events, phase plans, or ground truth:

| Policy | Inputs Used | Behavior Summary |
| :--- | :--- | :--- |
| `no-reclaim` | None | Baseline reference that always emits `RETAIN`. |
| `interaction-timeout` | Interaction & health | Emits `IDLE_CANDIDATE` when elapsed time since last user action meets `interaction_timeout_ms` (40s default). |
| `cpu-only` | cgroup CPU + mapping/loss | Emits `IDLE_CANDIDATE` when quota-normalized CPU stays below `cpu_threshold_pct` (1.0%) for `quiet_ms` (30s). |
| `resource-multi` | CPU, disk, net, eBPF events | Requires CPU below threshold and zero disk/network/process/I/O/socket activity across the quiet window; abstains (`UNKNOWN`) if any required signal is null/degraded. |
| `interaction-aware` | All resource + interaction | Combines multi-signal resource quietness with `interaction_grace_ms` (30s) after user actions; abstains (`UNKNOWN`) when signals are missing. |

---

## Running Tests

Run the full unit, contract, deployment, and preflight test suite from the repository root:

```bash
python3 -m unittest discover -s tests -v
```

To run the live host fault-injection and verification suite (requires Docker & eBPF host support):

```bash
python3 -m tests.live_measured verify data/measured-v1/debian-first-run
python3 -m tests.live_measured data/measured-v1/source-42 /tmp/fault-checks-run
```

To run the OpenLabScale workspace backend unit, load-workflow, and live Linux Docker tests:

```bash
python3 -m unittest discover -s backend_tests -v
OPENLABSCALE_LIVE=1 python3 -m unittest discover -s backend_tests -p test_live.py -v
```

The `python -m backend.load suite /tmp/load-run` workload provisions temporary
student and administrator identities, signs in before starting the timed
submissions, and removes its temporary identity database after the run. Use a
fresh output directory for each run.

---

## Documentation Index

* [OpenLabScale Local & AWS EC2 Deployment Guide](docs/06-openlabscale-backend.md)
* [Retained Concurrent Load Evidence (`data/load-v1/`)](data/load-v1/README.md)
* [Offline Simulation Guide](data/simulation-v1/README.md)
  * [Schema & Field Dictionary (`FIELDS.md`)](data/simulation-v1/FIELDS.md)
  * [Scenario Templates (`SCENARIOS.md`)](data/simulation-v1/SCENARIOS.md)
  * [Replay & Determinism (`REPLAY.md`)](data/simulation-v1/REPLAY.md)
  * [Policy Specifications (`POLICIES.md`)](data/simulation-v1/POLICIES.md)
* [Measured Experiment Guide](measured/README.md)
* [Retained Measured Evidence Index](data/measured-v1/README.md)
