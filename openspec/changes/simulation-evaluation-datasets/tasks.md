# Tasks

## 1. Dataset contract and validation

- [x] 1.1 Add the Python 3 `simulation` CLI structure and a versioned field dictionary for manifest and five CSV tables, including enums, units, payload fields, and source labels; verify command help runs and a minimal documented bundle parses without third-party dependencies.
- [x] 1.2 Implement bundle validation for checksums, identities/references, elapsed time, window availability, resource bounds, lifecycle consistency, complete truth coverage, and provenance; verify focused valid/invalid fixtures yield actionable file/row errors, including partial windows and unsupported versions.
- [x] 1.3 Document legacy timestamp discrepancies and explicit exclusion of automatic conversion; verify original four CSV checksums remain unchanged and legacy input fails with an explanatory schema/timing error.

## 2. Scenario inputs and independent truth

- [x] 2.1 Add ten documented 300-second templates covering all seven workload families and agreed interaction/failure cases; verify a coverage test checks required cases, bounded parameters, job-linked execute events, and trailing quiet periods.
- [x] 2.2 Implement deterministic schedule expansion, stable opaque IDs, independent per-session random streams, configurable count/start offsets, and overwrite protection; verify byte-identical repeat generation and unchanged original session schedules when sessions are appended.
- [x] 2.3 Generate complete independent interaction/workload/connection/eligibility intervals with fixed 30-second interaction truth semantics; verify editing-only retains, disconnect preserves jobs, waiting jobs retain, connected abandonment becomes eligible, and unknown execution remains unknown.
- [x] 2.4 Document replay parameters and future execution-acknowledgement mapping, including limits and job failure handling; verify representative CPU, network wait, disconnect, and reconnect schedules can be followed using only the documented fields.

## 3. Synthetic observations

- [x] 3.1 Generate five-second modeled resource windows and observed interaction/connection/service-health events using a separate noise stream and explicit source labels; verify no scenario/truth/command-duration fields appear in the observation projection and final short windows retain actual bounds.
- [x] 3.2 Add independent reporting outages, missing resource groups, delayed delivery, invalid mapping and event-loss fixtures; verify missing values remain null, available-at times prevent early access, and actual synthetic truth is unaffected by observation failure.
- [x] 3.3 Publish signal model ranges and limitations beside generator usage; verify every default generated bundle validates and is labeled synthetic in its manifest and observations.

## 4. Offline policy comparison

- [x] 4.1 Add an allowlisted causal policy input interface and prediction export, separate from truth scoring; verify changing truth/scenario plans leaves predictions unchanged and future observations remain inaccessible.
- [x] 4.2 Implement no-reclaim, fixed interaction timeout, CPU-only, resource multi-signal, and interaction-aware multi-signal with recorded configurations; verify hand-authored timelines demonstrate expected differences for editing, background jobs, bursts, and connected abandonment without asserting a policy must win.
- [x] 4.3 Implement freshness, missingness, event-loss, and mapping checks plus timer resets/recovery; verify exact 30+10-second boundaries, intentional disconnect versus unhealthy reporting, delayed-window handling, and UNKNOWN behavior through outages.
- [x] 4.4 Document policy inputs/defaults and recommendation-only behavior; verify the evaluation command runs without Docker, privileges, kernel features, or network services.

## 5. Scoring and example datasets

- [x] 5.1 Implement half-open truth joins, confusion counts, conditional precision/recall/F1 and false rates, coverage/idle capture, latency with censored intervals, and unknown exclusions; verify hand-calculated fixtures including all-UNKNOWN predictions, absent positive classes, phase boundaries, and undetected eligible intervals.
- [x] 5.2 Export deterministic predictions, JSON metrics, and a readable report grouped by policy/scenario/seed and overall with separate micro/macro summaries; verify all formulas, denominators, null metrics, configuration hashes, and synthetic provenance are present.
- [x] 5.3 Generate small versioned seed-42/43 development and seed-44 held-out example bundles and reports; document exact generate/validate/evaluate commands and scale options, and verify those commands work from a clean local checkout with Python 3.

## 6. Integration acceptance

- [x] 6.1 Run the complete generate–validate–predict–score flow twice and compare checksums; verify reproducibility, all required scenarios, all five policy outputs, zero legacy-file changes, and no live container actions.
- [x] 6.2 Validate a small hand-authored measured-mode contract fixture with execution acknowledgements and an unconfirmed job; verify measured/synthetic provenance cannot be pooled and planned execution is never accepted as actual success.
