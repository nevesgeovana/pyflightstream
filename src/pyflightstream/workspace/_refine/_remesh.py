"""Remeshing of the families a refinement does not resample as a grid (FR-424 R8, FR-425 R2).

The target edge length at a point is the source's local edge length there
divided by the family's factor, so the source's distribution of sizes is kept
and only scaled. Passes of edge split, edge collapse, edge flip and tangential
smoothing change the panel count and never the shape: every node is projected
back onto the source surface.

CURVES are the edges whose nodes move only along the source curve they lie
on and are split and collapsed along it, never flipped: open boundaries, the
trailing edge, the edges whose dihedral exceeds the ridge angle, and an
interface between two families remeshed together (remeshed once, so both
share it). An interface with a family outside the group is FROZEN: its nodes
never move, unless :meth:`Remesher.conform` first rebuilds it on the new
nodes of a grid family refined before it.

QUAD-DOMINANT families (the refinement file's ``elements``) are remeshed into
triangles first, so sizes, curves, frozen and conformed interfaces, the
trailing edge and a stretch are all honored as above; their triangles are
then paired into quadrilaterals across edges that are no curve, each pair
merged only into a convex quadrilateral within ``QUAD_ANGLE_BAND`` and
``QUAD_WARP_DEGREES`` of :mod:`._geometry`, best quality first; the
triangles left unpaired stay. Their free nodes are then smoothed and
projected onto the source surface as above, curve, fixed and corner nodes
held, and a move that would break a face is undone. A family in the default
mode, ``"triangles"``, is returned exactly as the remesh ends.

The projection onto the source surface searches a spatial index that ships
with the geometry extra, so every import of trimesh, scipy and rtree here is
deferred: a refinement of grid families alone imports none of them
(FR-424 R10). :func:`require_geometry_extra` is the check an orchestrator
calls before any family is resampled.
"""

from __future__ import annotations

import importlib
import math
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, NamedTuple

import numpy

from pyflightstream.extras import MissingExtraError, missing_extra
from pyflightstream.workspace._refine._config import QUAD_DOMINANT, TRIANGLES
from pyflightstream.workspace._refine._geometry import (
    QUAD_ANGLE_BAND,
    QUAD_WARP_DEGREES,
    RIDGE_DEGREES,
    Faces,
    Points,
    Stretch,
    dihedral_degrees,
    edge_faces,
    order_like,
    orient_like,
    quad_shapes,
)
from pyflightstream.workspace._refine._obj import ObjMesh

Edge = tuple[int, int]

#: The passes of split, collapse, flip and smoothing one remesh runs.
PASSES = 8
#: An edge longer than this multiple of its target length is split.
SPLIT_RATIO = 4.0 / 3.0
#: An edge shorter than this multiple of its target length is collapsed.
COLLAPSE_RATIO = 4.0 / 5.0
#: A collapse is refused when a moved face's normal keeps less than this cosine.
COLLAPSE_COSINE = 0.2
#: A flip is refused when a new face's normal keeps less than this cosine.
FLIP_COSINE = 0.3
#: Quad-dominant: a pairing grows the matching along alternating paths this many pairs deep.
AUGMENT_DEPTH = 4
#: Quad-dominant: the passes of smoothing after the pairing. Measured on a remeshed plate, one
#: pass to three lowers the median skewness from 0.30 to 0.26, six only to 0.25.
SMOOTH_PASSES = 3
#: Quad-dominant: a smoothing move is undone when a face's normal keeps less than this cosine.
SMOOTH_COSINE = 0.9
#: A grid node this close to an interface node (a fraction of the interface's size) keeps it.
CONFORM_FRACTION = 1e-6
#: What the geometry extra supplies to a remesh, for the refusal of FR-424 R10.
SPATIAL_INDEX = "scipy and rtree, the spatial index the projection onto the source surface searches"
#: The modules whose absence refuses a remesh (FR-424 R10).
INDEX_MODULES = ("scipy.spatial", "rtree")

#: The kinds of curve, as the keys of ``info["curve_edges"]``.
BOUNDARY = "boundary"
TRAILING_EDGE = "trailing_edge"
RIDGE = "ridge"
FROZEN = "frozen"
INTERFACE = "interface"


def geometry_extra_refusal(names: Sequence[str]) -> MissingExtraError:
    """Return the refusal of a remesh without the geometry extra (FR-424 R10, R11).

    Parameters
    ----------
    names : sequence of str
        The families the refinement would remesh.

    Returns
    -------
    MissingExtraError
        Naming the families and ``pip install pyflightstream[geom]``, its
        message ending "Nothing was written.".
    """
    noun = "family" if len(names) == 1 else "families"
    error = missing_extra(
        "geom", package=SPATIAL_INDEX, purpose=f"Remeshing the {noun} {', '.join(names)}"
    )
    # ImportError prints its ``msg`` attribute, not ``args``: both carry the ending of R11.
    error.msg = f"{error.args[0]}. Nothing was written."
    error.args = (error.msg,)
    return error


def require_geometry_extra(families: Iterable[str]) -> None:
    """Refuse a remesh, before any work, when the geometry extra is missing (FR-424 R10).

    Parameters
    ----------
    families : iterable of str
        The families the refinement would remesh; none means no check.

    Raises
    ------
    MissingExtraError
        When scipy or rtree cannot be imported.
    """
    names = list(families)
    if not names:
        return
    try:
        for module in INDEX_MODULES:
            importlib.import_module(module)
    except ImportError as error:
        raise geometry_extra_refusal(names) from error


