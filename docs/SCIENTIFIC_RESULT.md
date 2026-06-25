# Scientific Result: LAE-LiDAR

This document states the research result in claim-and-evidence form. The goal is
to make each quality or runtime statement auditable from concrete repository
files, generated GDS layouts, and comparison tables.

## Result Summary

LAE-LiDAR is a layout-grounded agentic engineering method for migrating and
improving a photonic LiDAR router from Python semantics to a C++ implementation.
The method couples a C++ routing core with locked GDS rendering, tiered
benchmark gates, standard-GDS validation, exact-GDS preservation tests, repeated
paired timing trials, and an explicit accept/reject memory for hypotheses.

The current packaged router is the H015 reference:

```text
source iteration: H015 latest-safe first-access turn on top of H011/H013
benchmark cases: 9
completed cases: 9
DRC-clean cases: 6
total DRC markers: 89
route-geometry markers: 88
total route-core time: 809.774909 s
total full-flow time: 1599.973670 s
```

Primary evidence:

```text
results/research_evidence/h015_public_validation_summary.json
results/research_evidence/h015_effect_evidence_matrix.csv
results/research_evidence/research_claims_ledger.csv
results/reference_run/reference_run.csv
results/reference_run/*.gds
```

Repository-internal verification command:

```powershell
python tools\validate_research_artifact.py --root .
```

Paper-ready generated tables, figure data, and SVG figures:

```text
results/research_evidence/paper_assets/
```

## Core Contributions

1. A semantics-preserving C++ implementation of the Python LiDAR routing model,
   including bitmap construction, port access, crossing-aware A*, rip-up and
   reroute, post-processing, PIC-DB writeback, DB-level DRC, and GDS rendering.
2. A non-semantic A* speed stack accepted only after exact-GDS preservation:
   allocation reservation, structured grid-node keys, unordered heap-entry
   lookup, and cached fixed step costs.
3. General MRR geometry-quality fixes that do not read standard GDS files and do
   not branch on case name, net name, or standard coordinates:
   crossing-cell separation, first-access fanout detours, and latest-safe
   first-access turnpoints.
4. A reproducible evidence ladder that binds every claim to benchmark YAML,
   generated GDS files, SHA256 hashes, DRC summaries, route metrics, runtime
   metrics, GDS XOR, and A/B timing outputs.
5. An agentic optimization protocol that records positive and negative results,
   so rejected changes remain part of the scientific evidence.

## Claim Ledger

The machine-readable claim ledger is:

```text
results/research_evidence/research_claims_ledger.csv
results/research_evidence/research_claims_ledger.json
```

It currently records these claim classes:

| claim id | type | core statement | primary evidence |
|---|---|---|---|
| C-H015-QUALITY-001 | quality | H015 completes 9 / 9 cases and leaves 6 / 9 DRC-clean. | `h015_public_validation_summary.json`, `reference_run.csv` |
| C-H015-QUALITY-002 | quality | H015 reduces markers by 10 vs H013 and by 30 vs H010. | `h015_public_validation_summary.json`, H010/H013 summaries |
| C-H015-QUALITY-003 | quality | Standard-case metrics remain stable: Clements exact, MMI near-exact. | `h015_standard_gds_pair_summary.csv` |
| C-H015-GDS-001 | GDS | H015 changes only the two larger MRR GDS files vs H013. | `h015_vs_h013_reference_gds_pair_summary.csv` |
| C-H015-RUNTIME-001 | runtime | H015 records per-case route-core and full-flow runtime for each GDS. | `reference_run.csv`, `h015_effect_evidence_matrix.csv` |
| C-H015-RUNTIME-002 | runtime | H015 n=3 selected timing shows no runtime penalty vs H013. | `h015_ab_timing_n3_summary_by_case.csv` |
| C-SPEED-STACK-001 | runtime | The accepted A* speed stack preserves full-suite GDS exactly and has paired timing support. | `PERFORMANCE_AND_QUALITY_EVIDENCE.md`, H010 evidence |

## GDS-Grounded Evaluation Matrix

The central per-case matrix is:

```text
results/research_evidence/h015_effect_evidence_matrix.csv
results/research_evidence/h015_effect_evidence_matrix.json
```

Each row contains:

```text
case
benchmark_yml
generated_gds
generated_sha256
generated_bytes
DRC clean flag and marker breakdown
crossing count and route length
route-core and full-flow runtime
exact match / XOR / overlap against H013 package reference
standard-GDS XOR and overlap where a standard file exists
selected H015-vs-H013 A/B timing where that case was sampled
primary evidence files
```

This matrix is the preferred entry point for reviewers because it connects the
headline claims to concrete layouts such as:

```text
results/reference_run/mrr_weight_bank_8x8_cpp.gds
results/reference_run/mrr_weight_bank_16x16_cpp.gds
results/reference_run/clements_8x8_cpp.gds
results/reference_run/multiportmmi_8x8_cpp.gds
results/reference_run/multiportmmi_16x16_cpp.gds
```

## Quality Evaluation

The current H015 full-suite result is:

