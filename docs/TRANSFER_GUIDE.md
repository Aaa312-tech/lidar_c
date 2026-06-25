# Transfer Guide

This guide explains how to move `lidar_c` into a clean PIC-DB checkout and
reproduce the native C++ LiDAR flow.

## 1. Prepare Inputs

You need:

```text
lidar_c package
full PIC-DB source tree
Python environment from requirements-gds-render.txt
optional original Python LiDAR source tree for trace comparison
optional standard GDS directory for XOR comparison
```

Use variables in the examples below:

```powershell
$LidarCRoot = "<path-to-lidar_c>"
$PicdbRoot = "<path-to-full-PIC-DB>"
```

## 2. Merge Into PIC-DB

From `lidar_c`:

```powershell
cd $LidarCRoot
.\tools\merge_into_picdb.ps1 -PicdbRoot $PicdbRoot
```

This copies:

```text
code/src/algorithm/routing/lidar -> <PicdbRoot>/src/algorithm/routing/lidar
code/tools/pr_lidar_native       -> <PicdbRoot>/tools/pr_lidar_native
code/tools/picbench_flow         -> <PicdbRoot>/tools/picbench_flow
code/configs/pr_lidar            -> <PicdbRoot>/configs/pr_lidar
code/benchmarks/picroute         -> <PicdbRoot>/lidar_c_benchmarks/picroute
```

If the target PIC-DB checkout already contains local changes in those
directories, inspect the diff before overwriting or committing.

## 3. Build

From the PIC-DB root:

```powershell
cd $PicdbRoot
cmake --build build_native_release --target pr_lidar_native -j 8
```

If CMake does not know `pr_lidar_native`, confirm that the host PIC-DB CMake
files include the router module and native tool directories copied above.

## 4. Install GDS Render Environment

From `lidar_c`:

```powershell
cd $LidarCRoot
py -3.11 -m venv .venv-gds-render
.\.venv-gds-render\Scripts\python.exe -m pip install --upgrade pip
.\.venv-gds-render\Scripts\python.exe -m pip install -r requirements-gds-render.txt
```

Before running the native full flow:

```powershell
$env:PICDB_PYTHON = "$LidarCRoot\.venv-gds-render\Scripts\python.exe"
```

## 5. Run One Case

```powershell
cd $PicdbRoot
$env:PICDB_PYTHON = "$LidarCRoot\.venv-gds-render\Scripts\python.exe"
build_native_release\pr_lidar_native.exe `
  lidar_c_benchmarks\picroute\clements_8x8\clements_8x8.yml `
  build_native_release\checks\manual\clements_8x8_cpp.gds
```

Expected outputs:

```text
build_native_release/checks/manual/clements_8x8_cpp.gds
build_native_release/checks/manual/clements_8x8_cpp_picdb_flow/cpp/lidar_route_result.yml
build_native_release/checks/manual/clements_8x8_cpp_picdb_flow/cpp/db_drc_summary.txt
```

## 6. Run Default Regression

```powershell
cd $LidarCRoot
.\tools\run_all_cases.ps1 `
  -PicdbRoot $PicdbRoot `
  -PythonExe "$LidarCRoot\.venv-gds-render\Scripts\python.exe" `
  -DriverPython "$LidarCRoot\.venv-gds-render\Scripts\python.exe" `
  -OutputDir build_native_release\checks\benchmark_regression `
  -Prefix benchmark_regression
```

If your benchmarks live outside the merged default location, add:

```powershell
-BenchmarkRoot "<path-to-picroute-benchmarks>"
```

## 7. Compare With Standard GDS

Place the standard files in one directory:

```text
clements_8x8_comp_LiDAR_id-2.gds
multiportmmi_8x8_comp_LiDAR_id-2_bak.gds
multiportmmi_16x16_comp_LiDAR_id-2_bak.gds
```

Then run:

```powershell
cd $PicdbRoot
$env:LIDAR_STANDARD_GDS_DIR = "<path-to-standard-gds-directory>"
$env:LIDAR_CPP_GDS_DIR = "build_native_release\checks\benchmark_regression"
python tools\pr_lidar_native\scripts\compare_gds_geometry.py `
  --out-dir build_native_release\checks\reference_gds_compare
```

You can also pass explicit parameters:

```powershell
python tools\pr_lidar_native\scripts\compare_gds_geometry.py `
  --standard-dir "<path-to-standard-gds-directory>" `
  --cpp-dir build_native_release\checks\benchmark_regression `
  --out-dir build_native_release\checks\reference_gds_compare
```

## 8. Optional Python Baseline Trace

If you have the original Python LiDAR checkout:

```powershell
$env:PICROUTE_ROOT = "<path-to-original-LiDAR-src>"
python tools\pr_lidar_native\scripts\run_python_lidar_original.py `
  --benchmark lidar_c_benchmarks\picroute\clements_8x8\clements_8x8.yml `
  --gds build_native_release\checks\python_original\clements_8x8_python.gds `
  --route-dump build_native_release\checks\python_original\clements_8x8_trace.yml
```

This is useful for debugging path parity. It is not required for normal C++
routing.

## 9. Minimum Transfer Checks

After moving to a new machine or checkout, verify:

```text
pr_lidar_native target builds
one small case runs to completion
output GDS exists
db_drc_summary.txt exists
clements_8x8 has clean=1
clements_8x8 XOR is 0 when using the matching standard GDS and locked render environment
```

Also validate the packaged research artifact from the `lidar_c` root:

```powershell
python tools\validate_research_artifact.py --root .
```

This checks repository-internal JSON, claim ledgers, generated GDS file
existence, GDS SHA256 values, H015 summary totals, standard-GDS comparison
rows, and portable-path hygiene.

## 10. Common Transfer Failures

```text
PICDB_PYTHON points to a Python without gdsfactory/kfactory
gdsfactory/kfactory versions differ from requirements-gds-render.txt
PIC-DB CMake did not include the copied native tool
benchmark root path is wrong
PICDB_LIDAR_SRC is needed because the input YAML is outside a LiDAR-like tree
standard GDS directory was not passed to the compare script
```

For detailed debugging patterns, see:

```text
docs/EXPERIENCE_AND_TROUBLESHOOTING.md
```