def _ek(a: int, b: int) -> Edge:
    """Return the undirected key of an edge, low vertex first."""
    return (a, b) if a < b else (b, a)


def _unit_normal(p: Points) -> Points:
    """Return the (unnormalised) normal of a triangle given as three rows."""
    return numpy.cross(p[1] - p[0], p[2] - p[0])


def _keeps_direction(n0: Points, n1: Points, cosine: float) -> bool:
    """Return whether n1 turns away from n0 by less than the given cosine allows."""
    return bool(numpy.dot(n0, n1) > cosine * numpy.linalg.norm(n0) * numpy.linalg.norm(n1))


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


class Remesher:
    """Split, collapse, flip and smooth a patch towards its target edge lengths.

    With a stretch (FR-428) the nodes live in the stretched space while every
    projection is made in the real one: a moved node is mapped back, placed
    on the real source surface or curve, and mapped forward again. A fixed
    node keeps its real coordinates exactly.

    Parameters
    ----------
    patch : Patch
        The triangles, their curves, fixed nodes and target lengths.
    """

    def __init__(self, patch: Patch) -> None:
        import trimesh

        self.stretch = patch.stretch
        real = numpy.asarray(patch.verts, dtype=float)
        self.V = list(self._to_work(real))
        self.exact: dict[int, Points] = {v: real[v] for v in patch.fixed} if self.stretch else {}
        self.F: dict[int, list[int]] = {i: list(f) for i, f in enumerate(patch.faces)}
        self.L: dict[int, str] = dict(enumerate(patch.labels))
        self.next_face = len(patch.faces)
        self.E: dict[Edge, set[int]] = defaultdict(set)
        self.VF: dict[int, set[int]] = defaultdict(set)
        for i, f in self.F.items():
            self._index_face(i, f)
        self.fixed = set(patch.fixed)
        self.frozen = set(patch.frozen)
        self.CE = dict(patch.curve)
        self.vcurve: dict[int, set[str]] = {}
        ends: dict[int, list[int]] = defaultdict(list)
        for (a, b), key in self.CE.items():
            self.vcurve.setdefault(a, set()).add(key)
            self.vcurve.setdefault(b, set()).add(key)
            ends[a].append(b)
            ends[b].append(a)
        self.corner = {v for v, ks in self.vcurve.items() if len(ks) > 1 or self._turns(v, ends[v])}
        self.h = [float(x) for x in patch.target]
        self.h_source = numpy.asarray(patch.target, dtype=float)
        self.surface = trimesh.Trimesh(
            numpy.asarray(patch.verts), numpy.asarray(patch.faces), process=False
        )
        self.curves = self._source_curves(patch)

    def _turns(self, v: int, ends: list[int]) -> bool:
        """Return whether a curve node is a corner: the end of a curve, a branch, or a sharp turn.

        A node where its curve turns by more than the ridge angle keeps its
        place, as a node on two curves does, so a corner of a boundary is
        not cut by smoothing along it. The turn is measured in the real space,
        since a stretch (FR-428) changes angles.
        """
        if len(ends) != 2:
            return True
        a, p, b = self._real_points([ends[0], v, ends[1]])
        before, after = p - a, b - p
        return not _keeps_direction(before, after, math.cos(math.radians(RIDGE_DEGREES)))

    def _source_curves(self, patch: Patch) -> dict[str, tuple[Points, Points]]:
        """Return the source segments of each curve, the targets of its nodes' projection."""
        segments: dict[str, list[Edge]] = defaultdict(list)
        for edge, key in patch.curve.items():
            segments[key].append(edge)
        verts = numpy.asarray(patch.verts, dtype=float)
        return {
            key: (verts[[a for a, _ in es]], verts[[b for _, b in es]])
            for key, es in segments.items()
        }

    # ---- the stretched space (FR-428)

    def _to_work(self, points: Points) -> Points:
        """Return real points in the space the remesh runs in (themselves without a stretch)."""
        return points if self.stretch is None else self.stretch.forward(points)

    def _to_real(self, points: Points) -> Points:
        """Return points of the remesh's space in the real space."""
        return points if self.stretch is None else self.stretch.inverse(points)

    def _real_points(self, ids: Sequence[int]) -> Points:
        """Return the real coordinates of some nodes, a fixed node's exactly as it came."""
        points = numpy.array([self.V[v] for v in ids]).reshape(-1, 3)
        if self.stretch is None:
            return points
        points = self._to_real(points)
        for i, v in enumerate(ids):
            if v in self.exact:
                points[i] = self.exact[v]
        return points

    # ---- bookkeeping

    def _index_face(self, i: int, f: list[int]) -> None:
        for a, b in zip(f, f[1:] + f[:1], strict=True):
            self.E[_ek(a, b)].add(i)
        for v in f:
            self.VF[v].add(i)

    def _del_face(self, i: int) -> list[int]:
        f = self.F.pop(i)
        self.L.pop(i)
        for a, b in zip(f, f[1:] + f[:1], strict=True):
            k = _ek(a, b)
            self.E[k].discard(i)
            if not self.E[k]:
                del self.E[k]
        for v in f:
            self.VF[v].discard(i)
        return f

    def _new_face(self, f: list[int], label: str) -> None:
        i = self.next_face
        self.next_face += 1
        self.F[i] = f
        self.L[i] = label
        self._index_face(i, f)

    def neighbours(self, v: int) -> set[int]:
        """Return the vertices that share a face with v."""
        out: set[int] = set()
        for i in self.VF[v]:
            out.update(self.F[i])
        out.discard(v)
        return out

    def _length(self, k: Edge) -> float:
        return float(numpy.linalg.norm(self.V[k[0]] - self.V[k[1]]))

    def _target(self, k: Edge) -> float:
        return 0.5 * (self.h[k[0]] + self.h[k[1]])

    def _curve_neighbours(self, v: int) -> list[int]:
        return [u for u in sorted(self.neighbours(v)) if _ek(u, v) in self.CE]

    # ---- operations

    def split(self, a: int, b: int) -> int:
        """Split the edge a-b at its mid-point and return the new vertex."""
        k = _ek(a, b)
        m = len(self.V)
        self.V.append(0.5 * (self.V[a] + self.V[b]))
        self.h.append(0.5 * (self.h[a] + self.h[b]))
        key = self.CE.pop(k, None)
        for i in sorted(self.E[k]):
            f, label = self.F[i], self.L[i]
            self._del_face(i)
            j = f.index(a)
            if f[(j + 1) % 3] == b:
                c = f[(j + 2) % 3]
                self._new_face([a, m, c], label)
                self._new_face([m, b, c], label)
            else:
                c = f[(j + 1) % 3]
                self._new_face([a, c, m], label)
                self._new_face([m, c, b], label)
        if key is not None:
            self.CE[_ek(a, m)] = key
            self.CE[_ek(m, b)] = key
            self.vcurve[m] = {key}
        if k in self.frozen:
            self.frozen.discard(k)
            self.frozen |= {_ek(a, m), _ek(m, b)}
        return m

    def split_at(self, a: int, b: int, point: Points) -> int:
        """Split the edge a-b at the given point and return the new vertex."""
        m = self.split(a, b)
        self.V[m] = numpy.asarray(point, dtype=float).copy()
        return m

    def _link_ok(self, a: int, b: int) -> bool:
        """Return whether collapsing a-b keeps the surface a manifold (the link condition)."""
        k = _ek(a, b)
        opposite = {v for i in self.E[k] for v in self.F[i] if v not in (a, b)}
        return (self.neighbours(a) & self.neighbours(b)) == opposite

    def _no_long_edge(self, a: int, b: int) -> bool:
        """Return whether collapsing a onto b leaves no edge above the split length."""
        hb, pb = self.h[b], self.V[b]
        return all(
            numpy.linalg.norm(self.V[v] - pb) <= SPLIT_RATIO * 0.5 * (self.h[v] + hb)
            for v in self.neighbours(a)
            if v != b
        )

    def _no_fold(self, a: int, b: int) -> bool:
        """Return whether collapsing a onto b turns no face over."""
        for i in self.VF[a]:
            f = self.F[i]
            if b in f:
                continue
            before = numpy.array([self.V[x] for x in f])
            after = numpy.array([self.V[b] if x == a else self.V[x] for x in f])
            if not _keeps_direction(_unit_normal(before), _unit_normal(after), COLLAPSE_COSINE):
                return False
        return True

    def can_collapse(self, a: int, b: int) -> bool:
        """Return whether a may collapse onto b."""
        if a in self.fixed or a in self.corner:
            return False
        on_curve = _ek(a, b) in self.CE
        if (a in self.vcurve) != on_curve:
            return False
        return self._link_ok(a, b) and self._no_long_edge(a, b) and self._no_fold(a, b)

    def collapse(self, a: int, b: int) -> None:
        """Collapse vertex a onto vertex b."""
        k = _ek(a, b)
        around = sorted(self.neighbours(a))
        for i in sorted(self.E[k]):
            self._del_face(i)
        self.CE.pop(k, None)
        for i in sorted(self.VF[a]):
            f, label = self.F[i], self.L[i]
            self._del_face(i)
            self._new_face([b if x == a else x for x in f], label)
        for o in around:
            key = self.CE.pop(_ek(a, o), None)
            if key is not None and o != b:
                self.CE[_ek(o, b)] = key
        self.vcurve.pop(a, None)
        if self.frozen:
            renamed = {_ek(b if x == a else x, b if y == a else y) for x, y in self.frozen}
            self.frozen = {e for e in renamed if e[0] != e[1]}

    def _valence_gain(self, a: int, b: int, c: int, d: int) -> bool:
        """Return whether flipping a-b into c-d moves the valences towards their ideal."""
        valence = {v: len(self.neighbours(v)) for v in (a, b, c, d)}

        def deviation(v: int, n: int) -> int:
            return abs(n - (4 if v in self.vcurve else 6))

        before = sum(deviation(v, valence[v]) for v in (a, b, c, d))
        after = (
            deviation(a, valence[a] - 1)
            + deviation(b, valence[b] - 1)
            + deviation(c, valence[c] + 1)
            + deviation(d, valence[d] + 1)
        )
        return after < before

    def try_flip(self, a: int, b: int) -> bool:
        """Flip the edge a-b when it is not a curve and the valences improve."""
        k = _ek(a, b)
        fs = sorted(self.E.get(k, ()))
        if len(fs) != 2 or k in self.CE or self.L[fs[0]] != self.L[fs[1]]:
            return False
        f0, f1 = self.F[fs[0]], self.F[fs[1]]
        c = next(v for v in f0 if v not in (a, b))
        d = next(v for v in f1 if v not in (a, b))
        if _ek(c, d) in self.E or not self._valence_gain(a, b, c, d):
            return False
        j = f0.index(a)
        n0, n1 = ([a, d, c], [b, c, d]) if f0[(j + 1) % 3] == b else ([a, c, d], [b, d, c])
        old = _unit_normal(numpy.array([self.V[x] for x in f0]))
        for g in (n0, n1):
            if not _keeps_direction(
                old, _unit_normal(numpy.array([self.V[x] for x in g])), FLIP_COSINE
            ):
                return False
        label = self.L[fs[0]]
        self._del_face(fs[0])
        self._del_face(fs[1])
        self._new_face(n0, label)
        self._new_face(n1, label)
        return True

    # ---- smoothing and projection

    def _tangent_move(self, v: int) -> Points:
        """Return v moved halfway to its neighbours' centroid within its tangent plane."""
        centroid = numpy.mean([self.V[u] for u in sorted(self.neighbours(v))], axis=0)
        normal = numpy.zeros(3)
        for i in sorted(self.VF[v]):
            normal += _unit_normal(numpy.array([self.V[x] for x in self.F[i]]))
        normal /= max(float(numpy.linalg.norm(normal)), 1e-300)
        d = centroid - self.V[v]
        return self.V[v] + 0.5 * (d - numpy.dot(d, normal) * normal)

    def _curve_move(self, v: int) -> Points | None:
        """Return v moved towards its two curve neighbours, or None at a curve's end."""
        ends = self._curve_neighbours(v)
        if len(ends) != 2:
            return None
        return 0.5 * self.V[v] + 0.25 * (self.V[ends[0]] + self.V[ends[1]])

    def _onto_curve(self, v: int, p: Points) -> Points:
        """Return the point of v's source curve nearest p, found in the real space."""
        key = min(self.vcurve[v])
        if key not in self.curves:
            return self.V[v]
        a, b = self.curves[key]
        p = self._to_real(p)
        ab = b - a
        t = numpy.clip(
            ((p - a) * ab).sum(axis=1) / numpy.maximum((ab * ab).sum(axis=1), 1e-300), 0, 1
        )
        on = a + t[:, None] * ab
        return self._to_work(on[int(numpy.argmin(numpy.linalg.norm(on - p, axis=1)))])

    def _onto_surface(self, moves: dict[int, Points]) -> None:
        """Place the free moved vertices on the source surface and read their target there."""
        from trimesh.proximity import closest_point
        from trimesh.triangles import points_to_barycentric

        free = [v for v in moves if v not in self.vcurve]
        if not free:
            return
        q, _, tid = closest_point(
            self.surface, self._to_real(numpy.array([moves[v] for v in free]))
        )
        bary = points_to_barycentric(self.surface.triangles[tid], q)
        hq = (bary * self.h_source[self.surface.faces[tid]]).sum(axis=1)
        for v, p, h in zip(free, self._to_work(q), hq, strict=True):
            self.V[v] = numpy.asarray(p, dtype=float)
            self.h[v] = float(h)

    def smooth_and_project(self) -> None:
        """Smooth every movable vertex and project it back onto the source surface or curve."""
        moves: dict[int, Points] = {}
        for v in sorted(v for v, fs in self.VF.items() if fs):
            if v in self.fixed or v in self.corner:
                continue
            p = self._curve_move(v) if v in self.vcurve else self._tangent_move(v)
            if p is not None:
                moves[v] = p
        self._onto_surface(moves)
        for v in [v for v in moves if v in self.vcurve]:
            self.V[v] = self._onto_curve(v, moves[v])

    # ---- the passes

    def _held(self, k: Edge) -> bool:
        """Return whether an edge may not be split (frozen, or fixed at both ends on a curve)."""
        if k in self.frozen:
            return True
        both_fixed = k[0] in self.fixed and k[1] in self.fixed
        return both_fixed and (k in self.CE or len(self.E[k]) == 1)

    def _split_long(self) -> None:
        for k in [k for k in list(self.E) if self._length(k) > SPLIT_RATIO * self._target(k)]:
            if k in self.E and not self._held(k):
                self.split(*k)

    def _collapse_short(self) -> None:
        for k in sorted(self.E, key=self._length):
            if k not in self.E or self._length(k) >= COLLAPSE_RATIO * self._target(k):
                continue
            a, b = k
            if self.can_collapse(a, b):
                self.collapse(a, b)
            elif self.can_collapse(b, a):
                self.collapse(b, a)

    def run(self, passes: int = PASSES) -> None:
        """Run the passes of split, collapse, flip and smoothing."""
        for _ in range(passes):
            self._split_long()
            self._collapse_short()
            for k in list(self.E):
                if k in self.E:
                    self.try_flip(*k)
            self.smooth_and_project()

    # ---- conforming an interface to a grid's new nodes (FR-425 R2)

    def _place(self, p: Points, chain: set[Edge], keep: set[int], tol: float) -> int:
        """Keep the chain node at p, or insert one there; return 1 when a node was inserted."""
        on = sorted({v for k in chain for v in k})
        d = numpy.linalg.norm(numpy.array([self.V[v] for v in on]) - p, axis=1)
        j = int(numpy.argmin(d))
        if d[j] < tol and on[j] not in keep:
            keep.add(on[j])
            self.V[on[j]] = p.copy()
            return 0
        k = min(sorted(chain), key=lambda e: _segment_distance(self.V[e[0]], self.V[e[1]], p))
        m = self.split_at(k[0], k[1], p)
        chain.discard(k)
        for e in (_ek(k[0], m), _ek(m, k[1])):
            chain.add(e)
            self.frozen.add(e)
            self.CE.setdefault(e, FROZEN)
        keep.add(m)
        return 1

    def _drop(self, o: int, chain: set[Edge], keep: set[int]) -> bool:
        """Collapse a chain node no new node keeps onto a chain neighbour; return success."""
        ends = [x for k in sorted(chain) if o in k for x in k if x != o]
        order = sorted(
            ends, key=lambda x: (x not in keep, float(numpy.linalg.norm(self.V[x] - self.V[o])), x)
        )
        for b in order:
            if not self._link_ok(o, b):
                continue
            self.collapse(o, b)
            renamed = {_ek(b if x == o else x, b if y == o else y) for x, y in chain}
            chain.clear()
            chain.update(e for e in renamed if e[0] != e[1])
            self.fixed.discard(o)
            self.corner.discard(o)
            return True
        return False

    def conform(self, old: Iterable[int], new_points: Points) -> dict[str, int]:
        """Rebuild a frozen interface on the new nodes of a grid refined before it (FR-425 R2).

        Each new point is inserted on the interface at its own position (an
        old node it coincides with is kept and takes the point exactly), each
        old node no new point keeps is collapsed along the interface, and the
        result is fixed node for node, so the two families weld again.

        Parameters
        ----------
        old : iterable of int
            The local vertices of the interface in the source.
        new_points : ndarray
            The grid's new nodes on that interface, in the real space.

        Returns
        -------
        dict
            The counts ``inserted``, ``kept``, ``removed`` and ``not_removed``.
        """
        old_set = set(old)
        chain = {
            k for k, fs in self.E.items() if k[0] in old_set and k[1] in old_set and len(fs) == 1
        }
        if not chain:
            return {"inserted": 0, "kept": 0, "removed": 0, "not_removed": 0}
        span = numpy.array([self.V[v] for v in sorted(old_set)])
        tol = CONFORM_FRACTION * max(float(numpy.linalg.norm(numpy.ptp(span, axis=0))), 1e-300)
        keep: set[int] = set()
        real = numpy.asarray(new_points, dtype=float).reshape(-1, 3)
        inserted = 0
        for p, q in zip(real, self._to_work(real), strict=True):
            before = set(keep)
            inserted += self._place(q, chain, keep, tol)
            if self.stretch is not None:
                self.exact.update(dict.fromkeys(keep - before, p))
        dropped = [self._drop(o, chain, keep) for o in sorted({v for k in chain for v in k} - keep)]
        self.fixed |= keep
        return {
            "inserted": inserted,
            "kept": len(keep) - inserted,
            "removed": sum(dropped),
            "not_removed": len(dropped) - sum(dropped),
        }

    # ---- quad-dominant: pairing triangles into quadrilaterals

    def _real_all(self) -> Points:
        """Return the real coordinates of every node, a fixed node's exactly as it came."""
        return self._real_points(range(len(self.V)))

    def _mergeable(self, k: Edge, labels: set[str]) -> tuple[int, int] | None:
        """Return the two triangles an edge may be merged across, or None.

        It may when it is no curve (an open boundary, the trailing edge, a
        ridge, an interface, a frozen edge) and its two faces are triangles
        of one quad-dominant family.
        """
        fs = self.E.get(k, set())
        if len(fs) != 2 or k in self.CE or k in self.frozen:
            return None
        i, j = sorted(fs)
        same = self.L[i] == self.L[j] and self.L[i] in labels
        return (i, j) if same and len(self.F[i]) == len(self.F[j]) == 3 else None

    def _merge_candidates(self, labels: set[str]) -> tuple[list[tuple[int, int]], Faces, Points]:
        """Return every pair of triangles that merges into a valid quadrilateral, and its quality.

        A quadrilateral is valid when it is convex, every interior angle lies
        in ``QUAD_ANGLE_BAND`` and its warp is at most ``QUAD_WARP_DEGREES``,
        all measured in the real space. Its quality is one minus its
        equiangle skewness, 1 for a rectangle.
        """
        pairs: list[tuple[int, int]] = []
        quads: Faces = []
        for k in sorted(self.E):
            pair = self._mergeable(k, labels)
            quad = None if pair is None else _quad_of(self.F[pair[0]], self.F[pair[1]], k)
            if pair is not None and quad is not None:
                pairs.append(pair)
                quads.append(quad)
        if not quads:
            return [], [], numpy.zeros(0)
        angle, warp, convex = quad_shapes(self._real_all()[numpy.array(quads)])
        low, high = QUAD_ANGLE_BAND
        valid = convex & (angle.min(axis=1) >= low) & (angle.max(axis=1) <= high)
        valid &= warp <= QUAD_WARP_DEGREES
        quality = 1.0 - numpy.abs(angle - 90.0).max(axis=1) / 90.0
        keep = numpy.nonzero(valid)[0].tolist()
        return [pairs[c] for c in keep], [quads[c] for c in keep], quality[keep]

    def pair_quads(self, labels: Iterable[str]) -> int:
        """Merge pairs of triangles of the given families into quadrilaterals; return how many.

        The pairs are chosen best quality first (a greedy matching), then
        the matching is grown along alternating paths of up to
        :data:`AUGMENT_DEPTH` matched pairs, each of which merges one more
        pair, so the share of quadrilaterals is high. A quadrilateral runs
        through its corners the way its two triangles did, so it keeps their
        orientation. Curves are never merged across; nodes do not move.
        """
        pairs, quads, quality = self._merge_candidates(set(labels))
        mate = _matching(pairs, quality)
        merged = 0
        for (i, j), quad in zip(pairs, quads, strict=True):
            if mate.get(i) == j and i in self.F and j in self.F:
                label = self.L[i]
                self._del_face(i)
                self._del_face(j)
                self._new_face(quad, label)
                merged += 1
        return merged

    def _edge_neighbors(self, v: int) -> list[int]:
        """Return the nodes joined to v by a face edge (not across a quadrilateral)."""
        out: set[int] = set()
        for i in self.VF[v]:
            f = self.F[i]
            j = f.index(v)
            out.update((f[j - 1], f[(j + 1) % len(f)]))
        return sorted(out)

    def _face_valid(self, i: int, real: Points, normal: Points) -> bool:
        """Return whether a face keeps its normal's direction and, a quadrilateral, its shape."""
        p = real[self.F[i]]
        if not _keeps_direction(normal, _face_normal(p), SMOOTH_COSINE):
            return False
        if len(p) != 4:
            return True
        angle, warp, convex = quad_shapes(p[None])
        low, high = QUAD_ANGLE_BAND
        inside = low <= float(angle.min()) and float(angle.max()) <= high
        return bool(convex[0]) and inside and float(warp[0]) <= QUAD_WARP_DEGREES

    def smooth_quads(self, labels: Iterable[str]) -> int:
        """Smooth the free nodes of quad-dominant families once; return how many moved.

        A node moves halfway to the centroid of its edge neighbors within its
        tangent plane and is projected onto the source surface, as the
        remesh's own smoothing does. Nodes on a curve, fixed, frozen or at a
        corner never move, nor any node of a family not in ``labels``. A move
        that turns a face by more than :data:`SMOOTH_COSINE` allows or leaves
        a quadrilateral outside the merge bounds is undone, with the moves of
        the face's other nodes, until every face is valid again.
        """
        families = set(labels)
        free = [
            v
            for v in sorted(v for v, fs in self.VF.items() if fs)
            if v not in self.fixed
            and v not in self.vcurve
            and v not in self.corner
            and all(self.L[i] in families for i in self.VF[v])
        ]
        if not free:
            return 0
        before = {v: (self.V[v].copy(), self.h[v]) for v in free}
        real = self._real_all()
        touched = sorted({i for v in free for i in self.VF[v]})
        normals = {i: _face_normal(real[self.F[i]]) for i in touched}
        self._onto_surface({v: self._tangent_quad_move(v) for v in free})
        moved = set(free)
        while True:
            real = self._real_all()
            bad = [i for i in touched if not self._face_valid(i, real, normals[i])]
            back = {v for i in bad for v in self.F[i] if v in moved}
            if not back:
                return len(moved)
            for v in sorted(back):
                self.V[v], self.h[v] = before[v]
            moved -= back

    def _tangent_quad_move(self, v: int) -> Points:
        """Return v moved halfway to its edge neighbors' centroid within its tangent plane."""
        centroid = numpy.mean([self.V[u] for u in self._edge_neighbors(v)], axis=0)
        normal = numpy.zeros(3)
        for i in sorted(self.VF[v]):
            normal += _face_normal(numpy.array([self.V[x] for x in self.F[i]]))
        normal /= max(float(numpy.linalg.norm(normal)), 1e-300)
        d = centroid - self.V[v]
        return self.V[v] + 0.5 * (d - numpy.dot(d, normal) * normal)

    # ---- the result

    def edge_ratio_median(self) -> float:
        """Return the median ratio of a non-curve edge's length to its target (FR-424 R8)."""
        ratios = [self._length(k) / self._target(k) for k in self.E if k not in self.CE]
        return float(numpy.median(ratios)) if ratios else float("nan")

    def result(self) -> tuple[Points, dict[str, Faces], Points]:
        """Return the points, the faces per family and the trailing-edge mid-points."""
        used = sorted({v for f in self.F.values() for v in f})
        renumber = {v: i for i, v in enumerate(used)}
        points = self._real_points(used)
        families: dict[str, Faces] = defaultdict(list)
        for i, f in self.F.items():
            families[self.L[i]].append([renumber[v] for v in f])
        te = [k for k, key in self.CE.items() if key == TRAILING_EDGE]
        mid = 0.5 * (self._real_points([a for a, _ in te]) + self._real_points([b for _, b in te]))
        return points, dict(families), mid


