"""Full-quad spinner and nacelle sectors, and the power-off body made of them (PFS-2186.06).

Pipeline role: the body half of ``pyfs-workspace geometry sector-remesh`` and the whole of
``pyfs-workspace geometry power-off-body``. A sector spans its own angle about the axis; the two
seam sides of every surface carry nodes at the same meridian positions, so the copies merge and
the mesh has the sector's periodicity. A pole is closed by a kite of quads, the sectors meeting
at the pole node. The nacelle is built by one function, called with the same arguments by both
verbs, which is what makes the nacelle of the remeshed wheel and of the body the same nodes.
Around a blade the spinner is an O-grid between the blade's root loop and a rectangle of the
(meridian, azimuth) plane, smoothed by Winslow's equations; the root loop is given and never
moved, so the spinner adapts to the blade.

The method is the one that produced the accepted full-wheel mesh (see docs/geometry.md). Scipy
is imported inside the functions that need it, so importing the package does not load it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy
from numpy.typing import NDArray

from pyflightstream._errors import InputValueError
from pyflightstream.workspace._sector_read import Sector, radius_of, wrap
from pyflightstream.workspace._sector_save import QuadSink

__all__ = [
    "Builder",
    "FoldedGridError",
    "Meridian",
    "NacelleSpec",
    "SpinnerSpec",
    "nacelle",
    "seam_meridian",
    "spinner_closed",
    "spinner_with_root",
]

Array = NDArray[numpy.float64]


class FoldedGridError(ValueError):
    """The spinner's O-grid folded: the layers around the blade root are too few."""


@dataclass
class SpinnerSpec:
    """The spinner's cell counts and its two lengths, in the mesh unit."""

    theta: int
    rings: int
    layers: int = 4
    margin: float = 0.0
    nose: float = 0.0


@dataclass
class NacelleSpec:
    """The nacelle's cell counts and the groups of its rim and base in the physics block."""

    theta: int
    cells: int
    rim_group: int
    base_group: int


class Meridian:
    """x(s) and r(s) along a surface's seam line, s the arc length from its first point."""

    def __init__(self, x: Any, r: Any) -> None:
        from scipy.interpolate import PchipInterpolator

        x, r = numpy.asarray(x, float), numpy.asarray(r, float)
        self.s = numpy.r_[0.0, numpy.cumsum(numpy.hypot(numpy.diff(x), numpy.diff(r)))]
        self.length = float(self.s[-1])
        self._x, self._r = PchipInterpolator(self.s, x), PchipInterpolator(self.s, r)

    def point(self, s: Any) -> tuple[Any, Any]:
        """Return the axial coordinate and the radius at arc length ``s``."""
        return self._x(s), self._r(s)

    def s_of_x(self, x: Any) -> Any:
        """Return the arc length at axial coordinate ``x``."""
        grid = numpy.linspace(0, self.length, 4001)
        return numpy.interp(x, self._x(grid), grid)

    def s_of_r(self, r: float, s_max: float) -> float:
        """Return the arc length, up to ``s_max``, at radius ``r``."""
        grid = numpy.linspace(0, s_max, 2001)
        return float(numpy.interp(r, self._r(grid), grid))

    def s_at_radius(self, r: float) -> float:
        """Return the first arc length where the radius reaches ``r``."""
        grid = numpy.linspace(0, self.length, 4001)
        return float(grid[numpy.argmax(self._r(grid) >= r)])


def seam_meridian(sector: Sector, nodes: Any, *, pole: bool) -> Meridian:
    """Return the meridian of a surface from its nodes on the sector's low seam.

    With ``pole`` the line starts at the surface's axial minimum on the axis (a spinner).
    """
    q = sector.q[nodes]
    low = sector.centre - 0.5 * sector.span
    on = numpy.abs(wrap(numpy.arctan2(q[:, 2], q[:, 1]) - low)) < 0.2 / 60.0 * sector.span
    r = radius_of(q)
    keep = on & (r > 1e-6 * float(r.max()))
    order = numpy.argsort(q[keep, 0])
    a, rad = q[keep, 0][order], r[keep][order]
    good = numpy.r_[True, numpy.diff(a) > 1e-7 * float(numpy.ptp(q[:, 0]))]
    a, rad = a[good], rad[good]
    if pole:
        a, rad = numpy.r_[float(q[:, 0].min()), a], numpy.r_[0.0, rad]
    return Meridian(a, rad)


