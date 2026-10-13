"""P0400-SIGDIGITS: MU, time_s and coefficients are written at significant digits.

At the 0.40.0 base every float of every product went through the five-decimal
funnel, so sea-level viscosity was written 0.00002 (one significant digit, 12
per cent off the stated value) and a rotor's time steps were quantised.
"""

from __future__ import annotations

import pytest

from pyflightstream.post._tables import read_csv_table, write_csv_table
from pyflightstream.post.point_tables import write_sections_table
from tests.tier1_offline.test_post_products import SLOADS, _series_call

MU = 1.7892976260350732e-05


def test_p0400_sigdigits_the_funnel_keeps_mu_time_and_coefficients(tmp_path):
    """P0400-SIGDIGITS: quantities keep six digits; exact values keep five decimals."""
    table = write_csv_table(
        tmp_path / "t.csv",
        ("time_s", "MU", "CL"),
        [(2.78e-5, MU, 0.123456789), (1234.56789, MU, 1.0)],
    )
    _, rows = read_csv_table(table)
    assert rows[0] == {"time_s": "2.78e-05", "MU": "1.7893e-05", "CL": "0.123457"}
    assert rows[1] == {"time_s": "1234.56789", "MU": "1.7893e-05", "CL": "1.00000"}


def test_p0400_sigdigits_mu_round_trips_in_a_sections_file(tmp_path):
    """P0400-SIGDIGITS: a sections table states MU to four significant digits or more."""
    condition = {"ALPHA": 0.0, "BETA": 0.0, "MACH": 0.2, "RHO": 1.225, "MU": MU}
    table = write_sections_table(tmp_path / "s.csv", SLOADS, mach=0.2, condition=condition)
    _, rows = read_csv_table(table)
    assert rows and all(float(row["MU"]) == pytest.approx(MU, rel=1e-4) for row in rows)


def test_p0400_sigdigits_mu_round_trips_in_a_series(tmp_path):
    """P0400-SIGDIGITS: a series table states MU to four significant digits or more."""
    from pyflightstream.post.series import write_point_series

    workspace, arguments = _series_call(tmp_path)
    written, _ = write_point_series(
        workspace.root, overwrite=True, condition={"MU": MU, "RHO": 1.225}, **arguments
    )
    (series,) = [path for path in written if path.name.endswith("_loads_series.csv")]
    _, rows = read_csv_table(series)
    assert rows and all(float(row["MU"]) == pytest.approx(MU, rel=1e-4) for row in rows)


@pytest.mark.parametrize(
    "column",
    [
        "Time (sec)",
        "Time",
        "RHO",
        "Offset",
        "Fx",
        "momentum_thickness",
        "FX_PROP",
        "VX1",
        "BL_MOMENTUM_THICKNESS2",
        "BL_TOTAL_THICKNESS",
        "AZIMUTH_START",
    ],
)
def test_p0400_sigdigits_small_dimensional_cells_keep_their_scale(tmp_path, column):
    """P0400-SIGDIGITS: dimensional cells beyond viscosity and series time retain digits."""
    small = 1.234567e-6
    table = write_csv_table(tmp_path / "physical.csv", [column, "CL_PROP"], [[small, small]])
    _, rows = read_csv_table(table)
    assert float(rows[0][column]) == pytest.approx(small, rel=1e-5)
    assert float(rows[0]["CL_PROP"]) == pytest.approx(small, rel=1e-5)
