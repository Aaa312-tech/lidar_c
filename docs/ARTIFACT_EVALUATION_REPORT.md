# Artifact Evaluation Report

This report summarizes whether the current `lidar_c` package satisfies the
research artifact requirements: quality metrics, runtime metrics, concrete GDS
evidence, a reproducible agent/method protocol, and paper-ready deliverables.

The machine-readable scorecard is:

```text
results/research_evidence/artifact_scorecard.csv
results/research_evidence/artifact_scorecard.json
```

## Current Evaluation Result

```text
status: satisfied with documented limitations
validation command: python tools\validate_research_artifact.py --root .
current reference: H015
generated GDS files: results/reference_run/*.gds
```

## Requirement Summary

| requirement | status | primary evidence |
|---|---|---|
| Quality metrics are present | satisfied | `h015_public_validation_summary.json`, `h015_effect_evidence_matrix.csv` |
| Runtime metrics are present | satisfied | `reference_run.csv`, `h015_ab_timing_n3_summary_by_case.csv` |
| Results are tied to concrete GDS | satisfied | `results/reference_run/*.gds`, SHA256 fields in the matrix |
| Standard-GDS comparison is documented | satisfied | `h015_standard_gds_pair_summary.csv` |
| GPT-5.5-class agent protocol exists | satisfied | `docs/GPT55_AGENT_SPEC.md`, `docs/LAE_LIDAR_AGENT_PROTOCOL.md` |
| Methodology exists | satisfied | `docs/METHODOLOGY.md`, `docs/ALGORITHM_CHANGES_AND_INNOVATIONS.md` |
| Paper-ready assets exist | satisfied | `results/research_evidence/paper_assets/` |
| Validation is reproducible | satisfied | `tools/validate_research_artifact.py` |
| Limitations are disclosed | satisfied | `docs/SCIENTIFIC_RESULT.md`, `docs/PAPER_BLUEPRINT.md` |

## Key Metrics

```text
cases: 9
ok_cases: 9
clean_cases: 6
total_markers: 89
route_geometry_markers: 88
total_route_core_s: 809.774909
total_full_flow_s: 1599.973670
standard clements_8x8 XOR: 0.000000
standard multiportmmi_8x8 XOR: 5.091752
standard multiportmmi_16x16 XOR: 18.680864
H015 selected A/B route-core delta: -1.416757%
H015 selected A/B full-flow delta: -1.906418%
```

## Concrete GDS Evidence

Generated package-reference GDS files:

```text
results/reference_run/toy_example_gp_cpp.gds
results/reference_run/mrr_weight_bank_4x4_cpp.gds
results/reference_run/mrr_weight_bank_8x8_cpp.gds
results/reference_run/mrr_weight_bank_16x16_cpp.gds
results/reference_run/clements_8x8_cpp.gds
results/reference_run/clements_16x16_cpp.gds
results/reference_run/multiportmmi_8x8_cpp.gds
results/reference_run/multiportmmi_16x16_cpp.gds
results/reference_run/multiportmmi_32x32_cpp.gds
```

The scorecard and effect matrix record SHA256 hashes for these files, and the
validator checks the current file content against those hashes.

## Limitations

The artifact is not marked as a solved universal photonic router:

```text
MRR8 still has 2 route-geometry markers.
MRR16 still has 86 route-geometry markers.
MultiportMMI standard XOR is near-zero but not exactly zero.
Full-flow timing includes conversion, rendering, KLayout write, and IO.
External standard GDS files are not redistributed.
```

These limitations are part of the evaluation record and should remain visible in
any paper or release built from this package.
