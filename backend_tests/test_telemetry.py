from __future__ import annotations

import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock

from fastapi.testclient import TestClient

from backend.api import create_app
from backend.auth import COOKIE
from backend.engine import Engine
from backend.identity import IdentityStore
from backend.models import Session, Settings, State
from backend.telemetry import ObservabilityTracker


def make_settings(**overrides) -> Settings:
    base = dict(
        deployment="unit-obs",
        identity_database="unused.db",
        terminal_origin="http://127.0.0.1:8000",
        secure_cookie=False,
        enable_ebpf=True,
        idle_cpu_threshold_pct=1.0,
        idle_quiet_seconds=10.0,
        interaction_grace_seconds=5.0,
        stale_threshold_seconds=8.0,
    )
    base.update(overrides)
    return Settings(**base)


def make_session(sid: str = "sess1", owner: str = "u1") -> Session:
    return Session(id=sid, owner=owner, cpu_millis=500, memory_mib=256, state=State.RUNNING, container_id="cid-" + sid)


def cg_sample(cgid: int, usage_ns: int, mono_s: float, mem: int = 32 * 1024**2, psi_io: float = 0.0) -> dict:
    return {
        "cgroup_id": cgid,
        "usage_ns": usage_ns,
        "quota_ratio": 0.5,
        "memory_bytes": mem,
        "blk_read_bytes": 0,
        "blk_write_bytes": 0,
        "blk_io_ops": 0,
        "psi_cpu_some_avg10": 0.0,
        "psi_io_some_avg10": psi_io,
        "mono_ns": int(mono_s * 1_000_000_000),
    }


def ebpf_snap(
    cgid: int,
    mono_s: float,
    *,
    exec_c: int = 0,
    fork_c: int = 0,
    exit_c: int = 0,
    io_r: int = 0,
    io_w: int = 0,
    io_ops: int = 0,
    sock_rx: int = 0,
    sock_tx: int = 0,
    sock_ops: int = 0,
    loss_count: int = 0,
    comm: str | None = None,
    status: str = "OK",
) -> dict:
    return {
        "status": status,
        "reason": "Attached" if status == "OK" else "Failed",
        "probes": ["sched:sched_process_exec", "fexit:vfs_read", "fexit:vfs_write"],
        "loss_count": loss_count,
        "last_snapshot_mono": mono_s,
        "last_snapshot_at": "2026-11-17T01:00:00Z",
        "cgroups": {
            cgid: {
                "exec": exec_c,
                "fork": fork_c,
                "exit": exit_c,
                "io_read_bytes": io_r,
                "io_write_bytes": io_w,
                "io_events": io_ops,
                "sock_rx_bytes": sock_rx,
                "sock_tx_bytes": sock_tx,
                "socket_events": sock_ops,
            }
        },
        "recent_comm": ({cgid: comm} if comm else {}),
        "tracked_cgroups": [cgid],
    }


