"""Tier 1: the clockings table states blade one's azimuth as the sections table does (0.31.0).

P0310-QS-POSITIONS-AZIMUTH. ``_qs_positions.csv`` wrote ``AZIMUTH`` as
``datum + clocking_deg`` unsigned, while the sections of the same wheel follow
the one home of a blade's azimuth,
``pyflightstream.post.axes.clocked_blade_azimuth_deg``:
``datum + sign(rpm) * theta_i``. For a left-hand wheel the two disagreed. The
clockings table now reads the same home, so both agree for either hand.
"""
# The evidence line of these requirements cites this module (docs/srs/functional-requirements.md):
# FR-182.

from __future__ import annotations

from pathlib import Path

import pytest

from pyflightstream.cases import qsteady as arithmetic
from pyflightstream.post import qsteady as post_qsteady
from pyflightstream.post.products import read_csv_table, rotor_shaft_loads
from tests.tier1_offline.test_goal035_qsteady_rotor import LOADS, REFERENCE, ROTOR, _case, _lines


def _wheel(tmp_path: Path, rpm_sign: int) -> tuple[arithmetic.QsteadyRecord, Path]:
    """A three-blade wheel at three clockings, as the builder records it, its exports on disk."""
    rotor = ROTOR.model_copy(update={"rpm_sign": rpm_sign})
    _, script = _lines(_case(rotor=rotor, PASSAGE_POSITIONS="3", ALPHA_POINT=5.0))
    folder = tmp_path / f"hand{rpm_sign:+d}"
    folder.mkdir()
    (folder / "DP_qsteady.json").write_text(str(script.pending_input_files["DP_qsteady.json"]))
    record = arithmetic.read_qsteady_record(folder / "DP.txt")
    for position in record.positions:
        (folder / position.loads).write_text(LOADS.format(c1="+0.1", c2="+0.2", c3="+0.3"))
    return record, folder


@pytest.mark.parametrize(
    ("rpm_sign", "expected"), [(1, [0.0, 40.0, 80.0]), (-1, [0.0, 320.0, 280.0])]
)
def test_the_clockings_table_turns_blade_one_the_way_the_sections_do(tmp_path, rpm_sign, expected):
    """theta_i = i * (360 / 3) / 3 = 40 i deg, turned in the sense of the rotor's speed."""
    # P0310-QS-POSITIONS-AZIMUTH
    record, folder = _wheel(tmp_path, rpm_sign)
    assert record.rpm * rpm_sign > 0.0
    clockings = post_qsteady.clockings_of(
        record, folder, reference=REFERENCE, density_kg_m3=1.2, shaft_loads=rotor_shaft_loads
    )
    assert not isinstance(clockings, str)
    assert [clocking.azimuth_deg for clocking in clockings] == pytest.approx(expected)
    # The sections table's reading of blade one at each clocking is the same number.
    sections = [
        post_qsteady.wheel_block_identity(record, ["Blade1"], clocking.index)[1]
        for clocking in clockings
    ]
    assert [clocking.azimuth_deg for clocking in clockings] == pytest.approx(sections)


def test_the_written_clockings_table_of_a_left_hand_wheel_states_the_signed_azimuth(tmp_path):
    """The AZIMUTH column of _qs_positions.csv, left hand: 0, 320 and 280 deg."""
    # P0310-QS-POSITIONS-AZIMUTH
    record, folder = _wheel(tmp_path, -1)
    clockings = post_qsteady.clockings_of(
        record, folder, reference=REFERENCE, density_kg_m3=1.2, shaft_loads=rotor_shaft_loads
    )
    assert not isinstance(clockings, str)
    point = post_qsteady.WheelPoint(
        pol="9001",
        condition={"ALPHA": 5.0},
        record=record,
        clockings=clockings,
        validity=post_qsteady.PointValidity({}),
    )
    written = post_qsteady.write_qsteady_tables(
        tmp_path / "pos.csv", tmp_path / "avg.csv", [point], reference=REFERENCE
    )
    assert written is not None
    _, rows = read_csv_table(tmp_path / "pos.csv")
    assert [float(row["AZIMUTH"]) for row in rows] == pytest.approx([0.0, 320.0, 280.0])
