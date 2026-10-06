"""Thresholds and geometric primitives the refinement and the audit share (FR-424 to FR-428).

THE THRESHOLDS are engineering choices that the proof-of-concept levels met;
each is defined here once, and changing one requires a reason in the SRS
revision row that changes it.

THE PRIMITIVES need numpy alone, so a grid family and the audit run without
the geometry extra (FR-424 R10): the nearest-point query bins the points into
cells, not a k-d tree. Face order (FR-424 R7) is written here too, because a grid family
that is not one sweep and a remeshed family both take the source's order the
same way.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Sequence

import numpy
from numpy.typing import NDArray

Points = NDArray[numpy.float64]
Faces = list[list[int]]

#: FR-424 R8: an edge whose dihedral exceeds this many degrees is a curve.
RIDGE_DEGREES = 40.0
#: FR-424 R8: the median ratio of a remeshed edge to its target lies in this band.
EDGE_BAND = (0.8, 1.2)
#: FR-424 R6: a grid node lies within this fraction of the family's size from the source.
GRID_SURFACE_DISTANCE = 1e-3
#: FR-426 R2 G1: two nodes closer than this fraction of the size are one position.
DUPLICATE_FRACTION = 1e-9
#: FR-426 R2 G1: a face whose area is below this fraction of the size squared has zero area.
ZERO_AREA_FRACTION = 1e-12
#: FR-426 R2 G4: a trailing-edge point lies on the edge whose mid-point is this close (of the size).
TE_POINT_FRACTION = 1e-6
#: FR-426 R3: the 95th percentile of the equiangle skewness may grow by this much.
SKEWNESS_MARGIN = 0.05
#: FR-426 R3: the 95th percentile of the quadrilateral warp may reach this many degrees.
WARP_FLOOR_DEGREES = 10.0
#: FR-426 R3: the 95th percentile of the size growth may reach this ratio.
GROWTH_FLOOR = 2.0
#: FR-426 R3: size growth is measured across edges whose dihedral is below this.
GROWTH_DIHEDRAL_DEGREES = 30.0
#: FR-426 R3: the percentile every relative check reads (linear interpolation).
PERCENTILE = 95.0
#: FR-426 R4: the aspect ratio beyond which a face is counted (the solver's stated anisotropy).
ASPECT_LIMIT = 50.0
#: FR-426 R4: the face quality ratio called good below this.
QUALITY_GOOD = 2.0
#: FR-426 R4: the pre-processor's panel quality thresholds, counted and never judged:
#: (figure, measure, counted when above the limit rather than below it, limit).
PANEL_PRACTICE_COUNTS: tuple[tuple[str, str, bool, float], ...] = (
    ("aspect_over_8", "aspect", True, 8.0),
    ("aspect_over_20", "aspect", True, 20.0),
    ("skewness_over_0p5", "skewness", True, 0.5),
    ("warp_over_10_degrees", "warp", True, 10.0),
    ("warp_over_45_degrees", "warp", True, 45.0),
    ("quad_min_angle_under_45_degrees", "quad_min_angle", False, 45.0),
    ("tri_min_angle_under_30_degrees", "tri_min_angle", False, 30.0),
)
#: FR-427 R1: the matched cut nodes of a periodic level lie within this fraction of the size.
PERIODIC_LEVEL_FRACTION = 1e-9
#: FR-427 R2: the source's cut boundaries must match within this fraction of the size.
PERIODIC_SOURCE_FRACTION = 1e-6
#: FR-428 R1: the projected edge lengths match their factor within this fraction.
AXIAL_BAND = 0.15
#: FR-425 R3: the band of an unchanged neighbour is this many face layers deep.
BAND_LAYERS = 2
#: The schema version of refine.json and audit.json (FR-424 R4, FR-426 R1).
SCHEMA_VERSION = 1


def triangles(faces: Faces) -> NDArray[numpy.int64]:
    """Return the faces fanned into triangles from each face's first vertex."""
    out = [[f[0], f[k], f[k + 1]] for f in faces for k in range(1, len(f) - 1)]
    return numpy.array(out, dtype=numpy.int64).reshape(-1, 3)


