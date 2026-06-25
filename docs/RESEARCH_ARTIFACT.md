# Research Artifact: LAE-LiDAR

LAE-LiDAR is a layout-grounded agentic engineering workflow for evolving a
C++ photonic LiDAR router while preserving GDS-level correctness. The artifact
contains the router source, benchmark inputs, shipped GDS outputs, reproducible
quality metrics, runtime metrics, and a protocol for accepting or rejecting
algorithmic changes.

This is not a hardcoded GDS replay system. Standard/manual GDS files are used
only as validators. They are not shipped as router inputs and are not read by
the router during generation.

## Current Public Validation

The latest public validation run was produced from package commit:

```text
28e3a70760c62afb5e8d904185180b19639c4cbd
```

Primary machine-readable evidence:

```text
results/research_evidence/h010_public_validation_summary.json
results/research_evidence/h010_public_validation_evidence_ledger.csv
results/research_evidence/h010_public_validation_evidence_ledger.json
results/research_evidence/h010_public_validation_run_summary.csv
results/research_evidence/h010_reference_vs_public_run_gds_pair_summary.csv
results/research_evidence/h010_standard_vs_public_run_gds_pair_summary.csv
```

The concrete shipped GDS files used as package references are:

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

The reproduced run writes the same GDS names to:

```text
<PICDB_ROOT>/build_native_release/checks/lidar_c_public_h010_full/
```

The evidence ledger records both the shipped GDS hash and the reproduced-run
GDS hash for every case.

## Quality Results

Full public run:

| metric | value |
|---|---:|
| benchmark cases | 9 |
| completed cases | 9 |
| DRC-clean cases | 6 |
| total DRC markers | 119 |
| route-geometry markers | 117 |
| GDS exact matches vs package reference | 9 / 9 |
| total GDS XOR vs package reference | 0.0 um^2 |

Per-case quality and speed:

| case | clean | markers | route-core s | full-flow s | GDS exact vs reference |
|---|---:|---:|---:|---:|---:|
| toy_example_gp | 0 | 1 | 0.099301 | 13.670229 | yes |
| mrr_weight_bank_4x4 | 1 | 0 | 1.002947 | 15.445478 | yes |
| mrr_weight_bank_8x8 | 0 | 8 | 1.853486 | 25.248483 | yes |
| mrr_weight_bank_16x16 | 0 | 110 | 25.663113 | 83.480800 | yes |
| clements_8x8 | 1 | 0 | 0.928382 | 26.357202 | yes |
| clements_16x16 | 1 | 0 | 9.878940 | 60.627538 | yes |
| multiportmmi_8x8 | 1 | 0 | 17.782196 | 44.767949 | yes |
| multiportmmi_16x16 | 1 | 0 | 67.921257 | 132.095731 | yes |
| multiportmmi_32x32 | 1 | 0 | 398.729173 | 591.600722 | yes |

The non-clean cases are not hidden:

```text
toy_example_gp:
  known component-geometry marker in the input-sized smoke case

mrr_weight_bank_8x8:
  8 route-geometry markers

mrr_weight_bank_16x16:
  1 component-geometry marker
  109 route-geometry markers
```

## Standard-GDS Agreement

The external standard GDS files are optional validation inputs. They are referred
to by placeholder path:

```text
<STANDARD_GDS_DIR>/
```

Current public validation against the three standard cases:

| case | generated GDS | standard XOR um^2 | overlap | interpretation |
|---|---|---:|---:|---|
| clements_8x8 | `results/reference_run/clements_8x8_cpp.gds` | 0.000000 | 1.000000000 | exact geometry |
| multiportmmi_8x8 | `results/reference_run/multiportmmi_8x8_cpp.gds` | 5.091752 | 0.999978471 | tiny crossing-area residual |
| multiportmmi_16x16 | `results/reference_run/multiportmmi_16x16_cpp.gds` | 18.680864 | 0.999969043 | tiny crossing-area residual |

