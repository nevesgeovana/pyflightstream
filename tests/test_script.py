"""Tier 1: script builder validation, phase ordering, and goldens."""

from pathlib import Path

import pytest

from pyflightstream.commands import CommandNotInVersionError
from pyflightstream.script import CommandArgumentError, Script, ScriptOrderError

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
