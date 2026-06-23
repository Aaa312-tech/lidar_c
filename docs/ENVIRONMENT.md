# Environment

This document records the portable environment requirements for the C++ LiDAR
router package.

## Host Requirements

Required:

```text
Windows or Linux host capable of building PIC-DB
CMake
C++17-capable compiler
Full PIC-DB source tree
Python 3.11 recommended for GDS rendering
```

The C++ target depends on PIC-DB's existing build graph and libraries:

```text
PIC-DB database layer
PIC-DB IO / LEF / DEF utilities
PIC-DB DRC utilities
yaml-cpp
spdlog
```

This package does not vendor those dependencies. Merge it into a complete
PIC-DB checkout before building.

## Build

From the PIC-DB root:

```powershell
cmake --build build_native_release --target pr_lidar_native -j 8
```

Expected binary:

```text
build_native_release/pr_lidar_native.exe
```

On non-Windows platforms the executable suffix may differ.

## Python Environment For GDS Rendering

`pr_lidar_native` delegates conversion/rendering steps to Python. Select the
interpreter with:

```powershell
$env:PICDB_PYTHON = "<path-to-gds-render-python>"
```

If `PICDB_PYTHON` is unset, the tool uses `python` from `PATH`.

Install the recommended environment:

```powershell
py -3.11 -m venv .venv-gds-render
.\.venv-gds-render\Scripts\python.exe -m pip install --upgrade pip
.\.venv-gds-render\Scripts\python.exe -m pip install -r requirements-gds-render.txt
```

Key tested package versions:

```text
gdsfactory==9.40.2
kfactory==2.4.6
klayout==0.30.6
shapely==2.1.2
hydra-core==1.3.3
omegaconf==2.3.1
numba==0.65.1
multimethod==2.0.2
PyYAML==6.0.3
ryaml==0.5.1
ruamel.yaml==0.19.1
```

The exact dependency lock is:

```text
requirements-gds-render.txt
```

## Optional Environment For Original Python LiDAR

The original Python LiDAR router is only needed for trace comparison and
baseline debugging. It is not required to run the C++ router.

Install it separately if you need Python-vs-C++ trace parity checks:

```powershell
py -3.11 -m venv .venv-python-lidar
.\.venv-python-lidar\Scripts\python.exe -m pip install --upgrade pip
.\.venv-python-lidar\Scripts\python.exe -m pip install -r requirements-python-lidar-original.txt
```

Point the wrapper at the original Python LiDAR source root:

```powershell
$env:PICROUTE_ROOT = "<path-to-original-LiDAR-src>"
```

or pass:

```powershell
python tools\pr_lidar_native\scripts\run_python_lidar_original.py `
  --picroute-root <path-to-original-LiDAR-src> `
  --benchmark <path-to-benchmark-yml> `
  --gds <path-to-output-gds>
```

## Useful Environment Variables

```text
PICDB_PYTHON              Python interpreter used by pr_lidar_native
PICDB_LIDAR_SRC           Optional LiDAR src root for converter/render scripts
LIDAR_BENCHMARK_ROOT      Benchmark root for regression helper
LIDAR_STANDARD_GDS_DIR    Directory containing standard GDS files
LIDAR_CPP_GDS_DIR         Directory containing generated C++ GDS files
LIDAR_CPP_RESULTS_DIR     Directory containing generated C++ route-result folders
LIDAR_PYTHON_GDS_DIR      Optional original Python GDS output directory
LIDAR_PYTHON_RESULTS_DIR  Optional original Python stdout/result directory
PICROUTE_ROOT             Optional original Python LiDAR source root
PICROUTE_CONFIG           Optional original Python LiDAR config file
```

## External Standard GDS

The three standard GDS files used for geometry comparison are not included:

```text
clements_8x8_comp_LiDAR_id-2.gds
multiportmmi_8x8_comp_LiDAR_id-2_bak.gds
multiportmmi_16x16_comp_LiDAR_id-2_bak.gds
```

Place them in any directory and set `LIDAR_STANDARD_GDS_DIR` or pass
`--standard-dir` to:

```text
code/tools/pr_lidar_native/scripts/compare_gds_geometry.py
```

They are comparison-only files. The router never reads them during generation.

## Version Sensitivity

The following outputs are sensitive to Python package versions:

```text
gdsfactory crossing cells
kfactory cell names and metadata
KLayout GDS writer behavior
path extrusion polygonization
layer 44 crossing/via arrays
```

For strict standard-GDS matching, use the dependency versions in
`requirements-gds-render.txt`. For portability testing, run the same regression
with newer versions and compare DRC and XOR reports before trusting the output.
