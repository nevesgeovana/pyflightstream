"""The multiblock grid of an all-quadrilateral family, recovered and resampled.

(FR-915, FR-920, FR-921, FR-923, FR-932).

A family of quadrilaterals that is not one sheet or one tube (a nacelle whose
pylon junction cuts a hole, a fuselage sheet whose boundary has six corners)
is still structured piecewise. Its LAYOUT is found from the connectivity
alone:

1. the SINGULAR vertices are the interior vertices with other than four
   edges or faces, and the boundary vertices with other than two faces (a
   convex corner has one, a re-entrant corner three);
2. from each singular vertex, along each of its interior edges, a SEPARATRIX
   follows the grid line straight through every regular vertex (the edge of
   the four that shares no face with the edge it arrived by) until it reaches
   the boundary or a singular vertex. A grid line through an edge sharper than
   ``_geometry.RIDGE_DEGREES``, or through a trailing-edge edge, is traced the
   same way in both directions, so no spline crosses a ridge;
3. the separatrices and the boundary cut the family into PATCHES, each a
   rectangle of rows by columns of quadrilaterals, and the cut into ARCS,
   each the whole side of one patch or the side two patches share. Lines
   traced to their ends cross one another rather than stopping, so a side
   never meets a corner of the patch beside it: the arcs are the sides.

Resampling (FR-920) keeps that structure: each arc is resampled ONCE, by the
cubic spline of :func:`._grid.not_a_knot` through its source nodes in index
space, to ``round(f m)`` intervals of its m; opposite sides of a patch hold
the same m, so they agree. A patch's interior is the tensor spline of its
nodes, as a single grid's is, and its boundary nodes are the arcs' nodes, so
two patches sharing an arc share its nodes exactly. The source's nodes at
integer parameters are kept bit for bit, the layout's corners among them.
The count of each arc is given per arc (:func:`resample`): ``factor`` applies
to every arc, and ``chordwise`` and ``spanwise`` by the arc's direction, read
from the family's trailing edge (:func:`te_directions`, FR-915, PFS-2150).

Face order (FR-921): every new face takes the position of the source face whose
centroid is nearest (``_geometry.order_like``), each patch oriented like the
source faces it replaces; at factor 1 the family is the source in coordinates
and in order. A family with a face that is not a quadrilateral, or whose
layout is one patch (a sheet or a tube, recovered or refused by
:mod:`._grid`), or whose cut leaves a patch that is not four-sided, has no
multiblock grid, and falls back as before.

GRIDS THAT SHARE NODES ARE RESAMPLED TOGETHER (FR-932). The grid families of
quadrilaterals that touch, sheets and multiblock families alike, are taken
as one surface: the edges where two of them meet are cut, and the grid line
through each is traced on to its end like a separatrix
(:func:`recover_joined`), so the union is cut into four-sided
patches each inside one family, and every curve two families share is the
side of a patch, an ARC, resampled ONCE: both families hold the same nodes on
it. Each new cell is written back to the family of its patch, oriented like
that patch's source faces, and each family's faces are written in its own
source order (FR-921, the nearest source face's position). A lone multiblock
family is the same layout with one family.

THE COUNT OF AN ARC (FR-915) is ``max(1, round(f m))`` of its m source
intervals, f the factor of each family holding it in the arc's direction
(``factor`` in both; a sheet's ``chordwise`` along its stations and
``spanwise`` along its columns, a multiblock family's by its trailing
edge, :func:`te_directions`). Two families giving one arc different counts
are refused naming both and the curve, before any work (FR-925). A side whose
``f m`` is below 1 is kept and reported, as on a lone multiblock family.

A family that cannot join a layout, a tube, a family with a triangle, or one
that keeps its first row (FR-430), and the touching grids whose union is not a
layout of four-sided patches, are left to the rule before this one: the first
of them in the source's family order is a grid, and a later one sharing its
nodes is remeshed, or refused under ``method = "grid"``.

This module imports neither scipy nor rtree (FR-924).
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass

import numpy
from numpy.typing import NDArray

from pyflightstream._errors import InputArtifactError, PyflightstreamWarning, warn
from pyflightstream.workspace._refine._config import FamilySpec
from pyflightstream.workspace._refine._geometry import (
    RIDGE_DEGREES,
    Faces,
    Points,
    dihedral_degrees,
    edge_faces,
    order_like,
)
from pyflightstream.workspace._refine._grid import Grid, GridLevel, not_a_knot, recover_grid
from pyflightstream.workspace._refine._obj import KIND

Edge = tuple[int, int]
#: The four sides of a patch: its first row, its last row, its first column, its last column.
SIDES = ("first row", "last row", "first column", "last column")


class _NoLayoutError(Exception):
    """The reason, as its message, why a family's multiblock layout was not recovered."""


class _OnePatchError(Exception):
    """The layout is a single patch: the family is a sheet or a tube, judged by :mod:`._grid`."""