def normals_and_centroids(verts: Points, faces: Faces) -> tuple[Points, Points]:
    """Return each face's area-weighted normal (twice its area long) and its vertex centroid."""
    normals = numpy.zeros((len(faces), 3))
    centroids = numpy.zeros((len(faces), 3))
    for j, f in enumerate(faces):
        p = verts[f]
        c = p.mean(axis=0)
        centroids[j] = c
        normals[j] = sum(
            (numpy.cross(p[a] - c, p[(a + 1) % len(f)] - c) for a in range(len(f))),
            numpy.zeros(3),
        )
    return normals, centroids


def edge_faces(faces: Faces) -> dict[tuple[int, int], list[int]]:
    """Return each undirected edge (low vertex first) with the faces that use it."""
    out: dict[tuple[int, int], list[int]] = defaultdict(list)
    for k, f in enumerate(faces):
        for a, b in zip(f, f[1:] + f[:1], strict=True):
            out[(min(a, b), max(a, b))].append(k)
    return dict(out)


def boundary_edges(faces: Faces) -> list[tuple[int, int]]:
    """Return the edges used by exactly one face, sorted."""
    return sorted(e for e, fs in edge_faces(faces).items() if len(fs) == 1)


def boundary_loops(faces: Faces) -> list[list[int]]:
    """Return the open boundary as chains of vertices, each closed loop listed once."""
    adjacency: dict[int, list[int]] = defaultdict(list)
    for a, b in boundary_edges(faces):
        adjacency[a].append(b)
        adjacency[b].append(a)
    seen: set[int] = set()
    loops: list[list[int]] = []
    for start in sorted(adjacency):
        if start in seen:
            continue
        loop, prev, cur = [start], -1, start
        seen.add(start)
        while True:
            nxt = next((n for n in adjacency[cur] if n != prev and n not in seen), None)
            if nxt is None:
                break
            loop.append(nxt)
            seen.add(nxt)
            prev, cur = cur, nxt
        loops.append(loop)
    return loops


def dihedral_degrees(verts: Points, faces: Faces) -> dict[tuple[int, int], float]:
    """Return the angle between the normals of the two faces of every interior edge."""
    normals, _ = normals_and_centroids(verts, faces)
    lengths = numpy.linalg.norm(normals, axis=1)
    unit = normals / numpy.maximum(lengths, 1e-300)[:, None]
    out: dict[tuple[int, int], float] = {}
    for edge, fs in edge_faces(faces).items():
        if len(fs) == 2:
            cosine = float(numpy.clip(numpy.dot(unit[fs[0]], unit[fs[1]]), -1.0, 1.0))
            out[edge] = math.degrees(math.acos(cosine))
    return out


#: The direction close pairs are swept along; any fixed direction is exact, and
#: one off every axis and diagonal keeps a structured grid's rows apart.
_SWEEP = numpy.array([0.5390, 0.6830, 0.4930]) / numpy.linalg.norm([0.5390, 0.6830, 0.4930])


def close_pairs(points: Points, tolerance: float) -> NDArray[numpy.int64]:
    """Return every pair of points within ``tolerance`` of each other, lower index first.

    The points are sorted by their coordinate along one fixed direction; two
    points within the tolerance are within it along that direction too, so
    each point is compared only with the run of successors that stays within
    it. The answer is exact, and needs numpy alone.
    """
    pts = numpy.asarray(points, dtype=float).reshape(-1, 3)
    key = pts @ _SWEEP
    order = numpy.argsort(key, kind="stable")
    ranked = key[order]
    found = [numpy.zeros((0, 2), dtype=numpy.int64)]
    for shift in range(1, len(order)):
        near = ranked[shift:] - ranked[:-shift] <= tolerance
        if not near.any():
            break
        a, b = order[:-shift][near], order[shift:][near]
        close = numpy.linalg.norm(pts[a] - pts[b], axis=1) <= tolerance
        found.append(numpy.stack([numpy.minimum(a, b), numpy.maximum(a, b)], axis=1)[close])
    pairs = numpy.concatenate(found)
    return pairs[numpy.lexsort((pairs[:, 1], pairs[:, 0]))]


