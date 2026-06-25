# GPT-5.5 Agent Specification: LAE-LiDAR

This document specifies a GPT-5.5-class coding agent for improving and
evaluating the C++ LiDAR router. It is project-specific and does not follow or
copy an external skill/plugin manifest. The purpose is to make the agentic
research method reproducible by a model, a human engineer, or an artifact
reviewer.

## Mission

Evolve the C++ LiDAR router while preserving GDS-level layout correctness,
improving quality and runtime only when concrete evidence supports the change.

The agent must produce:

```text
router source changes when justified
generated GDS outputs
quality metrics
runtime metrics
GDS hash and XOR comparisons
claim-to-evidence ledgers
accepted/rejected hypothesis records
paper-ready tables and figures
```

## Non-Negotiable Constraints

The agent must not:

```text
read standard GDS geometry as router generation input
copy standard GDS polygons into generated output
branch on benchmark case name to emit a fixed route
branch on net id to force a known answer
patch XOR hotspots by hand
claim speedup without timing evidence
claim GDS correctness from visual similarity alone
hide remaining DRC markers or near-exact XOR residuals
```

## Required Repository Interfaces

Primary package:

```text
lidar_c/
```

Core router source:

```text
code/src/algorithm/routing/lidar/
```

Generated reference GDS:

```text
results/reference_run/*.gds
```

Primary evidence:

```text
results/reference_run/reference_run.csv
results/research_evidence/h015_effect_evidence_matrix.csv
results/research_evidence/research_claims_ledger.csv
results/research_evidence/artifact_scorecard.csv
results/research_evidence/paper_assets/
```

Validation:

```powershell
python tools\validate_research_artifact.py --root .
```

Paper asset regeneration:

```powershell
python tools\generate_paper_assets.py --root .
```

## Agent Memory Model

The agent should maintain the following memory records:

```text
accepted hypotheses:
  H005, H007, H008, H010 speed stack
  H011, H013, H015 quality stack

rejected hypotheses:
  H006 crossing connector simplification
  H009 current-node snapshot
  H014 fixed upward first-access detour

open targets:
  MRR8 remaining 2 route-geometry markers
  MRR16 remaining 86 route-geometry markers
  MultiportMMI near-exact but nonzero standard XOR
  render-stage and conversion-stage full-flow cost
```

## Iteration Contract

For each iteration, the agent must write or update an evidence record with:

```text
iteration_id
hypothesis_id
technique_family
source_diff_scope
benchmark_scope
generated_gds_dir
quality_metrics
runtime_metrics
gds_comparison_files
decision
reason
next_hypothesis
```

The decision must be one of:

```text
accepted_quality
accepted_speed
accepted_quality_and_speed
rejected_quality_regression
rejected_runtime_regression
rejected_insufficient_evidence
parked_needs_more_data
```

## Execution Loop

1. Load current evidence:

```powershell
python tools\validate_research_artifact.py --root .
```

2. Select one hypothesis. The hypothesis must predict a measurable movement:

```text
fewer route-geometry markers
more clean cases
lower route-core time
lower full-flow time
smaller GDS XOR
exact-GDS preservation for non-semantic speed patches
```

3. Edit only the necessary source boundary.

4. Run tiered validation:

```text
tier 0: fast smoke and sensitive cases
tier 1: focused medium/large cases
tier 2: full nine-case regression
```

5. Bind the result to concrete files:

```text
generated GDS paths
SHA256 hashes
DRC summaries
runtime CSV/JSON
GDS pair summaries
layer-XOR summaries
A/B timing summaries when needed
```

6. Update:

```text
results/research_evidence/h015_effect_evidence_matrix.csv or successor
results/research_evidence/research_claims_ledger.csv
results/research_evidence/artifact_scorecard.csv
docs/SCIENTIFIC_RESULT.md
docs/PAPER_BLUEPRINT.md
docs/LAE_LIDAR_AGENT_PROTOCOL.md
```

7. Regenerate paper assets:

```powershell
python tools\generate_paper_assets.py --root .
```

8. Validate the package:

```powershell
python tools\validate_research_artifact.py --root .
```

## Acceptance Rules

Quality change acceptance:

```text
all benchmark cases in scope generate GDS
protected clean cases remain clean
marker count improves or targeted marker class improves
standard-GDS metrics do not regress
changed GDS files are localized to the intended family
remaining failures are documented
```

Speed change acceptance:

```text
GDS is exact for protected cases
DRC metrics are unchanged or improved
paired A/B timing is used
route-core and full-flow timing are reported separately
confidence limitations are stated
```

Research artifact acceptance:

```text
quality metrics are present
runtime metrics are present
all claims link to concrete GDS and evidence files
paper assets regenerate
validation script passes
portable-path scan passes
limitations remain visible
```

## Current Baseline Facts

Current public baseline:

```text
iteration: H015
cases: 9
ok_cases: 9
clean_cases: 6
total_markers: 89
route_geometry_markers: 88
total_route_core_s: 809.774909
total_full_flow_s: 1599.973670
```

Current GDS entry point:

```text
results/reference_run/*.gds
```

Current per-case evidence:

```text
results/research_evidence/h015_effect_evidence_matrix.csv
```

Current scorecard:

```text
results/research_evidence/artifact_scorecard.csv
```

## Output Style

The agent should report each completed iteration with:

```text
what changed
which files changed
which GDS files changed
quality result
runtime result
standard-GDS result
validation command and result
remaining risk
next hypothesis
```

Unsupported claims must be explicitly marked as unsupported, not silently
omitted.
