# OpenLabScale deployment and operations

OpenLabScale runs a FastAPI service, React portal, FIFO scheduler, and Docker
workspace engine on one Linux host. The offline simulation and measured bundle
workflows are independent.

## Prerequisites

Use a Linux host with Docker, cgroup v2, Python 3.11 or newer, and Node.js and
npm for the frontend build. The backend requires access to the local Docker
Unix socket. Docker socket access gives the service substantial host control,
so run it only on a host and account trusted for that purpose. The backend
uses one worker because the workspace ledger and queue are in memory.

## Local setup

From the repository root, install the backend dependencies and build the UI:

```bash
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements-test.txt
(cd frontend && npm ci && npm run build)
docker image inspect alpine:latest >/dev/null || docker pull alpine:latest
mkdir -p -m 700 ~/.local/share/openlabscale
```

Create the first administrator interactively. The command prompts twice without
echoing the password and refuses to bootstrap a database that already contains
users. Keep passwords out of command arguments, shell history, and files.

```bash
.venv/bin/python -m backend.identity \
  --database ~/.local/share/openlabscale/identity.db --username admin
```

Set the database path to an absolute path and configure a loopback development
origin. Remove the old `tokens` and `admin` fields from existing
`OPENLABSCALE_CONFIG` values.

```bash
export OPENLABSCALE_CONFIG="$(python3 - <<'PY'
import json
from pathlib import Path
print(json.dumps({
    'deployment': 'openlabscale-local',
    'identity_database': str(Path.home() / '.local/share/openlabscale/identity.db'),
    'terminal_origin': 'http://127.0.0.1:8000',
    'secure_cookie': False,
    'host_cpu_millis': 2000,
    'host_memory_mib': 2048,
    'headroom_cpu_millis': 500,
    'headroom_memory_mib': 512,
}))
PY
)"
.venv/bin/python -m uvicorn backend.api:create_app --factory --host 127.0.0.1 --port 8000 --workers 1
```

Visit `http://127.0.0.1:8000/login`, sign in as the administrator, and use
Users to create student accounts. Students sign in at `/student` and
administrators at `/admin`. A student can request CPU and memory, open the
terminal once its workspace is running, and release it. Administrators can
inspect telemetry, the FIFO queue, accounts, and effective system settings.
Configuration changes require a service restart.

For Vite development, run `npm run dev` in `frontend/` and configure the
backend's `terminal_origin` as `http://127.0.0.1:5173`. The Vite proxy
forwards API and WebSocket requests. Build the UI again for production serving.

## Access and role matrix

| Action | Student | Administrator |
| --- | --- | --- |
| Login, logout, change own password | Yes | Yes |
| Request, list, release, and open terminal for own workspaces | Yes | No |
| Read another student's workspace or terminal | No | No |
| View all sessions, queue, capacity, and telemetry | No | Yes |
| List users, create students, activate or deactivate accounts | No | Yes |
| Reset a student password | No | Yes |
| View effective scheduler settings | No | Yes |

The backend enforces role and ownership checks. A workspace owner is the stable
user ID, and unknown and other-owned workspace reads return 404. Deactivation,
password changes, and administrator resets revoke the affected user's login
sessions. Logout revokes the current session. A terminal rechecks its session
at most one second apart under normal operation and closes if the session is
revoked, expired, or cannot be checked. Existing workspaces retain their normal
lifetime and cleanup behavior after access is revoked.

## Authentication and data

Users and login sessions are persisted in SQLite at the configured path.
The `users` table contains a unique immutable ID and username, Argon2id hash,
role, active flag, and creation and update times. The `auth_sessions` table
contains a digest of each random session cookie, a user reference, a CSRF
token, and expiry. Versioned migrations run at startup. Newly created database
files use owner-only permissions. Protect the database directory and backups
with operator-only access.

The opaque cookie is HttpOnly and SameSite=Lax, with an eight-hour absolute
session lifetime. Secure cookies are the default and require a configured
HTTPS origin. An insecure cookie is accepted only when the configured origin is
loopback HTTP. Mutating requests require the configured Origin and an
`X-CSRF-Token` from `GET /auth/me`. Login requires the same Origin. Failed
logins are limited per client address and username in this single process. Rate-limit state
is lost on restart. Deploy behind a trusted HTTPS proxy when remote access is
needed, and configure the public browser origin exactly. Configure Uvicorn's
trusted proxy addresses explicitly and ensure the proxy replaces incoming
forwarded headers. Without trusted forwarding, clients behind a proxy share its
address for rate limiting.

