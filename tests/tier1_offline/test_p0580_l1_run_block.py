"""PFS-2231 (0.58.0, lane L1): the canonical run block every csv of the post opens with.

The design of the 0.58.0 post outputs, section 3: the columns in their order,
NA for a column that does not apply, rotor columns by id with no underscore,
none for a reference without rotors, the window NA on a steady row, and
``J_CLOCK`` and ``RPM_CLOCK`` defined on ``docs/definitions/the-run-block.md``.
The column list is compared with that page, as the flight-condition columns
were compared with theirs.
"""

from __future__ import annotations

import math
import re
from pathlib import Path

import pytest

from pyflightstream._errors import ProductError
from pyflightstream.post._run_block import (
    RUN_BLOCK_SPEC,
    RotorRunValues,
    run_block_columns,
    run_block_row,
)

PAGE = Path(__file__).resolve().parents[2] / "docs" / "definitions" / "the-run-block.md"
_ROW = re.compile(r'^\| <a id="([^"]+)"></a>`([^`]+)` \| ([^|]+) \|', re.MULTILINE)

#: Section 3 of the design, in order, read from the page the owner approved.
DESIGN_ORDER = (
    "POL",
    "POINT_ID",
    "POINT",
    "<IDENTIFIER>",
    "RUN_TYPE",
    "ALPHA",
    "BETA",
    "MACH",
    "RE",
    "VINF",
    "VREF",
    "RPM<id>",
    "J<id>",
    "MTIP<id>",
    "MHEL<id>",
    "J",
    "J_CLOCK",
    "RPM_CLOCK",
    "THRUST",
    "ALT",
    "RHO",
    "TEMP",
    "MU",
    "SREF",
    "CREF",
    "BREF",
    "XMOM",
    "YMOM",
    "ZMOM",
    "D<id>",
    "ADISC<id>",
    "PITCH<id>",
    "TOE<id>",
    "FIRST_STEP",
    "LAST_STEP",
    "STEPS",
    "WINDOW_REVS",
    "WINDOW_PASSAGES",
)


def test_the_block_is_the_designed_order():
    assert tuple(spec.name for spec in RUN_BLOCK_SPEC) == DESIGN_ORDER


def test_the_definitions_page_states_the_same_columns_units_and_anchors():
    rows = _ROW.findall(PAGE.read_text(encoding="utf-8"))
    assert [name for _anchor, name, _unit in rows] == [spec.name for spec in RUN_BLOCK_SPEC]
    assert [unit.strip() for _a, _n, unit in rows] == [spec.unit for spec in RUN_BLOCK_SPEC]
    assert [anchor for anchor, _n, _u in rows] == [spec.anchor for spec in RUN_BLOCK_SPEC]


def test_the_page_defines_the_clock_columns():
    text = PAGE.read_text(encoding="utf-8")
    assert '<a id="the-clock-rotor"></a>' in text
    section = text.split('<a id="the-clock-rotor"></a>', 1)[1]
    assert "J_CLOCK = VINF / (|n| D)" in section and "RPM_CLOCK" in section


def test_a_reference_without_rotors_writes_no_rotor_column():
    columns = run_block_columns()
    assert not [c for c in columns if re.fullmatch(r"(RPM|J|MTIP|MHEL|D|ADISC|PITCH|TOE)\d+", c)]
    assert columns[:3] == ("POL", "POINT_ID", "POINT") and columns[3] == "RUN_TYPE"
    assert columns[-1] == "WINDOW_PASSAGES"


def test_rotor_columns_are_by_id_ascending_and_grouped_per_rotor():
    columns = run_block_columns(("FLAP", "TESTE"), (1, 0))
    assert columns[3:5] == ("FLAP", "TESTE")
    start = columns.index("VREF") + 1
    assert columns[start : columns.index("J")] == (
        "RPM0",
        "J0",
        "MTIP0",
        "MHEL0",
        "RPM1",
        "J1",
        "MTIP1",
        "MHEL1",
    )
    start = columns.index("ZMOM") + 1
    assert columns[start : columns.index("FIRST_STEP")] == (
        "D0",
        "ADISC0",
        "PITCH0",
        "TOE0",
        "D1",
        "ADISC1",
        "PITCH1",
        "TOE1",
    )
    assert not [c for c in columns if "_" in c and c.rstrip("0123456789") != c]


def test_an_identifier_that_spells_a_block_column_is_refused():
    with pytest.raises(ProductError, match="VINF"):
        run_block_columns(("VINF",))


def _rotor(rotor_id=0, rpm=1200.0):
    return RotorRunValues(
        rotor_id=rotor_id, diameter_m=0.5, pitch_deg=5.0, toe_deg=0.0, rpm=rpm, mtip=0.3, mhel=0.31
    )


def test_a_row_carries_every_column_and_na_where_nothing_applies():
    row = run_block_row(
        pol="P0001",
        point_id=2,
        point="AL+002",
        run_type="unsteady_rotor",
        condition={"vinf": 15.0, "ALPHA": 2.0, "MU": 1.8e-5, "FIRST_STEP": 361, "RHO": math.nan},
        identifiers={"FLAP": 10},
        rotors=[_rotor()],
    )
    assert tuple(row) == run_block_columns(("FLAP",), (0,))
    assert row["POL"] == "P0001" and row["POINT_ID"] == 2 and row["FLAP"] == 10
    assert row["VINF"] == 15.0 and row["ALPHA"] == 2.0
    assert row["MU"] == "1.80000e-05"
    assert row["RHO"] == "NA" and row["THRUST"] == "NA" and row["BETA"] == "NA"
    assert row["FIRST_STEP"] == 361
    assert row["J0"] == pytest.approx(15.0 / (20.0 * 0.5))
    assert row["ADISC0"] == pytest.approx(math.pi * 0.25 / 4.0)
    assert row["RPM0"] == 1200.0 and row["PITCH0"] == 5.0 and row["MTIP0"] == 0.3


def test_a_steady_row_states_no_window():
    row = run_block_row(
        pol="P0001",
        point_id=1,
        point="AL+000",
        run_type="steady",
        condition={"FIRST_STEP": 3, "LAST_STEP": 9, "STEPS": 7, "WINDOW_REVS": 1, "VINF": 40.0},
    )
    for name in ("FIRST_STEP", "LAST_STEP", "STEPS", "WINDOW_REVS", "WINDOW_PASSAGES"):
        assert row[name] == "NA"


def test_a_rotor_the_row_does_not_turn_reads_na_speed_and_ratio():
    row = run_block_row(
        pol="P0002",
        point_id=1,
        point="AL+000",
        run_type="steady",
        condition={"VINF": 40.0},
        rotors=[_rotor(rpm=None)],
    )
    assert row["RPM0"] == "NA" and row["J0"] == "NA" and row["D0"] == 0.5


@pytest.mark.parametrize("bad", [{"run_type": "transient"}, {"point_id": 0}, {"point_id": True}])
def test_an_unknown_run_type_or_point_id_is_refused(bad):
    arguments = {"pol": "P1", "point_id": 1, "point": "A", "run_type": "steady", "condition": {}}
    arguments.update(bad)
    with pytest.raises(ProductError):
        run_block_row(**arguments)
