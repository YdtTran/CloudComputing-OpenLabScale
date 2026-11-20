# Spec Delta

## Purpose

Provides idle container classification rules, causal telemetry projection constraints, and socket inactivity grace periods to optimize cloud workspace resource reclamation.

## ADDED Requirements

### Requirement: Socket Inactivity Grace Period
The evaluation policy SHALL provide a configurable socket grace duration (`socket_grace_ms`, default 120,000 ms) that protects containers with open sockets from premature reclamation during long-silent network requests.

#### Scenario: Silent wait within grace period
- **WHEN** a container has open established sockets, CPU usage is below threshold, network transfer is zero, and silence duration is less than `socket_grace_ms`
- **THEN** policy emits `RETAIN` with reason `awaiting_socket_response`

### Requirement: Zombie Socket Inactivity Expiration
The evaluation policy SHALL treat open sockets as leaked connections when zero network transfer, zero process events, and sub-threshold CPU persist for at least `socket_grace_ms`.

#### Scenario: Silence exceeds grace duration
- **WHEN** a container maintains open sockets but zero network bytes, zero process events, and zero client interactions persist for at least `socket_grace_ms`
- **THEN** policy ignores the stale sockets and begins quiet window observation toward `IDLE_CANDIDATE`