The byte-level file hash differs from the standard files because cell metadata
and file serialization differ, but geometry XOR is zero for `clements_8x8` and
near-zero for the two MultiportMMI standards.

## Runtime Results

The current public validation run reports:

| metric | value |
|---|---:|
| total route-core time | 523.858795 s |
| total full-flow time | 993.294132 s |
| average route-core time | 58.206533 s |
| average full-flow time | 110.366015 s |

The strongest repeated speed claims are the paired A/B trials from the research
workflow:

```text
H005+H007+H008 vs initial C++ seed:
  cases: clements_16x16, mrr_weight_bank_16x16, multiportmmi_16x16
  repetitions: 3 per case
  all_quality_same: true
  all_gds_exact: true
  average route-core delta: -9.057515%
  average full-flow delta: -1.612740%

H010 vs H008:
  cases: clements_16x16, multiportmmi_8x8
  repetitions: 3 per case
  all_quality_same: true
  all_gds_exact: true
  average route-core delta: -9.949529%
  average full-flow delta: -9.582883%
```

The H010 timing intervals were wide, so the defensible statement is a
conservative incremental hot-loop improvement, not a new cumulative
seed-to-H010 percentage.

## Accepted Algorithmic Changes

The current source contains four accepted non-semantic A* optimizations:

```text
H005: reserve A* node/index/neighbor storage from a conservative route bound
H007: replace per-lookup string node keys with structured integer grid keys
H008: replace HeapDict ordered entry lookup with unordered membership lookup
H010: cache fixed A* step costs and reuse step-type predicates in the hot loop
```

These changes are intentionally limited:

```text
unchanged cost formulas
unchanged neighbor order
unchanged crossing legality
unchanged DRC checks
unchanged heap priority comparison
unchanged route post-processing
unchanged GDS rendering
```

Direct full-suite GDS preservation:

```text
initial C++ seed -> H005+H007+H008+H010
cases: 9
exact_file_match: 9 / 9
layer-XOR nonzero rows: 0
xor_total_area_um2: 0.0 for every case
```

## Agentic Method

The research contribution is a repeatable agentic optimization loop:

```text
1. freeze benchmark and standard-GDS validators
2. propose one falsifiable router hypothesis
3. edit only the intended router source boundary
4. build and run tiered benchmark gates
5. collect route metrics, DRC markers, timing, GDS hashes, and layer XOR
6. accept only if hard quality gates pass and speed evidence is positive
7. record rejected hypotheses with concrete failure evidence
8. update the hypothesis memory before the next iteration
```

This protocol produced both positive and negative evidence. For example, H009
preserved GDS exactly but slowed paired timing, so it was rejected. H006 changed
crossing geometry and failed DRC/standard-GDS gates, so it was rejected even
though it appeared attractive as a geometric simplification.

## Reproduction

After merging the package into a full PIC-DB checkout and building
`pr_lidar_native`, run:

```powershell
.\tools\run_all_cases.ps1 `
  -PicdbRoot "<PICDB_ROOT>" `
  -PythonExe "<GDS_RENDER_PYTHON>" `
  -DriverPython "<GDS_RENDER_PYTHON>" `
  -BenchmarkRoot "<LIDAR_C_ROOT>\code\benchmarks\picroute" `
  -OutputDir build_native_release\checks\lidar_c_public_h010_full `
  -Prefix lidar_c_public_h010_full
```

Then compare the reproduced GDS files against the package references:

```text
results/research_evidence/h010_reference_vs_public_run_gds_pair_summary.csv
```

Expected result:

```text
exact_file_match: 9 / 9
total XOR: 0.0 um^2
```

## Limitations

This artifact is strong on evidence discipline and GDS-preserving runtime
optimization. It is not yet a complete routing-policy breakthrough for every
family. The remaining technical targets are:

```text
MRR 8x8 and 16x16 route-geometry marker reduction
MultiportMMI crossing residual reduction without standard-GDS leakage
more repeated full-suite timing trials
render-stage acceleration beyond the native route core
```
