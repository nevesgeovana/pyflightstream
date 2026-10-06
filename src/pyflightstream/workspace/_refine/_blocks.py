"""The multiblock grid of an all-quadrilateral family, recovered and resampled (FR-424 R6, R7, R9).

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

Resampling (R6) keeps that structure: each arc is resampled ONCE, by the
cubic spline of :func:`._grid.not_a_knot` through its source nodes in index
space, to ``round(f m)`` intervals of its m; opposite sides of a patch hold
the same m, so they agree. A patch's interior is the tensor spline of its
nodes, as a single grid's is, and its boundary nodes are the arcs' nodes, so
two patches sharing an arc share its nodes exactly. The source's nodes at
integer parameters are kept bit for bit, the layout's corners among them.

Face order (R7): every new face takes the position of the source face whose
centroid is nearest (``_geometry.order_like``), each patch oriented like the
source faces it replaces; at factor 1 the family is the source in coordinates
and in order. A family with a face that is not a quadrilateral, or whose
layout is one patch (a sheet or a tube, recovered or refused by
:mod:`._grid`), or whose cut leaves a patch that is not four-sided, has no
multiblock grid, and falls back as before.

This module imports neither scipy nor rtree (R10).
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass

import numpy
from numpy.typing import NDArray

from pyflightstream._errors import InputArtifactError
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


def _recover(verts: Points, faces: Faces, te: frozenset[int]) -> Blocks:
    """Return the multiblock grid of a family of quadrilaterals or raise why it has none."""
    topo = _Topology.of(faces)
    cut = {e for e, fs in topo.emap.items() if len(fs) == 1}
    for a, b in _seeds(verts, topo, te):
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


def check_factor(blocks: Blocks, family: str, spec: FamilySpec) -> None:
    """Refuse chordwise or spanwise on a multiblock family, and a factor leaving no interval.

    A factor below 1/m for the m source intervals of any patch side would
    leave that side no interval (FR-424 R1), so it is refused naming the
    family, the patch side and the value rather than rounded up to one.

    Parameters
    ----------
    blocks : Blocks
        The family's recovered multiblock grid.
    family : str
        The family's name, for the message.
    spec : FamilySpec
        The family's request.

    Raises
    ------
    InputArtifactError
        Naming the family (and the patch side); nothing was written.
    """
    if spec.chordwise is not None or spec.spanwise is not None:
        raise InputArtifactError(
            f"family {family}: chordwise and spanwise are not defined for {blocks.describe()}, "
            "whose patches share no index directions. Give its factor alone and run again. "
            "Nothing was written.",
            kind=KIND,
        )
    factor = spec.factor
    shortest = min(
        (len(blocks.arcs[arc]) - 1, p, side)
        for p, sides in enumerate(blocks.sides)
        for side, (arc, _) in zip(SIDES, sides, strict=True)
    )
    m, patch, side = shortest
    if factor * m < 1.0:
        raise InputArtifactError(
            f"family {family}: the factor {factor:g} is below 1/{m}: the {side} of patch "
            f"{patch + 1} has {m} source intervals and would be left with none. Give a factor "
            f"of at least 1/{m} and run again. Nothing was written.",
            kind=KIND,
        )


def _count(m: int, factor: float) -> int:
    """Return round(f m), at least one interval."""
    return max(1, round(m * factor))


def nodes_change(blocks: Blocks, factor: float) -> bool:
    """Return whether resampling by ``factor`` would change the nodes of any patch side.

    Read from the counts alone, before any family is resampled (FR-424
    R11): a side keeps its nodes when its count is the source's. Any side
    changing is taken to change every curve the family shares.
    """
    return any(_count(len(arc) - 1, factor) != len(arc) - 1 for arc in blocks.arcs)


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
    factor: float,
) -> NDArray[numpy.int64]:
    """Return the level's node index of every point of a patch's new grid."""
    ids = blocks.patches[p]
    rows, cols = ids.shape[0] - 1, ids.shape[1] - 1
    s = numpy.linspace(0, cols, _count(cols, factor) + 1)
    t = numpy.linspace(0, rows, _count(rows, factor) + 1)
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


def refine_blocks(verts: Points, faces: Faces, blocks: Blocks, *, factor: float) -> GridLevel:
    """Resample a multiblock family by its factor (FR-424 R6, R7).

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
    verts = numpy.asarray(verts, dtype=float)
    arcs = [
        not_a_knot(
            verts[list(arc)], numpy.linspace(0, len(arc) - 1, _count(len(arc) - 1, factor) + 1)
        )
        for arc in blocks.arcs
    ]
    nodes = _Nodes()
    built: Faces = []
    shapes = []
    for p, ids in enumerate(blocks.patches):
        grid = _patch_nodes(verts, blocks, p, arcs, nodes, factor=factor)
        same = _forward(faces[int(blocks.cells[p][0, 0])], int(ids[0, 0]), int(ids[0, 1]))
        for r in range(grid.shape[0] - 1):
            for c in range(grid.shape[1] - 1):
                quad = [
                    int(grid[r, c]),
                    int(grid[r, c + 1]),
                    int(grid[r + 1, c + 1]),
                    int(grid[r + 1, c]),
                ]
                built.append(quad if same else [quad[0], quad[3], quad[2], quad[1]])
        shapes.append((ids.shape, grid.shape))
    points = numpy.array(nodes.points, dtype=float).reshape(-1, 3)
    ordered = order_like(points, built, verts, faces)
    te = [0.5 * (arcs[a][:-1] + arcs[a][1:]) for a in sorted(blocks.te_arcs)]
    report = {
        "layout": "multiblock",
        "split": "quadrilaterals",
        "patches": len(blocks.patches),
        "blocks": [
            {"rows": [a[0] - 1, b[0] - 1], "columns": [a[1] - 1, b[1] - 1]} for a, b in shapes
        ],
        "arcs": len(blocks.arcs),
        "faces": [len(faces), len(ordered)],
        "order": "nearest",
    }
    midpoints = numpy.vstack(te) if te else numpy.zeros((0, 3))
    return GridLevel(points, ordered, midpoints, report)
