# OpenLabScale single-host backend

OpenLabScale runs real, short-lived Linux workspaces for a trusted university demo. The FastAPI process owns the in-memory session ledger and the Docker SDK client. The existing simulator and measured experiment continue to run independently.

## Start locally

Use Linux, Python 3.10+, and a running Docker Engine with cgroup CPU, memory, swap and PID controls. The backend needs access to the local Unix Docker socket. Docker access is privileged, so run it under a trusted operator account. Use one backend worker per host and retain the same deployment ID across restarts. Choose a deployment ID dedicated to this service.

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r backend/requirements-test.txt
docker pull alpine:latest

export STUDENT_TOKEN=$(python -c 'import secrets; print(secrets.token_urlsafe(32))')
export ADMIN_TOKEN=$(python -c 'import secrets; print(secrets.token_urlsafe(32))')
export OPENLABSCALE_CONFIG=$(python - <<'PY'
import json
import os

print(json.dumps({
    "deployment": "campus-demo",
    "tokens": {os.environ["STUDENT_TOKEN"]: "student", os.environ["ADMIN_TOKEN"]: "operator"},
    "admin": "operator",
    "max_sessions": 1,
}))
PY
)
uvicorn backend.api:create_app --factory --host 127.0.0.1 --port 8000 --workers 1
```

Keep the API on loopback. Use SSH port forwarding for a remote demo and share the student token privately. Each participant needs a separate random token mapped to a server-defined identity. The admin token can inspect all sessions and must stay with the operator. Tokens are static demo credentials. Keep them out of logs, URLs, committed files, and shared shell transcripts. The browser WebSocket origin must match the configured origin. The host, image, and participants are trusted for the demonstration.

## Verify the workflow

In a second shell with the same demo tokens exported, use `curl` and `jq`.

```sh
api=http://127.0.0.1:8000
student="Authorization: Bearer $STUDENT_TOKEN"
admin="Authorization: Bearer $ADMIN_TOKEN"
curl -fsS "$api/health"
submit() {
  curl -fsS -H "$student" -H 'Content-Type: application/json' -d '{}' "$api/sessions" | jq -r .id
}
first=$(submit)
second=$(submit)
curl -fsS -H "$student" "$api/sessions/$first" | jq '{state,events}'
curl -fsS -H "$student" "$api/sessions/$second" | jq '{state,queue_position}'
```

Health returns `{"status":"ok"}`. The first request's events include REQUESTED, QUEUED, PROVISIONING, and RUNNING. Poll until the first reaches RUNNING. The second remains QUEUED at position 1.

```sh
container=$(curl -fsS -H "$student" "$api/sessions/$first" | jq -r .container_id)
docker inspect "$container" --format '{{.State.Status}} {{.Config.User}} {{.HostConfig.NanoCpus}} {{.HostConfig.Memory}} {{.HostConfig.PidsLimit}} {{.HostConfig.NetworkMode}}'
curl -fsS -H "$admin" "$api/stats" | jq '{active_containers, reserved, available, queue, host, containers}'
FIRST="$first" python - <<'PY'
import os
from websockets.sync.client import connect

with connect(
    f"ws://127.0.0.1:8000/sessions/{os.environ['FIRST']}/terminal",
    subprotocols=["openlabscale", "auth." + os.environ["STUDENT_TOKEN"]],
) as ws:
    ws.send('{"rows":24,"cols":80}')
    ws.send(b"printf 'workspace-user=%s\\n' \"$(id -u)\"\n")
    output = b""
    while b"workspace-user=65534" not in output:
        output += ws.recv(timeout=5)
    print(output.decode(errors="replace"))
PY