@dataclass(frozen=True, eq=False)
class Blocks:
    """The multiblock grid of one family, as recovered from its connectivity.

    Attributes
    ----------
    patches : tuple of numpy.ndarray
        Per patch, the source vertex indices, shape (rows + 1, columns + 1).
    cells : tuple of numpy.ndarray
        Per patch, the source face of each cell, shape (rows, columns).
    arcs : tuple of tuple of int
        The source vertex chain of each arc, from one patch corner to another.
    sides : tuple of tuple of (int, bool)
        Per patch, for each of :data:`SIDES`, its arc and whether the side runs
        against the arc's direction.
    te_arcs : frozenset of int
        The arcs whose every edge joins two trailing-edge vertices.
    """

    patches: tuple[NDArray[numpy.int64], ...]
    cells: tuple[NDArray[numpy.int64], ...]
    arcs: tuple[tuple[int, ...], ...]
    sides: tuple[tuple[tuple[int, bool], ...], ...]
    te_arcs: frozenset[int]

    layout = "multiblock"

    def describe(self) -> str:
        """Return the recovery reason of a multiblock grid that was recovered."""
        return f"a multiblock of {len(self.patches)} four-sided patches of quadrilaterals"


# ------------------------------------------------------------- the recovery


def recover_family(
    verts: Points, faces: Faces, te_vertices: Collection[int]
) -> Grid | Blocks | str:
    """Recover a family's grid: a sheet or a tube, else a multiblock grid of quadrilaterals.

    Parameters
    ----------
    verts : numpy.ndarray
        All the mesh's vertices, shape (V, 3).
    faces : list of list of int
        The family's faces, as indices into ``verts``.
    te_vertices : collection of int
        The family's trailing-edge vertices.

    Returns
    -------
    Grid or Blocks or str
        The grid, or the reason no grid was recovered. A family whose faces
        are not all quadrilaterals, or whose layout is one patch, gets the
        reason of :func:`._grid.recover_grid` alone.
    """
    found = recover_grid(verts, faces, te_vertices)
    if isinstance(found, Grid) or any(len(f) != 4 for f in faces):
        return found
    try:
        return _recover(numpy.asarray(verts, dtype=float), faces, frozenset(te_vertices))
    except _OnePatchError:
        return found
    except _NoLayoutError as why:
        return f"{found}; no multiblock layout: {why}"


def _key(a: int, b: int) -> Edge:
    return (a, b) if a < b else (b, a)


@dataclass(frozen=True, eq=False)
class _Topology:
    """The connectivity the layout is traced on."""

    faces: Faces
    emap: Mapping[Edge, list[int]]
    adj: Mapping[int, set[int]]
    stops: frozenset[int]  # the boundary and singular vertices, where a separatrix ends
    singular: tuple[int, ...]

    @classmethod
    def of(cls, faces: Faces) -> _Topology:
        """Return the topology of a family of quadrilaterals."""
        emap = edge_faces(faces)
        if any(len(fs) > 2 for fs in emap.values()):
            raise _NoLayoutError("an edge is shared by more than two faces")
        adj: dict[int, set[int]] = defaultdict(set)
        for a, b in emap:
            adj[a].add(b)
            adj[b].add(a)
        count = Counter(v for f in faces for v in f)
        boundary = {v for e, fs in emap.items() if len(fs) == 1 for v in e}
        singular = sorted(
            v
            for v in adj
            if (v in boundary and count[v] != 2)
            or (v not in boundary and (len(adj[v]) != 4 or count[v] != 4))
        )
        return cls(faces, emap, adj, frozenset(boundary | set(singular)), tuple(singular))

    def straight(self, a: int, b: int) -> int:
        """Return the vertex after b on the grid line a-b, through the regular vertex b."""
        beside = {x for k in self.emap[_key(a, b)] for x in _quad_neighbours(self.faces[k], b)}
        ahead = self.adj[b] - beside - {a}
        if len(ahead) != 1:
            raise _NoLayoutError(f"the grid line through vertex {b + 1} does not go straight on")
        return ahead.pop()

    def trace(self, a: int, b: int) -> list[Edge]:
        """Return the edges of the separatrix leaving a along a-b, to its end."""
        out: list[Edge] = []
        seen: set[tuple[int, int]] = set()
        while (a, b) not in seen:
            seen.add((a, b))
            out.append(_key(a, b))
            if b in self.stops:
                break
            a, b = b, self.straight(a, b)
        return out


def _quad_neighbours(quad: Sequence[int], v: int) -> tuple[int, int]:
    """Return the two vertices next to v around a face."""
    i = list(quad).index(v)
    return quad[i - 1], quad[(i + 1) % len(quad)]


def _seeds(verts: Points, topo: _Topology, te: frozenset[int]) -> list[tuple[int, int]]:
    """Return the first edge of every separatrix: the singular vertices', then the ridges'."""
    seeds = [
        (v, u)
        for v in topo.singular
        for u in sorted(topo.adj[v])
        if len(topo.emap[_key(v, u)]) == 2
    ]
    sharp = dihedral_degrees(verts, topo.faces)
    for (a, b), angle in sorted(sharp.items()):
        if angle > RIDGE_DEGREES or (a in te and b in te):
            seeds += [(a, b), (b, a)]
    return seeds


def recover_joined(
    verts: Points, faces: Faces, te_vertices: Collection[int], joins: Collection[Edge]
) -> Blocks | str:
    """Recover the multiblock grid of several families' quadrilaterals taken as one (FR-932).

    ``joins`` are the edges where two of the families meet: they are cut, and
    the grid line through each is traced on in both directions like a
    separatrix, so every patch lies inside one family and every curve two
    families share is the side of a patch. Returns the reason, as text, when
    no such layout exists.
    """
    if any(len(f) != 4 for f in faces):
        return "a face is not a quadrilateral"
    try:
        return _recover(
            numpy.asarray(verts, dtype=float), faces, frozenset(te_vertices), frozenset(joins)
        )
    except _OnePatchError:
        return "the faces form one patch"
    except _NoLayoutError as why:
        return str(why)


