"""Tier 1: a rotating free stream, stated as a body rate (0.21.0, GOAL-024 arm 6).

The author's decision of 2026-09-15. A row states ONE body rate --
``roll_rate``, ``pitch_rate`` or ``yaw_rate`` -- in deg/s and in
flight-mechanics signs, and the free stream turns about the MOMENT REFERENCE
POINT of the row's REF at that rate. Which axis of the model that is belongs to
the configuration, so the reference artifact declares it in ``[body_axes]``;
a reference declaring none is a configuration no row may turn.

Every rate zero, or no rate at all, writes ``SET_FREESTREAM CONSTANT``, which
is what every row written before this release does.

WHAT THESE TESTS DO NOT MEASURE: what the SOLVER does with a positive angular
velocity. No edition of the manual states it; it was measured by two licensed
probes on 26.124, each recorded as a report with its evidence under
``reports/probes``: RPT-052 (pitch) and RPT-060 (the probe T11, roll and yaw).
The solver turns the free stream as a right-hand rotation about the frame axis
it is given, so the sign of the emitted rotation is the sign of the body axis in
the geometry's frame: -1 for roll, +1 for pitch, -1 for yaw (G13, 0.27.0).
Until 0.27.0 one sign of +1 served all three, and the two roll and yaw pins
below encoded it: they were the defect's fixture and moved with the fix. What
the solver does with the emitted line is scored against the recorded probes in
``test_ops2011_rate_sense_against_recorded_probes.py``.

This module is the evidence of FR-105.

The test names carry ``goal024_freestream_rotation`` so the goal's checker can
select them.
"""

from __future__ import annotations

import pytest

from pyflightstream.cases import CampaignConfigError
from pyflightstream.cases.matrix import MatrixError, read_matrix
from pyflightstream.cases.workflows import workflow_registry
from pyflightstream.run.matrix import run_matrix
from tests.tier1_offline.test_goal024_point_name import RECIPES, _matrix
from tests.tier1_offline.test_matrix_run import (
    WRITES_EVERY_EXPORT,
    CountingStub,
    converged,
)

#: The axes the fixture configuration declares: the model flies along X, with
#: Y to starboard and Z up, which is what an aircraft mesh usually carries.
BODY_AXES = '\n[body_axes]\nroll = "X"\npitch = "Y"\nyaw = "Z"\n'


def _rate_matrix(tmp_path, *, condition, values="0.0,2.0", axes=BODY_AXES):
    """A one-row matrix whose cell states a body rate, and a reference declaring axes."""
    workspace, matrix = _matrix(tmp_path, condition=condition, values=values)
    if axes:
        reference = workspace.inputs_dir / "references" / "r003.toml"
        reference.write_text(reference.read_text(encoding="utf-8") + axes, encoding="utf-8")
    return workspace, matrix


def _script(workspace, matrix):
    """Run the row with a stub and return the one script it emitted."""
    run_matrix(
        matrix,
        workspace,
        name="turning",
        default_fs_version="26.120",
        recipes=RECIPES,
        recipe_registry=workflow_registry(),
        assess=converged,
        executor=CountingStub(WRITES_EVERY_EXPORT),
    )
    scripts = sorted((workspace.sim_dir("3207") / "scripts").glob("*.txt"))
    assert len(scripts) == 1, scripts
    return scripts[0].read_text(encoding="utf-8")


def _free_stream(script: str) -> list[str]:
    """Return the SET_FREESTREAM line, split into its words.

    The emitter writes this command INLINE -- the kind and its arguments on the
    one line -- which is the layout the manual gives it, so the arguments are
    read from that line rather than from the lines after it.
    """
    line = next(line.strip() for line in script.splitlines() if line.startswith("SET_FREESTREAM"))
    return line.split()


def test_goal024_freestream_rotation_a_pitch_rate_turns_the_free_stream(tmp_path):
    """4 deg/s nose-up: ROTATION about the MRP frame, on the pitch axis, in rev/min."""
    workspace, matrix = _rate_matrix(
        tmp_path,
        condition="MACH:0.2, REmi:2.3, ALPHA:sweep, pitch_rate:4.0",
    )
    script = _script(workspace, matrix)
    words = _free_stream(script)
    # SET_FREESTREAM ROTATION <frame> <axis> <rev/min>: the axis is the one
    # [body_axes] gives the pitch rate, and the speed is the rate in rev/min,
    # 4 deg/s being 4 x 60 / 360.
    assert words[:2] == ["SET_FREESTREAM", "ROTATION"], words
    assert words[3] == "Y", words
    assert float(words[4]) == pytest.approx(4.0 * 60.0 / 360.0), words
    # AND THE FRAME IS THE MOMENT POINT'S, read out of the script rather than
    # written here: `>= 1` accepted any frame, so a regression turning the free
    # stream about a ROTOR frame passed green and FR-105's first clause had no
    # test that could fail (the V&V lens, 2026-09-16).
    assert int(words[2]) == _mrp_frame(script), (words, script)