class ObservabilityUnitTests(unittest.TestCase):
    def test_unknown_when_ebpf_disabled_stale_or_loss(self):
        session = make_session()
        disabled = ObservabilityTracker(make_settings(enable_ebpf=False))
        for t in (1.0, 3.0):
            res = disabled.observe(
                [session],
                {"sess1": {"available": True, "cpu_usage_ns": int(t * 1000), "memory_usage_bytes": 1024, "sampled_at": "2026-11-17T01:00:00Z"}},
                cgroup_reader=lambda _: cg_sample(42, int(t * 1000), t),
                pid_lookup=lambda _: 123,
                now_mono=t,
            )
        entry = res["containers"]["sess1"]
        self.assertEqual(entry["signal_quality"]["status"], "DEGRADED")
        self.assertEqual(entry["recommendation"]["decision"], "UNKNOWN")

        tracker = ObservabilityTracker(make_settings())
        tracker.observe(
            [session], None,
            ebpf_snapshot=ebpf_snap(42, 1.0),
            cgroup_reader=lambda _: cg_sample(42, 0, 1.0),
            pid_lookup=lambda _: 123,
            now_mono=1.0,
        )
        # Stale snapshot (> 8s old) must abstain as UNKNOWN
        stale_res = tracker.observe(
            [session], None,
            ebpf_snapshot=ebpf_snap(42, 1.0),
            cgroup_reader=lambda _: cg_sample(42, 0, 12.0),
            pid_lookup=lambda _: 123,
            now_mono=12.0,
        )
        self.assertEqual(stale_res["containers"]["sess1"]["signal_quality"]["status"], "STALE")
        self.assertEqual(stale_res["containers"]["sess1"]["recommendation"]["decision"], "UNKNOWN")

        # Loss delta > 0 must mark DEGRADED and abstain as UNKNOWN
        loss_res = tracker.observe(
            [session], None,
            ebpf_snapshot=ebpf_snap(42, 14.0, loss_count=2),
            cgroup_reader=lambda _: cg_sample(42, 0, 14.0),
            pid_lookup=lambda _: 123,
            now_mono=14.0,
        )
        self.assertEqual(loss_res["containers"]["sess1"]["signal_quality"]["status"], "DEGRADED")
        self.assertEqual(loss_res["containers"]["sess1"]["recommendation"]["decision"], "UNKNOWN")

    def test_io_socket_and_cpu_background_stay_active_without_browser_input(self):
        session = make_session()
        tracker = ObservabilityTracker(make_settings())
        tracker.observe(
            [session], None,
            ebpf_snapshot=ebpf_snap(42, 1.0),
            cgroup_reader=lambda _: cg_sample(42, 0, 1.0),
            pid_lookup=lambda _: 123,
            now_mono=1.0,
        )
        # Quiet CPU (0%) but active VFS tmpfs I/O
        io_res = tracker.observe(
            [session], None,
            ebpf_snapshot=ebpf_snap(42, 3.0, io_w=65536, io_ops=16),
            cgroup_reader=lambda _: cg_sample(42, 0, 3.0),
            pid_lookup=lambda _: 123,
            now_mono=3.0,
        )
        rec = io_res["containers"]["sess1"]["recommendation"]
        self.assertEqual(rec["decision"], "ACTIVE")
        self.assertIn("VFS I/O", rec["reason"])

        # Quiet CPU + IO, active socket communication
        sock_res = tracker.observe(
            [session], None,
            ebpf_snapshot=ebpf_snap(42, 5.0, io_w=65536, io_ops=16, sock_rx=128, sock_ops=2),
            cgroup_reader=lambda _: cg_sample(42, 0, 5.0),
            pid_lookup=lambda _: 123,
            now_mono=5.0,
        )
        self.assertEqual(sock_res["containers"]["sess1"]["recommendation"]["decision"], "ACTIVE")
        self.assertIn("Socket", sock_res["containers"]["sess1"]["recommendation"]["reason"])

    def test_interaction_grace_and_pure_idle_transition_and_cgroup_reset(self):
        session = make_session()
        tracker = ObservabilityTracker(make_settings(idle_quiet_seconds=10.0, interaction_grace_seconds=6.0))
        tracker.record_interaction("sess1", "terminal_input", now_mono=10.0, now_utc="2026-11-17T01:00:10Z")

        for t in (1.0, 2.0, 13.0):
            res = tracker.observe(
                [session], None,
                ebpf_snapshot=ebpf_snap(42, t),
                cgroup_reader=lambda _, ts=t: cg_sample(42, 0, ts),
                pid_lookup=lambda _: 123,
                now_mono=t,
            )
        # At t=13.0: quiet for 11s (>=10s), but interaction was 3s ago (<6s grace) -> ACTIVE
        self.assertEqual(res["containers"]["sess1"]["recommendation"]["decision"], "ACTIVE")
        self.assertIn("grace", res["containers"]["sess1"]["recommendation"]["reason"])

        # At t=17.0: interaction was 7s ago (>=6s grace) and quiet 15s (>=10s) -> IDLE_CANDIDATE (read-only)
        idle_res = tracker.observe(
            [session], None,
            ebpf_snapshot=ebpf_snap(42, 17.0),
            cgroup_reader=lambda _: cg_sample(42, 0, 17.0),
            pid_lookup=lambda _: 123,
            now_mono=17.0,
        )
        rec = idle_res["containers"]["sess1"]["recommendation"]
        self.assertEqual(rec["decision"], "IDLE_CANDIDATE")
        self.assertTrue(rec["read_only"])

        # Cgroup ID changes (container restarted) -> must reset baseline & abstain UNKNOWN
        reset_res = tracker.observe(
            [session], None,
            ebpf_snapshot=ebpf_snap(99, 19.0),
            cgroup_reader=lambda _: cg_sample(99, 0, 19.0),
            pid_lookup=lambda _: 124,
            now_mono=19.0,
        )
        self.assertEqual(reset_res["containers"]["sess1"]["recommendation"]["decision"], "UNKNOWN")

    def test_api_stats_exposes_observability_safely(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / "users.db"
            store = IdentityStore(db)
            store.migrate()
            store.bootstrap("admin", "password")
            store.create_student("alice", "password")
            engine = Mock()
            engine.reconcile.return_value = None
            engine.check_runtime.return_value = None
            engine.provision.return_value = "cid-1"
            engine.status.return_value = "running"
            engine.remove.return_value = None
            engine.reap_orphans.return_value = None
            engine.telemetry.return_value = {
                "host": {"available": False},
                "active_containers": 1,
                "containers": {},
            }
            settings = make_settings(identity_database=str(db), enable_ebpf=False)
            with TestClient(create_app(settings, engine=engine), headers={"origin": settings.terminal_origin}) as client:
                r = client.post("/auth/login", json={"username": "admin", "password": "password"})
                headers = {"origin": settings.terminal_origin, "cookie": f"{COOKIE}={r.cookies[COOKIE]}"}
                stats = client.get("/stats", headers=headers).json()
                self.assertIn("observability", stats)
                self.assertIn("demo", stats)
                self.assertTrue(stats["observability"]["read_only"])
                self.assertEqual(stats["observability"]["ebpf"]["status"], "UNAVAILABLE")

                # Student cannot trigger demo endpoints; unknown scenario is rejected with 422
                alice_login = client.post("/auth/login", json={"username": "alice", "password": "password"})
                alice_hdr = {"origin": settings.terminal_origin, "cookie": f"{COOKIE}={alice_login.cookies[COOKIE]}"}
                alice_hdr["x-csrf-token"] = client.get("/auth/me", headers=alice_hdr).json()["csrf"]
                self.assertEqual(client.post("/admin/demo/run", headers=alice_hdr, json={"scenario": "ebpf-contrast"}).status_code, 403)
                headers["x-csrf-token"] = client.get("/auth/me", headers=headers).json()["csrf"]
                self.assertEqual(client.post("/admin/demo/run", headers=headers, json={"scenario": "nonexistent"}).status_code, 422)
                self.assertEqual(client.get("/admin/demo", headers=headers).json()["state"], "idle")


@unittest.skipUnless(os.environ.get("OPENLABSCALE_LIVE") == "1", "set OPENLABSCALE_LIVE=1")
class LiveEbpfObservabilityTests(unittest.TestCase):
    def test_live_ebpf_io_socket_exec_and_idle_contrast(self):
        from uuid import uuid4

        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / "users.db"
            store = IdentityStore(db)
            store.migrate()
            store.bootstrap("admin", "password")
            settings = Settings(
                deployment=f"ebpf-{uuid4().hex[:8]}",
                identity_database=str(db),
                secure_cookie=False,
                enable_ebpf=True,
                max_sessions=2,
                per_user=1,
                poll_seconds=0.5,
                idle_quiet_seconds=3.0,
                interaction_grace_seconds=2.0,
                stale_threshold_seconds=8.0,
                image=os.environ.get("OPENLABSCALE_TEST_IMAGE", "alpine:latest"),
            )
            engine = Engine(settings)
            self.addCleanup(engine.client.close)
            self.addCleanup(engine.reconcile)

            with TestClient(create_app(settings), headers={"origin": settings.terminal_origin}) as client:
                def login(username):
                    resp = client.post("/auth/login", json={"username": username, "password": "password"})
                    self.assertEqual(resp.status_code, 200, resp.text)
                    headers = {"origin": settings.terminal_origin, "cookie": f"{COOKIE}={resp.cookies[COOKIE]}"}
                    headers["x-csrf-token"] = client.get("/auth/me", headers=headers).json()["csrf"]
                    return headers

                admin = login("admin")
                for student in ("idle_u", "busy_u"):
                    self.assertEqual(
                        client.post("/admin/users", headers=admin, json={"username": student, "password": "password"}).status_code,
                        201,
                    )
                idle_hdr, busy_hdr = login("idle_u"), login("busy_u")
                idle_sid = client.post("/sessions", headers=idle_hdr, json={}).json()["id"]
                busy_sid = client.post("/sessions", headers=busy_hdr, json={}).json()["id"]

                deadline = time.monotonic() + 20
                sessions = {}
                for sid, hdr in ((idle_sid, idle_hdr), (busy_sid, busy_hdr)):
                    while True:
                        row = client.get(f"/sessions/{sid}", headers=hdr).json()
                        if row["state"] == "RUNNING":
                            sessions[sid] = row
                            break
                        self.assertLess(time.monotonic(), deadline)
                        time.sleep(0.1)

                # Wait for eBPF baseline & grace window to establish OK status
                busy_active_io = False
                idle_reached = False
                deadline = time.monotonic() + 20
                while time.monotonic() < deadline:
                    # Continuously drive real VFS tmpfs I/O + loopback socket inside busy container
                    if not busy_active_io:
                        busy_container = engine.client.containers.get(sessions[busy_sid]["container_id"])
                        busy_container.exec_run(
                            ["sh", "-c", "dd if=/dev/zero of=/tmp/work.bin bs=4096 count=8 2>/dev/null; nc -lk -p 9011 -e cat >/dev/null 2>&1 & sleep 0.1; printf 'ebpf-live\\n' | nc -w 1 127.0.0.1 9011 >/dev/null || true"],
                            user="65534:65534",
                        )
                    stats = client.get("/stats", headers=admin).json()
                    obs = stats["observability"]["ebpf"]
                    self.assertEqual(obs["status"], "OK", obs)
                    self.assertGreaterEqual(len(obs["probes"]), 7)
                    busy_sample = stats["containers"].get(busy_sid, {})
                    idle_sample = stats["containers"].get(idle_sid, {})
                    busy_sig = busy_sample.get("signals") or {}
                    if (busy_sig.get("io_write_bytes_total") or 0) >= 32768 and (busy_sig.get("sock_tx_bytes_total") or 0) > 0:
                        if busy_sample.get("recommendation", {}).get("decision") == "ACTIVE":
                            busy_active_io = True
                    if idle_sample.get("recommendation", {}).get("decision") == "IDLE_CANDIDATE":
                        idle_reached = True
                    if busy_active_io and idle_reached:
                        # Confirm read-only: idle candidate container is still RUNNING!
                        self.assertEqual(client.get(f"/sessions/{idle_sid}", headers=idle_hdr).json()["state"], "RUNNING")
                        break
                    time.sleep(0.8)

                self.assertTrue(busy_active_io, f"busy container did not register VFS+socket ACTIVE: {stats['containers'].get(busy_sid)}")
                self.assertTrue(idle_reached, f"idle container did not reach IDLE_CANDIDATE: {stats['containers'].get(idle_sid)}")

                for sid, hdr in ((idle_sid, idle_hdr), (busy_sid, busy_hdr)):
                    self.assertEqual(client.delete(f"/sessions/{sid}", headers=hdr).status_code, 202)
                release_deadline = time.monotonic() + 15
                for sid, hdr in ((idle_sid, idle_hdr), (busy_sid, busy_hdr)):
                    while client.get(f"/sessions/{sid}", headers=hdr).json()["state"] != "RELEASED":
                        self.assertLess(time.monotonic(), release_deadline)
                        time.sleep(0.1)

            collectors = engine.client.containers.list(
                all=True, filters={"label": [f"openlabscale.deployment={settings.deployment}", "openlabscale.role=collector"]}
            )
            self.assertEqual(collectors, [])
            self.assertEqual(engine.owned(), [])
