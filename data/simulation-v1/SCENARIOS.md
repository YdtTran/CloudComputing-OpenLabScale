# Default templates

The authoritative templates are `simulation/scenarios.py`. Every lifetime is
[0,300000) ms. All connect at 0; there is no observable abandonment event.
Quota is 0.5 CPU cores and 256 MiB by default. A job request and acknowledged start
occur at the first job phase; completion occurs at the last end. MIXED is a
sequence of concrete phases belonging to one job. All cases end with >=90 seconds
of quiet after the final interaction grace/job. No logout is inferred at end.

| Template | Schedule in seconds | Expected truth |
|---|---|---|
| cpu-background | CPU 20–180; disconnect 40 | Retain 0–180, eligible thereafter; disconnect preserves job |
| disk-wait | DISK_IO 20–180 | Retain 0–180, including low CPU waits; then eligible |
| network-wait | NETWORK_WAIT 20–180; disconnect 40 | Retain 0–180 even during silent waits; then eligible |
| bursty | BURST 20–180, 200ms pulse/10s | Retain through job, then eligible |
| low-use | LOW_CPU 20–180 | Useful low duty work retains through 180; then eligible |
| pure-idle | Connect and remain connected | Retain 0–30, eligible 30–300 |
| mixed | Edit 10; CPU 20–70, disk 70–120, burst 120–180 | Retain through 180, then eligible |
| editing-only | Edit every 10s from 10 through 180 | Retain 0–210 despite quiet resources; then eligible |
| reconnect | Edit 10,20,30; disconnect 40; reconnect 90; edit 100–180/10s | Retain 0–60 and 90–210; eligible 60–90 and 210–300 |
| signal-loss | Edit 10,20; service outage 50–100; resource outage 150–175 | Retain 0–50, eligible 50–300 independently of outages |

Signal-loss additionally has missing cgroup 110–115, missing event group 120–125,
invalid mapping 130–135, event loss 180–185, and 15s delivery delay for the window
ending 195. Fault intervals use window start times. Health outage removes observed
interactions in that interval and emits unhealthy service heartbeats. These faults
change observations only. Later quiet permits recovery. Additional seeds vary
bounded amplitudes and memory, keeping the fixed schedule assertions. Count >10
repeats templates with independent per-session streams; count <10 is a subset.
