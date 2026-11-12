import unittest
from unittest.mock import Mock

from docker.errors import NotFound
from requests.exceptions import ReadTimeout

from backend.engine import Engine, LABEL
from backend.models import Session, Settings


class DockerLifecycle(unittest.TestCase):
    def setUp(self):
        self.settings = Settings(deployment="unit", identity_database="unused.db", terminal_origin="https://localhost")
        self.client = Mock()
        self.engine = Engine(self.settings, self.client)
        self.session = Session(id="test", owner="admin", cpu_millis=500, memory_mib=256)
        self.container = self.client.containers.create.return_value
        self.container.labels = {LABEL: "unit", "openlabscale.session": "test"}
        self.container.status = "running"
        self.client.containers.get.return_value = self.container

    def test_limits_and_owned_cleanup(self):
        self.engine.provision(self.session)
        options = self.client.containers.create.call_args.kwargs
        self.assertEqual(options["nano_cpus"], 500_000_000)
        self.assertEqual(options["mem_limit"], 256 * 1024**2)
        self.assertEqual(options["memswap_limit"], options["mem_limit"])
        self.assertEqual(options["pids_limit"], self.settings.pids)
        self.assertEqual(options["user"], "65534:65534")
        self.assertEqual(options["network_mode"], "none")
        self.assertEqual(options["cap_drop"], ["ALL"])
        self.container.start.assert_called_once()
        self.engine.remove(self.session)
        self.container.remove.assert_called_once_with(force=True)
        self.client.containers.get.side_effect = NotFound("gone")
        self.engine.remove(self.session)

    def test_ambiguous_create_retains_capacity_until_seen(self):
        self.client.containers.create.side_effect = ReadTimeout("uncertain")
        with self.assertRaises(ReadTimeout):
            self.engine.provision(self.session)
        self.client.containers.get.side_effect = NotFound("not yet visible")
        with self.assertRaises(RuntimeError):
            self.engine.remove(self.session)
        self.client.containers.get.side_effect = None
        self.engine.remove(self.session)

    def test_reconcile_does_not_remove_unrelated(self):
        unrelated = Mock(labels={LABEL: "other"})
        self.client.containers.list.side_effect = [[unrelated, self.container], [unrelated]]
        self.engine.reconcile()
        unrelated.remove.assert_not_called()
        self.container.remove.assert_called_once_with(force=True)

    def test_restart_with_inflight_create_fails_closed_until_observed(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as directory:
            pending = Path(directory)
            engine = Engine(self.settings, self.client, pending)
            self.client.containers.create.side_effect = ReadTimeout("daemon may still be creating")
            with self.assertRaises(ReadTimeout):
                engine.provision(self.session)
            restarted = Engine(self.settings, self.client, pending)
            self.client.containers.list.return_value = []
            with self.assertRaisesRegex(RuntimeError, "Unresolved Docker create"):
                restarted.reconcile()
            self.client.containers.list.side_effect = [[self.container], []]
            restarted.reconcile()
            self.assertEqual(list(pending.iterdir()), [])
            self.container.remove.assert_called_once_with(force=True)

    def test_telemetry_skips_removed_container(self):
        removed = Mock(labels={LABEL: "unit", "openlabscale.session": "gone"}, status="running")
        removed.stats.side_effect = NotFound("gone")
        self.container.stats.return_value = {
            "cpu_stats": {"cpu_usage": {"total_usage": 100}},
            "memory_stats": {"usage": 200},
            "read": "2026-11-09T06:00:00Z",
        }
        self.client.containers.list.return_value = [removed, self.container]
        telemetry = self.engine.telemetry()
        self.assertTrue(self.client.containers.list.call_args.kwargs.get("ignore_removed"))
        self.assertEqual(telemetry["active_containers"], 1)
        self.assertEqual(list(telemetry["containers"]), ["test"])
