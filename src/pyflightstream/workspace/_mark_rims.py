"""Where the marked edges are on the imported mesh: placement, rims and the edges between.

The mid-points of a trailing-edge file are carried through the import operations like the
OBJ is; on 26.100 the matched edges are also split into rims for the vertex import.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np

from pyflightstream._errors import InputArtifactError
from pyflightstream._lengths import METRES_PER_UNIT
from pyflightstream.cases.mesh import MeshImport
from pyflightstream.workspace.wake_edges import length_scale, mesh_edge_table, nearest_candidates


def _obj_edges(mesh: Path, unit: str) -> list[tuple[str, tuple[float, ...]]]:
    """Read polygon perimeter midpoints, retaining their surface ownership."""
    # Plain floats, not a numpy array per vertex and per edge: the same IEEE operations in the
    # same order, so the mid-points are the bits the array form gave, at a fraction of the cost.
    scale = METRES_PER_UNIT[unit]
    vertices: list[tuple[float, float, float]] = []
    edges: list[tuple[str, tuple[float, ...]]] = []
    family = "Boundary-1"
    for line in mesh.read_text(encoding="utf-8").splitlines():
        words = line.split("#", 1)[0].split()
        if not words:
            continue
        if words[0] == "v":
            vertices.append(
                (float(words[1]) * scale, float(words[2]) * scale, float(words[3]) * scale)
            )
        elif words[0] in {"g", "o"}:
            family = words[1]
        elif words[0] == "f":
            ids = [int(word.split("/")[0]) for word in words[1:]]
            ids = [i - 1 if i > 0 else len(vertices) + i for i in ids]
            for a, b in zip(ids, ids[1:] + ids[:1], strict=True):
                p, q = vertices[a], vertices[b]
                edges.append((family, ((p[0] + q[0]) / 2, (p[1] + q[1]) / 2, (p[2] + q[2]) / 2)))
    return edges


def _move_copies(copies, operation: Any, unit: str):
    """Apply one affine operation to all copies of a point, in metres."""
    if operation.op == "mirror":
        axis = {"YZ": 0, "XZ": 1, "XY": 2}[operation.plane]
        reflected = [xyz.copy() for xyz in copies]
        for xyz in reflected:
            xyz[axis] *= -1
        return copies + reflected
    if operation.op == "scale":
        return [xyz * operation.factors for xyz in copies]
    if operation.op == "translate":
        shift = np.asarray(operation.vector) * METRES_PER_UNIT[unit]
        return [xyz + shift for xyz in copies]
    axis = np.eye(3)[{"X": 0, "Y": 1, "Z": 2}[operation.axis]]
    angle = math.radians(operation.angle_deg)
    return [
        xyz * math.cos(angle)
        + np.cross(axis, xyz) * math.sin(angle)
        + axis * np.dot(axis, xyz) * (1 - math.cos(angle))
        for xyz in copies
    ]


class _ObjEdges:
    """The mid-points of an OBJ's polygon edges with their families, indexed for lookup."""

    def __init__(self, mesh: Path, unit: str) -> None:
        from scipy.spatial import cKDTree

        edges = _obj_edges(mesh, unit)
        self.mesh = mesh
        self.names = sorted({name for name, _ in edges})
        code = {name: number for number, name in enumerate(self.names)}
        self.codes = np.fromiter((code[name] for name, _ in edges), dtype=np.intp, count=len(edges))
        self.tree = cKDTree(np.asarray([xyz for _, xyz in edges], dtype=float).reshape(-1, 3))

    def families(self, points, tolerance: float) -> list[list[str]]:
        """Return, per point, the sorted families with an edge mid-point within ``tolerance``."""
        found = self.tree.query_ball_point(
            np.asarray(points, dtype=float).reshape(-1, 3), tolerance
        )
        return [sorted({self.names[self.codes[i]] for i in hits}) for hits in found]


