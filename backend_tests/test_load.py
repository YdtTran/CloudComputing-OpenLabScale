import asyncio
import csv
import json
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Lock

from backend.load import CSV_COLUMNS, execute_load, reserve_output


class MockLoadDocker:
    def __init__(self, provision_delay: float = 0.01, remove_delay: float = 0.005, fail_every: int = 0):
        self.lock = Lock()
        self.containers: set[str] = set()
        self.peak_containers = 0
        self.calls = 0
        self.provision_delay = provision_delay
        self.remove_delay = remove_delay
        self.fail_every = fail_every

    def reconcile(self) -> None:
        with self.lock:
            self.containers.clear()

    def reap_orphans(self, reserved: set[str]) -> None:
        with self.lock:
            self.containers.intersection_update(reserved)

    def provision(self, session) -> str:
        with self.lock:
            self.calls += 1
            call_num = self.calls
            self.containers.add(session.id)
            if len(self.containers) > self.peak_containers:
                self.peak_containers = len(self.containers)
        if self.provision_delay > 0:
            time.sleep(self.provision_delay)
        if self.fail_every and call_num % self.fail_every == 0:
            raise RuntimeError("simulated provisioning fault")
        return f"container-{session.id[:8]}"

    def status(self, session) -> str:
        with self.lock:
            return "running" if session.id in self.containers else "missing"

    def remove(self, session) -> None:
        if self.remove_delay > 0:
            time.sleep(self.remove_delay)
        with self.lock:
            self.containers.discard(session.id)

    def telemetry(self) -> dict:
        with self.lock:
            active = len(self.containers)
            samples = {
                sid: {
                    "available": True,
                    "cpu_usage_ns": 10_000_000,
                    "memory_usage_bytes": 16 * 1024**2,
                    "sampled_at": "2026-11-09T06:00:00Z",
                }
                for sid in self.containers
            }
        return {
            "host": {
                "available": True,
                "cpu_total_ticks": 1000,
                "cpu_idle_ticks": 800,
                "memory_total_bytes": 2048 * 1024**2,
                "memory_used_bytes": 512 * 1024**2,
                "sampled_at": "2026-11-09T06:00:00Z",
            },
            "active_containers": active,
            "containers": samples,
        }


