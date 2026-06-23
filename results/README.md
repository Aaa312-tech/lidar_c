# Results

This directory contains archived outputs from the current C++ LiDAR regression.

```text
reference_run/
reference_gds_compare/
```

`reference_run` contains generated C++ GDS files for the default 9 benchmark
cases plus CSV/JSON summaries. The paths inside the summaries are sanitized to
portable relative paths.

`reference_gds_compare` contains geometry comparison reports against external
standard GDS files. The standard files themselves are not included; report paths
use the placeholder `standard_gds/`.

These files are reference artifacts. New runs should normally write to a build
or checks directory inside the host PIC-DB checkout.