def _face_normal(p: Points) -> Points:
    """Return a polygon's (unnormalized) normal: the cross product of its diagonals for four."""
    if len(p) == 4:
        return numpy.cross(p[2] - p[0], p[3] - p[1])
    return _unit_normal(p)


def _quad_of(f0: list[int], f1: list[int], k: Edge) -> list[int] | None:
    """Return the quadrilateral two triangles sharing the edge k make, or None.

    The first triangle runs a, b, c and the second must run b, a, d (the two
    agree in orientation); the quadrilateral is a, d, b, c, which runs every
    remaining edge the way its triangle did.
    """
    a, b = k
    j = f0.index(a)
    if f0[(j + 1) % 3] != b:
        a, b = b, a
        j = f0.index(a)
    c = f0[(j + 2) % 3]
    m = f1.index(b)
    if f1[(m + 1) % 3] != a:
        return None
    return [a, f1[(m + 2) % 3], b, c]


def _matching(pairs: Sequence[tuple[int, int]], quality: Points) -> dict[int, int]:
    """Return a matching of triangles: greedy best quality first, then grown.

    Ties of quality are broken by the pair's face numbers, so the matching is
    deterministic (FR-424 R12).
    """
    mate: dict[int, int] = {}
    order = sorted(range(len(pairs)), key=lambda c: (-float(quality[c]), pairs[c]))
    for c in order:
        i, j = pairs[c]
        if i not in mate and j not in mate:
            mate[i], mate[j] = j, i
    around: dict[int, list[int]] = defaultdict(list)
    for c in order:
        i, j = pairs[c]
        around[i].append(j)
        around[j].append(i)
    grown = True
    while grown:
        grown = False
        for t in sorted(around):
            if t not in mate and _augment(t, around, mate, AUGMENT_DEPTH, {t}):
                grown = True
    return mate