| family | case | DRC clean | markers | generated GDS |
|---|---|---:|---:|---|
| smoke | toy_example_gp | 0 | 1 | `results/reference_run/toy_example_gp_cpp.gds` |
| MRR | mrr_weight_bank_4x4 | 1 | 0 | `results/reference_run/mrr_weight_bank_4x4_cpp.gds` |
| MRR | mrr_weight_bank_8x8 | 0 | 2 | `results/reference_run/mrr_weight_bank_8x8_cpp.gds` |
| MRR | mrr_weight_bank_16x16 | 0 | 86 | `results/reference_run/mrr_weight_bank_16x16_cpp.gds` |
| Clements | clements_8x8 | 1 | 0 | `results/reference_run/clements_8x8_cpp.gds` |
| Clements | clements_16x16 | 1 | 0 | `results/reference_run/clements_16x16_cpp.gds` |
| MMI | multiportmmi_8x8 | 1 | 0 | `results/reference_run/multiportmmi_8x8_cpp.gds` |
| MMI | multiportmmi_16x16 | 1 | 0 | `results/reference_run/multiportmmi_16x16_cpp.gds` |
| MMI | multiportmmi_32x32 | 1 | 0 | `results/reference_run/multiportmmi_32x32_cpp.gds` |

MRR quality improved through the accepted geometry sequence:

```text
mrr_weight_bank_8x8 markers: 8 -> 6 -> 2
mrr_weight_bank_16x16 markers: 110 -> 92 -> 86
sequence: H010 -> H013 -> H015
```

Evidence:

```text
results/research_evidence/h010_public_validation_summary.json
results/research_evidence/h013_public_validation_summary.json
results/research_evidence/h015_public_validation_summary.json
results/research_evidence/h015_vs_h013_reference_gds_pair_summary.csv
```

## Standard-GDS Agreement

External standard GDS files are validators only. They are not shipped and are
not read by the router. With those standards available, H015 reports:

| case | generated GDS | standard XOR um2 | overlap ratio |
|---|---|---:|---:|
| clements_8x8 | `results/reference_run/clements_8x8_cpp.gds` | 0.000000 | 1.000000000 |
| multiportmmi_8x8 | `results/reference_run/multiportmmi_8x8_cpp.gds` | 5.091752 | 0.999978471 |
| multiportmmi_16x16 | `results/reference_run/multiportmmi_16x16_cpp.gds` | 18.680864 | 0.999969043 |

Evidence:

```text
results/research_evidence/h015_standard_gds_pair_summary.csv
results/research_evidence/h015_standard_gds_layer_xor.csv
results/reference_gds_compare/gds_pair_summary.csv
```

## Runtime Evaluation

The current H015 package records two runtime levels:

| level | meaning | evidence |
|---|---|---|
| route-core | native C++ routing time | `timing_cpp_route_core_s` in `reference_run.csv` |
| full-flow | conversion, native routing, DB DRC, GDS rendering, and IO | `timing_lidar_full_flow_s` in `reference_run.csv` |

H015 full-suite totals:

```text
route-core total: 809.774909 s
full-flow total: 1599.973670 s
```

H015-vs-H013 selected A/B timing:

```text
cases: mrr_weight_bank_8x8, mrr_weight_bank_16x16, multiportmmi_16x16
repetitions: 3
average route-core delta: -1.416757%
average full-flow delta: -1.906418%
interpretation: H015 is a quality fix; selected timing does not show a runtime penalty
```

Accepted speed-stack evidence remains separate from H015:

```text
H005+H007+H008 vs initial C++ seed:
  average route-core delta: -9.057515%
  average full-flow delta: -1.612740%
  all repeated GDS exact: true

H010 vs H008:
  average route-core delta: -9.949529%
  average full-flow delta: -9.582883%
  all repeated GDS exact: true
```

Evidence:

```text
results/research_evidence/h015_ab_timing_n3_summary.json
results/research_evidence/h015_ab_timing_n3_summary_by_case.csv
docs/PERFORMANCE_AND_QUALITY_EVIDENCE.md
```

## Hardcoding Exclusion

The artifact explicitly separates generation from validation:

```text
generation inputs: benchmark YAML, route config, C++ router, GDS-render environment
validation inputs: optional external standard GDS files
```

Disallowed mechanisms:

```text
copying standard GDS polygons
branching on benchmark case name to emit fixed routes
branching on net id to force a known answer
patching XOR hotspots by hand
using standard GDS geometry as a routing input
```

The evidence supporting this claim is structural: standard GDS files are not
included in the repository, are referenced only by comparison scripts, and the
generated files carry their own SHA256 hashes in the evidence ledger.

## Limitations

The artifact is not claimed to be a fully solved photonic router. The remaining
research targets are concrete:

```text
MRR 8x8 still has 2 route-geometry markers.
MRR 16x16 still has 86 route-geometry markers.
MultiportMMI standard XOR is near-zero but not exactly zero.
Full-flow runtime is still dominated partly by Python conversion/rendering and IO.
More repeated full-suite timing trials are needed for broader speed claims.
```

These limitations are intentionally preserved in the public evidence rather
than hidden behind viewer-level similarity.
