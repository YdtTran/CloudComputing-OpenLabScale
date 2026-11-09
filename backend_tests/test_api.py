import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from threading import Event

from fastapi.testclient import TestClient

from backend.api import create_app
from backend.models import Settings


class Docker:
    def __init__(self):
        self.containers = set()
        self.started = Event()
        self.unblock = Event()
        self.unblock.set()
        self.fail_start = False
        self.fail_cleanup = False

    def reconcile(self):
        self.containers.clear()

    def reap_orphans(self, reserved):
        self.containers.intersection_update(reserved)

    def provision(self, session):
        self.containers.add(session.id)
        self.started.set()
        self.unblock.wait(5)
        if self.fail_start:
            raise RuntimeError("startup failed")
        return session.id

    def status(self, session):
        return "running"

    def remove(self, session):
        if self.fail_cleanup:
            raise RuntimeError("cleanup failed")
        self.containers.discard(session.id)

    def telemetry(self):
        return {"active_containers": len(self.containers)}


class API(unittest.TestCase):
    def setUp(self):
        self.docker = Docker()
        self.settings = Settings(deployment="mock", tokens={"a": "alice", "b": "bob", "c": "admin"},
                                 admin="admin", max_sessions=1, poll_seconds=0.02)
        self.client = TestClient(create_app(self.settings, self.docker))
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)
        self.addCleanup(self.docker.unblock.set)

    def request(self, method, path, token="a", **kwargs):
        return self.client.request(method, path, headers={"Authorization": f"Bearer {token}"}, **kwargs)

    def submit(self, token="a", **body):
        response = self.request("POST", "/sessions", token, json=body)
        self.assertEqual(response.status_code, 202, response.text)
        return response.json()["id"]

    def wait(self, session, state, token="a"):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            body = self.request("GET", f"/sessions/{session}", token).json()
            if body.get("state") == state:
                return body
            time.sleep(0.02)
        self.fail(body)

    def test_fifo_and_ownership(self):
        first, second, third = self.submit(), self.submit("b"), self.submit()
        self.wait(first, "RUNNING")
        self.wait(second, "QUEUED", "b")
        self.wait(third, "QUEUED")
        self.assertEqual(self.request("GET", f"/sessions/{first}", "b").status_code, 404)
        self.assertEqual(len(self.request("GET", "/sessions", "b").json()), 1)
        self.assertEqual(self.request("GET", "/stats").status_code, 403)
        self.assertEqual(self.request("GET", "/stats", "c").json()["reserved"]["slots"], 1)
        self.request("DELETE", f"/sessions/{first}")
        self.wait(first, "RELEASED")
        self.wait(second, "RUNNING", "b")
        self.request("DELETE", f"/sessions/{third}")
        self.wait(third, "CANCELLED")
        self.assertEqual(self.client.get("/health").status_code, 200)
        for cpu in (-1, 9):
            self.assertEqual(self.request("POST", "/sessions", json={"cpu_millis": cpu}).status_code, 422)

    def test_concurrent_admission_and_cancellation_during_create(self):
        self.docker.unblock.clear()
        with ThreadPoolExecutor(8) as pool:
            ids = list(pool.map(lambda _: self.submit(), range(8)))
        self.assertTrue(self.docker.started.wait(2))
        rows = self.request("GET", "/sessions").json()
        provisioning = [row["id"] for row in rows if row["state"] == "PROVISIONING"]
        self.assertEqual(len(provisioning), 1)
        self.assertEqual(len(ids), 8)
        self.request("DELETE", f"/sessions/{provisioning[0]}")
        self.assertEqual(self.request("GET", "/stats", "c").json()["reserved"]["slots"], 1)
        self.docker.unblock.set()
        self.wait(provisioning[0], "CANCELLED")
        next_session = next(row["id"] for row in rows if row["queue_position"] == 1)
        self.wait(next_session, "RUNNING")
        self.assertEqual(len(self.docker.containers), 1)

    def test_failure_keeps_capacity_until_cleanup(self):
        self.docker.fail_start = self.docker.fail_cleanup = True
        first = self.submit()
        second = self.submit()
        self.wait(first, "RELEASING")
        self.wait(second, "QUEUED")
        self.docker.fail_start = self.docker.fail_cleanup = False
        self.wait(first, "FAILED")
        self.wait(second, "RUNNING")

    def test_strict_fifo_per_user_and_impossible_request(self):
        # The first session uses one slot and leaves room for Bob, but Alice is at her limit.
        scheduler = self.client.app.state.scheduler
        scheduler.settings.max_sessions = 3
        scheduler.settings.per_user = 1
        first = self.submit()
        self.wait(first, "RUNNING")
        blocked = self.submit()
        later = self.submit("b")
        self.wait(blocked, "QUEUED")
        self.wait(later, "QUEUED", "b")
        self.assertEqual(self.request("POST", "/sessions", json={"cpu_millis": 2000}).status_code, 422)
        self.request("DELETE", f"/sessions/{blocked}")
        self.wait(later, "RUNNING", "b")

    def test_timeout_advances_queue(self):
        self.settings.lifetime_seconds = 1
        first, second = self.submit(), self.submit("b")
        self.wait(first, "RUNNING")
        self.wait(first, "COMPLETED")
        self.wait(second, "RUNNING", "b")
        self.assertNotIn(first, self.docker.containers)

    def test_terminal_ownership_and_disconnect(self):
        import socket
        from fastapi import WebSocketDisconnect

        session = self.submit()
        self.wait(session, "RUNNING")
        path = f"/sessions/{session}/terminal"
        for protocols, headers in [
            (["openlabscale", "auth.b"], {}),
            (["openlabscale", "auth.a"], {"Origin": "https://elsewhere.test"}),
        ]:
            with self.assertRaises(WebSocketDisconnect):
                with self.client.websocket_connect(path, subprotocols=protocols, headers=headers):
                    self.fail("terminal access was granted")
        queued = self.submit("b")
        with self.assertRaises(WebSocketDisconnect):
            with self.client.websocket_connect(f"/sessions/{queued}/terminal",
                                               subprotocols=["openlabscale", "auth.b"]):
                self.fail("queued session allowed terminal access")
        local, remote = socket.socketpair()
        self.addCleanup(local.close)
        self.addCleanup(remote.close)
        self.docker.open_terminal = lambda session: ("terminal", "marker", local, b"")
        self.docker.resize = lambda terminal, rows, cols: None
        remote.settimeout(2)
        with self.client.websocket_connect(path, subprotocols=["openlabscale", "auth.a"]) as ws:
            ws.send_bytes(b"command")
            self.assertEqual(remote.recv(7), b"command")
            remote.sendall(b"output")
            self.assertEqual(ws.receive_bytes(), b"output")
            self.request("DELETE", f"/sessions/{session}")
            self.assertEqual(ws.receive()["type"], "websocket.close")
        self.assertEqual(remote.recv(1), b"")

    def test_cpu_and_memory_budget(self):
        self.settings.max_sessions = 10
        first = self.submit(cpu_millis=1200, memory_mib=1200)
        head = self.submit("b", cpu_millis=400, memory_mib=128)
        tail = self.submit("b", cpu_millis=100, memory_mib=400)
        self.wait(first, "RUNNING")
        self.assertEqual(self.wait(head, "QUEUED", "b")["queue_position"], 1)
        self.assertEqual(self.wait(tail, "QUEUED", "b")["queue_position"], 2)
        self.request("DELETE", f"/sessions/{head}", "b")
        self.assertEqual(self.wait(tail, "QUEUED", "b")["queue_position"], 1)
        self.request("DELETE", f"/sessions/{first}")
        self.wait(tail, "RUNNING", "b")
        self.request("DELETE", f"/sessions/{first}")
        self.wait(first, "RELEASED")

    def test_queue_expiry(self):
        self.settings.queue_seconds = 1
        first, second = self.submit(), self.submit("b")
        self.wait(first, "RUNNING")
        self.assertEqual(self.wait(second, "FAILED", "b")["failure"], "Queue deadline exceeded")

    def test_admin_stats_telemetry_and_access_control(self):
        self.assertEqual(self.client.get("/stats").status_code, 401)
        self.assertEqual(self.request("GET", "/stats", "a").status_code, 403)
        self.assertEqual(self.request("GET", "/stats", "b").status_code, 403)
        samples = [
            {
                "host": {"available": True, "cpu_total_ticks": 1000, "cpu_idle_ticks": 800,
                         "memory_total_bytes": 1024, "memory_used_bytes": 512, "sampled_at": "2026-11-09T06:00:00Z"},
                "active_containers": 1,
                "containers": {"s1": {"available": True, "cpu_usage_ns": 500_000_000,
                                      "memory_usage_bytes": 64 * 1024**2, "sampled_at": "2026-11-09T06:00:00Z"}},
            },
            {
                "host": {"available": True, "cpu_total_ticks": 1200, "cpu_idle_ticks": 950,
                         "memory_total_bytes": 1024, "memory_used_bytes": 512, "sampled_at": "2026-11-09T06:00:02Z"},
                "active_containers": None,
                "containers": None,
            },
        ]
        self.docker.telemetry = lambda: samples.pop(0)
        first = self.request("GET", "/stats", "c").json()
        self.assertIsNone(first["host"]["cpu_utilization_pct"])
        self.assertEqual(first["containers"]["s1"]["memory_usage_bytes"], 64 * 1024**2)
        second = self.request("GET", "/stats", "c").json()
        self.assertAlmostEqual(second["host"]["cpu_utilization_pct"], 25.0)
        self.assertIsNone(second["active_containers"])
        self.assertIsNone(second["containers"])


class TerminalCancellation(unittest.IsolatedAsyncioTestCase):
    async def test_cancel_waiting_for_docker_attach(self):
        import asyncio
        import socket
        from unittest.mock import AsyncMock, Mock

        from backend.models import Session
        from backend.scheduler import Entry
        from backend.terminal import bridge

        local, peer = socket.socketpair()
        self.addCleanup(local.close)
        self.addCleanup(peer.close)
        started, unblock = Event(), Event()
        engine = Mock()

        def open_terminal(session):
            started.set()
            unblock.wait(2)
            return "terminal", "marker", local, b""

        engine.open_terminal.side_effect = open_terminal
        entry = Entry(Session(id="cancel", owner="alice", cpu_millis=500, memory_mib=256))
        entry.terminal_attached = True
        websocket = AsyncMock()
        task = asyncio.create_task(bridge(websocket, entry, engine))
        self.assertTrue(await asyncio.to_thread(started.wait, 2))
        task.cancel()
        unblock.set()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(local.fileno(), -1)
        self.assertFalse(entry.terminal_attached)
        engine.close_terminal.assert_called_once_with(entry.session, "marker")
