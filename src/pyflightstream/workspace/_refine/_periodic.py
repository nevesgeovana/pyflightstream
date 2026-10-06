"""The two cut faces of a periodic sector, refined node for node (FR-427).

A sector is one of ``copies`` identical pieces of a turn about an axis; its
two CUT BOUNDARIES are open boundary chains that the rotation by 360/copies
degrees maps onto each other. The source's are found before any work and
refused when they do not match (R2); the level's are made to match:

* a side whose families are all refined as a grid or left unchanged keeps
  its nodes, and the other side is rebuilt on them, rotated;
* when both sides are remeshed, the first side (the MASTER, its family
  first in the source's family order) is resampled along its own nodes by
  the family's factor, and both sides are rebuilt on those positions;
* after assembly, every node of the other side (the SLAVE) is placed on its
  master node rotated, and the match is measured (R1).

The open boundary is split into chains at its corners (a node where it
turns by more than the ridge angle, or where more than two boundary edges
meet), so a cut is one chain or several, each paired with its image.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from itertools import combinations, pairwise
from typing import Any

import numpy
from numpy.typing import NDArray

from pyflightstream._errors import InputArtifactError
from pyflightstream.workspace._refine._config import Periodic
from pyflightstream.workspace._refine._geometry import (
    DUPLICATE_FRACTION,
    ON_CURVE_FRACTION,
    PERIODIC_LEVEL_FRACTION,
    PERIODIC_SOURCE_FRACTION,
    RIDGE_DEGREES,
    Faces,
    NearestIndex,
    Points,
    boundary_edges,
    boundary_loops,
    segment_distances,
)
from pyflightstream.workspace._refine._obj import KIND

Conform = list[tuple[set[int], Points]]


@dataclass(frozen=True)
class CutPair:
    """One chain of the master cut and its image on the slave cut.

    Attributes
    ----------
    master, slave : tuple of int
        The source vertices of each chain, in order along it.
    sense : int
        +1 when the master rotated by +360/copies degrees lands on the slave, else -1.
    distance : float
        The largest distance between a rotated master node and its slave node, in the source.
    families : tuple of tuple of str
        The families holding the master's and the slave's edges, in the source's order.
    """

    master: tuple[int, ...]
    slave: tuple[int, ...]
    sense: int
    distance: float
    families: tuple[tuple[str, ...], tuple[str, ...]]


def _refuse(where: str, reason: str) -> InputArtifactError:
    return InputArtifactError(f"{where}: {reason}. Nothing was written.", kind=KIND)


def _ek(a: int, b: int) -> tuple[int, int]:
    return (a, b) if a < b else (b, a)


# ------------------------------------------------------------------ rotation


def rotate(points: Points, periodic: Periodic, sense: int) -> Points:
    """Return the points rotated by ``sense`` times 360/copies degrees about the periodic axis."""
    axis = numpy.asarray(periodic.axis, dtype=float)
    k = axis / numpy.linalg.norm(axis)
    angle = sense * 2.0 * math.pi / periodic.copies
    cross = numpy.array([[0.0, -k[2], k[1]], [k[2], 0.0, -k[0]], [-k[1], k[0], 0.0]])
    matrix = numpy.eye(3) + math.sin(angle) * cross + (1.0 - math.cos(angle)) * cross @ cross
    origin = numpy.asarray(periodic.origin, dtype=float)
    return (numpy.asarray(points, dtype=float).reshape(-1, 3) - origin) @ matrix.T + origin


def nearest_match(moved: Points, target: Points) -> tuple[float, NDArray[numpy.int64]] | None:
    """Return the largest nearest distance and the matched indices, or None without a bijection."""
    if len(moved) != len(target) or not len(target):
        return None
    dist, index = NearestIndex(target).query(moved)
    if len(numpy.unique(index)) != len(index):
        return None
    return float(dist.max()), index


def level_distance(master: Points, slave: Points, periodic: Periodic, sense: int) -> float:
    """Return the largest distance of a rotated master node from its slave node (FR-427 R1).

    Infinite when the two sides hold different numbers of nodes or the
    nearest slave node of two master nodes is one node.
    """
    found = nearest_match(rotate(master, periodic, sense), numpy.asarray(slave, dtype=float))
    return math.inf if found is None else found[0]


# --------------------------------------------------------------- the chains


def _corner(verts: Points, loop: list[int], k: int, closed: bool) -> bool:
    """Return whether the boundary turns at loop[k] by more than the ridge angle."""
    n = len(loop)
    if not closed and k in (0, n - 1):
        return True
    before = verts[loop[k]] - verts[loop[k - 1]]
    after = verts[loop[(k + 1) % n]] - verts[loop[k]]
    norms = float(numpy.linalg.norm(before) * numpy.linalg.norm(after))
    return bool(numpy.dot(before, after) < math.cos(math.radians(RIDGE_DEGREES)) * norms)


def boundary_chains(verts: Points, faces: Faces) -> list[list[int]]:
    """Return the open boundary as chains of vertices, split at its corners."""
    edges = set(boundary_edges(faces))
    degree = Counter(v for e in edges for v in e)
    chains: list[list[int]] = []
    for loop in boundary_loops(faces):
        closed = len(loop) > 2 and _ek(loop[-1], loop[0]) in edges
        breaks = [
            k for k in range(len(loop)) if degree[loop[k]] != 2 or _corner(verts, loop, k, closed)
        ]
        if not breaks:
            chains.append(loop)
            continue
        first = breaks[0]
        seq = loop[first:] + loop[:first] + ([loop[first]] if closed else [])
        marks = sorted({(k - first) % len(loop) for k in breaks} | {len(seq) - 1})
        chains += [seq[a : b + 1] for a, b in pairwise(marks)]
    return [c for c in chains if len(c) >= 2]


def _min_edge(verts: Points, chain: Sequence[int]) -> float:
    return float(numpy.linalg.norm(numpy.diff(verts[list(chain)], axis=0), axis=1).min())


def _pair(verts: Points, a: list[int], b: list[int], periodic: Periodic) -> CutPair | None:
    """Return the two chains as a candidate pair, or None when no rotation maps one on the other.

    A candidate is a pair whose nodes correspond one to one unambiguously
    (every distance below half the shortest edge), matched or not.
    """
    best: tuple[float, int] | None = None
    for sense in (1, -1):
        found = nearest_match(rotate(verts[a], periodic, sense), verts[b])
        if found is not None and (best is None or found[0] < best[0]):
            best = (found[0], sense)
    if best is None or best[0] >= 0.5 * min(_min_edge(verts, a), _min_edge(verts, b)):
        return None
    return CutPair(tuple(a), tuple(b), best[1], best[0], ((), ()))


def _owners(families: Mapping[str, Faces]) -> dict[tuple[int, int], str]:
    """Return the family holding each edge (the first in family order for an interface)."""
    owner: dict[tuple[int, int], str] = {}
    for name, faces in families.items():
        for f in faces:
            for a, b in zip(f, f[1:] + f[:1], strict=True):
                owner.setdefault(_ek(a, b), name)
    return owner


def _side_families(
    chain: Sequence[int], owner: Mapping[tuple[int, int], str], order: Sequence[str]
) -> tuple[str, ...]:
    held = {owner[_ek(a, b)] for a, b in pairwise(chain) if _ek(a, b) in owner}
    return tuple(n for n in order if n in held)


def _swap(p: CutPair) -> CutPair:
    return CutPair(p.slave, p.master, -p.sense, p.distance, ((), ()))


def _oriented(pairs: list[CutPair], families: Mapping[str, Faces]) -> list[CutPair]:
    """Return the pairs with the master first in family order and one sense for every pair."""
    owner, order = _owners(families), list(families)

    def rank(chain: Sequence[int]) -> tuple[int, int]:
        held = _side_families(chain, owner, order)
        return (order.index(held[0]) if held else len(order), min(chain))

    first = [p if rank(p.master) <= rank(p.slave) else _swap(p) for p in pairs]
    first.sort(key=lambda p: rank(p.master))
    sense = first[0].sense
    out = []
    for p in first:
        q = p if p.sense == sense else _swap(p)
        sides = (_side_families(q.master, owner, order), _side_families(q.slave, owner, order))
        out.append(CutPair(q.master, q.slave, sense, q.distance, sides))
    return out


def find_cuts(
    verts: Points,
    families: Mapping[str, Faces],
    periodic: Periodic | None,
    *,
    size: float,
    where: str,
) -> list[CutPair]:
    """Return the source's cut boundaries as chain pairs, refusing what does not match (R2).

    Parameters
    ----------
    verts : ndarray
        The source's vertices.
    families : mapping of str to list of list of int
        The source's faces per family, in the source's order.
    periodic : Periodic or None
        The ``[periodic]`` table; None returns no pair (R3).
    size : float
        The source's size.
    where : str
        The object a refusal names.

    Returns
    -------
    list of CutPair
        Every chain pair, the master first in family order.

    Raises
    ------
    InputArtifactError
        No pair is found, or the largest distance exceeds PERIODIC_SOURCE_FRACTION of the size.
    """
    if periodic is None:
        return []
    faces = [f for fs in families.values() for f in fs]
    chains = boundary_chains(verts, faces)
    found = [_pair(verts, a, b, periodic) for a, b in combinations(chains, 2)]
    pairs = [p for p in found if p is not None]
    if not pairs:
        raise _refuse(
            where,
            f"no two open boundary chains map onto each other by the rotation of "
            f"360/{periodic.copies} degrees about axis {list(periodic.axis)} through origin "
            f"{list(periodic.origin)}; the mesh has no cut boundaries, or axis, origin or "
            f"copies is not the sector's",
        )
    worst = max(p.distance for p in pairs)
    if worst > PERIODIC_SOURCE_FRACTION * size:
        raise _refuse(
            where,
            f"the cut boundaries do not map onto each other: the largest distance is {worst:.6g} "
            f"({worst / size:.3g} of the size), above {PERIODIC_SOURCE_FRACTION:g} of the size",
        )
    return _oriented(pairs, families)


# ---------------------------------------------------------- rebuilding a cut


@dataclass(frozen=True)
class _Plan:
    """What rebuilding the cuts reads: the source, the rotation and each family's method."""

    verts: Points
    periodic: Periodic
    remeshed: Mapping[str, float]
    grids: Mapping[str, tuple[Points, Faces]]
    owner: Mapping[tuple[int, int], str]
    size: float


