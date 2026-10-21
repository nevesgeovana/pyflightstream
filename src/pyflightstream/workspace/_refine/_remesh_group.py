"""The group a remesh works on: its local numbering, targets, curves and order (FR-921, FR-922).

A section of :mod:`._remesh`, which imports every name of it that other
modules read, so their import paths hold. A group is the families remeshed
together, numbered locally and
fanned into triangles; its TARGETS are the source's local edge lengths over
each family's factor, and beside a refined side the length of the new shared
edges returning to the family's own over :data:`SHARED_LAYERS` face layers
(FR-964, FR-965). Its CURVES are the edges a remesh splits and collapses only
along their source curve: open boundaries, the trailing edge, ridges, and the
interfaces between families; an interface with a family outside the group is
FROZEN. The remeshed families are returned oriented and ordered like their
source faces (FR-921). Nothing here imports the geometry extra.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field

import numpy

from pyflightstream.workspace._refine._geometry import (
    RIDGE_DEGREES,
    SHARED_LAYERS,
    Faces,
    NearestIndex,
    Points,
    Stretch,
    dihedral_degrees,
    edge_faces,
    order_like,
    orient_like,
)
from pyflightstream.workspace._refine._obj import ObjMesh

Edge = tuple[int, int]

#: The kinds of curve, as the keys of ``info["curve_edges"]``.
BOUNDARY = "boundary"
TRAILING_EDGE = "trailing_edge"
RIDGE = "ridge"
FROZEN = "frozen"
INTERFACE = "interface"


def _ek(a: int, b: int) -> Edge:
    """Return the undirected key of an edge, low vertex first."""
    return (a, b) if a < b else (b, a)


@dataclass
class Patch:
    """The triangles of a group of families, with what a remesh must keep.

    Attributes
    ----------
    verts : ndarray
        The group's vertices, numbered locally.
    faces : list of list of int
        Its triangles.
    labels : list of str
        The family of each triangle.
    target : ndarray
        The target edge length at each vertex.
    curve : dict
        Each curve edge with its curve key.
    fixed : set of int
        Vertices that never move (shared with a family outside the group).
    frozen : set of tuple
        Curve edges never split nor collapsed.
    stretch : Stretch or None
        For a body refined along and around its axis (FR-428), the map into
        the space the remesh runs in; ``verts`` and ``target`` stay in the
        real space, and the source surface and curves the nodes are projected
        onto are the real ones.
    """

    verts: Points
    faces: Faces
    labels: list[str]
    target: Points
    curve: dict[Edge, str]
    fixed: set[int] = field(default_factory=set)
    frozen: set[Edge] = field(default_factory=set)
    stretch: Stretch | None = None


@dataclass
class _Group:
    """The local numbering of a group: source vertices, triangles, labels, source faces."""

    ids: list[int]
    verts: Points
    faces: Faces
    labels: list[str]
    source: dict[str, Faces]


def _newell(points: Points) -> Points:
    """Return the (unnormalised) normal of a polygon given by its corner points, in order."""
    return numpy.cross(points, numpy.roll(points, -1, axis=0)).sum(axis=0)


def _triangulate(verts: Points, f: list[int]) -> Faces:
    """Return a polygon's triangles: the fan of its first corner, else ear clipping (F-309).

    The fan of a convex polygon is kept as it was. A concave polygon's fan can
    overlap itself (a triangle turned against the polygon's normal), and those
    triangles would define the projection surface; the polygon is then cut by
    ear clipping, every triangle turned with the polygon.
    """
    if len(f) == 3:
        return [list(f)]
    normal = _newell(verts[f])
    fan = [[f[0], f[k], f[k + 1]] for k in range(1, len(f) - 1)]
    if all(float(numpy.dot(_newell(verts[t]), normal)) > 0.0 for t in fan):
        return fan
    rest, out = list(f), []
    while len(rest) > 3:
        for i in range(len(rest)):
            a, b, c = rest[i - 1], rest[i], rest[(i + 1) % len(rest)]
            tri = verts[[a, b, c]]
            if float(numpy.dot(_newell(tri), normal)) <= 0.0:
                continue
            inside = False
            for v in rest:
                if v in (a, b, c):
                    continue
                p = verts[v]
                signs = [
                    float(numpy.dot(numpy.cross(tri[(k + 1) % 3] - tri[k], p - tri[k]), normal))
                    for k in range(3)
                ]
                if all(s >= 0.0 for s in signs):
                    inside = True
                    break
            if not inside:
                out.append([a, b, c])
                del rest[i]
                break
        else:
            return fan  # no ear (a degenerate polygon): keep the fan rather than lose faces
    out.append(rest)
    return out


def _group(mesh: ObjMesh, names: Sequence[str]) -> _Group:
    """Return the group's faces numbered locally, each polygon fanned into triangles."""
    ids = sorted({v for n in names for f in mesh.families[n] for v in f})
    local = {v: i for i, v in enumerate(ids)}
    source = {n: [[local[v] for v in f] for f in mesh.families[n]] for n in names}
    faces: Faces = []
    labels: list[str] = []
    for n in names:
        for f in source[n]:
            fan = _triangulate(mesh.verts[ids], f)
            faces += fan
            labels += [n] * len(fan)
    return _Group(ids, mesh.verts[ids], faces, labels, source)


def _targets(group: _Group, factors: Mapping[str, float]) -> Points:
    """Return the target length at each vertex: its mean incident edge length over its factor.

    A vertex shared by two families takes the larger factor (the finer target).
    """
    total = numpy.zeros(len(group.verts))
    count = numpy.zeros(len(group.verts))
    for a, b in edge_faces(group.faces):
        d = float(numpy.linalg.norm(group.verts[a] - group.verts[b]))
        total[[a, b]] += d
        count[[a, b]] += 1
    factor = numpy.zeros(len(group.verts))
    for f, label in zip(group.faces, group.labels, strict=True):
        factor[f] = numpy.maximum(factor[f], factors[label])
    return total / numpy.maximum(count, 1) / factor


def shared_targets(
    points: Points,
    faces: Sequence[Sequence[int]],
    labels: Sequence[str],
    *,
    own: Points,
    held: Collection[int],
    chains: Sequence[Collection[Edge]],
    sources: Collection[int] = (),
) -> tuple[dict[int, float], dict[str, dict[str, float]]]:
    """Return the targets FR-432 sets along and near the curves shared with a refined side.

    The mesh is the group's once each shared interface has been rebuilt on
    the refined side's new nodes (FR-933), so every node of the curve,
    an inserted one included, is a node of ``chains``. A curve node takes
    the mean length of the new shared edges incident to it (FR-964). A node
    ``d`` face layers from the curve, ``d`` below :data:`SHARED_LAYERS`,
    takes ``s + (own - s) * d / SHARED_LAYERS``, ``s`` the target of the
    curve node nearest it and ``own`` its own target, and a node farther
    keeps its own, so there is no step (FR-965). A source node of the curve
    that is no longer a curve node takes the target of the curve node
    nearest it, so the source's field of targets agrees at the curve. A
    ``held`` node keeps its own target.

    Parameters
    ----------
    points : ndarray
        The nodes, shape (V, 3).
    faces : sequence of sequence of int
        The faces, as indices into ``points``.
    labels : sequence of str
        The family of each face.
    own : ndarray
        Each node's own target, shape (V,).
    held : collection of int
        The nodes that keep their own target (on a face of a family at
        another factor).
    chains : sequence of collection of tuple
        The edges of each shared curve, between the refined side's nodes.
    sources : collection of int, optional
        The source's nodes of the shared curves.

    Returns
    -------
    tuple
        The targets to set, by node (empty with no shared curve, FR-967), and
        per family the least, the mean and the greatest target of its curve
        nodes, twelve decimals (FR-966).
    """
    curve = _curve_targets(points, chains, held)
    if not curve:
        return {}, {}
    ids = sorted(curve)
    _, nearest = NearestIndex(points[ids]).query(points)
    start = {v for chain in chains for e in chain for v in e}
    out: dict[int, float] = {}
    for v in sorted(set(sources) - start - set(held)):
        out[v] = curve[ids[int(nearest[v])]]
    for v, d in _face_layers(faces, start, SHARED_LAYERS - 1).items():
        if v not in held:
            s = curve[ids[int(nearest[v])]]
            out[v] = s + (float(own[v]) - s) * d / SHARED_LAYERS
    out.update(curve)
    return out, _curve_record(faces, labels, curve)


def _curve_targets(
    points: Points, chains: Sequence[Collection[Edge]], held: Collection[int]
) -> dict[int, float]:
    """Return at each curve node the mean length of its incident shared edges (FR-964)."""
    total: dict[int, float] = defaultdict(float)
    count: dict[int, int] = defaultdict(int)
    for edge in sorted({_ek(*e) for chain in chains for e in chain}):
        length = float(numpy.linalg.norm(points[edge[0]] - points[edge[1]]))
        for v in edge:
            total[v] += length
            count[v] += 1
    return {v: total[v] / count[v] for v in sorted(total) if v not in held}


def _face_layers(faces: Sequence[Sequence[int]], start: set[int], depth: int) -> dict[int, int]:
    """Return the face-layer distance (1 to ``depth``) of each node so near ``start``.

    A node is one layer from a set when it shares a face with a node of it.
    """
    around: dict[int, set[int]] = defaultdict(set)
    for f in faces:
        for v in f:
            around[v].update(f)
    reached = dict.fromkeys(start, 0)
    ring = set(start)
    for d in range(1, depth + 1):
        ring = {u for v in ring for u in around[v] if u not in reached}
        reached.update(dict.fromkeys(ring, d))
    return {v: d for v, d in sorted(reached.items()) if d > 0}


def _curve_record(
    faces: Sequence[Sequence[int]], labels: Sequence[str], curve: Mapping[int, float]
) -> dict[str, dict[str, float]]:
    """Return per family the least, the mean and the greatest target of its curve nodes."""
    nodes: dict[str, set[int]] = defaultdict(set)
    for f, label in zip(faces, labels, strict=True):
        nodes[label].update(v for v in f if v in curve)
    record = {}
    for name, found in nodes.items():
        if found:
            values = [curve[v] for v in sorted(found)]
            record[name] = {
                "min": round(min(values), 12),
                "mean": round(sum(values) / len(values), 12),
                "max": round(max(values), 12),
            }
    return record


def _edge_kind(
    edge: Edge, fs: list[int], group: _Group, held: tuple[set[int], set[Edge]]
) -> str | None:
    """Return the curve key of one edge, or None for an edge free to flip.

    The trailing edge is named before an open boundary or an interface it may
    also be, so its new edges are the ones its points file is rewritten from.
    """
    fixed, te = held
    a, b = edge
    # Named before FROZEN too: a trailing-edge edge between two interface nodes is
    # still the trailing edge, and the level's points file is written from these
    # keys. It stays frozen through the frozen set (:func:`_curves`).
    if edge in te:
        return TRAILING_EDGE
    if a in fixed and b in fixed:
        return FROZEN
    if len(fs) != 2:
        return BOUNDARY
    first, second = group.labels[fs[0]], group.labels[fs[1]]
    if first != second:
        return f"{INTERFACE}:{min(first, second)}|{max(first, second)}"
    return None


def _curves(group: _Group, fixed: set[int], te: set[Edge]) -> tuple[dict[Edge, str], set[Edge]]:
    """Return every curve edge with its key, and the frozen edges."""
    dihedral = dihedral_degrees(group.verts, group.faces)
    curve: dict[Edge, str] = {}
    for edge, fs in edge_faces(group.faces).items():
        kind = _edge_kind(edge, fs, group, (fixed, te))
        if kind is None and dihedral.get(edge, 0.0) > RIDGE_DEGREES:
            kind = RIDGE
        if kind is not None:
            curve[edge] = kind
    return curve, {e for e in curve if e[0] in fixed and e[1] in fixed}


def _ordered(points: Points, families: dict[str, Faces], group: _Group) -> dict[str, Faces]:
    """Return each family oriented and ordered like its source faces (FR-921)."""
    out: dict[str, Faces] = {}
    for n, source in group.source.items():
        faces = families.get(n, [])
        if faces:
            faces = orient_like(points, faces, group.verts, source)
            faces = order_like(points, faces, group.verts, source)
        out[n] = faces
    return out
