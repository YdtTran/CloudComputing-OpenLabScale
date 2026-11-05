# Mandatory Policy Abstention on Degraded Telemetry

When telemetry sources (e.g. disk/network counters or event ring buffers) are uncollected, null, or corrupted, multi-signal policies must emit `UNKNOWN` (abstention) rather than treating missing data as zero activity. This prevents fatal false-idle classifications and stops unapproved container destruction under observability failures.
