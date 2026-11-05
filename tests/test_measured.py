import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from simulation.contract import TABLES, digest, dumps, read_table, write_json, write_table
from simulation.generator import generate
from simulation.policies import predict, causal_projection, POLICIES
from simulation.validation import validate
from measured.source import select
from measured.telemetry import normalized_cpu, resource_windows, loss_delta, verify_mapping
from measured.truth import build_truth
from measured.run import Experiment, reserve_output
from measured.preflight import command as real_command


def rehash(root):
    m = json.loads((root / 'manifest.json').read_text())
    m['files'] = {n + '.csv': digest(root / (n + '.csv')) for n in TABLES}
    write_json(root / 'manifest.json', m)


class SourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'source'
        generate(self.root)

    def test_selection_preserves_all_source_bytes(self):
        before = {p.name: p.read_bytes() for p in self.root.iterdir()}
        selected = select(self.root)
        self.assertEqual([s['scenario_id'] for s in selected['sessions']], ['cpu-background', 'pure-idle'])
        self.assertNotIn('observations', selected)
        self.assertNotIn('truth', selected)
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.root.iterdir()})

    def test_missing_and_duplicate_sessions(self):
        for count in (2, 20):
            root = Path(self.temp.name) / str(count)
            generate(root, count=count)
            with self.assertRaisesRegex(ValueError, 'exactly one'):
                select(root)

    def test_unsupported_phase_memory_and_cpu_bounds(self):
        phases = read_table(self.root, 'phases')
        cpu = next(p for p in phases if p['workload'] == 'CPU')
        for change in ('LOW_CPU', 'memory'):
            original = copy.deepcopy(phases)
            if change == 'memory':
                params = json.loads(cpu['parameters_json'])
                params['memory_bytes'] = 129 * 2**20
                cpu['parameters_json'] = dumps(params)
            else:
                cpu['workload'] = change
            write_table(self.root / 'phases.csv', 'phases', phases)
            rehash(self.root)
            with self.assertRaises(ValueError):
                select(self.root)
            phases = original
            cpu = next(p for p in phases if p['workload'] == 'CPU')
        write_table(self.root / 'phases.csv', 'phases', phases)
        sessions = read_table(self.root, 'sessions')
        sessions[0]['cpu_limit_cores'] = 1
        write_table(self.root / 'sessions.csv', 'sessions', sessions)
        rehash(self.root)
        with self.assertRaisesRegex(ValueError, '0.5 CPU'):
            select(self.root)


class TruthTests(unittest.TestCase):
    def events(self, terminal='JOB_COMPLETE', end=80000):
        pairs = [(0, 'CONNECT', ''), (10000, 'EXECUTE', 'j'), (11000, 'JOB_START', 'j'), (20000, 'DISCONNECT', '')]
        if terminal:
            pairs.append((end, terminal, 'j'))
        return [dict(at_ms=t, action=a, job_id=j) for t, a, j in pairs]

    def truth(self, events):
        return build_truth(dict(run_id='r', session_id='s', start_ms=0, end_ms=100000), events)

    def at(self, truth, t):
        return next(r for r in truth if r['start_ms'] <= t < r['end_ms'])

    def test_late_actual_completion_and_disconnect(self):
        truth = self.truth(self.events())
        self.assertEqual(self.at(truth, 70000)['workload'], 'ACTIVE')
        self.assertEqual(self.at(truth, 70000)['connection'], 'DISCONNECTED')
        self.assertEqual(self.at(truth, 80000)['workload'], 'IDLE')
        self.assertEqual(self.at(truth, 39999)['interaction'], 'RECENT')
        self.assertEqual(self.at(truth, 40000)['interaction'], 'ABSENT')

    def test_failed_and_missing_acknowledgements(self):
        for terminal in ('JOB_ERROR', 'JOB_INTERRUPT', None):
            truth = self.truth(self.events(terminal))
            self.assertEqual(self.at(truth, 60000)['workload'], 'UNKNOWN')
            self.assertEqual(self.at(truth, 90000)['workload'], 'UNKNOWN' if terminal is None else 'IDLE')
        events = [e for e in self.events(None) if e['action'] != 'JOB_START']
        self.assertEqual(self.at(self.truth(events), 90000)['workload'], 'UNKNOWN')