class NearestIndex:
    """Exact nearest-point queries over a fixed point set (numpy only, no k-d tree).

    The points are binned into cubic cells sized for a surface (about four
    points per cell on a sheet). A query reads the 27 cells around its own; any
    point outside them is at least one cell away, so a nearest point found
    within one cell is the nearest of all. The few queries farther than a cell
    from every point fall back to blocked brute force. The answer is the one a
    k-d tree gives.
    """

    #: The largest number of distances held at once by the brute-force fallback.
    BLOCK_CELLS = 4_000_000

    def __init__(self, points: Points) -> None:
        self.points = numpy.asarray(points, dtype=float).reshape(-1, 3)
        if not len(self.points):
            raise ValueError("a nearest-point index needs at least one point")
        self.low = self.points.min(axis=0)
        diagonal = float(numpy.linalg.norm(self.points.max(axis=0) - self.low))
        self.cell = max(2.0 * diagonal / max(len(self.points) ** 0.5, 1.0), 1e-12)
        keys = numpy.floor((self.points - self.low) / self.cell).astype(numpy.int64)
        self.dims = keys.max(axis=0) + 3  # room for the -1 and +1 neighbours of every cell
        ids = self._ids(keys)
        self.order = numpy.argsort(ids, kind="stable")
        self.sorted_ids = ids[self.order]
        self.unique, self.starts, self.counts = numpy.unique(
            self.sorted_ids, return_index=True, return_counts=True
        )

    def _ids(self, keys: NDArray[numpy.int64]) -> NDArray[numpy.int64]:
        shifted = keys + 1
        return shifted[:, 0] + self.dims[0] * (shifted[:, 1] + self.dims[1] * shifted[:, 2])

    def _brute(self, queries: Points) -> tuple[Points, NDArray[numpy.int64]]:
        """Return the nearest points of far queries: a matrix product, then the best few exactly."""
        dist = numpy.empty(len(queries))
        index = numpy.empty(len(queries), dtype=numpy.int64)
        center = self.points.mean(axis=0)
        shifted = self.points - center
        norms = (shifted**2).sum(axis=1)
        k = min(8, len(self.points))
        block = max(1, self.BLOCK_CELLS // len(self.points))
        for start in range(0, len(queries), block):
            q = queries[start : start + block] - center
            approx = (q**2).sum(axis=1)[:, None] + norms[None, :] - 2.0 * q @ shifted.T
            best = (
                numpy.argsort(approx, axis=1)[:, :k]
                if k == len(self.points)
                else (numpy.argpartition(approx, k - 1, axis=1)[:, :k])
            )
            exact = numpy.linalg.norm(shifted[best] - q[:, None, :], axis=2)
            pick = numpy.argmin(exact, axis=1)
            rows = numpy.arange(len(q))
            dist[start : start + len(q)] = exact[rows, pick]
            index[start : start + len(q)] = best[rows, pick]
        return dist, index

    def query(self, queries: Points) -> tuple[Points, NDArray[numpy.int64]]:
        """Return the distance to, and the index of, the nearest point of each query."""
        queries = numpy.asarray(queries, dtype=float).reshape(-1, 3)
        best_d = numpy.full(len(queries), numpy.inf)
        best_i = numpy.full(len(queries), -1, dtype=numpy.int64)
        keys = numpy.floor((queries - self.low) / self.cell).astype(numpy.int64)
        inside = numpy.all((keys >= -1) & (keys <= self.dims - 3), axis=1)
        for offset in numpy.array(numpy.meshgrid([-1, 0, 1], [-1, 0, 1], [-1, 0, 1])).T.reshape(
            -1, 3
        ):
            neighbour = numpy.clip(keys + offset, -1, self.dims - 2)
            ids = self._ids(neighbour)
            slot = numpy.clip(numpy.searchsorted(self.unique, ids), 0, len(self.unique) - 1)
            hit = inside & (self.unique[slot] == ids)
            count = numpy.where(hit, self.counts[slot], 0)
            start = self.starts[slot]
            for c in range(int(count.max(initial=0))):
                take = count > c
                rows = numpy.nonzero(take)[0]
                candidate = self.order[start[rows] + c]
                d = numpy.linalg.norm(self.points[candidate] - queries[rows], axis=1)
                better = d < best_d[rows]
                best_d[rows[better]] = d[better]
                best_i[rows[better]] = candidate[better]
        unsure = ~(best_d <= self.cell)
        if unsure.any():
            best_d[unsure], best_i[unsure] = self._brute(queries[unsure])
        return best_d, best_i


class Stretch:
    """The affine map that scales along an axis by one factor and across it by another (FR-428).

    A point p goes to ``origin + axial * a + circumferential * r``, where
    ``a`` is the part of ``p - origin`` along the axis and ``r`` the part
    perpendicular to it. Remeshing a surface of revolution isotropically in
    the stretched space, towards target lengths measured in the real space,
    gives edges ``axial`` times shorter along the axis and ``circumferential``
    times shorter around it once mapped back. The map is affine, so a point
    on a stretched triangle maps back onto the same real triangle with the
    same barycentric coordinates, and a straight segment stays one.

    Parameters
    ----------
    axis : sequence of float
        The direction of the axis, not zero; its length and sign do not matter.
    origin : sequence of float
        A point on the axis.
    axial, circumferential : float
        The factors along and around the axis, each above zero.
    """

    def __init__(
        self,
        axis: Sequence[float] | Points,
        origin: Sequence[float] | Points,
        axial: float,
        circumferential: float,
    ) -> None:
        direction = numpy.asarray(axis, dtype=float).reshape(3)
        self.axis = direction / float(numpy.linalg.norm(direction))
        self.origin = numpy.asarray(origin, dtype=float).reshape(3)
        self.factors = (float(axial), float(circumferential))

    def _scaled(self, points: Points, along: float, across: float) -> Points:
        d = numpy.asarray(points, dtype=float) - self.origin
        a = (d @ self.axis)[..., None] * self.axis
        return self.origin + along * a + across * (d - a)

    def forward(self, points: Points) -> Points:
        """Return points of the real space mapped into the stretched space."""
        return self._scaled(points, *self.factors)

    def inverse(self, points: Points) -> Points:
        """Return points of the stretched space mapped back into the real space."""
        return self._scaled(points, 1.0 / self.factors[0], 1.0 / self.factors[1])

    def same_linear_part(self, other: Stretch) -> bool:
        """Return whether two stretches scale the same axis by the same factors.

        The origin only translates the stretched space, and a remesh does not
        depend on where the mesh sits, so two families stretched alike can be
        remeshed together whatever their origins.
        """
        aligned = abs(float(self.axis @ other.axis)) > 1.0 - 1e-12
        return aligned and self.factors == other.factors


def order_like(pts: Points, new_faces: Faces, verts: Points, faces: Faces) -> Faces:
    """Write new faces in the order of the source faces they fall on (FR-424 R7).

    Each new face takes the position of the source face whose centroid is
    nearest its own; faces on one source face keep the order in which that
    face runs through its vertices; each face starts at the vertex nearest the
    source face's first vertex, keeping its orientation.
    """
    _, c_old = normals_and_centroids(verts, faces)
    _, c_new = normals_and_centroids(pts, new_faces)
    _, j = NearestIndex(c_old).query(c_new)
    sub = numpy.zeros(len(new_faces))
    for n, (k, c) in enumerate(zip(j, c_new, strict=True)):
        d = numpy.linalg.norm(verts[faces[k]] - c, axis=1)
        sub[n] = numpy.argmin(d) + 0.001 * d.min()
    out: Faces = []
    for i in numpy.lexsort((sub, j)):
        f, ref = new_faces[i], faces[j[i]]
        s = int(numpy.argmin(numpy.linalg.norm(pts[f] - verts[ref[0]], axis=1)))
        out.append(f[s:] + f[:s])
    return out


def orient_like(pts: Points, new_faces: Faces, verts: Points, faces: Faces) -> Faces:
    """Flip every new face when most of them oppose the nearest source faces.

    One vote over the whole family, because near a thin trailing edge the
    nearest source face of one face can be on the other side.
    """
    n_old, c_old = normals_and_centroids(verts, faces)
    n_new, c_new = normals_and_centroids(pts, new_faces)
    _, j = NearestIndex(c_old).query(c_new)
    agree = numpy.sign((n_new * n_old[j]).sum(axis=1))
    return [f[::-1] for f in new_faces] if agree.sum() < 0 else new_faces
