import argparse
import copy
import hashlib
import inspect
import json
import re
import sys
import traceback
from pathlib import Path

import yaml


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


def load_lidar_yaml(path: Path):
    text = normalize_legacy_python_yaml_tags(path.read_text())
    try:
        return yaml.full_load(text)
    except yaml.YAMLError:
        return yaml.unsafe_load(text)


def register_optional_gdsfactory_adapters():
    try:
        from gdsfactory_adapters import register_picbench_cells

        register_picbench_cells()
    except Exception:
        pass


def make_lidar_db_config(lidar_src, lidar_data):
    from picroute.config.config import Config

    config = Config()
    for config_name in ("comp_LiDAR.yml", "default_config.yml"):
        config_path = lidar_src / "picroute" / "config" / config_name
        if config_path.exists():
            config.load(str(config_path), recursive=False)
            break

    dr_config = config.setdefault("dr", Config())
    if not isinstance(dr_config, Config):
        dr_config = Config(dr_config)
        config["dr"] = dr_config

    loss_comp = dr_config.setdefault("loss_comp", Config())
    if not isinstance(loss_comp, dict):
        loss_comp = Config()
        dr_config["loss_comp"] = loss_comp

    for macro_name in (lidar_data.get("library", {}) or {}).keys():
        loss_comp.setdefault(macro_name, 0.0)
    for instance in (lidar_data.get("instances", {}) or {}).values():
        settings = instance.get("settings", {}) or {}
        macro_type = settings.get("macro_type")
        if macro_type:
            loss_comp.setdefault(macro_type, 0.0)
    return config


def to_float(value):
    return float(value)


def orientation_to_picdb(orientation):
    orientation = str(orientation or "N").upper()
    mapping = {
        "N": (0.0, False),
        "W": (90.0, False),
        "S": (180.0, False),
        "E": (270.0, False),
        "FN": (0.0, True),
        "FW": (90.0, True),
        "FS": (180.0, True),
        "FE": (270.0, True),
    }
    if orientation not in mapping:
        raise ValueError(f"Unsupported LiDAR orientation: {orientation}")
    return mapping[orientation]


def pin_xsection(pin_name, pin_width):
    if str(pin_name).lower().startswith(("o", "i")):
        return "strip"
    if float(pin_width) <= 1.0:
        return "metal1"
    return "metal1"


def macro_size(library, macro_type, instance_node):
    if macro_type in library:
        return [to_float(value) for value in library[macro_type]["size"]]
    settings = instance_node.get("settings", {}) or {}
    if "size" in settings:
        return [to_float(value) for value in settings["size"]]
    raise KeyError(f"Macro '{macro_type}' is not in library and has no size")


def placement_tuple(instance_node):
    settings = instance_node.get("settings", {}) or {}
    placement = settings.get("placement")
    if not placement or len(placement) < 3:
        raise ValueError("LiDAR instance is missing settings.placement")
    status = placement[0]
    lower_left = placement[1]
    orientation = placement[2]
    return status, [to_float(lower_left[0]), to_float(lower_left[1])], orientation


def oriented_size(width, height, orientation):
    orientation = str(orientation or "N").upper()
    if orientation in {"E", "W", "FE", "FW"}:
        return height, width
    return width, height


def snap_gdsfactory_dbu(value):
    return round(float(value) * 1000.0) / 1000.0


def placement_rotation_and_mirror(orientation):
    rotation, mirror = orientation_to_picdb(orientation)
    return rotation, mirror


def clean_none_values(value):
    if isinstance(value, dict):
        return {
            key: clean_none_values(child)
            for key, child in value.items()
            if child is not None
        }
    if isinstance(value, list):
        return [clean_none_values(child) for child in value]
    return value