class TelemetryTests(unittest.TestCase):
    def sample(self, t, usage, **changes):
        return dict(timestamp_ns=t * 1000000, usage_usec=usage, cgroup_id=9,
                    cpu_max=['50000', '100000'], memory_bytes=1234, **changes)

    def test_quota_normalization_missing_reset_and_over_range(self):
        a, b = self.sample(0, 100), self.sample(1000, 250100)
        self.assertEqual(normalized_cpu(a, b), (50, None))
        for key, value in [('usage_usec', 0), ('cgroup_id', 10), ('cpu_max', ['10000', '100000']), ('usage_usec', None)]:
            c = dict(b, **{key: value})
            self.assertIsNone(normalized_cpu(a, c)[0])
        self.assertIsNone(normalized_cpu(a, self.sample(1000, 99999999))[0])
        self.assertEqual(loss_delta(0, 2), 2)
        self.assertIsNone(loss_delta(0, None))
        self.assertIsNone(loss_delta(2, 0))

    def test_late_event_overrun_partial_and_missing_values(self):
        session = dict(run_id='r', session_id='s', container_instance_id='c', start_ms=0, end_ms=20000)
        event = dict(cgroup_id=9, timestamp_ns=2000000000, coordinator_received_ns=9000000000)
        rows = resource_windows(session, 0, self.sample(0, 0), self.sample(4900, 1000000), [event], 0, 2, 5000000000)
        r = rows[0]
        p = json.loads(r['payload_json'])
        self.assertEqual(r['available_at_ms'], 9000)
        self.assertEqual(p['process_events'], 1)
        self.assertEqual(p['loss_count'], 2)
        self.assertEqual(p['memory_bytes'], 1234)
        for k in ('io_events', 'socket_events', 'disk_read_bytes', 'network_rx_bytes'):
            self.assertIsNone(p[k])
        self.assertEqual(r['status'], 'DEGRADED')
        self.assertFalse(causal_projection([r], session, 5000))
        rows = resource_windows(session, 0, self.sample(0, 0), self.sample(12000, 1000000), [], 0, None, 13000000000)
        self.assertEqual([(r['window_start_ms'], r['window_end_ms']) for r in rows], [(0, 5000), (5000, 10000), (10000, 12000)])
        self.assertTrue(all(json.loads(r['payload_json'])['cpu_pct'] is None for r in rows))
        self.assertTrue(all(json.loads(r['payload_json'])['loss_count'] is None for r in rows))

    def test_restart_mapping_never_relabels_instance(self):
        original = dict(docker_id='old', started_at='old-start', cgroup_id=9)
        with patch('measured.telemetry.mapping', return_value=dict(original, started_at='new-start', cgroup_id=10)):
            with self.assertRaisesRegex(RuntimeError, 'replacement must not inherit'):
                verify_mapping(original)
        self.assertEqual(original['cgroup_id'], 9)


class OwnershipTests(unittest.TestCase):
    def test_startup_failure_and_interruption_retain_incomplete_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / 'source'
            generate(source)
            for name, error in [('startup', RuntimeError('startup fixture')), ('interrupt', KeyboardInterrupt('interrupted fixture'))]:
                e = Experiment(source, Path(temp) / name)
                def setup():
                    e.created = True
                    if name == 'startup':
                        raise error
                with patch.object(e, 'setup', side_effect=setup), patch.object(e, 'collect', side_effect=error), patch('measured.run.command') as cmd:
                    with self.assertRaises(type(error)):
                        e.run()
                status = json.loads((e.root / 'run-status.json').read_text())
                self.assertEqual(status['status'], 'incomplete')
                self.assertIn('fixture', status['diagnostic'])
                self.assertTrue((e.root / 'raw-cgroup.json').exists())
                self.assertEqual(cmd.call_args.args[0][-3:], ['down', '--timeout', '5'])
                self.assertIn(e.project, cmd.call_args.args[0])

    def test_destination_is_exclusive_and_cleanup_is_scoped_bounded(self):
        with tempfile.TemporaryDirectory() as temp:
            root = reserve_output(temp)
            with self.assertRaisesRegex(ValueError, 'nonempty'):
                reserve_output(root)
            e = Experiment.__new__(Experiment)
            e.created = True
            e.compose = ['docker', 'compose', '-p', 'unique-owned-project']
            e.streams = []
            e.metadata = {}
            with patch('measured.run.command', side_effect=RuntimeError('cleanup timeout')) as cmd:
                self.assertEqual(e.cleanup(), ['cleanup timeout'])
            self.assertEqual(cmd.call_args.args[0], e.compose + ['down', '--timeout', '5'])
            self.assertEqual(cmd.call_args.kwargs['timeout'], 20)


