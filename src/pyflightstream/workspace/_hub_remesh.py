"""Remesh a hub band between two frozen loops, shared by hub-rings and repitch (PFS-2192, PFS-2196).

Both verbs take a hole of hub faces out around a blade root and fill the annulus between an inner
loop (the outer ring of ``hub-rings``, the turned root of the repitch remesh route) and the hole's
boundary: first triangulated in a chart of the hub, then remeshed quad-dominant by the remesh
``refine`` uses, both loops frozen and every free node projected on the source hub. The kept faces
keep their place and order, and each blade's new faces take the place of its first face taken,
because the solver's results depend on face order. The checks of the result live here too, so
both verbs hold their output to the source in one way: broken invariants (a kept node, face or
open edge changed, an edge over two faces, a frozen loop node moved) refuse; the quality of the
new cells is measured and returned for the verb to warn.
"""

from __future__ import annotations

import copy
import math
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

import numpy as np

from pyflightstream._errors import InputValueError, PyflightstreamWarning, warn
from pyflightstream.workspace._hub_rings_grid import (
    Region,
    _best_ear,
    boundary_loop,
    clip_annulus,
    inside,
    islands_filled,
    march,
    one_layer,
    region,
    signed_area,
    walk_loops,
)
from pyflightstream.workspace._refine._obj import ObjMesh
from pyflightstream.workspace._refine._remesh import (
    FROZEN,
    PASSES,
    SMOOTH_PASSES,
    Patch,
    Remesher,
    element_report,
)
from pyflightstream.workspace._repitch import HubSurface, RingChart, _nearest
from pyflightstream.workspace._repitch_grid import edges, incidence, quality, root_loop

Edge = tuple[int, int]
Triangles = list[tuple[int, int, int]]

#: The widths tried, each this fraction of the one before, when a band does not fit.
SHRINK, TRIES = 0.9, 44
#: The remesh passes tried in turn on an annulus, while a pass count turns a cell over.
PASSES_TRIED = (PASSES, 4, 2, 1, 0)


def need(ok: bool, message: str, verb: str) -> None:
    """Refuse with the verb's name when a condition does not hold."""
    if not ok:
        raise InputValueError(f"{verb}: {message}. No file was written.")


class Plan(Protocol):
    """What the remesh of one blade's band reads: the blade, the hub family, the hole."""

    name: str
    family: str
    taken: set[int]
    hole: list[int]
    tris: Triangles


def hub_family(mesh: ObjMesh, hubs: list[str], loop: list[int], blade: str, verb: str) -> str:
    """Return the one hub family the faces along a root loop belong to."""
    root = set(edges(loop))
    found = {n for n in hubs for f in mesh.families[n] if root & set(edges(f))}
    need(
        len(found) == 1,
        f"blade {blade!r}: the hub faces along its root belong to {sorted(found)}, not one family",
        verb,
    )
    return found.pop()


def forbidden(mesh: ObjMesh, family: str, blade: str, gone: set[int]) -> set[int]:
    """Return the hub faces never taken: on an open boundary, another family or another hole."""
    owners = incidence([f for fs in mesh.families.values() for f in fs])
    banned = {v for e, own in owners.items() if len(own) == 1 for v in e}
    for name, faces in mesh.families.items():
        if name not in (family, blade):
            banned.update(v for f in faces for v in f)
    faces = mesh.families[family]
    return {i for i, f in enumerate(faces) if banned & set(f)} | gone


def root_edge_median(mesh: ObjMesh, family: str, loop: list[int], verb: str) -> float:
    """Return the median length of the hub edges that leave a root loop (its local cell size)."""
    on = set(loop)
    lengths = [
        float(np.linalg.norm(mesh.verts[a] - mesh.verts[b]))
        for a, b in incidence(mesh.families[family])
        if (a in on) != (b in on)
    ]
    need(bool(lengths), f"no hub edge of {family!r} leaves the root loop", verb)
    return float(np.median(lengths))


def reached(faces: list[list[int]], area: Region, rows: np.ndarray, loop: list[int]) -> set[int]:
    """Return the hub faces a march reaches: inside its outer row, holding a row node, or root."""
    local = {int(v): k for k, v in enumerate(area.ids)}
    points = rows[1:].reshape(-1, 2)
    root = set(edges(loop))
    found = {i for i, f in enumerate(faces) if root & set(edges(f))}
    for i, face in enumerate(faces):
        if any(v not in local for v in face):
            continue
        xy = area.xy[[local[v] for v in face]]
        if inside(xy, rows[-1]).any() or inside(points, xy).any():
            found.add(i)
    return found