def _recover(
    verts: Points, faces: Faces, te: frozenset[int], joins: frozenset[Edge] = frozenset()
) -> Blocks:
    """Return the multiblock grid of a family of quadrilaterals or raise why it has none."""
    topo = _Topology.of(faces)
    cut = {e for e, fs in topo.emap.items() if len(fs) == 1} | joins
    seeds = _seeds(verts, topo, te) + [s for a, b in sorted(joins) for s in ((a, b), (b, a))]
    for a, b in seeds:
        cut.update(topo.trace(a, b))
    groups = _patches(topo, cut)
    if len(groups) < 2:
        raise _OnePatchError
    grids = [_patch_grid(topo, group, cut) for group in groups]
    arcs, sides = _arcs([ids for ids, _ in grids], cut)
    te_arcs = frozenset(n for n, arc in enumerate(arcs) if all(v in te for v in arc))
    return Blocks(
        tuple(ids for ids, _ in grids),
        tuple(cells for _, cells in grids),
        arcs,
        sides,
        te_arcs,
    )


def _patches(topo: _Topology, cut: set[Edge]) -> list[list[int]]:
    """Return the faces of each patch, joined across the edges not cut, by first face."""
    parent = list(range(len(topo.faces)))

    def root(k: int) -> int:
        while parent[k] != k:
            parent[k] = parent[parent[k]]
            k = parent[k]
        return k

    for e, fs in topo.emap.items():
        if len(fs) == 2 and e not in cut:
            parent[root(fs[0])] = root(fs[1])
    groups: dict[int, list[int]] = defaultdict(list)
    for k in range(len(topo.faces)):
        groups[root(k)].append(k)
    return sorted(groups.values(), key=lambda g: g[0])


def _across(
    topo: _Topology, face: int, u: int, v: int, cut: set[Edge]
) -> tuple[int, int, int] | None:
    """Return the face beyond the edge u-v of a patch and its vertices next to u and to v."""
    if _key(u, v) in cut:
        return None
    other = [k for k in topo.emap[_key(u, v)] if k != face]
    if not other:
        return None
    quad = topo.faces[other[0]]
    nu = [x for x in _quad_neighbours(quad, u) if x != v]
    nv = [x for x in _quad_neighbours(quad, v) if x != u]
    return other[0], nu[0], nv[0]


def _first_cell(topo: _Topology, group: list[int]) -> tuple[int, list[list[int]]]:
    """Return the patch's corner cell: the face of its lowest one-face corner, as a 2 by 2 grid."""
    count = Counter(v for k in group for v in topo.faces[k])
    corners = sorted(v for v, c in count.items() if c == 1)
    if len(corners) != 4:
        raise _NoLayoutError(f"a patch has {len(corners)} corners, not four")
    c = corners[0]
    face = next(k for k in group if c in topo.faces[k])
    quad = topo.faces[face]
    i = quad.index(c)
    a, x, b = quad[(i + 1) % 4], quad[(i + 2) % 4], quad[(i + 3) % 4]
    if b < a:
        a, b = b, a
    return face, [[c, a], [b, x]]


def _patch_grid(
    topo: _Topology, group: list[int], cut: set[Edge]
) -> tuple[NDArray[numpy.int64], NDArray[numpy.int64]]:
    """Return a patch's nodes (rows + 1, columns + 1) and its cells' source faces, or raise."""
    face, rows = _first_cell(topo, group)
    cells = [[face]]
    while True:  # the first row of cells, column by column
        nxt = _across(topo, cells[0][-1], rows[0][-1], rows[1][-1], cut)
        if nxt is None:
            break
        if nxt[0] in cells[0]:
            raise _NoLayoutError("a patch closes on itself")
        cells[0].append(nxt[0])
        rows[0].append(nxt[1])
        rows[1].append(nxt[2])
    while True:  # each next row of cells, from the row above
        below = [
            _across(topo, k, rows[-1][j], rows[-1][j + 1], cut) for j, k in enumerate(cells[-1])
        ]
        if all(b is None for b in below):
            break
        if len(cells) * len(cells[0]) >= len(group):
            raise _NoLayoutError("a patch closes on itself")
        cells.append(_row_below(below, rows))
    ids = numpy.array(rows, dtype=numpy.int64)
    held = numpy.array(cells, dtype=numpy.int64)
    if sorted(held.ravel().tolist()) != sorted(group):
        raise _NoLayoutError("a patch is not a rectangle of rows by columns")
    return ids, held


def _row_below(below: list[tuple[int, int, int] | None], rows: list[list[int]]) -> list[int]:
    """Return the next row of cells, appending its nodes to ``rows``, or raise when ragged."""
    if any(b is None for b in below):
        raise _NoLayoutError("a patch is not a rectangle of rows by columns")
    found = [b for b in below if b is not None]
    row = [found[0][1]] + [b[2] for b in found]
    joined = all(found[j][2] == found[j + 1][1] for j in range(len(found) - 1))
    if not joined or len(set(row)) != len(row):
        raise _NoLayoutError("a patch is not a rectangle of rows by columns")
    rows.append(row)
    return [b[0] for b in found]


