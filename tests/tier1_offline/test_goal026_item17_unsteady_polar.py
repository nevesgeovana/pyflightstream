"""Tier 1, v0.23.0 item 17: the unsteady POLAR comes from the PLOTS.

THE OWNER'S ANSWERS, 2026-09-18, and the item rests on the first of them:

    "E o ultimo passo de tempo."            (the native loads export)
    "A POLAR do unsteady sempre vai vir do unsteady plots, alem de ter a media
     temporal"
    "despega daqueles nomes da polar, escreve o nome das variaveis como elas
     vieram no unsteady plots"

THE FIRST ANSWER IS WHAT MAKES THE ITEM NECESSARY. The native coefficient export
states the LAST TIME STEP, which on an oscillating rotor is one instant of a
cycle. A polar read from it is a polar of an instant, and it looks exactly like
a polar of an average.

SINCE 0.58.0 (design of the post outputs, D14 and 2.2) the unsteady polar is no
file of its own: the window average of every family and group is a row of the
FAM files and the group files, under the names of a steady polar, and the run
block of every row states the window. The cases below are the item's, read from
those files, over plots whose six components of every family and of the total
are the ramp the old table's `CL` was: the value of `FX` of family B rises by
one each step, so every average is checkable by hand.
"""

from __future__ import annotations

import pytest

from pyflightstream.post.products import read_csv_table
from tests.tier1_offline.test_goal028_uns_axes import AXES, posted_unsteady, skipped_by_the_post

SIX = ("FX", "FY", "FZ", "MX", "MY", "MZ")


def _ramp(rows: int, *, first: float, steps: list[int] | None = None) -> dict[str, list[float]]:
    """One plots history whose FX of family B rises by one each step, from ``first``.

    Over steps 5 to 8 of a ramp from 1 the average is 6.5, and the LAST STEP is 8. The
    other five components and family W are zero; the total is the sum, as a run plots it.
    """
    clock = steps if steps is not None else list(range(1, rows + 1))
    ramp = [first + step - 1 for step in clock]
    history: dict[str, list[float]] = {"steps": clock}
    for group in ("W", "B", "TOTAL"):
        for part in SIX:
            moving = part == "FX" and group != "W"
            history[f"{part}_MRP_{group}"] = list(ramp) if moving else [0.0] * len(clock)
    return history


def test_p0430_polar_refuses_a_gap_in_per_step_history(tmp_path):
    history = _ramp(0, first=1.0, steps=[1, 3])
    workspace, polars, _said = posted_unsteady(tmp_path, [history], window=(1, 3))
    notes = " ".join(skipped_by_the_post(workspace).values())
    assert "gap" in notes or "sample" in notes, notes
    assert not list(polars.glob("*P6002*")), sorted(p.name for p in polars.iterdir())


def test_the_row_is_the_polars_and_names_the_window_not_the_export_names(tmp_path):
    """HER DECISION, AND THE ONE THAT REMOVED THE ONLY WAY LEFT TO BE SILENTLY WRONG.

    The names are the polar's own: since 0.58.0 a unsteady row is a row of the ACOEF file of
    its group, the axis coefficients carry the bare names of a steady polar, and none of the
    plots export's variable names (`FX_MRP_TOTAL`) is a column. The row opens with its
    polar and its point, the run block follows, and the window the average was taken over
    is in it: the file says it is an average and over what.
    """
    _workspace, polars, _said = posted_unsteady(
        tmp_path, [_ramp(8, first=1.0)], window=(1, 8), alpha=2.0
    )
    columns, rows = read_csv_table(polars / "P6002-TOTAL-ACOEF.csv")
    assert list(columns[:3]) == ["POL", "POINT_ID", "POINT"], columns
    first = columns.index("FIRST_STEP")
    assert list(columns[first : first + 3]) == ["FIRST_STEP", "LAST_STEP", "STEPS"], columns
    assert set(AXES) <= set(columns), columns
    assert not [name for name in columns if name.startswith(("FX_", "FZ_", "CL_"))], columns
    assert rows[0]["ALPHA"] == "2.00000", rows[0]
    assert (rows[0]["FIRST_STEP"], rows[0]["LAST_STEP"], rows[0]["STEPS"]) == ("1", "8", "8")


def test_the_value_is_the_average_over_the_window_and_not_the_last_step(tmp_path):
    """THE WHOLE POINT OF THE ITEM, asserted on an arithmetic anyone can check.

    `FX` runs 1, 2, ... 8. Over steps 5 to 8 the average is 6.5 and the LAST
    STEP is 8. A table built from the native export would carry 8 here, and it
    would look exactly like this one.
    """
    _workspace, polars, _said = posted_unsteady(tmp_path, [_ramp(8, first=1.0)], window=(5, 8))
    _, family = read_csv_table(polars / "FAM-DIM-P6002.csv")
    (blade,) = [row for row in family if row["FAMILY"] == "B"]
    assert float(blade["FX_MRP"]) == pytest.approx(6.5), (
        f"the mean of 5,6,7,8 is 6.5; the LAST STEP is 8: {blade['FX_MRP']}"
    )
    _, total = read_csv_table(polars / "P6002-TOTAL-DIM.csv")
    assert float(total[0]["FX_MRP"]) == pytest.approx(6.5), total[0]


def test_one_row_per_point_in_the_order_given(tmp_path):
    """A sweep is a table of its points, and the row order is the sweep's."""
    _workspace, polars, _said = posted_unsteady(
        tmp_path, [_ramp(4, first=1.0), _ramp(4, first=10.0)], window=(1, 4)
    )
    _, rows = read_csv_table(polars / "P6002-TOTAL-DIM.csv")
    assert [row["POINT_ID"] for row in rows] == ["1", "2"], rows
    assert [row["POINT"][-5:] for row in rows] == ["J+170", "J+171"], rows
    assert [float(row["FX_MRP"]) for row in rows] == pytest.approx([2.5, 11.5]), rows


def test_a_point_with_no_plots_export_is_left_out_and_never_written_as_na(tmp_path):
    """A sweep is a table of what RAN, and an absent point is absent.

    Writing it as a row of `NA` would put a point in the table that produced
    nothing, and a reader counting rows would count it.
    """
    workspace, polars, _said = posted_unsteady(tmp_path, [_ramp(4, first=1.0), None], window=(1, 4))
    for name in ("FAM-DIM-P6002.csv", "P6002-TOTAL-DIM.csv", "P6002-TOTAL-ACOEF.csv"):
        _, rows = read_csv_table(polars / name)
        assert {row["POINT_ID"] for row in rows} == {"1"}, (name, rows)
    assert "no plots table" in " ".join(skipped_by_the_post(workspace).values())


def test_no_point_yields_a_row_and_nothing_is_written(tmp_path):
    """An unsteady simulation whose points exported no plots is an ordinary campaign.

    It costs these files and never the simulation's other products, so the post
    carries on and writes none of them rather than raising.
    """
    workspace, polars, _said = posted_unsteady(tmp_path, [None], window=(1, 4))
    assert not list(polars.glob("*P6002*")), sorted(p.name for p in polars.iterdir())
    assert (polars / "FAM-DIM-P6001.csv").is_file(), "the steady simulation is unaffected"
    assert "no plots table" in " ".join(skipped_by_the_post(workspace).values())