class ExportTests(unittest.TestCase):
    def test_export_validates_and_predictions_ignore_truth(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / 'source'
            generate(source)
            e = Experiment(source, Path(temp) / 'measured')
            e.origin = 1000000000
            e.origin_utc = '2026-11-05T00:00:00Z'
            e.duration = 300000
            e.source_map = {s['session_id']: 'measured-' + str(i) for i, s in enumerate(e.plan['sessions'])}
            e.job_map = {p['job_id']: 'measured-job' for p in e.plan['phases'] if p['job_id']}
            e.metadata['worker_clocks'] = []
            e.metadata['collector_image'] = 'sha256:collector-fixture'
            e.metadata['images'] = [dict(Id='sha256:collector-fixture'), dict(Id='sha256:worker-fixture')]
            for i, s in enumerate(e.plan['sessions']):
                sid = e.source_map[s['session_id']]
                e.sessions.append(dict(s, run_id=e.run_id, session_id=sid, container_instance_id='instance-' + str(i)))
                e.instances[sid] = dict(cgroup_id=10+i, docker_id='docker-'+str(i), image='sha256:worker-fixture')
                e.samples[sid] = [dict(timestamp_ns=e.origin+t*1000000, usage_usec=t*100, cpu_max=['50000','100000'], memory_bytes=100, cgroup_id=10+i) for t in (0, 4900, 9000)]
            for i, original in enumerate(e.plan['events']):
                t = int(original['at_ms'])
                if original['action'] == 'JOB_COMPLETE':
                    t += 1000
                e.events.append(dict(original, run_id=e.run_id, event_id='e'+str(i), session_id=e.source_map[original['session_id']],
                                     job_id=e.job_map.get(original['job_id'], ''), at_ms=t,
                                     parameters_json=dumps(dict(planned_at_ms=int(original['at_ms']), ack='fixture'))))
            e.signals = [dict(type='loss', count=0, coordinator_received_ns=e.origin+t*1000000) for t in range(-100, 9301, 100)]
            def cmd(args, timeout=20):
                if args[0] == 'docker':
                    if 'image' in args:
                        raise AssertionError('export must use startup image snapshot; old images may be uninspectable after retagging')
                    return '[]' if 'inspect' in args else '{}'
                return real_command(args, timeout)
            with patch('measured.run.command', side_effect=cmd):
                e.export()
            manifest = validate(e.root)
            self.assertEqual(manifest['source_mode'], 'measured')
            self.assertEqual(manifest['config']['images'], e.metadata['images'])
            report = (e.root / 'evaluation/report.md').read_text()
            self.assertIn('Partial measured collection', report)
            self.assertIn('I/O, socket, disk and network', report)
            self.assertIn('overhead', report)
            predictions = (e.root / 'evaluation/predictions.csv').read_bytes()
            truth = read_table(e.root, 'truth')
            for row in truth:
                row.update(interaction='RECENT', eligibility='RETAIN')
            write_table(e.root / 'truth.csv', 'truth', truth)
            rehash(e.root)
            validate(e.root)
            predict(e.root, e.root / 'modified-label-predictions')
            self.assertEqual(predictions, (e.root / 'modified-label-predictions/predictions.csv').read_bytes())
            import csv
            with (e.root / 'evaluation/predictions.csv').open() as f:
                pp = list(csv.DictReader(f))
            self.assertEqual({p['policy'] for p in pp}, set(POLICIES))
            self.assertTrue(all(p['decision'] == 'UNKNOWN' for p in pp if p['policy'] in ('resource-multi', 'interaction-aware')))
            observations = read_table(e.root, 'observations')
            self.assertTrue(all(o['kind'] == 'resource' for o in observations), 'export invented interaction/health')
            observations[0]['container_instance_id'] = 'replacement'
            write_table(e.root / 'observations.csv', 'observations', observations)
            rehash(e.root)
            with self.assertRaisesRegex(ValueError, 'mapping mismatch'):
                validate(e.root)
            observations[0]['container_instance_id'] = next(s['container_instance_id'] for s in e.sessions if s['session_id'] == observations[0]['session_id'])
            observations[0]['source'] = 'synthetic_model'
            write_table(e.root / 'observations.csv', 'observations', observations)
            rehash(e.root)
            with self.assertRaisesRegex(ValueError, 'provenance'):
                validate(e.root)
