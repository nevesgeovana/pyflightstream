"""Tier 1: script builder validation, phase ordering, and goldens."""

from pathlib import Path

import pytest

from pyflightstream.commands import CommandNotInVersionError
from pyflightstream.script import (
    CommandArgumentError,
    Script,
    ScriptLineBreakError,
    ScriptOrderError,
)

GOLDENS = Path(__file__).parent / "goldens"


def build_steady_polar(script: Script) -> None:
    script.comment("Golden: minimal steady polar point for FlightStream 26.120")
    script.emit("OPEN", "C:/cases/wing.fsm")
    script.emit("SET_SIMULATION_LENGTH_UNITS", "METER")
    script.emit("AUTO_DETECT_TRAILING_EDGES")
    script.emit("AUTO_DETECT_WAKE_TERMINATION_NODES")
    script.emit("SET_FREESTREAM", "CONSTANT")
    script.emit("AIR_ALTITUDE", 0.0, "METERS")
    script.emit(
        "INITIALIZE_SOLVER",
        solver_model="INCOMPRESSIBLE",
        surfaces=-1,
        wake_termination_x="DEFAULT",
        symmetry="MIRROR",
        wall_collision_avoidance="DISABLE",
    )
    script.emit("SOLVER_SET_AOA", 2.0)
    script.emit("SOLVER_SET_VELOCITY", 30.0)
    script.emit("SOLVER_SET_REF_VELOCITY", 30.0)
    script.emit("SOLVER_SET_REF_AREA", 11.5)
    script.emit("SOLVER_SET_REF_LENGTH", 1.5)
    script.emit("SOLVER_SET_ITERATIONS", 500)
    script.emit("SOLVER_SET_CONVERGENCE", 1e-5)
    script.emit("START_SOLVER")
    script.emit("SET_VORTICITY_DRAG_BOUNDARIES", -1)
    script.emit("SET_LOADS_AND_MOMENTS_UNITS", "COEFFICIENTS")
    script.emit("EXPORT_SOLVER_ANALYSIS_SPREADSHEET", "C:/cases/out/loads.txt")
    script.emit("CLOSE_FLIGHTSTREAM")


def test_steady_polar_matches_the_golden():
    script = Script(version="26.12")
    build_steady_polar(script)
    golden = (GOLDENS / "steady_polar_26.120.txt").read_text(encoding="utf-8")
    assert script.render() == golden
    assert not script.raw_flag


def test_removed_command_raises_with_citation():
    script = Script(version="26.12")
    with pytest.raises(CommandNotInVersionError, match=r"SRC-003 p\.328"):
        script.emit("SONIC_VELOCITY", 340.0)


def test_phase_order_is_enforced_with_a_didactic_message():
    script = Script(version="26.12")
    script.emit(
        "INITIALIZE_SOLVER",
        solver_model="INCOMPRESSIBLE",
        surfaces=-1,
        wake_termination_x="DEFAULT",
        symmetry="NONE",
    )
    with pytest.raises(ScriptOrderError, match="INITIALIZE_SOLVER at line"):
        script.emit("CREATE_NEW_COORDINATE_SYSTEM")


def test_control_commands_are_exempt_from_phase_ordering():
    script = Script(version="26.12")
    script.emit("START_SOLVER")
    script.emit("PRINT", "solver finished")
    script.emit("SAVEAS", "C:/cases/wing_done.fsm")
    assert "PRINT solver finished" in script.render()


def test_enum_membership_and_case_normalization():
    script = Script(version="26.12")
    script.emit("SET_SOLVER_STEADY")
    script.emit("SET_BOUNDARY_LAYER_TYPE", "transitional")
    assert "SET_BOUNDARY_LAYER_TYPE TRANSITIONAL" in script.render()
    with pytest.raises(CommandArgumentError, match="LAMINAR, TRANSITIONAL, TURBULENT"):
        script.emit("SET_BOUNDARY_LAYER_TYPE", "INVISCID")


