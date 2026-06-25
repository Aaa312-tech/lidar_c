# File Manifest

This manifest lists the important files in `lidar_c`.

## Dependency locks

| File | Purpose |
|---|---|
| `.gitignore` | Keeps build outputs, virtual environments, caches, and local standard GDS files out of Git. |
| `requirements-gds-render.txt` | Python packages used by conversion, validation, and final GDS rendering. |
| `requirements-python-lidar-original.txt` | Optional packages for running the original Python LiDAR baseline wrapper. |

## Core C++ module

| File | Purpose |
|---|---|
| `code/src/algorithm/routing/lidar/CMakeLists.txt` | Builds the LiDAR routing library inside PIC-DB. |
| `code/src/algorithm/routing/lidar/include/lidar_astar.h` | A* router interface and route data structures. |
| `code/src/algorithm/routing/lidar/include/lidar_bitmap.h` | Bitmap occupancy model. |
| `code/src/algorithm/routing/lidar/include/lidar_drc.h` | Runtime DRC manager interface. |
| `code/src/algorithm/routing/lidar/include/lidar_router.h` | Top-level route API. |
| `code/src/algorithm/routing/lidar/include/picdb_lidar_view.h` | PIC-DB to LiDAR runtime view adapter. |
| `code/src/algorithm/routing/lidar/src/lidar_astar.cpp` | A*, crossing-aware routing, rip-up/reroute, post-process, writeback. |
| `code/src/algorithm/routing/lidar/src/lidar_bitmap.cpp` | Bitmap allocation and blockage initialization. |
| `code/src/algorithm/routing/lidar/src/lidar_drc.cpp` | DRC checks, port spreading, bitmap updates. |
| `code/src/algorithm/routing/lidar/src/lidar_python_set.cpp` | Deterministic Python-like set behavior. |
| `code/src/algorithm/routing/lidar/src/lidar_router.cpp` | Flow summaries and top-level routing orchestration. |
| `code/src/algorithm/routing/lidar/src/picdb_lidar_view.cpp` | Builds runtime view from PIC-DB design. |

## Native executable

| File | Purpose |
|---|---|
| `code/tools/pr_lidar_native/CMakeLists.txt` | Builds `pr_lidar_native.exe`. |
| `code/tools/pr_lidar_native/main.cpp` | CLI entry. Supports LiDAR YAML full-flow and legacy PIC-DB mode. |
| `code/tools/pr_lidar_native/README.md` | Original native tool notes. |

## Python bridge and validation scripts

| File | Purpose |
|---|---|
| `code/tools/pr_lidar_native/scripts/lidar_yml_to_picdb_yml.py` | Converts LiDAR benchmark YAML to PIC-DB intermediate LEF/DEF-style YAML. |
| `code/tools/pr_lidar_native/scripts/render_route_result_gds.py` | Renders C++ route result to GDS using gdsfactory/kfactory. |
| `code/tools/pr_lidar_native/scripts/run_lidar_benchmark_regression.py` | Runs multiple benchmark cases and collects timing/DRC/GDS metrics. |
| `code/tools/pr_lidar_native/scripts/run_python_lidar_original.py` | Runs original Python LiDAR and can dump route traces. |
| `code/tools/pr_lidar_native/scripts/compare_gds_geometry.py` | Compares standard/Python/C++ GDS using layer area and XOR. |
| `code/tools/pr_lidar_native/scripts/compare_lidar_net_metrics.py` | Compares route/net-level metrics. |
| `code/tools/pr_lidar_native/scripts/gdsfactory_adapters.py` | Registers missing/custom gdsfactory adapters used by benchmarks. |

## PICBench flow bridge

| File | Purpose |
|---|---|
| `code/tools/picbench_flow/run_picdb_dreamplace_lidar_flow.py` | DREAMPlace/PICBench to LiDAR flow bridge. |
| `code/tools/picbench_flow/gdsfactory_adapters.py` | Adapter helpers for PICBench gdsfactory cells. |
| `code/tools/picbench_flow/README.md` | Original flow documentation. |

## Configs

| Path | Purpose |
|---|---|
| `code/configs/pr_lidar/route_config/comp_LiDAR.yml` | LiDAR route config. |
| `code/configs/pr_lidar/place_config/*.yml` | Placement config entry points. |
| `code/configs/pr_lidar/place_config/*.json` | Placement JSON configs. |

## Benchmarks

| Path | Purpose |
|---|---|
| `code/benchmarks/picroute/toy_example/` | Small smoke benchmark. |
| `code/benchmarks/picroute/mrr_weight_bank_4x4/` | MRR 4x4 benchmark. |
| `code/benchmarks/picroute/mrr_weight_bank_8x8/` | MRR 8x8 benchmark. |
| `code/benchmarks/picroute/mrr_weight_bank_16x16/` | MRR 16x16 benchmark. |
| `code/benchmarks/picroute/clements_8x8/` | Clements 8x8 benchmark. |
| `code/benchmarks/picroute/clements_16x16/` | Clements 16x16 benchmark. |
| `code/benchmarks/picroute/multiportmmi_8x8/` | Multiport MMI 8x8 benchmark. |
| `code/benchmarks/picroute/multiportmmi_16x16/` | Multiport MMI 16x16 benchmark. |
| `code/benchmarks/picroute/multiportmmi_32x32/` | Multiport MMI 32x32 benchmark. |