@dataclass
class Hole:
    """The hub faces a band takes, the hole's boundary loop and the annulus's first triangles."""

    taken: set[int]
    hole: list[int]
    tris: Triangles
    route: str


def cut(
    verts: np.ndarray,
    faces: list[list[int]],
    area: Region,
    reach: tuple[np.ndarray, list[int]],
    inner: np.ndarray,
    *,
    banned: set[int],
) -> Hole | None:
    """Take the faces a march reaches plus one layer; triangulate from ``inner`` to the hole.

    ``reach`` holds the marched chart rows and the root loop they start from; ``inner`` is the
    annulus's inner loop in the chart, counterclockwise. Returns None when the hole would take a
    banned face, has no single boundary, or neither first triangulation closes.
    """
    found = hole_of(verts, faces, area, reach, banned=banned)
    if found is None:
        return None
    return join(inner, found[2], found[:2])


def hole_of(
    verts: np.ndarray,
    faces: list[list[int]],
    area: Region,
    reach: tuple[np.ndarray, list[int]],
    *,
    banned: set[int],
) -> tuple[set[int], list[int], np.ndarray] | None:
    """Return the faces a march reaches plus one layer, the hole's loop and its chart points.

    The loop runs counterclockwise in the chart. None when the hole would take a banned face or
    has no single boundary.
    """
    rows, loop = reach
    taken = islands_filled(faces, one_layer(faces, reached(faces, area, rows, loop)))
    hole = None if taken & banned else boundary_loop(faces, taken, loop)
    if hole is None:
        return None
    hole_xy = area.chart.coordinates(verts[hole])
    if signed_area(hole_xy) < 0.0:
        hole, hole_xy = hole[::-1], hole_xy[::-1]
    return taken, hole, hole_xy


def join(inner: np.ndarray, hole_xy: np.ndarray, found: tuple[set[int], list[int]]) -> Hole | None:
    """Triangulate from ``inner`` to the hole's loop: by the two-pointer walk, else by ears."""
    tris, route = walk_loops(inner, hole_xy), "two-pointer walk"
    if tris is None:
        tris, route = clip_annulus(inner, hole_xy), "ear clipping"
    if tris is None:
        return None
    return Hole(found[0], found[1], tris, route)


def targets(mesh: ObjMesh, family: str) -> np.ndarray:
    """Return, per node, the mean length of the hub edges at it (0 off the hub)."""
    total = np.zeros(len(mesh.verts))
    count = np.zeros(len(mesh.verts))
    for a, b in incidence(mesh.families[family]):
        length = float(np.linalg.norm(mesh.verts[a] - mesh.verts[b]))
        total[[a, b]] += length
        count[[a, b]] += 1
    return np.divide(total, count, out=np.zeros_like(total), where=count > 0)


def _loop_target(points: np.ndarray) -> np.ndarray:
    side = np.linalg.norm(np.roll(points, -1, axis=0) - points, axis=1)
    return 0.5 * (side + np.roll(side, 1))


def _remesher(
    mesh: ObjMesh, plan: Plan, inner: np.ndarray, surface: HubSurface
) -> tuple[Remesher, Patch]:
    """Return the remesher of an annulus, both loops frozen, and the patch it starts from."""
    n, m = len(inner), len(plan.hole)
    hole = mesh.verts[plan.hole]
    loops = [[(k, (k + 1) % n) for k in range(n)], [(n + k, n + (k + 1) % m) for k in range(m)]]
    frozen = {(min(a, b), max(a, b)) for loop in loops for a, b in loop}
    patch = Patch(
        np.vstack([inner, hole]),
        [list(t) for t in plan.tris],
        [plan.family] * len(plan.tris),
        np.r_[_loop_target(inner), _loop_target(hole)],
        dict.fromkeys(frozen, FROZEN),
        set(range(n + m)),
        frozen,
    )
    remesher = Remesher(patch)
    # Every node is projected on the source hub, not on the first triangulation.
    remesher.surface = surface.mesh
    remesher.h_source = targets(mesh, plan.family)
    return remesher, patch


def _finished(
    remesher: Remesher, plan: Plan, patch: Patch, surface: HubSurface, verb: str
) -> tuple[np.ndarray, list[list[int]]]:
    """Repair, pair and smooth a remesher after its passes; return its points and faces."""
    remesher.repair_degenerate()
    remesher.pair_quads([plan.family])
    for _ in range(SMOOTH_PASSES):
        remesher.smooth_quads([plan.family])
    points, families, _ = remesher.result()
    frozen = len(patch.verts)
    need(
        np.array_equal(points[:frozen], patch.verts),
        f"blade {plan.name!r}: the annulus remesh moved a frozen loop node",
        verb,
    )
    # A node a pass made last (a split) can sit on a chord; every free node ends on the hub.
    if len(points) > frozen:
        points[frozen:] = surface.nearest(points[frozen:])[0]
    return points, families[plan.family]


