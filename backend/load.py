"""Reproducible asyncio + httpx concurrent session load generator and evidence exporter."""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import platform
import socket
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from uuid import uuid4

import httpx
import uvicorn

from .api import create_app
from .engine import Engine
from .models import Settings, State, now

TERMINAL = {State.COMPLETED.value, State.CANCELLED.value, State.RELEASED.value, State.FAILED.value}
CSV_COLUMNS = (
    "client_id", "owner", "session_id", "container_id", "http_status", "final_state",
    "timed_out", "cleanup_pending", "admission_latency_ms", "initial_queue_position",
    "max_queue_position", "waiting_ms", "provisioning_ms", "execution_ms", "release_ms",
    "completion_ms", "requested_at", "queued_at", "provisioning_at", "running_at",
    "releasing_at", "finished_at", "failure",
)


def reserve_output(output: Path | str) -> Path:
    root = Path(output)
    root.mkdir(parents=True, exist_ok=True)
    if any(root.iterdir()):
        raise ValueError(f"{root}: refusing nonempty output directory")
    return root


def parse_ts(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def delta_ms(start: Optional[str], end: Optional[str]) -> Optional[float]:
    t0, t1 = parse_ts(start), parse_ts(end)
    if t0 is None or t1 is None:
        return None
    return round(max(0.0, (t1 - t0).total_seconds() * 1000.0), 3)


def sweep_peak(intervals: list[tuple[Optional[str], Optional[str]]]) -> int:
    points: list[tuple[datetime, int]] = []
    for start_raw, end_raw in intervals:
        start, end = parse_ts(start_raw), parse_ts(end_raw)
        if start is not None and end is not None and end >= start:
            points.append((start, 1))
            points.append((end, -1))
    points.sort(key=lambda item: (item[0], item[1]))
    current = peak = 0
    for _, change in points:
        current += change
        if current > peak:
            peak = current
    return peak


def summarize_ms(values: list[float]) -> dict:
    clean = sorted(v for v in values if v is not None)
    if not clean:
        return {"count": 0, "min": None, "p50": None, "p95": None, "max": None, "mean": None}

    def pct(p: float) -> float:
        idx = min(len(clean) - 1, max(0, int(round((len(clean) - 1) * p))))
        return round(clean[idx], 3)

    return {
        "count": len(clean),
        "min": round(clean[0], 3),
        "p50": pct(0.50),
        "p95": pct(0.95),
        "max": round(clean[-1], 3),
        "mean": round(sum(clean) / len(clean), 3),
    }


def host_platform_info(docker_client=None) -> dict:
    info = {
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "cpu_count": os.cpu_count(),
    }
    if docker_client is not None:
        try:
            daemon = docker_client.info()
            info["docker"] = {
                "server_version": daemon.get("ServerVersion"),
                "cgroup_version": daemon.get("CgroupVersion"),
                "os_type": daemon.get("OSType"),
                "operating_system": daemon.get("OperatingSystem"),
                "ncpu": daemon.get("NCPU"),
                "mem_total_bytes": daemon.get("MemTotal"),
            }
        except Exception:
            info["docker"] = None
    return info


async def _run_client(
    idx: int,
    token: str,
    owner: str,
    client: httpx.AsyncClient,
    barrier: asyncio.Barrier,
    *,
    cpu_millis: int,
    memory_mib: int,
    job_seconds: float,
    wait_timeout_seconds: float,
    release_timeout_seconds: float,
    poll_seconds: float,
    cancel_when_queued: bool = False,
) -> dict:
    client_id = f"client-{idx:03d}"
    await barrier.wait()
    t0 = time.monotonic()
    response = await client.post(
        "/sessions",
        headers={"Authorization": f"Bearer {token}"},
        json={"cpu_millis": cpu_millis, "memory_mib": memory_mib},
    )
    admission_ms = round((time.monotonic() - t0) * 1000.0, 3)
    if response.status_code != 202:
        detail = response.json().get("detail") if response.headers.get("content-type", "").startswith("application/json") else response.text
        return {
            "client_id": client_id, "owner": owner, "session_id": None, "container_id": None,
            "http_status": response.status_code, "final_state": "REJECTED",
            "timed_out": False, "cleanup_pending": False, "admission_latency_ms": admission_ms,
            "initial_queue_position": None, "max_queue_position": None,
            "waiting_ms": None, "provisioning_ms": None, "execution_ms": None,
            "release_ms": None, "completion_ms": admission_ms,
            "requested_at": None, "queued_at": None, "provisioning_at": None,
            "running_at": None, "releasing_at": None, "finished_at": None,
            "failure": str(detail),
        }

    session = response.json()
    session_id = session["id"]
    headers = {"Authorization": f"Bearer {token}"}
    initial_q = session.get("queue_position")
    max_q = initial_q
    timed_out = False
    released = False

    try:
        if cancel_when_queued:
            del_resp = await client.delete(f"/sessions/{session_id}", headers=headers)
            session = del_resp.json()
            released = True
        else:
            deadline = time.monotonic() + wait_timeout_seconds
            while session["state"] not in TERMINAL and session["state"] != State.RUNNING.value:
                if time.monotonic() >= deadline:
                    timed_out = True
                    break
                q_wait = poll_seconds * min(4, max(1, (session.get("queue_position") or 1) // 4))
                await asyncio.sleep(min(q_wait, max(0.0, deadline - time.monotonic())))
                poll_resp = await client.get(f"/sessions/{session_id}", headers=headers)
                session = poll_resp.json()
                qpos = session.get("queue_position")
                if qpos is not None:
                    if initial_q is None:
                        initial_q = qpos
                    max_q = max(max_q or qpos, qpos)

            if session["state"] == State.RUNNING.value and not timed_out:
                if job_seconds > 0:
                    await asyncio.sleep(job_seconds)
                del_resp = await client.delete(f"/sessions/{session_id}", headers=headers)
                session = del_resp.json()
                released = True
    finally:
        if not released and session.get("state") not in TERMINAL:
            try:
                del_resp = await client.delete(f"/sessions/{session_id}", headers=headers)
                if del_resp.status_code == 202:
                    session = del_resp.json()
            except Exception:
                pass

    cleanup_deadline = time.monotonic() + release_timeout_seconds
    while (session["state"] not in TERMINAL or session.get("cleanup_pending")) and time.monotonic() < cleanup_deadline:
        await asyncio.sleep(poll_seconds)
        poll_resp = await client.get(f"/sessions/{session_id}", headers=headers)
        session = poll_resp.json()

    completion_ms = round((time.monotonic() - t0) * 1000.0, 3)
    events = {event["state"]: event["at"] for event in session.get("events", [])}
    final_state = session["state"]
    finished_at = events.get(final_state)
    waiting_ms = (
        round(session["queue_seconds"] * 1000.0, 3)
        if session.get("queue_seconds") is not None
        else delta_ms(events.get("QUEUED"), events.get("PROVISIONING") or finished_at)
    )
    provisioning_ms = (
        round(session["provisioning_seconds"] * 1000.0, 3)
        if session.get("provisioning_seconds") is not None
        else delta_ms(events.get("PROVISIONING"), events.get("RUNNING") or events.get("RELEASING"))
    )
    execution_ms = delta_ms(events.get("RUNNING"), events.get("RELEASING"))
    release_ms = delta_ms(events.get("RELEASING"), finished_at)
    failure = session.get("failure")
    if timed_out and not failure:
        failure = "Client wait timeout exceeded"

    return {
        "client_id": client_id,
        "owner": owner,
        "session_id": session_id,
        "container_id": session.get("container_id"),
        "http_status": response.status_code,
        "final_state": final_state,
        "timed_out": timed_out,
        "cleanup_pending": bool(session.get("cleanup_pending")),
        "admission_latency_ms": admission_ms,
        "initial_queue_position": initial_q,
        "max_queue_position": max_q,
        "waiting_ms": waiting_ms,
        "provisioning_ms": provisioning_ms,
        "execution_ms": execution_ms,
        "release_ms": release_ms,
        "completion_ms": completion_ms,
        "requested_at": events.get("REQUESTED"),
        "queued_at": events.get("QUEUED"),
        "provisioning_at": events.get("PROVISIONING"),
        "running_at": events.get("RUNNING"),
        "releasing_at": events.get("RELEASING"),
        "finished_at": finished_at,
        "failure": failure,
    }


async def execute_load(
    *,
    output_dir: Optional[Path | str] = None,
    clients: int = 10,
    users: Optional[int] = None,
    max_sessions: int = 4,
    per_user: int = 2,
    host_cpu_millis: int = 2500,
    headroom_cpu_millis: int = 500,
    host_memory_mib: int = 2048,
    headroom_memory_mib: int = 512,
    cpu_millis: int = 500,
    memory_mib: int = 256,
    job_seconds: float = 1.0,
    lifetime_seconds: int = 30,
    queue_seconds: int = 180,
    wait_timeout_seconds: float = 180.0,
    release_timeout_seconds: float = 30.0,
    poll_seconds: float = 0.05,
    client_poll_seconds: float = 0.05,
    stats_interval_seconds: float = 0.15,
    image: str = "alpine:latest",
    deployment: Optional[str] = None,
    engine=None,
    use_asgi: bool = False,
    cancel_clients: frozenset[int] = frozenset(),
) -> dict:
    root = reserve_output(output_dir) if output_dir is not None else None
    user_count = users or clients
    tokens = {f"token-{i:03d}": f"student-{i:03d}" for i in range(1, user_count + 1)}
    admin_token = "token-admin"
    tokens[admin_token] = "admin"
    deployment_id = deployment or f"load-{uuid4().hex[:12]}"
    settings = Settings(
        deployment=deployment_id,
        tokens=tokens,
        admin="admin",
        image=image,
        host_cpu_millis=host_cpu_millis,
        headroom_cpu_millis=headroom_cpu_millis,
        host_memory_mib=host_memory_mib,
        headroom_memory_mib=headroom_memory_mib,
        default_cpu_millis=cpu_millis,
        default_memory_mib=memory_mib,
        max_sessions=max_sessions,
        per_user=per_user,
        lifetime_seconds=lifetime_seconds,
        queue_seconds=queue_seconds,
        poll_seconds=poll_seconds,
    )
    configured_cap = min(
        settings.max_sessions,
        settings.cpu_budget // cpu_millis,
        settings.memory_budget // memory_mib,
        user_count * settings.per_user,
    )

    app = create_app(settings, engine=engine)
    server = None
    server_task = None
    sock = None
    lifespan_ctx = None
    transport = None
    base_url = "http://127.0.0.1:8000"

    try:
        if use_asgi:
            lifespan_ctx = app.router.lifespan_context(app)
            await lifespan_ctx.__aenter__()
            transport = httpx.ASGITransport(app=app)
        else:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
            base_url = f"http://127.0.0.1:{port}"
            config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", access_log=False)
            server = uvicorn.Server(config)
            server_task = asyncio.create_task(server.serve(sockets=[sock]))
            while not server.started:
                if server_task.done():
                    server_task.result()
                await asyncio.sleep(0.02)

        limits = httpx.Limits(max_connections=max(200, clients + 20), max_keepalive_connections=max(100, clients + 10))
        async with httpx.AsyncClient(base_url=base_url, transport=transport, limits=limits, timeout=30.0) as http:
            stats_samples: list[dict] = []
            stop_sampling = asyncio.Event()

            async def sample_stats() -> None:
                headers = {"Authorization": f"Bearer {admin_token}"}
                while not stop_sampling.is_set():
                    try:
                        resp = await http.get("/stats", headers=headers)
                        if resp.status_code == 200:
                            stats_samples.append(resp.json())
                    except Exception:
                        pass
                    try:
                        await asyncio.wait_for(stop_sampling.wait(), stats_interval_seconds)
                    except asyncio.TimeoutError:
                        pass

            sampler_task = asyncio.create_task(sample_stats())
            barrier = asyncio.Barrier(clients)
            run_started_at = now().isoformat()
            wall_t0 = time.monotonic()

            tasks = []
            for idx in range(1, clients + 1):
                user_idx = ((idx - 1) % user_count) + 1
                token = f"token-{user_idx:03d}"
                owner = tokens[token]
                tasks.append(
                    asyncio.create_task(
                        _run_client(
                            idx, token, owner, http, barrier,
                            cpu_millis=cpu_millis, memory_mib=memory_mib,
                            job_seconds=job_seconds,
                            wait_timeout_seconds=wait_timeout_seconds,
                            release_timeout_seconds=release_timeout_seconds,
                            poll_seconds=client_poll_seconds,
                            cancel_when_queued=(idx in cancel_clients),
                        )
                    )
                )

            rows = await asyncio.gather(*tasks)
            wall_clock_ms = round((time.monotonic() - wall_t0) * 1000.0, 3)
            stop_sampling.set()
            await sampler_task

            final_resp = await http.get("/stats", headers={"Authorization": f"Bearer {admin_token}"})
            final_stats = final_resp.json()
            stats_samples.append(final_stats)

        docker_client = getattr(app.state.scheduler.docker, "client", None)
        platform_meta = host_platform_info(docker_client)
        remaining_owned = 0
        if hasattr(app.state.scheduler.docker, "owned"):
            remaining_owned = len(await asyncio.to_thread(app.state.scheduler.docker.owned))
        elif hasattr(app.state.scheduler.docker, "containers"):
            remaining_owned = len(app.state.scheduler.docker.containers)
    finally:
        if lifespan_ctx is not None:
            await lifespan_ctx.__aexit__(None, None, None)
        if server is not None and server_task is not None:
            server.should_exit = True
            await server_task
        if sock is not None:
            sock.close()

    rows.sort(key=lambda r: r["client_id"])
    state_counts = Counter(r["final_state"] for r in rows)

    peak_running_stats = max(
        [
            max(s.get("active_containers") or 0, s.get("counts", {}).get(State.RUNNING.value, 0))
            for s in stats_samples
        ] or [0]
    )
    peak_reserved_stats = max([s.get("reserved", {}).get("slots", 0) for s in stats_samples] or [0])
    peak_queued_stats = max([len(s.get("queue", [])) for s in stats_samples] or [0])
    peak_queued_clients = max([r["max_queue_position"] or 0 for r in rows] or [0])

    peak_running_events = sweep_peak([(r["running_at"], r["releasing_at"]) for r in rows])
    peak_reserved_events = sweep_peak([(r["provisioning_at"], r["finished_at"]) for r in rows])
    peak_running = max(peak_running_stats, peak_running_events)
    peak_reserved = max(peak_reserved_stats, peak_reserved_events)

    server_counts = final_stats.get("counts", {})
    accepted_rows = [r for r in rows if r["session_id"] is not None]
    client_terminal_counts = Counter(r["final_state"] for r in accepted_rows)
    counts_match = all(
        server_counts.get(state, 0) == client_terminal_counts.get(state, 0)
        for state in (State.RELEASED.value, State.COMPLETED.value, State.FAILED.value, State.CANCELLED.value)
    ) and final_stats.get("total_sessions") == len(accepted_rows)
    capacity_reclaimed = (
        final_stats.get("reserved", {}).get("slots") == 0
        and final_stats.get("reserved", {}).get("cpu_millis") == 0
        and final_stats.get("reserved", {}).get("memory_mib") == 0
        and (final_stats.get("active_containers") in (0, None))
        and len(final_stats.get("queue", [])) == 0
        and remaining_owned == 0
    )

    summary = {
        "run_date": run_started_at,
        "completed_at": now().isoformat(),
        "semantics_note": (
            f"{clients} simultaneous HTTP clients submitted POST /sessions requests concurrently. "
            f"At most {peak_running} containers ran simultaneously (configured cap: {configured_cap}), "
            "and 0 interactive browser terminals were attached during this batch API workload."
        ),
        "platform": platform_meta,
        "configuration": {
            "deployment": deployment_id,
            "image": image,
            "clients": clients,
            "users": user_count,
            "max_sessions": max_sessions,
            "per_user": per_user,
            "host_cpu_millis": host_cpu_millis,
            "headroom_cpu_millis": headroom_cpu_millis,
            "cpu_budget_millis": settings.cpu_budget,
            "host_memory_mib": host_memory_mib,
            "headroom_memory_mib": headroom_memory_mib,
            "memory_budget_mib": settings.memory_budget,
            "request_cpu_millis": cpu_millis,
            "request_memory_mib": memory_mib,
            "configured_max_concurrent_containers": configured_cap,
            "job_seconds": job_seconds,
            "lifetime_seconds": lifetime_seconds,
            "queue_seconds": queue_seconds,
            "wait_timeout_seconds": wait_timeout_seconds,
            "poll_seconds": poll_seconds,
            "client_poll_seconds": client_poll_seconds,
            "stats_interval_seconds": stats_interval_seconds,
        },
        "metrics_method": {
            "admission_latency_ms": "Client monotonic elapsed time for POST /sessions HTTP 202 response.",
            "waiting_ms": "Server-recorded monotonic queue residence duration (QUEUED -> PROVISIONING/terminal).",
            "provisioning_ms": "Server-recorded monotonic Docker container create+start duration (PROVISIONING -> RUNNING/RELEASING).",
            "execution_ms": "Timestamp delta between RUNNING and RELEASING lifecycle events.",
            "release_ms": "Timestamp delta between RELEASING and terminal lifecycle event after container removal.",
            "completion_ms": "Client monotonic elapsed time from synchronized POST /sessions submission to terminal cleanup.",
            "peak_running_containers": "Maximum of admin GET /stats active container samples and exact sweep-line overlap of server [RUNNING, RELEASING) lifecycle intervals.",
        },
        "outcomes": {
            "submitted_clients": clients,
            "accepted_sessions": len(accepted_rows),
            "released": state_counts.get(State.RELEASED.value, 0),
            "completed": state_counts.get(State.COMPLETED.value, 0),
            "failed": state_counts.get(State.FAILED.value, 0),
            "cancelled": state_counts.get(State.CANCELLED.value, 0),
            "rejected_http": state_counts.get("REJECTED", 0),
            "timed_out": sum(1 for r in rows if r["timed_out"]),
            "active_terminals": 0,
        },
        "concurrency": {
            "concurrent_http_clients": clients,
            "active_terminals": 0,
            "configured_max_concurrent_containers": configured_cap,
            "peak_running_containers": peak_running,
            "peak_running_from_stats": peak_running_stats,
            "peak_running_from_events": peak_running_events,
            "peak_reserved_slots": peak_reserved,
            "peak_reserved_from_stats": peak_reserved_stats,
            "peak_reserved_from_events": peak_reserved_events,
            "peak_queued_sessions": max(peak_queued_stats, peak_queued_clients),
            "stats_samples_collected": len(stats_samples),
            "limits_respected": peak_running <= configured_cap and peak_reserved <= configured_cap,
        },
        "timings_ms": {
            "wall_clock_duration_ms": wall_clock_ms,
            "admission_latency_ms": summarize_ms([r["admission_latency_ms"] for r in rows if r["admission_latency_ms"] is not None]),
            "waiting_ms": summarize_ms([r["waiting_ms"] for r in rows if r["waiting_ms"] is not None]),
            "provisioning_ms": summarize_ms([r["provisioning_ms"] for r in rows if r["provisioning_ms"] is not None]),
            "execution_ms": summarize_ms([r["execution_ms"] for r in rows if r["execution_ms"] is not None]),
            "release_ms": summarize_ms([r["release_ms"] for r in rows if r["release_ms"] is not None]),
            "completion_ms": summarize_ms([r["completion_ms"] for r in rows if r["completion_ms"] is not None]),
        },
        "reconciliation": {
            "final_stats_total_sessions": final_stats.get("total_sessions"),
            "final_stats_counts": server_counts,
            "final_reserved": final_stats.get("reserved"),
            "final_active_containers": final_stats.get("active_containers"),
            "final_queue_length": len(final_stats.get("queue", [])),
            "remaining_owned_containers": remaining_owned,
            "counts_match": counts_match,
            "capacity_reclaimed": capacity_reclaimed,
        },
    }

    if root is not None:
        with (root / "sessions.csv").open("w", encoding="utf-8", newline="\n") as handle:
            writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
        with (root / "summary.json").open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(summary, handle, indent=2, sort_keys=True)
            handle.write("\n")

    return {"summary": summary, "sessions": rows}


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run OpenLabScale concurrent session load experiment.")
    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="Execute a single bounded concurrent load run.")
    run_p.add_argument("output", help="Fresh output directory for sessions.csv and summary.json")
    run_p.add_argument("--clients", type=int, default=10)
    run_p.add_argument("--max-sessions", type=int, default=4)
    run_p.add_argument("--per-user", type=int, default=2)
    run_p.add_argument("--host-cpu-millis", type=int, default=2500)
    run_p.add_argument("--headroom-cpu-millis", type=int, default=500)
    run_p.add_argument("--host-memory-mib", type=int, default=2048)
    run_p.add_argument("--headroom-memory-mib", type=int, default=512)
    run_p.add_argument("--cpu-millis", type=int, default=500)
    run_p.add_argument("--memory-mib", type=int, default=256)
    run_p.add_argument("--job-seconds", type=float, default=1.0)
    run_p.add_argument("--lifetime-seconds", type=int, default=30)
    run_p.add_argument("--queue-seconds", type=int, default=180)
    run_p.add_argument("--wait-timeout-seconds", type=float, default=180.0)
    run_p.add_argument("--image", default=os.environ.get("OPENLABSCALE_TEST_IMAGE", "alpine:latest"))

    suite_p = sub.add_parser("suite", help="Run 10-client smoke test followed by 100-client workload.")
    suite_p.add_argument("output_root", help="Fresh parent directory for smoke-10/ and concurrent-100/")
    suite_p.add_argument("--smoke-clients", type=int, default=10)
    suite_p.add_argument("--load-clients", type=int, default=100)
    suite_p.add_argument("--max-sessions", type=int, default=4)
    suite_p.add_argument("--job-seconds", type=float, default=1.0)
    suite_p.add_argument("--image", default=os.environ.get("OPENLABSCALE_TEST_IMAGE", "alpine:latest"))

    args = parser.parse_args(argv)
    if args.command == "run":
        result = asyncio.run(
            execute_load(
                output_dir=args.output,
                clients=args.clients,
                max_sessions=args.max_sessions,
                per_user=args.per_user,
                host_cpu_millis=args.host_cpu_millis,
                headroom_cpu_millis=args.headroom_cpu_millis,
                host_memory_mib=args.host_memory_mib,
                headroom_memory_mib=args.headroom_memory_mib,
                cpu_millis=args.cpu_millis,
                memory_mib=args.memory_mib,
                job_seconds=args.job_seconds,
                lifetime_seconds=args.lifetime_seconds,
                queue_seconds=args.queue_seconds,
                wait_timeout_seconds=args.wait_timeout_seconds,
                image=args.image,
            )
        )
        print(json.dumps(result["summary"], indent=2, sort_keys=True))
        return 0

    root = reserve_output(args.output_root)
    smoke = asyncio.run(
        execute_load(
            output_dir=root / f"smoke-{args.smoke_clients}",
            clients=args.smoke_clients,
            max_sessions=args.max_sessions,
            job_seconds=args.job_seconds,
            image=args.image,
        )
    )
    load = asyncio.run(
        execute_load(
            output_dir=root / f"concurrent-{args.load_clients}",
            clients=args.load_clients,
            max_sessions=args.max_sessions,
            job_seconds=args.job_seconds,
            image=args.image,
        )
    )
    print(json.dumps({"smoke": smoke["summary"], "concurrent": load["summary"]}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
