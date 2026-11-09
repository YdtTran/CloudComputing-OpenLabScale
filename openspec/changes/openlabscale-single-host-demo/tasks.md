## 1. Session backend ([#4](https://github.com/YdtTran/CloudComputing-OpenLabScale/issues/4))

- [x] 1.1 Define demo service configuration, server-derived identities, API payloads, lifecycle transitions, and timeout defaults.
- [x] 1.2 Implement the FIFO reservation ledger and test contention, impossible requests, expiry, and capacity return.
- [x] 1.3 Add bounded Docker provisioning and release, with isolation and ownership labels. Test cancellation during creation, ambiguous errors, restart cleanup, and isolation from unrelated containers.
- [x] 1.4 Verify request, status, and release against a real local Linux Docker host.

## 2. Student portal ([#5](https://github.com/YdtTran/CloudComputing-OpenLabScale/issues/5), after 1)

- [x] 2.1 Bridge an owned running session's Docker PTY over WebSocket. Verify cross-user denial and terminal closure on release.
- [x] 2.2 Build the student request, waiting, terminal, and release screens. Verify a browser command executes inside the assigned container and releases capacity.

## 3. Administrator dashboard ([#6](https://github.com/YdtTran/CloudComputing-OpenLabScale/issues/6), after 1)

- [x] 3.1 Expose an admin-only snapshot with lifecycle counts, queue, capacity, and real host and owned-container CPU and memory samples.
- [x] 3.2 Render the snapshot and verify queue changes under load, correct units, stale and unavailable indicators, and denial of student access.

## 4. Request-load experiment ([#7](https://github.com/YdtTran/CloudComputing-OpenLabScale/issues/7), after 1 and 3)

- [ ] 4.1 Implement the bounded client workflow and CSV/JSON export with reproducible configuration, timing, errors, timeouts, and peak running count.
- [ ] 4.2 Run the 5–10 client smoke test, then 100 synchronized submissions. Reconcile outcomes with service counts and verify cleanup.

## 5. Deployment and complete demonstration ([#8](https://github.com/YdtTran/CloudComputing-OpenLabScale/issues/8), after 2–4)

- [ ] 5.1 Document local and EC2 prerequisites, private access, host headroom, sizing, CPU credits, costs and teardown.
- [ ] 5.2 Verify the full student and administrator demo on local Linux and EC2, record the environment and outcomes, and confirm owned-resource cleanup.
- [ ] 5.3 Rerun the existing experiment regression suite and validate retained bundles before delivery.
