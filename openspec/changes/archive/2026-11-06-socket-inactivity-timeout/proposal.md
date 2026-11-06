# Proposal: Socket Inactivity Timeout (v1.1)

## Why

In interactive cloud workspace container reclamation, long-silent network requests (such as database queries, web scraping, or long-polling HTTP requests) cause False Positives (premature reclamation) because CPU usage drops near 0% and no network packets are transferred during the wait. However, naively retaining containers indefinitely based solely on open TCP sockets creates a catastrophic vulnerability to socket leaks and dead connections (zombie sockets). This change introduces an explicit, configurable socket inactivity grace period (`socket_grace_ms`) to accurately distinguish genuine waiting jobs from leaked connections.

## What Changes

- **Add `socket_grace_ms` policy parameter**: Configurable duration (default 120,000ms / 2 minutes) allowing containers with active open sockets to remain in `RETAIN` despite zero CPU and zero network traffic.
- **Zombie Socket Detection**: When a container has open sockets but zero network bytes, zero CPU activity, and zero process events for longer than `socket_grace_ms`, the policy treats the connection as leaked/zombie and transitions to standard quiet-window observation for reclamation.
- **Enhanced `interaction-aware` and `resource-multi` policies**: Update decision logic in `simulation/policies.py` to evaluate socket activity and silence duration.
- **Update documentation**: Document v1.1 policy changes, benchmarks, and configuration parameters in `README.md`.

## Capabilities

### New Capabilities
- `idle-detection`: Defines multi-signal idle container classification rules, causal evaluation constraints, and socket inactivity timeout mechanisms.

### Modified Capabilities
None.

## Impact

- **Affected code**: `simulation/policies.py`, `simulation/scoring.py`, `tests/test_policies.py`.
- **Breaking changes**: None. The schema remains backwards-compatible; `socket_grace_ms` defaults to 120000ms if omitted.
