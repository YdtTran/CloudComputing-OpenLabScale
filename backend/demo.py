from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from .models import Request, Settings, State, now
from .scheduler import Scheduler

log = logging.getLogger(__name__)

SCENARIOS: dict[str, dict[str, Any]] = {
    "ebpf-contrast": {
        "id": "ebpf-contrast",
        "title": "eBPF Workload Contrast (4 Sessions)",
        "description": "Runs pure-idle, CPU background, VFS tmpfs I/O, and loopback socket IPC concurrently without browser typing to showcase read-only eBPF idle detection.",
        "requests": 4,
        "duration_seconds": 55,
    },
    "fifo-burst-12": {
        "id": "fifo-burst-12",
        "title": "FIFO Contention Burst (12 Requests)",
        "description": "Submits 12 concurrent student requests against the single-host cap so 8 wait in FIFO order and advance slot-by-slot as real workloads finish.",
        "requests": 12,
        "duration_seconds": 10,
    },
    "stress-24": {
        "id": "stress-24",
        "title": "Multi-Tenant Stress (24 Requests / 10 Students)",
        "description": "Launches 24 simultaneous workspace requests across student accounts with mixed CPU, tmpfs I/O, socket, and idle phases under continuous eBPF tracking.",
        "requests": 24,
        "duration_seconds": 8,
    },
}


def _workload_command(kind: str, seconds: int) -> list[str]:
    if kind == "cpu":
        script = (
            f"end=$(($(date +%s)+{seconds})); i=0; "
            "while [ $(date +%s) -lt $end ]; do i=$((i+1)); done"
        )
        return ["/bin/sh", "-c", script]
    if kind == "io":
        script = (
            f"end=$(($(date +%s)+{seconds})); "
            "while [ $(date +%s) -lt $end ]; do "
            "dd if=/dev/zero of=/tmp/demo-io.bin bs=4096 count=16 2>/dev/null; "
            "dd if=/tmp/demo-io.bin of=/dev/null bs=4096 2>/dev/null; "
            "sleep 1; "
            "done; rm -f /tmp/demo-io.bin"
        )
        return ["/bin/sh", "-c", script]
    if kind == "socket":
        script = (
            "nc -lk -p 9020 -e cat >/dev/null 2>&1 & "
            "srv=$!; "
            f"end=$(($(date +%s)+{seconds})); "
            "while [ $(date +%s) -lt $end ]; do "
            "printf 'openlabscale-heartbeat\\n' | nc -w 1 127.0.0.1 9020 >/dev/null 2>&1 || true; "
            "sleep 1; "
            "done; "
            "kill $srv 2>/dev/null || true"
        )
        return ["/bin/sh", "-c", script]
    return ["/bin/sh", "-c", f"sleep {seconds}"]


