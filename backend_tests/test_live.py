"""Opt-in integration against the local Linux Docker socket."""

import os
import time
import unittest
from uuid import uuid4

import docker
from fastapi.testclient import TestClient

from backend.api import create_app
from backend.engine import Engine, LABEL, SESSION_LABEL
from backend.models import Settings


@unittest.skipUnless(os.environ.get("OPENLABSCALE_LIVE") == "1", "set OPENLABSCALE_LIVE=1")
class LiveDocker(unittest.TestCase):
    def test_real_session_terminal_fifo_and_restart(self):
        settings = Settings(deployment=f"verify-{uuid4().hex}", tokens={"demo": "admin"}, admin="admin",
                            max_sessions=1, image=os.environ.get("OPENLABSCALE_TEST_IMAGE", "alpine:latest"),
                            poll_seconds=0.1)
        engine = Engine(settings)
        self.addCleanup(engine.client.close)
        self.addCleanup(engine.reconcile)
        leftover = engine.client.containers.create(settings.image, ["sleep", "30"],
                                                    labels={LABEL: settings.deployment, SESSION_LABEL: "leftover"})
        headers = {"Authorization": "Bearer demo"}
        with TestClient(create_app(settings)) as client:
            with self.assertRaises(docker.errors.NotFound):
                leftover.reload()

            def submit():
                response = client.post("/sessions", json={}, headers=headers)
                self.assertEqual(response.status_code, 202, response.text)
                return response.json()["id"]

            def wait(session, state):
                deadline = time.monotonic() + 15
                while time.monotonic() < deadline:
                    row = client.get(f"/sessions/{session}", headers=headers).json()
                    if row["state"] == state:
                        return row
                    if row["state"] == "FAILED":
                        self.fail(row)
                    time.sleep(0.05)
                self.fail(row)

            first, second = submit(), submit()
            running = wait(first, "RUNNING")
            wait(second, "QUEUED")
            container = engine.client.containers.get(running["container_id"])
            host = container.attrs["HostConfig"]
            self.assertEqual(host["NanoCpus"], 500_000_000)
            self.assertEqual(host["Memory"], 256 * 1024**2)
            self.assertEqual(host["PidsLimit"], settings.pids)
            self.assertEqual(host["NetworkMode"], "none")
            self.assertFalse(host["Privileged"])
            self.assertFalse(container.attrs["Mounts"])
            self.assertEqual(container.attrs["Config"]["User"], "65534:65534")
            if engine.client.info()["CgroupVersion"] == "2":
                limits = container.exec_run(["cat", "/sys/fs/cgroup/cpu.max", "/sys/fs/cgroup/memory.max",
                                             "/sys/fs/cgroup/pids.max"])
                self.assertEqual(limits.exit_code, 0)
                cpu, memory, pids = limits.output.decode().splitlines()
                quota, period = map(int, cpu.split())
                self.assertEqual(quota * 2, period)
                self.assertEqual(int(memory), 256 * 1024**2)
                self.assertEqual(int(pids), settings.pids)
            stats = client.get("/stats", headers=headers).json()
            self.assertEqual(stats["active_containers"], 1)
            self.assertGreater(stats["containers"][first]["memory_usage_bytes"], 0)
            self.assertGreater(stats["containers"][first]["cpu_usage_ns"], 0)
            with client.websocket_connect(f"/sessions/{first}/terminal",
                                          subprotocols=["openlabscale", "auth.demo"]) as ws:
                ws.send_text('{"rows":24,"cols":80}')
                ws.send_bytes(b"printf 'user=%s\\n' \"$(id -u)\"\n")
                received = b""
                while b"user=65534" not in received:
                    received += ws.receive_bytes()
            deadline = time.monotonic() + 3
            while any("sh -i" in row[-1] for row in container.top()["Processes"]):
                self.assertLess(time.monotonic(), deadline, "terminal shell survived disconnect")
                time.sleep(0.05)
            with client.websocket_connect(f"/sessions/{first}/terminal",
                                          subprotocols=["openlabscale", "auth.demo"]) as ws:
                self.assertEqual(client.delete(f"/sessions/{first}", headers=headers).status_code, 202)
                while ws.receive()["type"] != "websocket.close":
                    pass
            wait(first, "RELEASED")
            with self.assertRaises(docker.errors.NotFound):
                container.reload()
            wait(second, "RUNNING")
        self.assertEqual(engine.owned(), [])
