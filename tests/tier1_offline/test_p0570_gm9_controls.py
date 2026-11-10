"""PFS-2215: control cuts preserve imported trims and clearance uses trimmed faces."""

from __future__ import annotations

import pytest

from pyflightstream.exceptions import InputValueError
from tests.tier1_offline._kernel_support import kernel_or_skip


@pytest.fixture
def kernel():
    kernel_or_skip()
    from pyflightstream.workspace._gmsh import open_kernel

    instance = open_kernel("control surface checks")
    try:
        yield instance
    finally:
        instance.close()


def _surface(kernel):
    return kernel.add_bspline_surface(
        [[(float(i), float(j), 0.0) for j in range(4)] for i in range(4)],
        knots_u=[0.0, 1.0],
        knots_v=[0.0, 1.0],
        mult_u=[4, 4],
        mult_v=[4, 4],
        deg_u=3,
        deg_v=3,
    )


def _loop(a, b, c, d):
    corners = [(a, c), (b, c), (b, d), (a, d)]
    return [[corners[i], corners[(i + 1) % 4]] for i in range(4)]


@pytest.mark.parametrize("direction", ["u", "v"], ids=["P0570-G9-ISO-U", "P0570-G9-ISO-V"])
def test_p0570_gm9_imported_split_preserves_hole(kernel, tmp_path, direction):
    base = _surface(kernel)
    trimmed = kernel.add_trimmed_face(base, [_loop(0, 1, 0, 1), _loop(0.2, 0.4, 0.2, 0.4)])
    path = tmp_path / "perforated.igs"
    kernel.export_iges({"PANEL": [trimmed]}, path)
    face = kernel.import_iges(path).faces[0]
    split = getattr(kernel, "split_imported_face_uv", kernel.split_face_uv)
    try:
        pieces = split(face, direction, 0.6)
    except InputValueError as error:
        pytest.fail(f"an imported B-spline must support exact iso splitting: {error}")
    assert len(pieces) == 2
    assert [kernel.area(f) for f in pieces] == pytest.approx([5.04, 3.6], abs=1e-8)
    assert not any(kernel.is_inside(f, (0.3, 0.3)) for f in pieces)
    # NO: invalid parameters must not remove or alter any face.
    before = [(f, kernel.area(f)) for f in kernel.faces()]
    with pytest.raises(InputValueError, match="direction"):
        split(pieces[0], "w", 0.3)
    with pytest.raises(InputValueError, match="finite"):
        split(pieces[0], direction, float("nan"))
    assert [(f, kernel.area(f)) for f in kernel.faces()] == before


@pytest.mark.parametrize("offset", [0.25, 0.0], ids=["P0570-G9-DIST-YES", "P0570-G9-DIST-NO"])
def test_p0570_gm9_minimum_distance_contact_and_separation(kernel, offset):
    a = kernel.add_planar_face([(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)])
    b = kernel.add_planar_face([(0, 0, offset), (1, 0, offset), (1, 1, offset), (0, 1, offset)])
    distance = getattr(kernel, "minimum_distance", None)
    assert callable(distance), "F3 requires a native face-set minimum distance"
    assert distance([a], [b]) == pytest.approx(offset, abs=1e-12)
    assert (distance([a], [b]) > 0) is (offset > 0)
    with pytest.raises(InputValueError, match="empty"):
        distance([], [b])


def test_p0570_gm9_minimum_distance_respects_holes_and_crossings(kernel):
    base = _surface(kernel)
    ring = kernel.add_trimmed_face(base, [_loop(0, 1, 0, 1), _loop(0.2, 0.8, 0.2, 0.8)])
    inside_hole = kernel.add_planar_face([(1, 1, 0), (2, 1, 0), (2, 2, 0), (1, 2, 0)])
    crossing = kernel.add_planar_face([(0.3, 0, -1), (0.3, 3, -1), (0.3, 3, 1), (0.3, 0, 1)])
    distance = getattr(kernel, "minimum_distance", None)
    assert callable(distance), "F3 requires a native face-set minimum distance"
    assert distance([ring], [inside_hole]) == pytest.approx(0.4, abs=1e-9)
    assert distance([ring], [inside_hole, crossing]) == pytest.approx(0, abs=1e-12)