class DemoRunner:
    """Orchestrate real Docker + eBPF workload demo scenarios strictly scoped to demo-created sessions."""

    def __init__(self, settings: Settings, scheduler: Scheduler, store: Any):
        self.settings = settings
        self.scheduler = scheduler
        self.store = store
        self._task: Optional[asyncio.Task] = None
        self._demo_session_ids: set[str] = set()
        self._session_roles: dict[str, str] = {}
        self.scenario: Optional[str] = None
        self.started_at: Optional[str] = None
        self.finished_at: Optional[str] = None
        self.state = "idle"
        self.message = "Ready to launch a live demo scenario"
        self.total_submitted = 0
        self.completed_count = 0

    def start(self, scenario_id: str) -> dict[str, Any]:
        if scenario_id not in SCENARIOS:
            raise ValueError(f"Unknown demo scenario: {scenario_id}")
        if self._task is not None and not self._task.done():
            raise RuntimeError("A demo scenario is already running; stop it first")
        users = [u for u in self.store.users() if u.get("role") == "student" and u.get("is_active")]
        if not users:
            raise ValueError("No active student accounts available for demo")

        self._demo_session_ids.clear()
        self._session_roles.clear()
        self.scenario = scenario_id
        self.started_at = now().isoformat()
        self.finished_at = None
        self.state = "running"
        self.total_submitted = 0
        self.completed_count = 0
        self.message = f"Running scenario '{scenario_id}' across {len(users)} student account(s)"
        self._task = asyncio.create_task(self._execute(scenario_id, users))
        return self.status()

    async def _run_container_workload(self, session_id: str, kind: str, duration_s: int) -> None:
        try:
            while not self.scheduler.stopping:
                entry = self.scheduler.sessions.get(session_id)
                if entry is None:
                    return
                st = entry.session.state
                if st == State.RUNNING:
                    break
                if st in (State.FAILED, State.CANCELLED, State.RELEASED, State.COMPLETED):
                    self.completed_count += 1
                    return
                await asyncio.sleep(0.2)

            entry = self.scheduler.sessions.get(session_id)
            if entry is None or not entry.session.container_id:
                return
            if kind != "idle":
                cmd = _workload_command(kind, duration_s)
                await asyncio.to_thread(self._exec_in_container, entry.session.container_id, cmd)
            else:
                await asyncio.sleep(duration_s)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.debug("Demo workload ended for %s (%s): %s", session_id, kind, exc)
        finally:
            entry = self.scheduler.sessions.get(session_id)
            if entry is not None and entry.session.state in (State.RUNNING, State.QUEUED, State.PROVISIONING):
                self.scheduler.release(entry)
            self.completed_count += 1

    def _exec_in_container(self, container_id: str, cmd: list[str]) -> None:
        try:
            container = self.scheduler.docker.client.containers.get(container_id)
            container.exec_run(cmd, user="65534:65534")
        except Exception:
            pass

    async def _execute(self, scenario_id: str, students: list[dict[str, Any]]) -> None:
        spec = SCENARIOS[scenario_id]
        count = spec["requests"]
        duration_s = min(spec["duration_seconds"], max(4, self.settings.lifetime_seconds - 5))
        kinds_cycle = ["idle", "cpu", "io", "socket"]
        subtasks: list[asyncio.Task] = []
        try:
            for idx in range(count):
                owner = students[idx % len(students)]["id"]
                kind = kinds_cycle[idx % len(kinds_cycle)]
                session = self.scheduler.submit(owner, Request())
                self._demo_session_ids.add(session.id)
                self._session_roles[session.id] = kind
                self.total_submitted += 1
                subtasks.append(asyncio.create_task(self._run_container_workload(session.id, kind, duration_s)))
            await asyncio.gather(*subtasks, return_exceptions=True)
            if self.state == "running":
                self.state = "completed"
                self.message = f"Scenario '{scenario_id}' finished ({self.completed_count}/{self.total_submitted} sessions processed)"
        except asyncio.CancelledError:
            for t in subtasks:
                t.cancel()
            await asyncio.gather(*subtasks, return_exceptions=True)
            self.state = "stopped"
            self.message = f"Scenario '{scenario_id}' stopped"
            raise
        except Exception as exc:
            log.exception("Demo scenario '%s' failed", scenario_id)
            self.state = "failed"
            self.message = f"Scenario failed: {exc}"
        finally:
            self.finished_at = now().isoformat()

    async def stop(self) -> dict[str, Any]:
        if self._task is not None and not self._task.done():
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
        for sid in list(self._demo_session_ids):
            entry = self.scheduler.sessions.get(sid)
            if entry is not None:
                self.scheduler.release(entry)
        if self.state == "running":
            self.state = "stopped"
            self.message = "Demo workloads released"
            self.finished_at = now().isoformat()
        return self.status()

    def status(self) -> dict[str, Any]:
        active = 0
        for sid in self._demo_session_ids:
            entry = self.scheduler.sessions.get(sid)
            if entry is not None and entry.session.state in (State.REQUESTED, State.QUEUED, State.PROVISIONING, State.RUNNING, State.RELEASING):
                active += 1
        return {
            "state": self.state,
            "scenario": self.scenario,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "total_submitted": self.total_submitted,
            "active_demo_sessions": active,
            "completed_count": self.completed_count,
            "message": self.message,
            "session_roles": dict(self._session_roles),
            "scenarios": list(SCENARIOS.values()),
        }
