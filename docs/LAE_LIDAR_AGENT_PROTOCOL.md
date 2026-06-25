# LAE-LiDAR Agent Protocol

This is the project-specific agent protocol used to evolve the C++ LiDAR router.
It is not a copied or repackaged external skill format. It is a reproducible
engineering method that can be executed by a GPT-5.5-class coding agent or by a
human engineer following the same gates.

## Objective

Improve a photonic LiDAR router while preserving layout correctness at GDS
level. Every accepted change must be tied to measurable quality or runtime
evidence and to concrete generated GDS files.

## Inputs

Required:

```text
full PIC-DB checkout
lidar_c package
benchmark YAML inputs under code/benchmarks/picroute/
locked GDS-render Python environment
native pr_lidar_native build
```

Optional validators:

```text
external standard/manual GDS files
original Python LiDAR trace environment
previous package-reference GDS files
```

## Outputs

Each accepted iteration should produce:

```text
router source diff
generated GDS files
per-case route/DRC/runtime CSV and JSON
GDS pair comparison CSV
layer-XOR CSV
timing A/B summary when speed is claimed or runtime risk exists
claim/evidence ledger update
accepted/rejected hypothesis note
```

Current public evidence files:

```text
results/research_evidence/h015_effect_evidence_matrix.csv
results/research_evidence/research_claims_ledger.csv
results/reference_run/reference_run.csv
results/reference_run/*.gds
```

## Agent State

Maintain four state blocks:

```text
baseline:
  current accepted router source
  current package-reference GDS files
  current quality/runtime summary

hypotheses:
  proposed changes with expected benefit and risk
  accepted changes with evidence
  rejected changes with failure reason

validators:
  benchmark list
  standard-GDS comparison set
  exact-GDS comparison set
  DRC and runtime gates

artifact:
  docs, evidence matrices, claim ledger, and reproducibility notes
```

## Iteration Loop

Use one falsifiable hypothesis per iteration.

```text
1. Select one hypothesis and define the expected metric movement.
2. Identify the smallest source boundary that can implement it.
3. Edit router code without reading standard GDS geometry as generation input.
4. Build pr_lidar_native.
5. Run a tier-0 smoke gate on selected sensitive cases.
6. If tier 0 passes, run a broader tier-1 or full tier-2 regression.
7. Compare generated GDS against package references.
8. Compare standard cases against external standard GDS if available.
9. Run paired A/B timing if runtime is part of the claim or the change touches hot paths.
10. Accept, reject, or refine the hypothesis.
11. Update evidence matrices, claim ledger, and method notes.
```

## Acceptance Gates

Quality gates:

```text
all selected cases generate GDS
no protected clean case becomes dirty
DRC marker movement matches the hypothesis
changed GDS files are explained by the intended algorithmic change
standard-GDS metrics do not regress on protected standard cases
```

Runtime gates:

```text
route-core and full-flow time are recorded for every generated GDS
paired A/B timing is used for speed claims
full-flow timing is interpreted separately from native route-core timing
quality fixes are not marketed as speedups unless timing evidence supports it
```

Reproducibility gates:

```text
all result paths are portable repository-relative paths or placeholders
JSON files parse
GDS files named in evidence exist
SHA256 hashes match generated GDS files
claim ledger points to concrete evidence files
```

Hardcoding exclusion gates:

```text
no standard GDS file is used by router generation
no case-name branch emits fixed routes
no net-id branch forces known answers
no hand-patched polygons are added to match XOR hotspots
```

## Tiered Benchmarks

Tier 0: fast smoke or sensitive selected cases.

```text
toy_example_gp
mrr_weight_bank_8x8
clements_8x8
multiportmmi_8x8
```

Tier 1: technique-focused subset.

```text
clements_16x16
mrr_weight_bank_16x16
multiportmmi_16x16
```

Tier 2: full default suite.

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

The exact subset can be adjusted, but each report must state the scope.

## Scoring Model

Use hard gates first, then score.

```text
hard failure:
  build failure
  missing GDS
  protected clean-case DRC regression
  standard-GDS regression on protected standard cases
  unexplained nonlocal GDS change

positive quality score:
  fewer total markers
  fewer route-geometry markers
  more clean cases
  stable protected standard-GDS metrics

positive runtime score:
  lower route-core time under paired A/B
  lower full-flow time when route-core and render effects are understood
  exact-GDS preservation for non-semantic speed patches
```

## Evidence Schema

Every publishable result should include:

```text
case
benchmark_yml
generated_gds
generated_sha256
generated_bytes
status
clean
markers
route_geometry_markers
crossings
route_length_um
route_core_s
full_flow_s
reference comparison exact flag
reference XOR
standard-GDS XOR if available
A/B timing if sampled
primary evidence files
```

The current implementation of this schema is:

```text
results/research_evidence/h015_effect_evidence_matrix.csv
results/research_evidence/h015_effect_evidence_matrix.json
```

## Agent Operating Rules

1. Prefer source-level semantic alignment before performance tuning.
2. Treat GDS viewer similarity as weak evidence; use DRC and XOR.
3. Separate route-core timing from full-flow timing.
4. Accept negative results when they are informative.
5. Keep rejected hypotheses visible to prevent repeated mistakes.
6. Do not hide limitations; they define the next hypothesis.
7. Make every public claim traceable to a file in `results/` or `docs/`.

## Current Accepted Changes

Speed stack:

```text
H005: A* allocation reserve
H007: structured A* node keys
H008: unordered HeapDict entry lookup
H010: cached A* step costs
```

Quality stack:

```text
H011: supplemental crossing separation
H013: first-access fanout detours
H015: latest-safe first-access turnpoint
```

Rejected examples:

```text
H006: crossing connector simplification, rejected for MMI DRC/standard-GDS regression
H009: current-node snapshot, rejected for slower paired timing
H014: fixed upward first-access detour, rejected for MRR marker regression
```

## Research-Grade Reporting Rule

No paragraph in a paper, report, or README should claim quality or speed without
one of these links:

```text
results/research_evidence/research_claims_ledger.csv
results/research_evidence/h015_effect_evidence_matrix.csv
results/reference_run/reference_run.csv
results/research_evidence/*_gds_pair_summary.csv
results/research_evidence/*_ab_timing*_summary*.csv
```

This rule is the main difference between the LAE-LiDAR protocol and ordinary
ad hoc router tuning.
