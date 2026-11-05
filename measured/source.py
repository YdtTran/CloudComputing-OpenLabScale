"""Validate and select plans; synthetic signals and labels never leave this seam."""
import json
from pathlib import Path

from simulation.contract import TABLES, digest, read_table
from simulation.validation import validate


def select(source):
    root = Path(source)
    manifest = validate(root)
    if manifest['source_mode'] != 'synthetic':
        raise ValueError('replay source must be a validated synthetic bundle')
    sessions = read_table(root, 'sessions')
    selected = []
    for scenario in ('cpu-background', 'pure-idle'):
        matches = [s for s in sessions if s['scenario_id'] == scenario]
        if len(matches) != 1:
            raise ValueError(f'exactly one {scenario} session required, found {len(matches)}')
        s = matches[0]
        if (int(s['start_ms']) != 0 or int(s['end_ms']) > 300000
                or float(s['cpu_limit_cores']) != .5 or float(s['memory_limit_mb']) != 256):
            raise ValueError('selected sessions require zero offset, <=300s, 0.5 CPU and 256 MiB')
        selected.append(s)
    ids = {s['session_id'] for s in selected}
    phases = [p for p in read_table(root, 'phases') if p['session_id'] in ids]
    events = [e for e in read_table(root, 'events') if e['session_id'] in ids]
    for p in phases:
        params = json.loads(p['parameters_json'])
        if p['workload'] not in ('CPU', 'IDLE'):
            raise ValueError('only CPU/IDLE phases are supported')
        if (params.get('memory_bytes', 0) > 128 * 2**20
                or params.get('outcome', 'COMPLETE') != 'COMPLETE'
                or any(params.get(k, 0) for k in ('disk_file_bytes', 'disk_rate_bytes_s', 'network_bytes', 'response_delay_ms'))):
            raise ValueError('unsupported CPU replay parameters or memory >128 MiB')
        if p['workload'] != 'IDLE' and next(s for s in selected if s['session_id'] == p['session_id'])['scenario_id'] == 'pure-idle':
            raise ValueError('pure-idle cannot contain a job')
    return dict(manifest=manifest, sessions=selected, phases=phases, events=events,
                hashes={name + '.csv': digest(root / (name + '.csv')) for name in TABLES},
                manifest_hash=digest(root / 'manifest.json'))