def _near(points: Points, a: Points, b: Points) -> NDArray[numpy.bool_]:
    """Return which points lie on the segments a-b (within ON_CURVE_FRACTION of a segment)."""
    if not len(a) or not len(points):
        return numpy.zeros(len(points), dtype=bool)
    dist, k = segment_distances(points, a, b)
    length = numpy.linalg.norm(numpy.asarray(b) - numpy.asarray(a), axis=1)
    return numpy.asarray(dist < ON_CURVE_FRACTION * length[k])


def _edges_of(plan: _Plan, chain: Sequence[int], name: str) -> list[tuple[int, int]]:
    return [(a, b) for a, b in pairwise(chain) if plan.owner.get(_ek(a, b)) == name]


def _ends(verts: Points, edges: Sequence[tuple[int, int]]) -> tuple[Points, Points]:
    return verts[[a for a, _ in edges]].reshape(-1, 3), verts[[b for _, b in edges]].reshape(-1, 3)


def _fixed_nodes(plan: _Plan, chain: Sequence[int], side: Sequence[str]) -> Points:
    """Return the level nodes of a side none of whose families is remeshed (grid or source)."""
    parts = [numpy.zeros((0, 3))]
    for name in side:
        edges = _edges_of(plan, chain, name)
        if name in plan.grids:
            pts, faces = plan.grids[name]
            ids = sorted({v for e in boundary_edges(faces) for v in e})
            parts.append(pts[ids][_near(pts[ids], *_ends(plan.verts, edges))])
        else:
            parts.append(plan.verts[sorted({v for e in edges for v in e})])
    points = numpy.vstack(parts)
    keys = numpy.round(points / max(DUPLICATE_FRACTION * plan.size, 1e-300)).astype(numpy.int64)
    _, first = numpy.unique(keys, axis=0, return_index=True)
    return points[numpy.sort(first)]