def test_argument_type_errors_cite_the_manual():
    script = Script(version="26.12")
    with pytest.raises(CommandArgumentError, match=r"SRC-003 p\.339"):
        script.emit("SOLVER_SET_ITERATIONS", "many")
    with pytest.raises(CommandArgumentError, match="requires argument"):
        script.emit("SET_TRAILING_EDGE_TYPE", 1)
    with pytest.raises(CommandArgumentError, match="no argument"):
        script.emit("SOLVER_SET_AOA", angle_of_attack=2.0)


def test_count_versus_list_consistency():
    script = Script(version="26.12")
    with pytest.raises(CommandArgumentError, match="declared count is 2"):
        script.emit("SET_VTK_EXPORT_VARIABLES", 2, "DISABLE", ["VX", "VY", "VZ"])


def test_payload_lines_rendering_with_newline_separator():
    script = Script(version="26.12")
    script.emit("SET_VTK_EXPORT_VARIABLES", 3, "DISABLE", ["CP_REFERENCE", "VX", "VTOT"])
    assert script.render() == ("SET_VTK_EXPORT_VARIABLES 3 DISABLE\nCP_REFERENCE\nVX\nVTOT\n\n")


def test_param_lines_rendering_mixes_keys_and_bare_paths():
    script = Script(version="26.12")
    script.emit("PROBE_POINTS_IMPORT", "INCH", 1, "C:/probes/lattice.txt")
    assert script.render() == (
        "PROBE_POINTS_IMPORT\nUNITS INCH\nFRAME 1\nC:/probes/lattice.txt\n\n"
    )


def test_inline_own_line_path_renders_after_the_command():
    script = Script(version="26.12")
    script.declare_existing(actuators=2)
    script.emit("SET_PROP_ACTUATOR_PROFILE", 2, "NEWTONS", 4, "C:/props/thrust.txt")
    assert script.render() == ("SET_PROP_ACTUATOR_PROFILE 2 NEWTONS 4\nC:/props/thrust.txt\n\n")


def test_comma_separated_payload_list():
    script = Script(version="26.12")
    script.declare_existing(motions=1)
    script.emit("SET_MOTION_BOUNDARIES", 1, 4, [1, 2, 3, 5])
    assert script.render() == "SET_MOTION_BOUNDARIES 1 4\n1,2,3,5\n\n"


def test_import_renders_the_manual_keyword_block():
    script = Script(version="26.12")
    script.emit("IMPORT", "METER", "STL", "C:/geometry/wing.stl", clear=True)
    assert script.render() == (
        "IMPORT\nUNITS METER\nFILE_TYPE STL\nFILE C:/geometry/wing.stl\nCLEAR\n\n"
    )


def test_import_without_clear_omits_the_presence_keyword():
    script = Script(version="26.12")
    script.emit("IMPORT", "METER", "TRI", "C:/geometry/wing.tri")
    rendered = script.render()
    assert "CLEAR" not in rendered
    assert "FILE_TYPE TRI" in rendered


def test_import_clear_must_be_a_bool():
    script = Script(version="26.12")
    with pytest.raises(CommandArgumentError, match="True or False"):
        script.emit("IMPORT", "METER", "STL", "C:/geometry/wing.stl", clear="CLEAR")


def test_ccs_import_renders_its_toggles_and_path():
    script = Script(version="26.12")
    script.emit("CCS_IMPORT", "ENABLE", "DISABLE", "ENABLE", "C:/geometry/model.csv")
    assert script.render() == (
        "CCS_IMPORT\nCLOSE_COMPONENT_ENDS ENABLE\nUPDATE_PROPERTIES DISABLE\n"
        "CLEAR_EXISTING ENABLE\nFILE C:/geometry/model.csv\n\n"
    )


def test_export_surface_mesh_takes_the_path_on_its_own_line():
    script = Script(version="26.12")
    script.emit("EXPORT_SURFACE_MESH", "OBJ", -1, "C:/geometry/all.obj")
    assert script.render() == "EXPORT_SURFACE_MESH OBJ -1\nC:/geometry/all.obj\n\n"