def _placed_points(points, mesh: Path, spec: MeshImport, tolerance: float):
    """Carry source midpoints through the same ordered family transforms as the OBJ."""
    index = _ObjEdges(mesh, spec.units)
    placed: list[tuple[float, ...]] = []
    for point, families in zip(points, index.families(points, tolerance), strict=True):
        if not families:
            raise InputArtifactError(f"{mesh}: point {point} is not on an OBJ polygon edge")
        for family in families:
            placed.extend(_carry(point, family, spec))
    return tuple(dict.fromkeys(placed))


def _carry(point, family: str, spec: MeshImport) -> list[tuple[float, ...]]:
    """Carry one point of ``family`` through the ordered import operations, copies included."""
    copies = [np.asarray(point, dtype=float)]
    for operation in spec.operations:
        if operation.surface not in ("all", family):
            continue
        if operation.op == "rename":
            assert operation.to is not None
            family = operation.to
        else:
            copies = _move_copies(copies, operation, spec.units)
    return [tuple(float(v) for v in xyz) for xyz in copies]


def _placed_rim(rim, index: _ObjEdges, spec: MeshImport, tolerance: float):
    """Place a rim's edge end vertices like the OBJ is placed."""
    families = index.families(rim.mean(axis=1), tolerance)
    vertices: list[tuple[float, ...]] = []
    for edge, found in zip(rim, families, strict=True):
        if not found:
            raise InputArtifactError(f"{index.mesh}: a rim edge is not on an OBJ polygon edge")
        for family in found:
            for end in edge:
                vertices.extend(_carry(end, family, spec))
    return tuple(dict.fromkeys(vertices))


def _placed_cross(rims, cross, index: _ObjEdges, spec: MeshImport, tolerance: float):
    """Place the cross edges' mid-points by the family of the nearest edge of any of the rims."""
    if not len(cross):
        return ()
    edge_mids = np.vstack([rim.mean(axis=1) for rim in rims])
    families = index.families(edge_mids, tolerance)
    crossed: list[tuple[float, ...]] = []
    for mid in cross:
        nearest = int(np.linalg.norm(edge_mids - mid, axis=1).argmin())
        for family in families[nearest]:
            crossed.extend(_carry(mid, family, spec))
    return tuple(dict.fromkeys(crossed))


def _files_of_a_run(ends: np.ndarray, foreign: np.ndarray) -> list[np.ndarray]:
    """Part a run of rim edges so that no part holds both ends of a ``foreign`` edge.

    Measured on 26.100 (the joint trial of CMP-26100_2026-11-02_mark-26100-vertex), the solver
    marks every edge between the vertices of one file, not only the edges meant. A run with no
    foreign edge is one part, in its own order; otherwise each edge joins the first part
    it can, which keeps the number of files, and so of trailing-edge groups, small.
    """
    if not len(foreign):
        return [ends]
    across: dict[int, set[int]] = {}
    for a, b in foreign.tolist():
        across.setdefault(a, set()).add(b)
        across.setdefault(b, set()).add(a)
    parts: list[tuple[set[int], list[list[int]]]] = []
    for a, b in ends.tolist():
        for held, kept in parts:
            grown = held | {a, b}
            if not (across.get(a, set()) & grown or across.get(b, set()) & grown):
                held.update((a, b))
                kept.append([a, b])
                break
        else:
            parts.append(({a, b}, [[a, b]]))
    return [np.asarray(kept) for _, kept in parts]


