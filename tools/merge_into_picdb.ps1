param(
    [Parameter(Mandatory = $true)]
    [string]$PicdbRoot
)

$ErrorActionPreference = "Stop"

$PackageRoot = Split-Path -Parent $PSScriptRoot
$ResolvedPicdbRoot = (Resolve-Path -LiteralPath $PicdbRoot).Path

Write-Host "Package root: $PackageRoot"
Write-Host "PIC-DB root:   $ResolvedPicdbRoot"

$copies = @(
    @{ Source = "code\src\algorithm\routing\lidar"; Destination = "src\algorithm\routing\lidar" },
    @{ Source = "code\tools\pr_lidar_native"; Destination = "tools\pr_lidar_native" },
    @{ Source = "code\tools\picbench_flow"; Destination = "tools\picbench_flow" },
    @{ Source = "code\configs\pr_lidar"; Destination = "configs\pr_lidar" },
    @{ Source = "code\benchmarks\picroute"; Destination = "lidar_c_benchmarks\picroute" }
)

foreach ($copy in $copies) {
    $src = Join-Path $PackageRoot $copy.Source
    $dst = Join-Path $ResolvedPicdbRoot $copy.Destination
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $dst) | Out-Null
    Copy-Item -Path $src -Destination (Split-Path -Parent $dst) -Recurse -Force
    Write-Host "Copied $src -> $dst"
}

Write-Host "Done. Build pr_lidar_native inside the PIC-DB tree next."
