import contextlib
import io
import json
import os
import subprocess
import unittest

from measured.worker import cpu_job


class DeploymentTests(unittest.TestCase):
    def test_compose_isolation(self):
        result = subprocess.run(
            ['docker', 'compose', '-f', 'compose.measured.yaml', 'config', '--format', 'json'],
            env={**os.environ, 'MEASURED_PROJECT': 'measured-config-test'},
            check=True, capture_output=True, text=True)
        services = json.loads(result.stdout)['services']
        for name, service in services.items():
            self.assertFalse(service.get('privileged', False))
            self.assertEqual(service['cap_drop'], ['ALL'])
            self.assertFalse(any('docker.sock' in str(v) for v in service.get('volumes', [])))
            if name != 'collector':
                self.assertFalse(service.get('cap_add'))
                self.assertFalse(service.get('volumes'))
                self.assertEqual(float(service['cpus']), .5)
                self.assertEqual(service['mem_limit'], '268435456')

    def test_worker_bounds_and_actual_acknowledgements(self):
        for duration, duty, memory in [(301, .5, 0), (1, 2, 0), (1, .5, 129 * 2**20),
                                       (float('nan'), .5, 0), (1, .5, -1)]:
            with self.assertRaises(ValueError):
                cpu_job(duration, duty, memory, .5)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            cpu_job(.01, .5, 4096, .5)
        start, end = map(json.loads, output.getvalue().splitlines())
        self.assertEqual(start['type'], 'phase_started')
        self.assertEqual(end['type'], 'phase_completed')
        self.assertGreater(end['monotonic_ns'], start['monotonic_ns'])
