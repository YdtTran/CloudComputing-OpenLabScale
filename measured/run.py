"""One owned experiment: replay acknowledgements and collect independent signals."""
import json
import os
from pathlib import Path
import platform
import queue
import signal
import subprocess
import threading
import time
import uuid
from datetime import datetime, timezone

from simulation.contract import SCHEMA, TABLES, digest, dumps, identity, write_json, write_table
from simulation.validation import validate
from .preflight import COMPOSE, command, preflight
from .source import select
from .telemetry import mapping, verify_mapping, sample, resource_windows, normalized_cpu
from .truth import build_truth


LIMITATIONS = ('Partial measured collection: sched:sched_process_exec covers exec only; '
              'I/O, socket, disk and network counters are uncollected/null. All resource '
              'windows are DEGRADED. Multi-signal policies abstain. These two sessions '
              'do not establish real-world accuracy or monitoring overhead; synthetic '
              'and measured scores are never pooled. Ubuntu and full workloads are deferred.')


def reserve_output(output):
    root = Path(output)
    root.mkdir(parents=True, exist_ok=True)
    if any(root.iterdir()):
        raise ValueError(f'{root}: refusing nonempty output; use a fresh directory')
    # Exclusive creation also refuses another coordinator racing for this directory.
    with (root / 'run-status.json').open('x') as f:
        f.write(dumps(dict(status='incomplete')) + '\n')
    return root


