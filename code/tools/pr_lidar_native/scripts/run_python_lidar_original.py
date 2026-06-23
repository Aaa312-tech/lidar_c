#!/usr/bin/env python3
"""Run the original Python LiDAR entrypoint with Windows/headless shims."""

from __future__ import annotations

import argparse
import os
import re
import runpy
import sys
import time
import types
from pathlib import Path
from typing import Any

import yaml


SCRIPT_DIR = Path(__file__).resolve().parent
PICDB_ROOT = SCRIPT_DIR.parents[2]


def default_picroute_root() -> Path:
    """Find an original Python LiDAR checkout in portable locations."""
    env_value = os.environ.get("PICROUTE_ROOT") or os.environ.get("LIDAR_PICROUTE_ROOT")
    if env_value:
        return Path(env_value)

    candidates = [
        PICDB_ROOT / "third_party" / "LiDAR" / "src",
        PICDB_ROOT / "third-party" / "LiDAR" / "src",
        PICDB_ROOT.parent / "third_party" / "LiDAR" / "src",
        PICDB_ROOT.parent / "third-party" / "LiDAR" / "src",
    ]
    for candidate in candidates:
        if (candidate / "picroute" / "main" / "picroute.py").exists():
            return candidate
    return candidates[0]


DEFAULT_PICROUTE_ROOT = default_picroute_root()
DEFAULT_CONFIG = Path(
    os.environ.get(
        "PICROUTE_CONFIG",
        DEFAULT_PICROUTE_ROOT / "picroute" / "config" / "comp_LiDAR.yml",
    )
)