def _mrp_frame(script: str) -> int:
    """Return the index of the MRP coordinate system this script creates.

    The builder creates a coordinate system and then edits it, and the edit
    block carries the index it is editing (`FRAME <n>`) and the name it gives
    it (`NAME MRP`). Read from the script, so a renumbering moves the assertion
    with it rather than leaving a constant behind.
    """
    lines = [line.strip() for line in script.splitlines()]
    for index, line in enumerate(lines):
        if line == "NAME MRP" and index and lines[index - 1].startswith("FRAME "):
            return int(lines[index - 1].split()[1])
    raise AssertionError("the script names no MRP frame")


def test_goal024_freestream_rotation_each_rate_takes_its_own_axis(tmp_path):
    """Roll turns about X and yaw about Z, because the configuration says so."""
    for key, axis in (("roll_rate", "X"), ("yaw_rate", "Z")):
        workspace, matrix = _rate_matrix(
            tmp_path / key,
            condition=f"MACH:0.2, REmi:2.3, ALPHA:sweep, {key}:6.0",
        )
        words = _free_stream(_script(workspace, matrix))
        assert words[1] == "ROTATION", words
        assert words[3] == axis, (key, words)
        # NEGATIVE, because forward is -X and down is -Z of the geometry's
        # frame (G13). This pin read +1.0 until 0.27.0: it encoded the one sign
        # the package used for all three axes, which the probe T11 measured
        # asking the solver for the opposite roll and yaw (RPT-060).
        assert float(words[4]) == pytest.approx(-6.0 * 60.0 / 360.0), words


#: THE FRAME ALGEBRA the next test derives its expected arguments from, written
#: here and read from no module of the package (G13). The geometry's frame, the
#: one a loads export states its forces in, is x AFT, y RIGHT, z UP; the
#: flight-mechanics body axes are x FORWARD, y RIGHT, z DOWN. So each body axis a
#: rate turns about is, in the geometry's components:
_BODY_AXIS_IN_GEOMETRY_FRAME = {
    "roll_rate": (-1.0, 0.0, 0.0),  # forward, and x points aft
    "pitch_rate": (0.0, 1.0, 0.0),  # right, and y points right
    "yaw_rate": (0.0, 0.0, -1.0),  # down, and z points up
}
_GEOMETRY_FRAME_AXIS = {"X": (1.0, 0.0, 0.0), "Y": (0.0, 1.0, 0.0), "Z": (0.0, 0.0, 1.0)}


def _flight_mechanics_rpm(key: str, axis: str, rate_deg_s: float) -> float:
    """The rev/min about frame axis ``axis`` that turns the aircraft at ``rate_deg_s``.

    A body rate w about body axis b is the angular velocity w b. The solver
    turns the free stream as a RIGHT-HAND rotation about the frame axis it is
    given (RPT-052 for y, RPT-060 for x and z, both on 26.124), so the speed it
    must be given about axis e is the component w (b . e), in rev/min.
    """
    body = _BODY_AXIS_IN_GEOMETRY_FRAME[key]
    along = sum(b * e for b, e in zip(body, _GEOMETRY_FRAME_AXIS[axis], strict=True))
    return rate_deg_s * along * 60.0 / 360.0


def test_goal024_freestream_rotation_each_rate_turns_in_the_flight_mechanics_sense(tmp_path):
    """Positive p is right wing down, q nose up, r nose right, in either sign of the rate.

    G13 of 0.27.0: the expected rotation is DERIVED from the frame algebra
    above, not copied from the package, so a sign that agrees with itself and
    not with the frames fails here. Pitch is the control: RPT-052 measured it
    right, and it is unchanged.
    """
    wrong = []
    for key, axis in (("roll_rate", "X"), ("pitch_rate", "Y"), ("yaw_rate", "Z")):
        for rate in (6.0, -6.0):
            workspace, matrix = _rate_matrix(
                tmp_path / f"{key}{rate:+g}",
                condition=f"MACH:0.2, REmi:2.3, ALPHA:sweep, {key}:{rate}",
            )
            words = _free_stream(_script(workspace, matrix))
            assert words[:2] == ["SET_FREESTREAM", "ROTATION"], words
            assert words[3] == axis, (key, words)
            expected = _flight_mechanics_rpm(key, axis, rate)
            if float(words[4]) != pytest.approx(expected):
                wrong.append(
                    f"{key} {rate:+g} deg/s emits {axis} {float(words[4]):+.4f} rev/min, "
                    f"and flight mechanics asks {axis} {expected:+.4f}"
                )
    assert not wrong, "; ".join(wrong)


def test_goal024_freestream_rotation_the_sign_per_rate_is_the_export_to_body_turn():
    """The emitter's sign per rate and the post's export-to-body turn are one relation.

    The two live in two layers (``cases`` may not import ``post``), so this
    holds them together: a change to either without the other fails here.
    """
    from pyflightstream.cases.workflows import FREESTREAM_ROTATION_SIGN, RATE_VARIABLES
    from pyflightstream.post.axes import EXPORT_TO_BODY

    assert [name for _, name in RATE_VARIABLES] == ["roll", "pitch", "yaw"]
    assert set(FREESTREAM_ROTATION_SIGN) == {"roll", "pitch", "yaw"}
    for index, (_, name) in enumerate(RATE_VARIABLES):
        assert FREESTREAM_ROTATION_SIGN[name] == float(EXPORT_TO_BODY[index, index]), name