def remeshed(
    mesh: ObjMesh, plan: Plan, inner: np.ndarray, surface: HubSurface, passes: int, *, verb: str
) -> tuple[np.ndarray, list[list[int]]]:
    """Remesh the annulus with a number of passes; return its points and faces.

    The points are the inner loop (0..n), the hole's loop (n..n+m) and the free nodes after.
    """
    remesher, patch = _remesher(mesh, plan, inner, surface)
    remesher.run(passes)
    return _finished(remesher, plan, patch, surface, verb)


def remesh_series(
    mesh: ObjMesh, plan: Plan, inner: np.ndarray, surface: HubSurface, verb: str
) -> dict[int, tuple[np.ndarray, list[list[int]]]]:
    """Return :func:`remeshed` at every pass count of :data:`PASSES_TRIED`, the passes shared.

    A pass of the remesher does not depend on how many follow, so the passes run once, from
    the fewest up, and each count is finished on a copy; the result at each count is the one
    :func:`remeshed` gives. The copy shares only the source hub, which nothing changes.
    """
    remesher, patch = _remesher(mesh, plan, inner, surface)
    done, found = 0, {}
    for passes in sorted(PASSES_TRIED):
        remesher.run(passes - done)
        done = passes
        twin = copy.deepcopy(remesher, {id(surface.mesh): surface.mesh})
        found[passes] = _finished(twin, plan, patch, surface, verb)
    return found


def turned_cells(
    points: np.ndarray, faces: list[list[int]], surface: HubSurface, sense: int
) -> int:
    """Count the cells whose normal, in the written sense, opposes the nearest source face's."""
    centres = np.array([points[f].mean(axis=0) for f in faces])
    _, _, owner = _nearest(surface.mesh, centres)
    count = 0
    for face, tri in zip(faces, owner, strict=True):
        p = points[face]
        normal = np.cross(p, np.roll(p, -1, axis=0)).sum(axis=0)
        count += sense * float(normal @ surface.mesh.face_normals[tri]) <= 0.0
    return count


Counter = Callable[[np.ndarray, list[list[int]], HubSurface, int], int]


def annulus(
    mesh: ObjMesh,
    plan: Plan,
    inner: np.ndarray,
    surface: HubSurface,
    sense: int,
    *,
    turned: Counter = turned_cells,
    verb: str,
) -> tuple[np.ndarray, list[list[int]], int]:
    """Remesh the annulus quad-dominant; return its points, faces (inner 0.., hole n..), passes.

    The remesh of ``refine`` runs its full passes; when they leave a cell turned against the
    source hub, fewer passes are tried, down to none, where the first triangulation, valid by
    construction, is only paired and smoothed.
    """
    for passes in PASSES_TRIED:
        points, faces = remeshed(mesh, plan, inner, surface, passes, verb=verb)
        if not turned(points, faces, surface, sense):
            break
    return points, faces, passes


def forward(faces: list[list[int]], loop: list[int]) -> bool:
    """Return whether the hub face on the root's first edge runs that edge in the loop's order."""
    a, b = loop[0], loop[1]
    face = next(f for f in faces if a in f and b in f)
    return face[(face.index(a) + 1) % len(face)] == b


def numbered(
    faces: list[list[int]], loops: tuple[Any, list[int]], first: int, free: int, ahead: bool
) -> list[list[int]]:
    """Return annulus faces in mesh numbering: inner loop, hole loop, then ``free`` new nodes.

    The new nodes are numbered from ``first``; ``ahead`` is :func:`forward` of the root, and a
    root run the other way writes every face reversed.
    """
    inner, hole = loops
    local = np.r_[inner, hole, first + np.arange(free)]
    return [[int(local[v]) for v in (f if ahead else f[::-1])] for f in faces]


@dataclass
class Built:
    """What the bands add: points per blade, faces per blade in mesh numbering."""

    points: list[np.ndarray]
    faces: dict[str, list[list[int]]]
    quads: dict[str, dict[str, Any]]


@dataclass
class Result:
    """The rebuilt mesh with what the checks need to compare it with the source."""

    source: ObjMesh
    mesh: ObjMesh
    plans: list[Any]
    index: np.ndarray
    added: dict[str, list[list[int]]]
    kept: list[tuple[str, int]]
    annulus: dict[str, dict[str, Any]]


