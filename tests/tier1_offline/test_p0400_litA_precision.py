"""Reproduce write_csv_table with the study's small induced-drag coefficients."""

# ruff: noqa: N999 - the release lane requires this filename.

import pytest

from pyflightstream.post._tables import read_csv_table, write_csv_table


@pytest.mark.requirement("P0400-LITA-COEFFICIENT-PRECISION")
@pytest.mark.parametrize(
    "column",
    [
        "CL",
        "CDI",
        "CD0",
        "CDP",
        "CDV",
        "CMY",
        "CL_PROP",
        "CDI_T",
        "CDI_T_VORT",
        "CDI_NEAR_PRESSURE",
        "CT_PROP",
        "CQ_PROP",
        "CP_PROP",
        "Cx",
        "Total_CL",
        "Wing_CMx",
    ],
)
def test_p0400_lita_coefficients_keep_six_significant_figures(tmp_path, column):
    value = 0.000123456789
    table = write_csv_table(tmp_path / "product.csv", [column], [[value]])
    _, rows = read_csv_table(table)
    assert float(rows[0][column]) == pytest.approx(value, rel=5e-6)


@pytest.mark.requirement("P0400-LITA-COEFFICIENT-PRECISION")
def test_p0400_lita_settings_and_drift_keep_their_stated_format(tmp_path):
    table = write_csv_table(
        tmp_path / "product.csv",
        ["CL", "CL_DRIFT_PCT", "SET_CONVERGENCE"],
        [[0.000123456789, 0.123456789, "1e-06"]],
    )
    _, rows = read_csv_table(table)
    assert rows[0] == {"CL": "0.000123457", "CL_DRIFT_PCT": "0.12346", "SET_CONVERGENCE": "1e-06"}
