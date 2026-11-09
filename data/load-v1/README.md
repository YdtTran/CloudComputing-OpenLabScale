# OpenLabScale Concurrent Request-Load Evidence (`load-v1`)

Retained measurements produced by `python -m backend.load suite data/load-v1 --smoke-clients 10 --load-clients 100 --max-sessions 4 --job-seconds 1.0`.

## Scope and Distinction

- **100 simultaneous HTTP clients != 100 running containers or 100 active terminals.**
- In `concurrent-100/`, 100 `asyncio` + `httpx` clients synchronize at a barrier and submit `POST /sessions` concurrently (`concurrent_http_clients = 100`, `active_terminals = 0`).
- Scheduler capacity is bounded to **4 concurrent containers** (`host_cpu_millis = 2500`, `headroom_cpu_millis = 500` -> `2000` CPU millis budget at `500` CPU millis/session; `host_memory_mib = 2048`, `headroom_memory_mib = 512` -> `1536` MiB budget at `256` MiB/session; `max_sessions = 4`).
- Observed `peak_running_containers` is **4** (verified both via live `GET /stats` polling and exact sweep-line overlap of server `[RUNNING, RELEASING)` lifecycle event intervals). The remaining requests queue in FIFO order (`peak_queued_sessions = 100`) and drain as each 1.0s batch job releases its container.

## Environment and Method

- **Run date (UTC):** `2026-11-09T06:57:06Z` (`smoke-10`), `2026-11-09T06:57:11Z` (`concurrent-100`)
- **Platform:** `Linux-6.18.54.1-microsoft-standard-WSL2-x86_64-with-glibc2.41`, Python `3.11.18`, Docker Engine `29.9.2`, cgroup v2, 16 vCPU, 7,933,431,808 bytes RAM, image `alpine:latest`
- **Metrics method:**
  - `admission_latency_ms`: client monotonic latency for `POST /sessions` (`HTTP 202`).
  - `waiting_ms`: server monotonic queue wait duration (`QUEUED -> PROVISIONING`).
  - `provisioning_ms`: server monotonic Docker container create + start duration (`PROVISIONING -> RUNNING`).
  - `execution_ms`: server timestamp delta (`RUNNING -> RELEASING`).
  - `release_ms`: server timestamp delta (`RELEASING -> RELEASED`) after forced container removal.
  - `completion_ms`: client end-to-end duration from synchronized submission to terminal cleanup.
  - `peak_running_containers`: max of admin `GET /stats` samples and exact sweep-line overlap of `[RUNNING, RELEASING)` intervals.

## Files

- `smoke-10/sessions.csv` & `smoke-10/summary.json`: 10-client smoke test (`10` released, `0` failed, `peak_running_containers = 4`, `wall_clock_duration_ms = 4759.292`).
- `concurrent-100/sessions.csv` & `concurrent-100/summary.json`: 100-client concurrent workload (`100` released, `0` failed, `peak_running_containers = 4`, `wall_clock_duration_ms = 64569.675`).
