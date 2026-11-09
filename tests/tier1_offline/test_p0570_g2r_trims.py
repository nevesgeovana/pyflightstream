"""Trimmed faces of one base, their splits, and the preference the writer states (PFS-2220, G2R)."""

from __future__ import annotations

import math

import pytest

from pyflightstream._errors import InputValueError
from pyflightstream.workspace._iges_write import pack_records, read_iges
from tests.tier1_offline._kernel_support import kernel_or_skip


@pytest.fixture
def kernel():
    kernel_or_skip()
    from pyflightstream.workspace._gmsh import open_kernel

    k = open_kernel("test")
    try:
        yield k
    finally:
        k.close()


def _skin(kernel):
    """A degree 5 by 1 skin over a curved net, 2 by 3 m, its domain the unit square."""
    net = [[(2.0 * i / 5.0, 3.0 * j, 0.1 * math.sin(i)) for j in range(2)] for i in range(6)]
    return kernel.add_bspline_surface(
        net,
        knots_u=[0.0, 1.0],
        knots_v=[0.0, 1.0],
        mult_u=[6, 6],
        mult_v=[2, 2],
        deg_u=5,
        deg_v=1,
    )


def _box(u0, u1, v0=0.0, v1=1.0):
    corners = [(u0, v0), (u1, v0), (u1, v1), (u0, v1)]
    return [[[corners[k], corners[(k + 1) % 4]] for k in range(4)]]


def _two_faces(kernel):
    base = _skin(kernel)
    lower = kernel.add_trimmed_face(base, _box(0.0, 0.5))
    upper = kernel.add_trimmed_face(base, _box(0.5, 1.0))
    kernel.remove([base])
    return lower, upper


def test_a_skin_with_two_iso_trims_writes_and_reimports_as_two_faces(kernel, tmp_path):
    lower, upper = _two_faces(kernel)
    areas = [kernel.area(lower), kernel.area(upper)]
    assert [f.tag for f in kernel.faces()] == [lower.tag, upper.tag]
    path = tmp_path / "skin.igs"
    kernel.export_iges({"WING": [lower, upper]}, path)
    named = kernel.import_iges(path)
    assert len(named.faces) == 2
    back = sorted(kernel.area(f) for f in named.faces)
    assert back == pytest.approx(sorted(areas), rel=1e-6)
    assert sum(areas) > 0.0 and areas[0] != pytest.approx(areas[1], rel=1e-3)


def test_the_file_states_parameter_space_as_the_preference(kernel, tmp_path):
    lower, upper = _two_faces(kernel)
    path = tmp_path / "pref.igs"
    kernel.export_iges({"WING": [lower, upper]}, path)
    trims = [e for e in read_iges(path)["entities"] if e["type"] == 142]
    assert len(trims) == 2 and {e["parameters"][5] for e in trims} == {"1"}
    kernel.export_iges({"WING": [lower, upper]}, path, preference=2)
    trims = [e for e in read_iges(path)["entities"] if e["type"] == 142]
    assert {e["parameters"][5] for e in trims} == {"2"}
    with pytest.raises(InputValueError, match="IGES.PREF"):
        kernel.export_iges({"WING": [lower]}, path, preference=4)


def test_an_open_loop_is_refused_and_a_hole_is_a_second_loop(kernel):
    base = _skin(kernel)
    open_loop = [[[(0.1, 0.1), (0.9, 0.1)], [(0.9, 0.1), (0.9, 0.9)], [(0.9, 0.9), (0.1, 0.5)]]]
    with pytest.raises(InputValueError, match="open"):
        kernel.add_trimmed_face(base, open_loop)
    with pytest.raises(InputValueError, match="outer loop"):
        kernel.add_trimmed_face(base, [])
    whole = kernel.area(base)
    hole = kernel.area(kernel.add_trimmed_face(base, _box(0.4, 0.6, 0.4, 0.6)))
    ring = kernel.add_trimmed_face(base, [*_box(0.0, 1.0), *_box(0.4, 0.6, 0.4, 0.6)])
    assert kernel.area(ring) == pytest.approx(whole - hole, rel=1e-6)
    reversed_hole = [[[b, a] for a, b in reversed(_box(0.4, 0.6, 0.4, 0.6)[0])]]
    ring = kernel.add_trimmed_face(base, [*_box(0.0, 1.0), *reversed_hole])
    assert kernel.area(ring) == pytest.approx(whole - hole, rel=1e-6)


