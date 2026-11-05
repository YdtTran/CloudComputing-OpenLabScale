# Recommendation policies

All outputs are RETAIN, IDLE_CANDIDATE or UNKNOWN, with reason codes. They never
stop a container. Decision ticks are global-origin multiples of 5000 ms strictly
after session start and before session end, with no truncation after a candidate.
`predict` reads manifest timing/source mode, allowlisted session identity, lifetime
and resource limits, and observations only. It does not open truth, events or
phases. `score` opens truth after predictions are finalized. Input/config hashes
and prediction checksums are exported. Full bundle hashes belong to scoring only.

| Policy | Default candidate condition |
|---|---|
| no-reclaim | Always RETAIN |
| interaction-timeout | No observed connect/reconnect/edit/execute-request for >=40000ms; service healthy |
| cpu-only | CPU <1% for complete consecutive 30000ms +10000ms hysteresis |
| resource-multi | Same CPU condition plus zero disk/network deltas and process/I/O/socket counts |
| interaction-aware | Resource-multi plus no interaction for 30000ms and healthy interaction service |

Only observations with occurrence and available_at_ms <= decision time enter the
interface. Resource windows must end by that time. Payloads use explicit
allowlists. Planned commands/durations and labels cannot enter policy inputs.
Connection alone does not mean interaction. DISCONNECT/LOGOUT do not cancel work
or reset user activity. Healthy service heartbeats continue while disconnected.
A fresh edit/request/connect/reconnect resets interaction-aware quiet timing; quiet
evidence can accumulate after that action, but no candidate can precede its 30s
grace or the full 40s resource quiet requirement.

CPU policies require CPU, mapping validity and loss count. Multi-signal policies
also require all disk/network/event counters. Memory is not an activity signal.
A missing required value, invalid mapping, positive loss, or source age >10000ms
makes the decision UNKNOWN. Interaction policies also require healthy service age
<=10000ms and an observed interaction origin. UNKNOWN resets quiet evidence;
recovery starts with a new valid resource window entirely after the reset tick.
Nonconsecutive windows restart quiet accumulation. Delayed old windows cannot
replace newer windows, bridge gaps retroactively or advance timing twice.
Thirty seconds quiet yields quiet_pending; another ten yields a recommendation.
An active window resets timing. Required missing groups cannot be replaced by zero.

Override thresholds using `--policy-config path.json` on predict/evaluate. Keys:
`cpu_threshold_pct` (1.0), `quiet_ms` (30000), `hysteresis_ms` (10000),
`interaction_grace_ms` (30000), `interaction_timeout_ms` (40000), `freshness_ms`
(10000). Timings are positive integer ms; CPU threshold is finite in [0,100].
These are accelerated experimental thresholds, not production defaults. Truth
recency remains fixed at 30000ms even during threshold sweeps. Effective settings,
SHA-256 config hash and policy version 1.0 are saved for every run.

A CPU policy can miss quiet useful work; event counters may help low-duty work yet
still miss a completely silent pending network wait. Editing can look resource
idle. No policy is asserted to win. No-reclaim measures missed opportunities only,
not actual savings. All operations work offline using standard-library file I/O.
