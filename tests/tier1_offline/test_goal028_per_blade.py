"""Every blade is one family row of the polar files, over ONE shared window (CR-04).

THE DEFECT. `probes/<point>_per_blade_<ALIAS>.csv` was ONE row with the time
average's shape under the per-blade name: a four-blade rotor's file carried one
blade's worth of nothing, and the record's `blade1_azimuth_deg`, written "because
the products stage needs it", was read by nobody. the per-blade writer had no caller.

THE DEFINITION (`docs/post-processing-definitions.md`, `per_blade`): ONE window
shared by every blade, one row per blade, each row carrying that blade's start and
end azimuth over that window. 0.58.0 retired the `per_blade` table (design D20): a blade
is a family row of `polars/FAM-DIM-P<POL>.csv` and `polars/FAM-RCOEF-P<POL>.csv`, and the
window is in the run block that opens every row.

WHAT A BLADE'S ROW IS. A plot is named `<parameter>_<group>`, and a group cut per blade
is named for the blade's family, so blade one's columns are the ones ENDING in its
family: `FX_MRP_Blade1`. The family row carries them with the family removed, `FX_MRP`,
so two blades line up under one heading. A column the plots hold that is no blade's
(the total, a probe) is no row of the family files.

THE AZIMUTH is the sections table's: where the blade is AT a step,

    (blade1.azimuth_deg + k 360/blades + sense STEP 360/steps_per_revolution) mod 360

with `k` the blade's position in the rotor's own list and `sense` the sign of the
rotor's speed. Expected values below are that formula worked by hand. The design names no
home for the azimuth columns since D20 retired the table that held them: those cases look
for `AZIMUTH_START` and `AZIMUTH_END` in the blade's FAM-RCOEF row and are left failing
until it does.
"""

from __future__ import annotations

import numpy as np
import pytest

from pyflightstream.post.products import NOT_APPLICABLE, read_csv_table
from tests.tier1_offline.test_goal026_item08_per_blade import _rows, posted_blades

STEPS = np.arange(1, 9)
#: NOT constant and NOT linear, so a mean over the wrong window, a last value or a
#: median each give another number. Over steps 5 to 8: 43.5 and 13.0.
HISTORY = {
    "Blade1": {"FX": list(STEPS.astype(float) ** 2), "FZ": list(STEPS * 10.0)},
    "Blade2": {"FX": list(STEPS * 2.0), "FZ": list(STEPS * 100.0)},
}
#: A probe column, as real plots carry: it ENDS in a digit and is no blade's.
PROBE = {"VELOCITY_PROBE1": list(STEPS * 0.01)}


def _table(tmp_path, **kwargs):
    kwargs.setdefault("revolutions", 1.0)
    kwargs.setdefault("steps_per_revolution", 4.0)
    return posted_blades(tmp_path, HISTORY, extra_columns=PROBE, **kwargs)


def test_there_is_one_row_per_blade_over_the_one_shared_window(tmp_path):
    polars, _said, _count = _table(tmp_path)
    rows = _rows(polars / "FAM-RCOEF-P6002.csv")
    assert [(r["FAMILY"], r["ROTOR_ID"]) for r in rows] == [("Blade1", "0"), ("Blade2", "0")]
    dim = _rows(polars / "FAM-DIM-P6002.csv")
    assert {(r["FIRST_STEP"], r["LAST_STEP"], r["STEPS"]) for r in dim} == {("5", "8", "4")}
    assert {r["RUN_TYPE"] for r in dim} == {"unsteady_rotor"}
    assert not list(polars.glob("*per_blade*")), sorted(p.name for p in polars.iterdir())


def test_a_row_holds_that_blades_own_columns_under_a_shared_heading(tmp_path):
    polars, _said, _count = _table(tmp_path)
    columns, rows = read_csv_table(polars / "FAM-DIM-P6002.csv")
    assert "FX_MRP" in columns and "FZ_MRP" in columns, columns
    assert "FX_MRP_Blade1" not in columns and "FX_MRP_TOTAL" not in columns, columns
    assert "VELOCITY_PROBE1" not in columns, "a plot that is no blade's is no column of a blade"
    assert [r["FAMILY"] for r in rows] == ["Blade1", "Blade2"], "the total is no blade's row"
    assert float(rows[0]["FX_MRP"]) == pytest.approx(43.5)  # (25 + 36 + 49 + 64) / 4
    assert float(rows[1]["FX_MRP"]) == pytest.approx(13.0)  # 2 * (5 + 6 + 7 + 8) / 4
    assert float(rows[0]["FZ_MRP"]) == pytest.approx(65.0)
    assert float(rows[1]["FZ_MRP"]) == pytest.approx(650.0)


def test_each_row_says_where_its_blade_was_when_the_window_opened_and_closed(tmp_path):
    """GAP (see the module docstring): the azimuth columns have no home in the 0.58.0 files."""
    polars, _said, _count = _table(tmp_path, rpm=-1200.0, azimuth_deg=90.0)
    rows = _rows(polars / "FAM-RCOEF-P6002.csv")
    # 90 degrees a step, turning the NEGATIVE way, blade one's datum at 90:
    # step 5: 90 - 450 = -360 -> 0;   step 8: 90 - 720 = -630 -> 90.
    assert (float(rows[0]["AZIMUTH_START"]), float(rows[0]["AZIMUTH_END"])) == (0.0, 90.0)
    # Blade two is half a turn on: 180 and 270.
    assert (float(rows[1]["AZIMUTH_START"]), float(rows[1]["AZIMUTH_END"])) == (180.0, 270.0)


def test_a_rotor_whose_clock_the_record_does_not_state_still_gets_its_rows(tmp_path):
    """The averages need no speed; only the azimuths do, and they read `NA`, never zero.

    GAP on its second half (see the module docstring): the first half, the rows and their
    averages, holds in the family files; the azimuth columns have no home there.
    """
    polars, _said, _count = _table(tmp_path, rpm=None)
    rows = _rows(polars / "FAM-DIM-P6002.csv")
    assert len(rows) == 2 and float(rows[0]["FX_MRP"]) == pytest.approx(43.5)
    assert {r["AZIMUTH_START"] for r in _rows(polars / "FAM-RCOEF-P6002.csv")} == {NOT_APPLICABLE}


def test_a_sector_carrying_two_blades_of_four_spaces_its_blades_by_the_whole_wheel(tmp_path):
    """The spacing is the ROTOR's blade count; the rows are the blades the mesh carries.

    GAP (see the module docstring): the azimuth columns have no home in the 0.58.0 files.
    """
    polars, _said, _count = _table(tmp_path, blades=4, rpm=1200.0)
    rows = _rows(polars / "FAM-RCOEF-P6002.csv")
    # Step 5 of 90 degrees a step is 450 -> 90; blade two is a QUARTER turn on: 180.
    assert [float(r["AZIMUTH_START"]) for r in rows] == [90.0, 180.0]


def test_plots_holding_no_column_of_any_blade_say_so_by_name(tmp_path):
    """The plots hold the total only: the blades' rows are NA and the warning names their plots.

    It was a refusal of the `per_blade` table naming `Blade1` and `each`; the family rows are
    still written, as `NA`, and the one warning names every plot the history lacks.
    """
    polars, said, _count = _table(tmp_path, family_plots=False)
    for row in _rows(polars / "FAM-DIM-P6002.csv"):
        assert row["FX_MRP"] == NOT_APPLICABLE, row
    (warning,) = [text for text in said if "MRP_Blade1" in text and "MRP_Blade2" in text]
    assert NOT_APPLICABLE in warning, warning
