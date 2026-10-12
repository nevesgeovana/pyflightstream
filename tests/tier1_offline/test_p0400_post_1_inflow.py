"""P0400-MINUSXAXIS (PFS-2105.037): blade-view harmonics refuse a -X axis.

omega's sign is its hand about +X; with a -X axis a positive omega turned
left-handed about +X while every column of the product says right-handed.
"""

from __future__ import annotations

import pytest

from pyflightstream._errors import ProductError
from pyflightstream.post.inflow_tools import blade_view_harmonics
from tests.tier1_offline.test_p0320_d_inflow_tools import OMEGA, RADIUS, _uniform_at_aoa


@pytest.mark.parametrize((), [pytest.param(id="P0400-MINUSXAXIS")])
def test_p0400_minusxaxis_is_refused():
    """P0400-MINUSXAXIS: (-1, 0, 0) is refused, naming +X and the sign of omega."""
    with pytest.raises(ProductError, match=r"\+X and a negative omega"):
        blade_view_harmonics(
            _uniform_at_aoa(5.0),
            hub=(0.0, 0.0, 0.0),
            axis=(-1.0, 0.0, 0.0),
            omega_rad_s=OMEGA,
            radii_m=[RADIUS],
        )
    assert blade_view_harmonics(
        _uniform_at_aoa(5.0),
        hub=(0.0, 0.0, 0.0),
        axis=(2.0, 0.0, 0.0),
        omega_rad_s=OMEGA,
        radii_m=[RADIUS],
    )
