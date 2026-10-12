"""P0400-PLOTSNA and P0400-BANNER: the plots table, its `NA` cells and its banner.

At the 0.40.0 base a plots export whose banner states no free-stream velocity
raised a bare AnchorNotFoundError out of write_plots_table, which no caller
caught, so the whole post ended; a NaN the export carried was written `NA` and
neither plots_table_series nor the unsteady probes table could read that token
back.
"""

from __future__ import annotations

import math

import pytest

from pyflightstream._errors import ProductError
from pyflightstream.post._tables import plots_table_series, read_csv_table
from pyflightstream.post.point_tables import (
    write_plots_table,
    write_sections_table,
    write_unsteady_probes_table,
)
from tests.tier1_offline.test_post_products import (
    PLOTS_HEADER,
    SLOADS,
    _products_manifest,
    _unsteady_workspace,
)

_TABLE = "Time-step,CL_MRP_TOTAL,MACH1,\n1.0000,0.1,0.2,\n2.0000,NaN,0.3,\n3.0000,0.3,NaN,\n"
_FOOT = "-" * 60 + "\n     Force Units: Coefficients\n"


def _without_banner(text: str) -> str:
    return "".join(
        line for line in text.splitlines(keepends=True) if "Freestream velocity" not in line
    )


def test_p0400_banner_a_plots_export_without_its_banner_is_a_product_error(tmp_path):
    """P0400-BANNER: no 'Freestream velocity (m/s)' line is a ProductError naming the file."""
    export = _without_banner(PLOTS_HEADER) + _TABLE + _FOOT
    with pytest.raises(ProductError, match="P_plots.csv"):
        write_plots_table(tmp_path / "P_plots.csv", export)


def test_p0400_banner_the_post_records_a_skip_and_goes_on(tmp_path):
    """P0400-BANNER: the campaign post skips the point's plots table instead of ending."""
    from pyflightstream.post.products import write_campaign_products

    workspace = _unsteady_workspace(tmp_path, reductions=None)
    export = workspace.sim_dir("7001") / "outputs" / "AL-020_plots.txt"
    export.write_text(_without_banner(export.read_text(encoding="utf-8")), encoding="utf-8")
    write_campaign_products(workspace)
    skipped = _products_manifest(workspace)["skipped"]
    assert "Freestream velocity" in skipped["probes/AL-020_plots.csv"]


def test_p0400_banner_a_sections_export_without_its_reynolds_number_is_a_product_error(
    tmp_path,
):
    """P0400-BANNER: the sections table refuses a banner with no Reynolds number by name."""
    text = "".join(
        line for line in SLOADS.splitlines(keepends=True) if "Reynolds Number" not in line
    )
    assert text != SLOADS, "the fixture's Reynolds line moved"
    with pytest.raises(ProductError, match="S_sections.csv"):
        write_sections_table(tmp_path / "S_sections.csv", text, mach=0.2)


def test_p0400_plotsna_a_nan_round_trips_through_the_plots_table(tmp_path):
    """P0400-PLOTSNA: export NaN, table `NA`, series NaN, every other value kept."""
    table = write_plots_table(tmp_path / "P_plots.csv", PLOTS_HEADER + _TABLE + _FOOT)
    _, rows = read_csv_table(table)
    assert rows[1]["CL_MRP_TOTAL"] == "NA"
    columns, series = plots_table_series(table)
    cl = series.fields["CL_MRP_TOTAL"][:, 0]
    assert math.isnan(cl[1]) and cl[0] == pytest.approx(0.4) and cl[2] == pytest.approx(1.2)
    assert series.steps.tolist() == [1, 2, 3]


def test_p0400_plotsna_one_na_cell_keeps_the_probes_table(tmp_path):
    """P0400-PLOTSNA: an `NA` probe cell is `NA` in the probes table, the rest present."""
    table = write_plots_table(tmp_path / "P_plots.csv", PLOTS_HEADER + _TABLE + _FOOT)
    probes = write_unsteady_probes_table(
        tmp_path / "P_probes.csv",
        table,
        positions={1: (0.0, 0.0, 0.0, "MRP")},
        parameters=["MACH"],
    )
    assert probes is not None
    _, rows = read_csv_table(probes)
    assert [row["MACH"] for row in rows] == ["0.20000", "0.30000", "NA"]