def assemble(source: ObjMesh, plans: list[Any], built: Built) -> Result:
    """Drop the taken faces and the nodes only they used; put each blade's new faces in place."""
    taken = {(p.family, i): p.name for p in plans for i in p.taken}
    used = {
        v
        for name, fs in source.families.items()
        for i, f in enumerate(fs)
        if (name, i) not in taken
        for v in f
    }
    count = len(source.verts)
    # A hole node whose every kept face another blade's hole took (two holes that touch) is
    # still a corner of both annuli: it stays, or their faces would name a removed node.
    used |= {v for faces in built.faces.values() for f in faces for v in f if v < count}
    alive = np.array([i in used for i in range(count)])
    every = np.vstack([source.verts, *built.points]) if built.points else source.verts
    keep = np.r_[alive, np.ones(len(every) - count, dtype=bool)]
    index = np.where(keep, np.cumsum(keep) - 1, -1)
    families: dict[str, list[list[int]]] = {}
    kept: list[tuple[str, int]] = []
    for name, faces in source.families.items():
        rows, placed = [], set()
        for i, face in enumerate(faces):
            owner = taken.get((name, i))
            if owner is None:
                rows.append([int(index[v]) for v in face])
                kept.append((name, i))
            elif owner not in placed:
                placed.add(owner)
                rows += [[int(index[v]) for v in f] for f in built.faces[owner]]
        families[name] = rows
    text = source.vertex_text
    new_text = (
        ([t for t, a in zip(text, alive, strict=True) if a] + [None] * int(keep[count:].sum()))
        if len(text) == count
        else []
    )
    mesh = ObjMesh(every[keep], families, list(source.header), source.family_tag, new_text)
    added = {
        name: [[int(index[v]) for v in f] for f in faces] for name, faces in built.faces.items()
    }
    return Result(source, mesh, plans, index, added, kept, built.quads)


def chord_deviation(verts: np.ndarray, faces: list[list[int]]) -> float:
    """Return the largest sagitta of the source hub's facets, length times turn over eight.

    Two faces sharing an edge of length L whose normals differ by an angle t stand for a
    surface curved about that edge; the arc through it leaves the chord by about L t / 8.
    """
    normals = []
    for face in faces:
        p = verts[face]
        n = np.cross(p, np.roll(p, -1, axis=0)).sum(axis=0)
        normals.append(n / max(float(np.linalg.norm(n)), 1e-300))
    worst = 0.0
    for (a, b), own in incidence(faces).items():
        if len(own) == 2:
            turn = math.acos(min(1.0, max(-1.0, float(normals[own[0]] @ normals[own[1]]))))
            worst = max(worst, float(np.linalg.norm(verts[a] - verts[b])) * turn / 8.0)
    return worst


def cell_findings(r: Result, surface: HubSurface) -> tuple[dict[str, Any], int]:
    """Return the new cells' quality and the count of new cells turned against the source hub."""
    new = [f for faces in r.added.values() for f in faces]
    shape = quality(r.mesh.verts, new)
    centres = np.array([r.mesh.verts[f].mean(axis=0) for f in new])
    _, _, owner = _nearest(surface.mesh, centres)
    count = 0
    for face, tri in zip(new, owner, strict=True):
        p = r.mesh.verts[face]
        normal = np.cross(p, np.roll(p, -1, axis=0)).sum(axis=0)
        count += float(normal @ surface.mesh.face_normals[tri]) <= 0.0
    return shape, count


def cell_warnings(shape: dict[str, Any], count: int) -> list[str]:
    """Return the sentences that state folded and turned new cells with their numbers."""
    found = []
    if shape["folded_cells"]:
        found.append(
            f"{shape['folded_cells']} new hub cell(s) fold; the least scaled Jacobian of the new "
            f"cells is {shape['min_scaled_jacobian']:.6g}"
        )
    if count:
        found.append(f"{count} new hub cell(s) are turned against the source hub")
    return found


def distance_warning(
    r: Result, surface: HubSurface, allowed: float, skip: frozenset[int] = frozenset()
) -> tuple[float, list[str]]:
    """Return the largest distance of a new node to the source hub, and a warning beyond it.

    The nodes of the new faces are measured, but those in ``skip`` (output numbering): the
    turned root of repitch, which follows its blade and whose stand-off is reported apart.
    """
    added = sorted({v for faces in r.added.values() for f in faces for v in f} - skip)
    distance = surface.nearest(r.mesh.verts[added])[1]
    worst = int(np.argmax(distance))
    largest = float(distance[worst])
    if largest <= allowed:
        return largest, []
    return largest, [
        f"new hub node {added[worst]} (zero-based, in the output) lies {largest:.6g} from the "
        f"source hub, beyond the source's own chord deviation {allowed:.6g}"
    ]


