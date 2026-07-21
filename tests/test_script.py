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


def test_unsteady_monitoring_commands_render_the_manual_grammar():
    # 2026-07-21 legacy-case backfill (SRC-003 pp.344-348, 355): the
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
