"""A saved sector read for remeshing: its surfaces, axis frame and seams (PFS-2186.06).

Pipeline role: the reading half of ``pyfs-workspace geometry sector-remesh`` and ``power-off-body``
(:mod:`pyflightstream.workspace._sector_remesh`, :mod:`pyflightstream.workspace._sector_body`).
The saved layout is the one :mod:`pyflightstream.workspace._wheel_fsm` reads, and its reader is
used as it is; this module adds what remeshing needs on top of it and nothing else.

THE TOPOLOGY OF THIS RELEASE is stated here once and refused by name when a sector lacks it:

* three boundaries: one blade, a spinner and a nacelle (one blade per sector);
* the blade's quads end in two trailing-edge rim lines that start on the root loop, with a base
  strip between them (a blunt trailing edge; a sharp one is not covered yet);
* the spinner is the boundary the blade's root loop lies on; the nacelle is the other one, and it
  holds a flat base (faces of kind 3).

No boundary name, axis, sector angle or length is fixed here. The axis is one of ``x``, ``y``,
``z``; the sector angle is the azimuth range of the spinner and nacelle nodes; the flow direction
is the one from the spinner towards the nacelle's base.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy
from numpy.typing import NDArray

from pyflightstream.workspace._wheel import azimuth_range
from pyflightstream.workspace._wheel_fsm import _parse, _UnrecognizedError

__all__ = ["Frame", "Sector", "TopologyNotFoundError", "read_sector"]

_PERMUTATION = {"x": (0, 1, 2), "y": (1, 2, 0), "z": (2, 0, 1)}
_SNAP_DEG = 0.05  # a sector angle this close to 360/N is 360/N; further, the caller warns
_ON_AXIS = 1e-6  # a node closer to the axis than this fraction of the largest radius is a pole


class TopologyNotFoundError(ValueError):
    """A saved sector that lacks a part of the topology this release remeshes (it names it)."""


@dataclass(frozen=True)
class Frame:
    """The sector's own frame: axial, then two transverse coordinates, right-handed.

    ``local`` sends world points to (axial, t1, t2) with the axis cyclic first; ``flip`` is 1 or
    -1: -1 turns the frame half a turn about t1 so that the flow runs towards larger axial
    values, a proper rotation, so handedness is kept. ``world`` is the inverse of ``local``.
    """

    permutation: tuple[int, int, int]
    flip: float = 1.0

    def local(self, points: NDArray[numpy.float64]) -> NDArray[numpy.float64]:
        """Return the points in the frame."""
        q = numpy.asarray(points, dtype=float)[:, list(self.permutation)].copy()
        q[:, 0] *= self.flip
        q[:, 2] *= self.flip
        return q

    def world(self, q: NDArray[numpy.float64]) -> NDArray[numpy.float64]:
        """Return the points of the frame in the file's own coordinates."""
        r = numpy.asarray(q, dtype=float).copy()
        r[:, 0] *= self.flip
        r[:, 2] *= self.flip
        out = numpy.empty_like(r)
        out[:, list(self.permutation)] = r
        return out


def radius_of(q: NDArray[numpy.float64]) -> NDArray[numpy.float64]:
    """Return the distance of each point from the axis."""
    return numpy.hypot(q[:, 1], q[:, 2])


def azimuth_of(q: NDArray[numpy.float64]) -> NDArray[numpy.float64]:
    """Return the azimuth of each point about the axis, in radians."""
    return numpy.arctan2(q[:, 2], q[:, 1])


def wrap(angle: Any) -> Any:
    """Return an angle (or array) taken to (-pi, pi]."""
    return numpy.pi - numpy.mod(numpy.pi - angle, 2.0 * numpy.pi)


@dataclass
class Sector:
    """A saved sector: the parsed file, the frame, and the surfaces' arrays in that frame.

    ``blade``, ``spinner`` and ``nacelle`` are 1-based boundary positions (the values of the
    saved owner row); ``centre`` and ``span`` are the azimuth of the sector's middle and its
    angle, in radians; ``q`` holds the nodes in the frame.
    """

    path: Path
    parsed: Any
    frame: Frame
    q: NDArray[numpy.float64]
    tri: NDArray[numpy.int64]
    owner: NDArray[numpy.int64]
    kind: NDArray[numpy.int64]
    group: NDArray[numpy.int64]
    partner: NDArray[numpy.int64]
    names: list[str]
    blade: int
    spinner: int
    nacelle: int
    centre: float
    span: float

    @property
    def copies(self) -> int:
        """The number of sectors that make a turn, from the sector angle."""
        return int(round(2.0 * math.pi / self.span))

    def nodes_of(self, boundary: int, *, base: bool = True) -> NDArray[numpy.int64]:
        """Return the node ids of a boundary, without those only on base faces if asked."""
        mask = self.owner == boundary
        if not base:
            mask &= self.kind != 3
        return numpy.unique(self.tri[mask])

    def flag(self, slot: int) -> NDArray[numpy.bool_]:
        """Return which faces carry the trailing-edge flag of an edge slot (rows 21 to 23)."""
        row = self.parsed.mesh["rows"][21 + slot]
        return numpy.array([c == "T" for c in row], dtype=bool)


