# Paper Blueprint

This is a paper-ready outline for presenting LAE-LiDAR as a research artifact.
It is intentionally grounded in shipped repository evidence rather than
unverified narrative claims.

## Candidate Title

LAE-LiDAR: Layout-Evidence-Guided Agentic Migration and Optimization of a
Photonic LiDAR Router from Python to C++

## Abstract Draft

Photonic integrated-circuit routing requires layout-level correctness: a route
that is DRC-clean but geometrically far from the intended GDS may still be
unacceptable. We present LAE-LiDAR, a layout-evidence-guided agentic engineering
method for migrating a Python photonic LiDAR router into a faster C++ routing
core while preserving GDS-level behavior. The method combines semantic tracing,
crossing-aware A* alignment, deterministic C++ data structures, locked
gdsfactory/kfactory rendering, tiered DRC/GDS-XOR gates, repeated paired timing,
and a hypothesis memory that records accepted and rejected changes. On the
packaged nine-case benchmark suite, the current H015 router generates all GDS
outputs, leaves six cases DRC-clean, reduces MRR markers from 119 in the H010
validation baseline to 89, preserves the three standard-case metrics, and
records full quality/runtime evidence for every generated GDS. The accepted
non-semantic A* speed stack preserves full-suite GDS exactly and has repeated
paired timing support. All claims are shipped with concrete GDS files, SHA256
hashes, DRC summaries, runtime tables, XOR comparisons, and a machine-readable
claim ledger.

## Research Questions

RQ1: Can a Python photonic LiDAR router be migrated to a C++ native route core
without losing GDS-level layout correctness?

RQ2: Can non-semantic A* optimizations improve runtime while preserving exact
GDS across the benchmark suite?

RQ3: Can an agentic, hypothesis-driven loop improve difficult MRR routing
quality without leaking standard GDS answers into generation?

RQ4: Can every public quality and speed claim be made auditable through concrete
GDS files and machine-readable evidence?

## Contributions

1. A C++ implementation of the Python LiDAR routing semantics, including port
   access, bitmap DRC, crossing-aware A*, rip-up/reroute, post-processing,
   PIC-DB writeback, DB-level DRC, and GDS rendering.
2. A validated non-semantic A* speed stack: H005 allocation reserve, H007
   structured node keys, H008 unordered heap-entry lookup, and H010 cached step
   costs.
3. General geometry-quality fixes for MRR fanout and crossing post-processing:
   H011 crossing separation, H013 first-access detours, and H015 latest-safe
   first-access turnpoints.
4. A reproducible LAE-LiDAR agent protocol with explicit accept/reject gates,
   negative-result retention, and hardcoding exclusion.
5. A public artifact whose claims are backed by generated GDS files, SHA256
   hashes, DRC metrics, runtime metrics, GDS XOR, and A/B timing summaries.

## Experimental Setup

Benchmark suite:

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

Primary generated layouts:

```text
results/reference_run/*.gds
```

Primary evidence tables:

```text
results/reference_run/reference_run.csv
results/research_evidence/h015_effect_evidence_matrix.csv
results/research_evidence/research_claims_ledger.csv
results/research_evidence/artifact_scorecard.csv
results/research_evidence/paper_assets/
```

Validation command:

```powershell
python tools\validate_research_artifact.py --root .
```

Regenerate all paper tables, figure-data CSV files, and SVG figures:

```powershell
python tools\generate_paper_assets.py --root .
```

## Table 1: H015 Quality and Runtime

Use:

```text
results/research_evidence/h015_effect_evidence_matrix.csv
```

Columns to report:

```text
case
generated_gds
clean
markers
route_geometry_markers
crossings
route_core_s
full_flow_s
generated_sha256
```

Headline:

```text
9 / 9 cases generated
6 / 9 cases DRC-clean
total markers: 89
route-geometry markers: 88
route-core total: 809.774909 s
full-flow total: 1599.973670 s
```

## Table 2: Standard-GDS Agreement

Use:

```text
results/research_evidence/h015_standard_gds_pair_summary.csv
results/research_evidence/h015_standard_gds_layer_xor.csv
```

Rows:

| case | generated GDS | standard XOR um2 | overlap |
|---|---|---:|---:|
| clements_8x8 | `results/reference_run/clements_8x8_cpp.gds` | 0.000000 | 1.000000000 |
| multiportmmi_8x8 | `results/reference_run/multiportmmi_8x8_cpp.gds` | 5.091752 | 0.999978471 |
| multiportmmi_16x16 | `results/reference_run/multiportmmi_16x16_cpp.gds` | 18.680864 | 0.999969043 |

