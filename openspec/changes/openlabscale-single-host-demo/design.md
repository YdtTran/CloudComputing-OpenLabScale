## Context

Assessment for [issue #3](https://github.com/YdtTran/CloudComputing-OpenLabScale/issues/3), based on main commit `baa1ec4b276af57890a0d375a475d67c5f125731`.

| Existing code | Reuse decision and gap |
|---|---|
| `README.md`, `simulation/contract.py`, `simulation/policies.py`, `simulation/scoring.py` | The stdlib CLI evaluates offline bundles. Keep the two-clock projection and prediction-before-scoring contracts intact. Scheduler admission needs its own live reservation ledger. |
| `measured/run.py`, `measured/preflight.py`, `compose.measured.yaml` | Compose manages bounded experiment cohorts under unique project names. Carry the ownership and isolation rules into per-session Docker SDK calls. Interactive lifecycle, queue and terminal need a separate service. |
| `measured/telemetry.py` | Instance mapping, CPU deltas and memory counters are relevant. Try Docker stats for owned containers first to avoid requiring host PID and cgroup access in the API. The existing attribution and windowing code is tied to experiment evidence. |
| `collector/exec.bpf.c`, `collector/reader.c` | Exec tracepoints and ring-buffer loss reporting serve measured replay. Demo utilization can use Docker and host counters without collector privileges. |
| `tests/`, `data/`, existing OpenSpec changes | Keep the regression suite and retained bundles as compatibility checks. Use separate demo tests and result directories. Main has no demo API, frontend, scheduler or end-to-end deployment. |

Baseline verification passed 45 unit and contract tests, validated `dev-43`, `heldout-44`, `scale-120`, and `debian-first-run`, and parsed the measured Compose config. These checks cover retained evidence and configuration. Live replay and eBPF attachment were outside this baseline.

## Goals / Non-Goals

Deliver a real student session, a real admin snapshot, reproducible request-load evidence, and a local and EC2 deployment procedure. Scope the demo to one controlled host and one backend process. Production authentication, multi-host placement, automated idle reclamation, and eBPF integration are outside the demo scope.

## Decisions

1. **Service boundary.** A separately installed FastAPI service owns Docker operations and session state. React/Vite serves student and admin views, and xterm.js exchanges terminal frames with the backend. Use Docker SDK calls with finite deadlines outside the scheduler lock. A single backend worker avoids conflicting in-memory ledgers. A database and distributed queue would add persistence and coordination beyond the single-host demo.
2. **Admission.** Configure CPU and memory budgets after host headroom, plus per-user and global active limits. Reject requests that can never fit. Enqueue valid requests in arrival order and reserve CPU, memory and slots atomically for the head. If the head is temporarily blocked, later requests wait. Release and cancel operations wake the scheduler. Reserve against configured limits. Sampled usage serves observability.
3. **Lifecycle.** Use `QUEUED → PROVISIONING → RUNNING → RELEASING → COMPLETED | CANCELLED | FAILED`. Queue cancellation can go directly to `CANCELLED`. Docker operations are bounded and serialized per session. Cancellation during provisioning records intent and waits for provisioning and cleanup to settle. Keep reservations through cleanup until removal or confirmed absence, including after ambiguous timeouts. Surface pending cleanup and retry it. Label containers at creation with a stable deployment identifier and session ID. On startup reconcile owned containers before opening admission. If cleanup cannot be verified, fail startup with diagnostics.
4. **Data flow.** `POST /sessions` accepts a request and returns a session ID, `GET /sessions/{id}` reports status, and `DELETE /sessions/{id}` requests idempotent release. A session WebSocket checks ownership and running state before attaching to an unprivileged Docker exec PTY. Release closes the PTY. A read-only admin endpoint returns counts, queue order, reserved versus configured capacity, and sampled CPU and memory from owned containers and the host. Include timestamps, units, and unavailable indicators. Use server-derived identity and admin role on each HTTP request and WebSocket handshake.
5. **Isolation.** Run a pinned image as a non-root user with dropped capabilities, no privilege escalation, no network, a read-only root and bounded writable tmpfs where needed. Apply CPU, memory, PID and session time limits. Keep Docker access on the backend and expose the demo through a controlled private access path. Student containers receive no host mounts, secrets, or Docker socket.
6. **Load and evidence.** Use a bounded session job that exercises request, wait, run and release over the same service path. Run a 5–10 client smoke test before a synchronized 100-client submission. Collect per-client request, queue and provisioning timings and outcomes, plus server-observed peak running count. Write CSV and JSON with configuration and environment metadata to a fresh output directory.

## Risks / Trade-offs

- In-memory sessions and queue history are lost on restart. Reconciliation removes owned leftovers before admission. This design assumes exclusive operation of the backend for its deployment identifier.
- Strict FIFO can leave capacity unused while the head waits. Bound queue wait and session lifetime, and expose queue state.
- The backend controls Docker and must be restricted to trusted operators. Demo identities are for controlled access only.
- The epic's 0.5 vCPU and 256 MiB examples are per-container starting points. Choose caps after reserving host headroom. Measure EC2 CPU-credit behavior, cost and peak concurrency in Phase 6. A 100-request run establishes request workload behavior for its recorded configuration.
