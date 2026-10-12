"""P0400-FFHARMONICS: the azimuthal harmonics guard (PFS-2095.009, PFS-2086.003).

The anti-aliasing cap ``m_max >= n // 2`` refused an odd grid of
``n = 2 m_max + 1`` azimuths, which carries order ``m_max`` unaliased, with a
message that contradicted itself; a negative or non-integer ``m_max`` was
accepted and gave an empty or meaningless ``m`` axis.
"""

from __future__ import annotations

import numpy as np
import pytest
import xarray as xr

from pyflightstream.farfield import FarfieldInputError, azimuthal_harmonics


def _ring(n: int, values: np.ndarray | None = None, psi_0: float = 0.0) -> xr.DataArray:
    psi = psi_0 + 2.0 * np.pi * np.arange(n) / n
    data = np.cos(psi) if values is None else values
    return xr.DataArray(data, dims=("psi",), coords={"psi": psi})


def test_p0400_ffharmonics_odd_grid_carries_its_highest_order() -> None:
    """P0400-FFHARMONICS: n = 13 with m_max = 6 is accepted; n = 9 with m_max = 4 too."""
    assert azimuthal_harmonics(_ring(13), m_max=6).sizes["m"] == 7
    assert azimuthal_harmonics(_ring(9), m_max=4).sizes["m"] == 5


def test_p0400_ffharmonics_even_grid_nyquist_is_still_refused() -> None:
    """P0400-FFHARMONICS: n = 12 with m_max = 6 is the Nyquist order and is refused."""
    with pytest.raises(FarfieldInputError, match="needs more than 12 uniform azimuths"):
        azimuthal_harmonics(_ring(12), m_max=6)


@pytest.mark.parametrize("m_max", [-1, 2.5, True])
def test_p0400_ffharmonics_m_max_must_be_a_non_negative_integer(m_max: object) -> None:
    """P0400-FFHARMONICS: m_max = -1 or 2.5 on a 16-azimuth lattice is refused (PFS-2086.003)."""
    with pytest.raises(FarfieldInputError, match="is not an azimuthal order"):
        azimuthal_harmonics(_ring(16), m_max=m_max)  # type: ignore[arg-type]


def test_p0400_ffharmonics_origin_offset_grid_gives_unrotated_coefficients() -> None:
    """P0400-FFHARMONICS-ORIGIN (PFS-2105.003): psi starting at 0.3 rad gives c_1 = 1/2, real.

    The FFT computes c_m only for psi_k = 2 pi k / N; on a grid offset by psi_0 every order
    came back multiplied by exp(i m psi_0).
    """
    n, psi_0 = 16, 0.3
    psi = psi_0 + 2.0 * np.pi * np.arange(n) / n
    field = np.cos(psi) + 0.25 * np.sin(2.0 * psi)
    c = azimuthal_harmonics(_ring(n, field, psi_0), m_max=3).values
    np.testing.assert_allclose(c, [0.0, 0.5, -0.125j, 0.0], atol=1e-12)