def _side_chains(ids: NDArray[numpy.int64]) -> list[tuple[int, ...]]:
    """Return a patch's four sides, in the order of :data:`SIDES`."""
    return [tuple(int(v) for v in s) for s in (ids[0], ids[-1], ids[:, 0], ids[:, -1])]


def _arcs(
    patches: list[NDArray[numpy.int64]], cut: set[Edge]
) -> tuple[tuple[tuple[int, ...], ...], tuple[tuple[tuple[int, bool], ...], ...]]:
    """Return the arcs (each patch side, once) and each patch's sides as (arc, reversed)."""
    index: dict[tuple[int, ...], int] = {}
    owner: dict[Edge, int] = {}
    sides = []
    for ids in patches:
        mine = []
        for chain in _side_chains(ids):
            flip = (chain[0], chain[1]) > (chain[-1], chain[-2])
            canonical = chain[::-1] if flip else chain
            arc = index.setdefault(canonical, len(index))
            for a, b in zip(canonical, canonical[1:], strict=False):
                if owner.setdefault(_key(a, b), arc) != arc:
                    raise _NoLayoutError("two patches meet at a T-junction")
            mine.append((arc, flip))
        sides.append(tuple(mine))
    if set(owner) != cut:
        raise _NoLayoutError("a cut edge lies on no patch side")
    return tuple(index), tuple(sides)


# ------------------------------------------------------------- the factors


#: An arc runs SPANWISE when its edges run, on average weighted by length, within 45
#: degrees of the trailing-edge segment nearest each: the mean of |cos| at least cos 45.
#: Absolute cosine tolerance 1e-14 includes the boundary despite floating-point roundoff.
SPANWISE_COS = math.cos(math.radians(45.0))


def runs_spanwise(verts: Points, chain: Sequence[int], te: Points) -> bool:
    """Return whether an arc runs along the trailing edge (spanwise) rather than across it.

    ``te`` holds the trailing-edge segments, shape (T, 2, 3). Each edge of the
    arc is compared with the segment nearest its mid-point; the arc's value
    is the length-weighted mean of the absolute cosine between the two, so an
    arc wrapping round a leading edge, whose ends almost meet, is read by its
    edges and not by its chord (FR-915, PFS-2150).
    """
    p = numpy.asarray(verts, dtype=float)[list(chain)]
    edge = p[1:] - p[:-1]
    mid = 0.5 * (p[1:] + p[:-1])
    a, ab = te[:, 0], te[:, 1] - te[:, 0]
    t = ((mid[:, None, :] - a[None]) * ab[None]).sum(axis=2)
    t = numpy.clip(t / numpy.maximum((ab * ab).sum(axis=1), 1e-300)[None], 0.0, 1.0)
    gap = numpy.linalg.norm(a[None] + t[..., None] * ab[None] - mid[:, None, :], axis=2)
    near = ab[numpy.argmin(gap, axis=1)]
    length = numpy.linalg.norm(edge, axis=1)
    scale = numpy.maximum(length * numpy.linalg.norm(near, axis=1), 1e-300)
    cos = numpy.abs((edge * near).sum(axis=1)) / scale
    return float((cos * length).sum() / max(float(length.sum()), 1e-300)) >= SPANWISE_COS - 1e-14


def te_directions(
    verts: Points,
    blocks: Blocks,
    patches: Sequence[int],
    te: Points,
    *,
    family: str,
    what: str,
) -> dict[int, str]:
    """Return ``"chordwise"`` or ``"spanwise"`` for each arc of a family's patches (PFS-2150).

    An arc is classified from the family's trailing edge (:func:`runs_spanwise`).
    Opposite sides of a patch hold the same m and must classify alike, and its
    rows and its columns must run in different directions.

    Parameters
    ----------
    verts : numpy.ndarray
        All the mesh's vertices, shape (V, 3).
    blocks : Blocks
        The layout.
    patches : sequence of int
        The family's patches, numbered 1, 2, ... in this order in a refusal.
    te : numpy.ndarray
        The family's trailing-edge segments, shape (T, 2, 3).
    family : str
        The source and family, for a refusal.
    what : str
        The family's layout as a refusal names it.

    Raises
    ------
    InputArtifactError
        The family has no trailing edge, or a patch's two directions cannot be
        told apart, naming the patch and where it lies; nothing was written.
    """
    if not len(te):
        raise InputArtifactError(
            f"{family}: chordwise and spanwise are not defined for {what} without a trailing "
            "edge: its arcs are told chordwise or spanwise by the direction of the family's "
            "trailing edge, and it has none. Give its factor alone, or list its trailing edge "
            "in the points file, and run again. Nothing was written.",
            kind=KIND,
        )
    out: dict[int, str] = {}
    for n, p in enumerate(patches, 1):
        arcs = [arc for arc, _ in blocks.sides[p]]
        for arc in arcs:
            if arc not in out:
                spanwise = runs_spanwise(verts, blocks.arcs[arc], te)
                out[arc] = "spanwise" if spanwise else "chordwise"
        rows, columns = {out[a] for a in arcs[:2]}, {out[a] for a in arcs[2:]}
        if len(rows) == 1 and len(columns) == 1 and rows != columns:
            continue
        pts = numpy.asarray(verts, dtype=float)[blocks.patches[p].ravel()]
        where = ", ".join(f"{v:.3g}" for v in pts.mean(axis=0))
        raise InputArtifactError(
            f"{family}: chordwise and spanwise cannot be told apart on patch {n} of {what} "
            f"(centroid {where}): its rows run {' and '.join(sorted(rows))} and its columns "
            f"{' and '.join(sorted(columns))} of the trailing edge. Give the family's factor "
            "alone and run again. Nothing was written.",
            kind=KIND,
        )
    return out