def resample(points: Points, factor: float) -> Points:
    """Return a chain resampled along its own nodes to ``round(factor m)`` of its m intervals.

    The new nodes are placed at equal steps of the node index and linearly
    between source nodes, so the clustering is kept, both ends are exact and
    every node lies on the source chain.
    """
    pts = numpy.asarray(points, dtype=float).reshape(-1, 3)
    m = len(pts) - 1
    count = max(1, round(factor * m))
    t = numpy.arange(count + 1) * m / count
    i = numpy.minimum(numpy.floor(t).astype(numpy.int64), m - 1)
    frac = (t - i)[:, None]
    return (1.0 - frac) * pts[i] + frac * pts[i + 1]


def _targets(
    plan: _Plan, cut: CutPair, sides: tuple[tuple[str, ...], tuple[str, ...]]
) -> tuple[Points | None, Points | None]:
    """Return the positions the master and the slave are rebuilt on (None: the side is kept)."""
    master_moves, slave_moves = (any(n in plan.remeshed for n in s) for s in sides)
    if not master_moves and not slave_moves:
        return None, None
    if not master_moves:
        ref = _fixed_nodes(plan, cut.master, sides[0])
        return None, rotate(ref, plan.periodic, cut.sense)
    if not slave_moves:
        ref = _fixed_nodes(plan, cut.slave, sides[1])
        return rotate(ref, plan.periodic, -cut.sense), None
    factor = max(plan.remeshed[n] for n in sides[0] if n in plan.remeshed)
    ref = resample(plan.verts[list(cut.master)], factor)
    return ref, rotate(ref, plan.periodic, cut.sense)