class Builder:
    """Collects nodes after the given ones, and quads, oriented outward, into a sink.

    ``centre`` and ``half`` are the sector's middle azimuth and half angle. A quad is turned
    outward by comparing its normal with the direction from a point of the axis ``reach`` ahead
    of it (the owners in ``forward``, whose end faces the flow) or behind it (the others): that
    point is inside the body for a cap and for a flank alike when ``reach`` is a body radius or
    two.
    """

    def __init__(
        self,
        given: Array,
        sink: QuadSink,
        angles: tuple[float, float],
        reach: float,
        forward: set[int],
    ) -> None:
        self.given, self.first, self.sink = given, len(given), sink
        self.centre, self.half = angles
        self.reach, self.forward = reach, forward
        self.nodes: list[Array] = []

    def node(self, p: Any) -> int:
        """Add a node and return its id."""
        self.nodes.append(numpy.asarray(p, float))
        return self.first + len(self.nodes) - 1

    def position(self, nid: int) -> Array:
        """Return the position of a node, given or added."""
        return self.given[nid] if nid < self.first else self.nodes[nid - self.first]

    def all_nodes(self) -> Array:
        """Return the given nodes and the added ones."""
        extra = numpy.array(self.nodes).reshape(-1, 3)
        return numpy.vstack([self.given, extra]) if self.first else extra

    def polar(self, x: float, r: float, phi: float) -> Array:
        """Return the point at axial ``x``, radius ``r``, azimuth ``phi`` from the middle."""
        psi = self.centre + phi
        return numpy.array([x, r * math.cos(psi), r * math.sin(psi)])

    def add(
        self,
        nodes: tuple[int, int, int, int],
        owner: int,
        *,
        kind: int = 0,
        group: int = 0,
        rim: tuple[int, int] | None = None,
    ) -> None:
        """Add a quad turned outward."""
        a, b, c, d = nodes
        q = [self.position(n) for n in nodes]
        centre = numpy.mean(q, axis=0)
        ahead = self.reach if owner in self.forward else -self.reach
        inside = numpy.array([centre[0] + ahead, 0.0, 0.0])
        if numpy.dot(numpy.cross(q[2] - q[0], q[3] - q[1]), centre - inside) < 0:
            b, d = d, b
        self.sink.quad((a, b, c, d), owner, kind=kind, group=group, rim=rim)


def _transfinite(grid: dict[tuple[int, int], int], b: Builder, m: int, i: int, j: int) -> Array:
    """Return the Coons patch point of the kite at (i, j) from its four sides, in the plane."""
    pos = lambda key: b.position(grid[key])[1:]  # noqa: E731
    u, v = i / m, j / m
    return (
        (1 - v) * pos((i, 0))
        + v * pos((i, m))
        + (1 - u) * pos((0, j))
        + u * pos((m, j))
        - (
            (1 - u) * (1 - v) * pos((0, 0))
            + u * (1 - v) * pos((m, 0))
            + (1 - u) * v * pos((0, m))
            + u * v * pos((m, m))
        )
    )