def kept_sides(
    blocks: Blocks,
    verts: NDArray[numpy.float64],
    factor: float | Mapping[int, float],
    *,
    patches: Sequence[int] | None = None,
) -> list[dict[str, object]]:
    """Return the patch sides a factor below 1/m cannot coarsen, with where they lie.

    A side of m source intervals with ``factor * m < 1`` keeps
    ``max(1, round(factor * m))`` intervals rather than refusing the family,
    so the rest of the family is resampled as asked (FR-915). Each entry names
    the patch (1-based, in the order of ``patches``), the side, both counts, and
    the patch's centroid and bounding box in the mesh's units (three
    significant figures), so the side can be found in a viewer.

    Parameters
    ----------
    blocks : Blocks
        The recovered multiblock grid.
    verts : numpy.ndarray
        The source vertices, shape (n, 3).
    factor : float or mapping of int to float
        The family's factor, or the factor of each arc of its patches.
    patches : sequence of int, optional
        The family's patches (default: every patch of the layout).

    Returns
    -------
    list of dict
        One entry per kept side, in patch then :data:`SIDES` order; empty when none.
    """

    def _sig(values: NDArray[numpy.float64]) -> list[float]:
        return [float(f"{v:.3g}") for v in values]

    kept: list[dict[str, object]] = []
    mine = range(len(blocks.patches)) if patches is None else patches
    for n, p in enumerate(mine, 1):
        pts = verts[blocks.patches[p].ravel()]
        for side, (arc, _) in zip(SIDES, blocks.sides[p], strict=True):
            m = len(blocks.arcs[arc]) - 1
            f = factor[arc] if isinstance(factor, Mapping) else factor
            if f * m < 1.0:
                kept.append(
                    {
                        "patch": n,
                        "side": side,
                        "source_intervals": m,
                        "intervals": count(m, f),
                        "centroid": _sig(pts.mean(axis=0)),
                        "bbox_min": _sig(pts.min(axis=0)),
                        "bbox_max": _sig(pts.max(axis=0)),
                    }
                )
    return kept


def count(m: int, factor: float) -> int:
    """Return round(f m), at least one interval."""
    return max(1, round(m * factor))


def sheet_directions(grid: Grid, blocks: Blocks, arcs: Collection[int]) -> dict[int, str]:
    """Return ``"chordwise"`` or ``"spanwise"`` for each arc lying in a sheet grid.

    A sheet keeps its index directions when it is resampled with other grids
    (FR-932): an arc along one of its stations is chordwise, one along a
    column spanwise, as :func:`._grid.refine_grid` reads them.
    """
    place = {int(v): (k, i) for (k, i), v in numpy.ndenumerate(grid.ids)}
    out = {}
    for arc in arcs:
        a, b = (place[v] for v in blocks.arcs[arc][:2])
        out[arc] = "chordwise" if a[0] == b[0] else "spanwise"
    return out


# ------------------------------------------------------------- the resampling


class _Nodes:
    """The level's nodes, each made once and named by where it comes from."""

    def __init__(self) -> None:
        self.index: dict[tuple[object, ...], int] = {}
        self.points: list[Points] = []

    def node(self, key: tuple[object, ...], point: Points) -> int:
        """Return the index of a named node, making it at ``point`` the first time."""
        if key not in self.index:
            self.index[key] = len(self.points)
            self.points.append(point)
        return self.index[key]


def _patch_nodes(
    verts: Points,
    blocks: Blocks,
    p: int,
    arcs: list[Points],
    nodes: _Nodes,
    *,
    counts: Sequence[int],
) -> NDArray[numpy.int64]:
    """Return the level's node index of every point of a patch's new grid.

    Its columns are its first row's arc's count, its rows its first column's.
    """
    ids = blocks.patches[p]
    rows, cols = ids.shape[0] - 1, ids.shape[1] - 1
    s = numpy.linspace(0, cols, counts[blocks.sides[p][0][0]] + 1)
    t = numpy.linspace(0, rows, counts[blocks.sides[p][2][0]] + 1)
    across = not_a_knot(verts[ids].transpose(1, 0, 2), s).transpose(1, 0, 2)
    inside = not_a_knot(across, t)
    kp, cp = inside.shape[:2]
    out = numpy.empty((kp, cp), dtype=numpy.int64)
    corners = {(0, 0): ids[0, 0], (0, cp - 1): ids[0, -1], (kp - 1, 0): ids[-1, 0]}
    corners[(kp - 1, cp - 1)] = ids[-1, -1]
    lines = dict(zip(SIDES, blocks.sides[p], strict=True))
    for r in range(kp):
        for c in range(cp):
            if (r, c) in corners:
                v = int(corners[(r, c)])
                out[r, c] = nodes.node(("v", v), verts[v])
                continue
            on = _on_side(r, c, kp, cp)
            if on is None:
                out[r, c] = nodes.node(("p", p, r, c), inside[r, c])
                continue
            side, at, count = on
            arc, flip = lines[side]
            pos = count - at if flip else at
            out[r, c] = nodes.node(("a", arc, pos), arcs[arc][pos])
    return out


