# Legacy data

The four original CSV files previously stored directly under `data/` have been
removed, along with their checksum inventory. Current examples are versioned
bundles in this directory; see [README.md](README.md) for reproduction commands.

The removed examples contained abbreviated timestamps such as `00:00.0` and
`08:41.5`. No reliable date, hour rollover, timezone, or full precision could be
reconstructed from those strings alone. The validator still requires versioned
elapsed-ms bundles and rejects ambiguous legacy input. There is no automatic
conversion.

Any future conversion requires an explicit timing mapping and independent
execution evidence. Unknown durations and UNKNOWN labels must remain unknown,
including silent JuNE intervals. Legacy modeled metrics cannot be pooled with
measured observations or used as measured truth.
