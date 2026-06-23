"""GDSFactory component adapters for PICBench SAX netlists.

PICBench reference designs are functional SAX netlists.  Their components use
logical ports such as ``I1`` and ``O1`` rather than the physical ``o1/o2`` port
names from the generic GDSFactory PDK.  This module registers small schematic
cells with matching PICBench port names so converted YAML can be imported with
``gf.read.from_yaml``.
"""

from __future__ import annotations

from collections.abc import Iterable
from types import SimpleNamespace
from typing import Any

import gdsfactory as gf
from gdsfactory.typings import LayerSpec


LAYER: LayerSpec = (1, 0)
PORT_WIDTH = 0.5


MODEL_TO_CELL = {
    "straight": "picbench_straight",
    "waveguide": "picbench_straight",
    "straight_heat_metal": "picbench_straight_heat_metal",
    "mmi1x2": "picbench_mmi1x2",
    "mmi": "picbench_mmi1x2",
    "coupler": "picbench_coupler",
    "mzi_ps": "picbench_mzi_ps",
    "mzm": "picbench_mzm",
    "mzm_dual": "picbench_mzm_dual",
    "mrr": "picbench_mrr",
    "OSU": "picbench_osu",
    "osu": "picbench_osu",
}


def _activate_generic_pdk() -> None:
    """Activate the generic PDK when no compatible active PDK is available."""
    try:
        gf.get_active_pdk()
    except Exception:
        from gdsfactory.generic_tech import get_generic_pdk

        get_generic_pdk().activate()


def _install_legacy_gpdk_shim() -> None:
    """Expose the old gf.gpdk.PDK.activate API expected by LiDAR."""
    if hasattr(gf, "gpdk"):
        return
    from gdsfactory.generic_tech import get_generic_pdk

    gf.gpdk = SimpleNamespace(  # type: ignore[attr-defined]
        PDK=SimpleNamespace(activate=lambda: get_generic_pdk().activate())
    )


def _ys(count: int, pitch: float = 8.0) -> list[float]:
    if count <= 1:
        return [0.0]
    origin = (count - 1) * pitch / 2
    return [origin - index * pitch for index in range(count)]


def _block_with_ports(
    name: str,
    input_ports: Iterable[str],
    output_ports: Iterable[str],
    *,
    width: float = 30.0,
    height: float = 20.0,
    layer: LayerSpec = LAYER,
) -> gf.Component:
    c = gf.Component(name=name)
    c.add_polygon(
        [(0, -height / 2), (width, -height / 2), (width, height / 2), (0, height / 2)],
        layer=layer,
    )

    input_ports = tuple(input_ports)
    output_ports = tuple(output_ports)
    for port_name, y in zip(input_ports, _ys(len(input_ports)), strict=True):
        c.add_port(
            name=port_name,
            center=(0, y),
            width=PORT_WIDTH,
            orientation=180,
            layer=layer,
            port_type="optical",
        )

    for port_name, y in zip(output_ports, _ys(len(output_ports)), strict=True):
        c.add_port(
            name=port_name,
            center=(width, y),
            width=PORT_WIDTH,
            orientation=0,
            layer=layer,
            port_type="optical",
        )
    return c


@gf.cell
def picbench_straight(
    length: float = 20.0,
    layer: LayerSpec = LAYER,
    **settings: Any,
) -> gf.Component:
    height = float(settings.get("height", 4.0))
    return _block_with_ports(
        "picbench_straight",
        ("I1",),
        ("O1",),
        width=max(float(length), 1.0),
        height=height,
        layer=layer,
    )


@gf.cell
def picbench_straight_heat_metal(
    length: float = 20.0,
    phase: float | None = None,
    phase_shift: float | None = None,
    layer: LayerSpec = LAYER,
    **settings: Any,
) -> gf.Component:
    c = _block_with_ports(
        "picbench_straight_heat_metal",
        ("I1",),
        ("O1",),
        width=max(float(length), 1.0),
        height=6.0,
        layer=layer,
    )
    heater = c << gf.components.rectangle(size=(max(float(length), 1.0), 1.0), layer=(2, 0))
    heater.dmovey(-0.5)
    c.info["phase"] = phase if phase is not None else phase_shift
    return c


