# Paper Assets

These deterministic tables and figure-data CSV files are generated from
the repository evidence by:

```powershell
python tools\generate_paper_assets.py --root .
```

Main sources:

```text
results/research_evidence/h015_effect_evidence_matrix.csv
results/research_evidence/research_claims_ledger.csv
results/reference_run/reference_run.csv
```

Generated assets:

```text
table1_h015_quality_runtime.csv/.md
table2_standard_gds_agreement.csv/.md
table3_mrr_marker_progression.csv/.md
table4_runtime_evidence.csv/.md
figure_data_mrr_marker_progression.csv
figure_data_runtime_breakdown.csv
figure_data_standard_xor.csv
asset_manifest.json
```
