# pr_lidar_native

`pr_lidar_native` is the PIC-DB based C++ LiDAR routing entry point.

The recommended full-flow command takes a LiDAR benchmark YAML and writes a
GDS file:

```powershell
pr_lidar_native path\to\benchmark.yml path\to\out.gds
```

It can also take a PICBench reference JSON. In that case it automatically runs
the PICBench bridge first:

```powershell
pr_lidar_native path\to\case_ref.json path\to\out.gds
```

Optional routing arguments can be appended when a caller needs to override the
LiDAR-compatible defaults:

```powershell
pr_lidar_native path\to\benchmark.yml path\to\out.gds `
  --net-order=topo --grid-resolution=2 --max-iteration=10
```

This two-argument flow runs:

1. LiDAR YAML to PIC-DB LEF/DEF conversion.
2. C++ LiDAR routing and post-processing on PIC-DB.
3. PIC-DB routed DEF writeback.
4. PIC-DB DB-level DRC summary.
5. gdsfactory/LiDAR-based GDS rendering.

The routing algorithm and DB writeback are implemented in C++. The GDS render
step intentionally calls gdsfactory so the generated devices/components stay
compatible with the Python LiDAR/gdsfactory stack.

## Environment

The tool tries to infer the LiDAR source root from the input YAML path. If the
input YAML is not under a LiDAR checkout, set:

```powershell
$env:PICDB_LIDAR_SRC = "<path-to-LiDAR-src>"
```

The converter and renderer require Python packages used by LiDAR and
gdsfactory. By default the command uses `python` from `PATH`. To select a
specific interpreter, set:

```powershell
$env:PICDB_PYTHON = "<path-to-python>"
```

On Windows, make sure any required native DLL directories are also on `PATH`.

## Outputs

For `out.gds`, the tool creates a sibling working directory:

```text
out_picdb_flow/
  converted/
    converted_lef.yml
    converted_def.yml
    converted_lidar.yml
    conversion_manifest.yml
  cpp/
    lidar_grid_route_flow_summary.txt
    lidar_route_result.yml
    routed_def.yml
    db_drc_summary.txt
    render_invalid_access.txt
```

`out.gds` is rendered with components plus routed waveguides. Invalid access
S-bends and abnormal nets are skipped by the renderer so KLayout can open the
default GDS reliably; the skipped access details remain in
`render_invalid_access.txt`, and route/DB issues remain in
`db_drc_summary.txt`.

## Benchmark Regression

The bundled regression helper runs the native full flow on the LiDAR benchmark
set and collects stdout metrics plus DB DRC summaries into CSV/JSON:

```powershell
python tools\pr_lidar_native\scripts\run_lidar_benchmark_regression.py `
  --output-dir build_native_release\checks\benchmark_regression `
  --prefix full `
  --timeout 7200
```

For a quick smoke test:

```powershell
python tools\pr_lidar_native\scripts\run_lidar_benchmark_regression.py `
  --cases mrr_weight_bank_4x4 clements_8x8 `
  --output-dir build_native_release\checks\benchmark_regression_smoke `
  --prefix smoke `
  --timeout 900 `
  --fail-on-drc
```

Use `--list-cases` to show case names. The default case set is:

- `toy_example_gp`
- `mrr_weight_bank_4x4`, `mrr_weight_bank_8x8`, `mrr_weight_bank_16x16`
- `clements_8x8`, `clements_16x16`
- `multiportmmi_8x8`, `multiportmmi_16x16`, `multiportmmi_32x32`

`multiportmmi_32x32` can take more than an hour on a desktop workstation,
depending on Python/GDS rendering speed. If a case times out, the helper still
parses any generated `db_drc_summary.txt` and terminates the process tree on
Windows so child render processes do not keep running.

The native full flow now routes each case once and reuses that route result for
the flow summary, route-result YAML, DB writeback, DB DRC, and GDS rendering.
The regression CSV includes timing columns such as
`timing_cpp_route_core_s`, `timing_cpp_native_flow_s`,
`timing_lidar_convert_s`, `timing_lidar_render_s`, and
`timing_lidar_full_flow_s`.

`toy_example_gp` intentionally places `obstacle1` and `obstacle2` at the same
schematic coordinate in the original benchmark YAML. A `component_overlap`
marker for that pair is therefore an input-layout marker, not a routed
waveguide or pin-access failure.

For reference comparisons against the original Python LiDAR entrypoint, use the
headless compatibility wrapper:

```powershell
python tools\pr_lidar_native\scripts\run_python_lidar_original.py `
  --picroute-root <path-to-original-LiDAR-src> `
  --benchmark lidar_c_benchmarks\picroute\clements_8x8\clements_8x8.yml `
  --gds build_native_release\checks\python_original\clements_8x8_python.gds
```

The wrapper keeps the original router logic but adds Windows/headless shims for
the legacy `gf.gpdk` API, disables interactive `show()`, fills missing
`loss_comp` entries with zero, and writes temporary cleaned input/layout YAML
copies for current gdsfactory/Pydantic compatibility.

## PIC-DB Debug Mode

The legacy debug mode is still available when LEF/DEF are already converted:

```powershell
pr_lidar_native converted_lef.yml converted_def.yml out_dir `
  --net-order=topo --net-default-bound=100 --allow-abnormal
```

When the first two arguments are both existing YAML files and the second
argument is not a `.gds` output path, the tool also accepts the short form:

```powershell
pr_lidar_native converted_lef.yml converted_def.yml
```

The short form writes debug outputs under `<def_stem>_native_legacy` in the
current working directory. It is meant for existing PIC-DB LEF/DEF benchmark
pairs; full GDS generation still uses `pr_lidar_native input.yml output.gds`.

Supported debug options:

- `--net-order=<topo|naive>`
- `--net-default-bound=<int>`
- `--grid-resolution=<float>`
- `--max-iteration=<int>`
- `--route-group` / `--no-route-group`
- `--enable-45-neighbor` / `--disable-45-neighbor`
- `--deterministic-order`
- `--no-preserve-net-names`
- `--no-snap-near-integer`
- `--allow-abnormal`

## PICBench Place-And-Route Bridge

PICBench JSON bridge support lives in:

```powershell
python tools\picbench_flow\run_picdb_dreamplace_lidar_flow.py MZM
```

That flow converts a PICBench reference JSON into placeholder gdsfactory
macros, emits DREAMPlace Bookshelf files, converts the placement into LiDAR
`gp.yml`, and then calls this C++ native router by default. The same flow is
now also available through `pr_lidar_native <case_ref.json> <out.gds>`.
