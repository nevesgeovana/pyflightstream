"""Tier 1: the rotor speed is a flight-condition variable (0.21.0, GOAL-024 arm 5).

The author's decision of 2026-09-15. A rotor study varies the SPEED
and holds the flow, and until 0.20.x the speed could only be written on a
motion record: it could not be swept, and every motion of the row needed its
own copy. ``RPM`` is a key of ``FLIGHT_CONDITION`` now, it sweeps like any
other, and:

* a ``MOTIONS`` record naming a speed still wins over it;
* ``RPM`` with ``ADVANCE_RATIO`` and a velocity is refused by name, because the
  three are one relation and nothing can know which two were meant;
* ``RPM`` with ``ADVANCE_RATIO`` and no velocity COMPUTES the velocity,
  V = J x (RPM/60) x D, with D the diameter of the rotor ``CLOCK_MOTION``
  names, and a row naming none is refused by name.

This module is the evidence of FR-104.

The test names carry ``goal024_rpm`` so the goal's checker can select them.
"""

from __future__ import annotations

import pytest

from pyflightstream.cases.matrix import MatrixError, read_matrix
from pyflightstream.cases.workflows import workflow_registry
from pyflightstream.run.matrix import plan_matrix
from pyflightstream.workspace.matrix import resolve_matrix
from tests.tier1_offline.test_goal024_point_name import RECIPES, _matrix

#: The rotor row of the fixture library: one rotor, turning, with a clock.
ROTOR_CELL = (
    "MOTIONS: {MOVING_BC_ALIAS: PORT} / CLOCK_MOTION: PORT / DELTA_TIME: 0.01 / TIME_ITERATIONS: 8"
)

#: A rotor on the fixture reference, so a row can name a clock rotor with a
#: diameter. The library's own references carry lengths and no rotor.
ROTOR_BLOCK = """
[PORT]
kind = "rotor"
alias = "PORT"
x_m = 0.0
y_m = 0.0
z_m = 0.0
axis = "X"
rpm_sign = 1
diameter_m = 1.2
families_general = ["Hub"]
families_blades = ["Blade_1", "Blade_2"]
blade1 = { azimuth_deg = 0.0, zero = "Y" }
"""


def _rotor_matrix(tmp_path, *, condition, values, cell=ROTOR_CELL, pol="9001"):
    """A one-row rotor matrix, with a rotor on the reference the row names."""
    workspace, matrix = _matrix(
        tmp_path,
        condition=condition,
        values=values,
        pol=pol,
        workflow="unsteady_rotor",
        cell=cell,
    )
    reference = workspace.inputs_dir / "references" / "r003.toml"
    reference.write_text(reference.read_text(encoding="utf-8") + ROTOR_BLOCK, encoding="utf-8")
    return workspace, matrix


def test_goal024_rpm_is_a_flight_condition_key_and_reaches_the_motion(tmp_path):
    """A row states RPM in the cell and the rotor turns at it."""
    workspace, matrix = _matrix(
        tmp_path,
        condition="MACH:0.144, REmi:4.38, ALPHA:sweep, RPM:800",
        values="0.0,2.0",
    )
    (row,) = read_matrix(matrix)
    assert row.variables["RPM"] == 800.0
    assert "RPM" in row.condition_order


def test_goal024_rpm_sweeps_like_any_other_variable(tmp_path):
    """RPM:sweep is three points, three speeds and three names."""
    workspace, matrix = _matrix(
        tmp_path,
        condition="MACH:0.144, REmi:4.38, ALPHA:0.0, RPM:sweep",
        values="600,800,1000",
    )
    (row,) = read_matrix(matrix)
    assert row.sweep.type == "RPM"
    assert [point["RPM"] for point in row.sweep.points()] == [600.0, 800.0, 1000.0]
    plan = plan_matrix(
        matrix,
        workspace,
        name="rpm",
        default_fs_version="26.120",
        recipes=RECIPES,
        recipe_registry=workflow_registry(),
        write_plan=False,
    )
    # The speed is written signed, five characters, the sign included.
    assert [point.run_id.rsplit("/", 1)[-1] for point in plan.points] == [
        "M144RE438AL+000RPM00600",
        "M144RE438AL+000RPM00800",
        "M144RE438AL+000RPM01000",
    ]


def _case_of(workspace, matrix):
    """Return the one resolved case of a one-row matrix."""
    resolved = resolve_matrix(
        matrix,
        workspace,
        name="rpm",
        fs_version="26.120",
        recipes=RECIPES,
    )
    (case,) = resolved.campaign.sims
    return case


def _motion_speed(workspace, matrix) -> float:
    """Return the speed the row's MOTION turns at, as the package resolves it.

    Through `_optional_rotor_speed`, which is the seam the motion VIEW lives
    behind: the reductions, the products and the emitter all reach a record's
    speed through it, and no public function returns the number on its own. A
    test that merged the record over the row itself would agree with a package
    that had stopped doing it, which is the reason for going through the seam
    rather than around it.
    """
    from pyflightstream.cases.workflows import _optional_rotor_speed

    speed = _optional_rotor_speed(_case_of(workspace, matrix))
    assert speed is not None, "the row resolves no rotor speed at all"
    return speed.rpm


