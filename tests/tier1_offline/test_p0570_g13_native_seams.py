"""The native audit names the solver's seam slivers and still refuses any other (PFS-2220, G13).

A zero-area face of the mesh the solver makes of a CAD import passes only when every node lies on
an edge of a source face, or two of its nodes collapse onto a source vertex (a pole fan); a
zero-area face inside a source face is left unexplained and the build still fails.
"""

from __future__ import annotations

import importlib

from tests.tier1_offline._kernel_support import kernel_or_skip

_GRID = [(x / 3.0, y / 3.0) for y in range(4) for x in range(4)]


def _square_iges(path):
    gmsh = kernel_or_skip()
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("square")
        gmsh.model.occ.addRectangle(0, 0, 0, 1000.0, 1000.0)
        gmsh.model.occ.synchronize()
        gmsh.write(str(path))
    finally:
        gmsh.finalize()


def _mesh(path, extra_nodes, extra_faces):
    """Write the unit square as 18 triangles plus the given nodes and faces (1-based ids)."""
    nodes = [(x, y, 0.0) for x, y in _GRID] + extra_nodes
    faces = []
    for j in range(3):
        for i in range(3):
            a = j * 4 + i + 1
            faces += [(a, a + 1, a + 5), (a, a + 5, a + 4)]
    faces += extra_faces
    lines = ["g square"] + [f"v {x} {y} {z}" for x, y, z in nodes]
    lines += ["f " + " ".join(str(n) for n in face) for face in faces]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _explain(obj, iges):
    return importlib.import_module("pyflightstream.workspace._native_seams").explain_g1(obj, iges)


def test_slivers_on_a_source_edge_and_a_collapse_at_a_vertex_are_explained(tmp_path):
    iges, obj = tmp_path / "square.igs", tmp_path / "square.obj"
    _square_iges(iges)
    # nodes 17 to 19 lie on the bottom edge (collinear: zero area); 20 and 21 collapse at the
    # corner (0, 0) with node 2: a pole fan
    _mesh(
        obj,
        [(0.1, 0.0, 0.0), (0.2, 0.0, 0.0), (0.3, 0.0, 0.0), (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)],
        [(17, 18, 19), (20, 21, 2)],
    )
    record = _explain(obj, iges)
    assert record["zero_area"] == 2 and record["explained_zero_area"] == 2
    assert record["unexplained"] == 0 and record["off_edge_centroids"] == []


def test_a_zero_area_face_inside_a_source_face_is_not_explained(tmp_path):
    iges, obj = tmp_path / "square.igs", tmp_path / "square.obj"
    _square_iges(iges)
    _mesh(
        obj,
        [(0.4, 0.5, 0.0), (0.5, 0.5, 0.0), (0.6, 0.5, 0.0)],
        [(17, 18, 19)],
    )
    record = _explain(obj, iges)
    assert record["zero_area"] == 1 and record["unexplained"] == 1
    assert record["off_edge_centroids"] == [[0.5, 0.5, 0.0]]


def test_the_control_mesh_with_no_degenerate_face_has_nothing_to_explain(tmp_path):
    iges, obj = tmp_path / "square.igs", tmp_path / "square.obj"
    _square_iges(iges)
    _mesh(obj, [], [])
    record = _explain(obj, iges)
    assert record["zero_area"] == 0 and record["unexplained"] == 0


def test_nonmanifold_edge_between_different_source_edges_is_not_explained(tmp_path):
    iges, obj = tmp_path / "square.igs", tmp_path / "square.obj"
    _square_iges(iges)
    # The diagonal connects two boundary vertices but lies inside the source face.
    _mesh(obj, [], [(1, 4, 16), (1, 16, 13), (1, 16, 7)])
    record = _explain(obj, iges)
    assert record["nonmanifold"] > 0
    assert record["unexplained"] > 0


def test_duplicate_seam_face_is_not_explained(tmp_path):
    iges, obj = tmp_path / "square.igs", tmp_path / "square.obj"
    _square_iges(iges)
    _mesh(obj, [(0.1, 0, 0), (0.2, 0, 0), (0.3, 0, 0)], [(17, 18, 19), (19, 18, 17)])
    record = _explain(obj, iges)
    assert record["unexplained"] > 0


def test_duplicate_face_is_refused_even_when_g1_passed(tmp_path):
    from types import SimpleNamespace

    obj = tmp_path / "square.obj"
    _mesh(obj, [], [(1, 2, 6)])
    module = importlib.import_module("pyflightstream.workspace._native_seams")
    passed, _, _ = module.native_verdict(
        SimpleNamespace(passed=True, failures=[]), obj, "unused.igs"
    )
    assert not passed