These are input benchmarks, not standard routed GDS files.

## Results

| Path | Purpose |
|---|---|
| `results/reference_run/*.gds` | Archived C++ GDS outputs for 9 benchmark cases. |
| `results/reference_run/reference_run.csv` | Archived regression summary. |
| `results/reference_run/reference_run.json` | Archived regression summary in JSON. |
| `results/reference_gds_compare/gds_pair_summary.csv` | Standard/Python/C++ GDS pair comparisons. |
| `results/reference_gds_compare/gds_layer_xor.csv` | Layer-by-layer XOR. |
| `results/reference_gds_compare/gds_xor_hotspots.csv` | XOR hotspot report. |
| `results/research_evidence/README.md` | Explains the portable H015 evidence tables and retained H013/H010 evidence. |
| `results/research_evidence/h015_public_validation_summary.json` | Current top-level public validation metrics. |
| `results/research_evidence/h015_public_validation_evidence_ledger.csv` | Current per-case GDS, DRC, timing, hash, and XOR evidence ledger. |
| `results/research_evidence/h015_effect_evidence_matrix.csv` | Current per-case quality, runtime, GDS hash, H013 comparison, standard-GDS comparison, and A/B timing matrix. |
| `results/research_evidence/research_claims_ledger.csv` | Research claim ledger mapping publishable claims to concrete evidence files and GDS artifacts. |
| `results/research_evidence/h015_vs_h013_reference_gds_pair_summary.csv` | Previous H013 reference GDS vs current H015 GDS comparison. |
| `results/research_evidence/h015_standard_gds_pair_summary.csv` | External standard GDS vs current H015 GDS comparison. |
| `results/research_evidence/h015_ab_timing_n3_summary_by_case.csv` | Three-repetition H015 timing/quality A/B summary. |
| `results/research_evidence/h013_public_validation_summary.json` | Retained H013 top-level public validation metrics. |
| `results/research_evidence/h013_public_validation_evidence_ledger.csv` | Retained H013 per-case GDS, DRC, timing, hash, and XOR evidence ledger. |
| `results/research_evidence/h013_vs_h010_reference_gds_pair_summary.csv` | Previous H010 reference GDS vs H013 GDS comparison. |
| `results/research_evidence/h013_standard_gds_pair_summary.csv` | External standard GDS vs H013 GDS comparison. |
| `results/research_evidence/h013_min_ab_timing_summary_by_case.csv` | One-repetition H013 timing/quality A/B summary. |
| `results/research_evidence/h013_ab_timing_n3_summary_by_case.csv` | Three-repetition H013 timing/quality A/B summary. |
| `results/research_evidence/h010_public_validation_summary.json` | Top-level public validation metrics. |
| `results/research_evidence/h010_public_validation_evidence_ledger.csv` | Per-case GDS, DRC, timing, hash, and XOR evidence ledger. |
| `results/research_evidence/h010_reference_vs_public_run_gds_pair_summary.csv` | Shipped-reference GDS vs reproduced public-run GDS comparison. |
| `results/research_evidence/h010_standard_vs_public_run_gds_pair_summary.csv` | External standard GDS vs reproduced public-run GDS comparison. |
| `results/README.md` | Explains archived results and sanitized paths. |
| `standard_gds/README.md` | Placeholder note for external standard GDS files, which are not included. |

## Documentation

| File | Purpose |
|---|---|
| `README.md` | Main usage and current status. |
| `docs/CURRENT_RESULTS.md` | Current included GDS results and standard-GDS comparison. |
| `docs/METHODOLOGY.md` | Methodology for building/converting a high-quality router. |
| `docs/SCIENTIFIC_RESULT.md` | Paper-style research-result statement with claim-to-evidence mapping. |
| `docs/LAE_LIDAR_AGENT_PROTOCOL.md` | Project-specific agent protocol for hypothesis-driven router improvement. |
| `docs/ALGORITHM_CHANGES_AND_INNOVATIONS.md` | Algorithmic changes, engineering innovations, and what was not hardcoded. |
| `docs/EXPERIENCE_AND_TROUBLESHOOTING.md` | Lessons learned and debugging playbook. |
| `docs/ENVIRONMENT.md` | C++ and Python environment dependencies. |
| `docs/TRANSFER_GUIDE.md` | How to move this package into another PIC-DB tree. |
| `docs/RESEARCH_ARTIFACT.md` | Research-result summary with quality, speed, GDS evidence, and agentic method. |

## Helper tools

| File | Purpose |
|---|---|
| `tools/merge_into_picdb.ps1` | Copies packaged code into a PIC-DB source tree. |
| `tools/run_all_cases.ps1` | Runs the default 9-case regression in a PIC-DB tree. |
