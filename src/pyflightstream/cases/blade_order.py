"""Check declared blade order against readable geometry before building frames.

FR-3616 and FR-3617 compare area-weighted radial centroids with the positive
shaft rotation used by the blade frames. Spin direction is deliberately absent.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np

from pyflightstream._errors import PyflightstreamWarning, warn
from pyflightstream._fsm import (
    boundary_names,
    boundary_surface,
    names_of,
    saved_mesh_coordinate_unit,
)
from pyflightstream._lengths import METRES_PER_UNIT
from pyflightstream._mesh import obj_group_surface

from .reference_blocks import CampaignConfigError, RotorBlock

if TYPE_CHECKING:
    from . import SimCase

#: Maximum angular disagreement: a quarter of one blade pitch.
BLADE_ORDER_PITCH_TOLERANCE = 0.25
#: Smaller irregularities are worth reporting even when the order is acceptable.
SPACING_TOLERANCE_DEG = 1.0
_SAID: ContextVar[set[str] | None] = ContextVar("blade_order_warnings", default=None)


@contextmanager
def noting_blade_order() -> Iterator[None]:
    """Report each unavailable or uneven rotor once during one plan."""
    token = _SAID.set(set())
    try:
        yield
    finally:
        _SAID.reset(token)


def _note(message: str) -> None:
    said = _SAID.get()
    if said is None or message not in said:
        warn(message, PyflightstreamWarning)
        if said is not None:
            said.add(message)


@noting_blade_order()
def blade_order_errors(cases: Iterable[SimCase]) -> dict[str, str]:
    """Read each row's blade geometry once and return its refusal, if any.

    Parameters
    ----------
    cases : iterable of SimCase
        The plan's rows, before expansion into operating points.

    Returns
    -------
    dict of str to str
        Refusals keyed by simulation identifier; unavailable evidence only warns.
    """
    errors = {}
    for case in cases:
        try:
            for rotor in case.rotors.values():
                validate_blade_order(
                    case.geometry, rotor, units=getattr(case.mesh_import, "units", None)
                )
        except CampaignConfigError as error:
            errors[case.sim_id] = str(error)
    return errors


def _surface(path: Path, name: str) -> tuple[np.ndarray, np.ndarray]:
    read: Callable[[Path, str], tuple[Any, Any]]
    if path.suffix.lower() == ".fsm":
        names = boundary_names(path) or ()
        read = boundary_surface
    elif path.suffix.lower() == ".obj":
        names = tuple(
            dict.fromkeys(
                words[1]
                for line in path.read_text(encoding="utf-8", errors="replace").splitlines()
                if len(words := line.split("#", 1)[0].split()) > 1 and words[0] in ("o", "g")
            )
        )
        read = obj_group_surface
    else:
        raise ValueError("geometry is not a readable named surface mesh")
    vertices: list[tuple[float, float, float]] = []
    faces: list[tuple[int, int, int]] = []
    offset = 0
    for selected in names_of(name, names):
        points, triangles = read(path, selected)
        vertices.extend(points)
        faces.extend(np.asarray(triangles, dtype=int) + offset)
        offset += len(points)
    return np.asarray(vertices, dtype=float), np.asarray(faces, dtype=int)


def _directions(path: Path, rotor: RotorBlock, units: str | None) -> np.ndarray:
    unit = saved_mesh_coordinate_unit(path) if path.suffix.lower() == ".fsm" else units
    if unit is None or unit not in METRES_PER_UNIT:
        raise ValueError("stored mesh coordinate unit is unknown")
    axis = np.asarray(rotor.axis_vector)
    radial = []
    for name in rotor.families_blades:
        vertices, faces = _surface(path, name)
        if not len(faces):
            raise ValueError(f"family {name!r} has no readable faces (possibly a sector)")
        triangles = vertices[faces] * float(METRES_PER_UNIT[unit])
        areas = np.linalg.norm(
            np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0]), axis=1
        )
        if not np.isfinite(triangles).all() or not np.isfinite(areas).all() or areas.sum() <= 0:
            raise ValueError(f"family {name!r} has no finite positive area")
        delta = np.average(triangles.mean(axis=1), axis=0, weights=areas) - rotor.origin
        direction = delta - np.dot(delta, axis) * axis
        length = np.linalg.norm(direction)
        if length <= max(rotor.diameter_m * 1e-12, 1e-15):
            raise ValueError(f"family {name!r} has its area-weighted centroid on the axis")
        radial.append(direction / length)
    return np.asarray(radial)


def validate_blade_order(
    geometry: str | Path | None, rotor: RotorBlock, *, units: str | None = None
) -> None:
    """Refuse a readable wheel whose list assigns blades to the wrong frames.

    Parameters
    ----------
    geometry : str or Path or None
        Source mesh. No solver or sidecar export is needed for saved geometry.
    rotor : RotorBlock
        Declared hub, shaft and ordered blade families.
    units : str or None
        Import units for a raw OBJ; saved files supply their own coordinate unit.

    Raises
    ------
    CampaignConfigError
        Blade azimuths differ from their list positions by over a quarter pitch.
    """
    names = rotor.families_blades
    if len(names) < 2:
        return
    label = f"rotor {rotor.alias!r} in {geometry}: blade order"
    try:
        if geometry is None:
            raise ValueError("no geometry is available")
        directions = _directions(Path(geometry), rotor, units)
    except (OSError, ValueError) as error:
        _note(f"{label} was not checked: {error}")
        return
    first = directions[0]
    angles = (
        np.degrees(np.arctan2(np.cross(first, directions) @ rotor.axis_vector, directions @ first))
        % 360
    )
    angles[0] = 0.0
    order = np.argsort(angles, kind="stable")
    pitch = 360.0 / len(names)
    spacing = np.diff(np.r_[angles[order], 360.0])
    if np.max(np.abs(spacing - pitch)) > SPACING_TOLERANCE_DEG:
        _note(f"{label} has uneven blade spacing; the frame rule assumes {pitch:g} degrees.")
    errors = (angles - np.arange(len(names)) * pitch + 180) % 360 - 180
    if np.max(np.abs(errors)) > pitch * BLADE_ORDER_PITCH_TOLERANCE:
        correct = [names[int(i)] for i in order]
        raise CampaignConfigError(
            f"{label} disagrees with families_blades = {json.dumps(names)}. "
            "Per-blade frames would cut across the blade spans and corrupt per-blade loads. "
            f"Write families_blades = {json.dumps(correct)}; the tolerance is a quarter "
            f"of the blade pitch ({pitch * BLADE_ORDER_PITCH_TOLERANCE:g} degrees)."
        )