def check_kept(r: Result, verb: str) -> None:
    """Refuse a kept node moved or rewritten, or a kept face out of place or order."""
    src, out = r.source, r.mesh
    alive = sorted({v for n, i in r.kept for v in src.families[n][i]})
    mapped = r.index[alive]
    need(np.array_equal(out.verts[mapped], src.verts[alive]), "a kept node moved", verb)
    if out.vertex_text and src.vertex_text:
        same = all(
            out.vertex_text[j] == src.vertex_text[i] for i, j in zip(alive, mapped, strict=True)
        )
        need(same, "a kept node is written differently from the source", verb)
    expected = [(n, [int(r.index[v]) for v in src.families[n][i]]) for n, i in r.kept]
    added = {tuple(f) for faces in r.added.values() for f in faces}
    actual = [(n, f) for n, faces in out.families.items() for f in faces if tuple(f) not in added]
    need(
        actual == expected,
        "a kept face differs from the source in place, family or node order",
        verb,
    )
    check_order(r, verb)


def check_order(r: Result, verb: str) -> None:
    """Refuse new faces anywhere but at the place of their blade's first taken face."""
    first = {p.name: min(p.taken) for p in r.plans}
    for plan in r.plans:
        before = sum(1 for n, i in r.kept if n == plan.family and i < first[plan.name])
        before += sum(
            len(r.added[p.name])
            for p in r.plans
            if p.family == plan.family and first[p.name] < first[plan.name]
        )
        place = r.mesh.families[plan.family][before : before + len(r.added[plan.name])]
        need(
            place == r.added[plan.name],
            f"blade {plan.name!r}: its new faces are not where its first taken face was",
            verb,
        )


def open_edges(mesh: ObjMesh) -> tuple[set[frozenset], int]:
    """Return the edges one face owns, by the places of their ends, and the edges over two faces."""
    owners = incidence([f for fs in mesh.families.values() for f in fs])
    places = {
        frozenset(tuple(mesh.verts[v].tolist()) for v in e)
        for e, own in owners.items()
        if len(own) == 1
    }
    return places, sum(len(own) > 2 for own in owners.values())


def edge_counts(r: Result, verb: str) -> dict[str, int]:
    """Return the open edges and edges over two faces; refuse a change of them or a turned cell."""
    now, over = open_edges(r.mesh)
    was, over0 = open_edges(r.source)
    need(now == was, f"open edges differ from the source: {len(now ^ was)} edge(s) changed", verb)
    need(over <= over0, f"{over - over0} edge(s) now have more than two faces", verb)
    for plan in r.plans:
        runs: dict[Edge, int] = {}
        for face in r.mesh.families[plan.family]:
            for a, b in zip(face, [*face[1:], face[0]], strict=True):
                runs[(a, b)] = runs.get((a, b), 0) + 1
        new_edges = {e for f in r.added[plan.name] for e in zip(f, [*f[1:], f[0]], strict=True)}
        need(
            all(runs.get(e, 0) == 1 for e in new_edges),
            f"blade {plan.name!r}: a new hub cell runs an edge the way its neighbour does",
            verb,
        )
    return {"open_edges": len(now), "edges_over_two_faces": over}


def area(verts: np.ndarray, faces: list[list[int]]) -> float:
    """Return the total area of polygons, each by its vector area."""
    return sum(
        0.5 * float(np.linalg.norm(np.cross(verts[f], np.roll(verts[f], -1, axis=0)).sum(axis=0)))
        for f in faces
    )


def kept_edges(r: Result) -> set[Edge]:
    """Return the source edges of the kept faces."""
    return {e for n, i in r.kept for e in edges(r.source.families[n][i])}


def new_by_old(source: ObjMesh, mesh: ObjMesh, index: np.ndarray) -> np.ndarray:
    """Return each source node's place in the output, NaN for a node removed."""
    out = np.full_like(source.verts, np.nan)
    alive = index[: len(source.verts)] >= 0
    out[alive] = mesh.verts[index[: len(source.verts)][alive]]
    return out


# The remesh route of repitch (PFS-2196): one band per blade around its turned root.

#: Source cells across the default band beyond the root's largest move: two, the depth of the two
#: complete quad rings the ring route needs around a root.
BAND_CELLS = 2
#: Wider bands tried beside the first, each one more source cell across, while they fit.
WIDER = 2
_REPITCH = "repitch"


