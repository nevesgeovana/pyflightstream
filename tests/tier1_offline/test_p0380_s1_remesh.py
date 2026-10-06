"""Tier 1, 0.38.0 S1: the remeshed families of a refinement (FR-424 R8, R10, R12; FR-425 R2).

Every fixture is built in tests/p0380_mesh_fixtures.py: a sphere, a curved
plate with a square hole, a cube (its twelve edges are ridges) and a plate cut
into two families along one curve. Each behaviour is measured against the
source, never against the remesher's own bookkeeping, and each measurement is
also run once on an input it must reject, so a check that accepts everything
cannot pass.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import numpy
import pytest
import trimesh

import pyflightstream
from pyflightstream.extras import MissingExtraError
from pyflightstream.workspace._refine._geometry import (
    EDGE_BAND,
    RIDGE_DEGREES,
    NearestIndex,
    boundary_edges,
    boundary_loops,
    dihedral_degrees,
    edge_faces,
    normals_and_centroids,
)
from pyflightstream.workspace._refine._obj import ObjMesh
from pyflightstream.workspace._refine._remesh import (
    TRAILING_EDGE,
    refine_group,
    require_geometry_extra,
)
from tests.p0380_mesh_fixtures import cube, holed_plate, plate_nodes, sphere, two_families

# ---- measurements


def _size(points: numpy.ndarray) -> float:
    return float(numpy.linalg.norm(points.max(axis=0) - points.min(axis=0)))


def _local_lengths(verts: numpy.ndarray, faces: list[list[int]]) -> numpy.ndarray:
    """Return the mean incident edge length at each vertex (the source's local length)."""
    total, count = numpy.zeros(len(verts)), numpy.zeros(len(verts))
    for a, b in edge_faces(faces):
        d = numpy.linalg.norm(verts[a] - verts[b])
        total[[a, b]] += d
        count[[a, b]] += 1
    return total / numpy.maximum(count, 1)


def _edge_ratio_median(mesh: ObjMesh, name: str, points, faces, factor: float) -> float:
    """Return the median, over the new interior edges, of length over source length / factor."""
    used = mesh.family_vertices(name)
    h0 = _local_lengths(mesh.verts, mesh.families[name])[used]
    index = NearestIndex(mesh.verts[used])
    edges = [e for e, fs in edge_faces(faces).items() if len(fs) == 2]
    a = points[[e[0] for e in edges]]
    b = points[[e[1] for e in edges]]
    _, nearest = index.query(0.5 * (a + b))
    return float(numpy.median(numpy.linalg.norm(a - b, axis=1) / (h0[nearest] / factor)))


def _polyline_distance(points: numpy.ndarray, a: numpy.ndarray, b: numpy.ndarray) -> numpy.ndarray:
    """Return the distance from each point to the nearest of the segments a-b."""
    ab = b - a
    out = numpy.empty(len(points))
    for n, p in enumerate(points):
        t = numpy.clip(((p - a) * ab).sum(axis=1) / (ab * ab).sum(axis=1), 0.0, 1.0)
        out[n] = numpy.linalg.norm(a + t[:, None] * ab - p, axis=1).min()
    return out


def _source_boundary(mesh: ObjMesh, name: str) -> tuple[numpy.ndarray, numpy.ndarray]:
    edges = boundary_edges(mesh.families[name])
    return mesh.verts[[e[0] for e in edges]], mesh.verts[[e[1] for e in edges]]


def _on_line(points: numpy.ndarray, faces: list[list[int]]) -> numpy.ndarray:
    """Return the sorted rows of the used points lying on the cut x = 1."""
    used = sorted({v for f in faces for v in f})
    p = points[used]
    hit = p[numpy.abs(p[:, 0] - 1.0) < 1e-12]
    return hit[numpy.lexsort((hit[:, 2], hit[:, 1]))]


# ---- FR-424 R8: the edge length


@pytest.mark.parametrize("factor", [2.0, 0.5])
def test_the_median_edge_ratio_lies_in_the_band(factor):
    """P0380-REFINE (FR-424 R8): the median edge ratio of a remeshed sphere lies in EDGE_BAND.

    The control measures the same level against the factor it was NOT refined
    with, and the median leaves the band.
    """
    mesh = sphere()
    result = refine_group(mesh, ["S"], (), factor)
    faces = result.families["S"]
    median = _edge_ratio_median(mesh, "S", result.points, faces, factor)
    assert EDGE_BAND[0] <= median <= EDGE_BAND[1], median
    wrong = _edge_ratio_median(mesh, "S", result.points, faces, 1.0)
    assert not EDGE_BAND[0] <= wrong <= EDGE_BAND[1], wrong
    expected = len(mesh.families["S"]) * factor**2
    assert 0.5 * expected < len(faces) < 2.0 * expected
    assert EDGE_BAND[0] <= result.info["edge_ratio_median"] <= EDGE_BAND[1]


def test_every_node_lies_on_the_source_surface_and_faces_keep_the_orientation():
    """P0380-REFINE (FR-424 R8, R7): nodes are projected onto the source, faces face outward."""
    mesh = sphere()
    result = refine_group(mesh, ["S"], (), 2.0)
    source = trimesh.Trimesh(mesh.verts, numpy.asarray(mesh.families["S"]), process=False)
    _, distance, _ = trimesh.proximity.closest_point(source, result.points)
    assert distance.max() < 1e-9 * _size(mesh.verts)
    normals, centroids = normals_and_centroids(result.points, result.families["S"])
    assert ((normals * centroids).sum(axis=1) > 0).all()


# ---- FR-424 R8: curves


@pytest.mark.parametrize("factor", [2.0, 0.5])
def test_open_boundary_nodes_stay_on_the_boundary(factor):
    """P0380-REFINE (FR-424 R8): open boundaries are curves; a hole is neither opened nor closed.

    The control moves one source boundary node inward and the same check
    reports the level's boundary off the moved curve.
    """
    mesh = holed_plate()
    result = refine_group(mesh, ["P"], (), factor)
    faces = result.families["P"]
    loops = boundary_loops(faces)
    assert len(loops) == len(boundary_loops(mesh.families["P"])) == 2
    nodes = result.points[sorted({v for e in boundary_edges(faces) for v in e})]
    a, b = _source_boundary(mesh, "P")
    assert _polyline_distance(nodes, a, b).max() < 1e-9 * _size(mesh.verts)
    corners = mesh.verts[[0, 12, 13 * 12, 13 * 13 - 1, 4 * 13 + 4, 8 * 13 + 8]]
    assert NearestIndex(result.points).query(corners)[0].max() == 0.0
    moved = a.copy()
    moved[len(moved) // 2] += numpy.array([0.0, 0.0, 0.05])
    assert _polyline_distance(nodes, moved, b).max() > 1e-6


def test_a_quadrilateral_family_is_remeshed_into_triangles():
    """P0380-REFINE (FR-424 R8): a family of quadrilaterals is remeshed; its level is triangles.

    The control is the source itself, which the same check rejects.
    """
    quads = [
        [j * 9 + i, j * 9 + i + 1, (j + 1) * 9 + i + 1, (j + 1) * 9 + i]
        for j in range(8)
        for i in range(8)
    ]
    mesh = ObjMesh(plate_nodes(8, 8), {"Q": quads})
    result = refine_group(mesh, ["Q"], (), 2.0)
    faces = result.families["Q"]
    assert {len(f) for f in faces} == {3}
    assert {len(f) for f in mesh.families["Q"]} != {3}
    assert len(boundary_loops(faces)) == 1
    nodes = result.points[sorted({v for e in boundary_edges(faces) for v in e})]
    a, b = _source_boundary(mesh, "Q")
    assert _polyline_distance(nodes, a, b).max() < 1e-9 * _size(mesh.verts)
    assert 4 * 2 * 64 * 0.5 < len(faces) < 4 * 2 * 64 * 2


def test_ridge_nodes_stay_on_their_ridges():
    """P0380-REFINE (FR-424 R8): an edge whose dihedral exceeds RIDGE_DEGREES is a curve.

    On a cube every level edge sharper than the ridge angle has both nodes on
    a cube edge, every node stays on a cube face, and the eight corners stay.
    The control is a node off the edges, which the same predicate rejects.
    """
    mesh = cube()
    result = refine_group(mesh, ["C"], (), 2.0)
    pts, faces = result.points, result.families["C"]

    def on_cube_edge(p: numpy.ndarray) -> bool:
        return int((numpy.abs(numpy.abs(p) - 1.0) < 1e-9).sum()) >= 2

    sharp = [e for e, d in dihedral_degrees(pts, faces).items() if d > RIDGE_DEGREES]
    before = dihedral_degrees(mesh.verts, mesh.families["C"]).values()
    assert len(sharp) > 1.5 * sum(d > RIDGE_DEGREES for d in before)
    assert all(on_cube_edge(pts[v]) for e in sharp for v in e)
    assert (numpy.abs(numpy.abs(pts) - 1.0).min(axis=1) < 1e-9).all()
    corners = numpy.array([[x, y, z] for x in (-1, 1) for y in (-1, 1) for z in (-1, 1)], float)
    assert NearestIndex(pts).query(corners)[0].max() == 0.0
    assert not on_cube_edge(numpy.array([1.0, 0.3, 0.2]))
    assert len(faces) > 3 * len(mesh.families["C"])


def test_trailing_edge_edges_are_a_curve_and_reported():
    """P0380-REFINE (FR-424 R8, R4): trailing-edge nodes stay on it; its mid-points are returned.

    The plate's edge y = 0 is declared the trailing edge: every returned
    mid-point lies on that edge, and the source's mid-points are not what is
    returned at factor 2 (the control: the edge was resampled).
    """
    mesh = holed_plate()
    te = [i for i in range(13)]
    result = refine_group(mesh, ["P"], te, 2.0)
    mid = result.trailing_edge
    assert result.info["curve_edges"][TRAILING_EDGE] == 12
    assert len(mid) > 12
    assert numpy.abs(mid[:, 1]).max() < 1e-12
    assert numpy.abs(mid[:, 2]).max() < 1e-12
    none = refine_group(mesh, ["P"], (), 2.0)
    assert len(none.trailing_edge) == 0


# ---- FR-424 R8: interfaces


def test_an_interface_with_an_unchanged_family_keeps_its_nodes():
    """P0380-REFINE (FR-424 R8): remeshing A alone leaves its nodes on the cut with B unchanged.

    The control remeshes A and B together, and the same comparison sees the
    cut's nodes change.
    """
    mesh = two_families()
    source = _on_line(mesh.verts, mesh.families["A"])
    result = refine_group(mesh, ["A"], (), 2.0)
    kept = _on_line(result.points, result.families["A"])
    assert kept.shape == source.shape and numpy.array_equal(kept, source)
    both = refine_group(mesh, ["A", "B"], (), 2.0)
    shared = _on_line(both.points, both.families["A"])
    assert shared.shape != source.shape


def test_an_interface_between_two_remeshed_families_is_remeshed_once_and_shared():
    """P0380-REFINE (FR-424 R8): the cut between two remeshed families is one set of nodes."""
    mesh = two_families()
    result = refine_group(mesh, ["A", "B"], (), 2.0)
    fa, fb = result.families["A"], result.families["B"]
    common = {v for f in fa for v in f} & {v for f in fb for v in f}
    assert len(common) > 9
    assert numpy.abs(result.points[sorted(common)][:, 0] - 1.0).max() < 1e-9
    assert len(boundary_loops(fa + fb)) == 1


# ---- FR-425 R2: conforming to a grid's new nodes


def _cut_ids(mesh: ObjMesh) -> list[int]:
    a = set(mesh.family_vertices("A").tolist())
    return sorted(a & set(mesh.family_vertices("B").tolist()))


def _resampled_cut(mesh: ObjMesh, ys: numpy.ndarray) -> numpy.ndarray:
    return numpy.column_stack([numpy.ones_like(ys), ys, 0.15 * numpy.sin(numpy.pi * ys)])


@pytest.mark.parametrize(
    ("ys", "counts"),
    [
        (numpy.linspace(0.0, 1.0, 17), (8, 9, 0)),
        (numpy.linspace(0.0, 1.0, 5), (0, 5, 4)),
        (0.5 - 0.5 * numpy.cos(numpy.linspace(0.0, numpy.pi, 12)), (10, 2, 7)),
    ],
    ids=["doubled", "halved", "clustered"],
)
def test_conform_makes_the_neighbour_share_exactly_the_new_nodes(ys, counts):
    """P0380-DUMMY (FR-425 R2): B, rebuilt on A's new cut nodes, holds exactly those nodes there.

    Three resamplings of the cut: every source node kept and one inserted per
    interval, every other node dropped, and a clustering that keeps only the
    two ends. The report counts the nodes inserted, kept and removed. The
    control remeshes B without conforming, and its cut nodes are the
    source's, not the new ones.
    """
    mesh = two_families()
    new = _resampled_cut(mesh, ys)
    result = refine_group(mesh, ["B"], (), 1.0, conform=[(_cut_ids(mesh), new)])
    got = _on_line(result.points, result.families["B"])
    want = new[numpy.lexsort((new[:, 2], new[:, 1]))]
    assert got.shape == want.shape and numpy.array_equal(got, want)
    report = result.info["conformed_interfaces"][0]
    assert (report["inserted"], report["kept"], report["removed"]) == counts
    assert report["not_removed"] == 0
    assert len(boundary_loops(result.families["B"])) == 1
    plain = refine_group(mesh, ["B"], (), 1.0)
    assert not numpy.array_equal(_on_line(plain.points, plain.families["B"]), want)


# ---- FR-424 R10: the geometry extra


def _block_extra(monkeypatch) -> None:
    for name in ("scipy", "scipy.spatial", "rtree"):
        monkeypatch.setitem(sys.modules, name, None)


def test_a_remesh_without_the_extra_is_refused_before_any_work(monkeypatch):
    """P0380-REFINE (FR-424 R10, R11): no scipy or rtree refuses, naming the family and the remedy.

    The refusal comes before any work: a family the mesh does not hold would
    fail on its first use, and it is the refusal that is raised. The control
    is the same call with the extra present, which is not refused.
    """
    require_geometry_extra(["S"])
    require_geometry_extra([])
    _block_extra(monkeypatch)
    with pytest.raises(MissingExtraError) as caught:
        refine_group(sphere(), ["S"], (), 2.0)
    text = str(caught.value)
    assert "family S" in text and "pip install pyflightstream[geom]" in text
    assert text.endswith("Nothing was written.")
    with pytest.raises(MissingExtraError, match="Wing, Hub"):
        refine_group(sphere(), ["Wing", "Hub"], (), 2.0)
    require_geometry_extra([])


def test_the_remesh_module_imports_no_geometry_library_at_import():
    """P0380-REFINE (FR-424 R10): the remesh module imports no geometry library at import.

    Measured in a fresh interpreter against what the modules it imports have
    already loaded; the control imports trimesh by hand and is seen.
    """
    probe = textwrap.dedent(
        """
        import sys
        import pyflightstream.extras
        import pyflightstream.workspace._refine._obj
        import pyflightstream.workspace._refine._geometry
        watched = ("trimesh", "scipy", "rtree")
        before = {m for m in watched if m in sys.modules}
        import pyflightstream.workspace._refine._remesh
        after = {m for m in watched if m in sys.modules}
        if sys.argv[1:] == ["control"]:
            import trimesh
            after = {m for m in watched if m in sys.modules}
        print(sorted(after - before))
        """
    )
    # The interpreter imports the package these tests import (the checkout or the wheel).
    root = str(Path(pyflightstream.__file__).resolve().parents[1])
    env = {**os.environ, "PYTHONPATH": root}
    for argv in ([], ["control"]):
        out = subprocess.run(
            [sys.executable, "-c", probe, *argv],
            capture_output=True,
            text=True,
            check=True,
            env=env,
        ).stdout.strip()
        assert (out == "[]") is (not argv), out
        assert ("'trimesh'" in out) is bool(argv), out


# ---- FR-424 R12: determinism


def test_two_remeshes_of_one_source_are_identical():
    """P0380-REFINE (FR-424 R12): the same source and factor give the same nodes and faces."""
    mesh = two_families()
    first = refine_group(mesh, ["A", "B"], (), 0.5)
    second = refine_group(mesh, ["A", "B"], (), 0.5)
    assert numpy.array_equal(first.points, second.points)
    assert first.families == second.families
    assert first.info == second.info
