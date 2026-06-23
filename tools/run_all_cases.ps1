param(
    [Parameter(Mandatory = $true)]
    [string]$PicdbRoot,

    [Parameter(Mandatory = $true)]
    [string]$PythonExe,

    [string]$DriverPython = "python",

    [string]$BenchmarkRoot = "",

    [string]$OutputDir = "build_native_release\checks\benchmark_regression",

    [string]$Prefix = "benchmark_regression",

    [int]$Timeout = 7200
)

$ErrorActionPreference = "Stop"

$ResolvedPicdbRoot = (Resolve-Path -LiteralPath $PicdbRoot).Path
$NativeLidar = Join-Path $ResolvedPicdbRoot "build_native_release\pr_lidar_native.exe"
$Script = Join-Path $ResolvedPicdbRoot "tools\pr_lidar_native\scripts\run_lidar_benchmark_regression.py"

if (!(Test-Path -LiteralPath $NativeLidar)) {
    throw "Native binary not found: $NativeLidar"
}

if (!(Test-Path -LiteralPath $Script)) {
    throw "Regression script not found: $Script"
}

$env:PICDB_PYTHON = $PythonExe

Push-Location $ResolvedPicdbRoot
try {
    $CommandArgs = @(
        $Script,
        "--native-lidar", $NativeLidar,
        "--output-dir", $OutputDir,
        "--timeout", $Timeout,
        "--prefix", $Prefix
    )

    if ($BenchmarkRoot) {
        $CommandArgs += @("--benchmark-root", $BenchmarkRoot)
    }

    & $DriverPython @CommandArgs
}
finally {
    Pop-Location
}
