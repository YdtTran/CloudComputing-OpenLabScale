## Purpose

Provide controlled access to short-lived Linux containers on a single Docker host with predictable admission and cleanup.

## ADDED Requirements

### Requirement: Resource-aware FIFO admission
The service SHALL reserve configured CPU, memory and session slots atomically before provisioning and SHALL admit eligible queued requests in FIFO order.

#### Scenario: Head cannot fit temporarily
- **WHEN** concurrent requests exceed available capacity and the head is waiting for capacity
- **THEN** later requests remain queued until the head is admitted, cancelled, or expires

#### Scenario: Request cannot ever fit
- **WHEN** requested resources exceed the configured total budget
- **THEN** the service rejects the request before adding it to the queue

### Requirement: Owned lifecycle and cleanup
The service SHALL enforce non-root execution, restricted capabilities, disabled networking, CPU, memory, PID and lifetime limits. It SHALL retain reservations until cleanup is confirmed and reconcile only deployment-owned containers before admission on startup.

#### Scenario: Cancellation races with provisioning
- **WHEN** a session is cancelled while Docker creation is in flight
- **THEN** the service resolves the creation outcome and confirms the owned container is absent before returning capacity

#### Scenario: Backend restarts with leftover containers
- **WHEN** owned containers remain after a crash
- **THEN** admission stays closed until owned leftovers are removed and unrelated containers remain untouched

### Requirement: Student terminal and release
A student SHALL be able to request a session, view queue or lifecycle status, attach to a running owned container through a browser terminal, and release the session.

#### Scenario: Student uses and releases an owned session
- **WHEN** the owner opens the terminal, runs a command and requests release
- **THEN** the command runs inside that container, release closes the terminal and cleanup makes capacity available

#### Scenario: Another identity attempts access
- **WHEN** a different student requests status, terminal access or release for the session
- **THEN** the service denies access without exposing terminal output or changing the session
