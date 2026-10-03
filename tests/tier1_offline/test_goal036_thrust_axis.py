"""Tier 1: a wheel's thrust and torque shares are taken along the rotor's axis (0.31.0).

P0310-THRUST-AXIS. The validity columns ``THRUST_PCT_K_GT_0_1`` and
``TORQUE_PCT_K_GT_0_1`` read the sectional loads export's ``Fx`` and ``Fz``,
which are in the axes of the frame the distribution was cut in. Each
station's force is projected on the rotor's axis (the record's
``axis_vector`` stated in that frame) before the shares, and the torque is the
moment of the in-plane component about the axis. A share whose total has no
sign reads ``NA`` and the post says so in its log.

Every blade here is cut in a frame whose axes are NOT the export's reading of
the shaft: a rotor turning about z cut in its blade frame's XZ plane, whose
``Fx`` lies in the disc, and a tilted rotor cut in the geometry's frame.
"""

from __future__ import annotations

import math
from pathlib import Path
from types import SimpleNamespace

import pytest

from pyflightstream._errors import PyflightstreamWarning
from pyflightstream.cases import qsteady as arithmetic
from pyflightstream.post import qsteady as post_qsteady
from pyflightstream.post.axes import section_station_shaft_loads

HEADER = "POL,STEP,FAMILY,PLANE,ROTOR,AZIMUTH,Offset,Chord,X_QC,Z_QC,Fx,Fz,Moment"
#: Four stations of blade one: r, chord. At 1200 rev/min and 30 m/s the first
#: three are above k = 0.1 and the fourth, of a 0.05 m chord, is below it.
STATIONS = ((0.25, 0.2), (0.5, 0.2), (0.75, 0.2), (0.9, 0.05))
#: The strip each station stands for, half-way to its neighbours.
STRIPS = (0.125, 0.25, 0.2, 0.075)
HOT = (True, True, True, False)


def _record(*, letter: str, axis: tuple[float, float, float]) -> arithmetic.QsteadyRecord:
    return arithmetic.QsteadyRecord(
        case="wheel",
        rotor_alias="PROP",
        blades=3,
        rpm=1200.0,
        shaft_frame_axis=letter,
        hub_m=(0.0, 0.0, 0.0),
        axis_vector=axis,
        diameter_m=2.0,
        families_general=(),
        families_blades=("Blade1", "Blade2", "Blade3"),
        blade1_azimuth_deg=0.0,
        positions=(arithmetic.QsteadyClocking(0, 0.0, 0.0, "DP.txt"),),
        validity=None,
    )


def _table(path: Path, forces: tuple[tuple[float, float], ...], *, plane: str = "XZ") -> Path:
    rows = [
        f"9001,60,Blade1,{plane},PROP,NA,{r},{c},0,0,{fx},{fz},0"
        for (r, c), (fx, fz) in zip(STATIONS, forces, strict=True)
    ]
    path.write_text("\n".join([HEADER, *rows]) + "\n", encoding="utf-8")
    return path


def _layout(frame: str, *, plane: str = "XZ") -> list[dict[str, object]]:
    return [{"families": ["Blade1"], "plane": plane, "frame": frame, "count": 4}]


def _share(values: list[float]) -> float:
    return 100.0 * sum(v for v, hot in zip(values, HOT, strict=True) if hot) / sum(values)


@pytest.mark.requirement("FR-191")
def test_a_rotor_turning_about_z_takes_its_thrust_from_fz_in_its_blade_frame(tmp_path):
    """The blade frame's z is the shaft, so the export's Fz is the thrust and Fx is in the disc.

    Fz 10, 20, 30, 40 N/m over strips 0.125, 0.25, 0.2, 0.075 m: 12.25 of
    15.25 above k = 0.1, 80.33 %. The torque is (r e_y x F) . e_z = -r Fx:
    Fx 1, 1, 1, 50 N/m give -0.03125, -0.125, -0.15, -3.375, 8.32 % above.
    Read as before (Fx the thrust) the thrust share would be 13.29 %.
    """
    # P0310-THRUST-AXIS
    forces = ((1.0, 10.0), (1.0, 20.0), (1.0, 30.0), (50.0, 40.0))
    table = _table(tmp_path / "s.csv", forces)
    validity = post_qsteady.add_reduced_frequency_to_sections(
        table,
        _record(letter="Z", axis=(0.0, 0.0, 1.0)),
        velocity_m_per_s=30.0,
        layout=_layout("PROP_RMRP1"),
    )
    assert validity is not None and validity.notes == ()
    thrust = [fz * w for (_fx, fz), w in zip(forces, STRIPS, strict=True)]
    torque = [-r * fx * w for (r, _c), (fx, _fz), w in zip(STATIONS, forces, STRIPS, strict=True)]
    assert validity.values["THRUST_PCT_K_GT_0_1"] == pytest.approx(_share(thrust))
    assert validity.values["THRUST_PCT_K_GT_0_1"] == pytest.approx(100.0 * 12.25 / 15.25)
    assert validity.values["TORQUE_PCT_K_GT_0_1"] == pytest.approx(_share(torque))
    old = [fx * w for (fx, _fz), w in zip(forces, STRIPS, strict=True)]
    assert abs(validity.values["THRUST_PCT_K_GT_0_1"] - _share(old)) > 50.0