Interpretation: Clements is exact against the standard geometry. The two MMI
cases are DRC-clean and near-exact with small crossing-area residuals.

## Table 3: MRR Quality Progression

Use:

```text
results/research_evidence/h010_public_validation_summary.json
results/research_evidence/h013_public_validation_summary.json
results/research_evidence/h015_public_validation_summary.json
results/research_evidence/h015_vs_h013_reference_gds_pair_summary.csv
```

Rows:

| case | H010 markers | H013 markers | H015 markers | H015 GDS |
|---|---:|---:|---:|---|
| mrr_weight_bank_8x8 | 8 | 6 | 2 | `results/reference_run/mrr_weight_bank_8x8_cpp.gds` |
| mrr_weight_bank_16x16 | 110 | 92 | 86 | `results/reference_run/mrr_weight_bank_16x16_cpp.gds` |

Interpretation: H011/H013/H015 reduce MRR route-geometry failures by general
post-processing and access-detour rules, not by replaying standard GDS geometry.

## Table 4: Runtime Evidence

Use:

```text
results/reference_run/reference_run.csv
results/research_evidence/h015_ab_timing_n3_summary_by_case.csv
docs/PERFORMANCE_AND_QUALITY_EVIDENCE.md
```

Report separately:

```text
H015 full-suite route-core and full-flow totals
H015-vs-H013 selected n=3 A/B timing
accepted speed-stack paired timing
```

Key numbers:

```text
H015 selected n=3 A/B:
  route-core delta: -1.416757%
  full-flow delta: -1.906418%

H005+H007+H008 vs initial C++ seed:
  route-core delta: -9.057515%
  full-flow delta: -1.612740%

H010 vs H008:
  route-core delta: -9.949529%
  full-flow delta: -9.582883%
```

Interpretation: H015 is accepted as a quality improvement with no selected
runtime penalty. The speed claim belongs to the non-semantic A* speed stack.

## Ablation and Negative Results

Use:

```text
docs/PERFORMANCE_AND_QUALITY_EVIDENCE.md
docs/ALGORITHM_CHANGES_AND_INNOVATIONS.md
docs/EXPERIENCE_AND_TROUBLESHOOTING.md
```

Important negative results:

```text
H006: crossing connector simplification failed MMI DRC/standard-GDS gates.
H009: current-node snapshot preserved GDS but slowed paired timing.
H014: fixed upward first-access detour regressed MRR8 markers.
```

These negative results support the artifact's central claim: changes are
accepted by evidence, not by plausibility.

## Figures To Generate

Recommended paper figures:

```text
Figure 1: MRR8/MRR16 marker progression H010 -> H013 -> H015.
Figure 2: Route-core vs full-flow timing breakdown.
Figure 3: Standard-GDS XOR summary for the three standard cases.
Figure 4: LAE-LiDAR agent loop and evidence gates.
Optional Figure 5: C++ router architecture from PIC-DB view to GDS render.
```

The repository ships plotting-tool-agnostic figure-data CSV files and generated
SVG figures under:

```text
results/research_evidence/paper_assets/
```

## Threats To Validity

1. The standard GDS files are not shipped, so external reviewers need their own
   copies to rerun standard-GDS comparisons.
2. H015 still leaves route-geometry markers in MRR8 and MRR16.
3. MultiportMMI standard-GDS agreement is near-exact, not mathematically exact.
4. Full-flow timing includes Python conversion/rendering and filesystem IO.
5. Repeated timing is limited to selected cases, not the full nine-case suite.

## Artifact Evaluation Checklist

Run:

```powershell
python tools\validate_research_artifact.py --root .
```

Expected core output:

```text
research_artifact_validation=pass
matrix_rows=9
matrix_gds_sha256_checked=9
h015_clean_cases=6
h015_total_markers=89
h015_route_geometry_markers=88
claims_checked=7
```

Then inspect:

```text
docs/SCIENTIFIC_RESULT.md
docs/LAE_LIDAR_AGENT_PROTOCOL.md
results/research_evidence/research_claims_ledger.csv
results/research_evidence/h015_effect_evidence_matrix.csv
results/research_evidence/paper_assets/
results/reference_run/*.gds
```