def test_raw_bypasses_validation_and_sets_the_flag():
    script = Script(version="26.12")
    script.raw("SOME_UNKNOWN_COMMAND 1 2")
    assert script.raw_flag
    assert "SOME_UNKNOWN_COMMAND 1 2" in script.render()


def test_two_scripts_do_not_share_state():
    first = Script(version="26.12")
    second = Script(version="26.12")
    first.emit("START_SOLVER")
    second.emit("CREATE_NEW_COORDINATE_SYSTEM")
    assert "CREATE_NEW_COORDINATE_SYSTEM" not in first.render()


def test_unsteady_monitoring_commands_render_the_manual_grammar():
    # 2026-07-21 case-reproduction backfill (SRC-003 pp.344-348, 355): the
    # unsteady plot blocks render exactly as the manual samples.
    script = Script(version="26.12")
    script.emit("NEW_SIMULATION")
    script.emit(
        "UNSTEADY_SOLVER_NEW_FORCE_PLOT",
        frame=1,
        units="NEWTONS",
        parameter="FORCE_X",
        name="Propeller_thrust",
        boundaries=3,
        boundary_indices=[1, 2, 4],
    )
    script.emit(
        "UNSTEADY_SOLVER_NEW_FLUID_PLOT",
        frame=1,
        parameter="VELOCITY",
        name="Propeller_slipstream",
        vertex="-2.0 1.4 0.0",
    )
    script.emit("SOLVER_SET_FARFIELD_LAYERS", 5)
    script.emit("SET_WAKE_TERMINATION_TIME_STEPS", -36)
    text = script.render()
    assert "UNSTEADY_SOLVER_NEW_FORCE_PLOT\nFRAME 1\nUNITS NEWTONS\n" in text
    assert "BOUNDARIES 3\n1,2,4\n" in text
    assert "VERTEX -2.0 1.4 0.0\n" in text
    assert "SOLVER_SET_FARFIELD_LAYERS 5\n" in text
    assert "SET_WAKE_TERMINATION_TIME_STEPS -36\n" in text


def test_bulk_separation_renders_the_grammar_of_its_target_version():
    # 26.1 versus 26.12 manual delta (SRC-725 p.341 / SRC-003 p.342):
    # 26.12 inserts SEPARATION_TYPE as the second argument.
    later = Script(version="26.12")
    later.emit("CREATE_BULK_SEPARATION", "GEAR", "FLAT_PLATE", 3, 0.2, [1, 3, 5])
    assert later.render() == "CREATE_BULK_SEPARATION GEAR FLAT_PLATE 3 0.2\n1,3,5\n\n"
    earlier = Script(version="26.1")
    earlier.emit("CREATE_BULK_SEPARATION", "GEAR", -1, 0.2)
    assert earlier.render() == "CREATE_BULK_SEPARATION GEAR -1 0.2\n\n"
    with pytest.raises(CommandArgumentError, match="no argument 'separation_type'"):
        Script(version="26.1").emit(
            "CREATE_BULK_SEPARATION",
            "GEAR",
            separation_type="FLAT_PLATE",
            num_boundaries=-1,
            diameter=0.2,
        )


def test_export_surface_sections_exists_only_from_26120():
    later = Script(version="26.12")
    later.emit("EXPORT_SURFACE_SECTIONS", 2)
    assert "EXPORT_SURFACE_SECTIONS 2" in later.render()
    with pytest.raises(CommandNotInVersionError, match="no recorded evidence"):
        Script(version="26.1").emit("EXPORT_SURFACE_SECTIONS", 2)


def test_volume_section_boundary_layer_is_removed_at_26120():
    earlier = Script(version="26.1")
    earlier.emit("VOLUME_SECTION_BOUNDARY_LAYER", 2, "DISABLE")
    assert "VOLUME_SECTION_BOUNDARY_LAYER 2 DISABLE" in earlier.render()
    with pytest.raises(CommandNotInVersionError, match=r"SRC-725 p\.365"):
        Script(version="26.12").emit("VOLUME_SECTION_BOUNDARY_LAYER", 2, "DISABLE")


