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

THE THIRD ANSWER IS WHAT MADE IT BUILDABLE. The steady polar has twenty-four
fixed coefficient columns in three axis systems. Nothing in this package knows
which plot label carries which of them, and a label invented here would not fail
loudly -- it would write `NA` down a whole column. Taking the names from the file
removes that possibility entirely rather than guarding against it.

ONE TABLE PER SIMULATION, one row per point, which is her choice of the three
layouts put to her: the steady polar is per GROUP because its source states loads
per family, and the plots history's columns are whatever the run defined.
"""

from __future__ import annotations

from pathlib import Path

from pyflightstream.post.products import (
    CONTEXT_COLUMNS,
    read_csv_table,
    unsteady_polar_file_name,
    write_unsteady_polar,
)


class _Point:
    def __init__(self, name: str) -> None:
        self.name = name


def _plots_file(path: Path, *, rows: int, first: float) -> Path:
    """One written PLOTS TABLE whose `CL` rises by one each step.

    THE WRITTEN TABLE AND NOT THE RAW EXPORT, which is what the polar reads: the
    reference-velocity scaling `write_plots_table` applies happens once, there,
    and a second reader of the raw export would perform it again or not at all.
    The table states its own clock in `Time-step`, so a window's first and last
    step mean what the file means.

    `CL` rising by one per step makes every average here checkable by hand: over
    steps 5 to 8 it is 6.5, and the LAST STEP is 8.
    """
    lines = ["Time-step,CL,CDi"]
    for step in range(1, rows + 1):
        value = first + step - 1
        lines.append(f"{step},{value:.5f},{value / 10:.5f}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_the_columns_are_the_names_the_export_prints(tmp_path):
    """HER DECISION, AND THE ONE THAT REMOVED THE ONLY WAY LEFT TO BE SILENTLY WRONG.

    The table carries `CL` and `CDi` because the file says `CL` and `CDi`. It
    does NOT carry `CDB`, `CLW`, `CMS25` or any other of the steady polar's
    twenty-four: those are a mapping the package would have had to invent.
    """
    written = write_unsteady_polar(
        tmp_path / "out.csv",
        points=[_Point("a")],
        plots={"a": _plots_file(tmp_path / "a.txt", rows=8, first=1.0)},
        window=(1, 8),
        conditions=[{"ALPHA": 2.0}],
        reference=None,
    )
    assert written is not None
    columns, rows = read_csv_table(written)
    assert "CL" in columns and "CDi" in columns, columns
    assert not {"CDB", "CLW", "CMS25"} & set(columns), (
        "the unsteady polar is carrying the steady polar's fixed coefficient names"
    )
    # ITEM 5 REACHES IT TOO: the condition block is in the row, whole and in order.
    # IT LED THE ROW UNTIL 0.24.0, WHEN THE REQUIREMENT CHANGED: the window the
    # average was taken over (`FIRST_STEP, LAST_STEP, STEPS`) now opens the row, so
    # the file says it is an average and over what. The block follows it.
    # THE POLAR FIRST since 0.27.0 (G16), then the window.
    assert list(columns[:4]) == ["POL", "FIRST_STEP", "LAST_STEP", "STEPS"], columns
    assert tuple(columns[4 : 4 + len(CONTEXT_COLUMNS)]) == tuple(CONTEXT_COLUMNS), columns
    assert rows[0]["ALPHA"] == "2.00000", rows[0]


def test_the_value_is_the_average_over_the_window_and_not_the_last_step(tmp_path):
    """THE WHOLE POINT OF THE ITEM, asserted on an arithmetic anyone can check.

    `CL` runs 1, 2, ... 8. Over steps 5 to 8 the average is 6.5 and the LAST
    STEP is 8. A table built from the native export would carry 8 here, and it
    would look exactly like this one.
    """
    written = write_unsteady_polar(
        tmp_path / "out.csv",
        points=[_Point("a")],
        plots={"a": _plots_file(tmp_path / "a.txt", rows=8, first=1.0)},
        window=(5, 8),
        conditions=[{"ALPHA": 0.0}],
        reference=None,
    )
    assert written is not None
    _, rows = read_csv_table(written)
    assert rows[0]["CL"] == "6.50000", (
        f"the mean of 5,6,7,8 is 6.5; the LAST STEP is 8: {rows[0]['CL']}"
    )


def test_one_row_per_point_in_the_order_given(tmp_path):
    """A sweep is a table of its points, and the row order is the sweep's."""
    written = write_unsteady_polar(
        tmp_path / "out.csv",
        points=[_Point("a"), _Point("b")],
        plots={
            "a": _plots_file(tmp_path / "a.txt", rows=4, first=1.0),
            "b": _plots_file(tmp_path / "b.txt", rows=4, first=10.0),
        },
        window=(1, 4),
        conditions=[{"ALPHA": -2.0}, {"ALPHA": 2.0}],
        reference=None,
    )
    assert written is not None
    _, rows = read_csv_table(written)
    assert [r["ALPHA"] for r in rows] == ["-2.00000", "2.00000"], rows
    assert [r["CL"] for r in rows] == ["2.50000", "11.50000"], rows


def test_a_point_with_no_plots_export_is_left_out_and_never_written_as_na(tmp_path):
    """A sweep is a table of what RAN, and an absent point is absent.

    Writing it as a row of `NA` would put a point in the table that produced
    nothing, and a reader counting rows would count it.
    """
    written = write_unsteady_polar(
        tmp_path / "out.csv",
        points=[_Point("a"), _Point("missing")],
        plots={"a": _plots_file(tmp_path / "a.txt", rows=4, first=1.0)},
        window=(1, 4),
        conditions=[{"ALPHA": 0.0}, {"ALPHA": 4.0}],
        reference=None,
    )
    assert written is not None
    _, rows = read_csv_table(written)
    assert len(rows) == 1, rows


def test_no_point_yields_a_row_and_nothing_is_written(tmp_path):
    """An unsteady simulation whose points exported no plots is an ordinary campaign.

    It costs this table and never the simulation's other products, so the
    writer returns None rather than raising.
    """
    assert (
        write_unsteady_polar(
            tmp_path / "out.csv",
            points=[_Point("a")],
            plots={},
            window=(1, 4),
            conditions=[{"ALPHA": 0.0}],
            reference=None,
        )
        is None
    )
    assert not (tmp_path / "out.csv").exists()


def test_the_file_name_carries_no_group():
    """It is per SIMULATION, which is the difference from the steady polar's name."""
    name = unsteady_polar_file_name("7001", name="a-sweep")
    # THE NAME CHANGED BECAUSE THE REQUIREMENT DID (0.24.0): it was
    # `7001_a-sweep_unsteady.csv`. `uns_avg` says what the file IS, and the `P` is the
    # prefix every per-point product carries. It still names no group.
    assert name == "P7001_a-sweep_uns_avg.csv", name
