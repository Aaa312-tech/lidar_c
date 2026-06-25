# Table 4: Runtime Evidence

Route-core timing is interpreted separately from full-flow timing.

| scope | cases | repetitions | route_core_metric | full_flow_metric | quality_gate | gds_gate | primary_evidence |
| --- | --- | --- | --- | --- | --- | --- | --- |
| H015 full-suite validation | 9 | 1 archived full run | total 809.774909 s | total 1599.973670 s | 6/9 clean, 89 markers | 9 generated GDS with SHA256 in matrix | results/reference_run/reference_run.csv |
| H015 vs H013 selected A/B | mrr_weight_bank_16x16, mrr_weight_bank_8x8, multiportmmi_16x16 | 3 cases x 3 reps | -1.416757% delta | -1.906418% delta | quality change intentionally affects MRR cases | MMI16 exact in 3/3 sampled reps | results/research_evidence/h015_ab_timing_n3_summary_by_case.csv |
| H005+H007+H008 vs initial C++ seed | clements_16x16, mrr_weight_bank_16x16, multiportmmi_16x16 | 3 per case | -9.057515% delta | -1.612740% delta | all_quality_same=true | all_gds_exact=true | docs/PERFORMANCE_AND_QUALITY_EVIDENCE.md |
| H010 vs H008 | clements_16x16, multiportmmi_8x8 | 3 per case | -9.949529% delta | -9.582883% delta | all_quality_same=true | all_gds_exact=true | docs/PERFORMANCE_AND_QUALITY_EVIDENCE.md |