def kite(
    b: Builder,
    owner: int,
    ring: list[int],
    pole: tuple[Any, ...],
    inner: Any,
    *,
    marks: tuple[int, int] = (0, 0),
) -> None:
    """Quads of the wedge between a ring (2m cells over the sector) and a pole node.

    ``pole`` is the pole point and the m-1 points of each side line from the pole out; ``inner``
    maps a point of the plane onto the surface; ``marks`` is the (kind, group) of every quad.
    """
    n = len(ring) - 1
    m = n // 2
    grid: dict[tuple[int, int], int] = {}
    hub = b.node(pole[0])
    sides = [
        [hub, *[b.node(p) for p in line], end]
        for line, end in zip(pole[1:], (ring[0], ring[-1]), strict=True)
    ]
    for i in range(m + 1):
        grid[(i, 0)], grid[(0, i)] = sides[0][i], sides[1][i]
        grid[(m, i)], grid[(i, m)] = ring[i], ring[n - i]
    for i in range(1, m):
        for j in range(1, m):
            grid[(i, j)] = b.node(inner(_transfinite(grid, b, m, i, j)))
    for i in range(m):
        for j in range(m):
            nodes = (grid[(i, j)], grid[(i + 1, j)], grid[(i + 1, j + 1)], grid[(i, j + 1)])
            b.add(nodes, owner, kind=marks[0], group=marks[1])


def sector_rings(
    b: Builder,
    owner: int,
    mer: Meridian,
    stations: Any,
    count: int,
    *,
    first: list[int] | None = None,
    rim: tuple[int, int] | None = None,
) -> list[int]:
    """Rings at the stations, quads between them; returns the last ring.

    ``first`` is the ring of the first station when it exists already; ``rim`` is the (kind,
    group) of the last ring's trailing-edge edge, flagged on its quads.
    """
    phis = numpy.linspace(-b.half, b.half, count + 1)

    def ring_at(s: float) -> list[int]:
        x, r = float(mer.point(s)[0]), float(mer.point(s)[1])
        return [b.node(b.polar(x, r, t)) for t in phis]

    prev = first if first is not None else ring_at(stations[0])
    for k in range(1, len(stations)):
        ring = ring_at(stations[k])
        end = rim is not None and k == len(stations) - 1
        for j in range(count):
            nodes = (prev[j], ring[j], ring[j + 1], prev[j + 1])
            if end and rim is not None:
                b.add(nodes, owner, kind=rim[0], group=rim[1], rim=(ring[j], ring[j + 1]))
            else:
                b.add(nodes, owner)
        prev = ring
    return prev


def nose(b: Builder, owner: int, mer: Meridian, s_ring: float, ring: list[int]) -> None:
    """Kite from a ring at arc length ``s_ring`` to the pole."""
    m = (len(ring) - 1) // 2
    lines = [
        [
            b.polar(
                float(mer.point(s_ring * i / m)[0]),
                float(mer.point(s_ring * i / m)[1]),
                sign * b.half,
            )
            for i in range(1, m)
        ]
        for sign in (-1, 1)
    ]

    def inner(p: Array) -> Array:
        r = float(numpy.hypot(*p))
        return numpy.array([float(mer.point(mer.s_of_r(r, s_ring))[0]), p[0], p[1]])

    kite(b, owner, ring, (numpy.array([float(mer.point(0.0)[0]), 0.0, 0.0]), *lines), inner)


def _kite_station(mer: Meridian, radius: float, rings_from: float) -> float:
    """Return the arc length of the nose kite's ring, which lies ahead of the first ring.

    A radius the spinner never reaches, or none at all, puts the ring on the pole and every
    face of the kite on one point; a ring behind ``rings_from`` folds the rings back over it.

    Raises
    ------
    InputValueError
        The ring is not on the spinner between the pole and the rings.
    """
    station = mer.s_at_radius(radius)
    if not 0.0 < station < rings_from:
        raise InputValueError(
            f"the nose kite's radius {radius:g}, in the mesh's unit, is not on the spinner ahead "
            "of its rings; lower nose_radius_r (CLI: --nose-radius-r, a fraction of the tip "
            "radius) to a small positive one, lower root_margin_r (CLI: --root-margin-r), or "
            "state the tip radius (CLI: --tip-radius). No file was written."
        )
    return station


