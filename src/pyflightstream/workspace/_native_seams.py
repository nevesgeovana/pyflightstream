"""Name the faces the solver's own tessellation of a source surface leaves degenerate (G13).

Pipeline role: the geometry build audits the mesh the solver makes of a CAD import (the native
route). Its gate G1 refuses a face of zero area and an edge of more than two faces. On a native
mesh some of those are the solver's tessellation of a correct surface along the boundary of
the source: a fan of slivers at a pole, a sliver pair folded along the seam of two source faces
(record ``tests/tier3_licensed/data/g13-native-import.json``). :func:`explain_g1` reads the
source IGES and decides, for each such face or edge, whether every node lies on an edge of a
source face (or two nodes collapse onto a source vertex, a pole fan); one that does is named by the
source faces whose edge it lies on and is explained, and one
with a node off every source edge is not. A caller passes a build only when nothing is left
unexplained, so a zero-area face inside a source face still fails.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from scipy.spatial import cKDTree

from pyflightstream.workspace._gmsh import open_kernel
from pyflightstream.workspace._gmsh_worker import run_isolated
from pyflightstream.workspace._refine._geometry import (
    ZERO_AREA_FRACTION,
    below_family_area,
    edge_faces,
)
from pyflightstream.workspace._refine._obj import read_obj

__all__ = ["explain_g1"]

#: A node is on a source edge when it is within this fraction of the mesh size of the edge.
EDGE_FRACTION = 1e-3

_PURPOSE = "naming the native tessellation seams"


def explain_g1(obj: str | Path, iges: str | Path) -> dict[str, Any]:
    """Return what G1 refuses on a solver mesh and how much of it lies on source edges.

    Parameters
    ----------
    obj : str or Path
        The OBJ the solver exported, in metres.
    iges : str or Path
        The IGES the solver imported.

    Returns
    -------
    dict
        ``zero_area`` and ``nonmanifold`` (the counts G1 judges), ``explained_zero_area`` and
        ``explained_nonmanifold`` (those with every node on a source edge), ``unexplained`` (the
        sum of what is left) and ``sources``, the faces named by the source faces whose edge they
        lie on.
    """
    return run_isolated(
        f"{__name__}:_explain",
        {"obj": str(obj), "iges": str(iges)},
        _explain,
    )


def _areas(verts: np.ndarray, faces: list[list[int]]) -> np.ndarray:
    """Return the area of each polygon (Newell's sum)."""
    out = np.zeros(len(faces))
    for row, face in enumerate(faces):
        p = verts[face]
        out[row] = 0.5 * np.linalg.norm(np.cross(p, np.roll(p, -1, axis=0)).sum(axis=0))
    return out


def _densified(samples: np.ndarray, spacing: float) -> np.ndarray:
    """Return the polyline ``samples`` with a point at least every ``spacing``."""
    pieces = [samples[:1]]
    for a, b in zip(samples[:-1], samples[1:], strict=True):
        count = max(1, int(np.ceil(np.linalg.norm(b - a) / spacing)))
        pieces.append(a + (b - a) * (np.arange(1, count + 1) / count)[:, None])
    return np.vstack(pieces)


class _SourceEdges:
    """The edges and vertices of the faces of one source IGES, with the faces that own each."""

    def __init__(self, iges: str, tolerance: float) -> None:
        kernel = open_kernel(_PURPOSE)
        try:
            self.topology = kernel.inspect_file(iges, None)
        finally:
            kernel.close()
        self.tolerance = tolerance
        points, self.edge_index = [], []
        for edge, (samples, _owners) in enumerate(self.topology.edges):
            dense = _densified(np.asarray(samples, float), tolerance / 2)
            points.append(dense)
            self.edge_index.extend([edge] * len(dense))
        self.tree = cKDTree(np.vstack(points)) if points else None
        ends = [np.asarray(s, float)[[0, -1]] for s, _ in self.topology.edges]
        self.end_owner = [owners for _, owners in self.topology.edges for _ in range(2)]
        self.end_tree = cKDTree(np.vstack(ends)) if ends else None

    def _named(self, faces: Any) -> list[str]:
        names = self.topology.names
        return sorted({names[f] or f"face {f}" for f in faces})

    def lying_on(self, points: np.ndarray) -> list[str] | None:
        """Name the source faces when the segments follow one source edge, else None."""
        if self.tree is None:
            return None
        # Every point of each mesh segment must follow one and the same source edge.
        # Checking only the endpoints admits a diagonal across a source face.
        segments = (
            [points]
            if len(points) < 2
            else [
                _densified(np.asarray([a, b]), self.tolerance / 2)
                for a, b in zip(points, np.roll(points, -1, axis=0), strict=True)
            ]
        )
        common: set[int] | None = None
        for point in np.vstack(segments):
            near = self.tree.query_ball_point(point, self.tolerance)
            edges = {self.edge_index[i] for i in near}
            common = edges if common is None else common & edges
            if not common:
                return None
        assert common is not None
        return self._named(f for edge in common for f in self.topology.edges[edge][1])

    def collapsed_at_a_vertex(self, points: np.ndarray) -> list[str] | None:
        """Name the source faces of a vertex that two of the points collapse onto."""
        if self.end_tree is None:
            return None
        distance, index = self.end_tree.query(points)
        near = [int(i) for d, i in zip(distance, index, strict=True) if d <= self.tolerance]
        for vertex in set(near):
            if near.count(vertex) >= 2:
                return self._named(self.end_owner[vertex])
        return None


def _duplicate_faces(faces: list[list[int]]) -> int:
    """Count repeated polygon loops, independent of starting point and orientation."""
    seen: set[tuple[int, ...]] = set()
    duplicates = 0
    for face in faces:
        loop = tuple(face)
        reverse = loop[::-1]
        key = min(
            sequence[i:] + sequence[:i] for sequence in (loop, reverse) for i in range(len(loop))
        )
        duplicates += key in seen
        seen.add(key)
    return duplicates


def _explain(obj: str, iges: str) -> dict[str, Any]:
    mesh = read_obj(obj)
    faces = [face for group in mesh.families.values() for face in group]
    family = np.repeat(np.arange(len(mesh.families)), [len(g) for g in mesh.families.values()])
    area = _areas(mesh.verts, faces)
    zero = (area < ZERO_AREA_FRACTION * mesh.size**2) | below_family_area(area, family)
    many = [edge for edge, owners in edge_faces(faces).items() if len(owners) > 2]
    source = _SourceEdges(iges, EDGE_FRACTION * mesh.size)
    sources: dict[str, int] = {}
    loose: list[list[float]] = []
    for row in np.nonzero(zero)[0]:
        corners = mesh.verts[faces[row]]
        named = source.lying_on(corners) or source.collapsed_at_a_vertex(corners)
        if named is None:
            loose.append([round(float(x), 6) for x in corners.mean(axis=0)])
        else:
            key = " / ".join(named)
            sources[key] = sources.get(key, 0) + 1
    explained_many = sum(source.lying_on(mesh.verts[list(edge)]) is not None for edge in many)
    duplicates = _duplicate_faces(faces)
    left = len(loose) + len(many) - explained_many + duplicates
    return {
        "zero_area": int(zero.sum()),
        "explained_zero_area": int(zero.sum()) - len(loose),
        "nonmanifold": len(many),
        "explained_nonmanifold": int(explained_many),
        "unexplained": left,
        "duplicate_faces": duplicates,
        "sources": sources,
        "off_edge_centroids": loose[:8],
        "tolerance_m": source.tolerance,
    }


def native_verdict(audit: Any, obj: str | Path, iges: str | Path) -> tuple[bool, list[str], str]:
    """Return the verdict of the audit of a native mesh, its failures and a note.

    The audit passes here when G1 is its one failure, G1 refuses only zero-area faces and edges
    of more than two faces (no two nodes at one position), and :func:`explain_g1` finds every one
    of them on an edge of a source face. Any other failure, or one face off every source edge,
    leaves the audit as it was.
    """
    failed = [f"{item.name} on {item.family}" for item in audit.failures]
    mesh = read_obj(obj)
    duplicates = _duplicate_faces([face for group in mesh.families.values() for face in group])
    if duplicates:
        return False, [*failed, "G1 duplicate faces"], f"native G1: {duplicates} duplicate faces"
    if audit.passed or [item.name for item in audit.failures] != ["G1"]:
        return audit.passed, failed, ""
    if audit.failures[0].values.get("node_pairs_at_one_position"):
        return False, failed, ""
    seams = explain_g1(obj, iges)
    if seams["unexplained"]:
        return (
            False,
            failed,
            f"native G1: {seams['unexplained']} unexplained of {seams['zero_area']} zero-area "
            f"faces and {seams['nonmanifold']} edges of more than two faces",
        )
    named = ", ".join(f"{n} on the edges of {k}" for k, n in sorted(seams["sources"].items()))
    note = (
        f"native G1: {seams['zero_area']} zero-area faces ({named}) and {seams['nonmanifold']} "
        "edges of more than two faces lie on source edges: the solver's tessellation of the seams"
    )
    return True, [], note
