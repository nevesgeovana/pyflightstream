"""Measure torsion grid accuracy against analytic sections, independently of prose."""

import pytest

from pyflightstream.fsi.sections import torsion_constant
from tests.tier1_offline.test_g41_section_properties import (
    _ellipse_torsion,
    _rectangle,
    _rectangle_torsion,
    _regular_polygon,
)


@pytest.mark.parametrize(
    "shape,a,b",
    [
        ("ellipse", 0.02, 0.02),
        ("ellipse", 0.04, 0.02),
        ("ellipse", 0.05, 0.005),
        ("rectangle", 0.03, 0.03),
        ("rectangle", 0.06, 0.02),
        ("rectangle", 0.05, 0.005),
    ],
    ids=[
        "P0410-circle",
        "P0410-ellipse2",
        "P0410-ellipse10",
        "P0410-square",
        "P0410-rectangle3",
        "P0410-plate10",
    ],
)
@pytest.mark.parametrize("cells,tolerance", [(32, 0.003), (64, 0.0008)])
def test_p0410_torsion_accuracy(shape, a, b, cells, tolerance):
    if shape == "ellipse":
        contour, exact = _regular_polygon(720, a, b), _ellipse_torsion(a, b)
    else:
        contour, exact = _rectangle(a, b), _rectangle_torsion(a, b)
    actual = torsion_constant(contour, grid_cells=cells).torsion_constant_m4
    assert abs(actual - exact) / exact < tolerance
