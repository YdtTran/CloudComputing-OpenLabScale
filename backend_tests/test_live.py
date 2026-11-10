"""Opt-in integration against the local Linux Docker socket."""

import os
import tempfile
from pathlib import Path
import time
import unittest
from uuid import uuid4

import docker
from fastapi.testclient import TestClient

from backend.api import create_app
from backend.engine import Engine, LABEL, SESSION_LABEL
from backend.models import Settings
from backend.identity import IdentityStore
from backend.auth import COOKIE


@unittest.skipUnless(os.environ.get("OPENLABSCALE_LIVE") == "1", "set OPENLABSCALE_LIVE=1")
class LiveDocker(unittest.TestCase):
    def test_real_session_terminal_fifo_and_restart(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        database = Path(directory.name) / 'users.db'
        store = IdentityStore(database)
        store.migrate()
        store.bootstrap('admin', 'password')
        store.create_student('student', 'password')
        settings = Settings(deployment=f"verify-{uuid4().hex}", identity_database=str(database), secure_cookie=False,
                            max_sessions=1, image=os.environ.get("OPENLABSCALE_TEST_IMAGE", "alpine:latest"),
                            poll_seconds=0.1)
        engine = Engine(settings)
        self.addCleanup(engine.client.close)
        self.addCleanup(engine.reconcile)
        leftover = engine.client.containers.create(settings.image, ["sleep", "30"],
                                                    labels={LABEL: settings.deployment, SESSION_LABEL: "leftover"})
        with TestClient(create_app(settings), headers={'origin': settings.terminal_origin}) as client:
            def authenticate(username):
                response = client.post('/auth/login', json={'username': username, 'password': 'password'})
                self.assertEqual(response.status_code, 200, response.text)
                cookie = response.cookies[COOKIE]
                headers = {'cookie': f'{COOKIE}={cookie}', 'origin': settings.terminal_origin}
                headers['x-csrf-token'] = client.get('/auth/me', headers=headers).json()['csrf']
                return headers

            headers = authenticate('student')
            admin_headers = authenticate('admin')
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
            stats = client.get("/stats", headers=admin_headers).json()
            self.assertEqual(stats["active_containers"], 1)
            self.assertGreater(stats["containers"][first]["memory_usage_bytes"], 0)
            self.assertGreater(stats["containers"][first]["cpu_usage_ns"], 0)
            with client.websocket_connect(f"/sessions/{first}/terminal",
                                          subprotocols=["openlabscale"], headers=headers) as ws:
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
                                          subprotocols=["openlabscale"], headers=headers) as ws:
                self.assertEqual(client.delete(f"/sessions/{first}", headers=headers).status_code, 202)
                while ws.receive()["type"] != "websocket.close":
                    pass
            wait(first, "RELEASED")
            with self.assertRaises(docker.errors.NotFound):
                container.reload()
            wait(second, "RUNNING")
        self.assertEqual(engine.owned(), [])

    def test_two_students_are_isolated_and_cleanup(self):
        from fastapi import WebSocketDisconnect

        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        database = Path(directory.name) / 'users.db'
        store = IdentityStore(database)
        store.migrate()
        store.bootstrap('admin', 'password')
        settings = Settings(deployment=f"verify-{uuid4().hex}", identity_database=str(database), secure_cookie=False,
                            image=os.environ.get('OPENLABSCALE_TEST_IMAGE', 'alpine:latest'), poll_seconds=0.1)
        with TestClient(create_app(settings), headers={'origin': settings.terminal_origin}) as client:
            def login(username):
                response = client.post('/auth/login', json={'username': username, 'password': 'password'})
                self.assertEqual(response.status_code, 200, response.text)
                headers = {'origin': settings.terminal_origin, 'cookie': f"{COOKIE}={response.cookies[COOKIE]}"}
                headers['x-csrf-token'] = client.get('/auth/me', headers=headers).json()['csrf']
                return headers

            admin = login('admin')
            for name in ('alice', 'bob'):
                response = client.post('/admin/users', headers=admin, json={'username': name, 'password': 'password'})
                self.assertEqual(response.status_code, 201, response.text)
            alice, bob = login('alice'), login('bob')
            workspaces = []
            for headers in (alice, bob):
                response = client.post('/sessions', headers=headers, json={})
                self.assertEqual(response.status_code, 202, response.text)
                workspaces.append(response.json()['id'])
            deadline = time.monotonic() + 20
            for session_id, headers in zip(workspaces, (alice, bob)):
                while True:
                    response = client.get(f'/sessions/{session_id}', headers=headers)
                    self.assertEqual(response.status_code, 200)
                    state = response.json()['state']
                    if state == 'RUNNING':
                        break
                    self.assertNotIn(state, ('FAILED', 'CANCELLED'))
                    self.assertLess(time.monotonic(), deadline)
                    time.sleep(0.1)
                with client.websocket_connect(f'/sessions/{session_id}/terminal', headers=headers,
                                              subprotocols=['openlabscale']) as ws:
                    ws.send_bytes(b"printf 'phase7-terminal-ok\\n'\\n")
                    output = b''
                    while b'phase7-terminal-ok' not in output:
                        output += ws.receive_bytes()
            self.assertEqual(client.get(f'/sessions/{workspaces[1]}', headers=alice).status_code, 404)
            with self.assertRaises(WebSocketDisconnect):
                with client.websocket_connect(f'/sessions/{workspaces[1]}/terminal', headers=alice,
                                              subprotocols=['openlabscale']):
                    self.fail('Cross-user terminal access was granted')
            stats = client.get('/stats', headers=admin).json()
            self.assertEqual(stats['counts']['RUNNING'], 2)
            for session_id, headers in zip(workspaces, (alice, bob)):
                self.assertEqual(client.delete(f'/sessions/{session_id}', headers=headers).status_code, 202)
            for session_id, headers in zip(workspaces, (alice, bob)):
                while client.get(f'/sessions/{session_id}', headers=headers).json()['state'] != 'RELEASED':
                    self.assertLess(time.monotonic(), deadline)
                    time.sleep(0.1)
            self.assertEqual(client.post('/auth/logout', headers=alice).status_code, 204)
            self.assertEqual(client.get('/sessions', headers=alice).status_code, 401)
            self.assertEqual(client.get('/stats', headers=admin).json()['reserved']['slots'], 0)