def winslow(grid: Array, sweeps: int = 3000, relax: float = 0.4) -> Array:
    """Winslow smoothing of an O-grid (layers, loop, 2), periodic along the loop.

    The inner and outer loops stay fixed. Plain Laplace smoothing in index space folded on the
    same loop, which is why this one is used.
    """
    g = grid.copy()
    for _ in range(sweeps):
        up, down, mid = g[2:], g[:-2], g[1:-1]
        ahead, back = numpy.roll(mid, -1, axis=1), numpy.roll(mid, 1, axis=1)
        d_xi, d_eta = 0.5 * (ahead - back), 0.5 * (up - down)
        alpha = numpy.sum(d_eta * d_eta, axis=2, keepdims=True)
        beta = numpy.sum(d_xi * d_eta, axis=2, keepdims=True)
        gamma = numpy.sum(d_xi * d_xi, axis=2, keepdims=True)
        cross = 0.25 * (
            numpy.roll(up, -1, axis=1)
            - numpy.roll(up, 1, axis=1)
            - numpy.roll(down, -1, axis=1)
            + numpy.roll(down, 1, axis=1)
        )
        new = (alpha * (ahead + back) + gamma * (up + down) - 2.0 * beta * cross) / (
            2.0 * (alpha + gamma)
        )
        g[1:-1] = mid + relax * (new - mid)
    return g


def _rectangle(s_front: float, s_end: float, half_v: float, shape: tuple[int, int]) -> Array:
    """Return the rectangle of the (meridian, azimuth) plane as a loop of n_s by n_t cells."""
    n_s, n_t = shape
    su = numpy.linspace(s_front, s_end, n_s + 1)
    tv = numpy.linspace(-half_v, half_v, n_t + 1)
    return numpy.array(
        [(s, tv[0]) for s in su[:-1]]
        + [(su[-1], t) for t in tv[:-1]]
        + [(s, tv[-1]) for s in su[:0:-1]]
        + [(su[0], t) for t in tv[:0:-1]]
    )


def _shoelace(loop: Array) -> float:
    return float(
        0.5
        * numpy.sum(
            loop[:, 0] * numpy.roll(loop[:, 1], -1) - numpy.roll(loop[:, 0], -1) * loop[:, 1]
        )
    )


def _folded_cells(grid: Array) -> int:
    """Count the O-grid cells whose orientation differs from the median's."""
    a = numpy.roll(grid[:-1], -1, axis=1) - grid[:-1]
    c = grid[1:] - grid[:-1]
    cells = a[:, :, 0] * c[:, :, 1] - a[:, :, 1] * c[:, :, 0]
    return int((cells * numpy.sign(numpy.median(cells)) <= 0).sum())


@dataclass
class _OGrid:
    """The smoothed O-grid in the (meridian, azimuth) plane and how it meets the rectangle."""

    grid: Array
    rect_ids: Any
    s_front: float
    r_ref: float


def _o_grid(b: Builder, mer: Meridian, root: list[int], spec: SpinnerSpec) -> _OGrid:
    """Build and smooth the O-grid between the root loop and the rectangle; refuse a folded one."""
    n_loop = len(root)
    n_s = n_loop // 2 - spec.theta
    xyz = numpy.array([b.position(n) for n in root])
    s_loop = mer.s_of_x(xyz[:, 0])
    s_front = float(s_loop.min() - spec.margin)
    _kite_station(mer, spec.nose, s_front)
    r_ref = float(mer.point(0.5 * (s_front + mer.length))[1])
    phi = wrap(numpy.arctan2(xyz[:, 2], xyz[:, 1]) - b.centre)
    loop_uv = numpy.c_[s_loop, r_ref * phi]
    rect = _rectangle(s_front, mer.length, b.half * r_ref, (n_s, spec.theta))
    ids = numpy.arange(n_loop)
    if _shoelace(loop_uv) * _shoelace(rect) < 0:
        rect, ids = rect[::-1], ids[::-1]
    best = min(
        range(n_loop), key=lambda k: float(numpy.sum((numpy.roll(rect, k, axis=0) - loop_uv) ** 2))
    )
    rect, ids = numpy.roll(rect, best, axis=0), numpy.roll(ids, best)
    t = numpy.linspace(0, 1, spec.layers + 1) ** 1.3
    grid = winslow(numpy.array([(1 - tk) * loop_uv + tk * rect for tk in t]))
    folded = _folded_cells(grid)
    if folded:
        raise FoldedGridError(
            f"the spinner O-grid folded in {folded} cells with {spec.layers} layers; raise "
            "--spinner-layers (spinner_layers)"
        )
    return _OGrid(grid, ids, s_front, r_ref)


