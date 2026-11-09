# Design

## Context

FastAPI currently maps bearer credentials through Settings.tokens, compares the resulting owner to Settings.admin for /stats, and uses the owner string for scheduler accounting. The WebSocket handshake looks up a credential in an auth subprotocol and currently accepts a missing Origin. React App.tsx uses a demo identity selector and hash-based portal switcher. Vite proxies current API paths, and the built frontend is mounted through StaticFiles. The load runner creates demo tokens and attributes its results to those identities.

## Goals / Non-Goals

- Keep FastAPI, React/Vite/TypeScript/Tailwind, xterm.js, the Docker engine and the existing scheduler. Keep login sessions distinct from in-memory workspace lifecycle records.
- Preserve the single-process, single-host deployment and existing reconciliation on restart. Keep role editing and live scheduler configuration outside this phase.

## Decisions

### SQLite identity and session storage

Use a versioned SQLite schema with a users table containing an immutable string ID, unique username, password hash, role, activation state, and timestamps. An auth_sessions table holds a unique digest of a random opaque cookie value, user ID foreign key, expiry and a session-bound CSRF value. Enable foreign keys per connection, bound lock waits and apply migrations transactionally. Password hashing uses Argon2id with bounded input and hashing concurrency, outside the event loop. Keep password changes and session invalidation atomic, and ensure a concurrent login cannot issue a session using credentials changed or disabled during verification.

Opaque sessions fit the requested revocation model because HTTP and terminals can consult the same authoritative store. Keep an absolute expiry with an eight-hour initial default and prune expired rows. Use a session cookie with Path=/, HttpOnly, SameSite=Lax and Secure by default. Allow an explicit insecure development setting only for loopback HTTP. Keep SQLite files and backups accessible only to the service operator. Bootstrap the initial admin with a non-echoing password prompt, using a transaction to enforce one-time initialization.

### API and authorization

POST /auth/login issues the cookie. GET /auth/me returns ID, username, role and the CSRF value. POST /auth/logout revokes the current session, and POST /auth/change-password verifies the old password, replaces its hash and revokes all sessions. Apply no-store to identity and credential responses. Require an exact configured browser origin on unsafe routes, including login, and a CSRF header for authenticated mutations. Use bounded, process-local login throttling by source and normalized username, with uniform credential failures and bounded counter retention. Trust forwarded client addresses only from an explicitly configured proxy.

GET and POST /admin/users list users and create students. PATCH /admin/users/{id} changes activation, and POST /admin/users/{id}/reset-password replaces a student's password. Keep mutations transactional, reject role fields and enforce the last-active-admin invariant. GET /stats remains admin-only and may add account totals and safe owner display names. Keep /health available for health checks. Use 401 for missing or invalid login, 403 for role or CSRF rejection, 404 for foreign workspaces, 409 for duplicate usernames, 422 for invalid inputs and 429 for throttling.

Workspace routes stay student-scoped and retain their methods and response shapes. The owner string now contains the stable user ID. Read personal slot limits and scheduler counts from the backend so React can show admission-relevant availability without approximating ownership rules. Use /stats for administrators' read-only cross-user visibility.

### Browser and terminal integration

Serve the SPA explicitly at /login, /student and /admin, with any required portal subroutes constrained to their prefixes. Preserve API precedence and JSON errors for /admin/users and other API routes. Configure the Vite proxy to distinguish admin API paths from the SPA and preserve the original trusted browser Origin during WebSocket forwarding. Resolve identity before rendering protected content, and clear stale portal state on 401 or sign-out.

Authenticate the WebSocket cookie and Origin before acquiring the existing terminal attachment slot. Retain the application subprotocol and terminal bridge. Recheck session validity at intervals of at most one second while attached, terminating on failed validation and releasing the attachment slot through the bridge cleanup path. Deactivation, password change and reset affect all of that user's terminals. Logout affects terminals using the revoked login session. The scheduler still owns workspace expiry and cleanup.

### Operational settings

Expose effective scheduler settings with restart guidance. Current budgets and limits are startup inputs used directly by admission and reservation code, so changing those inputs live would require defining how to handle already reserved capacity. Compute queue wait and report blocking reasons from existing scheduler state and checks.

## Risks / Trade-offs

- SQLite write contention → Keep transactions short, keep password hashing outside write transactions, and avoid writes on session reads.
- Terminal revocation lag → Check within the one-second polling interval under normal operation, close on store errors and test cleanup of the bridge and its attachment slot.
- Cookie and origin mismatch → Test built same-origin serving, Vite loopback proxying, and HTTPS with the configured public origin.
- Revocation leaves a workspace consuming capacity → Existing expiry and owned cleanup still bound its lifetime.
- Rate-limit counters reset on backend restart → Document the process-local scope and test time-window behavior deterministically.

## Migration Plan

1. Back up any identity database before upgrading. Configure a persistent database path and explicit trusted origin, remove demo token and admin identity fields, and set up HTTPS or loopback-only development.
2. Drain active demo workspaces before deployment. Existing workspace state is in memory and startup reconciliation handles deployment-owned leftovers. Bootstrap the administrator and provision students with fresh passwords.
3. Deploy the frontend, backend and authenticated load tooling together. Use temporary databases and distinct provisioned accounts for the load runs. Keep historical evidence as recorded.
4. To roll back, stop the new service, retain its database and backups, and restore the old code and configuration together. Restore a compatible database backup if rolling back a schema migration within the new service.
