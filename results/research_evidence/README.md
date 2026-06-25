# Research Evidence Files

This directory contains portable evidence tables for the current H013 public
validation run and the retained H010 speed-stack validation run. Paths use
placeholders so the files can be read after moving the package:

```text
<LIDAR_C_ROOT>      root of this package
<PICDB_ROOT>        full PIC-DB checkout after merging this package
<STANDARD_GDS_DIR>  optional directory containing external standard GDS files
```

## Files

| file | purpose |
|---|---|
| `h013_public_validation_summary.json` | Current top-level 9-case quality and runtime summary. |
| `h013_public_validation_evidence_ledger.csv` | Current per-case ledger with benchmark path, GDS path, DRC markers, timing, hashes, and XOR metrics. |
| `h013_public_validation_evidence_ledger.json` | JSON form of the current evidence ledger. |
| `h013_public_validation_run_summary.csv` | Sanitized H013 regression summary produced by `run_lidar_benchmark_regression.py`. |
| `h013_public_validation_run_summary.json` | JSON form of the sanitized H013 regression summary. |
| `h013_vs_h010_reference_gds_pair_summary.csv` | GDS hash/geometry comparison between the previous H010 reference GDS and current H013 GDS. |
| `h013_vs_h010_reference_gds_layer_xor.csv` | Layer-by-layer XOR for H010 reference GDS vs current H013 GDS. |
| `h013_standard_gds_pair_summary.csv` | Current GDS geometry comparison against the three external standard/manual GDS files. |
| `h013_standard_gds_layer_xor.csv` | Current layer-by-layer XOR against the three external standard/manual GDS files. |
| `h013_min_ab_timing_summary_by_case.csv` | One-repetition minimum A/B timing summary for H013 quality changes. |
| `h013_min_ab_timing_summary.json` | JSON aggregate for the H013 minimum A/B timing run. |
| `h010_public_validation_summary.json` | Top-level 9-case quality and runtime summary. |
| `h010_public_validation_evidence_ledger.csv` | Per-case ledger with benchmark path, GDS path, DRC markers, timing, hashes, and XOR metrics. |
| `h010_public_validation_evidence_ledger.json` | JSON form of the evidence ledger. |
| `h010_public_validation_run_summary.csv` | Sanitized regression summary produced by `run_lidar_benchmark_regression.py`. |
| `h010_public_validation_run_summary.json` | JSON form of the sanitized regression summary. |
| `h010_reference_vs_public_run_gds_pair_summary.csv` | GDS hash/geometry comparison between shipped reference GDS and reproduced public-run GDS. |
| `h010_reference_vs_public_run_gds_layer_xor.csv` | Layer-by-layer XOR for shipped reference GDS vs reproduced public-run GDS. |
| `h010_standard_vs_public_run_gds_pair_summary.csv` | GDS geometry comparison against the three external standard/manual GDS files. |
| `h010_standard_vs_public_run_gds_layer_xor.csv` | Layer-by-layer XOR against the three external standard/manual GDS files. |

## Expected Gates

The current H013 reference run should satisfy:

```text
cases: 9
ok_cases: 9
DRC-clean cases: 6
total markers: 99
route-geometry markers: 98
MRR marker delta vs H010: -20
```

The standard-GDS validator should satisfy:

```text
clements_8x8 XOR: 0.0 um^2
multiportmmi_8x8 overlap: 0.999978471
multiportmmi_16x16 overlap: 0.999969043
```

The standard GDS files are not part of this repository and are not router
inputs. They are used only to generate comparison reports.