def test_ccs_control_surface_space_axis_pair_is_26120_only():
    later = Script(version="26.12")
    later.emit(
        "NEW_CCS_WING_CONTROL_SURFACE",
        name="Aileron",
        v0=0.5,
        v1=0.7,
        u0=0.15,
        u1=0.15,
        hinge_height=0.5,
        angle=20.0,
        slot_gap=0.001,
        space="REAL",
        axis="Y",
    )
    assert (
        "NEW_CCS_WING_CONTROL_SURFACE Aileron 0.5 0.7 0.15 0.15 0.5 20.0 0.001 REAL Y"
        in later.render()
    )
    earlier = Script(version="26.1")
    earlier.emit("NEW_CCS_WING_CONTROL_SURFACE", "Aileron", 0.5, 0.7, 0.15, 0.15, 0.5, 20.0, 0.001)
    with pytest.raises(CommandArgumentError, match="no argument 'space'"):
        Script(version="26.1").emit(
            "NEW_CCS_WING_CONTROL_SURFACE",
            "Aileron",
            0.5,
            0.7,
            0.15,
            0.15,
            0.5,
            20.0,
            0.001,
            space="REAL",
        )


def test_probe_family_is_available_in_26100():
    # TSR evidence: the probe family grammar is unchanged between 26.1
    # and 26.12 (SRC-725 pp.361-362 / SRC-003 pp.362-363).
    script = Script(version="26.1")
    script.emit("NEW_PROBE_POINT", "VOLUME", 1.0, 0.5, 0.0)
    script.emit("UPDATE_PROBE_POINTS")
    script.emit("EXPORT_PROBE_POINTS", "C:/probes/out.txt")
    text = script.render()
    assert "NEW_PROBE_POINT VOLUME 1.0 0.5 0.0" in text
    assert "EXPORT_PROBE_POINTS\nC:/probes/out.txt" in text


# PYFS-001, the review REV-002 blocker reproduced at ecc212e. The published
# probe is reproduced verbatim as the first case, so a reader can compare
# this file against the review without translating anything.
#
# The defect: _check_scalar type-checked a STR and returned it unexamined,
# _format_scalar was str(value), and render() joins with "\n". So a newline
# inside any string or path argument became a LINE BOUNDARY, the text after
# it became the next command, and raw_flag stayed False, which is the flag
# whose entire job is to record that a script contains something nobody
# validated (FR-06, FR-07, FR-08a).
#
# Structural fix in three parts, and the third is the one that closes the
# class rather than the case: the two text argument types reject a line
# terminator with a message naming the consequence; comment() prefixes every
# physical line; and emit() checks the RENDERED block, so a future argument
# type or layout cannot reopen the hole without tripping it.


def test_a_newline_in_a_path_argument_cannot_inject_a_command():
    """The review's published probe, verbatim.

    ``s.emit("IMPORT", "METER", "STL", "wing.stl\nSTART_SOLVER", clear=True)``
    used to render START_SOLVER as its own line with ``raw_flag`` False.
    """
    script = Script("26.12")
    with pytest.raises(ScriptLineBreakError) as caught:
        script.emit("IMPORT", "METER", "STL", "wing.stl\nSTART_SOLVER", clear=True)
    message = str(caught.value)
    # The message must name the injected command, not merely say "invalid".
    assert "START_SOLVER" in message
    assert "raw" in message
    # Nothing was appended: the refusal happens before the script is touched.
    assert "START_SOLVER" not in script.render()
    assert script.raw_flag is False


def test_a_newline_in_a_comment_cannot_inject_a_command():
    """``comment("hello\nSTART_SOLVER")`` used to emit a bare command line.

    A comment is not refused, because commenting every line is what the
    caller meant. What must not survive is an uncommented second line.
    """
    script = Script("26.12")
    script.comment("hello\nSTART_SOLVER")
    lines = script.render().splitlines()
    assert lines == ["# hello", "# START_SOLVER"]
    assert script.raw_flag is False