@dataclass
class Root:
    """What a band is cut around: the blade, its hub family, root loop, cell and barred faces."""

    name: str
    family: str
    loop: list[int]
    cell: float
    banned: set[int]
    foot: list[list[int]] = field(default_factory=list)


def footprint(mesh: ObjMesh, hub_faces: list[list[int]], loop: list[int]) -> list[list[int]]:
    """Return triangles closing the hub under a blade's root loop, run as the hub's faces run.

    The loop is triangulated in the plane of its largest spread by clipping, each time, the ear
    with the widest least angle; an empty list when no ear is found.
    """
    chart = RingChart(mesh.verts[loop], None)
    xy = chart.coordinates(mesh.verts[loop])
    ccw = list(range(len(loop)))
    if signed_area(xy) < 0.0:
        ccw.reverse()
    ring = list(ccw)
    tris = []
    while len(ring) > 3:
        k = _best_ear(xy, ring)
        if k is None:
            return []
        tris.append([ring[k - 1], ring[k], ring[(k + 1) % len(ring)]])
        del ring[k]
    tris.append(ring)
    # A counterclockwise ear runs the root's edges as the loop does; the hub face across a root
    # edge runs it the other way when it runs the loop forward.
    ahead = forward(hub_faces, [loop[i] for i in ccw])
    return [[loop[i] for i in (t[::-1] if ahead else t)] for t in tris]


@dataclass
class Band:
    """One blade's band: its root loop (counterclockwise in the chart), the hole and annulus."""

    name: str
    family: str
    loop: list[int]
    taken: set[int]
    hole: list[int]
    tris: Triangles
    route: str
    width: float
    rows: Any = None


def root_move(verts: np.ndarray, moved: np.ndarray, loop: list[int]) -> float:
    """Return the largest move of a root node by the blade's turn."""
    return float(np.linalg.norm(moved[loop] - verts[loop], axis=1).max())


def band_at(mesh: ObjMesh, moved: np.ndarray, root: Root, width: float) -> Band | None:
    """Return the band of hub faces within ``width`` of the old root, or None when it does not fit.

    The band's edge is marched from the old root in steps of at most one source cell, so the
    normals are taken again at least once a cell; the faces it reaches plus one layer leave. The
    annulus runs from the turned root to the hole's boundary. Rows are marched from the turned
    root, one local cell apart, as many as stay a cell inside the hole (the hole reaches past
    the width, one layer of source faces beyond it), and lifted on the hub; they are written as
    quads, as hub-rings writes its rings, so the cells around the root have the source's size,
    and only the gap from the last row to the hole is triangulated and remeshed. When a row
    folds or leaves the hole, or the triangulation does not close, fewer rows are tried, down
    to none. None when the march folds, the turned root turns over in the chart,
    the hole would take a barred face or no triangulation closes.
    """
    faces = mesh.families[root.family]
    zone = region(mesh.verts, faces + root.foot, root.loop, width)
    loop = list(root.loop)
    xy = zone.chart.coordinates(mesh.verts[loop])
    if signed_area(xy) < 0.0:
        loop = [loop[0], *loop[:0:-1]]
        xy = xy[[0, *range(len(loop) - 1, 0, -1)]]
    rows = march(xy, max(1, math.ceil(width / root.cell)), width)
    inner = zone.chart.coordinates(moved[loop])
    if rows is None or signed_area(inner) <= 0.0:
        return None
    found = hole_of(mesh.verts, faces, zone, (rows, loop), banned=root.banned)
    if found is None:
        return None
    taken, hole, hole_xy = found
    gap = _gap(inner, hole_xy)
    for count in range(max(0, math.floor(gap / root.cell) - 1), -1, -1):
        ring = march(inner, count, count * root.cell) if count else inner[None]
        if ring is None or (count and not inside(ring[1:].reshape(-1, 2), hole_xy).all()):
            continue
        joined = join(ring[-1], hole_xy, (taken, hole))
        if joined is None:
            continue
        lifted = zone.chart.lift(ring[1:], mesh.verts[zone.ids], zone.triangles) if count else None
        return Band(
            root.name, root.family, loop, taken, hole, joined.tris, joined.route, width, lifted
        )
    return None


