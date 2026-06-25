# Research Evidence Files

This directory contains portable evidence tables for the H010 public validation
run. Paths use placeholders so the files can be read after moving the package:

```text
<LIDAR_C_ROOT>      root of this package
<PICDB_ROOT>        full PIC-DB checkout after merging this package
<STANDARD_GDS_DIR>  optional directory containing external standard GDS files
```

## Files

| file | purpose |
|---|---|
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

The reproduced public run should satisfy:

```text
cases: 9
ok_cases: 9
exact GDS vs package reference: 9 / 9
total reference-vs-reproduced XOR: 0.0 um^2
```

The standard-GDS validator should satisfy:

```text
clements_8x8 XOR: 0.0 um^2
multiportmmi_8x8 overlap: 0.999978471
multiportmmi_16x16 overlap: 0.999969043
```

The standard GDS files are not part of this repository and are not router
inputs. They are used only to generate comparison reports.
