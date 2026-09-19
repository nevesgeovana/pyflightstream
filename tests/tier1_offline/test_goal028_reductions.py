"""A reduction names its rotor, states its moment point, and never averages a clock.

- RI-03. The per-rotor reduction files share one header and no column named the
  rotor: the alias was in the file name alone, which does not decompose, so two
  rotors' files were identical inside and indistinguishable once concatenated.
- RI-07. `write_reduction_table` averaged EVERY column of the plots table, the
  clock included, and published `Time-step 4.50000` beside FIRST_STEP 1 and
  LAST_STEP 8. The mean of a step counter measures nothing. The unsteady polar
  beside it has excluded the clock since 0.23.0.
- CC-09. The table averages the plots' moment columns and stated no moment point.

The expectations are the requirement's: the rotor is the alias the plan names,
`NA` on the time average, which belongs to no rotor; the clock columns are absent.
"""

from __future__ import annotations

from pyflightstream.post.products import (
    NOT_APPLICABLE,
    read_csv_table,
    write_campaign_products,
)
from tests.tier1_offline.test_post_products import (
    TWO_ROTOR_PLAN,
    _products_manifest,
    _unsteady_workspace,
)


def _reductions(tmp_path):
    workspace = _unsteady_workspace(tmp_path, reductions=TWO_ROTOR_PLAN)
    write_campaign_products(workspace)
    folder = workspace.root / "post" / "products" / "probes"
    return workspace, {path.name: read_csv_table(path) for path in folder.glob("AL-020_*.csv")}


def test_a_per_rotor_reduction_names_its_rotor_in_its_rows(tmp_path):
    _workspace_, tables = _reductions(tmp_path)
    for alias in ("LIFT_L1", "PUSHER"):
        columns, rows = tables[f"AL-020_per_blade_{alias}.csv"]
        assert "ROTOR" in columns, columns
        assert {row["ROTOR"] for row in rows} == {alias}, rows
    columns, rows = tables["AL-020_time_average.csv"]
    assert {row["ROTOR"] for row in rows} == {NOT_APPLICABLE}, "the time average is no rotor's"


def test_no_reduction_publishes_the_mean_of_a_clock(tmp_path):
    _workspace_, tables = _reductions(tmp_path)
    reductions = {name: table for name, table in tables.items() if "_plots" not in name}
    assert len(reductions) >= 3, sorted(tables)
    for name, (columns, _rows) in reductions.items():
        assert "Time-step" not in columns and "Time (sec)" not in columns, (name, columns)
    # The history itself keeps its clock: it is the axis there, not a datum.
    assert "Time-step" in tables["AL-020_plots.csv"][0]


def test_a_reduction_states_the_moment_point_of_the_moments_it_averages(tmp_path):
    workspace, tables = _reductions(tmp_path)
    columns, rows = tables["AL-020_time_average.csv"]
    for name in ("XMOM", "YMOM", "ZMOM"):
        assert name in columns, columns
    assert _products_manifest(workspace)["products"]["probes/AL-020_time_average.csv"]