def _augment(
    t: int, around: Mapping[int, list[int]], mate: dict[int, int], depth: int, seen: set[int]
) -> bool:
    """Grow the matching by an alternating path from the free triangle t; return success.

    The path leaves t by a pair not in the matching, crosses a matched pair,
    and so on, until it reaches a free triangle, at most ``depth`` matched
    pairs deep and never through a triangle twice; it is then flipped, which
    matches one more pair.
    """
    for u in around[t]:
        if u in seen:
            continue
        w = mate.get(u)
        if w is None:
            mate[t], mate[u] = u, t
            return True
        if depth > 0 and w not in seen and _augment(w, around, mate, depth - 1, seen | {u, w}):
            mate[t], mate[u] = u, t
            return True
    return False


def element_report(mode: str, faces: Faces) -> dict[str, Any]:
    """Return what ``refine.json`` states of a remeshed family's elements.

    Parameters
    ----------
    mode : str
        The family's element mode, ``"triangles"`` or ``"quad-dominant"``.
    faces : list of list of int
        Its faces in the level.

    Returns
    -------
    dict
        ``elements`` (the mode), ``quads``, ``triangles`` and ``quad_share``
        (the quadrilaterals over the faces, six decimals).
    """
    quads = sum(len(f) == 4 for f in faces)
    share = quads / len(faces) if faces else 0.0
    return {
        "elements": mode,
        "quads": quads,
        "triangles": len(faces) - quads,
        "quad_share": round(share, 6),
    }