def _on_side(r: int, c: int, kp: int, cp: int) -> tuple[str, int, int] | None:
    """Return the side a new grid point lies on, its position along it and the side's count."""
    if r == 0:
        return SIDES[0], c, cp - 1
    if r == kp - 1:
        return SIDES[1], c, cp - 1
    if c == 0:
        return SIDES[2], r, kp - 1
    if c == cp - 1:
        return SIDES[3], r, kp - 1
    return None


def _forward(quad: Sequence[int], a: int, b: int) -> bool:
    """Return whether a face runs from a to b (rather than from b to a)."""
    i = list(quad).index(a)
    return quad[(i + 1) % len(quad)] == b


@dataclass(frozen=True, eq=False)
class Resampled:
    """A layout resampled: the new nodes, each patch's new faces and shapes, the trailing edge.

    Attributes
    ----------
    points : numpy.ndarray
        The new nodes, shape (P, 3), each arc's made once.
    cells : tuple of list of list of int
        Per patch, its new faces, oriented like its source faces.
    shapes : tuple of tuple
        Per patch, its node array's shape before and after.
    te_midpoints : numpy.ndarray
        One mid-point per new trailing-edge edge, shape (T, 3).
    """

    points: Points
    cells: tuple[Faces, ...]
    shapes: tuple[tuple[tuple[int, ...], tuple[int, ...]], ...]
    te_midpoints: Points


def resample(verts: Points, faces: Faces, blocks: Blocks, counts: Sequence[int]) -> Resampled:
    """Resample every arc of a layout to its count, then every patch inside its arcs (FR-920).

    ``counts`` holds each arc's new interval count; opposite sides of a patch
    must hold the same. ``faces`` are the faces the layout was recovered on.
    """
    verts = numpy.asarray(verts, dtype=float)
    arcs = [
        not_a_knot(verts[list(arc)], numpy.linspace(0, len(arc) - 1, counts[n] + 1))
        for n, arc in enumerate(blocks.arcs)
    ]
    nodes = _Nodes()
    cells: list[Faces] = []
    shapes = []
    for p, ids in enumerate(blocks.patches):
        grid = _patch_nodes(verts, blocks, p, arcs, nodes, counts=counts)
        same = _forward(faces[int(blocks.cells[p][0, 0])], int(ids[0, 0]), int(ids[0, 1]))
        built: Faces = []
        for r in range(grid.shape[0] - 1):
            for c in range(grid.shape[1] - 1):
                quad = [
                    int(grid[r, c]),
                    int(grid[r, c + 1]),
                    int(grid[r + 1, c + 1]),
                    int(grid[r + 1, c]),
                ]
                built.append(quad if same else [quad[0], quad[3], quad[2], quad[1]])
        cells.append(built)
        shapes.append((tuple(ids.shape), tuple(grid.shape)))
    points = numpy.array(nodes.points, dtype=float).reshape(-1, 3)
    te = [0.5 * (arcs[a][:-1] + arcs[a][1:]) for a in sorted(blocks.te_arcs)]
    midpoints = numpy.vstack(te) if te else numpy.zeros((0, 3))
    return Resampled(points, tuple(cells), tuple(shapes), midpoints)


def report(
    blocks: Blocks, done: Resampled, patches: Sequence[int], faces: tuple[int, int]
) -> dict[str, object]:
    """Return the ``refine.json`` entry of the family holding ``patches`` of a resampled layout."""
    shapes = [done.shapes[p] for p in patches]
    return {
        "layout": "multiblock",
        "split": "quadrilaterals",
        "patches": len(patches),
        "blocks": [
            {"rows": [a[0] - 1, b[0] - 1], "columns": [a[1] - 1, b[1] - 1]} for a, b in shapes
        ],
        "arcs": len({arc for p in patches for arc, _ in blocks.sides[p]}),
        "faces": list(faces),
        "order": "nearest",
    }


def refine_blocks(verts: Points, faces: Faces, blocks: Blocks, *, factor: float) -> GridLevel:
    """Resample a multiblock family by its factor (FR-920, FR-921).

    Parameters
    ----------
    verts : numpy.ndarray
        All the mesh's vertices, shape (V, 3).
    faces : list of list of int
        The family's source faces, as indices into ``verts``.
    blocks : Blocks
        The family's layout, from :func:`recover_family`.
    factor : float
        The factor of every arc's interval count.

    Returns
    -------
    GridLevel
        The new points, faces, trailing-edge mid-points and report.
    """
    done = resample(verts, faces, blocks, [count(len(arc) - 1, factor) for arc in blocks.arcs])
    built = [f for cell in done.cells for f in cell]
    ordered = order_like(done.points, built, numpy.asarray(verts, dtype=float), faces)
    entry = report(blocks, done, range(len(blocks.patches)), (len(faces), len(ordered)))
    return GridLevel(done.points, ordered, done.te_midpoints, entry)


# ------------------------------------------------- grids resampled as one layout (FR-932)


Recovered = Grid | Blocks


