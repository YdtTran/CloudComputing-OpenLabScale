# Proposal

## Why

OpenLabScale's static demo credentials and shared portal switcher make it difficult to operate as a classroom service with distinct student accounts and administrators. Phase 7 introduces persistent identity and separate portals while preserving the single-host workspace lifecycle.

## What Changes

- Add SQLite-backed accounts, Argon2id passwords, revocable cookie sessions, password changes, and administrator-managed student provisioning.
- Add dedicated login, student, and administrator routes with server-enforced role and ownership checks.
- Authenticate terminal connections with the login cookie and enforce origin, ownership, and revocation throughout the connection.
- Preserve FIFO, resource reservations, per-user and global capacity, lifecycle cleanup, and real telemetry. Adapt both load experiments to provision and authenticate test accounts.
- **BREAKING** Remove demo bearer tokens, the terminal auth subprotocol, token configuration, and hash-based portal navigation. Workspace owner values become stable user IDs.
- Keep deployment on one Linux Docker host. Public registration, role editing, external identity providers, and multi-host orchestration are outside this phase.

## Capabilities

### New Capabilities

- `user-auth` — Persistent identity, sessions, account administration, and request protections.
- `role-protected-portals` — Student workspace access, administrator operations, and authenticated terminal behavior.

### Modified Capabilities

## Impact

Touches FastAPI routes and settings, workspace and terminal authorization, React navigation and API calls, test fixtures and load tooling, and local and EC2 deployment documentation. The completed single-host demo change defines the scheduler and telemetry baseline. Its capability deltas have yet to be published as main specs, so this proposal adds separate capabilities.
