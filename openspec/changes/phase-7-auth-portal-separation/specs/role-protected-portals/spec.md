# Role-Protected Portals

## Purpose

Separate students' personal workspace workflows from administrator monitoring and account operations while preserving the existing single-host scheduler.

## ADDED Requirements

### Requirement: Dedicated role-based navigation
The application SHALL provide a login page and separate responsive layouts and navigation at /student and /admin. It SHALL resolve the current role from the server on direct navigation and refresh, provide accessible form labels and loading and error states, and remove demo identity controls.

#### Scenario: Direct protected navigation
- **WHEN** an unauthenticated visitor opens a portal
- **THEN** the application prompts for login and sends a successfully authenticated user to their role's portal

#### Scenario: Student opens administrator portal
- **WHEN** a student navigates directly to /admin
- **THEN** the browser denies that navigation and administrative APIs return 403 independently of browser routing

### Requirement: Personal workspace management
The student portal SHALL show the authenticated username, active and queued counts, personal slot availability, owned workspaces, and workspace creation and account settings. Each workspace SHALL display IDs, state, allocated resources, creation time, queue position and running duration when applicable, with terminal and release actions when supported.

#### Scenario: Student requests resources
- **WHEN** a student submits supported CPU and memory options
- **THEN** the request is owned by their stable user ID and the portal reflects its queue and lifecycle status
- **AND** invalid or unschedulable requests produce a clear error

#### Scenario: Cross-user workspace access
- **WHEN** a student lists workspaces or attempts to read or release another student's workspace
- **THEN** the list contains only the caller's workspaces and direct cross-user requests return 404 without changing the workspace

### Requirement: Scheduler continuity
The service SHALL preserve FIFO ordering, resource reservations, global and per-user limits, lifecycle transitions and deployment-owned cleanup. Revocation SHALL remove authenticated access while existing workspace lifetime and cleanup rules continue to apply.

#### Scenario: Concurrent submissions exceed capacity
- **WHEN** a queued request cannot fit within available capacity or its owner's limit
- **THEN** later requests cannot bypass the queue head and confirmed cleanup returns reserved capacity

### Requirement: Authenticated terminal
The terminal SHALL require a valid login cookie, a trusted explicit Origin, and ownership of a running workspace before attachment. It SHALL reject credentials in URLs or subprotocols and close existing connections promptly on logout, expiry, deactivation or password revocation.

#### Scenario: Owner attaches and releases
- **WHEN** a student opens the terminal of their running workspace and later releases it
- **THEN** the terminal executes in that container, closes on release and the container is cleaned up

#### Scenario: Unauthorized connection
- **WHEN** another student or an administrator attempts to attach to a student's workspace, or a request lacks a trusted Origin
- **THEN** the connection is rejected before Docker attachment

#### Scenario: Credentials are revoked during use
- **WHEN** a terminal's login session expires or is revoked
- **THEN** the terminal closes within the documented revocation bound and subsequent attachment with that cookie fails

### Requirement: Administrator operations
The administrator portal SHALL present account counts, active account counts, running and queued work, available capacity, lifecycle events, host CPU and memory, and container allocation and measured usage when available. The queue view SHALL show FIFO order, owners, wait durations, requested resources and known blocking reasons.

#### Scenario: Administrator inspects operation
- **WHEN** an administrator opens monitoring
- **THEN** the portal shows all workspaces with owner, container ID, state, creation time and duration when applicable, plus queue and capacity information
- **AND** missing or stale telemetry is labeled without estimating values

#### Scenario: Administrator opens settings
- **WHEN** an administrator opens system settings
- **THEN** the portal displays effective validated scheduler limits and identifies startup-only settings as requiring an operator configuration change and restart
