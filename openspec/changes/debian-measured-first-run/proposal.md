# Proposal

## Why

The synthetic pipeline is complete, but it does not establish that Docker workloads, host eBPF collection, attribution, or measured evaluation work together. Prove that path on the approved Debian host before expanding to the assignment's complete monitoring scope.

## What Changes

- Replay the existing seeded `cpu-background` and `pure-idle` schedules in two bounded Docker containers using Compose, preserving the CPU job across client disconnect.
- Package Clang/bpftool in a build image and a minimal libbpf collector in a separate runtime image; keep workloads unprivileged and free of monitoring tools.
- Check Docker, cgroup v2, BTF, tracefs, permissions and actual probe attachment; record the host environment and actionable failures.
- Collect real cgroup CPU/RAM and one process tracepoint through a ring buffer, attribute events to the selected container instances, and export five-second windows with quality and loss evidence.
- Build measured truth from actual execution acknowledgements; reuse validation, prediction and scoring without feeding plans or labels to policies.
- Leave uncollected I/O/socket signals missing, and expose multi-signal abstentions rather than fabricating complete coverage.

## Capabilities

### New Capabilities

- `measured-workload-replay`: Bounded replay of selected existing schedules, real lifecycle evidence, cleanup and measured-bundle assembly.
- `host-telemetry`: Containerized host preflight, minimal process-event/cgroup collection, instance attribution and quality-aware windows.

### Modified Capabilities

None. Durable specs are empty; the completed `simulation-evaluation-datasets` change supplies the existing contract, which this change preserves.

## Impact

Proposed additions: `measured/` Python orchestration/export, `collector/` native eBPF/libbpf implementation and images, Compose configuration, measured tests and run instructions. Reuse `simulation/contract.py`, `policies.py`, `validation.py` and `scoring.py`; add acknowledgement-derived truth logic without reusing the plan-based `generator.build_truth` as measured truth. Existing synthetic data and outputs remain unchanged.

The run needs Docker access and explicitly documented collector capabilities/mounts. No dashboard, approved-reclamation controller, automatic stopping based on predictions, seven-family coverage, full I/O/socket collection, overhead claims, four-state live detector or Ubuntu certification is included. Cleanup stops only containers created by the run, independently of policy recommendations.
