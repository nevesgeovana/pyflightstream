"""The 0.40.0 NumPy replacement for the far-field point adapter."""

import numpy as np

from pyflightstream.farfield import LatticeFields, lattice_fields
from pyflightstream.probes import ProbeLattice


def test_p0400_numpy_point_mapping_preserves_coordinates_and_named_fields():
    """P0400-POINT-MAPPING (FR-41, FR-457): the interim adapter maps NumPy fields.

    PFS-2023.03 replaces dataset_to_points with LatticeFields.points in 0.40.0.
    This proves that preparatory mapping, not the pending ITACA integration.
    """
    lattice = ProbeLattice(tip_radius=2.0, stations=(0.5, 1.5), ring_edges=(0.5, 1.0), n_psi=8)
    u = np.arange(16.0).reshape(2, 1, 8)
    survey = lattice_fields(lattice, fields={"u": u, "p_prime": u + 10.0})
    assert isinstance(survey, LatticeFields)
    assert isinstance(survey.stations, np.ndarray)
    np.testing.assert_array_equal(survey.stations, [0.5, 1.5])
    points, fields = survey.points()
    assert isinstance(points, np.ndarray)
    assert points.shape == (16, 3)
    diagonal = 1.5 / np.sqrt(2.0)
    np.testing.assert_array_equal(points[:, 0], [1.0] * 8 + [3.0] * 8)
    np.testing.assert_allclose(
        points[:, 1],
        [0.0, diagonal, 1.5, diagonal, 0.0, -diagonal, -1.5, -diagonal] * 2,
        atol=1e-14,
    )
    np.testing.assert_allclose(
        points[:, 2],
        [1.5, diagonal, 0.0, -diagonal, -1.5, -diagonal, 0.0, diagonal] * 2,
        atol=1e-14,
    )
    assert set(fields) == {"u", "p_prime"}
    for name, expected in (("u", np.arange(16.0)), ("p_prime", np.arange(10.0, 26.0))):
        assert isinstance(fields[name], np.ndarray)
        np.testing.assert_array_equal(fields[name], expected)
