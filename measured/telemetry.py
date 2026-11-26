"""Stable instance mapping, raw cgroup samples and conservative partial windows."""
import json
from pathlib import Path
import time

from simulation.contract import RESOURCE, dumps
from .preflight import command


def mapping(container):
    info = json.loads(command(['docker', 'inspect', container]))[0]
    state = info['State']
    if not state['Running'] or state.get('Restarting'):
        raise RuntimeError(f'selected instance stopped/restarting: {container}')
    pid = state['Pid']
    lines = Path(f'/proc/{pid}/cgroup').read_text().splitlines()
    paths = [line[3:] for line in lines if line.startswith('0::')]
    if len(paths) != 1 or '..' in Path(paths[0]).parts:
        raise RuntimeError(f'ambiguous cgroup mapping for {container}')
    path = Path('/sys/fs/cgroup') / paths[0].lstrip('/')
    return dict(docker_id=info['Id'], started_at=state['StartedAt'], pid=pid,
                restart_count=info['RestartCount'], cgroup_path=str(path),
                cgroup_id=path.stat().st_ino, image=info['Image'])


def verify_mapping(original):
    current = mapping(original['docker_id'])
    if current != original:
        raise RuntimeError('instance mapping changed; abort and reset baselines; replacement must not inherit old identity: ' + dumps(dict(original=original, current=current)))


def sample(instance):
    path = Path(instance['cgroup_path'])
    started = time.monotonic_ns()
    usage = dict(line.split() for line in (path / 'cpu.stat').read_text().splitlines())
    maximum = (path / 'cpu.max').read_text().split()
    memory = int((path / 'memory.current').read_text())
    return dict(timestamp_ns=time.monotonic_ns(), acquisition_start_ns=started,
                usage_usec=int(usage['usage_usec']), cpu_max=maximum,
                memory_bytes=memory, cgroup_id=instance['cgroup_id'])


def normalized_cpu(previous, current):
    if previous is None:
        return None, 'missing baseline'
    if previous['usage_usec'] is None or current['usage_usec'] is None:
        return None, 'missing CPU sample; baseline invalidated'
    if (current['cgroup_id'] != previous['cgroup_id'] or current['cpu_max'] != previous['cpu_max']
            or current['usage_usec'] < previous['usage_usec']):
        return None, 'mapping/quota/counter reset; baseline invalidated'
    quota, period = current['cpu_max']
    elapsed = current['timestamp_ns'] - previous['timestamp_ns']
    if quota == 'max' or int(period) <= 0 or int(quota) <= 0 or elapsed <= 0:
        return None, 'invalid quota or monotonic duration'
    value = (current['usage_usec'] - previous['usage_usec']) * 1000 / elapsed / (int(quota) / int(period)) * 100
    if not 0 <= value <= 100:
        return None, f'out-of-range normalized CPU {value}; retained in raw evidence'
    return value, None


def loss_delta(before, after):
    if before is None or after is None or after < before:
        return None
    return after - before


def _snapshot_delta(snapshots, cgid, previous_ns, current_ns):
    if not snapshots:
        return None
    key = str(cgid)
    before = None
    after = None
    for item in snapshots:
        ts = item.get('monotonic_ns')
        row = (item.get('cgroups') or {}).get(key)
        if ts is None or row is None:
            continue
        if ts <= previous_ns:
            before = item
        if ts >= current_ns and after is None:
            after = item
    if before is None or after is None:
        return None
    b_row, a_row = before['cgroups'][key], after['cgroups'][key]
    return dict(
        disk_read_bytes=max(0, a_row['io_read_bytes'] - b_row['io_read_bytes']),
        disk_write_bytes=max(0, a_row['io_write_bytes'] - b_row['io_write_bytes']),
        network_rx_bytes=max(0, a_row['sock_rx_bytes'] - b_row['sock_rx_bytes']),
        network_tx_bytes=max(0, a_row['sock_tx_bytes'] - b_row['sock_tx_bytes']),
        io_events=max(0, a_row['io_events'] - b_row['io_events']),
        socket_events=max(0, a_row['socket_events'] - b_row['socket_events']),
        received_ns=after.get('coordinator_received_ns', current_ns),
    )


def resource_windows(session, origin_ns, previous, current, events, before_loss, after_loss, available_ns, mapping_valid=True, snapshots=None):
    """A sample overrun yields missing CPU windows, never an averaged on-time claim."""
    lo = max(int(session['start_ms']), (previous['timestamp_ns'] - origin_ns) // 1000000)
    hi = min(int(session['end_ms']), (current['timestamp_ns'] - origin_ns) // 1000000)
    if hi <= lo:
        return []
    cpu, _ = normalized_cpu(previous, current)
    overrun = hi - lo > 5000
    snap = _snapshot_delta(snapshots, current['cgroup_id'], previous['timestamp_ns'], current['timestamp_ns']) if not overrun and mapping_valid else None
    loss = loss_delta(before_loss, after_loss)
    result = []
    for a in range(lo, hi, 5000):
        b = min(a + 5000, hi)
        payload = {key: None for key in RESOURCE}
        owned = [e for e in events if e['cgroup_id'] == current['cgroup_id'] and a <= (e['timestamp_ns'] - origin_ns) // 1000000 < b]
        delivery = max([available_ns] + [e['coordinator_received_ns'] for e in owned] + ([snap['received_ns']] if snap else []))
        mem_val = current['memory_bytes'] if b == hi and mapping_valid else None
        cpu_val = cpu if not overrun and mapping_valid else None
        proc_val = len(owned) if mapping_valid else None
        payload.update(cpu_pct=cpu_val, memory_bytes=mem_val, process_events=proc_val,
                       loss_count=loss, mapping_valid=mapping_valid,
                       cgroup_source='cgroup_v2', event_source='ebpf')
        full_ok = False
        if snap is not None and b == hi and cpu_val is not None and mem_val is not None and loss == 0:
            payload.update(
                disk_read_bytes=snap['disk_read_bytes'],
                disk_write_bytes=snap['disk_write_bytes'],
                network_rx_bytes=snap['network_rx_bytes'],
                network_tx_bytes=snap['network_tx_bytes'],
                io_events=snap['io_events'],
                socket_events=snap['socket_events'],
            )
            full_ok = True
        result.append(dict(run_id=session['run_id'], session_id=session['session_id'],
                           container_instance_id=session['container_instance_id'], kind='resource',
                           at_ms=b, available_at_ms=max(b, (delivery - origin_ns + 999999) // 1000000),
                           window_start_ms=a, window_end_ms=b, source='measured_collector',
                           status=('OK' if full_ok else ('DEGRADED' if mapping_valid else 'UNHEALTHY')), payload_json=dumps(payload)))
    return result
