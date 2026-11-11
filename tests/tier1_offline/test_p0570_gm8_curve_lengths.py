"""Native curve lengths for the measured control junction boundaries."""

import numpy as np
import pytest

from tests.tier1_offline._kernel_support import kernel_or_skip


def test_p0570_native_curve_length_uses_the_kernel_integral():
    from math import asinh, sqrt

    from pyflightstream.workspace._gmsh import open_kernel

    kernel_or_skip()
    kernel = open_kernel("native arc-length oracle")
    try:
        face = kernel.add_bspline_surface(
            [[(0, 0, 0), (0, 0, 1)], [(0.5, 0, 0), (0.5, 0, 1)], [(1, 1, 0), (1, 1, 1)]],
            knots_u=[0, 1],
            knots_v=[0, 1],
            mult_u=[3, 3],
            mult_v=[2, 2],
            deg_u=2,
            deg_v=1,
        )
        length = getattr(kernel, "edge_length", None)
        assert callable(length), "junction references need native arc lengths"
        for edge in kernel.boundary(face):
            lo, hi = kernel.edge_bounds(edge)
            ends = kernel.edge_values(edge, [lo, hi])
            if np.allclose(ends[:, 2], 0) and abs(ends[1, 0] - ends[0, 0]) > 0.9:
                exact = sqrt(5) / 2 + asinh(2) / 4
                assert length(edge) == pytest.approx(exact, abs=1e-10)
                assert length(-edge) == length(edge)
                break
        else:
            pytest.fail("the parabolic boundary must exist")
    finally:
        kernel.close()
