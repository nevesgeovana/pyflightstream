"""P0570 geometry kernel: a surface projection whose parameters the kernel returns as zeros.

gmsh 4.13, the declared floor, returns zeros for the parameters of a surface projection and later
versions return the true ones. These tests make the projection return those zeros, so they hold on
every installed version.
"""

import numpy as np
import pytest

LIMITS = {"chord_m": 0.2, "forward_count": 13, "reverse_count": 13, "edge_count": 19}


@pytest.fixture
def kernel():
    pytest.importorskip("gmsh", reason="needs the optional extra: gmsh")
    from pyflightstream.workspace._gmsh import session

    with session("a test") as gmsh:
        gmsh.model.add("test")
        yield gmsh


def _zero_surface_parameters(monkeypatch, gmsh):
    real = gmsh.model.getClosestPoint

    def closest(dim, tag, coord):
        xyz, parametric = real(dim, tag, coord)
        return (xyz, np.zeros_like(parametric)) if dim == 2 else (xyz, parametric)

    monkeypatch.setattr(gmsh.model, "getClosestPoint", staticmethod(closest))


def test_p0570_closest_on_face_recovers_zero_parameters_on_a_curved_face(kernel, monkeypatch):
    from pyflightstream.workspace._gmsh import closest_on_face

    occ = kernel.model.occ
    grid = np.linspace(0, 1, 5)
    points = [occ.addPoint(x, y, 0.2 * np.sin(x) * np.cos(y)) for y in grid for x in grid]
    face = occ.addBSplineSurface(points, 5)
    occ.synchronize()
    asked = np.array([[0.5, 0.5, 0.0], [0.25, 0.75, 0.3]])
    expected = np.asarray(kernel.model.getClosestPoint(2, face, asked.ravel())[0]).reshape(-1, 3)
    _zero_surface_parameters(monkeypatch, kernel)
    xyz, uv = closest_on_face(kernel.model, face, asked)
    assert xyz == pytest.approx(expected, abs=1e-6)
    at_uv = np.asarray(kernel.model.getValue(2, face, uv.ravel())).reshape(-1, 3)
    assert at_uv == pytest.approx(expected, abs=1e-6)


def test_p0570_closest_on_face_keeps_a_projection_inside_the_trim(kernel):
    from pyflightstream.workspace._gmsh import closest_on_face

    face = kernel.model.occ.addRectangle(0, 0, 0, 1, 1)
    kernel.model.occ.synchronize()
    xyz, uv = closest_on_face(kernel.model, face, np.array([[0.25, 0.75, 0.3]]))
    assert xyz[0] == pytest.approx([0.25, 0.75, 0.0], abs=1e-9)
    assert kernel.model.isInside(2, face, uv[0], parametric=True)


def test_p0570_reverse_sees_the_extension_when_the_kernel_returns_zero_parameters(
    kernel, monkeypatch
):
    from pyflightstream.workspace._geometry_check import check_against_original

    original = kernel.model.occ.addRectangle(0, 0, 0, 1, 1)
    rebuilt = kernel.model.occ.addRectangle(-1, -1, 0, 3, 3)
    kernel.model.occ.synchronize()
    _zero_surface_parameters(monkeypatch, kernel)
    result = check_against_original([rebuilt], [original], LIMITS)
    assert result["accepted"]
    assert result["unrestricted_reverse"]["max_m"] > 1
    assert result["restricted_reverse"]["max_m"] < 1e-12
    assert result["reverse_excluded_boundary_samples"] > 0
