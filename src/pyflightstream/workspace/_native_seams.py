"""Name the faces the solver's own tessellation of a source surface leaves degenerate (G13).

Pipeline role: the geometry build audits the mesh the solver makes of a CAD import (the native
route). Its gate G1 refuses a face of zero area and an edge of more than two faces. On a native
mesh some of those are the solver's tessellation of a correct surface along the boundary of
the source: a fan of slivers at a pole, a sliver pair folded along the seam of two source faces
(record ``tests/tier3_licensed/data/g13-native-import.json``). :func:`explain_g1` reads the
source IGES and decides, for each such face or edge, whether every node lies on an edge of a
source face (or two nodes collapse onto a source vertex, a pole fan); one that does is named by the
source faces whose edge it lies on and is explained, and one
with a point off every source edge is not. Distances are exact distances to the CAD curves,
never to sampled chords (R28-006). A caller passes a build only when nothing is left
unexplained, so a zero-area face inside a source face still fails.
"""

from __future__ import annotations

import json
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

#: A point is on a source edge when it is within this fraction of the mesh size (the diagonal of
#: the OBJ's bounding box) of the CAD curve, measured exactly. Why this value: the solver places
#: its seam nodes on the curve to its own geometric precision, several orders below this, so the
#: tolerance only has to absorb that and the OBJ's printed digits; it has to stay well below a
#: panel edge, so that a sliver it excuses lies in a strip of width ``2 * tolerance`` around a
#: source curve and cannot hide a fold across a panel. Its ratio to the panel edges of the
#: licensed native meshes is not measurable offline (the record keeps counts, not meshes) and is
#: owed by a licensed replay. Any off-curve sliver wider than the tolerance fails; the reviewer's
#: disk chord (0.019 m inside a 1 m radius, several tolerances) is refused.
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
    """The edges and vertices of the faces of one source IGES, with the faces that own each.

    Distances are measured to the CAD curve itself (the kernel's closest point on the curve,
    ``edge_project``), never to a polyline of samples: a chord of a curved edge can lie farther
    inside the face than the tolerance, and a defect along it would pass (review finding
    R28-006). The kernel stays open until :meth:`close`.
    """

    def __init__(self, iges: str, tolerance: float) -> None:
        self.kernel = open_kernel(_PURPOSE)
        try:
            read = self.kernel.import_iges(iges)
            index = {face.tag: i for i, face in enumerate(read.faces)}
            self.names = read.names
            tags = sorted({abs(e) for face in read.faces for e in self.kernel.boundary(face)})
            self.edges: list[tuple[int, tuple[int, ...], np.ndarray, np.ndarray]] = []
            ends, self.end_owner = [], []
            for tag in tags:
                owners = tuple(index[f.tag] for f in self.kernel.adjacent(tag) if f.tag in index)
                low, high = (np.asarray(b, float) for b in self.kernel.edge_bbox(tag))
                self.edges.append((tag, owners, low, high))
                ends.append(self.kernel.edge_values(tag, self.kernel.edge_bounds(tag)))
                self.end_owner += [owners, owners]
        except BaseException:
            self.kernel.close()
            raise
        self.tolerance = tolerance
        self.end_tree = cKDTree(np.vstack(ends)) if ends else None

    def close(self) -> None:
        """Close the kernel."""
        self.kernel.close()

    def _named(self, faces: Any) -> list[str]:
        return sorted({f"{self.names[f] or 'unnamed'} [face {f}]" for f in faces})

    def _distance(self, edge: tuple[int, Any, np.ndarray, np.ndarray], points: np.ndarray) -> Any:
        """Return the exact distance of each point to the curve of ``edge``."""
        tag, _owners, low, high = edge
        if np.linalg.norm(high - low) <= 1e-12 * max(1.0, float(np.abs(high).max())):
            # A curve of zero length (a collapsed loop edge) is its one point.
            return np.linalg.norm(points - (low + high) / 2, axis=1)
        try:
            on = self.kernel.edge_project(tag, [tuple(p) for p in points.tolist()])
        except Exception:  # noqa: BLE001 - a curve the kernel cannot project explains nothing
            return np.full(len(points), np.inf)
        return np.linalg.norm(points - on, axis=1)

    def lying_on(self, points: np.ndarray) -> list[str] | None:
        """Name the source faces when the segments follow one source edge, else None.

        Every point of each mesh segment (closed polygon) must lie within the tolerance of one
        and the same source curve; checking only the endpoints admits a diagonal across a source
        face (R28-001). The segments are sampled at spacing ``s = tolerance / 2`` and each sample
        must be within ``tolerance - s / 2`` of the curve: the distance to a curve is 1-Lipschitz
        and every point of a segment is within ``s / 2`` of a sample, so every point of every
        segment is then within ``tolerance`` of the curve. The bound is proved, not sampled.
        """
        spacing = self.tolerance / 2
        if len(points) < 2:
            dense = np.asarray(points, float)
        else:
            dense = np.vstack(
                [
                    _densified(np.asarray([a, b]), spacing)
                    for a, b in zip(points, np.roll(points, -1, axis=0), strict=True)
                ]
            )
        box_low, box_high = dense.min(axis=0), dense.max(axis=0)
        common: list[tuple[int, ...]] = []
        for edge in self.edges:
            _tag, owners, low, high = edge
            # The curve lies in its box, so a point farther than the tolerance from the box is
            # farther from the curve: only a box that reaches every point can explain them.
            if np.any(low - self.tolerance > box_high) or np.any(high + self.tolerance < box_low):
                continue
            if float(self._distance(edge, dense).max()) <= self.tolerance - spacing / 2:
                common.append(owners)
        if not common:
            return None
        return self._named(f for owners in common for f in owners)

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
    try:
        return _judge(mesh, faces, zero, many, source)
    finally:
        source.close()


def _judge(
    mesh: Any, faces: list[list[int]], zero: Any, many: list[Any], source: _SourceEdges
) -> dict[str, Any]:
    sources: dict[str, int] = {}
    explained_faces: list[dict[str, Any]] = []
    identities = [(name, i) for name, group in mesh.families.items() for i in range(len(group))]
    loose: list[list[float]] = []
    for row in np.nonzero(zero)[0]:
        corners = mesh.verts[faces[row]]
        named = source.lying_on(corners) or source.collapsed_at_a_vertex(corners)
        if named is None:
            loose.append([round(float(x), 6) for x in corners.mean(axis=0)])
        else:
            name, index = identities[int(row)]
            explained_faces.append({"family": name, "face": index, "source_faces": named})
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
        "explained_faces": explained_faces,
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
    face_list = json.dumps(seams["explained_faces"], sort_keys=True)
    note = (
        f"native G1: {seams['zero_area']} zero-area faces ({named}) and {seams['nonmanifold']} "
        "edges of more than two faces lie on source edges: the solver's tessellation of the seams; "
        f"excused faces (zero-based by family): {face_list}"
    )
    return True, [], note
