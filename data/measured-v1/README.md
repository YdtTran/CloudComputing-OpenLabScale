# Debian measured first slice

The seed-42 source is retained in `source-42/`. The measured runner selects
`cpu-background` and `pure-idle` from its default ten sessions. Source and
existing simulation datasets are preserved.

- [First successful run](debian-first-run/acceptance.json): actual CPU job
  started at 20.207s, disconnected at 40.013s and completed at 180.218s.
  Mean quota-normalized CPU was 71.1% during background work and 0% in both
  the idle container and the trailing quiet period.
- [Measured policy report](debian-first-run/evaluation/report.md): all five
  policies share the timeline. Resource-multi and interaction-aware each
  abstain on all 120 decision ticks because required signals are missing.
- [Successful fresh repeat](debian-repeat-final/acceptance.json): independently
  verified the same CPU/idle contrast, background completion, raw exec attribution,
  trailing quiet and abstentions. Collector image metadata remained correct even
  after retagging made the running image's old ID uninspectable by Docker.
- [Fault acceptance](fault-checks/acceptance.json): a real container restart
  changed PID/start time/cgroup identity and caused an attribution abort.
  SIGTERM during disconnected CPU execution retained incomplete evidence.
  Both trials removed only their owned projects; all unrelated containers
  remained running.
- [Final-code fault checks](fault-checks-final/acceptance.json) repeated restart,
  interruption and unrelated-container preservation after the provenance fix.

`debian-repeat-run/` intentionally retains the earlier incomplete repeat that
exposed the late image-inspection failure. It was not overwritten or presented
as a successful experiment; the fresh repeat verifies the startup-snapshot fix.

Each run retains `raw-signals.jsonl`, `raw-cgroup.json`, `actual-actions.json`,
`source-plan.json`, the five contract tables, image/host/probe metadata,
checksums, finalized predictions, scoring output and completion/cleanup status.
Fault trials intentionally remain `incomplete`; they are not valid successful
bundles. Recommendations never trigger a container stop.

Collection covers cgroup CPU/RAM and `sched:sched_process_exec` only. Every
resource window is DEGRADED; I/O/socket/disk/network values are null. These
results do not establish general detector accuracy or monitoring overhead.
The verified Debian collector needs explicit SYS_ADMIN; workloads have no
capabilities or host mounts. See [run instructions](../../measured/README.md).

Measured times and fresh identities differ between runs. Ubuntu, full workload
coverage, complete I/O/socket collection and overhead validation remain deferred
as specified by the change.
