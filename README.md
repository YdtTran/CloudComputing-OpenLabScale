# Cloud Workspace Idle Detection & Evaluation (`v1`)

A reproducible framework for evaluating idle-container reclamation policies across **offline deterministic simulations** and **real-host measured container experiments** using cgroup v2 resource counters and eBPF tracepoints.

---

## Overview

Cloud development workspaces and interactive containers frequently remain allocated while idle, or conversely run detached background jobs after a client disconnects. Relying solely on client interaction timeouts risks terminating active background computations, while relying solely on CPU thresholds can misclassify I/O-bound or bursty workloads.

This repository provides:
1. **`simulation/`** — A zero-dependency Python 3.9+ offline simulation engine that generates deterministic synthetic session bundles, validates schema contracts, executes causal idle-detection policies (`no-reclaim`, `interaction-timeout`, `cpu-only`, `resource-multi`, `interaction-aware`), and scores recommendations against ground truth.
2. **`measured/` & `collector/`** — A live Docker Compose + cgroup v2 + libbpf (`sched:sched_process_exec`) experiment runner that replays selected workload schedules in isolated containers, collects real kernel/cgroup telemetry, exports `v1`-compliant bundles, and evaluates the exact same policy and scoring pipeline.
3. **`data/`** — Versioned synthetic benchmark datasets (`data/simulation-v1/`) and retained real-host Debian measured evidence (`data/measured-v1/`).

---

## OpenLabScale workspace demo

The separate FastAPI backend provisions real Docker workspaces with a resource-aware FIFO queue and an ownership-checked terminal. See the [local setup, API, and verification guide](docs/06-openlabscale-backend.md).

## Repository Structure

```text
.
├── collector/               # Native libbpf eBPF collector (sched:sched_process_exec)
│   ├── Dockerfile           # Multi-stage build (clang/bpftool build -> minimal runtime)
│   ├── exec.bpf.c           # Kernel tracepoint probe & ringbuf/loss counter maps
│   └── reader.c             # Userspace ring-buffer reader emitting JSONL events
├── compose.measured.yaml    # Hardened Docker Compose deployment for measured runs
├── data/
│   ├── simulation-v1/       # Versioned synthetic bundles (dev-43, heldout-44, scale-120)
│   └── measured-v1/         # Source bundle (source-42) & retained Debian measured runs
├── docs/                    # Technical specification & project documentation
│   ├── 01-tong-quan-va-pham-vi.md
│   ├── 02-kien-truc-he-thong.md
│   ├── 03-mo-hinh-du-lieu-va-chinh-sach.md
│   ├── 04-huong-dan-thuc-nghiem-va-ket-qua.md
│   ├── 05-huong-dan-thuc-hanh-ebpf-live.md
│   └── adr/                 # Architecture Decision Records (Two-clock, Degraded abstention)
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

---

## Documentation Index

* [Offline Simulation Guide](data/simulation-v1/README.md)
  * [Schema & Field Dictionary (`FIELDS.md`)](data/simulation-v1/FIELDS.md)
  * [Scenario Templates (`SCENARIOS.md`)](data/simulation-v1/SCENARIOS.md)
  * [Replay & Determinism (`REPLAY.md`)](data/simulation-v1/REPLAY.md)
  * [Policy Specifications (`POLICIES.md`)](data/simulation-v1/POLICIES.md)
* [Measured Experiment Guide](measured/README.md)
* [Retained Measured Evidence Index](data/measured-v1/README.md)
