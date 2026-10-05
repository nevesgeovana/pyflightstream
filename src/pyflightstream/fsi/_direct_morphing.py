"""The structural program's half of direct mesh morphing (FR-341, route C).

With direct morphing the solver imports no structural nodes. Before every
structural call it writes the surface vertices it morphs, one row each, to
:data:`AERO_NODES_FILE`, and it reads back one displacement per row of that
file, in its order, from ``FSIDisp.txt``. With RIGID aerodynamic nodes (the
only direct mode the package offers) the rows are the UNDEFORMED vertices at
every call, and the displacements read back are totals from the undeformed
surface: build 26.125 moved the surface by exactly what was written over two
coupling cycles (FR-341 R2).

So the beam solution is evaluated at each vertex by the rigid-section
kinematics the mapped route encodes at its three nodes per station
(:mod:`pyflightstream.fsi.kinematics`): at station ``s`` a point ``p`` moves
by ``(w_s + theta_s d_s(p)) n_s``, with ``d_s(p)`` its chordwise distance
from the station's elastic-axis node along the toward-leading-edge axis and
``n_s`` the toward-suction axis. Between two stations the two motions are
blended linearly in the point's span coordinate; outside the station range
the end station's motion holds (the structure states nothing beyond its
stations, so nothing is extrapolated). At a structural node the field equals
the row the mapped route writes for it, exactly.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np

from pyflightstream.fsi import nodes
from pyflightstream.fsi.errors import FsiInputError

__all__ = [
    "AERO_NODES_FILE",
    "AERO_NODE_COLUMNS",
    "read_aero_nodes",
    "translations_at_points",
]

#: The aerodynamic nodes file the solver writes in direct mode, in the
#: aeroelastic working directory: a header, then one row per morphed vertex
#: with :data:`AERO_NODE_COLUMNS` comma separated values (position, unit
#: normal, force), positions in the frame the direct command named.
AERO_NODES_FILE = "FSInodes.txt"
AERO_NODE_COLUMNS = 9


def read_aero_nodes(path: str | Path) -> np.ndarray:
    """Read the vertex positions of the solver's aerodynamic nodes file.

    Parameters
    ----------
    path : str or Path
        The :data:`AERO_NODES_FILE` the solver wrote for this call.

    Returns
    -------
    numpy.ndarray
        Shape ``(rows, 3)``: the X, Y, Z of every row, in file order [m].

    Raises
    ------
    FsiInputError
        If the file is missing or holds no row of :data:`AERO_NODE_COLUMNS` numbers.
    """
    source = Path(path)
    if not source.is_file():
        raise FsiInputError(
            f"the run folder is configured for direct morphing and holds no {source.name}: the "
            "solver writes it before every structural call when the script set direct mesh "
            "morphing, so this folder's script did not, or the call ran elsewhere"
        )
    rows = []
    for line in source.read_text(encoding="utf-8", errors="replace").splitlines():
        values = _numbers(line)
        if values is not None and len(values) == AERO_NODE_COLUMNS:
            rows.append(values[:3])
    if not rows:
        raise FsiInputError(
            f"{source.name} holds no row of {AERO_NODE_COLUMNS} comma separated numbers "
            "(X, Y, Z, nx, ny, nz, Fx, Fy, Fz); it is not the aerodynamic nodes file of a "
            "direct morphing call"
        )
    return np.asarray(rows, dtype=float)


def _numbers(line: str) -> list[float] | None:
    """Return a comma separated line's numbers, or None for any other line."""
    parts = [part.strip() for part in line.split(",")]
    if len(parts) < 2:
        return None
    try:
        return [float(part) for part in parts]
    except ValueError:
        return None


def translations_at_points(
    layout: nodes.NodeOrderingMap,
    solutions: Sequence[Any],
    points: np.ndarray,
) -> np.ndarray:
    """Evaluate one blade's beam solution at arbitrary points of its surface.

    Parameters
    ----------
    layout : NodeOrderingMap
        The structural layout of the configuration: its stations, the
        elastic-axis node of each and the section axes.
    solutions : sequence
        One structural solution, carrying ``flap_deflection_m`` and
        ``elastic_twist_rad`` per station; direct morphing couples one blade.
    points : numpy.ndarray
        Shape ``(rows, 3)``: the undeformed points, in the frame the layout
        places its nodes in [m].

    Returns
    -------
    numpy.ndarray
        Shape ``(rows, 3)``: the translation of every point [m].

    Raises
    ------
    FsiInputError
        If the layout or the solutions describe more than one blade.
    """
    if layout.blade_count != 1 or len(solutions) != 1:
        raise FsiInputError(
            f"direct morphing couples one blade; the layout holds {layout.blade_count} and "
            f"the solve returned {len(solutions)}"
        )
    triads = nodes.station_triads(layout)
    elastic_axis = nodes.node_positions(layout)[:: len(layout.roles)]
    flap = np.asarray(solutions[0].flap_deflection_m, dtype=float)
    twist = np.asarray(solutions[0].elastic_twist_rad, dtype=float)
    points = np.asarray(points, dtype=float)
    radii = np.asarray(layout.station_radii_m, dtype=float)
    origin = np.asarray(layout.origin_m or (0.0, 0.0, 0.0), dtype=float)
    span = (points - origin) @ triads[0, 2]
    upper = np.clip(np.searchsorted(radii, span, side="right"), 1, len(radii) - 1)
    lower = upper - 1
    weight = np.clip((span - radii[lower]) / (radii[upper] - radii[lower]), 0.0, 1.0)

    def motion(station: np.ndarray) -> np.ndarray:
        chordwise = np.einsum("ij,ij->i", points - elastic_axis[station], triads[station, 0])
        normal = flap[station] + twist[station] * chordwise
        return normal[:, None] * triads[station, 1]

    return (1.0 - weight)[:, None] * motion(lower) + weight[:, None] * motion(upper)
