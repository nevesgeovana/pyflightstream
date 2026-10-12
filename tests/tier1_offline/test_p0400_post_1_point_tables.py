"""P0400-STATICPLOTS (PFS-2105.015): at VINF = 0 the plots table's coefficients read NA.

Rescaled by (VREF / VINF)^2 they cannot be; the table kept the VREF
normalisation in silence while the definition says the free stream's.
"""

from __future__ import annotations

import warnings

import pytest

from pyflightstream.post.point_tables import write_plots_table
from pyflightstream.post.products import read_csv_table
from tests.tier1_offline.test_post_superfile import _PLOTS


@pytest.mark.parametrize((), [pytest.param(id="P0400-STATICPLOTS")])
def test_p0400_staticplots_coefficients_are_na_and_said(tmp_path):
    """P0400-STATICPLOTS: CL and CDI columns NA, forces kept, and one warning."""
    export = _PLOTS.replace(
        "Freestream velocity (m/s)                   49.036",
        "Freestream velocity (m/s)                   .000",
    )
    assert export != _PLOTS
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        table = write_plots_table(tmp_path / "P1_plots.csv", export, pol="1")
    assert table is not None
    _columns, rows = read_csv_table(table)
    assert {row["CL_MRP_TOTAL"] for row in rows} == {"NA"}
    assert {row["CDI_MRP_TOTAL"] for row in rows} == {"NA"}
    assert [row["FX_MRP_TOTAL"] for row in rows] != ["NA", "NA"]
    assert any("free-stream velocity of 0 m/s" in str(w.message) for w in caught), caught