def _size(verts: Points, families: Mapping[str, Faces]) -> float:
    used = sorted({v for fs in families.values() for f in fs for v in f})
    pts = verts[used].reshape(-1, 3)
    return float(numpy.linalg.norm(pts.max(axis=0) - pts.min(axis=0))) if used else 0.0


def plan_conform(
    verts: Points,
    families: Mapping[str, Faces],
    cuts: Sequence[CutPair],
    periodic: Periodic | None,
    *,
    remeshed: Mapping[str, float],
    grids: Mapping[str, tuple[Points, Faces]],
) -> dict[str, Conform]:
    """Return, per remeshed family, the cut curves to rebuild and the positions to rebuild them on.

    Parameters
    ----------
    verts : ndarray
        The source's vertices.
    families : mapping of str to list of list of int
        The faces per family as they are remeshed (a band already cut out).
    cuts : sequence of CutPair
        The source's cut pairs (:func:`find_cuts`).
    periodic : Periodic or None
        The rotation; None plans nothing.
    remeshed : mapping of str to float
        Each remeshed family with the factor its cut is resampled by.
    grids : mapping of str to (ndarray, list of list of int)
        Each grid family's level points and faces.

    Returns
    -------
    dict
        Per family, ``(source vertices of its cut, new positions)`` entries in
        the form :meth:`Remesher.conform` takes.
    """
    if periodic is None or not cuts:
        return {}
    owner = _owners(families)
    plan = _Plan(verts, periodic, remeshed, grids, owner, _size(verts, families))
    order = list(families)
    out: dict[str, Conform] = defaultdict(list)
    for cut in cuts:
        chains = (cut.master, cut.slave)
        sides = (_side_families(cut.master, owner, order), _side_families(cut.slave, owner, order))
        for chain, side, pts in zip(chains, sides, _targets(plan, cut, sides), strict=True):
            if pts is None:
                continue
            for name in [n for n in side if n in remeshed]:
                edges = _edges_of(plan, chain, name)
                on = pts[_near(pts, *_ends(verts, edges))]
                out[name].append(({v for e in edges for v in e}, on))
    return dict(out)