def test_goal024_freestream_rotation_a_permuted_axis_turns_with_its_rates_sign(tmp_path):
    """D07: ``roll = "Y"`` turns a roll rate about Y, with roll's sign and not pitch's.

    What the page promises for a ``[body_axes]`` table that permutes the axes.
    No probe has measured such a mesh; this holds the emitted line only.
    """
    permuted = '\n[body_axes]\nroll = "Y"\npitch = "X"\nyaw = "Z"\n'
    for key, axis, sign in (("roll_rate", "Y", -1.0), ("pitch_rate", "X", 1.0)):
        workspace, matrix = _rate_matrix(
            tmp_path / key,
            condition=f"MACH:0.2, REmi:2.3, ALPHA:sweep, {key}:6.0",
            axes=permuted,
        )
        words = _free_stream(_script(workspace, matrix))
        assert words[:2] == ["SET_FREESTREAM", "ROTATION"], words
        assert words[3] == axis, (key, words)
        assert float(words[4]) == pytest.approx(sign * 6.0 * 60.0 / 360.0), (key, words)


def test_goal024_freestream_rotation_every_rate_zero_writes_constant(tmp_path):
    """A rate stated as zero is not a rotation: the row renders as it always did."""
    workspace, matrix = _rate_matrix(
        tmp_path,
        condition="MACH:0.2, REmi:2.3, ALPHA:sweep, pitch_rate:0.0, yaw_rate:0.0",
    )
    script = _script(workspace, matrix)
    assert _free_stream(script) == ["SET_FREESTREAM", "CONSTANT"], _free_stream(script)
    assert "ROTATION" not in script


def test_goal024_freestream_rotation_a_row_with_no_rate_at_all_writes_constant(tmp_path):
    """And so does every row written before this release."""
    workspace, matrix = _rate_matrix(
        tmp_path,
        condition="MACH:0.2, REmi:2.3, ALPHA:sweep",
    )
    assert _free_stream(_script(workspace, matrix)) == ["SET_FREESTREAM", "CONSTANT"]


def test_goal024_freestream_rotation_two_non_zero_rates_are_refused_by_name(tmp_path):
    """One axis, one speed: two rates would be composed into an axis nobody wrote."""
    workspace, matrix = _rate_matrix(
        tmp_path,
        condition="MACH:0.2, REmi:2.3, ALPHA:sweep, pitch_rate:4.0, yaw_rate:2.0",
    )
    with pytest.raises(MatrixError) as caught:
        read_matrix(matrix)
    message = str(caught.value)
    assert "pitch_rate, yaw_rate" in message, message
    assert "ONE axis" in message


def test_goal024_freestream_rotation_a_reference_declaring_no_axes_is_refused_by_name(tmp_path):
    """The axis is the configuration's to state, so a row cannot turn without it."""
    workspace, matrix = _rate_matrix(
        tmp_path,
        condition="MACH:0.2, REmi:2.3, ALPHA:sweep, pitch_rate:4.0",
        axes="",
    )
    with pytest.raises(MatrixError) as caught:
        _script(workspace, matrix)
    message = str(caught.value)
    assert "body_axes" in message and "pitch" in message, message


def test_goal024_freestream_rotation_a_rate_sweeps_like_any_other_variable(tmp_path):
    """The cluster's own case: hold the flow, vary the rate, one run per rate."""
    workspace, matrix = _rate_matrix(
        tmp_path,
        condition="MACH:0.2, REmi:2.3, ALPHA:0.0, pitch_rate:sweep",
        values="0.0,2.0,4.0",
    )
    (row,) = read_matrix(matrix)
    assert row.sweep.type == "pitch_rate"
    assert [point["pitch_rate"] for point in row.sweep.points()] == [0.0, 2.0, 4.0]
    from pyflightstream.run.matrix import plan_matrix

    plan = plan_matrix(
        matrix,
        workspace,
        name="turning",
        default_fs_version="26.120",
        recipes=RECIPES,
        recipe_registry=workflow_registry(),
        write_plan=False,
    )
    assert [point.run_id.rsplit("/", 1)[-1] for point in plan.points] == [
        "M200RE230AL+000Q+000",
        "M200RE230AL+000Q+020",
        "M200RE230AL+000Q+040",
    ]


def test_goal024_freestream_rotation_a_case_authored_in_python_is_refused_too(tmp_path):
    """The matrix reader is one door; a case built in Python meets the same rule."""
    from pyflightstream.cases import ReferenceData, SimCase, SweepAxis
    from pyflightstream.cases.workflows import _turning_rate

    case = SimCase(
        sim_id="3207",
        aircraft="Wing",
        recipe="steady",
        sweep=SweepAxis(type="alpha", values=[0.0]),
        reference=ReferenceData(area=10.0, length=1.2, body_axes={"pitch": "Y"}),
        variables={"pitch_rate": "4.0", "yaw_rate": "2.0"},
    )
    with pytest.raises(CampaignConfigError, match="ONE axis"):
        _turning_rate(case)