def _segment_distance(a: Points, b: Points, p: Points) -> float:
    """Return the distance from p to the segment a-b."""
    ab = b - a
    t = numpy.clip(numpy.dot(p - a, ab) / max(float(numpy.dot(ab, ab)), 1e-300), 0, 1)
    return float(numpy.linalg.norm(a + t * ab - p))


class Remeshed(NamedTuple):
    """The remesh of a group of families.

    Attributes
    ----------
    points : ndarray
        The group's new nodes.
    families : dict
        Each family's new triangles in the source's face order (FR-424 R7).
    trailing_edge : ndarray
        The mid-point of every trailing-edge edge of the new mesh.
    info : dict
        What ``refine.json`` reports of the remesh (JSON values only).
    """

    points: Points
    families: dict[str, Faces]
    trailing_edge: Points
    info: dict[str, Any]


@dataclass
class _Group:
    """The local numbering of a group: source vertices, triangles, labels, source faces."""

    ids: list[int]
    verts: Points
    faces: Faces
    labels: list[str]
    source: dict[str, Faces]


def _group(mesh: ObjMesh, names: Sequence[str]) -> _Group:
    """Return the group's faces numbered locally, each polygon fanned into triangles."""
    ids = sorted({v for n in names for f in mesh.families[n] for v in f})
    local = {v: i for i, v in enumerate(ids)}
    source = {n: [[local[v] for v in f] for f in mesh.families[n]] for n in names}
    faces: Faces = []
    labels: list[str] = []
    for n in names:
        for f in source[n]:
            fan = [[f[0], f[k], f[k + 1]] for k in range(1, len(f) - 1)]
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


