"""Version 1 field dictionary and deterministic bundle serialization."""
import csv
import hashlib
import json
from pathlib import Path

SCHEMA = '1.0'
TABLES = {
    'sessions': 'run_id session_id user_id container_instance_id scenario_id start_ms end_ms cpu_limit_cores memory_limit_mb',
    'events': 'run_id event_id session_id at_ms action job_id parameters_json',
    'phases': 'run_id phase_id session_id job_id start_ms end_ms workload parameters_json',
    'observations': 'run_id session_id container_instance_id kind at_ms available_at_ms window_start_ms window_end_ms source status payload_json',
    'truth': 'run_id session_id start_ms end_ms interaction connection workload eligibility reason label_source',
}
TABLES = {k: v.split() for k, v in TABLES.items()}
ACTIONS = {'CONNECT', 'EDIT', 'EXECUTE', 'DISCONNECT', 'RECONNECT', 'LOGOUT', 'JOB_START', 'JOB_COMPLETE', 'JOB_ERROR', 'JOB_INTERRUPT'}
WORKLOADS = {'CPU', 'DISK_IO', 'NETWORK_WAIT', 'BURST', 'LOW_CPU', 'IDLE', 'MIXED'}
COUNTERS = ['disk_read_bytes', 'disk_write_bytes', 'network_rx_bytes', 'network_tx_bytes', 'process_events', 'io_events', 'socket_events', 'loss_count']
CGROUP = ['cpu_pct', 'memory_bytes']
RESOURCE = CGROUP + COUNTERS + ['mapping_valid', 'cgroup_source', 'event_source']
KINDS = {'interaction', 'connection', 'interaction_health', 'resource'}
LIMITATION = 'Synthetic model results are not real monitoring accuracy, reclamation savings, or host/eBPF overhead.'


def dumps(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def identity(*parts):
    return hashlib.sha256(dumps(parts).encode()).hexdigest()[:24]


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n')


def write_table(path, name, rows):
    with Path(path).open('w', newline='') as f:
        w = csv.DictWriter(f, TABLES.get(name, list(rows[0]) if rows else []), lineterminator='\n')
        w.writeheader()
        w.writerows(rows)


def read_table(root, name):
    path = Path(root) / (name + '.csv')
    try:
        with path.open(newline='') as f:
            reader = csv.DictReader(f)
            if reader.fieldnames != TABLES[name]:
                raise ValueError(f'{path}: schema columns must be {TABLES[name]}; legacy timestamps require explicit conversion')
            return list(reader)
    except OSError as e:
        raise ValueError(f'{path}: {e.strerror}') from e


def read_manifest(root):
    try:
        return json.loads((Path(root) / 'manifest.json').read_text())
    except (OSError, json.JSONDecodeError) as e:
        raise ValueError(f'{root}/manifest.json: versioned manifest required; legacy abbreviated timestamps are not elapsed milliseconds ({e})') from e
