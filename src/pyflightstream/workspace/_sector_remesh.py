"""The blade of a sector rebuilt as full quads, with its distribution (PFS-2186.06).

Pipeline role: ``pyfs-workspace geometry sector-remesh``. The saved sector supplies the surface
only, never the distribution: the blade's chord rings are read from its quad grid, each section
is a monotonic spline of arc length on each side, and the new rows are placed by

* chord: geometric growth from the leading edge to mid-chord, then one fixed width to the
  trailing edge (the trailing edge is not refined), the same fractions on every row;
* span: constant cells, a short geometric region finer towards the tip;
* cuts: every row at one radius from mid blade outward, blending from the root row inboard;
* the root row follows the chord law and the spinner adapts to it, never the reverse.

One side carries one chord cell more than the other, so that a ring has an even number of edges
and the spinner's O-grid and the tip cap close with quads alone. The base between the two
trailing edges is one row of quads flagged from root to tip.

THE TOPOLOGY OF THIS RELEASE is stated in :mod:`pyflightstream.workspace._sector_read`: a blunt
trailing edge, rims from the root loop, one blade per sector, a nacelle with a flat base. A
sector without it is warned, naming what was not found, and nothing is written. A sharp
trailing edge (no base strip, one rim) is not covered yet.

THE SAVED LAYOUT IS INFERRED FROM SAVED FILES; see :mod:`pyflightstream.workspace._sector_save`.
Scipy is imported inside the functions that use it.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any

import numpy
from numpy.typing import NDArray

from pyflightstream._errors import InputValueError
from pyflightstream.workspace._sector_read import (
    Sector,
    TopologyNotFoundError,
    radius_of,
)
from pyflightstream.workspace._wheel import _NOTHING

__all__ = ["BladeSource", "Grid", "Plan", "blade_grid", "chord_fractions", "read_blade"]

Array = NDArray[numpy.float64]
Edge = tuple[int, int]


@dataclass
class Plan:
    """The distribution asked for, all lengths in the mesh's unit."""

    chord_cells: int
    le: float
    span_cell: float
    tip_ratio: float
    tip_length: float
    tip_radius: float


def _edge(a: Any, b: Any) -> Edge:
    a, b = int(a), int(b)
    return (a, b) if a < b else (b, a)


def _tri_edges(t: Any) -> tuple[Edge, Edge, Edge]:
    return _edge(t[0], t[1]), _edge(t[1], t[2]), _edge(t[2], t[0])


def _need(ok: bool, what: str) -> None:
    if not ok:
        raise TopologyNotFoundError(what)


# --- the blade of the source ---------------------------------------------------------------


@dataclass
class BladeSource:
    """What is read from the source blade: its rim lines, groups and the faces it left out."""

    rim_a: list[int]
    rim_b: list[int]
    groups: tuple[int, int]
    base_group: int
    skipped: int
    root_offset: float


def _quads_of(sector: Sector, faces: Any) -> tuple[list[list[Edge]], dict[Edge, list[int]], int]:
    """Return the blade's quads as outer edges, an index by edge, and the unpaired faces skipped."""
    quads: list[list[Edge]] = []
    by_edge: dict[Edge, list[int]] = defaultdict(list)
    seen: set[int] = set()
    skipped = 0
    for f in faces.tolist():
        p = int(sector.partner[f]) - 1
        if f in seen:
            continue
        if p < 0 or int(sector.owner[p]) != sector.blade:
            skipped += 1
            continue
        seen.update((f, p))
        count = Counter(e for t in (sector.tri[f], sector.tri[p]) for e in _tri_edges(t))
        outer = [e for e, v in count.items() if v == 1]
        for e in outer:
            by_edge[e].append(len(quads))
        quads.append(outer)
    _need(bool(quads), "a blade made of quad pairs")
    return quads, by_edge, skipped


