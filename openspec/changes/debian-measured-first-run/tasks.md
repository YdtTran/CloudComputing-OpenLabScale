# Tasks

## 1. Container images and host readiness

- [x] 1.1 Add the multi-stage Clang/bpftool/libbpf collector image, bounded CPU/idle worker image and Compose configuration; verify image builds and Compose validation, with no workload privileges/host mounts or collector Docker socket.
- [x] 1.2 Implement a read-only preflight and actual sched_process_exec attachment readiness check; verify denied Docker/tracefs/BTF/capability fixtures fail actionably before workload execution, then record a successful real Debian attach or the exact blocking diagnostic.
- [x] 1.3 Document build commands, required host kernel features and the verified capability/mount/namespace set in measured run instructions; verify configuration matches the documentation and does not silently fall back to privileged mode or synthetic collection.

## 2. Bounded replay and lifecycle evidence

- [x] 2.1 Add the measured run CLI and selection of exactly one cpu-background and pure-idle session from a validated source; test missing/duplicate selections, unsupported phases, resource bounds and unchanged source hashes, and document why generate --count 2 is unsuitable.
- [x] 2.2 Implement coordinator/worker readiness, a verified common monotonic origin and actual action/start/terminal acknowledgement records; test differing planned/actual completion and ensure disconnect preserves the CPU job, with declared CPU duty, memory and deadline limits enforced.
- [x] 2.3 Implement unique run ownership, refusal of nonempty outputs, incomplete staging status and bounded cleanup; test interruption/startup failure, cleanup timeout diagnostics and preservation of unrelated containers, and document owned cleanup versus policy-driven reclaim.

## 3. Real collection and attribution

- [x] 3.1 Implement the process-exec eBPF probe, ring-buffer reader and independently readable loss counter; verify an owned worker exec emits timestamp/PID/TGID/cgroup evidence, unrelated events are excluded and simulated loss/read failure yields positive/unknown loss rather than fabricated zero.
- [x] 3.2 Implement Docker-lifecycle-to-cgroup attribution and cgroup CPU/memory sampling without Docker resource statistics; test quota normalization, memory readings, baseline resets and restart/mapping changes, verifying abort and no old-to-new-instance relabeling.
- [x] 3.3 Aggregate measured five-second windows with actual availability and raw evidence; test delayed events, missing samples, sampling overruns and partial final windows, and verify omitted I/O/socket/disk/network values remain null with DEGRADED status. Document exact probe coverage beside the exported evidence.

## 4. Measured export and evaluator integration

- [x] 4.1 Implement acknowledgement-derived measured truth independently of planned phases; test actual late completion, failed/missing acknowledgements, interaction grace and disconnect behavior against the existing measured validator semantics.
- [x] 4.2 Export all existing tables and manifest with fresh identity mappings, source hashes, actual event provenance, host/image/probe configuration and output checksums; verify measured fixtures pass validation, invalid joins/provenance fail and unobserved interactions/health are not invented.
- [x] 4.3 Connect measured export to separate predict and score stages; verify truth changes cannot affect predictions, all five policies retain the common timeline, missing required signals cause multi-signal UNKNOWN/abstention and reports disclose partial collection without claiming full accuracy or overhead. Correct measured report wording only where necessary and document the exact commands.

## 5. First real-run acceptance

- [x] 5.1 Execute the documented seed-42 CPU-background/pure-idle experiment on Debian after preflight; retain raw signals, actual lifecycle evidence, host/image metadata, validated measured bundle, predictions and score report. Verify actual CPU-job exec attribution and cgroup CPU contrast, preserved job across disconnect, trailing quiet observations and explicit multi-signal abstentions without requiring any policy to win.
- [x] 5.2 Exercise a selected-container restart and an interrupted run; verify invalid attribution cannot remain healthy, replacements are not assigned old identities, incomplete evidence is identified and cleanup affects only owned resources. Retain diagnostics and confirm no policy recommendation triggers a stop.
- [x] 5.3 Run the existing simulation test suite and measured fixture tests, compare existing source/generated dataset hashes and verify repeat execution uses a fresh output without overwriting earlier evidence; record that measured timings are not byte-deterministic and Ubuntu/full-workload/overhead validation is deferred.