def patch_gdsfactory() -> None:
    """Restore assumptions made by the original LiDAR code."""
    import gdsfactory as gf

    if not hasattr(gf, "gpdk"):
        from gdsfactory.generic_tech import get_generic_pdk

        gf.gpdk = types.SimpleNamespace(PDK=get_generic_pdk())

    def no_op_show(self, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003
        return None

    gf.Component.show = no_op_show


def normalize_legacy_python_yaml_tags(text: str) -> str:
    def layer_replacement(match):
        values = [value.strip() for value in match.group(1).split(",") if value.strip()]
        if len(values) == 1:
            values.append("0")
        return "[" + ", ".join(values[:2]) + "]"

    return re.sub(
        r"!!python/object/apply:kfactory\.layer\.LAYER\s*\[([^\]]+)\]",
        layer_replacement,
        text,
    )


def load_local_yaml(path: Path):
    text = normalize_legacy_python_yaml_tags(path.read_text(encoding="utf-8"))
    try:
        return yaml.safe_load(text)
    except yaml.YAMLError:
        return yaml.load(text, Loader=yaml.UnsafeLoader)


def patch_picroute_layout_yaml(picroute_root: Path) -> None:
    if str(picroute_root) not in sys.path:
        sys.path.insert(0, str(picroute_root))

    from picroute.database import schematic as schematic_mod
    from render_route_result_gds import (
        clean_none_values,
        load_yaml_compat,
        sanitize_gdsfactory_layout_data,
    )

    original_to_yaml = schematic_mod.CustomNetlist.to_yaml

    def clean_generated_layout_yaml(self, filepath, *hook_args, **hook_kwargs):
        result = original_to_yaml(self, filepath, *hook_args, **hook_kwargs)
        layout_path = Path(filepath)
        try:
            layout_data = load_yaml_compat(layout_path)
            layout_path.write_text(
                yaml.safe_dump(
                    sanitize_gdsfactory_layout_data(
                        clean_none_values(layout_data)
                    ),
                    sort_keys=False,
                ),
                encoding="utf-8",
            )
        except Exception:
            pass
        return result

    schematic_mod.CustomNetlist.to_yaml = clean_generated_layout_yaml


def _plain_number(value: Any):
    try:
        return float(value)
    except Exception:
        return value


def _plain_point(point: Any):
    if hasattr(point, "tolist"):
        point = point.tolist()
    return [_plain_number(value) for value in point]


def _plain_points(points: Any):
    if points is None:
        return []
    if hasattr(points, "tolist"):
        points = points.tolist()
    return [_plain_point(point) for point in points]


def _plain_port(port: Any):
    if port is None:
        return {}
    center = getattr(port, "dcenter", getattr(port, "center", None))
    if center is not None and hasattr(center, "tolist"):
        center = center.tolist()
    return {
        "name": str(getattr(port, "name", "")),
        "center": _plain_point(center if center is not None else []),
        "orientation": _plain_number(getattr(port, "orientation", 0.0)),
        "width": _plain_number(getattr(port, "width", 0.5)),
        "layer": list(getattr(port, "layer", []))
        if hasattr(getattr(port, "layer", []), "__iter__")
        else getattr(port, "layer", None),
    }


def patch_picroute_route_trace(picroute_root: Path) -> None:
    if str(picroute_root) not in sys.path:
        sys.path.insert(0, str(picroute_root))

    from picroute.routing import astarsearch as astar_mod

    original_backtrack = astar_mod.AstarSearch.backTrack

    def traced_backtrack(self, node, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003
        path, origin_path, violated_nets = original_backtrack(self, node, *args, **kwargs)
        try:
            object.__setattr__(self._net, "_picdb_trace_processed_path_um", _plain_points(path))
            object.__setattr__(self._net, "_picdb_trace_origin_path_grid", _plain_points(origin_path))
            object.__setattr__(
                self._net,
                "_picdb_trace_violated_nets",
                sorted(str(net) for net in (violated_nets or [])),
            )
        except Exception:
            pass
        return path, origin_path, violated_nets

    astar_mod.AstarSearch.backTrack = traced_backtrack


def dump_python_route_trace(router: Any, route_dump: Path) -> None:
    cirdb = getattr(router, "cirdb", None)
    db_nets = getattr(cirdb, "dbNets", {}) if cirdb is not None else {}
    result: dict[str, Any] = {
        "schema": "picdb_python_lidar_route_trace",
        "schema_version": 1,
        "nets": {},
    }

    for net_name, net in db_nets.items():
        paths = []
        for path in getattr(net, "routed_path", []) or []:
            points = path[0] if len(path) > 0 else []
            start_port = path[1] if len(path) > 1 else None
            end_port = path[2] if len(path) > 2 else None
            paths.append(
                {
                    "points": _plain_points(points),
                    "start_port": _plain_port(start_port),
                    "end_port": _plain_port(end_port),
                }
            )

        result["nets"][str(net_name)] = {
            "routed": bool(getattr(net, "routed", False)),
            "origin_path_grid": getattr(net, "_picdb_trace_origin_path_grid", []),
            "processed_path_um": getattr(net, "_picdb_trace_processed_path_um", []),
            "post_paths": paths,
            "crossing_nets": sorted(str(value) for value in getattr(net, "crossing_nets", []) or []),
            "crossing_num": int(getattr(net, "crossing_num", 0) or 0),
            "wirelength": _plain_number(getattr(net, "wirelength", 0.0)),
            "bending": _plain_number(getattr(net, "bending", 0.0)),
            "vionets": int(getattr(net, "vionets", 0) or 0),
            "vio_nets": sorted(str(value) for value in getattr(net, "vioNets", []) or []),
        }

    route_dump.parent.mkdir(parents=True, exist_ok=True)
    route_dump.write_text(yaml.safe_dump(result, sort_keys=False), encoding="utf-8")


def make_compatible_config(
    *,
    config_path: Path,
    benchmark_path: Path,
    output_gds: Path,
    missing_loss_default: float,
) -> Path:
    """Fill loss_comp entries required unconditionally by the original loader."""
    config = load_local_yaml(config_path)
    benchmark = load_local_yaml(benchmark_path)

    macro_types: set[str] = set()
    for inst in benchmark.get("instances", {}).values():
        settings = inst.get("settings", {})
        macro_type = settings.get("macro_type")
        if macro_type:
            macro_types.add(str(macro_type))

    dr_config = config.setdefault("dr", {})
    loss_comp = dr_config.setdefault("loss_comp", {})
    if loss_comp is None:
        loss_comp = {}
        dr_config["loss_comp"] = loss_comp
    for macro_type in sorted(macro_types):
        loss_comp.setdefault(macro_type, missing_loss_default)

    compat_config = output_gds.parent / f"{output_gds.stem}.compat_config.yml"
    compat_config.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    return compat_config


def make_compatible_benchmark(benchmark_path: Path, output_gds: Path) -> Path:
    from render_route_result_gds import clean_none_values

    benchmark = clean_none_values(load_local_yaml(benchmark_path))
    compat_benchmark = output_gds.parent / f"{output_gds.stem}.compat_input.yml"
    compat_benchmark.write_text(
        yaml.safe_dump(benchmark, sort_keys=False),
        encoding="utf-8",
    )
    return compat_benchmark


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--picroute-root", type=Path, default=DEFAULT_PICROUTE_ROOT)
    parser.add_argument("--benchmark", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--gds", type=Path, required=True)
    parser.add_argument("--route-dump", type=Path, default=None)
    parser.add_argument("--missing-loss-default", type=float, default=0.0)
    parser.add_argument(
        "extra_args",
        nargs=argparse.REMAINDER,
        help="Extra options forwarded to picroute.py after a literal --.",
    )
    args = parser.parse_args()

    picroute_root = args.picroute_root.resolve()
    entrypoint = picroute_root / "picroute" / "main" / "picroute.py"
    if not entrypoint.exists():
        raise SystemExit(f"picroute.py not found: {entrypoint}")
    if not args.benchmark.exists():
        raise SystemExit(f"benchmark not found: {args.benchmark}")
    if not args.config.exists():
        raise SystemExit(f"config not found: {args.config}")

    args.gds.parent.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("MPLBACKEND", "Agg")
    patch_gdsfactory()
    patch_picroute_layout_yaml(picroute_root)
    if args.route_dump:
        patch_picroute_route_trace(picroute_root)
    compat_benchmark = make_compatible_benchmark(
        args.benchmark.resolve(),
        args.gds.resolve(),
    )
    compat_config = make_compatible_config(
        config_path=args.config.resolve(),
        benchmark_path=compat_benchmark.resolve(),
        output_gds=args.gds.resolve(),
        missing_loss_default=args.missing_loss_default,
    )

    forwarded = list(args.extra_args)
    if forwarded and forwarded[0] == "--":
        forwarded = forwarded[1:]

    sys.argv = [
        str(entrypoint),
        "--benchmark",
        str(compat_benchmark.resolve()),
        "--config",
        str(compat_config.resolve()),
        f"--run.output_layout_gds_path={args.gds.resolve()}",
        *forwarded,
    ]

    start = time.perf_counter()
    try:
        globals_after = runpy.run_path(str(entrypoint), run_name="__main__")
    finally:
        print(f"python_original_wall_time_s={time.perf_counter() - start:.3f}", flush=True)
        print(f"python_original_gds={args.gds.resolve()}", flush=True)
        print(f"python_original_gds_exists={args.gds.exists()}", flush=True)
        if args.gds.exists():
            print(f"python_original_gds_bytes={args.gds.stat().st_size}", flush=True)
    if args.route_dump:
        router = globals_after.get("router")
        dump_python_route_trace(router, args.route_dump.resolve())
        print(f"python_original_route_dump={args.route_dump.resolve()}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