def test_every_line_of_a_multi_line_comment_is_commented():
    """Including the blank one, which becomes a bare ``#`` and not a gap."""
    script = Script("26.12")
    script.comment("first\n\nthird")
    assert script.render().splitlines() == ["# first", "#", "# third"]


@pytest.mark.parametrize(
    "terminator",
    ["\n", "\r\n", "\r", "\x0b", "\x0c", "\x1c", "\x85", "\u2028", "\u2029"],
    ids=["lf", "crlf", "cr", "vt", "ff", "fs", "nel", "line-sep", "para-sep"],
)
def test_every_line_terminator_python_knows_is_refused(terminator):
    """Not just ``\n``.

    The guard is defined by ``str.splitlines`` rather than by a denylist of
    characters, precisely so this parametrization passes. A denylist written
    against CR and LF would let the other seven through, and they still
    arrive as two lines because ``render`` joins what ``splitlines`` split.
    """
    script = Script("26.12")
    with pytest.raises(ScriptLineBreakError) as caught:
        script.emit("IMPORT", "METER", "STL", f"wing.stl{terminator}START_SOLVER")
    # Assert the MESSAGE too, not only the type. The role-review QA pass
    # measured that the refusal named the wrong cause for seven of these
    # nine: it partitioned on a newline, found nothing for CR, VT, FF, FS,
    # NEL and the two Unicode separators, and so reported "the value ends with a
    # line break" while quoting the whole injected string back as the safe
    # prefix. Only the LF case asserted the text, so nothing noticed.
    message = str(caught.value)
    assert "START_SOLVER" in message, message
    assert "would render as 2 script lines" in message, message


def test_a_trailing_line_terminator_is_refused_too():
    """``"wing.stl\n"`` injects nothing by itself and still must not pass.

    It carries no second command, so a check asking "is there text after the
    break" would allow it, and the next command would then be appended to
    this line's own physical line. The invariant is one line, not one command.
    """
    script = Script("26.12")
    with pytest.raises(ScriptLineBreakError):
        script.emit("IMPORT", "METER", "STL", "wing.stl\n")


def test_raw_remains_the_sanctioned_route_and_still_flags():
    """The refusal has an answer, and the answer is the one that records itself.

    This is the control for the whole group: if unvalidated text could not be
    appended at all, the fix would have removed a capability rather than
    closed a hole.
    """
    script = Script("26.12")
    script.raw("START_SOLVER")
    assert "START_SOLVER" in script.render()
    assert script.raw_flag is True


def test_an_ordinary_path_still_emits_unchanged():
    """The guard must not cost a legitimate call anything."""
    script = Script("26.12")
    script.emit("IMPORT", "METER", "STL", "C:/cases/wing.stl")
    assert "C:/cases/wing.stl" in script.render()
    assert script.raw_flag is False


def test_the_emit_choke_point_catches_what_the_argument_checks_miss(monkeypatch):
    """The guard that closes the CLASS rather than the case, exercised.

    The argument-level checks cover the two text types that exist today. The
    loop in emit() covers the invariant: one element of _lines renders as one
    physical line, whatever produced it. The role-review QA pass measured that
    deleting that loop left the whole suite green, which is precisely the
    recurrence the structural-fix rule requires a proven guard against, so the
    formatter is monkeypatched to smuggle a break past the type checks.
    """
    import pyflightstream.script as script_module

    original = script_module.Script._format_scalar

    def leaky(self, value):
        rendered = original(self, value)
        return rendered.replace("wing.stl", "wing.stl\nSTART_SOLVER")

    monkeypatch.setattr(script_module.Script, "_format_scalar", leaky)
    script = Script("26.12")
    with pytest.raises(ScriptLineBreakError) as caught:
        script.emit("IMPORT", "METER", "STL", "wing.stl")
    assert "START_SOLVER" in str(caught.value)
    assert "START_SOLVER" not in script.render()
