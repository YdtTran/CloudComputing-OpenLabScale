"""Bounded worker entry points; client disconnect does not signal the job."""
import argparse
import json
import math
import signal
import time


def cpu_job(duration, duty, memory_bytes, quota):
    if not all(math.isfinite(v) for v in (duration, duty, quota)):
        raise ValueError('finite duration, duty and quota required')
    if not (0 < duration <= 300 and 0 <= duty <= 1 and quota == .5
            and 0 <= memory_bytes <= 128 * 2**20):
        raise ValueError('job exceeds duration/duty/memory/quota bounds')
    memory = bytearray(memory_bytes)
    # Touch pages so memory.current reflects the requested allocation.
    for page in range(0, len(memory), 4096):
        memory[page] = 1
    deadline = time.monotonic() + duration
    print(json.dumps(dict(type='phase_started', monotonic_ns=time.monotonic_ns())), flush=True)
    while time.monotonic() < deadline:
        start = time.monotonic()
        busy = time.process_time() + .1 * duty * quota
        while time.process_time() < busy and time.monotonic() < deadline:
            pass
        time.sleep(max(0, min(.1 - (time.monotonic() - start), deadline - time.monotonic())))
    print(json.dumps(dict(type='phase_completed', monotonic_ns=time.monotonic_ns())), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--duration', type=float)
    parser.add_argument('--duty', type=float, default=.75)
    parser.add_argument('--memory-bytes', type=int, default=64 * 2**20)
    parser.add_argument('--phases', help='JSON CPU phase list, bounded by the coordinator')
    args = parser.parse_args()
    if args.duration is not None or args.phases is not None:
        phases = json.loads(args.phases) if args.phases is not None else [dict(duration=args.duration, duty=args.duty, memory_bytes=args.memory_bytes)]
        if not phases or sum(p['duration'] for p in phases) > 300:
            raise ValueError('job deadline exceeds 300 seconds')
        # Independent wall deadline survives a disconnected coordinator/client.
        signal.alarm(math.ceil(sum(p['duration'] for p in phases)) + 3)
        print(json.dumps(dict(type='job_started', monotonic_ns=time.monotonic_ns())), flush=True)
        for phase in phases:
            cpu_job(phase['duration'], phase['duty'], phase['memory_bytes'], .5)
        print(json.dumps(dict(type='job_completed', monotonic_ns=time.monotonic_ns())), flush=True)
        signal.alarm(0)
    else:
        print(json.dumps(dict(type='ready', monotonic_ns=time.monotonic_ns())), flush=True)
        time.sleep(330)


if __name__ == '__main__':
    main()