def sanitized_component_settings(gf, component, settings):
    settings = clean_none_values(copy.deepcopy(settings or {}))
    settings.pop("placement", None)
    settings.pop("macro_type", None)

    if settings.get("cross_section") == "xs_sc":
        settings["cross_section"] = "strip"
    if isinstance(settings.get("cross_section"), dict):
        settings["cross_section"] = (
            "rib" if str(component).startswith("ring_") else "strip"
        )
    if isinstance(settings.get("pn_cross_section"), dict):
        settings.pop("pn_cross_section", None)
    if str(component).startswith("ring_") and isinstance(
        settings.get("heater_vias"), dict
    ):
        settings.pop("heater_vias", None)

    factory = gf.get_active_pdk().cells.get(component)
    if factory is None:
        return settings
    signature = inspect.signature(factory)
    if any(
        parameter.kind == inspect.Parameter.VAR_KEYWORD
        for parameter in signature.parameters.values()
    ):
        return settings
    allowed = {
        name
        for name, parameter in signature.parameters.items()
        if parameter.kind
        not in {
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        }
    }
    for key in list(settings.keys()):
        if key not in allowed:
            settings.pop(key, None)
    return settings


def port_width_um(port, default=0.5):
    for attr in ("dwidth", "width"):
        value = getattr(port, attr, None)
        if value is None:
            continue
        width = float(value)
        if attr == "width" and width > 10:
            width /= 1000.0
        return width
    return default


def port_center_um(port):
    center = getattr(port, "dcenter", None)
    if center is None:
        center = getattr(port, "center")
    return [float(center[0]), float(center[1])]


def port_layer_list(port):
    layer = getattr(port, "layer", (1, 0))
    if isinstance(layer, (list, tuple)):
        return list(layer)
    return [int(layer), 0]


def component_bounds_um(component):
    info = getattr(component, "dsize_info", None)
    if info is not None:
        return (
            float(info.west),
            float(info.south),
            float(info.east),
            float(info.north),
        )
    info = getattr(component, "size_info", None)
    if info is not None:
        return (
            float(info.west),
            float(info.south),
            float(info.east),
            float(info.north),
        )
    if hasattr(component, "bbox"):
        bbox = component.bbox
        if hasattr(bbox, "reshape"):
            bbox = bbox.reshape(-1)
        values = [float(value) for value in bbox]
        if len(values) == 4:
            return values[0], values[1], values[2], values[3]
    size = getattr(component, "size", None)
    if size is not None and len(size) >= 2:
        return 0.0, 0.0, float(size[0]), float(size[1])
    raise ValueError(f"Cannot determine bbox for component {component!r}")


def iter_optical_ports(component):
    if hasattr(component, "get_ports_list"):
        ports = component.get_ports_list(port_type="optical")
        if ports:
            return [(port.name, port) for port in ports]
    ports = iter_named_ports(component.ports)
    optical = [
        (name, port)
        for name, port in ports
        if getattr(port, "port_type", "optical") == "optical"
        or str(name).lower().startswith("o")
    ]
    return optical


def realize_instance_component(instance_node):
    try:
        import gdsfactory as gf
    except Exception:
        return None
    register_optional_gdsfactory_adapters()

    component_name = instance_node.get("component")
    if not component_name:
        return None

    settings = copy.deepcopy(instance_node.get("settings", {}) or {})
    if "parameters" in instance_node:
        settings.update(copy.deepcopy(instance_node["parameters"]))
    settings = sanitized_component_settings(gf, component_name, settings)

    try:
        component = gf.get_component(component_name, **settings)
    except Exception:
        return None

    try:
        west, south, east, north = component_bounds_um(component)
    except Exception:
        return None
    width = east - west
    height = north - south
    if width <= 0 or height <= 0:
        return None

    pins = {}
    for port_name, port in iter_optical_ports(component):
        center = port_center_um(port)
        pins[str(port_name)] = {
            "pin_offset_x": center[0] - west,
            "pin_offset_y": center[1] - south,
            "pin_width": port_width_um(port),
            "pin_orient": float(port.orientation),
            "pin_layer": port_layer_list(port),
        }

    return {
        "component": component_name,
        "settings": settings,
        "size": [float(width), float(height)],
        "pins": pins,
    }


def view_signature(view):
    return json.dumps(
        {
            "size": [round(float(value), 9) for value in view.get("size", [])],
            "pins": {
                name: {
                    key: round(float(pin[key]), 9)
                    for key in ("pin_offset_x", "pin_offset_y", "pin_width", "pin_orient")
                    if key in pin
                }
                for name, pin in sorted((view.get("pins") or {}).items())
            },
        },
        sort_keys=True,
    )


