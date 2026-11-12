# User Authentication

## Purpose

Give students and administrators persistent identities and revocable access to the classroom workspace service.

## ADDED Requirements

### Requirement: Persistent accounts
The service SHALL persist accounts with stable IDs, unique usernames, Argon2id password hashes, student or admin roles, activation state and creation and update timestamps. The database SHALL use a configurable persistent location and versioned, nondestructive schema migrations.

#### Scenario: Backend restarts
- **WHEN** an operator upgrades or restarts the backend with the existing database
- **THEN** existing accounts keep their IDs, roles and credentials

### Requirement: Credential login and current identity
The service SHALL authenticate active accounts through POST /auth/login and return the current authenticated identity through GET /auth/me. Failed credential checks SHALL return the same generic 401 for unknown, disabled and wrong-password accounts. The service SHALL rate-limit repeated failed login attempts.

#### Scenario: Successful credentials
- **WHEN** an active account submits valid credentials within the rate limit
- **THEN** a fresh opaque server-managed session is issued in an HttpOnly, SameSite cookie and the identity endpoint returns the account ID, username and role

#### Scenario: Repeated failures
- **WHEN** attempts exceed the login limit
- **THEN** the service returns 429 without disclosing whether the username exists

#### Scenario: Secure deployment
- **WHEN** served over HTTPS
- **THEN** the cookie also has Secure and the session secret is absent from response bodies, URLs, browser storage and application logs

### Requirement: Session expiry and revocation
The service SHALL reject expired, revoked and inactive-account sessions. Logout SHALL revoke the current session and clear the cookie. Deactivation, password change and administrative password reset SHALL revoke all sessions for the affected user.

#### Scenario: Password change
- **WHEN** an authenticated user changes their password after verifying their current password
- **THEN** prior credentials and all prior sessions lose access and the user can sign in with the new password

#### Scenario: Session replay
- **WHEN** a client presents an expired cookie or replays a cookie after logout, deactivation or password reset
- **THEN** authenticated endpoints return 401

### Requirement: Request forgery protection
The service SHALL reject unsafe browser requests from untrusted origins, including login, and require a session-bound CSRF proof for authenticated mutations.

#### Scenario: Cross-origin mutation
- **WHEN** a request presents a valid cookie with an untrusted Origin or a missing or invalid CSRF proof
- **THEN** the service returns 403 without applying the mutation

### Requirement: Administrator bootstrap and account management
The service SHALL provide an operator-only command to bootstrap the initial administrator and admin-only APIs to list users, create students, change activation and reset student passwords. Public registration and role mutation SHALL be unavailable. The last active administrator SHALL remain protected from deactivation.

#### Scenario: Authorized provisioning
- **WHEN** an administrator creates a student with a unique username
- **THEN** the student can log in and account responses omit passwords, hashes and session secrets

#### Scenario: Deactivation and reactivation
- **WHEN** an administrator deactivates and later reactivates a student
- **THEN** the student must sign in again and retains the same user ID

#### Scenario: Unauthorized user listing
- **WHEN** an anonymous caller or a student requests the user directory
- **THEN** the server returns 401 or 403 respectively
