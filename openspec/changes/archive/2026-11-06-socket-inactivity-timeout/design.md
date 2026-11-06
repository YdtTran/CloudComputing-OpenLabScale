# Design: Socket Inactivity Timeout (v1.1)

## Context

See `proposal.md` for motivation. Currently, `simulation/policies.py` treats `socket_events == 0` during observation windows as quietness. In `simulation/scenarios.py`, the `network-wait` scenario represents an active job waiting up to 120,000ms for a remote response, producing 0 network bytes during the wait and triggering False Positive reclaims.

## Goals / Non-Goals

**Goals:**
- Eliminate False Positive reclaims on `network-wait` workloads without sacrificing detection on dead/leaked connections.
- Maintain deterministic, zero-dependency Python stdlib compatibility.
- Ensure the two-clock causal gate remains strictly enforced.

**Non-Goals:**
- Modifying the live C eBPF collector in this change (addressed in future kernel probe rollout).
- Modifying the underlying v1 schema column definitions (schema remains `1.0` backward-compatible).

## Decisions

### Decision 1: Track `socket_silent_start` per session policy instance
- **Rationale**: Tracking elapsed silence duration since the last observable network traffic or CPU activity allows differentiating between an active wait ($< \text{socket\_grace\_ms}$) and a leaked connection ($\ge \text{socket\_grace\_ms}$).
- **Alternative considered**: Relying solely on `active_sockets > 0`. Rejected because leaked sockets would prevent container reclamation indefinitely.

### Decision 2: Default `socket_grace_ms = 120000` (2 minutes)
- **Rationale**: Aligns with common HTTP client timeouts (60–120s) and covers the synthetic `network-wait` scenario (120,000ms) while keeping wasted resource time bounded if a socket leak occurs.
- **Alternative considered**: 300,000ms (5 minutes). Too permissive for synthetic benchmark runs.

## Risks / Trade-offs

- **[Risk] Long keepalive pings without work** → Mitigation: If an application emits recurring keepalive packets, network bytes are non-zero and keep the session active; this is expected behavior for active connections.
- **[Trade-off] Increased detection latency for genuine leaked sockets** → Mitigated by bounding grace time to 120s.