def test_a_clocking_s_copy_of_a_blade_frame_has_the_same_shaft(tmp_path):
    """``PROP_RMRP1_QS02`` is the blade frame turned about the shaft: the shaft stays its z."""
    # P0310-THRUST-AXIS
    record = _record(letter="Z", axis=(0.0, 0.0, 1.0))
    assert post_qsteady.shaft_in_section_frame(record, "PROP_RMRP1_QS02") == (0.0, 0.0, 1.0)
    assert post_qsteady.shaft_in_section_frame(record, "prop_smrp") == (0.0, 0.0, 1.0)
    assert post_qsteady.shaft_in_section_frame(record, "OTHER_RMRP1") is None
    assert post_qsteady.shaft_in_section_frame(record, "PROP_RMRPX") is None


def test_a_tilted_rotor_cut_in_the_geometry_frame_projects_on_its_axis_vector(tmp_path):
    """Axis (cos 20, 0, sin 20) deg in MRP; a cut in XZ along y: F = (Fx, 0, Fz).

    Thrust per span F . a = Fx cos 20 + Fz sin 20; torque per span
    (r e_y x F) . a = r (Fz cos 20 - Fx sin 20).
    """
    # P0310-THRUST-AXIS
    tilt = math.radians(20.0)
    axis = (math.cos(tilt), 0.0, math.sin(tilt))
    forces = ((10.0, 5.0), (20.0, 12.0), (30.0, 20.0), (40.0, 30.0))
    table = _table(tmp_path / "s.csv", forces)
    validity = post_qsteady.add_reduced_frequency_to_sections(
        table, _record(letter="Z", axis=axis), velocity_m_per_s=30.0, layout=_layout("MRP")
    )
    assert validity is not None and validity.notes == ()
    thrust = [
        (fx * math.cos(tilt) + fz * math.sin(tilt)) * w
        for (fx, fz), w in zip(forces, STRIPS, strict=True)
    ]
    torque = [
        r * (fz * math.cos(tilt) - fx * math.sin(tilt)) * w
        for (r, _c), (fx, fz), w in zip(STATIONS, forces, STRIPS, strict=True)
    ]
    assert validity.values["THRUST_PCT_K_GT_0_1"] == pytest.approx(_share(thrust))
    assert validity.values["TORQUE_PCT_K_GT_0_1"] == pytest.approx(_share(torque))


def test_the_projection_is_the_one_in_post_axes():
    """The station's axial force and torque, by hand, for a shaft with every component."""
    # P0310-THRUST-AXIS
    a = (1.0 / 3.0, 2.0 / 3.0, 2.0 / 3.0)
    axial, torque = section_station_shaft_loads(4.0, -2.0, 0.5, plane="xz", shaft=a)
    # F = (4, 0, -2), r = (0, 0.5, 0): r x F = (-1, 0, -2).
    assert axial == pytest.approx(4.0 / 3.0 - 4.0 / 3.0)
    assert torque == pytest.approx(-1.0 / 3.0 - 4.0 / 3.0)
    # XY, measured on 26.124 at the 0.31.0 short confirmation: F = (4, -2, 0),
    # r = (0, 0, 0.5): r x F = (1, 2, 0).
    axial, torque = section_station_shaft_loads(4.0, -2.0, 0.5, plane="XY", shaft=a)
    assert axial == pytest.approx(4.0 / 3.0 - 4.0 / 3.0)
    assert torque == pytest.approx(1.0 / 3.0 + 4.0 / 3.0)
    assert section_station_shaft_loads(4.0, -2.0, 0.5, plane="YZ", shaft=a) is None
    assert section_station_shaft_loads(4.0, -2.0, 0.5, plane="XZ", shaft=(0, 0, 0)) is None


def test_a_frame_or_plane_the_post_cannot_read_leaves_both_shares_na_and_says_why(tmp_path):
    """A setup's own frame, a plane other than XZ, or a block the layout does not name."""
    # P0310-THRUST-AXIS
    forces = ((10.0, 1.0),) * 4
    record = _record(letter="X", axis=(1.0, 0.0, 0.0))
    cases = (
        ("XZ", _layout("SETUP_FRAME"), "the axes of frame SETUP_FRAME are not known"),
        ("YZ", _layout("PROP_RMRP1", plane="YZ"), "a cut in plane YZ are not read"),
        ("XZ", _layout("PROP_RMRP1", plane="XY"), "names no one frame for block Blade1 XZ"),
    )
    for at, (plane, layout, said) in enumerate(cases):
        table = _table(tmp_path / f"s{at}.csv", forces, plane=plane)
        validity = post_qsteady.add_reduced_frequency_to_sections(
            table, record, velocity_m_per_s=30.0, layout=layout
        )
        assert validity is not None
        assert validity.values["THRUST_PCT_K_GT_0_1"] is None
        assert validity.values["TORQUE_PCT_K_GT_0_1"] is None
        assert validity.values["K_1P_MAX"] is not None
        (note,) = validity.notes
        assert said in note and "read NA" in note


