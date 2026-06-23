#!/usr/bin/env python3
"""Run pr_lidar_native on LiDAR benchmarks and collect route/DRC metrics."""

from __future__ import annotations

import argparse
import csv
import json
import os
import platform
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


SCRIPT_DIR = Path(__file__).resolve().parent
PICDB_ROOT = SCRIPT_DIR.parents[2]
DEFAULT_BUILD_EXE = PICDB_ROOT / "build_native_release" / "pr_lidar_native.exe"
DEFAULT_OUTPUT_DIR = PICDB_ROOT / "build_native_release" / "checks" / "benchmark_regression"


def default_benchmark_root() -> Path:
    """Pick a portable benchmark root without relying on a local checkout path."""
    env_value = os.environ.get("LIDAR_BENCHMARK_ROOT")
    if env_value:
        return Path(env_value)

    candidates = [
        PICDB_ROOT / "lidar_c_benchmarks" / "picroute",
        PICDB_ROOT / "benchmarks" / "picroute",
        PICDB_ROOT / "code" / "benchmarks" / "picroute",
        PICDB_ROOT.parent / "lidar_c_benchmarks" / "picroute",
        PICDB_ROOT.parent / "benchmarks" / "picroute",
        PICDB_ROOT.parent / "code" / "benchmarks" / "picroute",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


DEFAULT_BENCHMARK_ROOT = default_benchmark_root()


@dataclass(frozen=True)
class BenchmarkCase:
    name: str
    relative_path: str


DEFAULT_CASES: tuple[BenchmarkCase, ...] = (
    BenchmarkCase("toy_example_gp", "toy_example/toy_example.gp.yml"),
    BenchmarkCase("mrr_weight_bank_4x4", "mrr_weight_bank_4x4/mrr_weight_bank_4x4.yml"),
    BenchmarkCase("mrr_weight_bank_8x8", "mrr_weight_bank_8x8/mrr_weight_bank_8x8.yml"),
    BenchmarkCase("mrr_weight_bank_16x16", "mrr_weight_bank_16x16/mrr_weight_bank_16x16.yml"),
    BenchmarkCase("clements_8x8", "clements_8x8/clements_8x8.yml"),
    BenchmarkCase("clements_16x16", "clements_16x16/clements_16x16.yml"),
    BenchmarkCase("multiportmmi_8x8", "multiportmmi_8x8/multiportmmi_8x8.yml"),
    BenchmarkCase("multiportmmi_16x16", "multiportmmi_16x16/multiportmmi_16x16.yml"),
    BenchmarkCase("multiportmmi_32x32", "multiportmmi_32x32/multiportmmi_32x32.yml"),
)

SUMMARY_COLUMNS = (
    "case",
    "status",
    "returncode",
    "wall_time_s",
    "clean",
    "markers",
    "component_geometry_markers",
    "pin_access_markers",
    "route_geometry_markers",
    "routes",
    "access_waveguides",
    "invalid_access_waveguides",
    "skipped_abnormal_nets",
    "crossings",
    "length",
    "timing_lidar_convert_s",
    "timing_cpp_load_design_s",
    "timing_cpp_runtime_init_s",
    "timing_cpp_route_core_s",
    "timing_cpp_write_reports_s",
    "timing_cpp_writeback_s",
    "timing_cpp_write_def_s",
    "timing_cpp_db_drc_s",
    "timing_cpp_native_flow_s",
    "timing_lidar_render_s",
    "timing_lidar_full_flow_s",
    "gds_exists",
    "gds_bytes",
    "input_yml",
    "gds",
    "flow_dir",
    "db_drc_summary",
    "stdout",
    "stderr",
)


def parse_key_value_lines(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("marker\t") or "\t" in line or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key] = value
    return values


def parse_marker_count(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(
        1
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines()
        if line.startswith("marker\t")
    )


def terminate_process_tree(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    if platform.system().lower().startswith("win"):
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    else:
        process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=10)


def run_case(
    *,
    case: BenchmarkCase,
    benchmark_root: Path,
    native_lidar: Path,
    output_dir: Path,
    route_args: list[str],
    timeout_s: int,
    overwrite: bool,
) -> dict[str, object]:
    input_yml = (benchmark_root / case.relative_path).resolve()
    if not input_yml.exists():
        raise FileNotFoundError(f"{case.name}: benchmark YAML not found: {input_yml}")

    output_dir.mkdir(parents=True, exist_ok=True)
    gds_path = output_dir / f"{case.name}_cpp.gds"
    stdout_path = output_dir / f"{case.name}_cpp.stdout.txt"
    stderr_path = output_dir / f"{case.name}_cpp.stderr.txt"
    flow_dir = output_dir / f"{case.name}_cpp_picdb_flow"
    drc_summary = flow_dir / "cpp" / "db_drc_summary.txt"

    if overwrite:
        for path in (gds_path, stdout_path, stderr_path):
            if path.exists():
                path.unlink()

    command = [str(native_lidar), str(input_yml), str(gds_path), *route_args]
    start = time.perf_counter()
    status = "ok"
    returncode: int | str = "NA"

    with stdout_path.open("wb") as stdout_file, stderr_path.open("wb") as stderr_file:
        process = subprocess.Popen(
            command,
            stdout=stdout_file,
            stderr=stderr_file,
            cwd=PICDB_ROOT,
        )
        try:
            returncode = process.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            status = "timeout"
            returncode = "timeout"
            terminate_process_tree(process)
    wall_time = time.perf_counter() - start

    if status == "ok" and returncode != 0:
        status = "failed"

    stdout_values = parse_key_value_lines(stdout_path)
    drc_values = parse_key_value_lines(drc_summary)
    marker_count = parse_marker_count(drc_summary)
    gds_exists = gds_path.exists()
    gds_bytes = gds_path.stat().st_size if gds_exists else 0

    row: dict[str, object] = {
        "case": case.name,
        "status": status,
        "returncode": returncode,
        "wall_time_s": f"{wall_time:.3f}",
        "clean": drc_values.get("clean", ""),
        "markers": drc_values.get("markers", str(marker_count) if drc_summary.exists() else ""),
        "component_geometry_markers": drc_values.get("component_geometry_markers", ""),
        "pin_access_markers": drc_values.get("pin_access_markers", ""),
        "route_geometry_markers": drc_values.get("route_geometry_markers", ""),
        "routes": stdout_values.get("routes", ""),
        "access_waveguides": stdout_values.get("access_waveguides", ""),
        "invalid_access_waveguides": stdout_values.get("invalid_access_waveguides", ""),
        "skipped_abnormal_nets": stdout_values.get("skipped_abnormal_nets", ""),
        "crossings": stdout_values.get("crossings", ""),
        "length": stdout_values.get("length", ""),
        "timing_lidar_convert_s": stdout_values.get("timing_lidar_convert_s", ""),
        "timing_cpp_load_design_s": stdout_values.get("timing_cpp_load_design_s", ""),
        "timing_cpp_runtime_init_s": stdout_values.get("timing_cpp_runtime_init_s", ""),
        "timing_cpp_route_core_s": stdout_values.get("timing_cpp_route_core_s", ""),
        "timing_cpp_write_reports_s": stdout_values.get("timing_cpp_write_reports_s", ""),
        "timing_cpp_writeback_s": stdout_values.get("timing_cpp_writeback_s", ""),
        "timing_cpp_write_def_s": stdout_values.get("timing_cpp_write_def_s", ""),
        "timing_cpp_db_drc_s": stdout_values.get("timing_cpp_db_drc_s", ""),
        "timing_cpp_native_flow_s": stdout_values.get("timing_cpp_native_flow_s", ""),
        "timing_lidar_render_s": stdout_values.get("timing_lidar_render_s", ""),
        "timing_lidar_full_flow_s": stdout_values.get("timing_lidar_full_flow_s", ""),
        "gds_exists": gds_exists,
        "gds_bytes": gds_bytes,
        "input_yml": str(input_yml),
        "gds": str(gds_path),
        "flow_dir": str(flow_dir),
        "db_drc_summary": str(drc_summary),
        "stdout": str(stdout_path),
        "stderr": str(stderr_path),
    }
    return row


def selected_cases(names: Iterable[str]) -> list[BenchmarkCase]:
    available = {case.name: case for case in DEFAULT_CASES}
    selected: list[BenchmarkCase] = []
    for name in names:
        if name not in available:
            choices = ", ".join(sorted(available))
            raise SystemExit(f"unknown case '{name}'. Available cases: {choices}")
        selected.append(available[name])
    return selected


def write_outputs(rows: list[dict[str, object]], output_dir: Path, prefix: str) -> None:
    csv_path = output_dir / f"{prefix}.csv"
    json_path = output_dir / f"{prefix}.json"
    with csv_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=SUMMARY_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in SUMMARY_COLUMNS})
    json_path.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print(f"summary_csv={csv_path}")
    print(f"summary_json={json_path}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark-root", type=Path, default=DEFAULT_BENCHMARK_ROOT)
    parser.add_argument("--native-lidar", type=Path, default=DEFAULT_BUILD_EXE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--cases",
        nargs="+",
        default=[case.name for case in DEFAULT_CASES],
        help="Benchmark case names to run. Use --list-cases to show names.",
    )
    parser.add_argument("--list-cases", action="store_true")
    parser.add_argument("--timeout", type=int, default=7200, help="Timeout per case in seconds.")
    parser.add_argument("--route-arg", action="append", default=[], help="Extra pr_lidar_native argument.")
    parser.add_argument("--prefix", default="summary", help="Output summary file prefix.")
    parser.add_argument("--no-overwrite", action="store_true", help="Keep existing stdout/stderr/GDS files.")
    parser.add_argument(
        "--fail-on-drc",
        action="store_true",
        help="Exit nonzero when any case has clean != 1.",
    )
    args = parser.parse_args()

    if args.list_cases:
        for case in DEFAULT_CASES:
            print(f"{case.name}\t{case.relative_path}")
        return 0

    native_lidar = args.native_lidar.resolve()
    if not native_lidar.exists():
        raise SystemExit(f"pr_lidar_native not found: {native_lidar}")
    benchmark_root = args.benchmark_root.resolve()
    if not benchmark_root.exists():
        raise SystemExit(f"benchmark root not found: {benchmark_root}")

    rows: list[dict[str, object]] = []
    for case in selected_cases(args.cases):
        print(f"RUN {case.name}", flush=True)
        row = run_case(
            case=case,
            benchmark_root=benchmark_root,
            native_lidar=native_lidar,
            output_dir=args.output_dir.resolve(),
            route_args=list(args.route_arg),
            timeout_s=args.timeout,
            overwrite=not args.no_overwrite,
        )
        rows.append(row)
        print(
            "RESULT "
            f"{row['case']} status={row['status']} clean={row['clean']} "
            f"markers={row['markers']} wall_time_s={row['wall_time_s']}",
            flush=True,
        )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_outputs(rows, args.output_dir.resolve(), args.prefix)

    has_failed_run = any(row["status"] != "ok" for row in rows)
    has_drc_failure = any(str(row.get("clean", "")) != "1" for row in rows)
    if has_failed_run or (args.fail_on_drc and has_drc_failure):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
