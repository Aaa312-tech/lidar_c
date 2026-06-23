#!/usr/bin/env python3
"""Compare original Python LiDAR net metrics with native C++ route results."""

from __future__ import annotations

import argparse
import csv
import math
import os
import re
from pathlib import Path

import yaml


PY_NET_RE = re.compile(
    r"Net:\s*(?P<net>n_\d+),\s*WL:\s*(?P<wl>[0-9.]+)\s*um,\s*"
    r"Accumulated bend:\s*(?P<bend>[0-9.]+),Crossing:\s*(?P<crossing>\d+)"
)


def parse_python_stdout(path: Path) -> dict[str, dict[str, float]]:
    metrics: dict[str, dict[str, float]] = {}
    text = path.read_text(encoding="utf-8", errors="replace")
    for match in PY_NET_RE.finditer(text):
        net = match.group("net")
        metrics[net] = {
            "python_wl_um": float(match.group("wl")),
            "python_bend_deg": float(match.group("bend")),
            "python_crossings": int(match.group("crossing")),
        }
    return metrics


def polyline_length(points: list[list[float]]) -> float:
    total = 0.0
    for a, b in zip(points, points[1:]):
        total += math.hypot(float(b[0]) - float(a[0]), float(b[1]) - float(a[1]))
    return total


def direction_changes(points: list[list[float]]) -> int:
    dirs: list[tuple[int, int]] = []
    for a, b in zip(points, points[1:]):
        dx = float(b[0]) - float(a[0])
        dy = float(b[1]) - float(a[1])
        if abs(dx) < 1e-9 and abs(dy) < 1e-9:
            continue
        sx = 0 if abs(dx) < 1e-9 else (1 if dx > 0 else -1)
        sy = 0 if abs(dy) < 1e-9 else (1 if dy > 0 else -1)
        dirs.append((sx, sy))
    return sum(1 for a, b in zip(dirs, dirs[1:]) if a != b)


def parse_cpp_route_result(path: Path) -> dict[str, dict[str, float]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    metrics: dict[str, dict[str, float]] = {}
    for entry in data.get("flow", []):
        net = str(entry.get("net", ""))
        if not net:
            continue
        points = entry.get("processed_path_um") or []
        crossings = entry.get("crossings") or []
        metrics[net] = {
            "cpp_polyline_um": polyline_length(points),
            "cpp_points": len(points),
            "cpp_turns": direction_changes(points),
            "cpp_crossings": len(crossings),
            "cpp_success": bool(entry.get("success", False)),
            "cpp_strict": bool(entry.get("strict", False)),
            "cpp_short_sbend": bool(entry.get("short_sbend", False)),
        }
    return metrics


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument(
        "--python-dir",
        type=Path,
        default=Path(
            os.environ.get(
                "LIDAR_PYTHON_RESULTS_DIR",
                "build_native_release/checks/python_original_full",
            )
        ),
        help=(
            "Directory containing {case}_python.stdout.txt files. "
            "Can also be set with LIDAR_PYTHON_RESULTS_DIR."
        ),
    )
    parser.add_argument(
        "--cpp-dir",
        type=Path,
        default=Path(
            os.environ.get(
                "LIDAR_CPP_RESULTS_DIR",
                "build_native_release/checks/benchmark_regression",
            )
        ),
        help=(
            "Directory containing {case}_cpp_picdb_flow/cpp/lidar_route_result.yml. "
            "Can also be set with LIDAR_CPP_RESULTS_DIR."
        ),
    )
    args = parser.parse_args()

    py_dir = args.python_dir
    cpp_base = args.cpp_dir
    cases = {
        "clements_8x8": {
            "py": py_dir / "clements_8x8_python.stdout.txt",
            "cpp": cpp_base
            / "clements_8x8_cpp_picdb_flow"
            / "cpp"
            / "lidar_route_result.yml",
        },
        "multiportmmi_8x8": {
            "py": py_dir / "multiportmmi_8x8_python.stdout.txt",
            "cpp": cpp_base
            / "multiportmmi_8x8_cpp_picdb_flow"
            / "cpp"
            / "lidar_route_result.yml",
        },
        "multiportmmi_16x16": {
            "py": py_dir / "multiportmmi_16x16_python.stdout.txt",
            "cpp": cpp_base
            / "multiportmmi_16x16_cpp_picdb_flow"
            / "cpp"
            / "lidar_route_result.yml",
        },
    }

    args.out_dir.mkdir(parents=True, exist_ok=True)
    summary_rows: list[dict[str, object]] = []
    net_rows: list[dict[str, object]] = []

    for case, paths in cases.items():
        py = parse_python_stdout(paths["py"])
        cpp = parse_cpp_route_result(paths["cpp"])
        nets = sorted(set(py) | set(cpp), key=lambda n: int(n.split("_")[1]))
        shared = sorted(set(py) & set(cpp), key=lambda n: int(n.split("_")[1]))

        for net in nets:
            row: dict[str, object] = {"case": case, "net": net}
            row.update(py.get(net, {}))
            row.update(cpp.get(net, {}))
            if net in py and net in cpp:
                row["wl_minus_cpp_polyline_um"] = round(
                    py[net]["python_wl_um"] - cpp[net]["cpp_polyline_um"], 6
                )
                row["crossing_delta_cpp_minus_python"] = int(
                    cpp[net]["cpp_crossings"] - py[net]["python_crossings"]
                )
            else:
                row["wl_minus_cpp_polyline_um"] = ""
                row["crossing_delta_cpp_minus_python"] = ""
            net_rows.append(row)

        summary_rows.append(
            {
                "case": case,
                "python_nets": len(py),
                "cpp_nets": len(cpp),
                "shared_nets": len(shared),
                "missing_in_cpp": " ".join(sorted(set(py) - set(cpp), key=lambda n: int(n.split("_")[1]))),
                "extra_in_cpp": " ".join(sorted(set(cpp) - set(py), key=lambda n: int(n.split("_")[1]))),
                "python_total_wl_um": round(sum(v["python_wl_um"] for v in py.values()), 6),
                "cpp_total_polyline_um": round(sum(v["cpp_polyline_um"] for v in cpp.values()), 6),
                "python_total_crossings": int(sum(v["python_crossings"] for v in py.values())),
                "cpp_total_crossings": int(sum(v["cpp_crossings"] for v in cpp.values())),
                "shared_crossing_mismatches": sum(
                    1 for net in shared if py[net]["python_crossings"] != cpp[net]["cpp_crossings"]
                ),
                "shared_abs_crossing_delta": int(
                    sum(abs(py[net]["python_crossings"] - cpp[net]["cpp_crossings"]) for net in shared)
                ),
            }
        )

    write_csv(args.out_dir / "net_metric_summary.csv", summary_rows)
    write_csv(args.out_dir / "net_metric_detail.csv", net_rows)
    print(f"Wrote {args.out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
