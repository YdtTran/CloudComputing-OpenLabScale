# Bundle schema 1.0

Python 3 standard library only. `simulation/contract.py:TABLES` is the ordered CSV
header dictionary. UTF-8 CSV, JSON object payloads, empty optional cells, no NaN.
Every row includes `run_id` equal to the manifest. IDs are opaque nonempty strings;
references are exact. Numbers use decimal notation. Time is integer elapsed
milliseconds from a common coordinator origin, intervals are half-open [start,end).
Empty numeric cells mean unknown, never zero. No timestamp inference is performed.

## Manifest

`schema_version="1.0"`, `generator_version` string, `run_id`, integer `seed`,
`config` (effective session_count, start_offset_ms, cpu_limit_cores, memory_limit_mb),
`duration_ms` (run end), `sample_ms=5000`, `interaction_truth_ms=30000`,
`clock="elapsed_ms"`, `origin_utc` null or UTC ISO-8601 string ending Z,
`source_mode` synthetic or measured, `files` mapping all five CSV filenames to
SHA-256 hex digests. Optional `host_metadata` object. Synthetic manifests include
`limitations`. Measured manifests must identify the collector in generator_version.

## Tables

| Table | Fields beyond run_id | Meaning |
|---|---|---|
| sessions | session_id,user_id,container_instance_id,scenario_id,start_ms,end_ms,cpu_limit_cores,memory_limit_mb | Unique session and container instance; scenario for scoring only. Positive CPU quota in cores, memory limit in MiB (2^20 bytes). End is observation end, not logout. |
| events | event_id,session_id,at_ms,action,job_id,parameters_json | Unique event; optional job ID except job actions. Action CONNECT,EDIT,EXECUTE,DISCONNECT,RECONNECT,LOGOUT,JOB_START,JOB_COMPLETE,JOB_ERROR,JOB_INTERRUPT. EXECUTE is a request; JOB_START is an acknowledgement. Completion/error/interrupt is terminal. Disconnect does not terminate jobs. |
| phases | phase_id,session_id,job_id,start_ms,end_ms,workload,parameters_json | Unique phase; workload CPU,DISK_IO,NETWORK_WAIT,BURST,LOW_CPU,IDLE,MIXED. MIXED templates expand to concrete phases. IDLE has no job. |
| observations | session_id,container_instance_id,kind,at_ms,available_at_ms,window_start_ms,window_end_ms,source,status,payload_json | Kinds interaction,connection,interaction_health,resource. Status OK,DEGRADED,UNHEALTHY. Resource at_ms=end; 0 < window length <=5000; final partial retained. Available time >= event/end, may exceed session end. Nonresource windows empty. |
| truth | session_id,start_ms,end_ms,interaction,connection,workload,eligibility,reason,label_source | Complete partition per session. Interaction RECENT,ABSENT,UNKNOWN; connection CONNECTED,DISCONNECTED,UNKNOWN; workload ACTIVE,IDLE,UNKNOWN; eligibility RETAIN,IDLE_ELIGIBLE,UNKNOWN. Label source synthetic_scenario or execution_ack matching mode. Reason explains semantics. |

## JSON payload dictionaries

Events/phase replay parameters: `cpu_duty` fraction [0,1], `memory_bytes`
[0,session memory limit], `disk_file_bytes` and `disk_rate_bytes_s` nonnegative
bounded bytes and bytes/s, `network_bytes` nonnegative bounded bytes,
`response_delay_ms` nonnegative bounded ms, `burst_width_ms` positive ms <=
`burst_period_ms` positive ms. `outcome` COMPLETE,ERROR,INTERRUPT,UNCONFIRMED.
EXECUTE references the phase job, with resource parameters in phases. Lifecycle
acknowledgements have `{}` payloads. All work must end within the declared phase.

Interaction/connection observation payload: only `action` (EDIT,EXECUTE_REQUEST,
CONNECT,DISCONNECT,RECONNECT,LOGOUT). No commands or durations.
Health payload: `healthy` boolean for the reporting service, independent of client
connection. Health heartbeat every 5000 ms, including after intentional disconnect.

Resource payload fields (null is missing): `cpu_pct` [0,100], percentage of declared
CPU quota; `memory_bytes` [0,limit]; `disk_read_bytes`,`disk_write_bytes`,
`network_rx_bytes`,`network_tx_bytes` nonnegative integer window deltas;
`process_events`,`io_events`,`socket_events`,`loss_count` nonnegative integer
window counts; `mapping_valid` boolean. `cgroup_source` synthetic_cgroup_v2 or
cgroup_v2; `event_source` synthetic_ebpf or ebpf. Missing cgroup/event groups retain
null values. Observation envelope source is synthetic_model or measured_collector
for resources, synthetic_session_service or session_service for other kinds.
All source labels must match manifest mode. Positive loss or invalid mapping is
explicit degraded evidence. Counts do not prove useful work.

## Minimal parseable fixture

`tests/fixtures.py:write_minimal` writes a one-session, 45-second pure-idle bundle
with a complete two-interval truth partition, an explicit CONNECT, no jobs, empty phases and
observations, and checksummed files. Missing observations are valid input and cause
policies that require evidence to abstain. Run:

```sh
python3 -c 'from tests.fixtures import write_minimal; write_minimal("/tmp/minimal-v1")'
python3 -m simulation validate /tmp/minimal-v1
```
