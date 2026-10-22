"""The hub and lattice geometry of the far-field probes of one point (FR-456, PFS-2081.93).

Pipeline role: the part of :mod:`pyflightstream.post.farfield_products` that places a
frame's lattice, the plane grid and the hub frame a quasi-steady rotor's probes turn about.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import numpy as np

from pyflightstream._errors import PyflightstreamError
from pyflightstream.post._condition import _recorded_speeds, row_rotor_speeds
from pyflightstream.post.farfield_fields import (
    FarLayout,
    derived_layout,
    frame_lattice,
    recorded_layout,
    rotor_lattice,
)

if TYPE_CHECKING:
    from pyflightstream.post._sim import SimContext
    from pyflightstream.post.polar import PolarPoint

_NA = float("nan")
_AXES = {"X": np.array([1.0, 0.0, 0.0]), "Y": np.array([0.0, 1.0, 0.0]), "Z": np.array([0, 0, 1.0])}


def _lattice_of(ctx: SimContext, spec) -> tuple[Any, np.ndarray | None, str] | None:
    if spec.ledgers is None:
        return None
    if spec.ledgers.rotor is None:
        return frame_lattice(spec.ledgers)
    rotor = (getattr(ctx.live, "rotors", None) or {}).get(spec.ledgers.rotor)
    if rotor is None:
        raise PyflightstreamError(
            f"the reference names no rotor {spec.ledgers.rotor!r} to place the lattice on"
        )
    return rotor_lattice(spec.ledgers, rotor)


def _plane_grid(ctx: SimContext, spec) -> tuple[float, float, float]:
    half_width, half_height, spacing = spec.trefftz.plane_bref()
    bref = float(ctx.reference.bref_m)
    return half_width * bref, half_height * bref, spacing * bref


def _hub(
    ctx: SimContext, point: PolarPoint, spec, layout: FarLayout
) -> tuple[float, np.ndarray, np.ndarray] | None:
    """Return the frame speed (rad/s, signed), axis and origin of a quasi-steady rotor's probes.

    PFS-2081.93: the speed is read as every other product of the point reads
    it, the record's plan where it states one and otherwise the row's own
    speed from the quasi-steady record beside the loads export
    (:func:`~pyflightstream.post._condition.row_rotor_speeds`), which a
    ``qsteady_rotor`` run always writes and never plans. That speed is SIGNED
    by the rotor's hand (``rpm_sign`` times the row's magnitude), so the frame
    turns about the axis by the sign of the speed alone; the hand is not
    applied a second time. The axis and the hub are the lattice's as the run
    recorded it, or the reference's rotor block for a record without a layout.
    """
    record = ctx.record_of[point.name]
    if str(record.recipe or "") != "qsteady_rotor" or spec.ledgers is None:
        return None
    alias = spec.ledgers.rotor
    own = row_rotor_speeds(record, getattr(point, "loads_path", None))
    rpm = _recorded_speeds(record.reductions, own).get(str(alias))
    rotor: Any = (getattr(ctx.live, "rotors", None) or {}).get(alias)
    if rpm is None:
        raise PyflightstreamError(
            f"the quasi-steady rotor {alias!r} states no speed in the point's record nor in "
            "its quasi-steady record, so its probes cannot be converted to the hub frame"
        )
    if layout.lattice_origin_m is not None:
        letter, origin = layout.axis, np.asarray(layout.lattice_origin_m, dtype=np.float64)
    elif rotor is not None:
        letter = str(rotor.axis)
        origin = np.asarray([rotor.x_m, rotor.y_m, rotor.z_m], dtype=np.float64)
    else:
        raise PyflightstreamError(
            f"the reference names no rotor {alias!r}, so the hub its probes turn about is unknown"
        )
    return 2.0 * math.pi * float(rpm) / 60.0, _AXES[letter.strip().upper()], origin


def _flow(point: PolarPoint) -> tuple[float, float, float, float]:
    """Return the density, the free-stream speed, alpha and beta (deg) of a point."""
    state = point.state
    rho = float(state.density_kg_m3) if state and state.density_kg_m3 else _NA
    loads = point.loads
    return rho, float(loads.freestream_velocity_m_s), loads.angle_of_attack_deg, loads.sideslip_deg


@dataclass(frozen=True)
class _Probe:
    """Where a point's far-field probes are and how to read them."""

    per_m: float
    layout: FarLayout
    hub: tuple[float, np.ndarray, np.ndarray] | None
    rotor: bool = False


def _layout(ctx: SimContext, point: PolarPoint, spec, rotor: bool) -> FarLayout:
    """Return the far-field probes of a point: as its run recorded them, else from the table.

    PFS-2081.58: the record's layout is what the plan laid or reused, so post
    integrates exactly those probes with their own grid, whatever the table
    states today. A record written before the layout was recorded is matched
    to the table as it stands, the plane and a frame's lattice by shape.
    """
    record = ctx.record_of[point.name]
    shapes = (getattr(record, "farfield_layout", None) or {}).get("shapes")
    if shapes:
        return recorded_layout(shapes)
    plane = spec.trefftz is not None and "plane" in spec.trefftz.variant and not rotor
    _rho, _speed, alpha, beta = _flow(point)
    a, b = math.radians(alpha), math.radians(beta)
    direction = (math.cos(a) * math.cos(b), -math.cos(a) * math.sin(b), math.sin(a))
    return derived_layout(
        plane_grid=_plane_grid(ctx, spec) if plane else None,
        direction=direction,
        lattice=_lattice_of(ctx, spec),
    )