def _edge_kind(
    edge: Edge, fs: list[int], group: _Group, held: tuple[set[int], set[int]]
) -> str | None:
    """Return the curve key of one edge, or None for an edge free to flip.

    The trailing edge is named before an open boundary or an interface it may
    also be, so its new edges are the ones its points file is rewritten from.
    """
    fixed, te = held
    a, b = edge
    if a in fixed and b in fixed:
        return FROZEN
    if a in te and b in te:
        return TRAILING_EDGE
    if len(fs) != 2:
        return BOUNDARY
    first, second = group.labels[fs[0]], group.labels[fs[1]]
    if first != second:
        return f"{INTERFACE}:{min(first, second)}|{max(first, second)}"
    return None


def _curves(group: _Group, fixed: set[int], te: set[int]) -> tuple[dict[Edge, str], set[Edge]]:
    """Return every curve edge with its key, and the frozen edges."""
    dihedral = dihedral_degrees(group.verts, group.faces)
    curve: dict[Edge, str] = {}
    for edge, fs in edge_faces(group.faces).items():
        kind = _edge_kind(edge, fs, group, (fixed, te))
        if kind is None and dihedral.get(edge, 0.0) > RIDGE_DEGREES:
            kind = RIDGE
        if kind is not None:
            curve[edge] = kind
    return curve, {e for e, k in curve.items() if k == FROZEN}