class Experiment:
    def __init__(self, source, output):
        self.plan = select(source)
        self.root = reserve_output(output)
        self.run_id = uuid.uuid4().hex
        self.project = 'measured-' + self.run_id
        self.compose = ['docker', 'compose', '-f', str(COMPOSE), '-p', self.project]
        self.instances = {}
        self.sessions = []
        self.events = []
        self.observations = []
        self.samples = {}
        self.signals = []
        self.actions = []
        self.streams = []
        self.messages = queue.Queue()
        self.origin = None
        self.created = False
        self.metadata = dict(run_id=self.run_id, project=self.project, status='incomplete')

    def status(self, state, **details):
        self.metadata.update(status=state, **details)
        write_json(self.root / 'run-status.json', self.metadata)

    def stream(self, args, kind, session=None, job=None):
        process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        def read():
            for line in process.stdout:
                received = time.monotonic_ns()
                try:
                    value = json.loads(line)
                except ValueError:
                    value = dict(type='unparsed', text=line.rstrip())
                value.update(coordinator_received_ns=received, stream=kind, session_id=session, job_id=job)
                self.messages.put(value)

        # Each stream has bounded output. Drain stderr concurrently to avoid pipe stalls.
        errors = []
        def read_errors():
            for line in process.stderr:
                errors.append(line.rstrip())
        reader = threading.Thread(target=read, daemon=True)
        error_reader = threading.Thread(target=read_errors, daemon=True)
        reader.start()
        error_reader.start()
        self.streams.append((process, reader, error_reader, errors, kind))
        return process

    def drain(self):
        while True:
            try:
                value = self.messages.get_nowait()
            except queue.Empty:
                return
            self.raw.write(dumps(value) + '\n')
            self.raw.flush()
            if value['stream'] == 'collector':
                if value.get('type') == 'exec' and value.get('cgroup_id') not in {i['cgroup_id'] for i in self.instances.values()}:
                    raise RuntimeError('collector delivered an unrelated cgroup event; attribution invalid')
                self.signals.append(value)
            elif value.get('type') in ('job_started', 'job_completed'):
                action = 'JOB_START' if value['type'] == 'job_started' else 'JOB_COMPLETE'
                self.event(value['session_id'], action, value['job_id'], value['monotonic_ns'], value['coordinator_received_ns'], dict(ack='worker'))

    def elapsed(self, timestamp=None):
        return max(0, ((timestamp if timestamp is not None else time.monotonic_ns()) - self.origin) // 1000000)

    def event(self, sid, action, job, occurred, received, parameters):
        self.events.append(dict(run_id=self.run_id, event_id=identity(self.run_id, len(self.events)),
                                session_id=sid, at_ms=self.elapsed(occurred), action=action,
                                job_id=job, parameters_json=dumps(parameters)))
        self.actions.append(dict(session_id=sid, action=action, job_id=job,
                                 monotonic_ns=occurred, received_ns=received, parameters=parameters))
        if action.startswith('JOB_'):
            return
        session = next(s for s in self.sessions if s['session_id'] == sid)
        kind = 'connection' if action in {'CONNECT', 'RECONNECT', 'DISCONNECT', 'LOGOUT'} else 'interaction'
        self.observations.append(dict(run_id=self.run_id, session_id=sid,
                                      container_instance_id=session['container_instance_id'], kind=kind,
                                      at_ms=self.elapsed(occurred), available_at_ms=max(self.elapsed(occurred), (received - self.origin + 999999) // 1000000),
                                      window_start_ms='', window_end_ms='', source='session_service', status='OK',
                                      payload_json=dumps(dict(action='EXECUTE_REQUEST' if action == 'EXECUTE' else action))))

    def setup(self):
        evidence = preflight()
        write_json(self.root / 'preflight.json', evidence)
        if evidence['status'] != 'attached':
            raise RuntimeError(evidence.get('diagnostic', evidence.get('cleanup_diagnostic', 'preflight failed')))
        self.created = True
        command(self.compose + ['up', '-d', '--no-build', '--no-deps', 'cpu', 'idle'])
        self.source_map = {}
        self.job_map = {}
        for source, service in zip(self.plan['sessions'], ('cpu', 'idle')):
            cid = command(self.compose + ['ps', '-q', service]).strip()
            instance = mapping(cid)
            sid = identity(self.run_id, source['session_id'])
            self.instances[sid] = instance
            self.source_map[source['session_id']] = sid
            self.sessions.append(dict(source, run_id=self.run_id, session_id=sid,
                                      user_id=identity(self.run_id, source['user_id']),
                                      container_instance_id=identity(self.run_id, instance['docker_id'], instance['started_at']),
                                      start_ms=0))
            # Fresh exec verifies the worker clock against a host monotonic bracket.
            before = time.monotonic_ns()
            worker = int(command(['docker', 'exec', cid, 'python3', '-c', 'import time; print(time.monotonic_ns())']).strip())
            after = time.monotonic_ns()
            if not before <= worker <= after:
                raise RuntimeError('worker and host monotonic clocks differ; refusing replay')
            deadline = time.monotonic() + 15
            logs = ''
            while time.monotonic() < deadline:
                logs = command(['docker', 'logs', cid], timeout=5)
                state = json.loads(command(['docker', 'inspect', '--format', '{{json .State}}', cid], timeout=5))
                if not state['Running']:
                    raise RuntimeError(f'worker {cid} stopped before readiness: {dumps(state)}; logs: {logs}')
                ready = [json.loads(line) for line in logs.splitlines()]
                if any(r.get('type') == 'ready' for r in ready):
                    break
                time.sleep(.1)
            else:
                raise RuntimeError(f'worker {cid} readiness timed out after 15s; logs: {logs}')
            instance['clock_verification'] = dict(before_ns=before, worker_ns=worker, after_ns=after)
        # Clock evidence is metadata, not part of the immutable Docker mapping.
        for instance in self.instances.values():
            self.metadata.setdefault('worker_clocks', []).append(instance.pop('clock_verification'))
        override = self.root / 'collector-command.json'
        write_json(override, dict(services=dict(collector=dict(command=[str(i['cgroup_id']) for i in self.instances.values()]))))
        self.compose = self.compose[:4] + ['-f', str(override.resolve())] + self.compose[4:]
        attach_before = time.monotonic_ns()
        command(self.compose + ['up', '-d', '--no-build', '--no-deps', 'collector'])
        collector = command(self.compose + ['ps', '-q', 'collector']).strip()
        self.metadata['collector_id'] = collector
        self.metadata['collector_image'] = json.loads(command(['docker', 'inspect', collector]))[0]['Image']
        # Retagging a local image can make its old config ID uninspectable later.
        # Capture metadata while the run's images are still addressable.
        images = json.loads(command(['docker', 'image', 'inspect', 'measured-worker:local', 'measured-collector:local']))
        actual_ids = {self.metadata['collector_image']} | {i['image'] for i in self.instances.values()}
        if not actual_ids <= {i['Id'] for i in images}:
            raise RuntimeError('image tags changed during startup; refusing unverified image provenance')
        self.metadata['images'] = images
        self.stream(['docker', 'logs', '-f', collector], 'collector')
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            self.drain()
            if any(r.get('type') == 'ready' for r in self.signals) and any(r.get('type') == 'loss' for r in self.signals):
                break
            time.sleep(.05)
        else:
            raise RuntimeError('run collector failed actual attach/loss-map readiness')
        ready = next(r for r in self.signals if r.get('type') == 'ready')
        if not attach_before <= ready['monotonic_ns'] <= ready['coordinator_received_ns']:
            raise RuntimeError('collector BPF/host monotonic origin is incompatible')
        for instance in self.instances.values():
            command(['docker', 'exec', instance['docker_id'], 'python3', '-c', 'pass'])
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            self.drain()
            seen = {r['cgroup_id'] for r in self.signals if r.get('type') == 'exec'}
            if seen == {i['cgroup_id'] for i in self.instances.values()}:
                break
            time.sleep(.05)
        else:
            raise RuntimeError('owned worker exec handshake missing; cgroup attribution unproven')
        if any(not attach_before <= r['timestamp_ns'] <= r['coordinator_received_ns']
               for r in self.signals if r.get('type') == 'exec'):
            raise RuntimeError('BPF event clock differs from host monotonic clock; refusing replay')
        self.origin = time.monotonic_ns()
        self.origin_utc = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        self.metadata.update(origin_monotonic_ns=self.origin, origin_utc=self.origin_utc, instances=self.instances)
        for sid, instance in self.instances.items():
            self.samples[sid] = [sample(instance)]
        self.status('incomplete', stage='replaying')

    def execute(self, original):
        sid = self.source_map[original['session_id']]
        job = self.job_map.setdefault(original['job_id'], identity(self.run_id, original['job_id'])) if original['job_id'] else ''
        occurred = time.monotonic_ns()
        self.event(sid, original['action'], job, occurred, time.monotonic_ns(), dict(source_event_id=original['event_id'], planned_at_ms=int(original['at_ms'])))
        if original['action'] != 'EXECUTE':
            return
        phases = sorted([p for p in self.plan['phases'] if p['job_id'] == original['job_id']], key=lambda p: int(p['start_ms']))
        arguments = [dict(duration=(int(p['end_ms']) - int(p['start_ms'])) / 1000,
                          duty=json.loads(p['parameters_json']).get('cpu_duty', 0),
                          memory_bytes=json.loads(p['parameters_json']).get('memory_bytes', 0)) for p in phases]
        cid = self.instances[sid]['docker_id']
        self.stream(['docker', 'exec', cid, 'python3', '-u', '/worker/worker.py', '--phases', dumps(arguments)], 'job', sid, job)

    def collect(self):
        schedule = sorted([e for e in self.plan['events'] if not e['action'].startswith('JOB_')], key=lambda e: int(e['at_ms']))
        index = 0
        duration = max(int(s['end_ms']) for s in self.plan['sessions'])
        next_sample = time.monotonic() + 4.9
        while self.elapsed() < duration:
            self.drain()
            for process, _, _, errors, kind in self.streams:
                code = process.poll()
                if code is not None and (kind == 'collector' or code != 0):
                    raise RuntimeError(f'{kind} exited unexpectedly ({code}): ' + '\n'.join(errors))
            now = self.elapsed()
            while index < len(schedule) and int(schedule[index]['at_ms']) <= now:
                self.execute(schedule[index])
                index += 1
            if time.monotonic() >= next_sample:
                self.take_samples()
                next_sample = time.monotonic() + 4.9
            time.sleep(.02)
        self.take_samples()
        # Allow ring-buffer delivery to complete; availability retains actual receipt.
        time.sleep(.25)
        self.drain()
        for s in self.sessions:
            s['end_ms'] = max(self.elapsed(), int(s['end_ms']))
        self.duration = max(int(s['end_ms']) for s in self.sessions)

    def take_samples(self):
        for sid, instance in self.instances.items():
            try:
                verify_mapping(instance)
            except (OSError, RuntimeError, ValueError) as error:
                # No new instance can reuse these baselines. The run remains incomplete.
                self.samples[sid].append(dict(type='invalid_mapping', mapping_valid=False, baseline_valid=False,
                                             received_ns=time.monotonic_ns(), diagnostic=str(error)))
                raise RuntimeError('attribution invalid; baselines reset; experiment aborted: ' + str(error)) from error
            try:
                value = sample(instance)
            except (OSError, ValueError) as error:
                value = dict(timestamp_ns=time.monotonic_ns(), usage_usec=None, cpu_max=['0', '1'],
                             memory_bytes=None, cgroup_id=instance['cgroup_id'], diagnostic=str(error))
            cpu, diagnostic = normalized_cpu(self.samples[sid][-1], value)
            value.update(normalized_cpu_pct=cpu, normalization_diagnostic=diagnostic)
            self.samples[sid].append(value)
            self.observations.append(dict(run_id=self.run_id, session_id=sid,
                                          container_instance_id=next(s['container_instance_id'] for s in self.sessions if s['session_id'] == sid),
                                          kind='interaction_health', at_ms=self.elapsed(value['timestamp_ns']),
                                          available_at_ms=self.elapsed(), window_start_ms='', window_end_ms='',
                                          source='session_service', status='OK', payload_json=dumps(dict(healthy=True))))

    def export(self):
        rows = dict(sessions=self.sessions, events=sorted(self.events, key=lambda e: (e['session_id'], e['at_ms'])),
                    phases=[], observations=self.observations, truth=[])
        for original in self.plan['phases']:
            p = dict(original)
            p.update(run_id=self.run_id, session_id=self.source_map[p['session_id']], phase_id=identity(self.run_id, p['phase_id']))
            if p['job_id']:
                p['job_id'] = self.job_map[p['job_id']]
                request = next(e for e in self.events if e['job_id'] == p['job_id'] and e['action'] == 'EXECUTE')
                planned = json.loads(request['parameters_json'])['planned_at_ms']
                shift = int(request['at_ms']) - planned
                p.update(start_ms=int(p['start_ms']) + shift, end_ms=int(p['end_ms']) + shift)
            rows['phases'].append(p)
        losses = [r for r in self.signals if r.get('type') == 'loss']
        execs = [r for r in self.signals if r.get('type') == 'exec']
        def loss_at(t):
            eligible = [r for r in losses if r['coordinator_received_ns'] <= t]
            if not eligible or t - eligible[-1]['coordinator_received_ns'] > 2000000000:
                return None
            return eligible[-1]['count']
        for s in self.sessions:
            sid = s['session_id']
            samples = self.samples[sid]
            for previous, current in zip(samples, samples[1:]):
                # Include delivery of the next loss-map reading to cover the final poll interval.
                next_loss = next((r for r in losses if r['coordinator_received_ns'] >= current['timestamp_ns']), None)
                after = next_loss['count'] if next_loss else None
                available = max(current['timestamp_ns'], next_loss['coordinator_received_ns'] if next_loss else current['timestamp_ns'])
                rows['observations'].extend(resource_windows(s, self.origin, previous, current, execs,
                                                            loss_at(previous['timestamp_ns']), after, available))
            rows['truth'].extend(build_truth(s, [e for e in self.events if e['session_id'] == sid]))
        for name in TABLES:
            write_table(self.root / (name + '.csv'), name, rows[name])
        write_json(self.root / 'source-plan.json', dict(sessions=self.plan['sessions'], events=self.plan['events'], phases=self.plan['phases']))
        config = dict(source_hashes=self.plan['hashes'], source_manifest_sha256=self.plan['manifest_hash'],
                      source_run_id=self.plan['manifest']['run_id'], source_to_measured_sessions=self.source_map,
                      source_to_measured_jobs=self.job_map, instances=self.instances,
                      phase_timing='source plan retained verbatim in source-plan.json; exported job phases shifted by actual request lag for contract joins; truth uses only worker acknowledgements',
                      host=dict(kernel=platform.release(), platform=platform.platform()),
                      deployment=json.loads(command(self.compose + ['config', '--format', 'json'])),
                      images=self.metadata['images'],
                      probe='sched:sched_process_exec', omitted=['io_events', 'socket_events', 'disk_read_bytes', 'disk_write_bytes', 'network_rx_bytes', 'network_tx_bytes'],
                      worker_clocks=self.metadata['worker_clocks'], origin_monotonic_ns=self.origin,
                      sampling='actual monotonic bounds, nominal 4.9s cadence to stay <=5s; overruns split into missing-CPU windows')
        write_json(self.root / 'manifest.json', dict(schema_version=SCHEMA, generator_version='measured-1',
                   run_id=self.run_id, seed=self.plan['manifest']['seed'], config=config, duration_ms=self.duration,
                   sample_ms=5000, interaction_truth_ms=30000, clock='elapsed_ms', origin_utc=self.origin_utc,
                   source_mode='measured', limitations=LIMITATIONS,
                   files={name + '.csv': digest(self.root / (name + '.csv')) for name in TABLES}))
        validate(self.root)
        # The policy stage finalizes predictions before scoring is allowed to read truth.
        command(['python3', '-m', 'simulation', 'predict', str(self.root), str(self.root / 'evaluation')], timeout=30)
        command(['python3', '-m', 'simulation', 'score', str(self.root), str(self.root / 'evaluation')], timeout=30)

    def cleanup(self):
        errors = []
        self.metadata['cleanup_started_ns'] = time.monotonic_ns()
        if self.created:
            try:
                command(self.compose + ['down', '--timeout', '5'], timeout=20)
            except RuntimeError as error:
                errors.append(str(error))
        for process, reader, error_reader, stderr, kind in self.streams:
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=2)
            reader.join(timeout=2)
            error_reader.join(timeout=2)
            if stderr:
                self.metadata.setdefault('stream_stderr', []).append(dict(kind=kind, lines=stderr))
            process.stdout.close()
            process.stderr.close()
        self.metadata['cleanup_finished_ns'] = time.monotonic_ns()
        return errors

    def run(self):
        previous = os.environ.get('MEASURED_PROJECT')
        os.environ['MEASURED_PROJECT'] = self.project
        old_term = signal.getsignal(signal.SIGTERM)
        def terminate(signum, frame):
            raise KeyboardInterrupt(f'signal {signum}')
        signal.signal(signal.SIGTERM, terminate)
        error = None
        with (self.root / 'raw-signals.jsonl').open('x') as self.raw:
            try:
                self.setup()
                self.collect()
                self.export()
            except BaseException as exc:
                error = exc
            finally:
                cleanup = self.cleanup()
                self.drain()
                write_json(self.root / 'raw-cgroup.json', self.samples)
                write_json(self.root / 'actual-actions.json', self.actions)
                self.status('incomplete' if error or cleanup else 'complete',
                            diagnostic=str(error) if error else None, cleanup_diagnostics=cleanup,
                            instances=self.instances,
                            evidence_sha256={str(p.relative_to(self.root)): digest(p) for p in self.root.rglob('*') if p.is_file() and p.name != 'run-status.json'})
                signal.signal(signal.SIGTERM, old_term)
                if previous is None:
                    os.environ.pop('MEASURED_PROJECT', None)
                else:
                    os.environ['MEASURED_PROJECT'] = previous
        if error:
            raise error
        if cleanup:
            raise RuntimeError('owned cleanup failed: ' + '; '.join(cleanup))
        return self.root


def run(source, output):
    return Experiment(source, output).run()
