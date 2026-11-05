# AGENTS.md — Coding Agent Instructions & Project Invariants

This document provides context, architectural invariants, safety constraints, and workflow instructions for AI coding agents working in this repository.

---

## 1. Project Architecture

The repository implements a unified **`v1` bundle contract** shared between an offline synthetic simulator (`simulation/`) and a live Linux container telemetry runner (`measured/` + `collector/`):

* **`simulation/`** (Pure Python 3.9+ stdlib):
  * `contract.py`: Defines `SCHEMA = '1.0'`, the 5 canonical CSV tables (`sessions.csv`, `events.csv`, `phases.csv`, `observations.csv`, `truth.csv`), JSON payload schemas, and SHA-256 manifest helpers.
  * `scenarios.py` & `generator.py`: Deterministic SHA-256-seeded PRNG streams generating 10 scenario templates.
  * `observations.py`: Integrates phase/burst intersections into 5000ms observation windows and applies synthetic fault models.
  * `validation.py`: Enforces schema columns, manifest file digests, monotonic timestamps, and domain constraints.
  * `policies.py`: Implements `causal_projection()` and the 5 policies (`no-reclaim`, `interaction-timeout`, `cpu-only`, `resource-multi`, `interaction-aware`).
  * `scoring.py`: Computes false-reclaim rate, idle-capture metrics, abstention rates, and writes `metrics.json` and `report.md`.
* **`measured/` & `collector/`** (Live Docker + cgroup v2 + eBPF):
  * `collector/`: C/libbpf tracepoint collector (`sched:sched_process_exec`) compiled inside `collector/Dockerfile`.
  * `measured/preflight.py`: Verifies Docker Compose config, builds/starts a uniquely named collector project, confirms tracepoint attachment, and cleans up.
  * `measured/run.py`: Replays `cpu-background` and `pure-idle` from a 10-session source bundle, samples cgroup v2 (`cpu.stat`, `cpu.max`, `memory.current`), merges eBPF exec events, builds acknowledgement-based truth, validates the exported bundle, and runs `predict` + `score`.

---

## 2. Strict Invariants & Rules (Do Not Violate)

### Causality & Truth Separation
1. **No truth leakage into policies**: `simulation/policies.py` must **never** read `phases.csv`, `truth.csv`, `source-plan.json`, job durations, or lifecycle completion events (`JOB_COMPLETE`, `JOB_ERROR`, `JOB_INTERRUPT`).
2. **Two-clock causal gate**: Policy decisions at `decision_ms` may only see observations where both `at_ms <= decision_ms` and `available_at_ms <= decision_ms` (and for `resource` rows, `window_end_ms <= decision_ms`).
3. **Prediction before scoring**: Always keep `predict` and `score` separable so predictions can be finalized and hashed before ground-truth scoring reads `truth.csv`.

### Measured Experiment Safety & Honesty
1. **No synthetic fallback in `measured/`**: If Docker, cgroup v2, BTF, tracefs, or eBPF attachment fails, `measured` must fail explicitly with nonzero exit code and diagnostic evidence. Never fabricate or substitute synthetic metrics in a measured run.
2. **Explicit missing/degraded signals**: The current probe attaches only to `sched:sched_process_exec`. Disk/network byte counters and I/O/socket event counts are uncollected (`null`), making every measured resource window `DEGRADED`. Multi-signal policies (`resource-multi`, `interaction-aware`) must abstain (`UNKNOWN`) rather than treating `null` as zero activity.
3. **Never overwrite retained evidence or nonempty run directories**: `measured/run.py` refuses nonempty output directories via `reserve_output()`. Never delete or overwrite checked-in evidence under `data/measured-v1/`, `data/simulation-v1/`, or `measured/evidence/` unless explicitly instructed by the user.
4. **Owned container cleanup only**: All Docker Compose operations must be scoped to a unique run-owned project name (`MEASURED_PROJECT=measured-<uuid>`). Cleanup must only tear down the run-owned project and must never stop or inspect unrelated host containers. Policy recommendations (`IDLE_CANDIDATE`) are observational and never trigger container termination.
5. **Least privilege & host preservation**:
   * Never modify host sysctls, kernel mounts, packages, AppArmor/seccomp profiles, or user groups.
   * Workload containers (`cpu`, `idle`) run unprivileged (`65534:65534`, `cap_drop: [ALL]`, `network_mode: none`, `read_only: true`, `no-new-privileges: true`, 0.5 CPU, 256 MiB RAM, 16 PIDs).
   * Only the `collector` container receives `cap_add: [SYS_ADMIN]` (with `cap_drop: [ALL]`, `network_mode: none`, `read_only: true`, and read-only mounts of `/sys/kernel/tracing`, `/sys/kernel/btf`, `/sys/fs/cgroup`).

### Determinism & Portability
1. **Zero external Python dependencies**: Keep `simulation/`, `measured/`, and `tests/` compatible with Python 3.9+ standard library only.
2. **Deterministic simulation**: Synthetic bundle generation and offline evaluation must be 100% byte-deterministic for a given seed and configuration (canonical JSON sorting, `\n` line endings, no wall-clock timestamps or absolute paths embedded in synthetic bundles).

---

## 3. Common Commands for Agents

### Run Unit & Contract Tests
Always run the test suite after modifying code in `simulation/`, `measured/`, or `tests/`:
```bash
python3 -m unittest discover -s tests -v
```

### Validate Existing Bundles
```bash
python3 -m simulation validate data/simulation-v1/dev-43
python3 -m simulation validate data/simulation-v1/heldout-44
python3 -m simulation validate data/simulation-v1/scale-120
python3 -m simulation validate data/measured-v1/debian-first-run
```

### Run Live Measured Preflight & Verification
```bash
export MEASURED_PROJECT=measured-build-check
docker compose -f compose.measured.yaml config --quiet
python3 -m measured preflight
python3 -m tests.live_measured verify data/measured-v1/debian-first-run
```

---

## 4. OpenSpec Workflow

This project uses **OpenSpec** (`openspec/`) for spec-driven development. Skills and workflows are located in `.agents/skills/` and `.agents/workflows/`:
* Check `openspec/changes/` for active or completed proposals, design docs, delta specs, and task checklists.
* When asked to propose, explore, apply, sync, update, or archive a change, follow the corresponding skill instructions in `.agents/skills/openspec-*/SKILL.md`.
