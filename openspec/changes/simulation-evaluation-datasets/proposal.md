# Proposal

## Why

OpenLab-Scale needs reproducible user-session and workload datasets to compare inactivity detection approaches before and during real Docker experiments. The existing sample mixes simulated metrics and partially observed traces, and its abbreviated timestamps differ from the guide; it cannot by itself establish real monitoring accuracy.

## What Changes

- Define a small, versioned dataset bundle separating executable scenario inputs, detector-visible observations, and evaluator-only ground truth.
- Generate deterministic synthetic sessions with editing interactions, connections, job execution, disconnects, reconnects, and abandonment; cover all seven workload families in the assignment.
- Provide a modest default suite and configurable session counts, seeds, and resource bounds for local use and future single-host AWS experiments.
- Provide explicitly synthetic observations for offline evaluation and a documented contract for future real-run observations and actual execution labels.
- Compare fixed interaction timeout, CPU-only, resource multi-signal, and interaction-aware multi-signal policies on the same observations without stopping containers.
- Validate time, joins, missingness, provenance, and label isolation; report errors, abstentions, and per-scenario metrics.
- Preserve the current CSVs as legacy examples; do not silently interpret their ambiguous timestamps or turn unknown durations into zero.

## Capabilities

### New Capabilities

- `simulation-datasets`: Versioned schemas, seeded scenario generation, synthetic interaction/resource observations, and validation for replayable experimental bundles.
- `policy-evaluation`: Comparable offline policy predictions and ground-truth scoring with explicit unknown handling and no label leakage.

### Modified Capabilities

None. No durable specs exist yet.

## Impact

Implementation will add a small Python 3 command-line dataset generator, validator, evaluator, scenario definitions, generated example bundles, and documentation alongside `data/`. Existing CSVs remain unchanged. This change defines integration contracts but does not implement Docker execution, eBPF collection, a session service, dashboard, container stopping, AWS deployment, or legacy trace conversion. Synthetic scores demonstrate pipeline behavior, not real eBPF effectiveness or host overhead.
