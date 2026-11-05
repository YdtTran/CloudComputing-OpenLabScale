# Future execution contract

This package writes schedules and recommendations; it performs no live actions.
An adapter can replay a session using only sessions/events/phases and manifest:

1. Map one host monotonic clock to manifest elapsed origin. UTC is display only.
   Allocate the session container with declared quota and memory limits. Use a new
   container_instance_id after restart. Enforce concurrency outside this bundle.
2. At session-relative CONNECT/EDIT/EXECUTE/DISCONNECT/RECONNECT times, drive the
   simulated session service. EXECUTE's job_id selects all phase rows for that job,
   in start order. Schedule generation includes future synthetic lifecycle rows;
   a real adapter must replace those with actual acknowledgements.
3. For CPU, use cpu_duty of the configured quota for the phase duration. Memory
   demand is memory_bytes, bounded by the container limit. Disk uses a private
   bounded disk_file_bytes file and disk_rate_bytes_s, with modeled alternating
   10-second active/wait segments. Network uses a controlled local peer with
   network_bytes total and response_delay_ms; never rely on a public endpoint.
   BURST uses cpu_duty for burst_width_ms every burst_period_ms from phase start.
   LOW_CPU is useful duty-cycle work. IDLE has no job. Mixed templates are already
   expanded to concrete phase rows. Adapters must enforce all bounds and deadlines.
4. DISCONNECT only changes client connection. For cpu-background, request/start
   at 20000, disconnect at 40000, continue job through 180000. For network-wait,
   preserve the pending operation across the same disconnect. For reconnect,
   connect 0, disconnect 40000, reconnect 90000, resume edits 100000–180000.
5. Capture actual JOB_START and JOB_COMPLETE/JOB_ERROR/JOB_INTERRUPT with job_id
   and elapsed at_ms. Requests alone never prove success. Error or missing start/
   terminal confirmation makes workload UNKNOWN for the affected interval. Pending
   unconfirmed work is UNKNOWN through observation end. Successful acknowledged
   start/end establishes ACTIVE only over that actual interval, including waits.
   Known recent interaction can still justify RETAIN while workload is UNKNOWN.
6. Measured observations use measured_collector/cgroup_v2/ebpf/session_service
   sources, source_mode=measured and label_source=execution_ack. The validator
   checks labels against actual lifecycle records; planned phases cannot replace
   acknowledgement evidence. Do not pool measured and synthetic score groups.

Replay parameters have hard contract maxima: CPU duty 1; memory <= session limit;
disk file/network total <=1 GiB; disk rate <=256 MiB/s; waits and burst periods <=
phase duration. Future adapters must handle resource exhaustion, errors and deadline
interruptions explicitly and record actual outcomes, rather than copying planned
completion. None of this package's outputs establishes executable adapter fidelity.
