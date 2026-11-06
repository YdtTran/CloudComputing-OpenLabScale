# Tasks

## 1. Core Policy Enhancement

- [x] 1.1 Add `socket_grace_ms` configuration parameter (default 160,000ms) to `simulation/policies.py`
- [x] 1.2 Implement socket silence duration tracking and grace period in `interaction-aware` and `resource-multi` policies in `simulation/policies.py`

## 2. Unit Testing & Invariants

- [x] 2.1 Add unit tests covering active wait ($< \text{socket\_grace\_ms}$) and zombie expiration ($\ge \text{socket\_grace\_ms}$) in `tests/test_policies.py`
- [x] 2.2 Run full test suite `python -m unittest discover -s tests -v` to verify zero regressions

## 3. Benchmark Verification & Documentation

- [x] 3.1 Run evaluation on benchmark bundle to confirm `network-wait` False Positives drop to 0
- [x] 3.2 Update `README.md` documenting v1.1 changes, new parameter, and updated benchmark results

## Workflow follow-up

- Run `/opsx-archive` to sync delta specs and archive the change.
