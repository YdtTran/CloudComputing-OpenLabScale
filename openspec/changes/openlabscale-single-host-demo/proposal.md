## Why

OpenLabScale needs a reproducible university demo of scheduling and using real Linux sessions on one Docker host. The existing idle-detection experiments provide measured telemetry and isolation patterns, while the interactive session service and its client workflow are new work.

## What Changes

- Add resource-limited session provisioning, FIFO admission, and an ownership-checked browser terminal and release flow.
- Show real capacity, utilization, queue, and lifecycle data to administrators.
- Measure a bounded 100-concurrent-request API workload and document local Linux and single-host EC2 deployment and cleanup.

## Capabilities

### New Capabilities

- `workspace-sessions` — Admission, lifecycle, isolation, and student access.
- `workspace-operations` — Admin telemetry, reproducible load evidence, and deployment.

### Modified Capabilities

None.

## Impact

The demo adds a separately installed FastAPI and Docker SDK backend, a React/Vite frontend with xterm.js, and load and deployment tooling. The existing stdlib experiment CLIs, data, and contracts retain their scope. The demo assumes a controlled single Linux Docker host. Campus rollout, production authentication, multi-host scheduling, and eBPF integration are outside this change.

Planning is tracked by [issue #3](https://github.com/YdtTran/CloudComputing-OpenLabScale/issues/3) under [epic #2](https://github.com/YdtTran/CloudComputing-OpenLabScale/issues/2).
