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
| toy_example_gp | ok | 0 | 1 | 2 | 0 | 0.180067s |
| mrr_weight_bank_4x4 | ok | 1 | 0 | 36 | 3 | 1.746271s |
| mrr_weight_bank_8x8 | ok | 0 | 2 | 106 | 6 | 3.351774s |
| mrr_weight_bank_16x16 | ok | 0 | 86 | 389 | 36 | 43.595247s |
| clements_8x8 | ok | 1 | 0 | 79 | 0 | 1.596117s |
| clements_16x16 | ok | 1 | 0 | 290 | 2 | 14.872963s |
| multiportmmi_8x8 | ok | 1 | 0 | 177 | 33 | 30.590119s |
| multiportmmi_16x16 | ok | 1 | 0 | 349 | 63 | 100.828301s |
| multiportmmi_32x32 | ok | 1 | 0 | 695 | 125 | 613.014050s |

Notes:

```text
toy_example_gp has a known input component overlap marker.
mrr_weight_bank_8x8 and mrr_weight_bank_16x16 still need more MRR-specific cleanup,
but H011/H013/H015 reduce their markers from 8/110 to 2/86.
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
