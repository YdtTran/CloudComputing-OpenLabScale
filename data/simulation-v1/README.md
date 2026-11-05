# Offline simulation v1

Python 3.9+; no third-party packages, containers, privileges, kernel features or
network services. Run from the project root. Synthetic scores demonstrate pipeline
behavior; they do not measure real monitoring accuracy, reclamation savings or
host/eBPF overhead. Every report repeats that limitation.

```sh
python3 -m simulation --help
python3 -m simulation generate /tmp/dev42 --seed 42
python3 -m simulation validate /tmp/dev42
python3 -m simulation evaluate /tmp/dev42 /tmp/report42
python3 -m simulation predict /tmp/dev42 /tmp/separate-report42
python3 -m simulation score /tmp/dev42 /tmp/separate-report42
python3 -m unittest discover -s tests -v
```

Use seeds 42 and 43 for development; seed 44 is a held-out synthetic check, not
real-world generalization. Scale with `--count 30 --start-offset-ms 10000
--cpu-limit-cores 0.5 --memory-limit-mb 256`. Offsets are per session index; they do
not implement host admission control. Default is ten simultaneous 300s sessions.
Repeated templates use independent deterministic streams. Explicit `--overwrite`
is required to replace a nonempty generated directory. Nothing executes a workload.

See [FIELDS.md](FIELDS.md), [SCENARIOS.md](SCENARIOS.md), [REPLAY.md](REPLAY.md),
[POLICIES.md](POLICIES.md) and [LEGACY.md](LEGACY.md).

## Signal model and limits

Schedule and noise PRNG streams derive independently from SHA-256 of seed,
template ID, repetition index, generator version and purpose. Fixed template times
preserve declared scenario boundaries; seeds vary CPU duty by 0.9–1.1 and memory
by 0.9–1.1. All resource values are explicitly synthetic. CPU is quota-normalized:
CPU duty 0.75, disk 0.005, network wait 0.002, low-use 0.004, burst duty 0.8.
Idle CPU floor is 0.05%; final window CPU receives 0.9–1.1 noise, capped at 100%.
Memory baseline is 20% of limit; active memory is approximately 64 MiB, capped at
75% of configured limit. Memory occupancy alone does not imply activity.

Disk uses 2 MiB/s active segments alternating with 10-second silent waits; write
bytes are half read bytes. Network has request and response edge traffic totaling
1 MiB received, with transmit bytes one eighth of receive. Pending network waits
can be completely silent. CPU has two process events/window; low-use has one;
bursts have one if a pulse intersects. Disk has two I/O events in active segments;
network edges have one socket event. Window deltas integrate actual phase and burst
intersections, including final partial windows. These are simple models, not a
kernel emulator, host calibration, observed usefulness, or realistic event rates.

Interaction observations expose only action; lifecycle acknowledgements, job IDs,
commands, phase durations and truth never enter policy inputs. Service health
heartbeats occur independently every five seconds. Faults can remove windows,
remove interactions, null cgroup/event groups, mark invalid mappings or event loss,
or delay delivery. Synthetic truth remains independently derived from schedules.
See the signal-loss template for exact timings. Reporting source names identify
synthetic cgroup and eBPF groups explicitly; they never claim real collection.

## Checked-in examples

`scale-120` adds 120 sessions (12 per template), with seed 42 and starts staggered
by 1000 ms per session. It includes 7140 observed resource windows (60 windows
omitted by reporting-outage scenarios) and all five policy
reports. Reproduce it with:

```sh
python3 -m simulation generate /tmp/reproduce-scale120 --seed 42 --count 120 --start-offset-ms 1000
python3 -m simulation validate /tmp/reproduce-scale120
python3 -m simulation evaluate /tmp/reproduce-scale120 /tmp/reproduce-scale120/evaluation
```

`dev-43` and `heldout-44` each include all ten templates (about 600 resource
windows), finalized
predictions, JSON metrics and a Markdown report. Exact reproduction from a fresh
checkout (use unused output paths, or `--overwrite` for regeneration):

```sh
python3 -m simulation generate /tmp/reproduce-dev43 --seed 43
python3 -m simulation validate /tmp/reproduce-dev43
python3 -m simulation evaluate /tmp/reproduce-dev43 /tmp/reproduce-dev43/evaluation
python3 -m simulation generate /tmp/reproduce-heldout44 --seed 44
python3 -m simulation validate /tmp/reproduce-heldout44
python3 -m simulation evaluate /tmp/reproduce-heldout44 /tmp/reproduce-heldout44/evaluation
```

Compare each tree with `dev-43` or `heldout-44` here. The smaller seed-42
bundle was replaced by `scale-120`; it can still be generated with the default
seed-42 command above. All content is
deterministic, including hashes and reports. No generation wall-clock times or
absolute output paths are embedded. Thresholds remain unchanged for seed 44.
The hand-authored measured contract fixture is `tests/fixtures/measured-v1`:
it is a contract example only, not a collected experiment or accuracy result.
