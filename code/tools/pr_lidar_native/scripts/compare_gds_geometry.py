#!/usr/bin/env python3
"""Compare LiDAR GDS results against reference GDS files.

The script intentionally compares geometry only.  It does not depend on
benchmark names for any route decision and does not modify layouts.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import klayout.db as kdb


@dataclass(frozen=True)
class GdsSpec:
    label: str
    path: Path


@dataclass
class LoadedGds:
    label: str
    path: Path
    file_bytes: int
    dbu: float
    top_name: str
    cell_count: int
    top_bbox: kdb.Box
    layers: dict[tuple[int, int], kdb.Region]


def box_to_um(box: kdb.Box, dbu: float) -> list[float]:
    if box.empty():
        return []
    return [
        round(box.left * dbu, 6),
        round(box.bottom * dbu, 6),
        round(box.right * dbu, 6),
        round(box.top * dbu, 6),
    ]


def box_dims_um(box: kdb.Box, dbu: float) -> list[float]:
    if box.empty():
        return []
    return [round(box.width() * dbu, 6), round(box.height() * dbu, 6)]


def layer_key_sort(key: tuple[int, int]) -> tuple[int, int]:
    return key[0], key[1]


def load_gds(spec: GdsSpec) -> LoadedGds:
    layout = kdb.Layout()
    layout.read(str(spec.path))
    top = layout.top_cell()
    if top is None:
        raise RuntimeError(f"{spec.path} has no top cell")

    layers: dict[tuple[int, int], kdb.Region] = {}
    for layer_index in layout.layer_indices():
        info = layout.get_info(layer_index)
        region = kdb.Region(top.begin_shapes_rec(layer_index))
        region.merge()
        layers[(int(info.layer), int(info.datatype))] = region

    return LoadedGds(
        label=spec.label,
        path=spec.path,
        file_bytes=spec.path.stat().st_size,
        dbu=float(layout.dbu),
        top_name=top.name,
        cell_count=int(layout.cells()),
        top_bbox=top.bbox(),
        layers=layers,
    )


def region_count(region: kdb.Region) -> int:
    try:
        return int(region.count())
    except Exception:
        return sum(1 for _ in region.each())


def area_um2(region: kdb.Region, dbu: float) -> float:
    return float(region.area()) * dbu * dbu


def shifted_layers(
    layers: dict[tuple[int, int], kdb.Region], dx: int, dy: int
) -> dict[tuple[int, int], kdb.Region]:
    if dx == 0 and dy == 0:
        return layers
    return {key: region.moved(dx, dy) for key, region in layers.items()}


def compare_pair(
    case: str,
    baseline: LoadedGds,
    candidate: LoadedGds,
    mode: str,
    candidate_layers: dict[tuple[int, int], kdb.Region],
) -> tuple[dict[str, object], list[dict[str, object]]]:
    if abs(baseline.dbu - candidate.dbu) > 1e-15:
        raise RuntimeError(
            f"DBU mismatch for {case} {baseline.label} vs {candidate.label}: "
            f"{baseline.dbu} vs {candidate.dbu}"
        )

    dbu = baseline.dbu
    all_keys = sorted(
        set(baseline.layers.keys()) | set(candidate_layers.keys()), key=layer_key_sort
    )
    detail_rows: list[dict[str, object]] = []
    total_base_area = 0.0
    total_cand_area = 0.0
    total_inter_area = 0.0
    total_only_base_area = 0.0
    total_only_cand_area = 0.0
    total_xor_area = 0.0

    for layer, datatype in all_keys:
        key = (layer, datatype)
        base = baseline.layers.get(key, kdb.Region())
        cand = candidate_layers.get(key, kdb.Region())
        inter = base & cand
        only_base = base - cand
        only_cand = cand - base

        base_area = area_um2(base, dbu)
        cand_area = area_um2(cand, dbu)
        inter_area = area_um2(inter, dbu)
        only_base_area = area_um2(only_base, dbu)
        only_cand_area = area_um2(only_cand, dbu)
        xor_area = only_base_area + only_cand_area

        total_base_area += base_area
        total_cand_area += cand_area
        total_inter_area += inter_area
        total_only_base_area += only_base_area
        total_only_cand_area += only_cand_area
        total_xor_area += xor_area

        denom = base_area + cand_area
        overlap_ratio = 0.0 if denom == 0.0 else (2.0 * inter_area / denom)

        detail_rows.append(
            {
                "case": case,
                "baseline": baseline.label,
                "candidate": candidate.label,
                "mode": mode,
                "layer": layer,
                "datatype": datatype,
                "baseline_area_um2": round(base_area, 6),
                "candidate_area_um2": round(cand_area, 6),
                "intersection_area_um2": round(inter_area, 6),
                "only_baseline_area_um2": round(only_base_area, 6),
                "only_candidate_area_um2": round(only_cand_area, 6),
                "xor_area_um2": round(xor_area, 6),
                "overlap_ratio": round(overlap_ratio, 9),
                "baseline_polygons": region_count(base),
                "candidate_polygons": region_count(cand),
                "baseline_bbox_um": json.dumps(box_to_um(base.bbox(), dbu)),
                "candidate_bbox_um": json.dumps(box_to_um(cand.bbox(), dbu)),
            }
        )

    denom = total_base_area + total_cand_area
    summary = {
        "case": case,
        "baseline": baseline.label,
        "candidate": candidate.label,
        "mode": mode,
        "baseline_file": str(baseline.path),
        "candidate_file": str(candidate.path),
        "baseline_file_bytes": baseline.file_bytes,
        "candidate_file_bytes": candidate.file_bytes,
        "baseline_top": baseline.top_name,
        "candidate_top": candidate.top_name,
        "baseline_cells": baseline.cell_count,
        "candidate_cells": candidate.cell_count,
        "dbu": dbu,
        "baseline_top_bbox_um": json.dumps(box_to_um(baseline.top_bbox, dbu)),
        "candidate_top_bbox_um": json.dumps(box_to_um(candidate.top_bbox, dbu)),
        "baseline_top_size_um": json.dumps(box_dims_um(baseline.top_bbox, dbu)),
        "candidate_top_size_um": json.dumps(box_dims_um(candidate.top_bbox, dbu)),
        "layer_count_union": len(all_keys),
        "baseline_total_area_um2": round(total_base_area, 6),
        "candidate_total_area_um2": round(total_cand_area, 6),
        "intersection_total_area_um2": round(total_inter_area, 6),
        "only_baseline_total_area_um2": round(total_only_base_area, 6),
        "only_candidate_total_area_um2": round(total_only_cand_area, 6),
        "xor_total_area_um2": round(total_xor_area, 6),
        "total_overlap_ratio": round(0.0 if denom == 0.0 else (2.0 * total_inter_area / denom), 9),
    }
    return summary, detail_rows


def top_region_pieces(
    region: kdb.Region, dbu: float, limit: int
) -> list[dict[str, object]]:
    pieces = []
    for polygon in region.each():
        pieces.append(
            {
                "area_um2": float(polygon.area()) * dbu * dbu,
                "bbox_um": json.dumps(box_to_um(polygon.bbox(), dbu)),
                "size_um": json.dumps(box_dims_um(polygon.bbox(), dbu)),
            }
        )
    pieces.sort(key=lambda item: float(item["area_um2"]), reverse=True)
    return pieces[:limit]


def hotspot_rows_for_pair(
    case: str,
    baseline: LoadedGds,
    candidate: LoadedGds,
    mode: str,
    candidate_layers: dict[tuple[int, int], kdb.Region],
    limit_per_side: int = 20,
) -> list[dict[str, object]]:
    dbu = baseline.dbu
    rows: list[dict[str, object]] = []
    all_keys = sorted(
        set(baseline.layers.keys()) | set(candidate_layers.keys()), key=layer_key_sort
    )
    for layer, datatype in all_keys:
        key = (layer, datatype)
        base = baseline.layers.get(key, kdb.Region())
        cand = candidate_layers.get(key, kdb.Region())
        for side, region in [
            ("only_baseline", base - cand),
            ("only_candidate", cand - base),
        ]:
            for rank, item in enumerate(
                top_region_pieces(region, dbu, limit_per_side), start=1
            ):
                rows.append(
                    {
                        "case": case,
                        "baseline": baseline.label,
                        "candidate": candidate.label,
                        "mode": mode,
                        "layer": layer,
                        "datatype": datatype,
                        "side": side,
                        "rank": rank,
                        "area_um2": round(float(item["area_um2"]), 6),
                        "bbox_um": item["bbox_um"],
                        "size_um": item["size_um"],
                    }
                )
    return rows


def write_csv(path: Path, rows: Iterable[dict[str, object]]) -> None:
    rows = list(rows)
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
        "--standard-dir",
        type=Path,
        default=Path(os.environ.get("LIDAR_STANDARD_GDS_DIR", "standard_gds")),
        help=(
            "Directory containing reference GDS files. "
            "Can also be set with LIDAR_STANDARD_GDS_DIR."
        ),
    )
    parser.add_argument(
        "--cpp-dir",
        type=Path,
        default=Path(
            os.environ.get(
                "LIDAR_CPP_GDS_DIR",
                "build_native_release/checks/benchmark_regression",
            )
        ),
        help="Directory containing {case}_cpp.gds files. Can also be set with LIDAR_CPP_GDS_DIR.",
    )
    parser.add_argument(
        "--python-dir",
        type=Path,
        default=Path(
            os.environ.get(
                "LIDAR_PYTHON_GDS_DIR",
                "build_native_release/checks/python_original_full",
            )
        ),
        help=(
            "Optional directory containing {case}_python.gds files. "
            "Can also be set with LIDAR_PYTHON_GDS_DIR."
        ),
    )
    args = parser.parse_args()

    standard_dir = args.standard_dir
    cpp_dir = args.cpp_dir
    py_dir = args.python_dir

    cases: dict[str, dict[str, Path]] = {
        "clements_8x8": {
            "standard": standard_dir / "clements_8x8_comp_LiDAR_id-2.gds",
            "cpp": cpp_dir / "clements_8x8_cpp.gds",
            "python_original": py_dir / "clements_8x8_python.gds",
        },
        "multiportmmi_8x8": {
            "standard": standard_dir / "multiportmmi_8x8_comp_LiDAR_id-2_bak.gds",
            "cpp": cpp_dir / "multiportmmi_8x8_cpp.gds",
            "python_original": py_dir / "multiportmmi_8x8_python.gds",
        },
        "multiportmmi_16x16": {
            "standard": standard_dir / "multiportmmi_16x16_comp_LiDAR_id-2_bak.gds",
            "cpp": cpp_dir / "multiportmmi_16x16_cpp.gds",
            "python_original": py_dir / "multiportmmi_16x16_python.gds",
        },
    }

    args.out_dir.mkdir(parents=True, exist_ok=True)
    summary_rows: list[dict[str, object]] = []
    layer_rows: list[dict[str, object]] = []
    gds_rows: list[dict[str, object]] = []
    hotspot_rows: list[dict[str, object]] = []

    for case, paths in cases.items():
        loaded: dict[str, LoadedGds] = {}
        for label, path in paths.items():
            if not path.exists():
                if label == "python_original":
                    continue
                raise FileNotFoundError(
                    f"{label} GDS not found for {case}: {path}. "
                    "Pass --standard-dir/--cpp-dir or set the matching environment variable."
                )
            loaded[label] = load_gds(GdsSpec(label=label, path=path))
            item = loaded[label]
            gds_rows.append(
                {
                    "case": case,
                    "label": label,
                    "file": str(path),
                    "file_bytes": item.file_bytes,
                    "dbu": item.dbu,
                    "top": item.top_name,
                    "cells": item.cell_count,
                    "top_bbox_um": json.dumps(box_to_um(item.top_bbox, item.dbu)),
                    "top_size_um": json.dumps(box_dims_um(item.top_bbox, item.dbu)),
                    "layers": json.dumps(sorted([list(k) for k in item.layers.keys()])),
                    "total_area_um2": round(
                        sum(area_um2(region, item.dbu) for region in item.layers.values()), 6
                    ),
                }
            )

        pair_labels = [
            ("standard", "cpp"),
        ]
        if "python_original" in loaded:
            pair_labels.extend(
                [
                    ("standard", "python_original"),
                    ("python_original", "cpp"),
                ]
            )

        for baseline_label, candidate_label in pair_labels:
            baseline = loaded[baseline_label]
            candidate = loaded[candidate_label]
            base_ll = baseline.top_bbox.p1
            cand_ll = candidate.top_bbox.p1
            dx = base_ll.x - cand_ll.x
            dy = base_ll.y - cand_ll.y

            for mode, candidate_layers in [
                ("raw", candidate.layers),
                ("candidate_bbox_ll_aligned", shifted_layers(candidate.layers, dx, dy)),
            ]:
                summary, details = compare_pair(
                    case=case,
                    baseline=baseline,
                    candidate=candidate,
                    mode=mode,
                    candidate_layers=candidate_layers,
                )
                summary["candidate_shift_dbu"] = json.dumps([dx if mode != "raw" else 0, dy if mode != "raw" else 0])
                summary["candidate_shift_um"] = json.dumps(
                    [
                        round((dx if mode != "raw" else 0) * baseline.dbu, 6),
                        round((dy if mode != "raw" else 0) * baseline.dbu, 6),
                    ]
                )
                summary_rows.append(summary)
                layer_rows.extend(details)
                if mode == "raw":
                    hotspot_rows.extend(
                        hotspot_rows_for_pair(
                            case=case,
                            baseline=baseline,
                            candidate=candidate,
                            mode=mode,
                            candidate_layers=candidate_layers,
                        )
                    )

    write_csv(args.out_dir / "gds_inventory.csv", gds_rows)
    write_csv(args.out_dir / "gds_pair_summary.csv", summary_rows)
    write_csv(args.out_dir / "gds_layer_xor.csv", layer_rows)
    write_csv(args.out_dir / "gds_xor_hotspots.csv", hotspot_rows)

    (args.out_dir / "gds_pair_summary.json").write_text(
        json.dumps(summary_rows, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"Wrote {args.out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