def _ordered(points: Points, families: dict[str, Faces], group: _Group) -> dict[str, Faces]:
    """Return each family oriented and ordered like its source faces (FR-424 R7)."""
    out: dict[str, Faces] = {}
    for n, source in group.source.items():
        faces = families.get(n, [])
        if faces:
            faces = orient_like(points, faces, group.verts, source)
            faces = order_like(points, faces, group.verts, source)
        out[n] = faces
    return out


def refine_group(
    mesh: ObjMesh,
    names: Sequence[str],
    te_vertices: Iterable[int],
    factor: float | Mapping[str, float],
    *,
    conform: Sequence[tuple[Iterable[int], Points]] = (),
    stretch: Stretch | None = None,
    elements: str | Mapping[str, str] = TRIANGLES,
) -> Remeshed:
    """Remesh a group of families together (FR-424 R8, FR-425 R2, FR-428).

    An interface between two families of the group is a curve remeshed once
    and shared by both; an interface with any other family of the mesh is
    frozen node for node, unless ``conform`` rebuilds it first on the new
    nodes of a grid family refined before it.

    A body refined along and around its axis (FR-428) is remeshed in the
    space ``stretch`` maps it into, towards the source's local lengths
    measured in the real space (its factor is 1): an edge of length L there
    is L / axial long along the axis and L / circumferential around it once
    mapped back. The curves (the dihedral of R8) are found in the real space
    and every node is projected onto the real source surface.

    Parameters
    ----------
    mesh : ObjMesh
        The source mesh; families outside ``names`` are read, never changed.
    names : sequence of str
        The families remeshed together, in the source's family order.
    te_vertices : iterable of int
        The source vertices of the trailing edge (mesh numbering).
    factor : float or mapping of str to float
        One factor for every family, or a factor per family.
    conform : sequence of (iterable of int, ndarray), optional
        For each interface with a grid family refined first, its source
        vertices (mesh numbering) and the grid's new nodes on it.
    stretch : Stretch, optional
        The map of a body refined with ``axial`` and ``circumferential``;
        every family of the group is remeshed in its space.
    elements : str or mapping of str to str, optional
        One element mode for every family, or a mode per family:
        ``"triangles"`` (the default; the remesh is returned as it ends) or
        ``"quad-dominant"`` (after the remesh, the family's triangles are
        paired into quadrilaterals by :meth:`Remesher.pair_quads` and its free
        nodes smoothed :data:`SMOOTH_PASSES` times by
        :meth:`Remesher.smooth_quads`).

    Returns
    -------
    Remeshed
        The points, the faces per family, the trailing-edge mid-points and the info.

    Raises
    ------
    MissingExtraError
        When the geometry extra is missing, before any work (FR-424 R10).
    """
    require_geometry_extra(names)
    factors = dict(factor) if isinstance(factor, Mapping) else {n: float(factor) for n in names}
    group = _group(mesh, names)
    local = {v: i for i, v in enumerate(group.ids)}
    others = [n for n in mesh.families if n not in names]
    fixed = {local[v] for n in others for v in mesh.family_vertices(n).tolist() if v in local}
    te = {local[v] for v in te_vertices if v in local}
    curve, frozen = _curves(group, fixed, te)
    patch = Patch(group.verts, group.faces, group.labels, _targets(group, factors), curve)
    patch.fixed, patch.frozen, patch.stretch = fixed, frozen, stretch
    remesher = Remesher(patch)
    conformed = [
        remesher.conform([local[v] for v in old if v in local], new) for old, new in conform
    ]
    remesher.run()
    modes = dict(elements) if isinstance(elements, Mapping) else dict.fromkeys(names, elements)
    quad_families = [n for n in names if modes.get(n, TRIANGLES) == QUAD_DOMINANT]
    if quad_families:
        remesher.pair_quads(quad_families)
        for _ in range(SMOOTH_PASSES):
            remesher.smooth_quads(quad_families)
    points, families, te_mid = remesher.result()
    kinds: dict[str, int] = defaultdict(int)
    for key in curve.values():
        kinds[key.partition(":")[0]] += 1
    info: dict[str, Any] = {
        "method": "remesh",
        "remeshed_together": list(names),
        "fixed_interface_nodes": len(fixed),
        "curve_edges": dict(sorted(kinds.items())),
        "edge_ratio_median": round(remesher.edge_ratio_median(), 6),
    }
    if conformed:
        info["conformed_interfaces"] = conformed
    if stretch is not None:
        info["stretched"] = {
            "axis": [round(float(x), 12) for x in stretch.axis],
            "axial": stretch.factors[0],
            "circumferential": stretch.factors[1],
        }
    return Remeshed(points, _ordered(points, families, group), te_mid, info)