def _need(ok: bool, what: str) -> None:
    if not ok:
        raise TopologyNotFoundError(what)


def _root_edges(
    tri: NDArray[numpy.int64], owner: NDArray[numpy.int64], blade: int, other: int
) -> int:
    """Count the blade's boundary edges whose both nodes are on another boundary."""
    own = tri[owner == blade]
    nodes = int(tri.max()) + 1
    edges = numpy.sort(numpy.concatenate([own[:, [0, 1]], own[:, [1, 2]], own[:, [2, 0]]]), axis=1)
    key, times = numpy.unique(edges[:, 0] * nodes + edges[:, 1], return_counts=True)
    once = key[times == 1]
    fam = numpy.unique(tri[owner == other])
    return int((numpy.isin(once // nodes, fam) & numpy.isin(once % nodes, fam)).sum())


def _families(
    names: list[str],
    blades: list[str],
    tri: NDArray[numpy.int64],
    owner: NDArray[numpy.int64],
    kind: NDArray[numpy.int64],
) -> tuple[int, int, int]:
    """Return the blade, spinner and nacelle boundary positions, or say what was not found.

    The spinner is the boundary the blade's root loop lies on (the most blade boundary edges
    with both nodes on it); the nacelle is the other one, and it must hold a base (kind 3).
    """
    _need(len(blades) == 1, "one blade per sector (--blades names one boundary)")
    _need(blades[0] in names, f"the blade {blades[0]!r} among the boundaries")
    blade = names.index(blades[0]) + 1
    others = [i for i in range(1, len(names) + 1) if i != blade]
    _need(len(others) == 2, "exactly a spinner and a nacelle beside the blade")
    loops = {o: _root_edges(tri, owner, blade, o) for o in others}
    spinner = max(others, key=lambda o: loops[o])
    nacelle = next(o for o in others if o != spinner)
    _need(loops[spinner] > 0, "a root loop of the blade lying on one boundary (the spinner)")
    _need(bool((kind[owner == nacelle] == 3).any()), "a nacelle with a flat base (faces of kind 3)")
    return blade, spinner, nacelle


def _direction(
    q: NDArray[numpy.float64],
    tri: NDArray[numpy.int64],
    owner: NDArray[numpy.int64],
    kind: NDArray[numpy.int64],
    ids: tuple[int, int],
) -> float:
    """Return 1 when the flow runs towards larger axial values, else -1 (spinner to the base)."""
    base = numpy.unique(tri[(owner == ids[1]) & (kind == 3)])
    front = numpy.unique(tri[owner == ids[0]])
    return 1.0 if q[base, 0].mean() > q[front, 0].mean() else -1.0


def _seams(q: NDArray[numpy.float64], bodies: NDArray[numpy.int64]) -> tuple[float, float]:
    """Return the azimuth of the sector's middle and its angle, from the body nodes' azimuths."""
    r = radius_of(q[bodies])
    keep = r > _ON_AXIS * float(r.max())
    return azimuth_range(azimuth_of(q[bodies][keep]))


def _snapped(span: float) -> float:
    """Return the span taken to exactly 360/N when the seams are within the data's rounding of it.

    Saved coordinates carry rounding of the order of 1e-8, which would leave the seams of the
    copies that far apart; a span within ``_SNAP_DEG`` of 360/N for a whole number N is 360/N.
    A span further than that is kept and warned by the caller.
    """
    n = round(2.0 * math.pi / span)
    if n >= 2 and abs(math.degrees(span) - 360.0 / n) <= _SNAP_DEG:
        return 2.0 * math.pi / n
    return span


def read_sector(path: Path, blades: list[str], axis: str) -> Sector:
    """Read a saved sector and find its blade, spinner, nacelle, frame and seams.

    Raises
    ------
    TopologyNotFoundError
        The layout is not the one the saved route reads, or the sector lacks a part of the
        topology of this release; the message names what was not found.
    """
    try:
        parsed = _parse(path.read_bytes().decode("latin-1"))
    except (_UnrecognizedError, ValueError, IndexError, KeyError) as error:
        raise TopologyNotFoundError(f"a recognized saved layout ({error})") from error
    ints = parsed.mesh["ints"]
    tri = numpy.stack([ints[2], ints[3], ints[4]], axis=1) - 1
    owner, kind = ints[11], ints[12]
    names = [h[4] for h in parsed.mesh["heads"]]
    blade, spinner, nacelle = _families(names, blades, tri, owner, kind)
    frame = Frame(_PERMUTATION[axis])
    q = frame.local(parsed.mesh["xyz"])
    frame = Frame(frame.permutation, _direction(q, tri, owner, kind, (spinner, nacelle)))
    q = frame.local(parsed.mesh["xyz"])
    bodies = numpy.unique(tri[(owner == spinner) | (owner == nacelle)])
    centre, span = _seams(q, bodies)
    _need(span > 0.0, "a sector with an angle about the axis (the bodies have one azimuth)")
    span = _snapped(span)
    return Sector(
        path, parsed, frame, q, tri, owner, kind, ints[5], ints[10], names,
        blade, spinner, nacelle, centre, span,
    )  # fmt: skip