@dataclass(frozen=True, eq=False)
class Layout:
    """Grid families resampled as one multiblock layout.

    Attributes
    ----------
    names : tuple of str
        Its families, in the source's family order.
    kinds : tuple of str
        Each family's own layout: ``"sheet"`` or ``"multiblock"``.
    blocks : Blocks
        The layout of their faces taken together, in the order of ``names``.
    owner : tuple of int
        Per patch, the index in ``names`` of the family holding it.
    counts : tuple of int
        Per arc, its new interval count.
    kept : dict
        Per family, the patch sides its factor cannot coarsen (FR-915).
    """

    names: tuple[str, ...]
    kinds: tuple[str, ...]
    blocks: Blocks
    owner: tuple[int, ...]
    counts: tuple[int, ...]
    kept: Mapping[str, list[dict[str, object]]]

    def patches_of(self, name: str) -> list[int]:
        """Return the patches of one family, in layout order."""
        i = self.names.index(name)
        return [p for p, o in enumerate(self.owner) if o == i]

    def changes(self, name: str) -> bool:
        """Return whether resampling changes the nodes of any side of the family's patches.

        Read from the counts alone, before any family is resampled (FR-424,
        FR-925); any side changing is taken to change every curve it shares.
        """
        arcs = {arc for p in self.patches_of(name) for arc, _ in self.blocks.sides[p]}
        return any(self.counts[a] != len(self.blocks.arcs[a]) - 1 for a in arcs)


def _refuse(text: str) -> InputArtifactError:
    return InputArtifactError(f"{text}. Nothing was written.", kind=KIND)


def _joinable(grid: Recovered, faces: Faces) -> bool:
    """Return whether a grid family can join a layout: quadrilaterals as a sheet or multiblock."""
    sheet = isinstance(grid, Grid) and grid.layout == "sheet"
    return (sheet or isinstance(grid, Blocks)) and all(len(f) == 4 for f in faces)


def _touching(names: Sequence[str], nodes: Mapping[str, set[int]]) -> list[list[str]]:
    """Return the groups of families joined by shared nodes, each in the order of ``names``."""
    groups: list[list[str]] = []
    for name in names:
        hit = [g for g in groups if any(nodes[name] & nodes[m] for m in g)]
        merged = sorted([name, *(m for g in hit for m in g)], key=names.index)
        groups = [g for g in groups if g not in hit] + [merged]
    return sorted(groups, key=lambda g: names.index(g[0]))


def _join(
    verts: Points, families: Mapping[str, Faces], group: Sequence[str], te: Collection[int]
) -> tuple[Blocks, tuple[int, ...]] | str:
    """Return the layout of a group of families taken as one and each patch's family, or why not."""
    faces = [f for n in group for f in families[n]]
    family = numpy.repeat(numpy.arange(len(group)), [len(families[n]) for n in group])
    joins = {
        e for e, fs in edge_faces(faces).items() if len(fs) == 2 and family[fs[0]] != family[fs[1]]
    }
    found = recover_joined(verts, faces, te, joins)
    if isinstance(found, str):
        return found
    return found, tuple(int(family[int(cells[0, 0])]) for cells in found.cells)


def _arc_factors(
    verts: Points,
    blocks: Blocks,
    patches: Sequence[int],
    grid: Recovered,
    spec: FamilySpec,
    *,
    te_edges: Collection[Edge],
    family: str,
) -> dict[int, float]:
    """Return the factor of each arc of a family's patches, in the arc's direction.

    A sheet's arcs take its own index directions; a multiblock family's are
    classified from its trailing edge (:func:`.te_directions`).
    """
    chordwise, spanwise = spec.directions
    arcs = sorted({arc for p in patches for arc, _ in blocks.sides[p]})
    if chordwise == spanwise:
        return dict.fromkeys(arcs, chordwise)
    if isinstance(grid, Grid):
        runs = sheet_directions(grid, blocks, arcs)
    else:
        te = numpy.asarray(verts, dtype=float)[sorted(te_edges)].reshape(-1, 2, 3)
        what = grid.describe() if len(patches) == len(blocks.patches) else "its patches"
        runs = te_directions(verts, blocks, patches, te, family=family, what=what)
    return {a: chordwise if runs[a] == "chordwise" else spanwise for a in arcs}


def _counted(
    verts: Points,
    names: tuple[str, ...],
    found: tuple[Blocks, tuple[int, ...]],
    grids: Mapping[str, Recovered],
    specs: Mapping[str, FamilySpec],
    *,
    te_edges: Mapping[str, Collection[Edge]],
    where: str,
) -> Layout:
    """Return the layout with every arc's count, refusing an arc two families count apart."""
    blocks, owner = found
    counts: dict[int, tuple[int, str]] = {}
    kept: dict[str, list[dict[str, object]]] = {}
    for i, name in enumerate(names):
        mine = [p for p, o in enumerate(owner) if o == i]
        factors = _arc_factors(
            verts,
            blocks,
            mine,
            grids[name],
            specs[name],
            te_edges=te_edges[name],
            family=f"{where} family {name}",
        )
        for arc, f in factors.items():
            chain = blocks.arcs[arc]
            new = count(len(chain) - 1, f)
            old, other = counts.setdefault(arc, (new, name))
            if old != new:
                raise _refuse(
                    f"{where} families {other} and {name}: the curve they share from node "
                    f"{chain[0] + 1} to node {chain[-1] + 1}, of {len(chain) - 1} source "
                    f"intervals, would hold {old} intervals as {other} is refined and {new} as "
                    f"{name} is; grids that share nodes are resampled as one layout, so give "
                    "the two factors that make one count of it"
                )
        kept[name] = kept_sides(blocks, verts, factors, patches=mine)
    kinds = tuple(grids[n].layout for n in names)
    return Layout(
        names, kinds, blocks, owner, tuple(counts[a][0] for a in range(len(blocks.arcs))), kept
    )


