# Two-Clock Causal Projection Gate

Policy evaluation decisions at `decision_ms` must only observe metrics where both event timestamp (`at_ms <= decision_ms`) and publication delay (`available_at_ms <= decision_ms`, with `window_end_ms <= decision_ms` for windowed telemetry) have elapsed. We enforce this two-clock gate to completely eliminate lookahead bias and prevent unrealistic reclamation policies that depend on future or un-flushed telemetry.