class LoadWorkflowTests(unittest.TestCase):
    def test_reserve_output_refuses_nonempty(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp) / "out"
            reserve_output(root)
            (root / "marker.txt").write_text("x", encoding="utf-8")
            with self.assertRaises(ValueError):
                reserve_output(root)

    def test_smoke_10_and_100_concurrent_requests_export_and_reconcile(self):
        with TemporaryDirectory() as tmp:
            smoke_dir = Path(tmp) / "smoke-10"
            docker_10 = MockLoadDocker(provision_delay=0.005, remove_delay=0.002)
            smoke = asyncio.run(execute_load(
                output_dir=smoke_dir,
                clients=10,
                max_sessions=3,
                host_cpu_millis=2000,
                headroom_cpu_millis=500,
                cpu_millis=500,
                job_seconds=0.03,
                poll_seconds=0.01,
                client_poll_seconds=0.01,
                stats_interval_seconds=0.02,
                engine=docker_10,
                use_asgi=True,
            ))
            s_sum = smoke["summary"]
            self.assertEqual(s_sum["outcomes"]["submitted_clients"], 10)
            self.assertEqual(s_sum["outcomes"]["released"], 10)
            self.assertTrue(s_sum["concurrency"]["limits_respected"])
            self.assertLessEqual(s_sum["concurrency"]["peak_running_containers"], 3)
            self.assertLessEqual(docker_10.peak_containers, 3)
            self.assertTrue(s_sum["reconciliation"]["counts_match"])
            self.assertTrue(s_sum["reconciliation"]["capacity_reclaimed"])

            load_dir = Path(tmp) / "concurrent-100"
            docker_100 = MockLoadDocker(provision_delay=0.002, remove_delay=0.001)
            load = asyncio.run(execute_load(
                output_dir=load_dir,
                clients=100,
                max_sessions=4,
                host_cpu_millis=2500,
                headroom_cpu_millis=500,
                cpu_millis=500,
                job_seconds=0.02,
                poll_seconds=0.01,
                client_poll_seconds=0.02,
                stats_interval_seconds=0.05,
                engine=docker_100,
                use_asgi=True,
            ))
            l_sum = load["summary"]
            self.assertEqual(l_sum["outcomes"]["submitted_clients"], 100)
            self.assertEqual(l_sum["outcomes"]["accepted_sessions"], 100)
            self.assertEqual(l_sum["outcomes"]["released"], 100)
            self.assertEqual(l_sum["outcomes"]["active_terminals"], 0)
            self.assertEqual(l_sum["concurrency"]["concurrent_http_clients"], 100)
            self.assertEqual(l_sum["concurrency"]["configured_max_concurrent_containers"], 4)
            self.assertGreaterEqual(l_sum["concurrency"]["peak_running_containers"], 1)
            self.assertLessEqual(l_sum["concurrency"]["peak_running_containers"], 4)
            self.assertLessEqual(docker_100.peak_containers, 4)
            self.assertGreater(l_sum["concurrency"]["peak_queued_sessions"], 0)
            self.assertTrue(l_sum["concurrency"]["limits_respected"])
            self.assertTrue(l_sum["reconciliation"]["counts_match"])
            self.assertTrue(l_sum["reconciliation"]["capacity_reclaimed"])
            self.assertIn("100 simultaneous HTTP clients", l_sum["semantics_note"])
            self.assertIn("0 interactive browser terminals", l_sum["semantics_note"])

            with (load_dir / "sessions.csv").open(encoding="utf-8") as handle:
                csv_rows = list(csv.DictReader(handle))
            self.assertEqual(len(csv_rows), 100)
            self.assertEqual(tuple(csv_rows[0].keys()), CSV_COLUMNS)
            saved_summary = json.loads((load_dir / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(saved_summary["outcomes"]["released"], 100)

    def test_burst_invariants_with_failures_cancellations_and_timeouts(self):
        docker = MockLoadDocker(provision_delay=0.002, remove_delay=0.001, fail_every=1)
        # Fail only the first provisioned session so it deterministically enters FAILED before client timeout.
        orig_provision = docker.provision

        def fail_first_only(session):
            docker.fail_every = 1 if docker.calls == 0 else 0
            return orig_provision(session)

        docker.provision = fail_first_only
        result = asyncio.run(execute_load(
            clients=12,
            max_sessions=2,
            host_cpu_millis=1500,
            headroom_cpu_millis=500,
            cpu_millis=500,
            job_seconds=0.12,
            wait_timeout_seconds=0.10,
            poll_seconds=0.01,
            client_poll_seconds=0.01,
            stats_interval_seconds=0.03,
            engine=docker,
            use_asgi=True,
            cancel_clients=frozenset({3, 4}),
        ))
        summary = result["summary"]
        outcomes = summary["outcomes"]
        self.assertEqual(outcomes["submitted_clients"], 12)
        self.assertGreaterEqual(outcomes["failed"], 1)
        self.assertGreaterEqual(outcomes["cancelled"], 2)
        self.assertGreaterEqual(outcomes["timed_out"], 1)
        self.assertEqual(
            outcomes["released"] + outcomes["completed"] + outcomes["failed"] + outcomes["cancelled"],
            12,
        )
        self.assertLessEqual(summary["concurrency"]["peak_running_containers"], 2)
        self.assertLessEqual(docker.peak_containers, 2)
        self.assertTrue(summary["concurrency"]["limits_respected"])
        self.assertTrue(summary["reconciliation"]["counts_match"])
        self.assertTrue(summary["reconciliation"]["capacity_reclaimed"])
        self.assertEqual(len(docker.containers), 0)
