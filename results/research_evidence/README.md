# Research Evidence Files

This directory contains portable evidence tables for the current H015 public
validation run, retained H013 quality-fix evidence, and retained H010
speed-stack validation evidence. Paths use placeholders so the files can be
read after moving the package:

```text
<LIDAR_C_ROOT>      root of this package
<PICDB_ROOT>        full PIC-DB checkout after merging this package
<STANDARD_GDS_DIR>  optional directory containing external standard GDS files
<EXPERIMENT_ROOT>   optional directory containing archived A/B trial outputs
```

## Files

| file | purpose |
|---|---|
| `h015_public_validation_summary.json` | Current top-level 9-case quality and runtime summary. |
| `h015_public_validation_evidence_ledger.csv` | Current per-case ledger with benchmark path, GDS path, DRC markers, timing, hashes, and XOR metrics. |
| `h015_public_validation_evidence_ledger.json` | JSON form of the current evidence ledger. |
| `h015_effect_evidence_matrix.csv` | Current per-case matrix joining generated GDS, SHA256, DRC, runtime, H013 GDS comparison, standard-GDS comparison, and selected A/B timing. |
| `h015_effect_evidence_matrix.json` | JSON form of the current effect evidence matrix. |
| `research_claims_ledger.csv` | Research claim ledger mapping quality/runtime/GDS claims to concrete evidence files. |
| `research_claims_ledger.json` | JSON form of the research claim ledger. |
| `artifact_scorecard.csv` | Requirement-by-requirement artifact scorecard with evidence and concrete GDS mappings. |
| `artifact_scorecard.json` | JSON form of the artifact scorecard. |
| `paper_assets/` | Generated paper-ready tables, Markdown table copies, figure-data CSV files, SVG figures, README, and asset manifest. |
| `h015_public_validation_run_summary.csv` | Sanitized H015 regression summary produced by `run_lidar_benchmark_regression.py`. |
| `h015_public_validation_run_summary.json` | JSON form of the sanitized H015 regression summary. |
| `h015_vs_h013_reference_gds_pair_summary.csv` | GDS hash/geometry comparison between the previous H013 reference GDS and current H015 GDS. |
| `h015_vs_h013_reference_gds_layer_xor.csv` | Layer-by-layer XOR for H013 reference GDS vs current H015 GDS. |
| `h015_standard_gds_pair_summary.csv` | Current GDS geometry comparison against the three external standard/manual GDS files. |
| `h015_standard_gds_layer_xor.csv` | Current layer-by-layer XOR against the three external standard/manual GDS files. |
| `h015_ab_timing_n3_summary_by_case.csv` | Three-repetition A/B timing summary for H015 quality changes. |
| `h015_ab_timing_n3_summary.json` | JSON aggregate for the H015 n=3 A/B timing run. |
| `h013_public_validation_summary.json` | Retained H013 top-level 9-case quality and runtime summary. |
| `h013_public_validation_evidence_ledger.csv` | Retained H013 per-case ledger with benchmark path, GDS path, DRC markers, timing, hashes, and XOR metrics. |
| `h013_public_validation_evidence_ledger.json` | JSON form of the retained H013 evidence ledger. |
| `h013_public_validation_run_summary.csv` | Sanitized H013 regression summary produced by `run_lidar_benchmark_regression.py`. |
| `h013_public_validation_run_summary.json` | JSON form of the sanitized H013 regression summary. |
| `h013_vs_h010_reference_gds_pair_summary.csv` | GDS hash/geometry comparison between the previous H010 reference GDS and H013 GDS. |
| `h013_vs_h010_reference_gds_layer_xor.csv` | Layer-by-layer XOR for H010 reference GDS vs H013 GDS. |
| `h013_standard_gds_pair_summary.csv` | H013 GDS geometry comparison against the three external standard/manual GDS files. |
| `h013_standard_gds_layer_xor.csv` | H013 layer-by-layer XOR against the three external standard/manual GDS files. |
| `h013_min_ab_timing_summary_by_case.csv` | One-repetition minimum A/B timing summary for H013 quality changes. |
| `h013_min_ab_timing_summary.json` | JSON aggregate for the H013 minimum A/B timing run. |
| `h013_ab_timing_n3_summary_by_case.csv` | Three-repetition A/B timing summary for H013 quality changes. |
| `h013_ab_timing_n3_summary.json` | JSON aggregate for the H013 n=3 A/B timing run. |
| `h010_public_validation_summary.json` | Retained H010 top-level 9-case quality and runtime summary. |
| `h010_public_validation_evidence_ledger.csv` | Retained H010 per-case ledger with benchmark path, GDS path, DRC markers, timing, hashes, and XOR metrics. |
| `h010_public_validation_evidence_ledger.json` | JSON form of the retained H010 evidence ledger. |
| `h010_public_validation_run_summary.csv` | Sanitized regression summary produced by `run_lidar_benchmark_regression.py`. |
| `h010_public_validation_run_summary.json` | JSON form of the sanitized regression summary. |
| `h010_reference_vs_public_run_gds_pair_summary.csv` | GDS hash/geometry comparison between shipped reference GDS and reproduced public-run GDS. |
| `h010_reference_vs_public_run_gds_layer_xor.csv` | Layer-by-layer XOR for shipped reference GDS vs reproduced public-run GDS. |
| `h010_standard_vs_public_run_gds_pair_summary.csv` | GDS geometry comparison against the three external standard/manual GDS files. |
| `h010_standard_vs_public_run_gds_layer_xor.csv` | Layer-by-layer XOR against the three external standard/manual GDS files. |

## Expected Gates

The current H015 reference run should satisfy:

```text
cases: 9
ok_cases: 9
DRC-clean cases: 6
total markers: 89
route-geometry markers: 88
MRR marker delta vs H010: -30
```

The standard-GDS validator should satisfy:

```text
clements_8x8 XOR: 0.0 um^2
multiportmmi_8x8 overlap: 0.999978471
multiportmmi_16x16 overlap: 0.999969043
```

The standard GDS files are not part of this repository and are not router
inputs. They are used only to generate comparison reports.

## Paper Assets

Regenerate the table, figure-data, and SVG assets from the repository root:

```powershell
python tools\generate_paper_assets.py --root .
```

Validate them together with the rest of the artifact:

```powershell
python tools\validate_research_artifact.py --root .
```