Back up a stopped service's database before upgrading, or use SQLite's online
backup API while the service is running. Store backups outside the repository.
For rollback, stop the new service, keep its database, and restore compatible
code, configuration, and a pre-upgrade database backup together.

## HTTP and WebSocket API

| Endpoint | Behavior |
| --- | --- |
| `POST /auth/login` | Exchange username and password for a login cookie. Invalid credentials use the same 401 response. |
| `GET /auth/me` | Return ID, username, role, and session-bound CSRF token. |
| `POST /auth/logout`, `POST /auth/change-password` | Revoke the current session or change the password and revoke all sessions. |
| `GET /admin/users`, `POST /admin/users` | List accounts or create a student, administrator only. |
| `PATCH /admin/users/{id}` | Change account activation, administrator only. The last active admin cannot be disabled. |
| `POST /admin/users/{id}/reset-password` | Replace a student password and revoke its sessions, administrator only. |
| `POST /sessions`, `GET /sessions` | Request a workspace or list the caller's workspaces. |
| `GET /sessions/{id}`, `DELETE /sessions/{id}` | Inspect or release an owned workspace. |
| `GET /workspace/summary` | Return the student's active and queued counts and personal slot availability. |
| `GET /stats`, `GET /settings` | Return administrator monitoring or effective startup settings. |
| `GET /health` | Return scheduler health. |
| WebSocket `/sessions/{id}/terminal` | Require the login cookie, exact Origin, ownership, a running workspace, and the `openlabscale` subprotocol. |

Missing or invalid authentication returns 401, role and CSRF failures return
403, unknown or foreign workspaces return 404, duplicate usernames return 409,
invalid requests return 422, and login throttling returns 429. The API retains
the workspace response fields, but `owner` now contains a user ID. Static
bearer tokens and the `auth.<token>` terminal subprotocol are removed.

## AWS EC2 and remote operation

Use one Linux EC2 instance with Docker and persistent storage for the database.
Size CPU, memory, and headroom for the host and workload. Keep the Docker socket
and backend private. A loopback-only backend can be reached through SSH local
port forwarding, with the browser origin matching the configured loopback
origin. For direct remote access, terminate HTTPS at a trusted reverse proxy,
set `terminal_origin` to its public HTTPS origin, retain the Secure cookie,
and configure WebSocket forwarding. Restrict network access to intended users
and manage certificates, database backups, host updates, EC2 storage, and
instance costs as part of operations.

The containers share the host kernel. CPU, memory, PID, network, non-root,
read-only filesystem, capability, and lifetime restrictions reduce exposure
but are not a substitute for a hardened multi-tenant isolation boundary.
Session and queue history is in memory and is reset on restart. Startup
reconciliation removes deployment-owned leftovers before admission resumes.

## Verification and cleanup

```bash
python3 -m unittest discover -s tests -v
.venv/bin/python -m unittest discover -s backend_tests -v
(cd frontend && npm run build && npm run lint)
OPENLABSCALE_LIVE=1 .venv/bin/python -m unittest backend_tests.test_live -v
.venv/bin/python -m backend.load suite /tmp/openlabscale-load-new
```

The load workflow provisions temporary accounts and signs in before timing
submissions. Its output directory must be fresh. It records CSV and JSON results
and checks owned-container cleanup. Stop Uvicorn with Ctrl+C after testing.
Only inspect or remove containers carrying the deployment label belonging to
the run being cleaned up. Do not prune unrelated Docker resources.

For an end-to-end check, create two students as the administrator, sign in
as each student, create workspaces, open each owner's terminal, verify
cross-user access is denied, inspect both sessions as administrator, release
the workspaces, and verify logout and cleanup. A live test result applies only
to the host and configuration on which it was run.

On 2026-11-10, a local cgroup v2 Docker host passed the two-student live test.
Authenticated 10- and 100-client runs accepted and released all requests,
with peak running counts of 2 and 4 respectively and no owned containers
remaining. The temporary run artifacts were written under
`/tmp/openlabscale-phase7-load-29Kbf3` and may be removed by the host.
The commands above passed on that host with 45 standard-library tests, 36
backend tests (the two opt-in Docker tests skipped in the ordinary run), both
Docker tests in the opt-in run, and a successful frontend build and lint. The
build reported a JavaScript chunk-size warning.