def _rim_lines(sector: Sector, faces: Any) -> dict[int, list[Edge]]:
    """Return the flagged trailing-edge edges of the blade by trailing-edge group."""
    found: dict[int, set[Edge]] = defaultdict(set)
    for slot, (i, j) in enumerate(((0, 1), (1, 2), (2, 0))):
        flag = sector.flag(slot)
        for f in faces[flag[faces]].tolist():
            found[int(sector.group[f])].add(_edge(sector.tri[f][i], sector.tri[f][j]))
    _need(
        len(found) == 2,
        "two trailing-edge rim lines on the blade (a blunt trailing edge; a sharp one is not "
        f"covered yet), found {len(found)}",
    )
    return {g: sorted(e) for g, e in found.items()}


def _chain(edges: list[Edge], radius: Array) -> list[int]:
    """Return the nodes of an open chain of edges, from its end nearest the axis."""
    nb: dict[int, list[int]] = defaultdict(list)
    for a, b in edges:
        nb[a].append(b)
        nb[b].append(a)
    ends = [n for n, v in nb.items() if len(v) == 1]
    _need(
        len(ends) == 2 and all(len(v) <= 2 for v in nb.values()),
        "each trailing-edge rim line one open chain from the root",
    )
    out: list[int] = [min(ends, key=lambda n: float(radius[n]))]
    prev = None
    while True:
        nxt = [x for x in nb[out[-1]] if x != prev]
        if not nxt:
            return out
        prev = out[-1]
        out.append(nxt[0])


@dataclass
class _Quads:
    """The blade's quads as outer edges, an index of them by edge, and the far rim line's edges."""

    edges: list[list[Edge]]
    by_edge: dict[Edge, list[int]]
    rim_b: set[Edge]


def _walk(s: int, rim_a: list[int], quads: _Quads) -> tuple[list[int], list[int]]:
    """Walk the strip between rim stations ``s`` and ``s + 1`` from rim line a to rim line b.

    Returns the ring of station ``s`` and that of station ``s + 1``, each from rim line a.
    """
    e = _edge(rim_a[s], rim_a[s + 1])
    here, there = rim_a[s], rim_a[s + 1]
    q = next(q for q in quads.by_edge[e] if not any(x in quads.rim_b for x in quads.edges[q]))
    lo, hi = [here], [there]
    for _ in quads.edges:  # a strip that closes on itself never meets the far rim line
        opp = next(x for x in quads.edges[q] if not set(x) & set(e))
        rail = next(x for x in quads.edges[q] if here in x and x != e)
        here = rail[0] if rail[1] == here else rail[1]
        there = opp[0] if opp[1] == here else opp[1]
        lo.append(here)
        hi.append(there)
        if opp in quads.rim_b:
            return lo, hi
        q = next(x for x in quads.by_edge[opp] if x != q)
        e = opp
    raise TopologyNotFoundError("a chord strip that runs from one rim line to the other")


def _chord_rings(rim_a: list[int], rim_b: list[int], quads: _Quads) -> NDArray[numpy.int64]:
    """Return the rings, one per rim station, each from rim line a round the leading edge to b."""
    quads.rim_b = {_edge(a, b) for a, b in zip(rim_b[:-1], rim_b[1:], strict=True)}
    try:
        walks = [_walk(s, rim_a, quads) for s in range(len(rim_a) - 1)]
    except (StopIteration, KeyError, IndexError) as error:
        raise TopologyNotFoundError(
            "a blade grid that runs from one trailing-edge rim line to the other"
        ) from error
    rings = [lo for lo, _ in walks] + [walks[-1][1]]
    _need(len({len(r) for r in rings}) == 1, "rings of one length along the span")
    _need(len(rings[0]) % 2 == 1, "rings with an odd number of nodes (equal cells on both sides)")
    return numpy.array(rings)


def _root_loop(sector: Sector, faces: Any) -> list[int]:
    """Return the closed loop of the blade's boundary edges whose nodes are on the spinner."""
    on = set(numpy.unique(sector.tri[sector.owner == sector.spinner]).tolist())
    count = Counter(e for f in faces.tolist() for e in _tri_edges(sector.tri[f]))
    edges = [e for e, v in count.items() if v == 1 and e[0] in on and e[1] in on]
    nb: dict[int, list[int]] = defaultdict(list)
    for a, b in edges:
        nb[a].append(b)
        nb[b].append(a)
    _need(bool(edges) and all(len(v) == 2 for v in nb.values()), "one closed root loop")
    loop: list[int] = [edges[0][0]]
    prev = None
    while len(loop) <= len(edges):
        nxt = [x for x in nb[loop[-1]] if x != prev]
        if nxt[0] == loop[0] and len(loop) > 2:
            break
        prev = loop[-1]
        loop.append(nxt[0])
    _need(len(loop) == len(edges), "one closed root loop (a single component)")
    return loop