def rim_edges(points: Any, mesh: Path, mesh_unit: str) -> tuple[list[np.ndarray], np.ndarray]:
    """Split the matched edges of one set into rims and find the edges joining the rims.

    Each point is the mid-point of a rim edge, in metres, and names the nearest edge of the
    triangulated mesh. A RIM is what one vertex file names: a run of those edges that share
    vertices, so the two sides of a blunt trailing edge are two rims. A CROSS EDGE is a mesh
    edge that is no rim edge and has both ends on rim vertices, which is how a one-cell base
    strip joins its two sides (FR-3470). A run that holds a cross edge of its own, as two sides
    that touch at a vertex or a rim closed in a loop do, is parted into several rims, so that
    no file names both ends of a cross edge.

    Parameters
    ----------
    points : array_like
        The (n, 3) mid-points in metres.
    mesh : Path
        The OBJ the mid-points name edges of.
    mesh_unit : str
        The unit of the OBJ's coordinates.

    Returns
    -------
    tuple
        Per rim an (n, 2, 3) array of edge end coordinates in metres, and the (c, 3)
        mid-points in metres of the cross edges between the rims.
    """
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components

    vertices, edges = mesh_edge_table(mesh)
    vertices = vertices * length_scale(mesh_unit, "METER")
    midpoints = (vertices[edges[:, 0]] + vertices[edges[:, 1]]) / 2.0
    chosen = np.unique(
        nearest_candidates(np.asarray(points, dtype=float).reshape(-1, 3), midpoints)[0]
    )
    ends = edges[chosen]
    size = len(vertices)
    graph = coo_matrix((np.ones(len(ends)), (ends[:, 0], ends[:, 1])), shape=(size, size))
    _, label = connected_components(graph, directed=False)
    rim_of_edge = label[ends[:, 0]]
    on_rim = np.zeros(size, dtype=bool)
    on_rim[ends.ravel()] = True
    own = np.zeros(len(edges), dtype=bool)
    own[chosen] = True
    cross = on_rim[edges[:, 0]] & on_rim[edges[:, 1]] & ~own
    rims: list[np.ndarray] = []
    for run in np.unique(rim_of_edge):
        inside = cross & (label[edges[:, 0]] == run) & (label[edges[:, 1]] == run)
        rims += [
            vertices[part] for part in _files_of_a_run(ends[rim_of_edge == run], edges[inside])
        ]
    return rims, midpoints[cross]


def rim_runs(
    points: Any, mesh: Path, mesh_unit: str, *, base_family: str | None = None
) -> list[np.ndarray]:
    """Part the mid-points of one file by the connected run of mesh edges they name.

    Each run is one rim: the two sides of a blunt trailing edge are two runs, a sharp edge or a
    closed ring one. The runs follow the order of their first point. Unlike :func:`rim_edges`,
    nothing is parted for cross edges: an edge the file names that joins two rims makes them
    one run.

    Inside a run the points keep the file's order, except on the rim of a base region
    (``base_family``), whose points are put in the order of :func:`_outside_face_order`.

    Parameters
    ----------
    points : array_like
        The (n, 3) mid-points in metres.
    mesh : Path
        The OBJ the mid-points name edges of.
    mesh_unit : str
        The unit of the OBJ's coordinates.
    base_family : str, optional
        The OBJ family of the base region whose rim the points are; None keeps the file's
        order.

    Returns
    -------
    list of numpy.ndarray
        Per run an (m, 3) array of the file's mid-points, in metres.
    """
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components

    vertices, edges = mesh_edge_table(mesh)
    vertices = vertices * length_scale(mesh_unit, "METER")
    midpoints = (vertices[edges[:, 0]] + vertices[edges[:, 1]]) / 2.0
    placed = np.asarray(points, dtype=float).reshape(-1, 3)
    ends = edges[nearest_candidates(placed, midpoints)[0]]
    size = len(vertices)
    graph = coo_matrix((np.ones(len(ends)), (ends[:, 0], ends[:, 1])), shape=(size, size))
    _, label = connected_components(graph, directed=False)
    run = label[ends[:, 0]]
    runs = [placed[run == value] for value in dict.fromkeys(run.tolist())]
    if base_family is None:
        return runs
    return [_outside_face_order(part, mesh, mesh_unit, base_family) for part in runs]


