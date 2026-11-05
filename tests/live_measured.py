"""Opt-in real-host acceptance: restart and interrupt only owned experiments.

Run: python3 -m tests.live_measured SOURCE FRESH_OUTPUT
"""
import json
from pathlib import Path
import signal
import subprocess
import sys
import time
import uuid

from measured.preflight import command
from simulation.contract import write_json


def wait_for(process, path, predicate, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists():
            try:
                value = json.loads(path.read_text())
            except ValueError:
                value = None
            if value and predicate(value):
                return value
        if process.poll() is not None:
            raise AssertionError(f'run exited early ({process.returncode}): {path}')
        time.sleep(.1)
    raise AssertionError(f'timed out waiting for {path}')


def verify_success(root):
    from simulation.validation import validate
    from simulation.contract import read_table
    manifest = validate(root)
    assert json.loads((root / 'run-status.json').read_text())['status'] == 'complete'
    events = read_table(root, 'events')
    sessions = read_table(root, 'sessions')
    cpu = next(s for s in sessions if s['scenario_id'] == 'cpu-background')
    idle = next(s for s in sessions if s['scenario_id'] == 'pure-idle')
    actions = {e['action']: int(e['at_ms']) for e in events if e['session_id'] == cpu['session_id']}
    assert actions['EXECUTE'] <= actions['JOB_START'] < actions['DISCONNECT'] < actions['JOB_COMPLETE']
    signals = [json.loads(line) for line in (root / 'raw-signals.jsonl').read_text().splitlines()]
    origin = manifest['config']['origin_monotonic_ns']
    cgroup = manifest['config']['instances'][cpu['session_id']]['cgroup_id']
    job_execs = [r for r in signals if r.get('type') == 'exec' and r['cgroup_id'] == cgroup
                 and actions['EXECUTE'] <= (r['timestamp_ns'] - origin) // 1000000 <= actions['JOB_START']]
    assert job_execs, 'CPU-job exec missing from actual request/start interval'
    assert all(r['pid'] > 0 and r['tgid'] > 0 for r in job_execs)
    selected = {v['cgroup_id'] for v in manifest['config']['instances'].values()}
    assert all(r['cgroup_id'] in selected for r in signals if r.get('type') == 'exec')
    raw = json.loads((root / 'raw-cgroup.json').read_text())
    def averages(s, start, end):
        samples = raw[s['session_id']]
        values = [r['normalized_cpu_pct'] for r in samples if r.get('normalized_cpu_pct') is not None
                  and start < (r['timestamp_ns'] - origin) // 1000000 < end]
        assert values
        return sum(values) / len(values)
    busy = averages(cpu, 50000, actions['JOB_COMPLETE'])
    idle_cpu = averages(idle, 50000, actions['JOB_COMPLETE'])
    trailing = averages(cpu, actions['JOB_COMPLETE'] + 10000, 300000)
    assert busy > idle_cpu + 10 and busy > trailing + 10, (busy, idle_cpu, trailing)
    observations = read_table(root, 'observations')
    resources = [r for r in observations if r['kind'] == 'resource']
    assert resources and all(r['status'] == 'DEGRADED' for r in resources)
    assert any(int(r['at_ms']) > actions['JOB_COMPLETE'] + 30000 for r in resources if r['session_id'] == cpu['session_id'])
    for r in resources:
        p = json.loads(r['payload_json'])
        assert all(p[k] is None for k in manifest['config']['omitted'])
        assert 0 < int(r['window_end_ms']) - int(r['window_start_ms']) <= 5000
    metrics = json.loads((root / 'evaluation/metrics.json').read_text())
    for name in ('resource-multi', 'interaction-aware'):
        m = metrics['policies'][name]['overall_micro']
        assert m['unknown_predictions'] > 0 and m['definite_predictions'] == 0
    return dict(status='verified', actual_cpu_actions_ms=actions, cpu_job_execs=job_execs,
                mean_busy_cpu_pct=busy, mean_idle_cpu_pct=idle_cpu, mean_trailing_cpu_pct=trailing,
                resource_windows=len(resources), limitations=manifest['limitations'])


def faults(source, output):
    root = Path(output)
    root.mkdir(parents=True, exist_ok=False)
    sentinel = 'measured-unrelated-' + uuid.uuid4().hex
    sentinel_id = command(['docker', 'run', '-d', '--name', sentinel, '--cap-drop', 'ALL',
                           '--network', 'none', '--read-only', '--cpus', '.1', '--memory', '32m',
                           'measured-worker:local']).strip()
    baseline = command(['docker', 'ps', '-q']).splitlines()
    result = dict(unrelated_sentinel_id=sentinel_id, unrelated_ids_before=baseline)
    try:
        for kind in ('restart', 'interrupt'):
            destination = root / kind
            with (root / (kind + '.log')).open('x') as log:
                process = subprocess.Popen(['python3', '-m', 'measured', 'run', str(source), str(destination)], stdout=log, stderr=log)
                try:
                    status = wait_for(process, destination / 'run-status.json', lambda s: s.get('stage') == 'replaying')
                    instances = status['instances']
                    if kind == 'restart':
                        target = next(iter(instances.values()))
                        time.sleep(1)
                        command(['docker', 'restart', '--time', '1', target['docker_id']])
                        restarted = json.loads(command(['docker', 'inspect', target['docker_id']]))[0]
                        assert restarted['State']['StartedAt'] != target['started_at']
                        result['restarted_lifecycle'] = dict(before=target, after=dict(id=restarted['Id'], started_at=restarted['State']['StartedAt'], pid=restarted['State']['Pid']))
                    else:
                        # The CPU job is already running and disconnected when interrupted.
                        while time.monotonic_ns() - status['origin_monotonic_ns'] < 42000000000:
                            assert process.poll() is None
                            time.sleep(.2)
                        process.send_signal(signal.SIGTERM)
                    code = process.wait(timeout=30)
                    assert code != 0
                    final = json.loads((destination / 'run-status.json').read_text())
                    assert final['status'] == 'incomplete' and not final['cleanup_diagnostics']
                    if kind == 'restart':
                        assert 'attribution invalid' in final['diagnostic']
                        samples = json.loads((destination / 'raw-cgroup.json').read_text())
                        assert any(rows[-1].get('type') == 'invalid_mapping' for rows in samples.values())
                        assert final['instances'] == instances, 'replacement acquired old identity'
                    else:
                        assert 'signal 15' in final['diagnostic']
                        actions = json.loads((destination / 'actual-actions.json').read_text())
                        assert any(a['action'] == 'JOB_START' for a in actions)
                        assert any(a['action'] == 'DISCONNECT' for a in actions)
                    remaining = command(['docker', 'ps', '-a', '-q', '--filter', 'label=com.docker.compose.project=' + status['project']]).strip()
                    assert not remaining, 'owned resources survived cleanup'
                    result[kind] = dict(status='verified', exit_code=code, diagnostic=final['diagnostic'], project=status['project'])
                finally:
                    if process.poll() is None:
                        process.send_signal(signal.SIGTERM)
                        process.wait(timeout=30)
            for cid in baseline:
                assert command(['docker', 'inspect', '--format', '{{.State.Running}}', cid]).strip() == 'true', f'unrelated container stopped: {cid}'
        result['unrelated_ids_after'] = command(['docker', 'ps', '-q']).splitlines()
        result['cleanup_is_policy_independent'] = 'Runner never reads recommendations; only unique owned Compose projects are removed.'
    finally:
        command(['docker', 'rm', '-f', sentinel_id])
        write_json(root / 'acceptance.json', result)
    return result


if __name__ == '__main__':
    if sys.argv[1] == 'verify':
        root = Path(sys.argv[2])
        value = verify_success(root)
        write_json(root / 'acceptance.json', value)
        print(json.dumps(value, indent=2))
    else:
        print(json.dumps(faults(Path(sys.argv[1]), Path(sys.argv[2])), indent=2))