curl -fsS -X DELETE -H "$student" "$api/sessions/$first" | jq .state
curl -fsS -H "$student" "$api/sessions/$second" | jq .state
```

Inspect should show `running 65534:65534 500000000 268435456 32 none`. The PTY command prints `workspace-user=65534`. After DELETE, poll until the first session is RELEASED and the second is RUNNING. The first container should now be absent.

```sh
docker inspect "$container"  # Expected error for the released container
curl -fsS -X DELETE -H "$student" "$api/sessions/$second" | jq .state
curl -fsS -H "$admin" "$api/stats" | jq '{active_containers,reserved}'
```

Poll stats until the active container count and reservation totals are zero. Stop Uvicorn with Ctrl+C, then run `docker ps -a --filter label=openlabscale.deployment=campus-demo`. The list should be empty. After an interrupted shutdown, start the service with the same deployment ID to reconcile leftovers before accepting work.

## API

HTTP authentication uses `Authorization: Bearer <token>`. Session reads and releases require the owning identity. Invalid credentials return 401. Unknown and other-owned sessions return the same 404. The error envelope contains `detail` and validation failures also include `errors`.

| Method and path | Behavior |
| --- | --- |
| POST `/sessions` | Submit `{}` for defaults or a body such as `{"cpu_millis":500,"memory_mib":256}`. Returns HTTP 202 and a session with `id`, `owner`, `state`, resource limits, queue information, lifecycle events, and nullable container and failure fields. Invalid or impossible requests return 422. |
| GET `/sessions` | List the caller's sessions, including final states. |
| GET `/sessions/{id}` | Read one owned session. `queue_position` is one-based while queued. |
| DELETE `/sessions/{id}` | Request release or cancellation, returning HTTP 202 with the current session. Repeating DELETE leaves a final state intact. |
| GET `/stats` | Admin-only queue, state counts, session history, scheduler budgets and reservations, and Docker and host measurements. |
| GET `/health` | Public liveness and scheduler availability. Docker inventory failure makes admission and health return 503 until recovery. |
| WS `/sessions/{id}/terminal` | Open one interactive PTY for an owned RUNNING session. Offer `openlabscale` and `auth.<token>` as WebSocket subprotocols. The server selects `openlabscale`. Send input and receive output as binary frames. Send JSON text such as `{"rows":24,"cols":80}` to resize. |

## Admission, lifecycle, and recovery

- REQUESTED is recorded on acceptance, then the session enters QUEUED. The scheduler evaluates the queue head in arrival order. A head blocked by CPU, memory, global slots, or the owner's active slot limit blocks later requests. Queue expiry yields FAILED. Deleting a queued session yields CANCELLED.
- The event-loop scheduler checks and reserves CPU, memory, and both slot limits together before entering PROVISIONING. A single background task runs Docker lifecycle calls in a thread. API requests can read or cancel sessions during those calls.
- After startup and inspection, PROVISIONING moves to RUNNING. Provisioning failure or a cancellation racing with creation moves through RELEASING to FAILED or CANCELLED. A running session moves through RELEASING to RELEASED on DELETE, COMPLETED on normal exit or expiry, or FAILED on unexpected exit. RELEASING closes terminal access and keeps the reservation until Docker confirms forced removal or absence.
- Containers carry deployment and session labels. Startup removes matching leftovers and verifies they are gone before opening admission. The worker checks for late orphans during normal operation. Before a create request is sent, the backend writes a marker in `~/.cache/openlabscale/<deployment>/<session-id>.create`. If a create times out and its result is still unknown, the slot remains reserved. A restart reconciles the marker if the object is visible. If startup reports an unresolved marker and Docker never created the object, stop the backend, verify with the Docker operator that the daemon-side request has settled and no matching container exists, then remove that session's marker and retry startup. Shutdown attempts cleanup and logs any reservations that need reconciliation.
- Sessions use a non-root shell, dropped capabilities, no network, a read-only root, bounded writable `/tmp`, no host mounts, and per-container CPU, memory and PID limits. A finite `sleep` workload bounds the container lifetime even if the API process dies. Terminal disconnect closes the socket and terminates the tagged shell. Detached jobs can live until container release or expiry.

## Configuration

Supply a JSON object in `OPENLABSCALE_CONFIG`. The values below are demonstration defaults. Set the host budget and headroom to suit your Docker host. Startup checks the configured host totals against the daemon's CPU and memory inventory. Docker itself enforces per-container limits, and the scheduler enforces the configured aggregate budget.

| Key | Default / meaning |
| --- | --- |
| `deployment`, `tokens`, `admin` | Required. Stable deployment label, bearer-token-to-identity map, and the identity allowed to read stats. |
| `image` | `alpine:latest`. Preload a trusted Linux image with BusyBox-compatible shell utilities and no declared volumes. Startup resolves the local image ID and rejects images that declare volumes. Supply a digest for repeatable demos. |
| `host_cpu_millis`, `headroom_cpu_millis` | 2000 and 500. 1000 millis is one vCPU. |
| `host_memory_mib`, `headroom_memory_mib` | 2048 and 512. The scheduler subtracts headroom before admission. |
| `default_cpu_millis`, `default_memory_mib` | 500 and 256 per request. Requests must specify at least 10 CPU millis and 6 MiB when overriding the defaults. |
| `max_sessions`, `per_user`, `pids` | 20 reserved slots globally, 2 per user, 32 PIDs per container, with a minimum configured limit of 8. CPU and memory may impose lower concurrency. |
| `lifetime_seconds`, `queue_seconds` | 900 seconds running and 300 seconds waiting. |
| `poll_seconds`, `docker_timeout_seconds` | 1 second between maintenance passes and 10 seconds for individual SDK requests. |
| `terminal_origin` | `http://127.0.0.1:8000`. Non-browser clients may omit Origin and still need valid credentials. |

