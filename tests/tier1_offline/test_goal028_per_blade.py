"""`per_blade` is one row PER BLADE, each stating where that blade was (CR-04).

THE DEFECT. `probes/<point>_per_blade_<ALIAS>.csv` was ONE row with the time
average's shape under the per-blade name: a four-blade rotor's file carried one
blade's worth of nothing, and the record's `blade1_azimuth_deg`, written "because
the products stage needs it", was read by nobody. `per_blade_rows` had no caller.

THE DEFINITION (`docs/post-processing-definitions.md`, `per_blade`): ONE window
shared by every blade, one row per blade, each row carrying that blade's start and
end azimuth over that window.

WHAT A BLADE'S COLUMNS ARE. A plot is named `<parameter>_<group>`, and a group cut
per blade is named for the blade's family, so blade one's columns are the ones
ENDING in its family: `CL_MRP_Blade1`, `FX_LOCAL_Blade1`. The row carries them with
the family removed, `CL_MRP`, so two blades line up under one heading.

THE AZIMUTH is the sections table's: where the blade is AT a step,

    (blade1.azimuth_deg + k 360/blades + sense STEP 360/steps_per_revolution) mod 360

with `k` the blade's position in the rotor's own list and `sense` the sign of the
rotor's speed. Expected values below are that formula worked by hand.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent))

from pyflightstream.post.products import (  # noqa: E402
    NOT_APPLICABLE,
    ReferenceValues,
    read_csv_table,
    write_per_blade_table,
)
from pyflightstream.post.unsteady import TimestepSeries  # noqa: E402

REFERENCE = ReferenceValues(sref_m2=50.0, cref_m=2.526, bref_m=20.0)
STEPS = np.arange(1, 9)
#: NOT constant and NOT linear, so a mean over the wrong window, a last value or a
#: median each give another number. Over steps 5 to 8: 43.5 and 13.0.
FIELDS = {
    "CL_MRP_TOTAL": STEPS * 0.5,
    "CL_MRP_Blade1": STEPS.astype(float) ** 2,
    "CL_MRP_Blade2": STEPS * 2.0,
    "FX_LOCAL_Blade1": STEPS * 10.0,
    "FX_LOCAL_Blade2": STEPS * 100.0,
    # A probe column, as real plots carry: it ENDS in a digit and is no blade's.
    "VELOCITY_PROBE1": STEPS * 0.01,
}
ROTOR = {
    "families": ["Blade1", "Blade2"],
    "steps_per_revolution": 4.0,
    "blade1_azimuth_deg": 90.0,
    "rpm": -1200.0,
}


def _history(fields) -> TimestepSeries:
    return TimestepSeries(
        steps=STEPS,
        times_s=None,
        points=np.zeros((1, 3)),
        fields={
            name: np.asarray(values, dtype=float).reshape(-1, 1) for name, values in fields.items()
        },
        sources=(),
    )


def _series() -> TimestepSeries:
    return _history(FIELDS)


def _table(tmp_path, rotor=ROTOR, blades=2):
    path = write_per_blade_table(
        tmp_path / "P_per_blade_PUSHER.csv",
        _series(),
        tuple(FIELDS),
        window=(5, 8),
        rotor="PUSHER",
        blades=blades,
        facts=rotor,
        condition={"ALPHA": 0.0, "MACH": 0.2},
        reference=REFERENCE,
    )
    return read_csv_table(path)


def test_there_is_one_row_per_blade_over_the_one_shared_window(tmp_path):
    columns, rows = _table(tmp_path)
    assert [(r["BLADE"], r["FAMILY"]) for r in rows] == [("1", "Blade1"), ("2", "Blade2")]
    assert {(r["FIRST_STEP"], r["LAST_STEP"], r["STEPS"]) for r in rows} == {("5", "8", "4")}
    assert {r["ROTOR"] for r in rows} == {"PUSHER"} and {r["REDUCTION"] for r in rows} == {
        "per_blade"
    }


def test_a_row_holds_that_blades_own_columns_under_a_shared_heading(tmp_path):
    columns, rows = _table(tmp_path)
    assert "CL_MRP" in columns and "FX_LOCAL" in columns, columns
    assert "CL_MRP_Blade1" not in columns and "CL_MRP_TOTAL" not in columns, columns
    at = columns.index("ZMOM") + 1
    assert list(columns[at:]) == ["CL_MRP", "FX_LOCAL"], "a blade's columns END IN ITS FAMILY"
    assert float(rows[0]["CL_MRP"]) == pytest.approx(43.5)  # (25 + 36 + 49 + 64) / 4
    assert float(rows[1]["CL_MRP"]) == pytest.approx(13.0)  # 2 * (5 + 6 + 7 + 8) / 4
    assert float(rows[0]["FX_LOCAL"]) == pytest.approx(65.0)
    assert float(rows[1]["FX_LOCAL"]) == pytest.approx(650.0)


def test_each_row_says_where_its_blade_was_when_the_window_opened_and_closed(tmp_path):
    _columns, rows = _table(tmp_path)
    # 90 degrees a step, turning the NEGATIVE way, blade one's datum at 90:
    # step 5: 90 - 450 = -360 -> 0;   step 8: 90 - 720 = -630 -> 90.
    assert (float(rows[0]["AZIMUTH_START"]), float(rows[0]["AZIMUTH_END"])) == (0.0, 90.0)
    # Blade two is half a turn on: 180 and 270.
    assert (float(rows[1]["AZIMUTH_START"]), float(rows[1]["AZIMUTH_END"])) == (180.0, 270.0)


def test_a_rotor_whose_clock_the_record_does_not_state_still_gets_its_rows(tmp_path):
    """The averages need no clock; only the azimuths do, and they read `NA`, never zero."""
    _columns, rows = _table(tmp_path, rotor={"families": ["Blade1", "Blade2"]})
    assert len(rows) == 2 and float(rows[0]["CL_MRP"]) == pytest.approx(43.5)
    assert {r["AZIMUTH_START"] for r in rows} == {NOT_APPLICABLE}


def test_a_sector_carrying_one_blade_of_four_spaces_its_blades_by_the_whole_wheel(tmp_path):
    """The spacing is the ROTOR's blade count; the rows are the blades the mesh carries."""
    sector = dict(ROTOR, families=["Blade1", "Blade2"], blade1_azimuth_deg=0.0, rpm=1200.0)
    _columns, rows = _table(tmp_path, rotor=sector, blades=4)
    # Step 5 of 90 degrees a step is 450 -> 90; blade two is a QUARTER turn on: 180.
    assert [float(r["AZIMUTH_START"]) for r in rows] == [90.0, 180.0]


def test_plots_holding_no_column_of_any_blade_are_refused_by_name(tmp_path):
    from pyflightstream.post.products import ProductError

    series = _history({"CL_MRP_TOTAL": STEPS * 0.5})
    with pytest.raises(ProductError) as caught:
        write_per_blade_table(
            tmp_path / "P_per_blade_PUSHER.csv",
            series,
            ("CL_MRP_TOTAL",),
            window=(5, 8),
            rotor="PUSHER",
            blades=2,
            facts=ROTOR,
        )
    assert "Blade1" in str(caught.value) and "each" in str(caught.value)
