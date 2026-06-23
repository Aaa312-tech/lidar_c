# PICBench DREAMPlace LiDAR Bridge

This tool runs a pragmatic PICBench-to-PIC-DB proof flow:

1. Read a PICBench `*_ref.json` logical netlist.
2. Build placeholder gdsfactory macro cells with PICBench port names.
3. Emit Bookshelf files for DREAMPlace global placement.
4. Convert the placement into LiDAR-compatible `gp.yml`.
5. Route and render GDS through PIC-DB `pr_lidar_native` by default.

## Usage

The preferred unified entry point is:

```powershell
pr_lidar_native path\to\case_ref.json path\to\out.gds
```

The standalone Python bridge is still available for debugging and sweeps:

```powershell
python tools\picbench_flow\run_picdb_dreamplace_lidar_flow.py MZM
```

Run one reference JSON directly:

```powershell
python tools\picbench_flow\run_picdb_dreamplace_lidar_flow.py `
  --ref-json path\to\case_ref.json --output-gds path\to\out.gds
```

Run all PICBench cases:

```powershell
python tools\picbench_flow\run_picdb_dreamplace_lidar_flow.py --all `
  --output-root path\to\picdb_flow_topo `
  --dreamplace-iterations 80 `
  --dreamplace-timeout 480 `
  --lidar-timeout 600 `
  --topo-weight 0.001
```

Use Python LiDAR as an A/B fallback:

```powershell
python tools\picbench_flow\run_picdb_dreamplace_lidar_flow.py MZM --router python
```

Useful output controls:

```powershell
python tools\picbench_flow\run_picdb_dreamplace_lidar_flow.py --all `
  --drc-gds-dir path\to\drc_gds `
  --summary-image path\to\summary.png
```

Use `--no-drc-gds` or `--no-summary-image` to disable those collection steps.

## Environment

The script tries to infer paths from this PIC-DB checkout. Override with:

- `PICBENCH_ROOT`: path to the PICBench directory that contains `testcases/`.
- `PICDB_NATIVE_LIDAR`: path to `pr_lidar_native.exe`.
- `PICDB_LIDAR_SRC`: LiDAR source root containing `picroute/`.
- `PICDB_PYTHON`: Python interpreter used by `pr_lidar_native`.
- `DREAMPLACE_WSL_DISTRO`: WSL distribution name, default `Ubuntu-22.04`.
- `DREAMPLACE_PLACER`: WSL path to DREAMPlace `Placer.py`.
- `DREAMPLACE_PYTHONPATH`: WSL `PYTHONPATH` for DREAMPlace.

## Outputs

By default outputs are written under `PICBENCH_ROOT/picdb_flow`. Each case
contains:

```text
<case>/
  dreamplace/
    <case>.aux
    <case>.nodes
    <case>.nets
    <case>.pl
    <case>.scl
    <case>.dreamplace.json
    dreamplace.log
  lidar/
    <case>.gp.yml
    <case>.route.yml
    lidar.log
gds/
  <case>.gds
  <case>_picdb_flow/
    converted/
    cpp/
drc_gds/
  <case>_with_drc.gds
previews/
  <case>.png
summary.png
manifest.json
```

`manifest.json` records whether DREAMPlace and LiDAR completed, which backend
was used, the final GDS path, the PIC-DB DB-DRC summary path, and the collected
DRC-marker GDS path. `drc_gds/` contains one GDS per case with PIC-DB DB-DRC
markers overlaid on marker layers. `summary.png` is a single mosaic image of
all previewable routed/DRC GDS outputs.