def _warn_kept(layout: Layout, specs: Mapping[str, FamilySpec], where: str) -> None:
    """Warn once per family naming each patch side its factor cannot coarsen (FR-915)."""
    for name in layout.names:
        kept = layout.kept[name]
        if not kept:
            continue
        chordwise, spanwise = specs[name].directions
        label = (
            f"factor {chordwise:g}"
            if chordwise == spanwise
            else f"factors chordwise {chordwise:g} and spanwise {spanwise:g}"
        )
        lines = "; ".join(
            f"patch {k['patch']} {k['side']}: {k['source_intervals']} source interval(s), "
            f"{k['intervals']} written, centroid {k['centroid']}, "
            f"box {k['bbox_min']} to {k['bbox_max']}"
            for k in kept
        )
        what = f"{len(layout.patches_of(name))} patches of {', '.join(layout.names)}"
        if len(layout.names) == 1:
            what = layout.blocks.describe()
        warn(
            f"{where} family {name}: the {label} cannot coarsen {len(kept)} patch side(s) of "
            f"{what}; they are kept and the rest of the family is resampled: {lines}",
            PyflightstreamWarning,
            stacklevel=6,  # past _warn_kept, plan, _grid_after_grid, _decide and refine_mesh
        )


def plan(
    verts: Points,
    families: Mapping[str, Faces],
    grids: Mapping[str, Recovered],
    specs: Mapping[str, FamilySpec],
    te_edges: Mapping[str, Collection[Edge]],
    *,
    held: Collection[str],
    where: str,
) -> tuple[dict[str, Layout], list[tuple[str, str, str]]]:
    """Group the grid families that share nodes into layouts, before any work (FR-932).

    Parameters
    ----------
    verts : numpy.ndarray
        All the mesh's vertices, shape (V, 3).
    families : mapping of str to faces
        Every family of the mesh, in the source's order.
    grids : mapping of str to Grid or Blocks
        The families recovered as grids.
    specs : mapping of str to FamilySpec
        The request of each family to change.
    te_edges : mapping of str to edges
        The trailing-edge edges of each family.
    held : collection of str
        Grids that keep their first row (FR-430), which join no layout.
    where : str
        The source, for a refusal or a warning.

    Returns
    -------
    dict, list
        The layout of each family resampled in one (every member of a group,
        and each lone multiblock family), and, per grid left to the rule of
        the first grid, its name, the grid refined first that it shares
        nodes with, and why it joined no layout ("" when it could not).

    Raises
    ------
    InputArtifactError
        Two families giving a shared curve different counts; nothing was written.
    """
    names = tuple(n for n in families if n in grids)
    nodes = {n: {v for f in families[n] for v in f} for n in names}
    joinable = [n for n in names if n not in held and _joinable(grids[n], families[n])]
    layouts: list[Layout] = []
    why: dict[str, str] = {}
    for group in _touching(joinable, nodes):
        if len(group) < 2:
            continue
        te = {v for n in group for e in te_edges[n] for v in e}
        found = _join(verts, families, group, te)
        if isinstance(found, str):
            why.update(
                dict.fromkeys(group, f"; the grids {', '.join(group)} form no layout: {found}")
            )
            continue
        layouts.append(
            _counted(verts, tuple(group), found, grids, specs, te_edges=te_edges, where=where)
        )
    done = [n for lay in layouts for n in lay.names]
    late: list[tuple[str, str, str]] = []
    for name in names:
        if name in done:
            continue
        first = [m for m in names if m in done and nodes[name] & nodes[m]]
        if first:
            late.append((name, first[0], why.get(name, "")))
            continue
        done.append(name)
        grid = grids[name]
        if isinstance(grid, Blocks):
            lone = (grid, (0,) * len(grid.patches))
            layouts.append(
                _counted(verts, (name,), lone, grids, specs, te_edges=te_edges, where=where)
            )
    for layout in layouts:
        _warn_kept(layout, specs, where)
    return {n: lay for lay in layouts for n in lay.names}, late


def refine_layout(
    verts: Points, families: Mapping[str, Faces], layout: Layout
) -> dict[str, GridLevel]:
    """Resample a layout and write each new cell back to its family (FR-920, FR-921, FR-932).

    Every family's level holds the layout's points; its faces are its
    patches' new faces in the order of its source faces. The new trailing-edge
    mid-points are the first family's.
    """
    verts = numpy.asarray(verts, dtype=float)
    faces = [f for n in layout.names for f in families[n]]
    done = resample(verts, faces, layout.blocks, layout.counts)
    out: dict[str, GridLevel] = {}
    for i, name in enumerate(layout.names):
        mine = layout.patches_of(name)
        built = [f for p in mine for f in done.cells[p]]
        ordered = order_like(done.points, built, verts, families[name])
        entry = report(layout.blocks, done, mine, (len(families[name]), len(ordered)))
        if len(layout.names) > 1:
            entry["layout"] = layout.kinds[i]
            entry["grouped_with"] = [n for n in layout.names if n != name]
        te = done.te_midpoints if i == 0 else numpy.zeros((0, 3))
        out[name] = GridLevel(done.points, ordered, te, entry)
    return out
