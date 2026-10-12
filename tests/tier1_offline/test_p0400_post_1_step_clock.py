"""P0400-ONECLOCK (PFS-2088.014): one reader of the plots table's Time-step clock.

The reductions, the probe table and the probe fields each read the clock with
their own fallback, so one non-monotonic clock gave a probe table whose STEP
disagreed with the steps the reductions used, and fields placed at steps no
other product names. Fed one non-monotonic clock, the three agree: the
reductions and the probe table on the ordinal, the fields by refusing.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from pyflightstream.post._tables import plots_table_series, read_csv_table
from pyflightstream.post.point_tables import write_unsteady_probes_table
from pyflightstream.post.probe_fields import write_recorded_probe_fields
from pyflightstream.script import Script, helpers

#: A clock that goes back: step 3 written before step 2.
_PLOTS = "POL,Time-step,VX1,VY1,VZ1\n1,3,11,3,5\n1,2,12,3,5\n"


@pytest.mark.parametrize((), [pytest.param(id="P0400-ONECLOCK")])
def test_p0400_oneclock_the_reductions_and_the_probe_table_agree(tmp_path):
    """P0400-ONECLOCK: the probe table's STEP is the step the reductions read, row for row."""
    plots = tmp_path / "plots.csv"
    plots.write_text(_PLOTS, encoding="utf-8")
    _columns, series = plots_table_series(plots)
    table = write_unsteady_probes_table(
        tmp_path / "probes.csv",
        plots,
        positions={1: (0.0, 0.0, 0.0, "REFERENCE")},
        parameters=["VX", "VY", "VZ"],
    )
    assert table is not None
    _names, rows = read_csv_table(table)
    assert [int(row["STEP"]) for row in rows] == [int(step) for step in series.steps] == [1, 2]


@pytest.mark.parametrize((), [pytest.param(id="P0400-ONECLOCK")])
def test_p0400_oneclock_the_fields_refuse_a_clock_the_others_read_as_ordinal(tmp_path):
    """P0400-ONECLOCK: a field is never placed on a step the other products do not name."""
    table = tmp_path / "probes.csv"
    table.write_text("PROBE,STEP,X,Y,Z,VX,VY,VZ\n1,3,0,0,0,11,3,5\n1,2,0,0,0,12,3,5\n")
    plots = tmp_path / "plots.csv"
    plots.write_text(_PLOTS, encoding="utf-8")
    record = SimpleNamespace(
        run_id="test",
        campaign=None,
        probe_field_layout=[
            dict(
                entry=1,
                probe_ids=[1],
                frame="REFERENCE",
                native_to_m=1,
                formats=["vtk"],
                reusable_inflow=False,
            )
        ],
        solver_setup=helpers.solver_settings(Script("26.124"), velocity=30).model_dump(mode="json"),
    )
    with pytest.raises(ValueError, match="strictly increasing"):
        write_recorded_probe_fields(table, record, tmp_path / "out", "P", step_source=plots)
    assert not (tmp_path / "out").exists()
