# Tasks

## 1. Persistent identity and authentication

- [x] 1.1 Add the configurable SQLite database, versioned migrations, Argon2id hashing and operator bootstrap. Test repeated migration, account persistence across restart, unique usernames, bootstrap protection and password hash storage. Document the schema, bootstrap and backup procedure.
- [x] 1.2 Implement login, logout, current identity and password change with expiry, Secure cookie defaults, CSRF checks and rate limiting. Test valid login, generic invalid, unknown and disabled login, throttling, expired and revoked cookie replay, password changes and forged requests. Document the session lifetime, cookie and proxy assumptions.
- [x] 1.3 Add the administrator user endpoints and transactional session revocation. Test provisioning, duplicate users, password reset, activation changes, last-admin protection and anonymous/student denial. Document provisioning and the role and permission matrix.

## 2. Workspace and terminal integration

- [x] 2.1 Replace the demo token configuration and API identity checks with authenticated stable IDs. Preserve workspace response fields and gate /stats by administrator role. Test ownership, release, per-user and global limits, FIFO, cleanup and status codes with existing backend fixtures updated to log in. Document the API migration and owner field change.
- [x] 2.2 Use cookie and strict Origin authorization for terminals. Test owner attachment, rejection before Docker attachment, logout, deactivation, password revocation, expiry and slot cleanup. Document the terminal revocation bound.
- [x] 2.3 Adapt the load runner and tests to provision temporary test identities, authenticate distinct clients and preserve synchronized submissions and evidence outputs. Verify fixture tests and report format compatibility. Update load commands and credentials setup in the README.

## 3. Separate browser portals

- [x] 3.1 Add direct login, student and administrator routes and a shared authenticated shell. Update production static serving, Vite proxying and cookie/CSRF requests. Verify direct visits and refresh, role denial, logout, expired-session handling and API routing in the built application.
- [x] 3.2 Move workspace creation, list, personal counts, resource allocation, release, terminal and password settings into the student portal. Verify the complete student workflow and accessible navigation, validation, loading and error states at narrow and wide widths.
- [x] 3.3 Move monitoring into the administrator portal and add student management and effective system settings. Verify account totals and actions, lifecycle and queue views, unavailable telemetry, and restart guidance. Document the new application layout and walkthrough.

## 4. Integrated verification and review

- [x] 4.1 Run backend/scheduler regression tests, repository unit tests, frontend build and lint, and available live Docker tests. Record exact commands, results and reasons for any unexecuted check.
- [x] 4.2 On one Linux Docker host, verify administrator bootstrap and login, creation of two students, both students requesting workspaces and using their own terminals, denial of cross-user workspace and terminal access, administrator visibility, release, cleanup and logout invalidation.
- [x] 4.3 Run authenticated 10- and 100-client experiments in fresh output locations. Verify client counts, peak running cap, timing and outcome artifacts, and confirmed owned cleanup. Update local and EC2 deployment and migration instructions with verified behavior, backup and restore guidance, and limitations.
- [x] 4.4 Open a reviewable pull request from codex/phase-7-auth-portal-separation targeting main. Include architecture, API, RBAC, database migration, test evidence, limitations and manual demo instructions. Verify the PR URL and target branch and leave the PR open for review.
