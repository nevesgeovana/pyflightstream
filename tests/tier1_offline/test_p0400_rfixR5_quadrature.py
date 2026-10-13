"""Exercise the strip-edge API contract on flat, descending and nonfinite coordinates."""

# ruff: noqa: N999 - The lane contract prescribes the rfixR5 filename.

import numpy as np
import pytest

from pyflightstream.farfield.quadrature import strip_edges


@pytest.mark.requirement("FR-451")
def test_p0400_rfixr5_strip_edges_contract():
    """P0400-RFIXR5-119: document trace order, actual refusals and NaN propagation."""
    np.testing.assert_array_equal(strip_edges(np.array([0, 0])), [0, 0, 0])
    np.testing.assert_array_equal(strip_edges(np.array([2, 1])), [2.5, 1.5, 0.5])
    assert np.isnan(strip_edges(np.array([0, np.nan]))).all()
    doc = strip_edges.__doc__ or ""
    assert "constant or descending" in doc
    assert "Nonfinite coordinates propagate" in doc
    assert "one-dimensional" in doc and "ends" in doc
    assert "strictly increasing" not in doc
