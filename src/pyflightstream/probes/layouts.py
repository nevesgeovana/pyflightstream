"""The layouts of probe shapes: line, rectangle, circle, survey lattice, far-field plane.

Pipeline role: the one place probe positions are computed (FR-459). The line,
rectangle and circle of a ``[[probes]]`` entry (FR-79) are laid out here, in
the entry's frame and scale, rounded to five decimals as the script carries
them; the arithmetic order and ``math.cos``/``math.sin`` are those the emitted
scripts were written with, so a script is byte-identical whichever module laid
its points out. The survey lattice of a ``lattices`` entry and the far-field
plane of Trefftz C are laid out here too, and so are the script lines and the
import csv that create and export probes (NEW_PROBE_POINT / PROBE_POINTS_IMPORT,
UPDATE_PROBE_POINTS, EXPORT_PROBE_POINTS; SRC-003 pp.362-363).

The shapes are read by attribute (an entry of the pproc artifact, or any object
with the same fields), so this module imports nothing above it.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np

import pyflightstream._textio as _textio
from pyflightstream.probes.errors import ProbeGeometryError
from pyflightstream.probes.lattice import ProbeLattice
from pyflightstream.script import Script, helpers
from pyflightstream.script.toggles import Toggle

__all__ = [
    "FarfieldPlane",
    "circle_points",
    "emit_probe_export",
    "emit_probe_import",
    "emit_probe_points",
    "farfield_plane",
    "lattice_points",
    "line_points",
    "rectangle_points",
    "write_points_csv",
    "write_probe_csv",
]


class _Rectangle(Protocol):
    origin: Sequence[float]
    along_u: Sequence[float]
    along_v: Sequence[float]
    points_u: int
    points_v: int


class _Circle(Protocol):
    center: Sequence[float]
    normal: Sequence[float]
    radius: float
    points_radial: int
    points_azimuth: int


def line_points(
    start: Sequence[float], end: Sequence[float], points: int, scale: float
) -> list[list[float]]:
    """Lay out the points of a probe line, both ends included (FR-77).

    Parameters
    ----------
    start, end : sequence of float
        The line's ends in the entry's frame, in the entry's unit.
    points : int
        The point count, at least two.
    scale : float
        The factor from the entry's unit to the simulation's length unit.

    Returns
    -------
    list of list of float
        ``points`` rows ``[x, y, z]``, rounded to five decimals.
    """
    out: list[list[float]] = []
    for step in range(points):
        fraction = step / (points - 1)
        out.append(
            [round((a + (b - a) * fraction) * scale, 5) for a, b in zip(start, end, strict=True)]
        )
    return out


def rectangle_points(rectangle: _Rectangle, scale: float) -> list[list[float]]:
    """Lay out the grid of a rectangular probe plane, row by row (FR-79).

    Three corners give two edge vectors from `origin`, and the grid runs along
    both with BOTH ENDS INCLUDED, so a declaration of 3 by 4 is twelve points
    and three of its corners are the three declared vertices. The order is v
    fastest within u, which is the reading order of a row of stations.
    """
    origin = list(rectangle.origin)
    edge_u = [b - a for a, b in zip(rectangle.origin, rectangle.along_u, strict=True)]
    edge_v = [b - a for a, b in zip(rectangle.origin, rectangle.along_v, strict=True)]
    out: list[list[float]] = []
    for index_u in range(rectangle.points_u):
        fraction_u = index_u / (rectangle.points_u - 1)
        for index_v in range(rectangle.points_v):
            fraction_v = index_v / (rectangle.points_v - 1)
            out.append(
                [
                    round(
                        (origin[axis] + edge_u[axis] * fraction_u + edge_v[axis] * fraction_v)
                        * scale,
                        5,
                    )
                    for axis in range(3)
                ]
            )
    return out


def circle_points(circle: _Circle, scale: float) -> list[list[float]]:
    """Lay out the polar grid of a circular probe plane (FR-79).

    `points_radial` stations from the centre to the rim INCLUDING both, and
    `points_azimuth` around. THE CENTRE APPEARS ONCE rather than once per
    azimuth: a survey that sampled its own centre eight times would weight it
    eight times in anything that averages the file.

    The two in-plane axes are built from the normal by taking the world axis
    least aligned with it, which is the standard way to get a stable basis and
    avoids the degenerate cross product a fixed choice hits when the normal
    happens to be that axis. ``math.cos`` and ``math.sin`` and not numpy's:
    the two may differ in the last bit and flip a fifth decimal of a script.
    """
    normal = list(circle.normal)
    length = math.sqrt(sum(value * value for value in normal))
    normal = [value / length for value in normal]
    least = min(range(3), key=lambda axis: abs(normal[axis]))
    seed = [1.0 if axis == least else 0.0 for axis in range(3)]
    first = [
        seed[1] * normal[2] - seed[2] * normal[1],
        seed[2] * normal[0] - seed[0] * normal[2],
        seed[0] * normal[1] - seed[1] * normal[0],
    ]
    span = math.sqrt(sum(value * value for value in first))
    first = [value / span for value in first]
    second = [
        normal[1] * first[2] - normal[2] * first[1],
        normal[2] * first[0] - normal[0] * first[2],
        normal[0] * first[1] - normal[1] * first[0],
    ]

    out: list[list[float]] = []
    for index_r in range(circle.points_radial):
        radius = circle.radius * index_r / (circle.points_radial - 1)
        if radius == 0.0:
            out.append([round(value * scale, 5) for value in circle.center])
            continue
        for index_a in range(circle.points_azimuth):
            angle = 2.0 * math.pi * index_a / circle.points_azimuth
            out.append(
                [
                    round(
                        (
                            circle.center[axis]
                            + radius
                            * (math.cos(angle) * first[axis] + math.sin(angle) * second[axis])
                        )
                        * scale,
                        5,
                    )
                    for axis in range(3)
                ]
            )
    return out


#: The cyclic order of the axes, so a lattice laid along any one of them stays
#: right-handed: x along the shaft, then the next two letters in turn.
_CYCLIC = {"X": (0, 1, 2), "Y": (1, 2, 0), "Z": (2, 0, 1)}


def lattice_points(lattice: ProbeLattice, *, axis: str = "X") -> np.ndarray:
    """Lay out a survey lattice in a frame whose ``axis`` is the shaft (FR-459 R2).

    The lattice's own coordinates (x along the shaft, ``y = r sin psi``,
    ``z = r cos psi``) are carried onto the frame's axes in cyclic order: for a
    shaft along the frame's Y, the lattice x is the frame's Y, its y the
    frame's Z and its z the frame's X, so the lattice stays right-handed. The
    order of the points is the loading contract of
    :meth:`~pyflightstream.probes.lattice.ProbeLattice.dimensional_points`.

    Parameters
    ----------
    lattice : ProbeLattice
        The survey lattice.
    axis : {"X", "Y", "Z"}
        The frame axis along the shaft.

    Returns
    -------
    numpy.ndarray
        Positions ``(point_count, 3)`` in the frame, in the lattice's length
        unit (the tip radius times the nondimensional positions).
    """
    order = _CYCLIC.get(str(axis).strip().upper())
    if order is None:
        raise ProbeGeometryError(f"a lattice's shaft axis is X, Y or Z, not {axis!r}")
    local = lattice.dimensional_points()
    out = np.empty_like(local)
    for source, target in enumerate(order):
        out[:, target] = local[:, source]
    return out


@dataclass(frozen=True, eq=False)
class FarfieldPlane:
    """The probe grid of a Trefftz C plane (FR-453 R4).

    Attributes
    ----------
    points : numpy.ndarray
        Positions ``(n_y * n_z, 3)`` in the frame the origin and the direction
        were stated in, ``z`` fastest within ``y``.
    y, z : numpy.ndarray
        The grid axes in the plane, m, centered on the origin's projection.
    axes : numpy.ndarray
        Rows ``x``, ``y``, ``z``: the free-stream direction and the two in-plane
        directions, unit vectors in the same frame.
    """

    points: np.ndarray
    y: np.ndarray
    z: np.ndarray
    axes: np.ndarray


def farfield_plane(
    origin: Sequence[float],
    direction: Sequence[float],
    *,
    distance: float,
    half_width: float,
    half_height: float,
    spacing: float,
) -> FarfieldPlane:
    """Lay out the Trefftz C plane: normal to the free stream, a uniform grid.

    The plane's normal is the free-stream ``direction`` (downstream); its
    in-plane ``y`` is horizontal, ``up x direction`` normalized with
    ``up = (0, 0, 1)``, and its ``z`` completes the right-handed set, so at zero
    incidence and sideslip the plane's axes are the frame's. The grid is
    centered on the point ``origin + distance direction``.

    Parameters
    ----------
    origin : sequence of float
        The point the plane is measured from (on the free-stream line through
        the moment reference point, level with the most downstream point of the
        selected families), m.
    direction : sequence of float
        The free-stream direction, any length.
    distance : float
        How far downstream of ``origin`` the plane stands, m.
    half_width, half_height : float
        Half the plane's extent along its ``y`` and ``z``, m.
    spacing : float
        The grid spacing, m; each half extent holds a whole number of
        spacings, rounded to the nearest.

    Returns
    -------
    FarfieldPlane
        The grid.
    """
    d = np.asarray(direction, dtype=float)
    norm = float(np.linalg.norm(d))
    if not (np.isfinite(norm) and norm > 0.0):
        raise ProbeGeometryError("the free-stream direction of a far-field plane has no length")
    if not (spacing > 0.0 and half_width > 0.0 and half_height > 0.0):
        raise ProbeGeometryError("a far-field plane needs a positive extent and spacing")
    x_axis = d / norm
    up = np.array([0.0, 0.0, 1.0])
    y_axis = np.cross(up, x_axis)
    y_norm = float(np.linalg.norm(y_axis))
    if y_norm < 1e-12:
        raise ProbeGeometryError("a far-field plane cannot be laid for a vertical free stream")
    y_axis = y_axis / y_norm
    z_axis = np.cross(x_axis, y_axis)
    n_y = int(round(half_width / spacing))
    n_z = int(round(half_height / spacing))
    y = spacing * np.arange(-n_y, n_y + 1)
    z = spacing * np.arange(-n_z, n_z + 1)
    center = np.asarray(origin, dtype=float) + distance * x_axis
    yy, zz = np.meshgrid(y, z, indexing="ij")
    points = center + yy.ravel()[:, None] * y_axis + zz.ravel()[:, None] * z_axis
    return FarfieldPlane(points=points, y=y, z=z, axes=np.vstack([x_axis, y_axis, z_axis]))


def emit_probe_points(script: Script, lattice: ProbeLattice) -> int:
    """Emit one NEW_PROBE_POINT line per lattice probe (SRC-003 p.362).

    Every probe is a VOLUME probe: the lattice samples the flow field,
    never the body surface. Emission is version-validated by the
    script's command view; the probe family is stable across 26.1 and
    26.12, and a version without recorded evidence (for example
    26.000) refuses with a citation.

    Parameters
    ----------
    script : Script
        Version-bound script builder.
    lattice : ProbeLattice
        Lattice to instantiate; points are emitted in the documented
        loading order of :meth:`ProbeLattice.dimensional_points`.

    Returns
    -------
    int
        Number of probe points emitted.
    """
    points = lattice.dimensional_points()
    helpers.probe_points(script, [(float(x), float(y), float(z)) for x, y, z in points])
    return len(points)


def write_probe_csv(lattice: ProbeLattice, path: str | Path) -> int:
    """Write the PROBE_POINTS_IMPORT csv for the whole lattice.

    The documented format (SRC-003 pp.362-363) is the point count on
    the first line, then one ``X,Y,Z,TYPE`` row per probe with TYPE 1
    for volume probes. This is the practical path for the full ~20k
    point lattice, where one NEW_PROBE_POINT line per probe would be
    unwieldy.

    Parameters
    ----------
    lattice : ProbeLattice
        Lattice to write, in the documented loading order.
    path : str or pathlib.Path
        Destination csv path.

    Returns
    -------
    int
        Number of probe rows written.
    """
    return write_points_csv(lattice.dimensional_points(), path)


def write_points_csv(points: np.ndarray, path: str | Path) -> int:
    """Write any probe positions as a PROBE_POINTS_IMPORT csv.

    Shared by the cylindrical survey lattice and the planar grids: the
    documented format (SRC-003 pp.362-363) is the point count on the
    first line, then one ``X,Y,Z,TYPE`` row per probe with TYPE 1 for
    volume probes. Rows follow the order of ``points``, which is the
    loading contract of the caller.

    Parameters
    ----------
    points : numpy.ndarray
        Positions, shape ``(n, 3)``, reference frame, simulation
        length units.
    path : str or pathlib.Path
        Destination csv path.

    Returns
    -------
    int
        Number of probe rows written.
    """
    points = np.asarray(points, dtype=float)
    # PFS-2038.07. The last boundary before a solver-facing file, and it
    # is checked here as well as at the frame because a point array
    # reaches this function from callers that never built a frame.
    if points.size and not bool(np.all(np.isfinite(points))):
        bad = int(np.count_nonzero(~np.isfinite(points).all(axis=-1)))
        raise ProbeGeometryError(
            f"{bad} of {len(points)} probe positions are not finite, so the csv would "
            "carry nan or inf where a coordinate goes. A written count of rows is not a "
            "written set of positions; nothing is written."
        )
    lines = [str(len(points))]
    lines += [f"{x},{y},{z},1" for x, y, z in points]
    _textio.write_text(Path(path), "\n".join(lines) + "\n")
    return len(points)


def emit_probe_import(
    script: Script,
    path: str | Path,
    *,
    units: str = "METER",
    frame: int = 1,
) -> None:
    """Emit PROBE_POINTS_IMPORT for a csv written by :func:`write_probe_csv`.

    Parameters
    ----------
    script : Script
        Version-bound script builder.
    path : str or pathlib.Path
        Csv path as the solver machine sees it.
    units : str
        Length unit token of the csv coordinates (SRC-003 p.362).
    frame : int
        Coordinate system index of the csv coordinates; 1 is the
        reference frame.
    """
    script.emit("PROBE_POINTS_IMPORT", units, frame, str(path))


def emit_probe_export(script: Script, path: str | Path, *, update: Toggle = True) -> None:
    """Emit the post-solve probe refresh and export (SRC-003 pp.362-363).

    UPDATE_PROBE_POINTS refreshes the probe values from the current
    solution and precedes the export by default; the exported file
    carries velocity components, both pressure coefficient forms, Mach
    and the boundary layer state flags (SRC-003 p.249).

    Parameters
    ----------
    script : Script
        Version-bound script builder.
    path : str or pathlib.Path
        Export destination as the solver machine sees it.
    update : bool or 'ENABLE' or 'DISABLE'
        Whether to refresh probe values first; disable only when an
        update was already emitted.

    Raises
    ------
    CommandArgumentError
        If this script already exports to ``path``. The solver writes one
        file per path, so two exports to one path meant the second
        silently replaced the first while the script carried two
        identical lines and nothing recorded that only one file survived
        (PFS-2011.02). The refusal names BOTH call sites: the earlier one
        by the entry point it used, and this one by raising here.

    Notes
    -----
    The register of exported paths lives on the
    :class:`~pyflightstream.script.Script`, because the collision is
    between two CALLS and only the script sees both. This function is a
    second entry point onto that register and re-stamps it with its own
    name, for the reason under the call below.
    """
    helpers.export_probes(script, str(path), update=update)
    # PFS-2011.02. `helpers.export_probes` registers the path under the
    # name of the helper, so a collision between two calls made THROUGH
    # THIS function told the reader "from export_probes", a function
    # their code never calls. A refusal that names a call site the caller
    # did not write is worse than one that names none: it sends them to
    # look for a line that is not there. This is the only one of the two
    # entry points that knows which was used, so the register is stamped
    # with the truthful site here. The remedy sentence of the refusal is
    # built inside `script.helpers` and still names the helper; moving
    # that into a caller-supplied site name is a change to `script`, not
    # to this layer, and is reported rather than made here.
    script._exported_paths[str(path)] = "emit_probe_export"