def _outside_face_order(points: np.ndarray, mesh: Path, unit: str, family: str) -> np.ndarray:
    """Order a base rim's mid-points by the OBJ face outside the base, the last face first.

    FlightStream 26.127 reads an IMPORT_WAKE_EDGES_FROM_FILE node file in the order written
    and drops some of the edges that meet an edge it has already marked when the new edge's
    face outside the base comes later in the mesh than the marked edge's; it has dropped none
    whose face comes earlier. Measured on 2026-11-06 with licensed probes of a six-blade wheel
    (the 0.56.0 wheel-routes receipt): 742 of 768 rim edges kept in the file's order, 768 of
    768 in this order, and 768 of 768 on 26.125 in the file's order. Writing the last face
    first makes every edge meet only edges of later faces.

    The points are returned in their order where it cannot be stated: the family is not an
    OBJ family, or a point's edge has no face outside it.
    """
    from scipy.spatial import cKDTree

    scale = METRES_PER_UNIT[unit]
    vertices: list[tuple[float, float, float]] = []
    owners: dict[tuple[int, int], list[tuple[int, str]]] = {}
    group = "Boundary-1"
    face = 0
    for line in mesh.read_text(encoding="utf-8").splitlines():
        words = line.split("#", 1)[0].split()
        if not words:
            continue
        if words[0] == "v":
            vertices.append(
                (float(words[1]) * scale, float(words[2]) * scale, float(words[3]) * scale)
            )
        elif words[0] in {"g", "o"}:
            group = words[1]
        elif words[0] == "f":
            ids = [int(word.split("/")[0]) for word in words[1:]]
            ids = [i - 1 if i > 0 else len(vertices) + i for i in ids]
            for a, b in zip(ids, ids[1:] + ids[:1], strict=True):
                owners.setdefault((min(a, b), max(a, b)), []).append((face, group))
            face += 1
    if not any(name == family for held in owners.values() for _, name in held):
        return points
    edges = list(owners)
    xyz = np.asarray(vertices, dtype=float)
    pairs = np.asarray(edges, dtype=np.intp)
    _, nearest = cKDTree((xyz[pairs[:, 0]] + xyz[pairs[:, 1]]) / 2.0).query(points)
    keys = []
    for index in np.atleast_1d(nearest):
        outside = [number for number, name in owners[edges[int(index)]] if name != family]
        if not outside:
            return points
        keys.append(max(outside))
    return points[np.argsort(-np.asarray(keys), kind="stable")]


def saved_cross_edges(sets: Sequence[dict[str, Any]], saved: Path) -> dict[str, int]:
    """Count, per entry label, the saved trailing edges that join two rims of that entry.

    The cross edges were found on the OBJ at plan time (``cross_m`` of an entry, each placed
    by the nearest edge of all its rims). An edge of the saved simulation within the set's
    tolerance of one of them, and
    nearer to it than to any rim edge the entry declares, is a cross edge that the solver
    marked, which the vertex files were written never to name. The tolerance alone would read
    a rim edge as a cross edge where a cell is narrower than twice the tolerance. The saved mesh
    is compared in metres, as the wake-edge verdict does.
    """
    from scipy.spatial import cKDTree

    from pyflightstream._fsm import saved_mesh_coordinate_unit, trailing_edge_midpoints
    from pyflightstream._lengths import scale

    expected = [entry for entry in sets if entry.get("cross_m")]
    if not expected:
        return {}
    unit = saved_mesh_coordinate_unit(saved)
    factor = None if unit is None else scale(unit, "METER")
    if factor is None:
        raise InputArtifactError(f"{saved}: the saved mesh coordinate unit is unknown")
    marked = np.asarray(trailing_edge_midpoints(saved), dtype=float).reshape(-1, 3) * factor
    counts: dict[str, int] = {}
    for entry in expected:
        hit = 0
        if len(marked):
            crossing = np.asarray(entry["cross_m"], dtype=float).reshape(-1, 3)
            declared = np.asarray(entry["points_m"], dtype=float).reshape(-1, 3)
            to_cross, nearest = cKDTree(crossing).query(marked)
            to_rim, _ = cKDTree(declared).query(marked)
            found = (to_cross <= entry["tolerance"]) & (to_cross < to_rim)
            hit = len(np.unique(nearest[found]))
        counts[entry["label"]] = counts.get(entry["label"], 0) + hit
    return counts