def _align_root(q: Array, loop: list[int], ring: Any) -> tuple[Any, float]:
    """Return the root loop as a ring (trying every shift and direction) and its largest offset."""
    ids = numpy.array(loop)
    ref = q[ring] - q[ring].mean(0)
    best: tuple[float, Any] | None = None
    for direction in (1, -1):
        for shift in range(len(ids)):
            cand = numpy.roll(ids[::direction], shift)
            d = float(numpy.linalg.norm((q[cand] - q[cand].mean(0)) - ref, axis=1).max())
            if best is None or d < best[0]:
                best = (d, cand)
    assert best is not None
    return best[1], best[0]


def read_blade(sector: Sector) -> tuple[BladeSource, NDArray[numpy.int64]]:
    """Read the blade's rings from the source quad grid.

    Returns the source description and the node ids of all rings, the root loop's first.

    Raises
    ------
    TopologyNotFoundError
        The blade is not a quad grid between two rim lines that start on the root loop.
    """
    faces = numpy.flatnonzero(sector.owner == sector.blade)
    edges, by_edge, skipped = _quads_of(sector, faces)
    lines = _rim_lines(sector, faces)
    ga, gb = sorted(lines)
    radius = radius_of(sector.q)
    rim_a, rim_b = _chain(lines[ga], radius), _chain(lines[gb], radius)
    _need(len(rim_a) == len(rim_b), "rim lines with the same number of nodes")
    rings = _chord_rings(rim_a, rim_b, _Quads(edges, by_edge, set()))
    loop = _root_loop(sector, faces)
    _need(len(loop) == rings.shape[1], "a root loop with as many nodes as a ring")
    root, offset = _align_root(sector.q, loop, rings[0])
    _need({rim_a[0], rim_b[0]} <= set(root.tolist()), "rim lines that start on the root loop")
    base = sector.group[faces[sector.kind[faces] == 3]]
    _need(len(set(base.tolist())) == 1, "one base region on the blade (the base strip)")
    source = BladeSource(rim_a, rim_b, (ga, gb), int(base[0]), skipped, offset)
    return source, numpy.vstack([root[None, :], rings])


# --- the distribution --------------------------------------------------------------------


def geometric(count: int, first: float, total: float) -> Array:
    """Return node positions 0..total of cells growing by one ratio from a first cell."""
    from scipy.optimize import brentq

    def total_error(g: float) -> float:
        return first * (g**count - 1) / (g - 1) - total

    ratio = brentq(total_error, 1.0 + 1e-7, 100.0)
    return numpy.r_[0.0, numpy.cumsum(first * ratio ** numpy.arange(count))]


def chord_fractions(cells: int, le: float) -> Array:
    """Return chord fractions from the leading edge: growth to mid-chord, then one fixed width.

    The split between growing and fixed cells is the one where the last growing cell comes
    closest to the fixed width without exceeding it, which keeps the widths monotonic.

    Raises
    ------
    InputValueError
        No split reaches a fixed width at mid-chord.
    """
    best: tuple[float, Array, int, float] | None = None
    for fixed in range(3, cells - 3):
        grow_n = cells - fixed
        if le * grow_n >= 0.5:
            continue
        try:
            grow = geometric(grow_n, le, 0.5)
        except ValueError:  # brentq: no growth reaches mid-chord from this first cell
            continue
        size = 0.5 / fixed
        last = grow[-1] - grow[-2]
        if last <= size and (best is None or size - last < best[0]):
            best = (size - last, grow, fixed, size)
    if best is None:
        raise InputValueError(
            f"chord-cells {cells} with le {le:g} give no growth that reaches a fixed width at "
            f"mid-chord; use more chord cells or a larger le. {_NOTHING}"
        )
    _, grow, fixed, size = best
    return numpy.r_[grow, 0.5 + size * numpy.arange(1, fixed + 1)]


