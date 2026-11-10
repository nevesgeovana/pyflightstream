"""PFS-2220 export checks and distance regression, from the lane acceptance.

Reproduction: measure a point on a unit plane whose v domain is [0, 10000].
Its distance must stay below 1e-9 of the model size near a parameter bound.
"""

import numpy as np
import pytest

from pyflightstream.workspace._geom_gate import _Surface


@pytest.mark.parametrize("u", [0.001, 0.999], ids=["P0570-low-bound", "P0570-high-bound"])
def test_p0570_anisotropic_surface_distance(u):
    values = [128, 1, 1, 1, 1, 0, 0, 1, 0, 0]
    values += [0, 0, 1, 1, 0, 0, 10000, 10000]
    values += [1, 1, 1, 1]
    values += [0, 0, 0, 1, 0, 0, 0, 1, 0, 1, 1, 0]
    values += [0, 1, 0, 10000]
    surface = _Surface([str(v) for v in values])
    point = np.array([u, 0.12345, 0.0])
    assert surface.distance(point) < 1e-9 * np.sqrt(2)