def _gap(inner: np.ndarray, loop: np.ndarray) -> float:
    """Return the least distance in the chart from the inner loop's nodes to a closed loop."""
    a, b = loop, np.roll(loop, -1, axis=0)
    ab = b - a
    along = np.einsum("pk,sk->ps", inner, ab) - (a * ab).sum(axis=1)[None, :]
    t = np.clip(along / np.maximum((ab * ab).sum(axis=1), 1e-300)[None, :], 0.0, 1.0)
    near = a[None, :, :] + t[:, :, None] * ab[None, :, :]
    return float(np.linalg.norm(near - inner[:, None, :], axis=2).min())


def bands_tried(
    mesh: ObjMesh, moved: np.ndarray, root: Root, stated: float | None
) -> tuple[list[Band], dict[str, Any]]:
    """Return the bands to remesh around one root and how their width was found.

    The first width is the stated ``band_width``, else the root's largest move plus
    :data:`BAND_CELLS` local cells (the median length of the hub edges leaving the root). When its
    band does not fit (it would take a face on an open boundary, another family or another
    blade's band), the width shrinks by :data:`SHRINK` until one fits, and that is warned.
    Otherwise up to :data:`WIDER` bands, each one local cell wider, join while they fit.
    """
    shift = root_move(mesh.verts, moved, root.loop)
    width = stated if stated is not None else shift + BAND_CELLS * root.cell
    info: dict[str, Any] = {
        "rule": "stated" if stated is not None else "root move plus two local cells",
        "asked": width,
        "root_largest_move": shift,
        "local_cell_size": root.cell,
        "shrunk_from": None,
    }
    first = band_at(mesh, moved, root, width)
    if first is not None:
        bands = [first]
        for k in range(1, WIDER + 1):
            wider = band_at(mesh, moved, root, width + k * root.cell)
            if wider is None:
                break
            bands.append(wider)
        return bands, info
    for k in range(1, TRIES + 1):
        first = band_at(mesh, moved, root, width * SHRINK**k)
        if first is not None:
            break
    need(
        first is not None,
        f"blade {root.name!r}: no hub band down to a hundredth of the width {width:.6g} fits "
        f"on hub {root.family!r} without an open boundary (a seam), another family or another "
        "blade's band; state [repitch] band_width, or hub_method = 'rings' with [hub_rings]",
        _REPITCH,
    )
    assert first is not None
    warn(
        f"repitch: blade {root.name!r}: the hub band of width {width:.6g} reaches an open "
        f"boundary (a seam), another family or another blade's band; it is shrunk to "
        f"{first.width:.6g}",
        PyflightstreamWarning,
    )
    info["shrunk_from"] = width
    return [first], info


@dataclass
class Candidate:
    """One remesh of one band: its pass count, points, faces, turned cells and shape."""

    band: Band
    passes: int
    points: np.ndarray
    faces: list[list[int]]
    ahead: bool
    turned: int
    shape: dict[str, Any]


def _inner(moved: np.ndarray, band: Band) -> np.ndarray:
    """Return the annulus's inner loop: the last held row, or the turned root without rows."""
    return moved[band.loop] if band.rows is None else band.rows[-1]


def best_candidate(
    mesh: ObjMesh, moved: np.ndarray, bands: list[Band], surface: HubSurface
) -> tuple[Candidate, list[dict[str, Any]]]:
    """Remesh every band at every pass count of the fallback; return the best and the table.

    The best has the fewest cells turned against the source hub (none, when one has none) and,
    among those, the highest least scaled Jacobian.
    """
    tried = []
    for band in bands:
        ahead = forward(mesh.families[band.family], band.loop)
        series = remesh_series(mesh, band, _inner(moved, band), surface, _REPITCH)
        for passes in PASSES_TRIED:
            points, faces = series[passes]
            turned = turned_cells(points, faces, surface, 1 if ahead else -1)
            shape = quality(points, faces)
            tried.append(Candidate(band, passes, points, faces, ahead, turned, shape))
    best = max(tried, key=lambda c: (-c.turned, c.shape["min_scaled_jacobian"]))
    table = [
        {
            "band_width": c.band.width,
            "passes": c.passes,
            "turned_cells": c.turned,
            "min_scaled_jacobian": c.shape["min_scaled_jacobian"],
            "max_aspect": c.shape["max_aspect"],
            "quad_share": element_report("quad-dominant", c.faces)["quad_share"],
        }
        for c in tried
    ]
    return best, table


def band_numbers(verts: np.ndarray, faces: list[list[int]]) -> dict[str, Any]:
    """Return a band's quality, its quad share and its mean edge length."""
    sides = [np.linalg.norm(np.roll(verts[f], -1, axis=0) - verts[f], axis=1) for f in faces]
    return {
        **quality(verts, faces),
        "quad_share": element_report("quad-dominant", faces)["quad_share"],
        "mean_edge": float(np.mean(np.concatenate(sides))),
    }