def uniquify_macro_name(base_name, view):
    digest = hashlib.sha1(view_signature(view).encode("utf-8")).hexdigest()[:10]
    return f"{base_name}__{digest}"


def build_layout_yaml_data(lidar_data):
    instances = {}
    placements = {}
    for instance_name, instance_node in (lidar_data.get("instances", {}) or {}).items():
        settings = copy.deepcopy(instance_node.get("settings", {}) or {})
        status, lower_left, orientation = placement_tuple(instance_node)
        settings.pop("placement", None)
        settings.pop("macro_type", None)
        component = instance_node.get("component")
        if not component:
            continue
        instance_entry = {"component": component, "settings": settings}
        if "parameters" in instance_node:
            instance_entry["settings"].update(copy.deepcopy(instance_node["parameters"]))
        instances[instance_name] = clean_none_values(instance_entry)
        rotation, mirror = placement_rotation_and_mirror(orientation)
        placements[instance_name] = {
            "x": lower_left[0],
            "y": lower_left[1],
            "port": "sw",
            "rotation": rotation,
            "mirror": mirror,
        }
    return {
        "pdk": "",
        "instances": instances,
        "placements": placements,
        "connections": {},
        "routes": {},
        "ports": {},
    }


def sanitize_gdsfactory_layout_data(data):
    try:
        import gdsfactory as gf
    except Exception:
        return data
    register_optional_gdsfactory_adapters()

    def remove_module_keys(value):
        if isinstance(value, dict):
            value.pop("module", None)
            for child in value.values():
                remove_module_keys(child)
        elif isinstance(value, list):
            for child in value:
                remove_module_keys(child)

    remove_module_keys(data)

    for instance in (data.get("instances", {}) or {}).values():
        settings = instance.get("settings")
        if not isinstance(settings, dict):
            continue
        component = instance.get("component")
        instance["settings"] = sanitized_component_settings(gf, component, settings)
    return data


def named_references(component):
    if hasattr(component, "named_references"):
        return component.named_references
    return {inst.name: inst for inst in component.insts}


def iter_named_ports(ports):
    if hasattr(ports, "items"):
        return list(ports.items())
    return [(port.name, port) for port in ports]


def infer_lidar_src(lidar_yml):
    for parent in [lidar_yml.parent, *lidar_yml.parents]:
        if (parent / "picroute" / "database" / "schematic.py").exists():
            return parent
        if parent.name == "src" and (parent / "picroute").exists():
            return parent
    return None


