# Current Results

This document records the latest generated C++ LiDAR GDS results included in this package.

## Output directory

```text
results/reference_run/
```

## Generated GDS files

```text
toy_example_gp_cpp.gds
mrr_weight_bank_4x4_cpp.gds
mrr_weight_bank_8x8_cpp.gds
mrr_weight_bank_16x16_cpp.gds
clements_8x8_cpp.gds
clements_16x16_cpp.gds
multiportmmi_8x8_cpp.gds
multiportmmi_16x16_cpp.gds
multiportmmi_32x32_cpp.gds
```

## Regression summary

| case | status | DRC clean | markers | routes | crossings | C++ core route time |
|---|---|---:|---:|---:|---:|---:|
| toy_example_gp | ok | 0 | 1 | 2 | 0 | 0.223614s |
| mrr_weight_bank_4x4 | ok | 1 | 0 | 36 | 3 | 1.436542s |
| mrr_weight_bank_8x8 | ok | 0 | 8 | 105 | 6 | 4.900504s |
| mrr_weight_bank_16x16 | ok | 0 | 110 | 375 | 31 | 58.900260s |
| clements_8x8 | ok | 1 | 0 | 79 | 0 | 1.308980s |
| clements_16x16 | ok | 1 | 0 | 290 | 2 | 14.863009s |
| multiportmmi_8x8 | ok | 1 | 0 | 177 | 33 | 28.720445s |
| multiportmmi_16x16 | ok | 1 | 0 | 349 | 63 | 123.624393s |
| multiportmmi_32x32 | ok | 1 | 0 | 695 | 125 | 735.129981s |

Notes:

```text
toy_example_gp has a known input component overlap marker.
mrr_weight_bank_8x8 and mrr_weight_bank_16x16 need more MRR-specific cleanup.
Clements and Multiport MMI cases are DRC clean in this latest run.
```

## Standard-GDS comparison

The following comparisons use the three user-provided standard GDS files.

| case | standard XOR | overlap ratio | conclusion |
|---|---:|---:|---|
| clements_8x8 | 0.000000 | 1.000000000 | exact geometry match |
| multiportmmi_8x8 | 5.091752 | 0.999978471 | visually almost identical, tiny crossing-area difference remains |
| multiportmmi_16x16 | 18.680864 | 0.999969043 | visually almost identical, tiny crossing-area difference remains |

Detailed files:

```text
results/reference_gds_compare/gds_pair_summary.csv
results/reference_gds_compare/gds_layer_xor.csv
results/reference_gds_compare/gds_xor_hotspots.csv
```

## Important interpretation

The generated C++ GDS files are not copied from the standard GDS files.

Evidence:

```text
file sizes differ
SHA256 hashes differ
MMI cell counts differ
standard GDS files are only referenced by compare_gds_geometry.py
```

`clements_8x8` is visually identical because it is truly 0 XOR. The two MMI cases look identical in a viewer because their overlap ratios are above 0.99996, but they are not mathematically exact.
