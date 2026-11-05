import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from measured.run import Experiment
from simulation.generator import generate


class WorkerReadinessTests(unittest.TestCase):
    def setup_fixture(self, logs, running=True):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        generate(root / 'source')
        experiment = Experiment(root / 'source', root / 'output')
        reads = []

        def command(args, timeout=20):
            if args[:2] == ['docker', 'exec']:
                return str(time.monotonic_ns())
            if args[:2] == ['docker', 'logs']:
                reads.append(args[-1])
                return logs.pop(0) if len(logs) > 1 else logs[0]
            if args[:2] == ['docker', 'inspect']:
                return json.dumps(dict(Running=running, ExitCode=0 if running else 1))
            if 'ps' in args:
                return args[-1]
            if 'up' in args and args[-1] == 'collector':
                raise RuntimeError('collector setup reached')
            return ''

        return experiment, command, reads

    def test_delayed_readiness_is_awaited_before_collector_start(self):
        e, command, reads = self.setup_fixture(['', '{"type":"ready"}'])
        with patch('measured.run.preflight', return_value={'status': 'attached'}), \
             patch('measured.run.mapping', side_effect=lambda cid: dict(docker_id=cid, started_at='fixture', cgroup_id=1)), \
             patch('measured.run.command', side_effect=command), \
             patch('measured.run.time.sleep'):
            with self.assertRaisesRegex(RuntimeError, 'collector setup reached'):
                e.setup()
        self.assertEqual(reads, ['cpu', 'cpu', 'idle'])

    def test_worker_exit_reports_lifecycle_before_scheduled_work(self):
        e, command, _ = self.setup_fixture([''], running=False)
        with patch('measured.run.preflight', return_value={'status': 'attached'}), \
             patch('measured.run.mapping', side_effect=lambda cid: dict(docker_id=cid, started_at='fixture', cgroup_id=1)), \
             patch('measured.run.command', side_effect=command):
            with self.assertRaisesRegex(RuntimeError, 'worker cpu stopped before readiness.*ExitCode'):
                e.setup()

    def test_missing_readiness_has_a_bounded_timeout(self):
        e, command, _ = self.setup_fixture([''])
        with patch('measured.run.preflight', return_value={'status': 'attached'}), \
             patch('measured.run.mapping', side_effect=lambda cid: dict(docker_id=cid, started_at='fixture', cgroup_id=1)), \
             patch('measured.run.command', side_effect=command), \
             patch('measured.run.time.monotonic', side_effect=[0, 0, 16]), \
             patch('measured.run.time.sleep'):
            with self.assertRaisesRegex(RuntimeError, 'worker cpu readiness timed out'):
                e.setup()
