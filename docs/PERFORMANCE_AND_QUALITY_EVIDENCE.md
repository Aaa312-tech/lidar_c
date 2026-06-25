# Performance And Quality Evidence

This document records the portable evidence shipped with this package and the
validated performance claims from the research run. All repository paths below
are relative to the `lidar_c` root.

## Shipped GDS Evidence

The current archived C++ outputs are in:

```text
results/reference_run/
```

Generated GDS files:

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

Per-case route, DRC, and timing table:

```text
results/reference_run/reference_run.csv
results/reference_run/reference_run.json
```

## Shipped Standard-GDS Comparison

The standard-GDS comparison reports are in:

```text
results/reference_gds_compare/gds_pair_summary.csv
results/reference_gds_compare/gds_layer_xor.csv
results/reference_gds_compare/gds_xor_hotspots.csv
```

The external standard GDS files are not included in the package. They are
validation inputs only and are never used by the router to generate routes.

Summary:

| case | generated GDS | DRC | standard XOR um^2 | overlap | interpretation |
|---|---|---:|---:|---:|---|
| clements_8x8 | `results/reference_run/clements_8x8_cpp.gds` | clean | 0.000000 | 1.000000000 | exact geometry match |
| multiportmmi_8x8 | `results/reference_run/multiportmmi_8x8_cpp.gds` | clean | 5.091752 | 0.999978471 | tiny crossing-area residual |
| multiportmmi_16x16 | `results/reference_run/multiportmmi_16x16_cpp.gds` | clean | 18.680864 | 0.999969043 | tiny crossing-area residual |

## Full Regression Quality

The shipped reference run covers 9 benchmark cases:

```text
toy_example_gp
mrr_weight_bank_4x4
mrr_weight_bank_8x8
mrr_weight_bank_16x16
clements_8x8
clements_16x16
multiportmmi_8x8
multiportmmi_16x16
multiportmmi_32x32
```

The Clements and Multiport MMI cases are DRC-clean in the archived reference
run. `toy_example_gp` has a known input component overlap marker. The larger MRR
cases still retain route-geometry markers and are documented as remaining work
rather than hidden as successes.

## Validated Speed Claim

The accepted optimization stack is:

```text
H005: A* allocation reserve
H007: structured A* node keys
H008: unordered HeapDict entry lookup
```

In the research validation run, this stack was compared against the initial C++
seed on selected larger cases with paired baseline/candidate repetitions.

Validated paired A/B result:

```text
cases: clements_16x16, mrr_weight_bank_16x16, multiportmmi_16x16
repetitions: 3 per case
quality same in all repetitions: true
GDS exact in all repetitions: true
average route-core delta: -9.057515%
average full-flow delta: -1.612740%
```

Interpretation:

The defensible performance claim is the repeated route-core improvement. The
full-flow improvement is smaller because it includes YAML conversion, Python
GDS rendering, KLayout/GDS writing, and filesystem I/O.

## Negative Runtime Result

One later candidate was rejected:

```text
H009: current-node scalar snapshot after A* heap pop
```

It preserved GDS exactly but failed the speed criterion:

```text
cases: clements_16x16, multiportmmi_8x8
repetitions: 3
quality same in all repetitions: true
GDS exact in all repetitions: true
average route-core delta: +3.143609%
average full-flow delta: +2.692912%
```

This negative result is important: output-preserving code changes are accepted
only when paired timing supports them.

## Reproduce Locally

Run the full default regression after merging into a PIC-DB checkout:

```powershell
.\tools\run_all_cases.ps1 `
  -PicdbRoot "<path-to-full-PIC-DB>" `
  -PythonExe "<path-to-gds-render-python>" `
  -DriverPython "<path-to-gds-render-python>" `
  -OutputDir build_native_release\checks\benchmark_regression `
  -Prefix benchmark_regression
```

Then compare against standard GDS files if available:

```powershell
python tools\pr_lidar_native\scripts\compare_gds_geometry.py `
  --standard-dir "<path-to-standard-gds-directory>" `
  --cpp-dir build_native_release\checks\benchmark_regression `
  --out-dir build_native_release\checks\reference_gds_compare
```