def extract_layout_ports_from_lidar_db(lidar_yml, lidar_data, out_dir):
    lidar_src = infer_lidar_src(lidar_yml)
    if lidar_src is None:
        return {}

    if str(lidar_src) not in sys.path:
        sys.path.insert(0, str(lidar_src))

    try:
        import gdsfactory as gf
        from picroute.database import schematic as schematic_mod
        from picroute.database.schematic import CustomSchematic
    except Exception:
        (out_dir / "layout_ports_lidar_import_error.txt").write_text(
            traceback.format_exc()
        )
        return {}
    register_optional_gdsfactory_adapters()

    original_show = getattr(gf.Component, "show", None)

    def no_show(self, *unused_args, **unused_kwargs):
        return None

    gf.Component.show = no_show
    original_to_yaml = schematic_mod.CustomNetlist.to_yaml

    def clean_generated_layout_yaml(self, filepath, *args, **kwargs):
        result = original_to_yaml(self, filepath, *args, **kwargs)
        layout_file = Path(filepath)
        try:
            layout_data = yaml.safe_load(layout_file.read_text()) or {}
            layout_file.write_text(
                yaml.safe_dump(
                    sanitize_gdsfactory_layout_data(
                        clean_none_values(layout_data)
                    ),
                    sort_keys=False,
                )
            )
        except Exception:
            pass
        return result

    schematic_mod.CustomNetlist.to_yaml = clean_generated_layout_yaml
    probe_yml = out_dir / "layout_ports_probe.yml"
    probe_yml.write_text(
        yaml.safe_dump(
            clean_none_values(load_lidar_yaml(lidar_yml)), sort_keys=False
        )
    )

    try:
        schematic = CustomSchematic(
            str(probe_yml),
            pdk=None,
            config=make_lidar_db_config(lidar_src, lidar_data),
        )
        schematic.load_gp()
    except Exception:
        (out_dir / "layout_ports_lidar_db_error.txt").write_text(
            traceback.format_exc()
        )
        return {}
    finally:
        if original_show is not None:
            gf.Component.show = original_show
        schematic_mod.CustomNetlist.to_yaml = original_to_yaml

    ports_by_instance = {}
    seen_ports = set()
    instances = lidar_data.get("instances", {}) or {}
    for net in schematic.dbNets.values():
        for db_port in (net.NetPort1, net.NetPort2):
            port_name = str(db_port.port_name)
            if "," not in port_name or db_port.gf_port is None:
                continue
            instance_name, pin_name = port_name.split(",", 1)
            key = (instance_name, pin_name)
            if key in seen_ports:
                continue
            seen_ports.add(key)
            if instance_name not in instances:
                continue
            _, lower_left, _ = placement_tuple(instances[instance_name])
            center = list(db_port.gf_port.dcenter)
            ports_by_instance.setdefault(instance_name, {})[pin_name] = {
                "center": [
                    float(center[0]) - lower_left[0],
                    float(center[1]) - lower_left[1],
                ],
                "orientation": float(db_port.gf_port.orientation),
                "width": float(db_port.gf_port.width),
            }
    return ports_by_instance


def extract_layout_ports(lidar_yml, lidar_data, out_dir):
    ports_from_lidar = extract_layout_ports_from_lidar_db(
        lidar_yml, lidar_data, out_dir
    )
    if ports_from_lidar:
        return ports_from_lidar

    layout_path = lidar_yml.with_suffix(".layout.yml")
    if layout_path.exists():
        layout_data = yaml.safe_load(layout_path.read_text()) or {}
    else:
        layout_data = build_layout_yaml_data(lidar_data)

    layout_data = sanitize_gdsfactory_layout_data(clean_none_values(layout_data))
    debug_layout = out_dir / "layout_ports_input.yml"
    debug_layout.write_text(yaml.safe_dump(layout_data, sort_keys=False))

    try:
        import gdsfactory as gf
    except Exception:
        return {}
    register_optional_gdsfactory_adapters()

    try:
        component = gf.read.from_yaml(str(debug_layout))
    except Exception:
        return {}

    ports_by_instance = {}
    refs = named_references(component)
    for instance_name, instance_node in (lidar_data.get("instances", {}) or {}).items():
        if instance_name not in refs:
            continue
        _, lower_left, _ = placement_tuple(instance_node)
        ref_ports = {}
        for port_name, port in iter_named_ports(refs[instance_name].ports):
            center = list(port.dcenter)
            ref_ports[port_name] = {
                "center": [
                    float(center[0]) - lower_left[0],
                    float(center[1]) - lower_left[1],
                ],
                "orientation": float(port.orientation),
                "width": float(port.width),
            }
        if ref_ports:
            ports_by_instance[instance_name] = ref_ports
    return ports_by_instance


def convert(lidar_data):
    return convert_with_layout_ports(lidar_data, {})


