"""Run a PICBench -> DREAMPlace -> LiDAR proof-of-flow.

The flow is intentionally pragmatic: PICBench golden JSON is a logical SAX
netlist, while PIC-DB/LiDAR expects physical macro data.  This bridge uses the
PICBench GDSFactory adapter cells as placeholder PCells, emits a Bookshelf
placement benchmark for DREAMPlace, converts the placement into LiDAR's gp.yml
format, and invokes LiDAR to produce a routed GDS.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import shlex
import subprocess
import sys
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import gdsfactory as gf
import yaml

from gdsfactory_adapters import component_name_for_model, register_picbench_cells


def _env_path(name: str) -> Path | None:
    value = os.environ.get(name)
    return Path(value).resolve() if value else None


def _first_existing(candidates: list[Path]) -> Path | None:
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    return None


PICDB_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
PICBENCH_ROOT = _env_path("PICBENCH_ROOT") or _first_existing(
    [
        PICDB_ROOT.parent / "PIC-Bench" / "PICBench",
        PICDB_ROOT.parent.parent / "PIC-Bench" / "PICBench",
        PICDB_ROOT / "external" / "PIC-Bench" / "PICBench",
    ]
) or (PICDB_ROOT.parent / "PIC-Bench" / "PICBench")
LIDAR_SRC = _env_path("PICDB_LIDAR_SRC") or _first_existing(
    [
        PICDB_ROOT / "third-party" / "LiDAR" / "src",
        PICDB_ROOT.parent / "LiDAR-external" / "src",
        PICDB_ROOT.parent.parent / "LiDAR-external" / "src",
    ]
) or (PICDB_ROOT / "third-party" / "LiDAR" / "src")
LIDAR_MAIN = LIDAR_SRC / "picroute" / "main" / "picroute.py"
NATIVE_LIDAR = _env_path("PICDB_NATIVE_LIDAR") or _first_existing(
    [
        PICDB_ROOT / "build" / "Release" / "pr_lidar_native.exe",
        PICDB_ROOT / "build" / "pr_lidar_native.exe",
        PICDB_ROOT / "build" / "Debug" / "pr_lidar_native.exe",
    ]
) or (PICDB_ROOT / "build" / "Release" / "pr_lidar_native.exe")
DREAMPLACE_WSL_DISTRO = os.environ.get("DREAMPLACE_WSL_DISTRO", "Ubuntu-22.04")
DREAMPLACE_PLACER = os.environ.get(
    "DREAMPLACE_PLACER",
    "/root/dreamplace_picbench/install/dreamplace/Placer.py",
)
DREAMPLACE_PYTHONPATH = os.environ.get(
    "DREAMPLACE_PYTHONPATH",
    "/root/dreamplace_picbench/install:/root/dreamplace_picbench/install/dreamplace",
)

MARKER_LAYER_BY_CLASS = {
    "component_geometry": (900, 0),
    "pin_access": (901, 0),
    "route_geometry": (902, 0),
}
MARKER_TEXT_LAYER = (903, 0)
PREVIEW_LAYER_COLORS = {
    (1, 0): "#ff4f8b",
    (2, 0): "#7357ff",
    (900, 0): "#ff2f2f",
    (901, 0): "#ff9a1f",
    (902, 0): "#8a4fff",
    (903, 0): "#111111",
}


Endpoint = tuple[str, str]


@dataclass(frozen=True)
class MacroRecord:
    name: str
    component: str
    settings: dict[str, Any]
    width: float
    height: float
    center_x: float
    center_y: float
    pins_lidar: dict[str, dict[str, Any]]
    pins_bookshelf: dict[str, tuple[float, float, str]]


@dataclass(frozen=True)
class InstanceRecord:
    original_name: str
    bookshelf_name: str
    component_token: str
    model_name: str
    macro: MacroRecord


@dataclass(frozen=True)
class TerminalRecord:
    port_name: str
    bookshelf_name: str
    endpoint: str
    direction: str
    x: float
    y: float
    width: float = 1.0
    height: float = 1.0


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_yaml(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=False), encoding="utf-8")


def _sanitize_name(name: str, *, default: str = "picbench") -> str:
    sanitized = re.sub(r"[^0-9A-Za-z_]+", "_", name).strip("_")
    if not sanitized:
        sanitized = default
    if sanitized[0].isdigit():
        sanitized = f"picbench_{sanitized}"
    return sanitized


def _unique_sanitized(names: list[str]) -> dict[str, str]:
    used: dict[str, int] = {}
    result: dict[str, str] = {}
    for name in names:
        base = _sanitize_name(name, default="node")
        index = used.get(base, 0)
        used[base] = index + 1
        result[name] = base if index == 0 else f"{base}_{index}"
    return result


def _parse_endpoint(endpoint: str) -> Endpoint:
    if "," not in endpoint:
        raise ValueError(f"Invalid endpoint {endpoint!r}; expected 'instance,port'.")
    instance, port = endpoint.split(",", 1)
    return instance.strip(), port.strip()


def _instance_component_and_settings(instance_spec: Any) -> tuple[str, dict[str, Any]]:
    if isinstance(instance_spec, str):
        return instance_spec.strip(), {}
    if isinstance(instance_spec, dict):
        component = instance_spec.get("component")
        if not isinstance(component, str):
            raise ValueError(f"Invalid instance spec {instance_spec!r}")
        settings = instance_spec.get("settings") or {}
        if not isinstance(settings, dict):
            raise ValueError(f"Invalid settings for {component!r}: {settings!r}")
        return component.strip(), dict(settings)
    raise ValueError(f"Invalid instance spec {instance_spec!r}")


def _collect_instance_ports(netlist: dict[str, Any]) -> dict[str, set[str]]:
    ports_by_instance = {name: set() for name in netlist["instances"]}
    for src, dst in netlist.get("connections", {}).items():
        for endpoint in (src, dst):
            instance, port = _parse_endpoint(endpoint)
            ports_by_instance.setdefault(instance, set()).add(port)
    for endpoint in netlist.get("ports", {}).values():
        instance, port = _parse_endpoint(endpoint)
        ports_by_instance.setdefault(instance, set()).add(port)
    return ports_by_instance


def _component_from_cell(cell_name: str, settings: dict[str, Any]) -> gf.Component:
    gf_settings = dict(settings)
    if "port_names" in gf_settings and isinstance(gf_settings["port_names"], list):
        gf_settings["port_names"] = tuple(gf_settings["port_names"])
    return gf.get_component(cell_name, settings=gf_settings)


def _component_bounds(component: gf.Component) -> tuple[float, float, float, float]:
    size_info = component.size_info
    return (
        float(size_info.west),
        float(size_info.south),
        float(size_info.east),
        float(size_info.north),
    )


def _pin_direction(port_name: str) -> str:
    return "I" if port_name.upper().startswith("I") else "O"


def _macro_for_component(
    *,
    macro_name: str,
    component_name: str,
    settings: dict[str, Any],
) -> MacroRecord:
    component = _component_from_cell(component_name, settings)
    west, south, east, north = _component_bounds(component)
    width = max(east - west, 1.0)
    height = max(north - south, 1.0)
    center_x = west + width / 2
    center_y = south + height / 2

    pins_lidar: dict[str, dict[str, Any]] = {}
    pins_bookshelf: dict[str, tuple[float, float, str]] = {}
    for port in component.get_ports_list(port_type="optical"):
        pins_lidar[port.name] = {
            "pin_offset_x": float(port.center[0] - west),
            "pin_offset_y": float(port.center[1] - south),
            "pin_width": float(port.width),
            "pin_orient": float(port.orientation),
            "pin_layer": list(port.layer),
        }
        pins_bookshelf[port.name] = (
            float(port.center[0] - center_x),
            float(port.center[1] - center_y),
            _pin_direction(port.name),
        )

    return MacroRecord(
        name=macro_name,
        component=component_name,
        settings=settings,
        width=width,
        height=height,
        center_x=center_x,
        center_y=center_y,
        pins_lidar=pins_lidar,
        pins_bookshelf=pins_bookshelf,
    )


def _build_records(data: dict[str, Any]) -> tuple[list[InstanceRecord], dict[str, str]]:
    register_picbench_cells()

    netlist = data["netlist"]
    models = data.get("models", {})
    ports_by_instance = _collect_instance_ports(netlist)
    name_map = _unique_sanitized(list(netlist["instances"]))

    records: list[InstanceRecord] = []
    for instance_name, instance_spec in netlist["instances"].items():
        component_token, settings = _instance_component_and_settings(instance_spec)
        model_name = models.get(component_token, component_token)
        cell_name = component_name_for_model(model_name)
        cell_settings = dict(settings)
        if cell_name == "picbench_generic":
            cell_settings["port_names"] = sorted(ports_by_instance.get(instance_name, ()))

        macro_name = f"m_{name_map[instance_name]}_{cell_name}"
        macro_name = _sanitize_name(macro_name, default="macro")
        macro = _macro_for_component(
            macro_name=macro_name,
            component_name=cell_name,
            settings=cell_settings,
        )
        records.append(
            InstanceRecord(
                original_name=instance_name,
                bookshelf_name=name_map[instance_name],
                component_token=component_token,
                model_name=model_name,
                macro=macro,
            )
        )

    return records, name_map


def _cell_graph(data: dict[str, Any]) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    instances = list(data["netlist"]["instances"])
    outgoing: dict[str, set[str]] = {name: set() for name in instances}
    incoming: dict[str, set[str]] = {name: set() for name in instances}
    for src, dst in data["netlist"].get("connections", {}).items():
        src_inst, _ = _parse_endpoint(src)
        dst_inst, _ = _parse_endpoint(dst)
        if src_inst == dst_inst or dst_inst in outgoing.setdefault(src_inst, set()):
            continue
        outgoing[src_inst].add(dst_inst)
        incoming.setdefault(dst_inst, set()).add(src_inst)
    return outgoing, incoming


def _raw_topology_levels(data: dict[str, Any]) -> list[list[str]]:
    instances = list(data["netlist"]["instances"])
    outgoing, incoming = _cell_graph(data)
    indegree = {name: len(incoming.get(name, set())) for name in instances}

    port_priority: dict[str, int] = {}
    for index, endpoint in enumerate(data["netlist"].get("ports", {}).values()):
        instance, _ = _parse_endpoint(endpoint)
        current = port_priority.get(instance)
        if current is None or index < current:
            port_priority[instance] = index

    ready = sorted(
        [name for name in instances if indegree.get(name, 0) == 0],
        key=lambda name: (port_priority.get(name, 10_000), name),
    )
    levels: list[list[str]] = []
    visited: set[str] = set()
    while ready:
        level = [name for name in ready if name not in visited]
        if not level:
            break
        levels.append(level)
        next_ready: list[str] = []
        for name in level:
            visited.add(name)
            for dst in sorted(outgoing.get(name, ())):
                indegree[dst] -= 1
                if indegree[dst] == 0:
                    next_ready.append(dst)
        ready = sorted(next_ready, key=lambda name: (port_priority.get(name, 10_000), name))

    remaining = [name for name in instances if name not in visited]
    if remaining:
        levels.append(sorted(remaining))
    return levels or [instances]


def _barycenter_sort_levels(data: dict[str, Any], levels: list[list[str]]) -> list[list[str]]:
    """Sort each topology layer to reduce crossings, using barycenter sweeps."""
    if len(levels) <= 1:
        return levels

    outgoing, incoming = _cell_graph(data)
    sorted_levels = [list(level) for level in levels]

    for _ in range(6):
        for level_index in range(1, len(sorted_levels)):
            prev_pos = {name: index for index, name in enumerate(sorted_levels[level_index - 1])}

            def key_from_prev(name: str) -> tuple[float, str]:
                preds = [prev_pos[pred] for pred in incoming.get(name, set()) if pred in prev_pos]
                bary = sum(preds) / len(preds) if preds else float("inf")
                return bary, name

            sorted_levels[level_index].sort(key=key_from_prev)

        for level_index in range(len(sorted_levels) - 2, -1, -1):
            next_pos = {name: index for index, name in enumerate(sorted_levels[level_index + 1])}

            def key_from_next(name: str) -> tuple[float, str]:
                succs = [next_pos[succ] for succ in outgoing.get(name, set()) if succ in next_pos]
                bary = sum(succs) / len(succs) if succs else float("inf")
                return bary, name

            sorted_levels[level_index].sort(key=key_from_next)

    return sorted_levels


def _topology_levels_original(data: dict[str, Any]) -> list[list[str]]:
    return _barycenter_sort_levels(data, _raw_topology_levels(data))


def _topology_levels(data: dict[str, Any], name_map: dict[str, str]) -> list[list[str]]:
    return [
        [name_map[name] for name in level]
        for level in _topology_levels_original(data)
    ]


def _initial_placements(
    records: list[InstanceRecord],
    levels: list[list[str]],
    *,
    margin: float,
    x_pitch: float = 140.0,
    y_pitch: float = 70.0,
) -> dict[str, tuple[float, float]]:
    by_book = {record.bookshelf_name: record for record in records}
    max_width = max(record.macro.width for record in records)
    max_height = max(record.macro.height for record in records)
    x_step = max(x_pitch, max_width + 95.0)
    y_step = max(y_pitch, max_height + 55.0)
    placements: dict[str, tuple[float, float]] = {}
    for level_index, level in enumerate(levels):
        for row_index, book_name in enumerate(level):
            record = by_book[book_name]
            x = margin + level_index * x_step
            y = margin + (len(level) - 1 - row_index) * y_step
            placements[record.original_name] = (x, y)
    return placements


def _die_size(
    records: list[InstanceRecord],
    placements: dict[str, tuple[float, float]],
    *,
    margin: float,
) -> tuple[float, float]:
    max_x = margin
    max_y = margin
    for record in records:
        x, y = placements[record.original_name]
        max_x = max(max_x, x + record.macro.width + margin)
        max_y = max(max_y, y + record.macro.height + margin)
    return max(max_x, 200.0), max(max_y, 160.0)


def _terminal_records(
    data: dict[str, Any],
    records: list[InstanceRecord],
    placements: dict[str, tuple[float, float]],
    *,
    die_width: float,
    die_height: float,
    margin: float,
) -> list[TerminalRecord]:
    by_original = {record.original_name: record for record in records}
    terminals: list[TerminalRecord] = []
    used_names: set[str] = {record.bookshelf_name for record in records}

    for port_name, endpoint in data["netlist"].get("ports", {}).items():
        instance_name, pin_name = _parse_endpoint(endpoint)
        record = by_original.get(instance_name)
        if record is None:
            continue

        x_inst, y_inst = placements[instance_name]
        pin = record.macro.pins_lidar.get(pin_name)
        pin_y = y_inst + (float(pin["pin_offset_y"]) if pin else record.macro.height / 2.0)
        pin_y = min(max(pin_y, margin), max(margin, die_height - margin))

        is_input = port_name.upper().startswith("I")
        base_name = f"PORT_{_sanitize_name(port_name, default='port')}"
        terminal_name = base_name
        suffix = 1
        while terminal_name in used_names:
            terminal_name = f"{base_name}_{suffix}"
            suffix += 1
        used_names.add(terminal_name)

        terminals.append(
            TerminalRecord(
                port_name=port_name,
                bookshelf_name=terminal_name,
                endpoint=endpoint,
                direction="O" if is_input else "I",
                x=0.0 if is_input else max(0.0, die_width - 1.0),
                y=pin_y,
            )
        )
    return terminals


def _write_bookshelf(
    *,
    design_name: str,
    data: dict[str, Any],
    records: list[InstanceRecord],
    name_map: dict[str, str],
    terminals: list[TerminalRecord],
    initial_placements: dict[str, tuple[float, float]],
    die_width: float,
    die_height: float,
    out_dir: Path,
) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    aux = out_dir / f"{design_name}.aux"
    nodes = out_dir / f"{design_name}.nodes"
    nets = out_dir / f"{design_name}.nets"
    pl = out_dir / f"{design_name}.pl"
    scl = out_dir / f"{design_name}.scl"
    topology = out_dir / f"{design_name}_topology.yml"

    aux.write_text(
        f"RowBasedPlacement : {nodes.name} {nets.name} {pl.name} {scl.name}\n",
        encoding="utf-8",
    )

    node_lines = [
        "UCLA nodes 1.0",
        "",
        f"NumNodes : {len(records) + len(terminals)}",
        f"NumTerminals : {len(terminals)}",
        "",
    ]
    for record in records:
        node_lines.append(
            f"\t{record.bookshelf_name}\t{record.macro.width:g}\t{record.macro.height:g}"
        )
    for terminal in terminals:
        node_lines.append(
            f"\t{terminal.bookshelf_name}\t{terminal.width:g}\t{terminal.height:g}\tterminal"
        )
    nodes.write_text("\n".join(node_lines) + "\n", encoding="utf-8")

    net_lines = ["UCLA nets 1.0", ""]
    connections = list(data["netlist"].get("connections", {}).items())
    terminal_connections = [(terminal.bookshelf_name, terminal) for terminal in terminals]
    net_lines.append(f"NumNets : {len(connections) + len(terminal_connections)}")
    net_lines.append(f"NumPins : {len(connections) * 2 + len(terminal_connections) * 2}")
    net_lines.append("")
    by_original = {record.original_name: record for record in records}
    for index, (src, dst) in enumerate(connections):
        net_lines.append(f"NetDegree : 2   n_{index}")
        for endpoint in (src, dst):
            instance_name, port_name = _parse_endpoint(endpoint)
            record = by_original[instance_name]
            try:
                pin_x, pin_y, direction = record.macro.pins_bookshelf[port_name]
            except KeyError as exc:
                raise KeyError(
                    f"{record.original_name},{port_name} is missing from {record.macro.component}"
                ) from exc
            net_lines.append(
                f"\t{name_map[instance_name]}\t{direction} : {pin_x:g}\t{pin_y:g}"
            )
    net_index = len(connections)
    for _, terminal in terminal_connections:
        instance_name, port_name = _parse_endpoint(terminal.endpoint)
        record = by_original[instance_name]
        pin_x, pin_y, direction = record.macro.pins_bookshelf[port_name]
        net_lines.append(f"NetDegree : 2   p_{net_index}_{terminal.bookshelf_name}")
        if terminal.direction == "O":
            net_lines.append(f"\t{terminal.bookshelf_name}\tO : 0\t0")
            net_lines.append(
                f"\t{name_map[instance_name]}\t{direction} : {pin_x:g}\t{pin_y:g}"
            )
        else:
            net_lines.append(
                f"\t{name_map[instance_name]}\t{direction} : {pin_x:g}\t{pin_y:g}"
            )
            net_lines.append(f"\t{terminal.bookshelf_name}\tI : 0\t0")
        net_index += 1
    nets.write_text("\n".join(net_lines) + "\n", encoding="utf-8")

    pl_lines = ["UCLA pl 1.0", ""]
    for record in records:
        x, y = initial_placements[record.original_name]
        pl_lines.append(f"{record.bookshelf_name} {x:g} {y:g} : N")
    for terminal in terminals:
        pl_lines.append(f"{terminal.bookshelf_name} {terminal.x:g} {terminal.y:g} : N /FIXED")
    pl.write_text("\n".join(pl_lines) + "\n", encoding="utf-8")

    row_height = max(1, math.ceil(max(record.macro.height for record in records)))
    num_rows = max(1, math.ceil(die_height / row_height))
    num_sites = max(1, math.ceil(die_width))
    scl_lines = ["UCLA scl 1.0", "", f"NumRows : {num_rows}", ""]
    for row in range(num_rows):
        y = row * row_height
        scl_lines.extend(
            [
                "CoreRow Horizontal",
                f"  Coordinate    :   {y:g}",
                f"  Height        :   {row_height:g}",
                "  Sitewidth     :   1",
                "  Sitespacing   :   1",
                "  Siteorient    :   1",
                "  Sitesymmetry  :   1",
                f"  SubrowOrigin  :   0\tNumSites  :  {num_sites}",
                "End",
            ]
        )
    scl.write_text("\n".join(scl_lines) + "\n", encoding="utf-8")

    _write_yaml(topology, {"circuit_levels": _topology_levels(data, name_map)})

    return {"aux": aux, "nodes": nodes, "nets": nets, "pl": pl, "scl": scl, "topology": topology}


def _windows_to_wsl_path(path: Path) -> str:
    resolved = path.resolve()
    drive = resolved.drive.rstrip(":").lower()
    parts = [part for part in resolved.parts[1:]]
    return f"/mnt/{drive}/" + "/".join(part.replace("\\", "/") for part in parts)


def _dreamplace_params(
    *,
    aux_path: Path,
    result_dir: Path,
    iterations: int,
    topo_weight: float,
) -> dict[str, Any]:
    return {
        "aux_input": _windows_to_wsl_path(aux_path),
        "gpu": 0,
        "num_bins_x": 32,
        "num_bins_y": 32,
        "global_place_stages": [
            {
                "num_bins_x": 32,
                "num_bins_y": 32,
                "iteration": iterations,
                "learning_rate": 0.01,
                "wirelength": "weighted_average",
                "optimizer": "nesterov",
                "Llambda_density_weight_iteration": 1,
                "Lsub_iteration": 1,
            }
        ],
        "topo_weight": topo_weight,
        "target_density": 0.75,
        "density_weight": 8e-5,
        "random_seed": 1000,
        "result_dir": _windows_to_wsl_path(result_dir),
        "scale_factor": 1.0,
        "shift_factor": [0.0, 0.0],
        "ignore_net_degree": 100,
        "gp_noise_ratio": 0.0,
        "enable_fillers": 0,
        "global_place_flag": 1,
        "legalize_flag": 0,
        "detailed_place_flag": 0,
        "stop_overflow": 0.1,
        "dtype": "float32",
        "detailed_place_engine": "",
        "detailed_place_command": "",
        "plot_flag": 0,
        "gamma": 4.0,
        "random_center_init_flag": 0,
        "gift_init_flag": 0,
        "sort_nets_by_degree": 0,
        "num_threads": 4,
        "deterministic_flag": 1,
    }


def _run_subprocess(
    command: list[str],
    *,
    cwd: Path,
    log_path: Path,
    timeout: int,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            env=env,
            text=True,
            capture_output=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode(errors="replace")
        if isinstance(stderr, bytes):
            stderr = stderr.decode(errors="replace")
        completed = subprocess.CompletedProcess(
            command,
            124,
            stdout,
            f"TIMEOUT after {timeout} seconds\n{stderr}",
        )
    log_path.write_text(
        f"$ {' '.join(command)}\n\n--- stdout ---\n{completed.stdout}\n"
        f"\n--- stderr ---\n{completed.stderr}\n",
        encoding="utf-8",
    )
    return completed


def _run_dreamplace(
    *,
    design_name: str,
    work_dir: Path,
    aux_path: Path,
    timeout: int,
    iterations: int,
    topo_weight: float,
) -> tuple[bool, Path, Path]:
    result_dir = work_dir / "results"
    params = _dreamplace_params(
        aux_path=aux_path,
        result_dir=result_dir,
        iterations=iterations,
        topo_weight=topo_weight,
    )
    params_path = work_dir / f"{design_name}.dreamplace.json"
    params_path.write_text(json.dumps(params, indent=2), encoding="utf-8")

    wsl_work_dir = _windows_to_wsl_path(work_dir)
    wsl_params = _windows_to_wsl_path(params_path)
    command_text = (
        f"cd {shlex.quote(wsl_work_dir)} && "
        f"PYTHONPATH={shlex.quote(DREAMPLACE_PYTHONPATH)} "
        f"python3 {shlex.quote(DREAMPLACE_PLACER)} {shlex.quote(wsl_params)}"
    )
    log_path = work_dir / "dreamplace.log"
    completed = _run_subprocess(
        ["wsl.exe", "-d", DREAMPLACE_WSL_DISTRO, "--", "bash", "-lc", command_text],
        cwd=PICDB_ROOT,
        log_path=log_path,
        timeout=timeout,
    )
    out_pl = result_dir / design_name / f"{design_name}.gp.pl"
    return completed.returncode == 0 and out_pl.exists(), out_pl, log_path


def _parse_pl(path: Path, name_by_bookshelf: dict[str, str]) -> dict[str, tuple[float, float]]:
    placements: dict[str, tuple[float, float]] = {}
    if not path.exists():
        return placements
    pattern = re.compile(r"^(\S+)\s+([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)\s+([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)")
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        match = pattern.match(line.strip())
        if not match:
            continue
        book_name, x_str, y_str = match.groups()
        original = name_by_bookshelf.get(book_name)
        if original:
            placements[original] = (float(x_str), float(y_str))
    return placements


def _spread_overlaps(
    records: list[InstanceRecord],
    placements: dict[str, tuple[float, float]],
    *,
    margin: float,
    gap: float = 25.0,
) -> dict[str, tuple[float, float]]:
    placed_boxes: list[tuple[float, float, float, float]] = []
    output: dict[str, tuple[float, float]] = {}
    by_original = {record.original_name: record for record in records}

    def overlaps(box: tuple[float, float, float, float]) -> bool:
        lx, ly, hx, hy = box
        for ox1, oy1, ox2, oy2 in placed_boxes:
            if lx < ox2 + gap and hx + gap > ox1 and ly < oy2 + gap and hy + gap > oy1:
                return True
        return False

    for name, (x_raw, y_raw) in sorted(placements.items(), key=lambda item: (item[1][0], item[1][1], item[0])):
        record = by_original[name]
        x = max(float(x_raw), margin)
        y = max(float(y_raw), margin)
        attempts = 0
        while True:
            box = (x, y, x + record.macro.width, y + record.macro.height)
            if not overlaps(box):
                break
            attempts += 1
            x += record.macro.width + gap
            if attempts % 8 == 0:
                x = margin
                y += record.macro.height + gap
        placed_boxes.append(box)
        output[name] = (x, y)
    return output


def _scale_placements(
    placements: dict[str, tuple[float, float]],
    *,
    scale_x: float,
    scale_y: float,
    margin: float,
) -> dict[str, tuple[float, float]]:
    if not placements:
        return placements
    min_x = min(x for x, _ in placements.values())
    min_y = min(y for _, y in placements.values())
    return {
        name: (
            margin + (x - min_x) * scale_x,
            margin + (y - min_y) * scale_y,
        )
        for name, (x, y) in placements.items()
    }


def _model_loss(model_name: str) -> float:
    model = model_name.lower()
    if "mmi" in model or "coupler" in model:
        return 0.3
    if "mzi" in model or "mzm" in model or "heater" in model or "straight_heat" in model:
        return 1.2
    if "mrr" in model or "ring" in model:
        return 1.0
    return 0.1


def _lidar_gp(
    *,
    design_name: str,
    data: dict[str, Any],
    records: list[InstanceRecord],
    placements: dict[str, tuple[float, float]],
    die_width: float,
    die_height: float,
) -> dict[str, Any]:
    library: dict[str, Any] = {}
    instances: dict[str, Any] = {}
    for record in records:
        macro = record.macro
        x, y = placements[record.original_name]
        library[macro.name] = {
            "property": None,
            "iloss": _model_loss(record.model_name),
            "type": "CORE",
            "origin": [0, 0],
            "size": [float(macro.width), float(macro.height)],
            "site": "core",
            "pins": macro.pins_lidar,
        }
        instance_settings = dict(macro.settings)
        instance_settings["macro_type"] = macro.name
        instance_settings["placement"] = ["PLACED", [float(x), float(y)], "N", [0, 0, 0, 0]]
        instances[record.original_name] = {
            "component": macro.component,
            "settings": instance_settings,
        }

    nets = {
        f"n_{index}": [_clean_endpoint(src), _clean_endpoint(dst)]
        for index, (src, dst) in enumerate(data["netlist"].get("connections", {}).items())
    }

    return {
        "settings": {
            "version": "1.0",
            "design": design_name,
            "units_distance_microns": 1,
            "die_area": [[0, 0], [float(die_width), float(die_height)]],
            "num_instances": len(instances),
            "num_nets": len(nets),
            "num_ports": len(data["netlist"].get("ports", {})),
            "wg_radius": 5,
        },
        "instances": instances,
        "library": library,
        "nets": nets,
        "ports": {
            port_name.strip(): _clean_endpoint(endpoint)
            for port_name, endpoint in data["netlist"].get("ports", {}).items()
        },
        "constraints": {},
    }


def _clean_endpoint(endpoint: str) -> str:
    instance, port = _parse_endpoint(endpoint)
    return f"{instance},{port}"


def _lidar_config(
    gds_path: Path,
    macro_losses: dict[str, float],
    *,
    route_fast: bool,
    route_grid_resolution: int | None,
    route_max_iterations: int | None,
    route_net_order: str | None,
    route_net_default_bound: int | None,
    route_group: bool | None,
    route_enable_45_neighbor: bool | None,
) -> dict[str, Any]:
    max_iteration = 1 if route_fast else 5
    grid_resolution = 5 if route_fast else 2
    net_order = "naive" if route_fast else "topo"
    group = False if route_fast else True
    enable_45_neighbor = False if route_fast else True
    if route_grid_resolution is not None:
        grid_resolution = route_grid_resolution
    if route_max_iterations is not None:
        max_iteration = route_max_iterations
    if route_net_order is not None:
        net_order = route_net_order
    net_default_bound = 100 if route_net_default_bound is None else route_net_default_bound
    if route_group is not None:
        group = route_group
    if route_enable_45_neighbor is not None:
        enable_45_neighbor = route_enable_45_neighbor
    return {
        "run": {
            "random_state": 42,
            "output_layout_gds_path": str(gds_path.resolve()),
        },
        "dr": {
            "router": "GridRoute",
            "maxIteration": max_iteration,
            "net_order": net_order,
            "group": group,
            "enable_45_neighbor": enable_45_neighbor,
            "historyCost": 1000,
            "ripup_times": max_iteration,
            "grid_resolution": grid_resolution,
            "bend_radius": 5,
            "net_bound_scale_factor": 1.5,
            "net_default_bound": net_default_bound,
            "loss_propagation": 1.5,
            "loss_bending": 50,
            "loss_crossing": 200,
            "loss_congestion": 500,
            "loss_cr": 0.52,
            "loss_pp": 0.00015,
            "loss_bend": 0.005,
            "loss_comp": macro_losses,
        },
        "show_temp": False,
        "eval": "comp",
        "il_cross": 0.52,
        "il_propogation": 1.5,
        "il_bending": 50,
    }


def _python_env_with_adapters() -> dict[str, str]:
    env = os.environ.copy()
    adapter_paths = [str(SCRIPT_DIR.resolve()), str((PICBENCH_ROOT / "PICBench").resolve())]
    env["PICBENCH_PYTHONPATH"] = os.pathsep.join(adapter_paths)
    env["PYTHONPATH"] = os.pathsep.join(
        adapter_paths + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else [])
    )
    if LIDAR_SRC.exists():
        env.setdefault("PICDB_LIDAR_SRC", str(LIDAR_SRC.resolve()))
    return env


def _native_lidar_route_args(
    *,
    route_fast: bool,
    route_grid_resolution: int | None,
    route_max_iterations: int | None,
    route_net_order: str | None,
    route_net_default_bound: int | None,
    route_group: bool | None,
    route_enable_45_neighbor: bool | None,
) -> list[str]:
    args: list[str] = []
    if route_fast:
        args.extend(
            [
                "--grid-resolution=5",
                "--max-iteration=1",
                "--net-order=naive",
                "--no-route-group",
                "--disable-45-neighbor",
            ]
        )
    if route_grid_resolution is not None:
        args.append(f"--grid-resolution={route_grid_resolution}")
    if route_max_iterations is not None:
        args.append(f"--max-iteration={route_max_iterations}")
    if route_net_order is not None:
        args.append(f"--net-order={route_net_order}")
    if route_net_default_bound is not None:
        args.append(f"--net-default-bound={route_net_default_bound}")
    if route_group is not None:
        args.append("--route-group" if route_group else "--no-route-group")
    if route_enable_45_neighbor is not None:
        args.append(
            "--enable-45-neighbor"
            if route_enable_45_neighbor
            else "--disable-45-neighbor"
        )
    return args


def _run_cpp_lidar(
    *,
    benchmark_path: Path,
    gds_path: Path,
    log_path: Path,
    timeout: int,
    route_fast: bool,
    route_grid_resolution: int | None,
    route_max_iterations: int | None,
    route_net_order: str | None,
    route_net_default_bound: int | None,
    route_group: bool | None,
    route_enable_45_neighbor: bool | None,
) -> subprocess.CompletedProcess[str]:
    route_args = _native_lidar_route_args(
        route_fast=route_fast,
        route_grid_resolution=route_grid_resolution,
        route_max_iterations=route_max_iterations,
        route_net_order=route_net_order,
        route_net_default_bound=route_net_default_bound,
        route_group=route_group,
        route_enable_45_neighbor=route_enable_45_neighbor,
    )
    return _run_subprocess(
        [str(NATIVE_LIDAR), str(benchmark_path), str(gds_path), *route_args],
        cwd=PICDB_ROOT,
        log_path=log_path,
        timeout=timeout,
        env=_python_env_with_adapters(),
    )


def _run_python_lidar(
    *,
    benchmark_path: Path,
    config_path: Path,
    log_path: Path,
    timeout: int,
) -> subprocess.CompletedProcess[str]:
    return _run_subprocess(
        [sys.executable, str(LIDAR_MAIN), "--benchmark", str(benchmark_path), "--config", str(config_path)],
        cwd=PICDB_ROOT,
        log_path=log_path,
        timeout=timeout,
        env=_python_env_with_adapters(),
    )


def _picdb_flow_dir_for_gds(gds_path: Path) -> Path:
    return gds_path.parent / f"{gds_path.stem}_picdb_flow"


def _parse_marker_fields(line: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for part in line.rstrip("\n").split("\t")[1:]:
        if "=" in part:
            key, value = part.split("=", 1)
            fields[key] = value
    return fields


def _parse_db_drc_summary(path: Path) -> tuple[dict[str, str], list[dict[str, str]]]:
    summary: dict[str, str] = {}
    markers: list[dict[str, str]] = []
    if not path.exists() or not path.is_file():
        return summary, markers
    for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("marker\t"):
            markers.append(_parse_marker_fields(line))
        elif "\t" not in line and "=" in line:
            key, value = line.split("=", 1)
            summary[key] = value
    return summary, markers


def _float_field(marker: dict[str, str], name: str, default: float = 0.0) -> float:
    try:
        return float(marker.get(name, default))
    except (TypeError, ValueError):
        return default


def _marker_bbox(marker: dict[str, str], marker_size_um: float) -> tuple[float, float, float, float]:
    bbox_text = marker.get("bbox", "")
    if bbox_text:
        try:
            x1, y1, x2, y2 = [float(part) for part in bbox_text.split(",", 3)]
            if abs(x2 - x1) > 1e-9 or abs(y2 - y1) > 1e-9:
                return x1, y1, x2, y2
        except ValueError:
            pass
    x = _float_field(marker, "x")
    y = _float_field(marker, "y")
    half = marker_size_um / 2.0
    return x - half, y - half, x + half, y + half


def _copy_gds_with_drc_markers(
    *,
    base_gds: Path,
    drc_summary: Path,
    out_gds: Path,
    marker_size_um: float,
) -> tuple[bool, dict[str, str], int]:
    summary, markers = _parse_db_drc_summary(drc_summary)
    if not base_gds.exists():
        return False, summary, len(markers)
    out_gds.parent.mkdir(parents=True, exist_ok=True)
    if not markers:
        shutil.copy2(base_gds, out_gds)
        return True, summary, 0

    import klayout.db as pya

    layout = pya.Layout()
    layout.read(str(base_gds))
    top = layout.top_cell()
    if top is None:
        shutil.copy2(base_gds, out_gds)
        return True, summary, len(markers)

    def to_dbu(value_um: float) -> int:
        return int(round(value_um / layout.dbu))

    text_layer = layout.layer(*MARKER_TEXT_LAYER)
    for index, marker in enumerate(markers, start=1):
        marker_class = marker.get("class", "")
        layer_info = MARKER_LAYER_BY_CLASS.get(marker_class, (904, 0))
        layer_index = layout.layer(*layer_info)
        x1, y1, x2, y2 = _marker_bbox(marker, marker_size_um)
        box = pya.Box(to_dbu(x1), to_dbu(y1), to_dbu(x2), to_dbu(y2))
        top.shapes(layer_index).insert(box)
        label = f"{index}:{marker.get('type', 'drc')} {marker.get('nets', '')}".strip()
        text = pya.Text(label, pya.Trans(pya.Point(to_dbu(x1), to_dbu(y2 + marker_size_um))))
        top.shapes(text_layer).insert(text)

    layout.write(str(out_gds))
    return True, summary, len(markers)


def _shape_polygons_um(shape: Any, dbu: float) -> list[list[tuple[float, float]]]:
    polygons: list[list[tuple[float, float]]] = []
    if shape.is_box():
        box = shape.box
        polygons.append(
            [
                (box.left * dbu, box.bottom * dbu),
                (box.right * dbu, box.bottom * dbu),
                (box.right * dbu, box.top * dbu),
                (box.left * dbu, box.top * dbu),
            ]
        )
    elif shape.is_polygon():
        polygon = shape.polygon
        polygons.append([(point.x * dbu, point.y * dbu) for point in polygon.each_point_hull()])
    elif shape.is_path():
        polygon = shape.path.polygon()
        polygons.append([(point.x * dbu, point.y * dbu) for point in polygon.each_point_hull()])
    return polygons


def _render_gds_preview(
    *,
    gds_path: Path,
    out_png: Path,
    title: str,
    status: str,
    size: tuple[int, int] = (520, 420),
) -> bool:
    if not gds_path.exists() or not gds_path.is_file():
        return False
    import klayout.db as pya
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Polygon as MplPolygon

    layout = pya.Layout()
    layout.read(str(gds_path))
    top = layout.top_cell()
    if top is None:
        return False

    fig_w = size[0] / 100.0
    fig_h = size[1] / 100.0
    fig, ax = plt.subplots(figsize=(fig_w, fig_h), dpi=100)
    ax.set_facecolor("#faf8f4")
    fig.patch.set_facecolor("#faf8f4")

    bbox = top.bbox()
    has_geometry = not bbox.empty()
    if has_geometry:
        ax.set_xlim(bbox.left * layout.dbu, bbox.right * layout.dbu)
        ax.set_ylim(bbox.bottom * layout.dbu, bbox.top * layout.dbu)
    drawn = 0
    for layer_index in layout.layer_indexes():
        layer_info = layout.get_info(layer_index)
        layer_key = (layer_info.layer, layer_info.datatype)
        color = PREVIEW_LAYER_COLORS.get(layer_key)
        if color is None:
            if layer_info.layer >= 900:
                color = "#d62728"
            else:
                color = "#ff6f9f"
        alpha = 0.75 if layer_info.layer < 900 else 0.95
        iterator = top.begin_shapes_rec(layer_index)
        while not iterator.at_end():
            shape = iterator.shape()
            for polygon in _shape_polygons_um(shape, layout.dbu):
                if len(polygon) >= 3:
                    ax.add_patch(
                        MplPolygon(
                            polygon,
                            closed=True,
                            facecolor=color,
                            edgecolor=color,
                            linewidth=0.25 if layer_info.layer < 900 else 1.2,
                            alpha=alpha,
                        )
                    )
                    drawn += 1
            iterator.next()
    if has_geometry:
        ax.set_aspect("equal", adjustable="box")
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_title(f"{title}\n{status}", fontsize=10, color="#1d1d1f")
    for spine in ax.spines.values():
        spine.set_color("#d0ccc4")
        spine.set_linewidth(0.8)
    if drawn == 0:
        ax.text(0.5, 0.5, "no geometry", ha="center", va="center", transform=ax.transAxes)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout(pad=0.35)
    fig.savefig(out_png)
    plt.close(fig)
    return True


def _compose_summary_image(
    *,
    manifest: list[dict[str, Any]],
    out_png: Path,
    previews_dir: Path,
    tile_size: tuple[int, int] = (520, 420),
) -> bool:
    from PIL import Image, ImageDraw, ImageFont

    preview_paths: list[Path] = []
    for result in manifest:
        case = result.get("case", "case")
        safe_case = _sanitize_name(str(case))
        source_text = result.get("drc_gds") or result.get("gds")
        if not source_text:
            continue
        source_gds = Path(source_text)
        status = (
            f"place={'OK' if result.get('dreamplace_ok') else 'FAIL'} "
            f"route={'OK' if result.get('lidar_ok') else 'FAIL'} "
            f"drc={'OK' if result.get('db_drc_clean') else 'FAIL'}"
        )
        preview = previews_dir / f"{safe_case}.png"
        if _render_gds_preview(gds_path=source_gds, out_png=preview, title=str(case), status=status, size=tile_size):
            preview_paths.append(preview)

    if not preview_paths:
        return False

    cols = max(1, math.ceil(math.sqrt(len(preview_paths))))
    rows = math.ceil(len(preview_paths) / cols)
    header_h = 54
    width = cols * tile_size[0]
    height = rows * tile_size[1] + header_h
    canvas = Image.new("RGB", (width, height), "#f4efe7")
    draw = ImageDraw.Draw(canvas)
    try:
        font = ImageFont.truetype("arial.ttf", 24)
        small_font = ImageFont.truetype("arial.ttf", 15)
    except OSError:
        font = ImageFont.load_default()
        small_font = ImageFont.load_default()
    clean_count = sum(1 for item in manifest if item.get("db_drc_clean"))
    routed_count = sum(1 for item in manifest if item.get("lidar_ok"))
    draw.text((18, 10), "PICBench PIC-DB DREAMPlace + C++ LiDAR Summary", fill="#1f1a17", font=font)
    draw.text(
        (18, 36),
        f"cases={len(manifest)} routed={routed_count} db_drc_clean={clean_count}",
        fill="#5f5850",
        font=small_font,
    )
    for index, preview in enumerate(preview_paths):
        row = index // cols
        col = index % cols
        image = Image.open(preview).convert("RGB")
        canvas.paste(image, (col * tile_size[0], header_h + row * tile_size[1]))
    out_png.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out_png)
    return True


def _find_case_ref(case: str, testcases_dir: Path) -> Path:
    direct = testcases_dir / case / f"{case}_ref.json"
    if direct.exists():
        return direct
    safe_case = _sanitize_name(case)
    for ref in sorted(testcases_dir.glob("*/*_ref.json")):
        if ref.parent.name == case or _sanitize_name(ref.parent.name) == safe_case:
            return ref
    raise FileNotFoundError(f"Could not find PICBench case {case!r} under {testcases_dir}")


def _iter_case_refs(testcases_dir: Path) -> list[Path]:
    return sorted(testcases_dir.glob("*/*_ref.json"), key=lambda path: _sanitize_name(path.parent.name))


def run_case(
    ref_path: Path,
    *,
    output_root: Path,
    output_gds: Path | None,
    drc_gds_dir: Path | None,
    drc_marker_size: float,
    router: str,
    dreamplace_timeout: int,
    lidar_timeout: int,
    dreamplace_iterations: int,
    topo_weight: float,
    route_fast: bool,
    route_grid_resolution: int | None,
    route_max_iterations: int | None,
    route_net_order: str | None,
    route_net_default_bound: int | None,
    route_group: bool | None,
    route_enable_45_neighbor: bool | None,
    fixed_terminals: bool,
    placement_scale_x: float,
    placement_scale_y: float,
) -> dict[str, Any]:
    output_root = output_root.resolve()
    case_name = ref_path.parent.name
    design_name = _sanitize_name(case_name)
    case_dir = output_root / design_name
    dreamplace_dir = case_dir / "dreamplace"
    lidar_dir = case_dir / "lidar"
    if output_gds is not None:
        gds_path = output_gds.resolve()
        gds_path.parent.mkdir(parents=True, exist_ok=True)
    else:
        gds_dir = output_root / "gds"
        gds_path = gds_dir / f"{design_name}.gds"
        gds_dir.mkdir(parents=True, exist_ok=True)

    data = _read_json(ref_path)
    records, name_map = _build_records(data)
    levels = _topology_levels(data, name_map)
    effective_topo_weight = topo_weight if any(len(level) > 1 for level in levels) else -1.0
    initial = _initial_placements(records, levels, margin=40.0)
    die_width, die_height = _die_size(records, initial, margin=80.0)
    terminals = (
        _terminal_records(
            data,
            records,
            initial,
            die_width=die_width,
            die_height=die_height,
            margin=40.0,
        )
        if fixed_terminals
        else []
    )

    bookshelf_paths = _write_bookshelf(
        design_name=design_name,
        data=data,
        records=records,
        name_map=name_map,
        terminals=terminals,
        initial_placements=initial,
        die_width=die_width,
        die_height=die_height,
        out_dir=dreamplace_dir,
    )

    dreamplace_ok, dreamplace_pl, dreamplace_log = _run_dreamplace(
        design_name=design_name,
        work_dir=dreamplace_dir,
        aux_path=bookshelf_paths["aux"],
        timeout=dreamplace_timeout,
        iterations=dreamplace_iterations,
        topo_weight=effective_topo_weight,
    )

    name_by_bookshelf = {book: original for original, book in name_map.items()}
    dreamplace_placements = _parse_pl(dreamplace_pl, name_by_bookshelf) if dreamplace_ok else {}
    placement_source = "dreamplace"
    if len(dreamplace_placements) != len(records):
        dreamplace_placements = initial
        placement_source = "initial_fallback"
    dreamplace_placements = _scale_placements(
        dreamplace_placements,
        scale_x=placement_scale_x,
        scale_y=placement_scale_y,
        margin=40.0,
    )
    placements = _spread_overlaps(records, dreamplace_placements, margin=40.0)
    die_width, die_height = _die_size(records, placements, margin=100.0)

    gp = _lidar_gp(
        design_name=design_name,
        data=data,
        records=records,
        placements=placements,
        die_width=die_width,
        die_height=die_height,
    )
    gp_path = lidar_dir / f"{design_name}.gp.yml"
    _write_yaml(gp_path, gp)

    macro_losses = {
        record.macro.name: _model_loss(record.model_name)
        for record in records
    }
    config_path = lidar_dir / f"{design_name}.route.yml"
    _write_yaml(
        config_path,
        _lidar_config(
            gds_path,
            macro_losses,
            route_fast=route_fast,
            route_grid_resolution=route_grid_resolution,
            route_max_iterations=route_max_iterations,
            route_net_order=route_net_order,
            route_net_default_bound=route_net_default_bound,
            route_group=route_group,
            route_enable_45_neighbor=route_enable_45_neighbor,
        ),
    )

    lidar_log = lidar_dir / "lidar.log"
    if router == "cpp":
        lidar_completed = _run_cpp_lidar(
            benchmark_path=gp_path,
            gds_path=gds_path,
            log_path=lidar_log,
            timeout=lidar_timeout,
            route_fast=route_fast,
            route_grid_resolution=route_grid_resolution,
            route_max_iterations=route_max_iterations,
            route_net_order=route_net_order,
            route_net_default_bound=route_net_default_bound,
            route_group=route_group,
            route_enable_45_neighbor=route_enable_45_neighbor,
        )
    elif router == "python":
        lidar_completed = _run_python_lidar(
            benchmark_path=gp_path,
            config_path=config_path,
            log_path=lidar_log,
            timeout=lidar_timeout,
        )
    else:
        raise ValueError(f"Unsupported LiDAR router backend: {router}")

    picdb_flow_dir = _picdb_flow_dir_for_gds(gds_path) if router == "cpp" else None
    db_drc_summary = (
        picdb_flow_dir / "cpp" / "db_drc_summary.txt"
        if picdb_flow_dir is not None
        else None
    )
    db_drc_data: dict[str, str] = {}
    db_drc_markers = 0
    drc_gds_path: Path | None = None
    if db_drc_summary is not None:
        db_drc_data, db_drc_marker_list = _parse_db_drc_summary(db_drc_summary)
        db_drc_markers = len(db_drc_marker_list)
    if drc_gds_dir is not None and gds_path.exists():
        drc_gds_path = drc_gds_dir / f"{design_name}_with_drc.gds"
        _, copied_drc_data, copied_marker_count = _copy_gds_with_drc_markers(
            base_gds=gds_path,
            drc_summary=db_drc_summary or Path(),
            out_gds=drc_gds_path,
            marker_size_um=drc_marker_size,
        )
        if copied_drc_data:
            db_drc_data = copied_drc_data
        db_drc_markers = copied_marker_count

    result = {
        "case": case_name,
        "design": design_name,
        "ref_json": str(ref_path),
        "instances": len(records),
        "nets": len(data["netlist"].get("connections", {})),
        "dreamplace_ok": dreamplace_ok,
        "dreamplace_log": str(dreamplace_log),
        "dreamplace_pl": str(dreamplace_pl),
        "placement_source": placement_source,
        "topo_weight": topo_weight,
        "effective_topo_weight": effective_topo_weight,
        "fixed_terminals_enabled": fixed_terminals,
        "fixed_terminals": len(terminals),
        "router": router,
        "native_lidar": str(NATIVE_LIDAR),
        "lidar_src": str(LIDAR_SRC),
        "route_fast": route_fast,
        "route_grid_resolution": route_grid_resolution,
        "route_max_iterations": route_max_iterations,
        "route_net_order": route_net_order,
        "route_net_default_bound": route_net_default_bound,
        "route_group": route_group,
        "route_enable_45_neighbor": route_enable_45_neighbor,
        "placement_scale_x": placement_scale_x,
        "placement_scale_y": placement_scale_y,
        "lidar_ok": lidar_completed.returncode == 0 and gds_path.exists(),
        "lidar_returncode": lidar_completed.returncode,
        "lidar_gp_yml": str(gp_path),
        "lidar_config": str(config_path),
        "lidar_log": str(lidar_log),
        "gds": str(gds_path),
        "picdb_flow_dir": str(picdb_flow_dir) if picdb_flow_dir is not None else None,
        "db_drc_summary": str(db_drc_summary) if db_drc_summary is not None else None,
        "db_drc_clean": (
            db_drc_data.get("clean") == "1" if db_drc_data else None
        ),
        "db_drc_markers": db_drc_markers,
        "drc_gds": str(drc_gds_path) if drc_gds_path is not None else None,
    }
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def main() -> None:
    global NATIVE_LIDAR

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", nargs="?", default="MZM", help="PICBench case name; ignored with --all.")
    parser.add_argument("--ref-json", type=Path, help="Run one PICBench *_ref.json file directly.")
    parser.add_argument("--all", action="store_true", help="Run all PICBench *_ref.json cases.")
    parser.add_argument("--max-cases", type=int, help="Limit number of cases when using --all.")
    parser.add_argument("--testcases-dir", type=Path, default=PICBENCH_ROOT / "testcases")
    parser.add_argument("--output-root", type=Path, default=PICBENCH_ROOT / "picdb_flow")
    parser.add_argument("--output-gds", type=Path, help="Final GDS path for a single-case run.")
    parser.add_argument(
        "--router",
        choices=["cpp", "python"],
        default="cpp",
        help="LiDAR backend. 'cpp' calls PIC-DB pr_lidar_native; 'python' calls picroute.py.",
    )
    parser.add_argument("--dreamplace-timeout", type=int, default=240)
    parser.add_argument("--lidar-timeout", type=int, default=360)
    parser.add_argument("--dreamplace-iterations", type=int, default=40)
    parser.add_argument("--topo-weight", type=float, default=1e-3)
    parser.add_argument("--route-fast", action="store_true", help="Use coarser, lower-iteration LiDAR settings.")
    parser.add_argument("--route-grid-resolution", type=int)
    parser.add_argument("--route-max-iterations", type=int)
    parser.add_argument("--route-net-order", choices=["topo", "naive", "custom"])
    parser.add_argument("--route-net-default-bound", type=int)
    parser.add_argument("--route-group", action=argparse.BooleanOptionalAction)
    parser.add_argument("--route-enable-45-neighbor", action=argparse.BooleanOptionalAction)
    parser.add_argument("--fixed-terminals", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--placement-scale-x", type=float, default=1.0)
    parser.add_argument("--placement-scale-y", type=float, default=1.0)
    parser.add_argument("--drc-gds-dir", type=Path, help="Directory for routed GDS files with DB DRC markers.")
    parser.add_argument("--no-drc-gds", action="store_true", help="Do not collect marker-annotated GDS files.")
    parser.add_argument("--drc-marker-size", type=float, default=8.0, help="Marker box size in microns for point DRC markers.")
    parser.add_argument("--summary-image", type=Path, help="Output PNG mosaic summarizing all routed/DRC GDS results.")
    parser.add_argument("--preview-dir", type=Path, help="Directory for per-case preview PNG tiles.")
    parser.add_argument("--no-summary-image", action="store_true", help="Do not render the summary mosaic image.")
    parser.add_argument("--native-lidar", type=Path, default=NATIVE_LIDAR)
    args = parser.parse_args()

    NATIVE_LIDAR = args.native_lidar.resolve()

    if not PICDB_ROOT.exists():
        raise SystemExit(f"PIC-DB checkout not found at {PICDB_ROOT}")
    if args.ref_json is None and not PICBENCH_ROOT.exists():
        raise SystemExit(
            f"PICBench root not found at {PICBENCH_ROOT}; set PICBENCH_ROOT."
        )
    if args.router == "cpp" and not NATIVE_LIDAR.exists():
        raise SystemExit(
            f"pr_lidar_native not found at {NATIVE_LIDAR}; build it or set PICDB_NATIVE_LIDAR."
        )
    if args.router == "python" and not LIDAR_MAIN.exists():
        raise SystemExit(f"LiDAR entry point not found at {LIDAR_MAIN}")

    args.output_root.mkdir(parents=True, exist_ok=True)
    args.output_root = args.output_root.resolve()
    drc_gds_dir = None if args.no_drc_gds else (args.drc_gds_dir or args.output_root / "drc_gds").resolve()
    summary_image = None if args.no_summary_image else (args.summary_image or args.output_root / "summary.png").resolve()
    preview_dir = (args.preview_dir or args.output_root / "previews").resolve()
    if drc_gds_dir is not None:
        drc_gds_dir.mkdir(parents=True, exist_ok=True)
    if summary_image is not None:
        preview_dir.mkdir(parents=True, exist_ok=True)
    if args.ref_json is not None:
        refs = [args.ref_json.resolve()]
    elif args.all:
        refs = _iter_case_refs(args.testcases_dir)
    else:
        case_as_path = Path(args.case)
        if case_as_path.suffix.lower() == ".json" and case_as_path.exists():
            refs = [case_as_path.resolve()]
        else:
            refs = [_find_case_ref(args.case, args.testcases_dir)]
    if args.max_cases is not None:
        refs = refs[: args.max_cases]
    if args.output_gds is not None and len(refs) != 1:
        raise SystemExit("--output-gds can only be used with a single case/ref JSON")

    manifest = []
    for ref in refs:
        print(f"=== {ref.parent.name} ===", flush=True)
        try:
            result = run_case(
                ref,
                output_root=args.output_root,
                output_gds=args.output_gds,
                drc_gds_dir=drc_gds_dir,
                drc_marker_size=args.drc_marker_size,
                router=args.router,
                dreamplace_timeout=args.dreamplace_timeout,
                lidar_timeout=args.lidar_timeout,
                dreamplace_iterations=args.dreamplace_iterations,
                topo_weight=args.topo_weight,
                route_fast=args.route_fast,
                route_grid_resolution=args.route_grid_resolution,
                route_max_iterations=args.route_max_iterations,
                route_net_order=args.route_net_order,
                route_net_default_bound=args.route_net_default_bound,
                route_group=args.route_group,
                route_enable_45_neighbor=args.route_enable_45_neighbor,
                fixed_terminals=args.fixed_terminals,
                placement_scale_x=args.placement_scale_x,
                placement_scale_y=args.placement_scale_y,
            )
        except Exception as exc:
            result = {
                "case": ref.parent.name,
                "ref_json": str(ref),
                "error": repr(exc),
                "dreamplace_ok": False,
                "lidar_ok": False,
            }
            print(f"ERROR {ref.parent.name}: {exc}", flush=True)
        manifest.append(result)
        print(
            f"{result.get('case')}: dreamplace={result.get('dreamplace_ok')} "
            f"lidar={result.get('lidar_ok')} gds={result.get('gds')}",
            flush=True,
        )

    manifest_path = args.output_root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    ok_count = sum(1 for item in manifest if item.get("lidar_ok"))
    print(f"wrote {manifest_path} ({ok_count}/{len(manifest)} routed)")
    if summary_image is not None:
        if _compose_summary_image(manifest=manifest, out_png=summary_image, previews_dir=preview_dir):
            print(f"wrote {summary_image}")
        else:
            print(f"summary image skipped: no previewable GDS files under {args.output_root}")
    if drc_gds_dir is not None:
        print(f"drc_gds_dir={drc_gds_dir}")


if __name__ == "__main__":
    main()