def span_rows(root: float, plan: Plan) -> Array:
    """Return the rows' radii: constant cells, then a short region growing finer to the tip."""
    cell, length, tip = plan.span_cell, plan.tip_length, plan.tip_radius
    for name, value in (
        ("span-cell", cell),
        ("tip-length", length),
        ("tip-radius", tip),
        ("tip-ratio", plan.tip_ratio),
    ):
        if not (math.isfinite(value) and value > 0.0):
            raise InputValueError(f"--{name} reads {value:g}; write a positive number. {_NOTHING}")
    n_t = int(round(length / (0.5 * (1 + plan.tip_ratio) * cell)))
    n_u = int(round((tip - length - root) / cell))
    if n_t < 1 or n_u < 1:
        raise InputValueError(
            "span-cell and tip-length leave no constant cells between the root and the tip "
            f"region of a blade from radius {root:g} to {tip:g}. {_NOTHING}"
        )
    d_u = (tip - length - root) / n_u
    try:
        fine = length - geometric(n_t, plan.tip_ratio * cell, length)[::-1]
    except ValueError as error:  # brentq: the tip cells already fill the region, with no growth
        raise InputValueError(
            f"--tip-ratio {plan.tip_ratio:g} leaves no growth in the tip region: its cells are "
            f"not finer than the constant one. Use a --tip-ratio below 1. {_NOTHING}"
        ) from error
    return numpy.r_[root + d_u * numpy.arange(n_u), tip - length + fine]


def _pchip() -> Any:
    from scipy.interpolate import PchipInterpolator

    return PchipInterpolator


def _arc_splines(q: Array, rings: Any, n_side: int) -> list[tuple[Any, Any]]:
    """Return, per ring, splines of position against arc fraction on each side from the LE."""
    pchip = _pchip()
    out = []
    for ring in rings:
        p = q[ring]
        pair = []
        for idx in (numpy.arange(n_side, -1, -1), numpy.arange(n_side, 2 * n_side + 1)):
            arc = numpy.r_[0.0, numpy.cumsum(numpy.linalg.norm(numpy.diff(p[idx], axis=0), axis=1))]
            pair.append(pchip(arc / arc[-1], p[idx]))
        out.append((pair[0], pair[1]))
    return out


@dataclass
class Grid:
    """The new blade nodes by row and column, and what the checks need to read them."""

    nodes: Array
    radii: Array
    f_a: Array
    f_b: Array
    mid_row: int


def blade_grid(q: Array, all_rings: Any, plan: Plan) -> Grid:
    """Place the new rows: a point per ring and chord fraction, then along each chord line."""
    pchip = _pchip()
    n_side = (all_rings.shape[1] - 1) // 2
    f_b = chord_fractions(plan.chord_cells, plan.le)
    f_a = chord_fractions(plan.chord_cells + 1, plan.le)
    sections = _arc_splines(q, all_rings, n_side)
    root = float(radius_of(q[all_rings[0]]).mean())
    v_new = span_rows(root, plan)
    pa = numpy.array([s[0](f_a) for s in sections])
    pb = numpy.array([s[1](f_b) for s in sections])
    lines = numpy.concatenate([pa[:, ::-1], pb[:, 1:]], axis=1)
    mid = 0.5 * (root + plan.tip_radius)
    t = numpy.minimum(1.0, (v_new - root) / (mid - root))
    blend = t * t * (3 - 2 * t)
    target = v_new[:, None] + (1 - blend)[:, None] * (radius_of(lines[0])[None, :] - root)
    grid = numpy.zeros((len(v_new), lines.shape[1], 3))
    for j in range(lines.shape[1]):
        rho = radius_of(lines[:, j])
        keep = numpy.r_[True, numpy.diff(numpy.maximum.accumulate(rho)) > 1e-9 * float(rho.max())]
        grid[:, j] = pchip(rho[keep], lines[keep, j], extrapolate=True)(target[:, j])
    grid[0] = lines[0]
    return Grid(grid, v_new, f_a, f_b, int(numpy.argmin(numpy.abs(v_new - mid))))