`/stats` distinguishes configured capacity from observations. Docker metrics are cumulative CPU nanoseconds and current memory bytes, keyed by session. Host memory comes from Linux `/proc/meminfo`. Host CPU utilization comes from the difference between successive `/proc/stat` reads. The first sample has a null CPU percentage. Unavailable measurements use null or `available: false`, and samples carry timestamps. Docker and ledger snapshots can differ briefly during state changes.

The ledger and history are process-local and are reset on restart. Startup locking protects a deployment ID under the same operator account. Operate the demo with a single backend instance and one Docker host. Terminal cleanup and scheduling can be delayed by Docker faults. Run the React/Vite frontend (`cd frontend && npm run dev`) on loopback (`127.0.0.1:5173`) to access the Student Portal (`/#student`) and Administrator Dashboard (`/#admin`); both proxy to the loopback backend and require bearer tokens (`GET /stats` is restricted to the configured `admin` identity). EC2 deployment is a later phase.

## Concurrent request-load experiment

`backend/load.py` runs synchronized `asyncio` + `httpx` clients that submit `POST /sessions` concurrently, poll `GET /sessions/{id}` until `RUNNING`, hold each disposable container for a bounded `job_seconds` duration, and call `DELETE /sessions/{id}` with automatic cleanup on timeout or error so the FIFO queue drains completely. An administrator sampler polls `GET /stats` concurrently and reconciles client outcomes against server lifecycle counts and remaining owned Docker containers.

```sh
python -m backend.load suite /tmp/load-run --smoke-clients 10 --load-clients 100 --max-sessions 4 --job-seconds 1.0
```

Each run writes `sessions.csv` and `summary.json` into a fresh output directory (refusing nonempty directories). Retained evidence from the local Linux Docker run (`2026-11-09`, Linux `6.18.54.1-microsoft-standard-WSL2`, Docker Engine `29.9.2`, cgroup v2, 16 vCPU, 7.39 GiB RAM, `alpine:latest`, `host_cpu_millis=2500`, `headroom_cpu_millis=500`, `host_memory_mib=2048`, `headroom_memory_mib=512`, `500` CPU millis and `256` MiB per session, `max_sessions=4`, `job_seconds=1.0`) is stored under `data/load-v1/`:

| Run | Concurrent HTTP clients | Active terminals | Configured container cap | Peak running containers | Released / Failed / Timed out | Admission latency p50 / p95 (ms) | Queue wait p50 / p95 (ms) | Provisioning p50 / p95 (ms) | Completion p50 / p95 (ms) | Cleanup verified |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `data/load-v1/smoke-10` | 10 | 0 | 4 | 4 | 10 / 0 / 0 | 42.80 / 45.58 | 1556.46 / 3312.36 | 202.94 / 236.47 | 3092.32 / 4740.69 | Yes (`0` remaining) |
| `data/load-v1/concurrent-100` | 100 | 0 | 4 | 4 | 100 / 0 / 0 | 285.41 / 315.93 | 34569.21 / 60682.52 | 270.23 / 341.24 | 37326.47 / 62582.87 | Yes (`0` remaining) |

**Important distinction:** `concurrent-100` measures **100 simultaneous HTTP clients** submitting `POST /sessions` requests against a cap of **4 concurrently running containers** (with **0 active browser terminals**). Excess requests remain `QUEUED` and advance in FIFO order as bounded jobs release capacity.

## Tests

```sh
python -m unittest discover -s tests -v
python -m unittest discover -s backend_tests -v
OPENLABSCALE_LIVE=1 python -m unittest discover -s backend_tests -p test_live.py -v
```

The live test uses a unique deployment label, creates a restart leftover, exercises the real session and terminal flow, inspects Docker limits and counters, and verifies queue advancement and cleanup. It requires a preloaded image. Set `OPENLABSCALE_TEST_IMAGE` to choose one.