@gf.cell
def picbench_mmi1x2(layer: LayerSpec = LAYER, **settings: Any) -> gf.Component:
    return _block_with_ports("picbench_mmi1x2", ("I1",), ("O1", "O2"), layer=layer)


@gf.cell
def picbench_coupler(layer: LayerSpec = LAYER, **settings: Any) -> gf.Component:
    return _block_with_ports(
        "picbench_coupler",
        ("I1", "I2"),
        ("O1", "O2"),
        width=34.0,
        height=24.0,
        layer=layer,
    )


@gf.cell
def picbench_mzi_ps(layer: LayerSpec = LAYER, **settings: Any) -> gf.Component:
    return _block_with_ports(
        "picbench_mzi_ps",
        ("I1", "I2"),
        ("O1", "O2"),
        width=46.0,
        height=24.0,
        layer=layer,
    )


@gf.cell
def picbench_mzm(layer: LayerSpec = LAYER, **settings: Any) -> gf.Component:
    return _block_with_ports(
        "picbench_mzm",
        ("I1",),
        ("O1",),
        width=48.0,
        height=16.0,
        layer=layer,
    )


@gf.cell
def picbench_mzm_dual(layer: LayerSpec = LAYER, **settings: Any) -> gf.Component:
    return _block_with_ports(
        "picbench_mzm_dual",
        ("I1",),
        ("O1",),
        width=56.0,
        height=18.0,
        layer=layer,
    )


@gf.cell
def picbench_mrr(
    cwl: float = 1.55,
    layer: LayerSpec = LAYER,
    **settings: Any,
) -> gf.Component:
    c = _block_with_ports(
        "picbench_mrr",
        ("I1",),
        ("O1", "O2", "O3"),
        width=28.0,
        height=28.0,
        layer=layer,
    )
    c.info["cwl"] = cwl
    return c


@gf.cell
def picbench_osu(layer: LayerSpec = LAYER, **settings: Any) -> gf.Component:
    return _block_with_ports(
        "picbench_osu",
        ("I1", "I2"),
        ("O1", "O2"),
        width=44.0,
        height=24.0,
        layer=layer,
    )


@gf.cell
def picbench_generic(
    port_names: tuple[str, ...] = ("I1", "O1"),
    layer: LayerSpec = LAYER,
    **settings: Any,
) -> gf.Component:
    input_ports = tuple(port for port in port_names if port.startswith("I"))
    output_ports = tuple(port for port in port_names if not port.startswith("I"))
    return _block_with_ports(
        "picbench_generic",
        input_ports or ("I1",),
        output_ports or ("O1",),
        width=30.0,
        height=max(16.0, 6.0 * max(len(input_ports), len(output_ports), 1)),
        layer=layer,
    )


def component_name_for_model(model_name: str) -> str:
    """Return the registered GDSFactory cell name for a PICBench model."""
    return MODEL_TO_CELL.get(model_name, "picbench_generic")


def register_picbench_cells() -> None:
    """Register all PICBench adapter cells into the active GDSFactory PDK."""
    _install_legacy_gpdk_shim()
    _activate_generic_pdk()
    pdk = gf.get_active_pdk()
    cells = {
        "picbench_straight": picbench_straight,
        "picbench_straight_heat_metal": picbench_straight_heat_metal,
        "picbench_mmi1x2": picbench_mmi1x2,
        "picbench_coupler": picbench_coupler,
        "picbench_mzi_ps": picbench_mzi_ps,
        "picbench_mzm": picbench_mzm,
        "picbench_mzm_dual": picbench_mzm_dual,
        "picbench_mrr": picbench_mrr,
        "picbench_osu": picbench_osu,
        "picbench_generic": picbench_generic,
    }
    missing = {name: cell for name, cell in cells.items() if name not in pdk.cells}
    if missing:
        pdk.register_cells(**missing)


__all__ = [
    "MODEL_TO_CELL",
    "component_name_for_model",
    "register_picbench_cells",
]
