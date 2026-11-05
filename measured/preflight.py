"""Read-only host checks and a short, owned real-probe attachment check."""
import json
import os
from pathlib import Path
import platform
import subprocess
import time
import uuid


COMPOSE = Path(__file__).resolve().parents[1] / 'compose.measured.yaml'


def command(args, timeout=20):
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise RuntimeError(f'{args[0]} unavailable or timed out: {error}') from error
    if result.returncode:
        raise RuntimeError(f'{" ".join(args)}: {result.stderr.strip() or result.stdout.strip()}')
    return result.stdout


def preflight():
    """No workload launches, package installs, mounts or host permission changes."""
    evidence = dict(kernel=platform.release(), platform=platform.platform(),
                    probe='sched:sched_process_exec', status='incomplete',
                    capabilities=['SYS_ADMIN'])
    name = 'measured-preflight-' + uuid.uuid4().hex
    compose = ['docker', 'compose', '-f', str(COMPOSE), '-p', name]
    # The name interpolation is required even when -p overrides the project name.
    previous = os.environ.get('MEASURED_PROJECT')
    os.environ['MEASURED_PROJECT'] = name
    created = False
    try:
        evidence['docker'] = json.loads(command(['docker', 'version', '--format', '{{json .}}']))
        evidence['configuration'] = json.loads(command(compose + ['config', '--format', 'json']))
        evidence['image'] = json.loads(command(['docker', 'image', 'inspect', 'measured-collector:local']))[0]['Id']
        # Only the collector is created. The readiness record follows actual attach.
        created = True
        command(compose + ['up', '-d', '--no-build', '--no-deps', 'collector'])
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            logs = command(compose + ['logs', '--no-color', '--no-log-prefix', 'collector'])
            evidence['collector_log'] = logs
            for line in logs.splitlines():
                try:
                    record = json.loads(line)
                except ValueError:
                    continue
                if record.get('type') == 'ready':
                    evidence['status'] = 'attached'
                    evidence['readiness'] = record
                    return evidence
            containers = json.loads(command(compose + ['ps', '-a', '--format', 'json']))
            if isinstance(containers, dict):
                containers = [containers]
            if any(c.get('State') == 'exited' for c in containers):
                raise RuntimeError('collector exited before attachment readiness:\n' + logs)
            time.sleep(.1)
        raise RuntimeError('collector attachment readiness timed out:\n' + evidence.get('collector_log', ''))
    except (RuntimeError, ValueError) as error:
        evidence['status'] = 'blocked'
        evidence['diagnostic'] = str(error)
        return evidence
    finally:
        if created:
            try:
                command(compose + ['down', '--timeout', '5'], timeout=15)
            except RuntimeError as error:
                evidence['status'] = 'blocked'
                evidence['cleanup_diagnostic'] = str(error)
        if previous is None:
            os.environ.pop('MEASURED_PROJECT', None)
        else:
            os.environ['MEASURED_PROJECT'] = previous