def spinner_with_root(
    b: Builder, owner: int, mer: Meridian, root: list[int], spec: SpinnerSpec
) -> int:
    """O-grid around the root loop, rings forward, kite at the nose; returns the O-grid cells.

    The loop must have ``2 * (theta + n_s)`` nodes, ``n_s`` being its extent in cells along
    the meridian. Raises :class:`FoldedGridError` before adding anything when the grid folds.
    """
    og = _o_grid(b, mer, root, spec)
    n_loop, layers = len(root), spec.layers
    ids = numpy.zeros((layers + 1, n_loop), dtype=int)
    ids[0] = root
    for k in range(1, layers + 1):
        for j in range(n_loop):
            s, v = og.grid[k, j]
            ids[k, j] = b.node(
                b.polar(float(mer.point(s)[0]), float(mer.point(s)[1]), v / og.r_ref)
            )
    for k in range(layers):
        for j in range(n_loop):
            j1 = (j + 1) % n_loop
            b.add((int(ids[k, j]), int(ids[k + 1, j]), int(ids[k + 1, j1]), int(ids[k, j1])), owner)
    by_rect = {int(og.rect_ids[j]): int(ids[layers, j]) for j in range(n_loop)}
    front = [by_rect[0]] + [by_rect[(n_loop - i) % n_loop] for i in range(1, spec.theta + 1)]
    s_kite = _kite_station(mer, spec.nose, og.s_front)
    stations = s_kite + (og.s_front - s_kite) * numpy.linspace(1, 0, spec.rings + 1) ** 1.25
    last = sector_rings(b, owner, mer, stations, spec.theta, first=front)
    nose(b, owner, mer, float(stations[-1]), last)
    return 0


def spinner_closed(b: Builder, owner: int, mer: Meridian, spec: SpinnerSpec) -> None:
    """Blades off: rings from the aft edge to the nose kite, no hole, even cells."""
    s_kite = _kite_station(mer, spec.nose, mer.length)
    stations = s_kite + (mer.length - s_kite) * numpy.linspace(1, 0, spec.rings + 1) ** 1.25
    last = sector_rings(b, owner, mer, stations, spec.theta)
    nose(b, owner, mer, float(stations[-1]), last)


def nacelle(b: Builder, owner: int, mer: Meridian, spec: NacelleSpec) -> None:
    """Add the nacelle, the same with and without blades: rings, flagged rim, base kite.

    Rings are finer at the front, where the surface curves; the aft rim carries kind 1 and the
    rim group; the flat base is closed by a kite of kind 3 and the base group.
    """
    stations = mer.length * numpy.linspace(0.0, 1.0, spec.cells + 1) ** 1.4
    last = sector_rings(b, owner, mer, stations, spec.theta, rim=(1, spec.rim_group))
    x_e, r_e = float(mer.point(mer.length)[0]), float(mer.point(mer.length)[1])
    m = spec.theta // 2
    lines = [[b.polar(x_e, r_e * i / m, sign * b.half) for i in range(1, m)] for sign in (-1, 1)]
    kite(
        b, owner, last, (numpy.array([x_e, 0.0, 0.0]), *lines),
        lambda p: numpy.array([x_e, p[0], p[1]]), marks=(3, spec.base_group),
    )  # fmt: skip