def convert_with_layout_ports(
    lidar_data, layout_ports_by_instance, realize_gdsfactory_lef=True
):
    library = lidar_data.get("library", {}) or {}
    instances = lidar_data.get("instances", {}) or {}
    nets = lidar_data.get("nets", {}) or {}
    settings = lidar_data.get("settings", {}) or {}

    instance_macro = {}
    macro_views = {}
    macro_sources = {}
    for instance_name, instance_node in instances.items():
        original_macro_type = (instance_node.get("settings", {}) or {}).get(
            "macro_type", instance_node.get("component")
        )
        if not original_macro_type:
            raise ValueError(f"Instance '{instance_name}' has no macro_type")
        library_macro = library.get(original_macro_type, {}) or {}
        has_lidar_abstract_view = library_macro.get("size") is not None
        should_realize = realize_gdsfactory_lef or not has_lidar_abstract_view
        realized_view = (
            realize_instance_component(instance_node) if should_realize else None
        )
        macro_type = original_macro_type
        if realized_view is not None:
            if not realized_view.get("pins") and library_macro.get("pins"):
                realized_view["pins"] = copy.deepcopy(library_macro["pins"])
            previous = macro_views.get(original_macro_type)
            if previous is not None and view_signature(previous) != view_signature(realized_view):
                macro_type = uniquify_macro_name(original_macro_type, realized_view)
            macro_views[macro_type] = realized_view
            macro_sources[macro_type] = "gdsfactory"
        elif original_macro_type not in macro_views:
            macro = library_macro
            size = macro.get("size")
            if size is None:
                size = macro_size(library, original_macro_type, instance_node)
            macro_views[original_macro_type] = {
                "component": instance_node.get("component", original_macro_type),
                "settings": copy.deepcopy(instance_node.get("settings", {}) or {}),
                "size": [to_float(value) for value in size],
                "pins": copy.deepcopy(macro.get("pins", {}) or {}),
            }
            macro_sources[original_macro_type] = "lidar_library"
        instance_macro[instance_name] = macro_type

    realized_lidar = copy.deepcopy(lidar_data)
    realized_library = copy.deepcopy(lidar_data.get("library", {}) or {})
    for instance_name, macro_type in instance_macro.items():
        instance_settings = (
            realized_lidar.setdefault("instances", {})
            .setdefault(instance_name, {})
            .setdefault("settings", {})
        )
        instance_settings["macro_type"] = macro_type

    for macro_type, macro_view in macro_views.items():
        original_macro_type = macro_type.split("__", 1)[0]
        macro = copy.deepcopy(
            library.get(macro_type, library.get(original_macro_type, {})) or {}
        )
        macro["size"] = [to_float(value) for value in macro_view["size"]]
        macro["pins"] = copy.deepcopy(macro_view.get("pins", {}) or {})
        if macro_type not in library and original_macro_type != macro_type:
            macro["lidar_original_macro_type"] = original_macro_type
        realized_library[macro_type] = macro
    realized_lidar["library"] = realized_library

    xsections = {"strip": {"width": 0.5}, "metal1": {"width": 10.0}}
    blocks = {}
    for macro_type, macro_view in macro_views.items():
        original_macro_type = macro_type.split("__", 1)[0]
        macro = library.get(macro_type, library.get(original_macro_type, {})) or {}
        width, height = [to_float(value) for value in macro_view["size"]]
        pins = {}
        for pin_name, pin_node in (macro_view.get("pins", {}) or {}).items():
            pin_width = to_float(pin_node.get("pin_width", 0.5))
            xsection = pin_xsection(pin_name, pin_width)
            xsections.setdefault(xsection, {"width": pin_width})
            pins[pin_name] = {
                "doc": "null",
                "width": pin_width,
                "xsection": xsection,
                "xya": [
                    to_float(pin_node.get("pin_offset_x", 0.0)),
                    to_float(pin_node.get("pin_offset_y", 0.0)),
                    to_float(pin_node.get("pin_orient", 0.0)),
                ],
            }
        block_settings = {
            key: copy.deepcopy(value)
            for key, value in macro.items()
            if key not in {"pins", "size"}
        }
        if macro_type not in library:
            block_settings["lidar_original_macro_type"] = original_macro_type
        blocks[macro_type] = {
            "bbox": [[0.0, 0.0], [width, 0.0], [width, height], [0.0, height]],
            "doc": "LiDAR native macro converted for PIC-DB smoke tests.",
            "parameters": {},
            "pins": pins,
            "settings": block_settings,
        }

    lef = {
        "header": {
            "description": f"{settings.get('design', 'lidar_native')}_converted"
        },
        "xsections": xsections,
        "blocks": blocks,
    }

    def_instances = {}
    placements = {}
    for instance_name, instance_node in instances.items():
        macro_type = instance_macro[instance_name]
        status, lower_left, orientation = placement_tuple(instance_node)
        rotation, mirror = orientation_to_picdb(orientation)
        width, height = macro_views[macro_type]["size"]
        def_instance = {"component": macro_type}
        if instance_node.get("component"):
            def_instance["generator"] = copy.deepcopy(instance_node["component"])
        if "parameters" in instance_node:
            def_instance["parameters"] = copy.deepcopy(instance_node["parameters"])
        instance_settings = copy.deepcopy(instance_node.get("settings", {}) or {})
        if instance_settings:
            def_instance["settings"] = instance_settings
        def_instances[instance_name] = def_instance
        oriented_width, oriented_height = oriented_size(width, height, orientation)
        # gdsfactory/kfactory places references on the 1 nm DBU grid.  Snap the
        # LiDAR lower-left before converting to PIC-DB's center reference so DB
        # pin centers match LiDAR layout port centers exactly.
        snapped_lower_left = [
            snap_gdsfactory_dbu(lower_left[0]),
            snap_gdsfactory_dbu(lower_left[1]),
        ]
        placements[instance_name] = {
            "x": snapped_lower_left[0] + oriented_width / 2.0,
            "y": snapped_lower_left[1] + oriented_height / 2.0,
            "rotation": rotation,
            "mirror": mirror,
            "status": status,
        }

    connections = {}
    skipped = {}
    for net_name, endpoints in nets.items():
        if not isinstance(endpoints, (list, tuple)) or len(endpoints) != 2:
            skipped[net_name] = endpoints
            continue
        source, target = str(endpoints[0]), str(endpoints[1])
        if "," not in source or "," not in target:
            skipped[net_name] = endpoints
            continue
        connections[net_name] = {"source": source, "target": target}

    die_area = settings.get("die_area", [[0, 0], [0, 0]])
    design_name = settings.get("design", "lidar_native")
    design = {
        "name": design_name,
        "bbox": die_area,
        "instances": def_instances,
        "placements": placements,
        "connections": connections,
    }
    manifest = {
        "schema": "lidar_native_to_picdb_yml",
        "design": design_name,
        "instances": len(def_instances),
        "macros": len(blocks),
        "nets": len(connections),
        "skipped_nets": skipped,
        "macro_sources": macro_sources,
        "realize_gdsfactory_lef": bool(realize_gdsfactory_lef),
    }
    return lef, design, manifest, realized_lidar


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("lidar_yml")
    parser.add_argument("out_dir")
    parser.add_argument(
        "--realize-gdsfactory-lef",
        action="store_true",
        default=True,
        help=(
            "Build macro bbox/pins from realized gdsfactory components. "
            "This is the default because parameterized cells can change bbox "
            "and pins."
        ),
    )
    parser.add_argument(
        "--preserve-lidar-library-lef",
        action="store_false",
        dest="realize_gdsfactory_lef",
        help=(
            "Compatibility mode: preserve LiDAR benchmark library.size/pins "
            "instead of realizing gdsfactory cells."
        ),
    )
    args = parser.parse_args()

    lidar_yml = Path(args.lidar_yml).resolve()
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    lidar_data = load_lidar_yaml(lidar_yml)
    layout_ports = extract_layout_ports(lidar_yml, lidar_data, out_dir)
    lef, design, manifest, realized_lidar = convert_with_layout_ports(
        lidar_data,
        layout_ports,
        realize_gdsfactory_lef=args.realize_gdsfactory_lef,
    )
    manifest["layout_ports_instances"] = len(layout_ports)
    lef_path = out_dir / "converted_lef.yml"
    def_path = out_dir / "converted_def.yml"
    realized_lidar_path = out_dir / "converted_lidar.yml"
    manifest_path = out_dir / "conversion_manifest.yml"
    lef_path.write_text(yaml.safe_dump(lef, sort_keys=False))
    def_path.write_text(yaml.safe_dump(design, sort_keys=False))
    realized_lidar_path.write_text(yaml.safe_dump(realized_lidar, sort_keys=False))
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False))
    print(f"lef={lef_path}")
    print(f"def={def_path}")
    print(f"lidar={realized_lidar_path}")
    print(f"manifest={manifest_path}")


if __name__ == "__main__":
    main()