def test_split_face_uv_cuts_exactly_on_an_iso_line_in_either_direction(kernel):
    base = _skin(kernel)
    face = kernel.add_trimmed_face(base, _box(0.1, 0.9, 0.05, 0.95))
    whole = kernel.area(face)
    low, high = kernel.split_face_uv(face, "u", 0.5)
    assert kernel.area(low) + kernel.area(high) == pytest.approx(whole, rel=1e-9)
    assert kernel.bbox(low)[1][0] < kernel.bbox(high)[1][0] + 1e-9
    assert kernel.uv_bounds(low)[1][0] == pytest.approx(0.5)
    assert kernel.uv_bounds(high)[0][0] == pytest.approx(0.5)
    before = kernel.area(high)
    first, second = kernel.split_face_uv(high, "v", 0.5)
    assert kernel.area(first) + kernel.area(second) == pytest.approx(before, rel=1e-9)
    assert kernel.uv_bounds(second)[0][1] == pytest.approx(0.5)
    (same,) = kernel.split_face_uv(second, "u", 0.99)
    assert kernel.area(same) == pytest.approx(kernel.area(second), rel=1e-9)


def test_split_face_uv_refuses_what_it_cannot_cut_exactly(kernel):
    base = _skin(kernel)
    face = kernel.add_trimmed_face(base, _box(0.0, 1.0))
    with pytest.raises(InputValueError, match="domain"):
        kernel.split_face_uv(face, "u", 1.5)
    with pytest.raises(InputValueError, match="'u' or 'v'"):
        kernel.split_face_uv(face, "w", 0.5)
    plane = kernel.add_planar_face([(0, 0, 5), (1, 0, 5), (1, 1, 5), (0, 1, 5)])
    with pytest.raises(InputValueError, match="B-spline base"):
        kernel.split_face_uv(plane, "u", 0.5)


def test_reparametrize_and_shared_curve_read_the_edge_between_two_faces(kernel):
    first, second = _two_faces(kernel)
    made = kernel.fragment([first], [second])
    (lower,), (upper,) = made.from_a[0], made.from_b[0]
    edge = kernel.shared_curve(lower, upper)
    assert edge is not None
    low, high = kernel.edge_bounds(edge)
    for t in (low, 0.5 * (low + high), high):
        for face in (lower, upper):
            uv = kernel.reparametrize(edge, face, t)
            assert uv[0] == pytest.approx(0.5)
            on_face = kernel.value(face, uv)
            on_edge = kernel.edge_values(edge, [t])[0]
            assert tuple(on_face) == pytest.approx(tuple(on_edge), abs=1e-9)
    far = kernel.add_planar_face([(9, 9, 9), (10, 9, 9), (10, 10, 9), (9, 10, 9)])
    assert kernel.shared_curve(lower, far) is None
    edges = {abs(e) for e in kernel.boundary(lower)} & {abs(e) for e in kernel.boundary(upper)}
    assert edges == {edge}


def test_shared_curve_refuses_two_faces_that_share_two_edges(kernel, monkeypatch):
    from pyflightstream.workspace._cad import Face

    edges = {1: (1, 2, -3), 2: (-2, 3, 4)}
    monkeypatch.setattr(kernel, "boundary", lambda face: edges[face.tag])
    with pytest.raises(InputValueError, match="share 2 edges"):
        kernel.shared_curve(Face(1), Face(2))


def test_parameter_lines_break_between_values_never_inside_a_number():
    values = [f"{1.0 / 3.0 + k:.17E}" for k in range(40)]
    records = pack_records(values, 64)
    assert all(len(r) <= 64 for r in records)
    joined = "".join(records)
    assert joined == ",".join(values) + ";"
    pieces = [piece for r in records for piece in r.replace(";", ",").split(",") if piece]
    assert sorted(pieces) == sorted(values)
    assert all(r.endswith(",") or r.endswith(";") for r in records)
