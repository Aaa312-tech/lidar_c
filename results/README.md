# Results

This directory contains archived outputs from the current C++ LiDAR regression.

```text
reference_run/
reference_gds_compare/
research_evidence/
```

`reference_run` contains generated C++ GDS files for the default 9 benchmark
cases plus CSV/JSON summaries. The paths inside the summaries are sanitized to
portable relative paths.

`reference_gds_compare` contains geometry comparison reports against external
standard GDS files. The standard files themselves are not included; report paths
use the placeholder `standard_gds/`.

`research_evidence` contains the current H015 public validation ledger plus
retained H013 quality-fix evidence and H010 speed-stack validation evidence.
The ledgers tie every case to concrete benchmark YAML, GDS file names, SHA256
hashes, DRC metrics, timing metrics, and GDS XOR comparison reports. Paths use
placeholders such as `<PICDB_ROOT>`, `<STANDARD_GDS_DIR>`, and
`<EXPERIMENT_ROOT>` so the evidence can be read after moving the package.

These files are reference artifacts. New runs should normally write to a build
or checks directory inside the host PIC-DB checkout.
