"""Rebuild the named hub around each blade root as rings of quads (PFS-2192), on an OBJ.

A hub that is quad-dominant has no complete rings of quads around a blade root, which repitch
needs. Per blade, ``rings`` rows of quads with as many nodes as the root loop are marched
outward on the hub, the hub faces they reach plus one layer leave, and the annulus between the
outer ring and that hole is remeshed quad-dominant by the remesh ``refine`` uses, with both loops
frozen and every node on the source hub. Blade nodes and root nodes never move; every other
family, the hub's open boundaries (a sector's seams) and the hub faces away from the roots stay
to the bit. The kept hub faces keep their order and the new faces take the place of the first
face taken, rings from the root outward, because the solver's results depend on face order.
"""

from __future__ import annotations

import json
import math
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

import pyflightstream._textio as _textio
from pyflightstream._digest import file_sha256
from pyflightstream._errors import InputValueError, NotApplicableWarning, warn
from pyflightstream.workspace._hub_rings_grid import (
    Region,
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
from pyflightstream.workspace._refine._obj import ObjMesh, mesh_unit, obj_text, read_obj
from pyflightstream.workspace._refine._remesh import (
    FROZEN,
    PASSES,
    SMOOTH_PASSES,
    Patch,
    Remesher,
    element_report,
)
from pyflightstream.workspace._repitch import HubSurface, _nearest
from pyflightstream.workspace._repitch_grid import edges, incidence, quality, rings, root_loop
from pyflightstream.workspace._repitch_io import (
    Rewrite,
    attachments,
    morphing_table,
    one_block_per_family,
    read_back,
    sidecar_reads_back,
)

__all__ = ["hub_rings_mesh"]

Edge = tuple[int, int]

#: The widths tried, each this fraction of the one before, when the rings do not fit.
_SHRINK, _TRIES = 0.9, 44
#: The remesh passes tried in turn on an annulus, while a pass count turns a cell over.
_PASSES = (PASSES, 4, 2, 1, 0)


def _need(ok: bool, message: str) -> None:
    if not ok:
        raise InputValueError(f"hub_rings: {message}. No file was written.")


def _names(cfg: dict[str, Any], key: str, mesh: ObjMesh) -> list[str]:
    names = cfg.get(key, [])
    _need(
        isinstance(names, list) and bool(names) and all(isinstance(n, str) for n in names),
        f"hub_rings.{key} must name one or more families",
    )
    _need(len(set(names)) == len(names), f"hub_rings.{key} repeats a family")
    absent = sorted(set(names) - mesh.families.keys())
    _need(not absent, f"hub_rings.{key} names absent families {absent}")
    return list(names)


def read_config(data: dict[str, Any], mesh: ObjMesh) -> dict[str, Any]:
    """Return the ``[hub_rings]`` table of a morphing file, checked against a mesh."""
    cfg = morphing_table(data, "hub_rings", ("blades", "hub"))
    _need(isinstance(cfg, dict), "the morphing file needs a [hub_rings] table")
    for key in sorted(set(cfg) - {"blades", "hub", "rings", "width"}):
        warn(f"hub_rings.{key} does not apply and is skipped", NotApplicableWarning)
    count = cfg.get("rings")
    _need(
        isinstance(count, int) and not isinstance(count, bool) and count >= 1,
        f"hub_rings.rings must be a whole number of rings, 1 or more, not {count!r}",
    )
    width = cfg.get("width")
    _need(
        width is None or (isinstance(width, (int, float)) and math.isfinite(width) and width > 0.0),
        f"hub_rings.width must be a positive length in the mesh's unit, not {width!r}",
    )
    blades, hubs = _names(cfg, "blades", mesh), _names(cfg, "hub", mesh)
    _need(not set(blades) & set(hubs), "hub_rings.blades and hub must be disjoint")
    return {"blades": blades, "hub": hubs, "rings": count, "width": width}


@dataclass
class _Blade:
    """One blade's rings: the root loop, the rows, the faces taken and the hole's boundary."""

    name: str
    family: str
    loop: list[int]
    rows: np.ndarray
    taken: set[int]
    hole: list[int]
    width: float
    area: Region
    tris: list[tuple[int, int, int]]
    route: str


def _family(mesh: ObjMesh, hubs: list[str], loop: list[int], blade: str) -> str:
    """Return the one hub family the faces along a root loop belong to."""
    root = set(edges(loop))
    found = {n for n in hubs for f in mesh.families[n] if root & set(edges(f))}
    _need(
        len(found) == 1,
        f"blade {blade!r}: the hub faces along its root belong to {sorted(found)}, not one family",
    )
    return found.pop()


def _forbidden(mesh: ObjMesh, family: str, blade: str, gone: set[int]) -> set[int]:
    """Return the hub faces never taken: on an open boundary, another family or another hole."""
    owners = incidence([f for fs in mesh.families.values() for f in fs])
    banned = {v for e, own in owners.items() if len(own) == 1 for v in e}
    for name, faces in mesh.families.items():
        if name not in (family, blade):
            banned.update(v for f in faces for v in f)
    faces = mesh.families[family]
    return {i for i, f in enumerate(faces) if banned & set(f)} | gone


def _default_width(mesh: ObjMesh, family: str, loop: list[int], count: int) -> float:
    """Return ``rings`` times the median length of the hub edges leaving the root loop."""
    on = set(loop)
    lengths = [
        float(np.linalg.norm(mesh.verts[a] - mesh.verts[b]))
        for a, b in incidence(mesh.families[family])
        if (a in on) != (b in on)
    ]
    _need(bool(lengths), f"no hub edge of {family!r} leaves the root loop")
    return count * float(np.median(lengths))


def _reached(faces: list[list[int]], area: Region, rows: np.ndarray, loop: list[int]) -> set[int]:
    """Return the hub faces the rings reach: inside the outer ring, holding a ring node, or root."""
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
class _Seed:
    """What one attempt at a blade's rings is asked: the root, its hub family, count and width."""

    name: str
    family: str
    loop: list[int]
    count: int
    width: float


def _attempt(mesh: ObjMesh, seed: _Seed, forbidden: set[int]) -> _Blade | None:
    """Return the blade's rings at the seed's width, or None when they fold or do not fit."""
    faces = mesh.families[seed.family]
    area = region(mesh.verts, faces, seed.loop, seed.width)
    loop = list(seed.loop)
    root = area.chart.coordinates(mesh.verts[loop])
    if signed_area(root) < 0.0:
        loop = [loop[0], *loop[:0:-1]]
        root = root[[0, *range(len(loop) - 1, 0, -1)]]
    rows = march(root, seed.count, seed.width)
    if rows is None:
        return None
    taken = islands_filled(faces, one_layer(faces, _reached(faces, area, rows, loop)))
    hole = None if taken & forbidden else boundary_loop(faces, taken, loop)
    if hole is None:
        return None
    hole_xy = area.chart.coordinates(mesh.verts[hole])
    if signed_area(hole_xy) < 0.0:
        hole, hole_xy = hole[::-1], hole_xy[::-1]
    tris, route = walk_loops(rows[-1], hole_xy), "two-pointer walk"
    if tris is None:
        tris, route = clip_annulus(rows[-1], hole_xy), "ear clipping"
    if tris is None:
        return None
    return _Blade(seed.name, seed.family, loop, rows, taken, hole, seed.width, area, tris, route)


def _plan(mesh: ObjMesh, name: str, cfg: dict[str, Any], gone: dict[str, set[int]]) -> _Blade:
    """Plan one blade's rings, refusing rings that do not fit and naming the width that does."""
    hub_faces = [f for n in cfg["hub"] for f in mesh.families[n]]
    loop = root_loop(mesh.families[name], hub_faces, name)
    family = _family(mesh, cfg["hub"], loop, name)
    forbidden = _forbidden(mesh, family, name, gone.setdefault(family, set()))
    width = cfg["width"] or _default_width(mesh, family, loop, cfg["rings"])
    seed = _Seed(name, family, loop, cfg["rings"], width)
    found = _attempt(mesh, seed, forbidden)
    if found is not None:
        gone[family] |= found.taken
        return found
    fits = None
    for k in range(1, _TRIES + 1):
        seed.width = width * _SHRINK**k
        if _attempt(mesh, seed, forbidden) is not None:
            fits = seed.width
            break
    raise InputValueError(
        f"hub_rings: blade {name!r}: {cfg['rings']} rings of width {width:.6g} do not fit on "
        f"hub {family!r}: they fold, or the faces they need reach an open boundary (a seam), "
        "another family or another blade's rings; "
        + (f"a width of {fits:.6g} fits" if fits else "no width down to a hundredth of it fits")
        + ". No file was written."
    )


def _targets(mesh: ObjMesh, family: str) -> np.ndarray:
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


def _remeshed(mesh: ObjMesh, plan: _Blade, outer: np.ndarray, surface: HubSurface, passes: int):
    """Remesh the annulus with a number of passes; return its points and faces."""
    n, m = len(outer), len(plan.hole)
    hole = mesh.verts[plan.hole]
    loops = [[(k, (k + 1) % n) for k in range(n)], [(n + k, n + (k + 1) % m) for k in range(m)]]
    frozen = {(min(a, b), max(a, b)) for loop in loops for a, b in loop}
    patch = Patch(
        np.vstack([outer, hole]),
        [list(t) for t in plan.tris],
        [plan.family] * len(plan.tris),
        np.r_[_loop_target(outer), _loop_target(hole)],
        dict.fromkeys(frozen, FROZEN),
        set(range(n + m)),
        frozen,
    )
    remesher = Remesher(patch)
    # Every node is projected on the source hub, not on the first triangulation.
    remesher.surface = surface.mesh
    remesher.h_source = _targets(mesh, plan.family)
    remesher.run(passes)
    remesher.repair_degenerate()
    remesher.pair_quads([plan.family])
    for _ in range(SMOOTH_PASSES):
        remesher.smooth_quads([plan.family])
    points, families, _ = remesher.result()
    _need(
        np.array_equal(points[: n + m], patch.verts),
        f"blade {plan.name!r}: the annulus remesh moved a frozen loop node",
    )
    # A node a pass made last (a split) can sit on a chord; every free node ends on the hub.
    if len(points) > n + m:
        points[n + m :] = surface.nearest(points[n + m :])[0]
    return points, families[plan.family]


def _turned_cells(
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


def _annulus(
    mesh: ObjMesh, plan: _Blade, outer: np.ndarray, surface: HubSurface, sense: int
) -> tuple[np.ndarray, list[list[int]], int]:
    """Remesh the annulus quad-dominant; return its points, faces (outer 0.., hole n..), passes.

    The remesh of ``refine`` runs its full passes; when they leave a cell turned against the
    source hub, fewer passes are tried, down to none, where the first triangulation, valid by
    construction, is only paired and smoothed.
    """
    for passes in _PASSES:
        points, faces = _remeshed(mesh, plan, outer, surface, passes)
        if not _turned_cells(points, faces, surface, sense):
            break
    return points, faces, passes


def _forward(faces: list[list[int]], loop: list[int]) -> bool:
    """Return whether the hub face on the root's first edge runs that edge in the loop's order."""
    a, b = loop[0], loop[1]
    face = next(f for f in faces if a in f and b in f)
    return face[(face.index(a) + 1) % len(face)] == b


@dataclass
class _Built:
    """What the rings and annuli add: points per blade, faces per blade in mesh numbering."""

    points: list[np.ndarray]
    faces: dict[str, list[list[int]]]
    quads: dict[str, dict[str, Any]]


def _new_faces(mesh: ObjMesh, plans: list[_Blade], surface: HubSurface) -> _Built:
    """Return the new nodes and the new faces of every blade, numbered after the source nodes."""
    built = _Built([], {}, {})
    start = len(mesh.verts)
    for plan in plans:
        count, n = len(plan.rows) - 1, len(plan.loop)
        lifted = plan.area.chart.lift(plan.rows[1:], mesh.verts[plan.area.ids], plan.area.triangles)
        forward = _forward(mesh.families[plan.family], plan.loop)
        points, annulus, passes = _annulus(mesh, plan, lifted[-1], surface, 1 if forward else -1)
        ids = np.vstack(
            [np.asarray(plan.loop)[None, :], start + np.arange(count * n).reshape(count, n)]
        )
        quads = [
            [ids[k, j], ids[k, (j + 1) % n], ids[k + 1, (j + 1) % n], ids[k + 1, j]]
            if forward
            else [ids[k, j], ids[k + 1, j], ids[k + 1, (j + 1) % n], ids[k, (j + 1) % n]]
            for k in range(count)
            for j in range(n)
        ]
        extra = start + count * n
        local = np.r_[ids[-1], plan.hole, extra + np.arange(len(points) - n - len(plan.hole))]
        ring_faces = [[int(local[v]) for v in (f if forward else f[::-1])] for f in annulus]
        built.faces[plan.name] = [[int(v) for v in q] for q in quads] + ring_faces
        built.points += [lifted.reshape(-1, 3), points[n + len(plan.hole) :]]
        built.quads[plan.name] = {**element_report("quad-dominant", annulus), "passes": passes}
        start = extra + len(points) - n - len(plan.hole)
    return built


@dataclass
class _Result:
    """The rebuilt mesh with what the checks need to compare it with the source."""

    source: ObjMesh
    mesh: ObjMesh
    plans: list[_Blade]
    index: np.ndarray
    added: dict[str, list[list[int]]]
    kept: list[tuple[str, int]]
    annulus: dict[str, dict[str, Any]]


def _assemble(source: ObjMesh, plans: list[_Blade], built: _Built) -> _Result:
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
    return _Result(source, mesh, plans, index, added, kept, built.quads)


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


def _check_rings(r: _Result) -> list[int]:
    """Refuse a blade whose output hub does not hold exactly the rings asked, from its root."""
    found = []
    for plan in r.plans:
        hub = r.mesh.families[plan.family]
        loop = [int(r.index[v]) for v in plan.loop]
        count = len(rings(loop, hub)) - 1
        asked = len(plan.rows) - 1
        _need(
            count == asked,
            f"blade {plan.name!r}: the output holds {count} complete rings, not {asked}",
        )
        found.append(count)
    return found


def _check_cells(r: _Result, surface: HubSurface) -> dict[str, Any]:
    """Refuse a fold or a cell turned against the source hub; report the new cells' quality."""
    new = [f for faces in r.added.values() for f in faces]
    shape = quality(r.mesh.verts, new)
    _need(shape["folded_cells"] == 0, f"{shape['folded_cells']} new hub cell(s) fold")
    centres = np.array([r.mesh.verts[f].mean(axis=0) for f in new])
    _, _, owner = _nearest(surface.mesh, centres)
    for face, tri in zip(new, owner, strict=True):
        p = r.mesh.verts[face]
        normal = np.cross(p, np.roll(p, -1, axis=0)).sum(axis=0)
        _need(
            float(normal @ surface.mesh.face_normals[tri]) > 0.0,
            "a new hub cell is turned against the source hub",
        )
    return shape


def _check_kept(r: _Result) -> None:
    """Refuse a kept node moved or rewritten, or a kept face out of place or order."""
    src, out = r.source, r.mesh
    alive = sorted({v for n, i in r.kept for v in src.families[n][i]})
    mapped = r.index[alive]
    _need(np.array_equal(out.verts[mapped], src.verts[alive]), "a kept node moved")
    if out.vertex_text and src.vertex_text:
        same = all(
            out.vertex_text[j] == src.vertex_text[i] for i, j in zip(alive, mapped, strict=True)
        )
        _need(same, "a kept node is written differently from the source")
    expected = [(n, [int(r.index[v]) for v in src.families[n][i]]) for n, i in r.kept]
    added = {tuple(f) for faces in r.added.values() for f in faces}
    actual = [(n, f) for n, faces in out.families.items() for f in faces if tuple(f) not in added]
    _need(actual == expected, "a kept face differs from the source in place, family or node order")
    _check_order(r)


def _check_order(r: _Result) -> None:
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
        _need(
            place == r.added[plan.name],
            f"blade {plan.name!r}: its new faces are not where its first taken face was",
        )


def _open_edges(mesh: ObjMesh) -> tuple[set[frozenset], int]:
    """Return the edges one face owns, by the places of their ends, and the edges over two faces."""
    owners = incidence([f for fs in mesh.families.values() for f in fs])
    places = {
        frozenset(tuple(mesh.verts[v].tolist()) for v in e)
        for e, own in owners.items()
        if len(own) == 1
    }
    return places, sum(len(own) > 2 for own in owners.values())


def _check_manifold(r: _Result) -> dict[str, int]:
    """Refuse an open edge made or closed, an edge over two faces, or a cell turned in the hub."""
    now, over = _open_edges(r.mesh)
    was, over0 = _open_edges(r.source)
    _need(now == was, f"open edges differ from the source: {len(now ^ was)} edge(s) changed")
    _need(over <= over0, f"{over - over0} edge(s) now have more than two faces")
    for plan in r.plans:
        runs: dict[Edge, int] = {}
        for face in r.mesh.families[plan.family]:
            for a, b in zip(face, [*face[1:], face[0]], strict=True):
                runs[(a, b)] = runs.get((a, b), 0) + 1
        new_edges = {e for f in r.added[plan.name] for e in zip(f, [*f[1:], f[0]], strict=True)}
        _need(
            all(runs.get(e, 0) == 1 for e in new_edges),
            f"blade {plan.name!r}: a new hub cell runs an edge the way its neighbour does",
        )
    return {"open_edges": len(now), "edges_over_two_faces": over}


def _area(verts: np.ndarray, faces: list[list[int]]) -> float:
    return sum(
        0.5 * float(np.linalg.norm(np.cross(verts[f], np.roll(verts[f], -1, axis=0)).sum(axis=0)))
        for f in faces
    )


def verify_rings(r: _Result, surface: HubSurface, hubs: list[str]) -> dict[str, Any]:
    """Run every check of the rebuilt hub before anything is written."""
    checks: dict[str, Any] = {"ring_counts": _check_rings(r)}
    checks["new_cell_quality"] = _check_cells(r, surface)
    _check_kept(r)
    checks["manifold"] = _check_manifold(r)
    added = sorted({v for faces in r.added.values() for f in faces for v in f})
    distance = float(surface.nearest(r.mesh.verts[added])[1].max())
    hub_faces = [f for n in hubs for f in r.source.families[n]]
    allowed = chord_deviation(r.source.verts, hub_faces)
    checks["largest_distance_to_source_hub"] = distance
    checks["source_chord_deviation"] = allowed
    _need(
        distance <= allowed,
        f"a new hub node lies {distance:.6g} from the source hub, beyond the source's own "
        f"chord deviation {allowed:.6g}",
    )
    before = _area(r.source.verts, hub_faces)
    after = _area(r.mesh.verts, [f for n in hubs for f in r.mesh.families[n]])
    checks["hub_area"] = {"source": before, "output": after, "relative_change": after / before - 1}
    return checks


def build_rings(source: ObjMesh, cfg: dict[str, Any]) -> tuple[_Result, HubSurface]:
    """Plan and build every named blade's rings, unchecked; return the result and the hub surface.

    :func:`verify_rings` holds the result to the source before anything is written.
    """
    gone: dict[str, set[int]] = {}
    plans = [_plan(source, name, cfg, gone) for name in cfg["blades"]]
    surface = HubSurface(source.verts, [f for n in cfg["hub"] for f in source.families[n]])
    return _assemble(source, plans, _new_faces(source, plans, surface)), surface


def rings_step(
    source: ObjMesh, cfg: dict[str, Any]
) -> tuple[ObjMesh, dict[str, Any], Rewrite, Any]:
    """Rebuild the hub around every named blade in memory.

    Returns the mesh, the report, the rewrite of the boundaries file and each source node's
    place in the output (NaN for a node removed).

    Every check runs here; nothing is written. The rewrite carries the boundaries file through
    the new node list: a marking on a removed node or edge is refused.
    """
    result, surface = build_rings(source, cfg)
    plans = result.plans
    checks = verify_rings(result, surface, cfg["hub"])
    report = _report(result, cfg, checks)
    removed = {i for i in range(len(source.verts)) if result.index[i] < 0}
    kept_edges = _kept_edges(result)
    rw = Rewrite(
        verb="hub_rings",
        counts=(
            sum(len(f) for f in result.mesh.families.values()),
            [len(f) for f in result.mesh.families.values()],
        ),
        gone=removed,
        dead={
            e
            for plan in plans
            for i in plan.taken
            for e in edges(source.families[plan.family][i])
            if e not in kept_edges
        },
    )
    return result.mesh, report, rw, _new_by_old(source, result.mesh, result.index)


def _kept_edges(r: _Result) -> set[Edge]:
    return {e for n, i in r.kept for e in edges(r.source.families[n][i])}


def _report(r: _Result, cfg: dict[str, Any], checks: dict[str, Any]) -> dict[str, Any]:
    blades = {}
    for plan in r.plans:
        added = r.added[plan.name]
        blades[plan.name] = {
            "hub_family": plan.family,
            "rings": len(plan.rows) - 1,
            "width": plan.width,
            "root_loop_nodes": len(plan.loop),
            "faces_taken": len(plan.taken),
            "faces_added": len(added),
            "hole_boundary_nodes": len(plan.hole),
            "annulus_first_triangulation": plan.route,
            "annulus": r.annulus[plan.name],
        }
    return {
        "rings": cfg["rings"],
        "width_stated": cfg["width"],
        "blades": blades,
        "checks": {"passed": True, **checks},
    }


def _new_by_old(source: ObjMesh, mesh: ObjMesh, index: np.ndarray) -> np.ndarray:
    """Return each source node's place in the output, NaN for a node removed."""
    out = np.full_like(source.verts, np.nan)
    alive = index[: len(source.verts)] >= 0
    out[alive] = mesh.verts[index[: len(source.verts)][alive]]
    return out


def hub_rings_mesh(mesh: str | Path, morphing: str | Path, out: str | Path) -> dict[str, Any]:
    """Rebuild the named hub around each named blade as rings of quads; write after every check.

    Parameters
    ----------
    mesh : str or Path
        Source OBJ, read only. A saved simulation (.fsm) is refused.
    morphing : str or Path
        TOML control file with a ``[hub_rings]`` table: ``rings`` (a whole number), optionally
        ``width`` (the total height of the rings in the mesh's unit), and ``blades`` and ``hub``
        of its own or at the top of the file.
    out : str or Path
        New OBJ. Existing outputs are refused.

    Returns
    -------
    dict
        The per-blade counts and the checks, also written as ``<out>.hub_rings.json``.
    """
    path, control, target = Path(mesh), Path(morphing), Path(out)
    record = Path(str(target) + ".hub_rings.json")
    _need(
        path.suffix.lower() == ".obj",
        f"mesh {path} must be an .obj: the operation works on the OBJ, not on a saved .fsm",
    )
    _need(target.suffix.lower() == ".obj", "--out must be an .obj")
    _need(target.resolve() != path.resolve(), "--out must differ from the source")
    _need(not target.exists() and not record.exists(), "output or report exists; choose new --out")
    source = read_obj(path)
    cfg = read_config(tomllib.loads(control.read_text(encoding="utf-8")), source)
    one_block_per_family(path, "hub_rings")
    built, report, rw, new_by_old = rings_step(source, cfg)
    payload = obj_text(built).encode("utf-8")
    read_back(built, payload, "hub_rings")
    report["checks"]["readback_equal"] = True
    extra = attachments(path, target, source, new_by_old, payload, rewrite=rw)
    sidecar_reads_back(extra, target, "hub_rings")
    for file in extra:
        _need(not file.exists(), f"attachment {file} exists; choose new --out")
    report["mesh_unit"] = mesh_unit(path)
    report["source_sha256"] = file_sha256(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)
    for file, content in extra.items():
        file.write_bytes(content)
    report["output_sha256"] = file_sha256(target)
    report["attachments"] = sorted(p.name for p in extra)
    _textio.write_text(record, json.dumps(report, indent=2) + "\n")
    return report
