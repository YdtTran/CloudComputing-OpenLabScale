import unittest
from unittest.mock import patch

from measured.preflight import preflight


class PreflightTests(unittest.TestCase):
    def fake_commands(self, diagnostic=None, docker_denied=False, cleanup_denied=False):
        calls = []

        def command(args, timeout=20):
            calls.append(args)
            if args[1] == 'version':
                if docker_denied:
                    raise RuntimeError('Docker socket permission denied; grant Docker access')
                return '{}'
            if args[1:3] == ['image', 'inspect']:
                return '[{"Id":"sha256:fixture"}]'
            if 'config' in args:
                return '{}'
            if 'logs' in args:
                return diagnostic or '{"type":"ready","monotonic_ns":123}'
            if 'ps' in args:
                return '{"State":"exited"}'
            if 'down' in args and cleanup_denied:
                raise RuntimeError('cleanup timed out')
            return ''

        return command, calls

    def test_denied_prerequisites_never_start_workloads(self):
        diagnostics = [
            'Prerequisite unreadable: /sys/kernel/tracing/events/sched/sched_process_exec/id',
            'Prerequisite unreadable: /sys/kernel/btf/vmlinux',
            'BPF/PERFMON capabilities: Operation not permitted',
            'perf_event_open() failed: Permission denied',
        ]
        for diagnostic in diagnostics:
            with self.subTest(diagnostic=diagnostic):
                command, calls = self.fake_commands(diagnostic)
                with patch('measured.preflight.command', side_effect=command):
                    result = preflight()
                self.assertEqual(result['status'], 'blocked')
                self.assertIn(diagnostic, result['diagnostic'])
                launches = [c for c in calls if 'up' in c]
                self.assertEqual(len(launches), 1)
                self.assertEqual(launches[0][-1], 'collector')
                self.assertTrue(any('down' in c for c in calls))

    def test_denied_docker_does_not_create_containers(self):
        command, calls = self.fake_commands(docker_denied=True)
        with patch('measured.preflight.command', side_effect=command):
            result = preflight()
        self.assertEqual(result['status'], 'blocked')
        self.assertIn('Docker socket permission denied', result['diagnostic'])
        self.assertFalse(any('up' in c for c in calls))

    def test_ready_requires_record_and_cleanup_failure_blocks_success(self):
        for denied in (False, True):
            command, _ = self.fake_commands(cleanup_denied=denied)
            with patch('measured.preflight.command', side_effect=command):
                result = preflight()
            self.assertEqual(result['status'], 'blocked' if denied else 'attached')
            self.assertEqual(result['readiness']['monotonic_ns'], 123)
            if denied:
                self.assertIn('cleanup timed out', result['cleanup_diagnostic'])