def _blade_numbers(
    mesh: ObjMesh, best: Candidate, info: dict[str, Any], table: list[dict[str, Any]]
) -> dict[str, Any]:
    """Return what the record says of one blade's band; the output band is filled in later."""
    band = best.band
    return {
        "hub_family": band.family,
        "band_width": band.width,
        "band_width_rule": info["rule"],
        "band_width_asked": info["asked"],
        "shrunk_from": info["shrunk_from"],
        "local_cell_size": info["local_cell_size"],
        "root_largest_move": info["root_largest_move"],
        "candidate_widths": sorted({c["band_width"] for c in table}),
        "root_loop_nodes": len(band.loop),
        "held_rows": 0 if band.rows is None else len(band.rows),
        "faces_taken": len(band.taken),
        "hole_boundary_nodes": len(band.hole),
        "first_triangulation": band.route,
        "passes": best.passes,
        "turned_cells": best.turned,
        "source_band": band_numbers(
            mesh.verts, [mesh.families[band.family][i] for i in band.taken]
        ),
        "candidates": table,
    }


def _rows_and_annulus(best: Candidate, start: int) -> tuple[list[list[int]], list[np.ndarray], int]:
    """Return a band's faces in mesh numbering from ``start``, its new points and their count.

    The held rows are written as quads from the root outward, as hub-rings writes its rings,
    then the remeshed annulus from the last row to the hole.
    """
    band = best.band
    n, m = len(band.loop), len(band.hole)
    count = 0 if band.rows is None else len(band.rows)
    ids = np.vstack(
        [np.asarray(band.loop)[None, :], start + np.arange(count * n).reshape(count, n)]
    )
    quads = [
        [ids[k, j], ids[k, (j + 1) % n], ids[k + 1, (j + 1) % n], ids[k + 1, j]]
        if best.ahead
        else [ids[k, j], ids[k + 1, j], ids[k + 1, (j + 1) % n], ids[k, (j + 1) % n]]
        for k in range(count)
        for j in range(n)
    ]
    free = len(best.points) - n - m
    ring = numbered(best.faces, (ids[-1], band.hole), start + count * n, free, best.ahead)
    points = ([] if band.rows is None else [band.rows.reshape(-1, 3)]) + [best.points[n + m :]]
    faces = [[int(v) for v in q] for q in quads] + ring
    return faces, points, count * n + free


def remesh_bands(
    source: ObjMesh, turned: ObjMesh, names: tuple[list[str], list[str]], stated: float | None
) -> tuple[Result, HubSurface, dict[str, dict[str, Any]]]:
    """Remesh the hub band around every turned blade root, unchecked; return the result.

    ``turned`` is the source with the blades turned; every band is cut and measured against the
    same source hub, in the order the blades are named, and no band takes a face another took.
    """
    blades, hubs = names
    hub_faces = [f for n in hubs for f in source.families[n]]
    roots = {name: root_loop(source.families[name], hub_faces, name) for name in blades}
    feet = {name: footprint(source, hub_faces, loop) for name, loop in roots.items()}
    # The source hub closed under each blade's old root: a turned root uncovers part of the
    # footprint, and the band's nodes there need a surface to lie on.
    surface = HubSurface(source.verts, hub_faces + [f for foot in feet.values() for f in foot])
    gone: dict[str, set[int]] = {}
    built = Built([], {}, {})
    start, plans, numbers = len(source.verts), [], {}
    for name in blades:
        loop = roots[name]
        family = hub_family(source, hubs, loop, name, _REPITCH)
        banned = forbidden(source, family, name, gone.setdefault(family, set()))
        cell = root_edge_median(source, family, loop, _REPITCH)
        root = Root(name, family, loop, cell, banned, feet[name])
        bands, info = bands_tried(source, turned.verts, root, stated)
        best, table = best_candidate(source, turned.verts, bands, surface)
        gone[family] |= best.band.taken
        faces, points, made = _rows_and_annulus(best, start)
        built.faces[name] = faces
        built.points += points
        built.quads[name] = element_report("quad-dominant", faces)
        start += made
        plans.append(best.band)
        numbers[name] = _blade_numbers(source, best, info, table)
    every = np.vstack([turned.verts, *built.points])
    for name, blade in numbers.items():
        blade["faces_added"] = len(built.faces[name])
        blade["output_band"] = band_numbers(every, built.faces[name])
        blade["size_ratio"] = blade["output_band"]["mean_edge"] / blade["source_band"]["mean_edge"]
    return assemble(turned, plans, built), surface, numbers