def test_a_total_with_no_sign_is_na_and_said(tmp_path):
    """Stations of opposite sign put the thrust share at 1225 %; a zero total has no share.

    Thrust per strip 1.25, 5, 6 above k = 0.1 and -11.25 below: total 1, share
    1225 %, outside 0 to 100. No station carries an in-plane force, so the
    torque sums to zero.
    """
    # P0310-THRUST-AXIS
    forces = ((10.0, 0.0), (20.0, 0.0), (30.0, 0.0), (-150.0, 0.0))
    table = _table(tmp_path / "s.csv", forces)
    validity = post_qsteady.add_reduced_frequency_to_sections(
        table,
        _record(letter="X", axis=(1.0, 0.0, 0.0)),
        velocity_m_per_s=30.0,
        layout=_layout("PROP_RMRP1"),
    )
    assert validity is not None
    assert validity.values["THRUST_PCT_K_GT_0_1"] is None
    assert validity.values["TORQUE_PCT_K_GT_0_1"] is None
    thrust_note, torque_note = validity.notes
    assert "THRUST_PCT_K_GT_0_1 reads NA" in thrust_note and "1225 per cent" in thrust_note
    assert "TORQUE_PCT_K_GT_0_1 reads NA" in torque_note and "is zero" in torque_note


def test_the_post_says_a_share_it_cannot_take_in_its_log(tmp_path):
    """The product stage turns each note into a WARNING line naming the point (post.log)."""
    # P0310-THRUST-AXIS
    from pyflightstream.post._rotor_products import _qsteady_sections

    record = _record(letter="X", axis=(1.0, 0.0, 0.0))
    (tmp_path / "DP_qsteady.json").write_text(record.to_text(), encoding="utf-8")
    table = _table(tmp_path / "DP_sections.csv", ((10.0, 1.0),) * 4)
    point = SimpleNamespace(
        name="DP",
        loads_path=tmp_path / "DP.txt",
        loads=SimpleNamespace(freestream_velocity_m_s=30.0),
    )
    run = SimpleNamespace(recipe="qsteady_rotor", sections_layout=_layout("SETUP_FRAME"))
    skipped: dict[str, str] = {}
    with pytest.warns(PyflightstreamWarning) as said:
        validity = _qsteady_sections(table, point, run, skipped, lambda path, text: None)
    assert validity["DP"].values["THRUST_PCT_K_GT_0_1"] is None
    lines = [str(warning.message) for warning in said]
    assert any(
        line.startswith("point=DP product=sections: THRUST_PCT_K_GT_0_1 and TORQUE_PCT")
        and "SETUP_FRAME" in line
        for line in lines
    ), lines


def test_a_station_whose_force_or_offset_is_na_leaves_both_shares_na_naming_it(tmp_path):
    """Invariant 8: an NA is never a zero load, so a gap costs both shares, said.

    Read as zero, an NA Fx at the second station would give a thrust share of
    the other three alone, a number the table does not support. A station
    whose Offset is NA has no reduced frequency, and still costs the shares.
    """
    # P0310-THRUST-AXIS
    forces = ((10.0, 1.0), (20.0, 2.0), (30.0, 3.0), (40.0, 4.0))
    record = _record(letter="X", axis=(1.0, 0.0, 0.0))
    at_column = HEADER.split(",").index
    for at, (column, bad, line) in enumerate(
        (("Fx", "NA", 3), ("Fz", "n/a", 4), ("Offset", "NA", 6))
    ):
        table = _table(tmp_path / f"s{at}.csv", forces)
        text = table.read_text(encoding="utf-8").splitlines()
        if line > len(text):
            # a fifth station of blade one, a copy of the fourth
            text.append(text[-1])
        cells = text[line - 1].split(",")
        cells[at_column(column)] = bad
        text[line - 1] = ",".join(cells)
        table.write_text("\n".join(text) + "\n", encoding="utf-8")
        validity = post_qsteady.add_reduced_frequency_to_sections(
            table, record, velocity_m_per_s=30.0, layout=_layout("PROP_RMRP1")
        )
        assert validity is not None
        assert validity.values["THRUST_PCT_K_GT_0_1"] is None, column
        assert validity.values["TORQUE_PCT_K_GT_0_1"] is None, column
        assert validity.values["K_1P_MAX"] is not None
        (note,) = validity.notes
        assert "THRUST_PCT_K_GT_0_1 and TORQUE_PCT_K_GT_0_1 read NA" in note
        assert f"line {line} of s{at}.csv (Blade1 XZ) states {column} {bad}" in note, note
        assert "never read as a zero load" in note