# ------------------------------------------------------------ the level's cuts


def _match_pair(
    level: Points, outline: NDArray[numpy.int64], cut: CutPair, plan: _Plan
) -> dict[str, Any]:
    """Place the slave's level nodes on the rotated master's and return the pair's report."""
    sides = []
    for chain in (cut.master, cut.slave):
        a, b = plan.verts[list(chain[:-1])], plan.verts[list(chain[1:])]
        sides.append(outline[_near(level[outline], a, b)])
    master, slave = sides
    rotated = rotate(level[master], plan.periodic, cut.sense)
    found = nearest_match(rotated, level[slave])
    if found is not None and found[0] <= PERIODIC_SOURCE_FRACTION * plan.size:
        level[slave[found[1]]] = rotated
    after = level_distance(level[master], level[slave], plan.periodic, cut.sense)
    return {
        "master": list(cut.families[0]),
        "slave": list(cut.families[1]),
        "sense_degrees": cut.sense * 360.0 / plan.periodic.copies,
        "source_nodes": len(cut.master),
        "level_nodes": [len(master), len(slave)],
        "source_distance": cut.distance,
        "level_distance": after,
    }


def match_level(
    level: Points,
    faces: Mapping[str, Faces],
    cuts: Sequence[CutPair],
    periodic: Periodic | None,
    *,
    source: Points,
    size: float,
    where: str,
) -> tuple[Points, dict[str, Any] | None]:
    """Make the level's cut boundaries match node for node and report them (FR-427 R1).

    Each slave node within PERIODIC_SOURCE_FRACTION of the size of its
    rotated master node is placed on it; a pair that then differs in its
    node count or by more than PERIODIC_LEVEL_FRACTION of the size is
    refused before anything is written.

    Parameters
    ----------
    level : ndarray
        The level's welded vertices.
    faces : mapping of str to list of list of int
        The level's faces per family.
    cuts : sequence of CutPair
        The source's cut pairs.
    periodic : Periodic or None
        The rotation; None returns the level unchanged and no report.
    source : ndarray
        The source's vertices.
    size : float
        The source's size.
    where : str
        The object a refusal names.

    Returns
    -------
    tuple
        The level's vertices (the slave nodes placed) and the ``periodic``
        entry of ``refine.json``.

    Raises
    ------
    InputArtifactError
        The level's cut boundaries do not match within PERIODIC_LEVEL_FRACTION.
    """
    if periodic is None or not cuts:
        return level, None
    out = numpy.array(level, dtype=float, copy=True)
    flat = [f for fs in faces.values() for f in fs]
    outline = numpy.array(sorted({v for e in boundary_edges(flat) for v in e}), dtype=numpy.int64)
    plan = _Plan(source, periodic, {}, {}, {}, size)
    rows = [_match_pair(out, outline, cut, plan) for cut in cuts]
    worst = max(r["level_distance"] for r in rows)
    if not worst <= PERIODIC_LEVEL_FRACTION * size:
        bad = next(r for r in rows if r["level_distance"] == worst)
        raise _refuse(
            where,
            f"the level's cut boundaries do not match node for node: the master chain of "
            f"{', '.join(bad['master'])} holds {bad['level_nodes'][0]} nodes and its image "
            f"{bad['level_nodes'][1]}, the largest distance is {worst:.6g}",
        )
    return out, {
        "axis": list(periodic.axis),
        "origin": list(periodic.origin),
        "copies": periodic.copies,
        "level_distance": worst,
        "pairs": rows,
    }