def test_goal024_rpm_the_cell_speed_reaches_the_motion(tmp_path):
    """The row states the speed once, in the cell, and THE MOTION turns at it.

    Read from the per-ROTOR reductions, which is the one place that can tell
    the two apart. A row stating RPM anywhere resolves a speed: with the cell's
    speed reaching no motion the record resolves to nothing, the rotor lands in
    the lost list, and the row's own flat speed answers instead -- the same
    number, from a rotor nobody turned. So the assertion is that PORT is a
    rotor this row TURNS, at 800, and that its blade passage was cut from it.
    """
    from pyflightstream.cases.workflows import reduction_windows

    workspace, matrix = _rotor_matrix(
        tmp_path,
        condition="MACH:0.144, REmi:4.38, ALPHA:sweep, RPM:800",
        values="0.0,2.0",
    )
    assert _motion_speed(workspace, matrix) == 800.0
    windows = reduction_windows(_case_of(workspace, matrix))
    assert windows is not None
    rotors = windows["rotors"]
    assert set(rotors) == {"PORT"}, rotors
    assert rotors["PORT"]["rpm"] == 800.0
    assert rotors["PORT"]["steps_per_revolution"] == pytest.approx(60.0 / (800.0 * 0.01))


def test_goal024_rpm_a_motions_record_wins_over_the_cell(tmp_path):
    """MOTIONS wins: a record naming a speed keeps it while the cell serves the rest."""
    from pyflightstream.cases.workflows import reduction_windows

    workspace, matrix = _rotor_matrix(
        tmp_path,
        condition="MACH:0.144, REmi:4.38, ALPHA:sweep, RPM:800",
        values="0.0,2.0",
        cell=(
            "MOTIONS: {MOVING_BC_ALIAS: PORT / RPM: 1200} / CLOCK_MOTION: PORT / "
            "DELTA_TIME: 0.01 / TIME_ITERATIONS: 8"
        ),
    )
    assert _motion_speed(workspace, matrix) == 1200.0
    rotors = reduction_windows(_case_of(workspace, matrix))["rotors"]
    assert rotors["PORT"]["rpm"] == 1200.0, rotors


def test_goal024_rpm_with_an_advance_ratio_and_a_velocity_is_refused_by_name(tmp_path):
    """The three are one relation, so the cell that states all three is refused."""
    workspace, matrix = _matrix(
        tmp_path,
        condition="MACH:0.144, ALPHA:sweep, RPM:800, ADVANCE_RATIO:0.8",
        values="0.0,2.0",
    )
    with pytest.raises(MatrixError) as caught:
        read_matrix(matrix)
    message = str(caught.value)
    assert "RPM, ADVANCE_RATIO and MACH" in message, message
    assert "V = J x (RPM/60) x D" in message


def test_goal024_rpm_with_an_advance_ratio_and_no_velocity_computes_the_velocity(tmp_path):
    """The static-rig form: the velocity is what the speed and the ratio work out to.

    The fixture rotor's diameter is read from the reference artifact the row's
    REF names, through the alias CLOCK_MOTION states, and
    V = J x (RPM/60) x D is asserted on the number rather than on its presence.
    """
    workspace, matrix = _rotor_matrix(
        tmp_path,
        condition="REmi:4.38, ALPHA:0.0, RPM:800, ADVANCE_RATIO:sweep",
        values="0.8,1.0",
    )
    resolved = resolve_matrix(
        matrix,
        workspace,
        name="rpm",
        fs_version="26.120",
        recipes=RECIPES,
    )
    (case,) = resolved.campaign.sims
    diameter = case.rotors["PORT"].diameter_m
    assert case.velocity == pytest.approx(0.8 * (800.0 / 60.0) * diameter)


def test_goal024_rpm_a_row_naming_no_clock_rotor_is_refused_by_name(tmp_path):
    """D is the clock rotor's diameter, so a row naming no clock has no velocity."""
    workspace, matrix = _rotor_matrix(
        tmp_path,
        condition="REmi:4.38, ALPHA:0.0, RPM:800, ADVANCE_RATIO:sweep",
        values="0.8,1.0",
        cell="MOTIONS: {MOVING_BC_ALIAS: PORT} / DELTA_TIME: 0.01 / TIME_ITERATIONS: 8",
    )
    with pytest.raises(MatrixError) as caught:
        resolve_matrix(
            matrix,
            workspace,
            name="rpm",
            fs_version="26.120",
            recipes=RECIPES,
        )
    message = str(caught.value)
    assert "CLOCK_MOTION" in message and "V = J x (RPM/60) x D" in message, message


def test_goal024_rpm_the_point_name_refuses_a_hand_written_into_the_speed():
    """0.22.0: `RPM` is a magnitude in the name, and a sign there is REFUSED.

    THE MUTANT THIS KILLS, which survived the first writing: nothing in tier one
    asserted the magnitude rule at all, so removing it changed a reachable output
    and 514 cases stayed green (the qa lens, FIX-0220). The two name assertions
    that existed used positive speeds and were green before the rule existed.

    AND IT REFUSES RATHER THAN ABSORBING, which is the half that was a defect.
    Taking the absolute value silently gave a swept `600, -600` two identical
    names, so the user met a FILE NAME COLLISION instead of the sentence saying
    where the hand belongs -- on a row whose scalar form refuses correctly.
    """
    from pyflightstream.cases import CampaignConfigError, name_field

    assert name_field("RPM", 800.0) == "RPM00800"

    with pytest.raises(CampaignConfigError) as caught:
        name_field("RPM", -800.0)
    message = str(caught.value)
    assert "MAGNITUDE" in message, message
    assert "rpm_sign" in message, "the refusal names where the hand belongs"


def test_goal024_rpm_the_other_signed_fields_keep_their_sign():
    """THE CONTROL, so the rule cannot be satisfied by making everything a magnitude.

    A rotor's hand is the ROTOR's; an angle of attack, a sideslip and a
    temperature offset are properties of the OPERATING POINT and their sign is
    part of the point's identity. A mutant that magnituded the whole table would
    pass the test above and fail here.
    """
    from pyflightstream.cases import name_field

    assert name_field("ALPHA", -2.0) == "AL-020"
    assert name_field("BETA", -6.0) == "BE-060"
    assert name_field("dISA", -1.5) == "DT-015"
