"""Tier 1: curated helper layer, cross references, and helper goldens."""

from pathlib import Path

import pytest

from pyflightstream.script import (
    CommandArgumentError,
    Script,
    ScriptReferenceError,
    helpers,
)
from pyflightstream.script.toggles import SOLVER_TOGGLE_WORDS, resolve_toggle

GOLDENS = Path(__file__).parent / "goldens"


def build_actuator_polar(script: Script) -> None:
    script.comment("Golden: actuator disc polar through the curated helpers, FlightStream 26.120")
    script.emit("OPEN", "C:/cases/prop_wing.fsm")
    script.emit("SET_SIMULATION_LENGTH_UNITS", "METER")
    script.emit("AUTO_DETECT_TRAILING_EDGES")
    script.emit("AUTO_DETECT_WAKE_TERMINATION_NODES")
    helpers.free_stream(script)
    helpers.atmosphere(script, altitude=1000.0)
    script.emit("CREATE_NEW_COORDINATE_SYSTEM")
    script.emit("SET_COORDINATE_SYSTEM_ORIGIN", 2, 1.2, 0.0, 0.0, "METER")
    helpers.actuator_disc(
        script,
        "prop_right",
        frame=2,
        axis="X",
        offset=0.0,
        r_tip=0.9,
        r_hub=0.12,
        rpm=2400.0,
        thrust=850.0,
        swirl=0.85,
    )
    helpers.initialize_solver(
        script,
        surfaces=[(1, True), (2, True), (3, False)],
        symmetry="MIRROR",
        wall_collision_avoidance=False,
    )
    helpers.solver_settings(
        script,
        vorticity_drag_boundaries="all",
        velocity=55.0,
        ref_velocity=55.0,
        ref_area=11.5,
        ref_length=1.5,
        iterations=600,
        convergence=1e-5,
        viscous_coupling=True,
    )
    helpers.sweep(
        script,
        aoa=[-4.0, -2.0, 0.0, 2.0, 4.0, 6.0],
        clear_solution=True,
        ref_velocity_same=True,
        export_spreadsheet="C:/cases/out/polar.txt",
    )
    script.emit("CLOSE_FLIGHTSTREAM")


def build_rotor_unsteady(script: Script) -> None:
    script.comment("Golden: periodic rotor in rotation through the helpers, FlightStream 26.120")
    script.emit("OPEN", "C:/cases/rotor_blade.fsm")
    script.emit("SET_SIMULATION_LENGTH_UNITS", "METER")
    script.emit("AUTO_DETECT_TRAILING_EDGES")
    script.emit("CREATE_NEW_COORDINATE_SYSTEM")
    script.emit("SET_COORDINATE_SYSTEM_AXIS", 2, "X", 1.0, 0.0, 0.0, "TRUE")
    helpers.free_stream(script, "ROTATION", frame=2, axis="X", rpm=1200.0)
    helpers.atmosphere(
        script,
        density=1.225,
        pressure=101325.0,
        temperature=288.15,
        viscosity=1.789e-5,
        specific_heat_ratio=1.4,
    )
    helpers.rotary_motion(
        script,
        frame=2,
        axis="X",
        rpm=1200.0,
        boundaries=[1, 2],
        start_time=0.05,
        wake_stabilization_blades=3,
    )
    helpers.unsteady_solver(script, time_iterations=180, delta_time=0.000556)
    helpers.initialize_solver(
        script, symmetry="PERIODIC", periodic_copies=3, wake_termination_x=5.0
    )
    helpers.solver_settings(
        script,
        vorticity_drag_boundaries="all",
        velocity=0.0,
        ref_velocity=150.0,
        ref_area=0.8,
        ref_length=0.25,
    )
    helpers.start_solver(script)
    helpers.analysis_setup(script, loads_frame=2, load_units="NEWTONS")
    helpers.probe_line(script, points=25, start=(0.0, 0.0, 0.5), end=(2.5, 0.0, 0.5))
    helpers.export_probes(script, "C:/cases/out/wake_line.txt")
    helpers.export_results(
        script,
        spreadsheet="C:/cases/out/rotor_loads.txt",
        vtk="C:/cases/out/rotor.vtk",
        vtk_variables=["CP_REFERENCE", "VX", "VTOT"],
    )
    script.emit("CLOSE_FLIGHTSTREAM")


def test_actuator_polar_matches_the_golden():
    script = Script(version="26.12")
    build_actuator_polar(script)
    golden = (GOLDENS / "actuator_polar_26.120.txt").read_text(encoding="utf-8")
    assert script.render() == golden
    assert not script.raw_flag


def test_rotor_unsteady_matches_the_golden():
    script = Script(version="26.12")
    build_rotor_unsteady(script)
    golden = (GOLDENS / "rotor_unsteady_26.120.txt").read_text(encoding="utf-8")
    assert script.render() == golden
    assert not script.raw_flag


def test_initialize_solver_periodic_requires_copies_and_only_then():
    script = Script(version="26.12")
    with pytest.raises(CommandArgumentError, match="PERIODIC symmetry appends"):
        helpers.initialize_solver(script, symmetry="PERIODIC")
    with pytest.raises(CommandArgumentError, match="PERIODIC symmetry appends"):
        helpers.initialize_solver(script, symmetry="MIRROR", periodic_copies=4)
    with pytest.raises(CommandArgumentError, match="positive count"):
        helpers.initialize_solver(script, symmetry="PERIODIC", periodic_copies=0)


def test_periodic_copies_join_the_symmetry_line():
    script = Script(version="26.12")
    helpers.initialize_solver(script, symmetry="PERIODIC", periodic_copies=6)
    assert "SYMMETRY PERIODIC 6" in script.render()


def test_surface_toggles_render_one_line_per_surface():
    script = Script(version="26.12")
    helpers.initialize_solver(script, surfaces=[(1, True), (3, False)])
    assert "SURFACES 2\n1,ENABLE\n3,DISABLE\n" in script.render()


def test_surface_toggle_count_mismatch_is_rejected_at_emit_level():
    script = Script(version="26.12")
    with pytest.raises(CommandArgumentError, match="declared count is 2"):
        script.emit(
            "INITIALIZE_SOLVER",
            solver_model="INCOMPRESSIBLE",
            surfaces=2,
            surface_toggles=["1,ENABLE", "2,ENABLE", "3,ENABLE"],
            wake_termination_x="DEFAULT",
            symmetry="NONE",
        )


def test_free_stream_conditional_combinations():
    script = Script(version="26.12")
    with pytest.raises(CommandArgumentError, match="ROTATION takes exactly"):
        helpers.free_stream(script, "ROTATION", frame=2, axis="X")
    with pytest.raises(CommandArgumentError, match="CUSTOM takes exactly"):
        helpers.free_stream(script, "CUSTOM", profile="C:/profiles/shear.txt", rpm=100.0)
    with pytest.raises(CommandArgumentError, match="CONSTANT takes no further input"):
        helpers.free_stream(script, "CONSTANT", rpm=100.0)
    helpers.free_stream(script, "CUSTOM", profile="C:/profiles/shear.txt", filetype="STRUCTURED")
    assert "SET_FREESTREAM CUSTOM STRUCTURED\nC:/profiles/shear.txt" in script.render()


def test_atmosphere_paths_are_mutually_exclusive():
    script = Script(version="26.12")
    with pytest.raises(CommandArgumentError, match="not both"):
        helpers.atmosphere(script, altitude=1000.0, density=1.2)
    with pytest.raises(CommandArgumentError, match="all five fluid properties"):
        helpers.atmosphere(script, density=1.2, pressure=101325.0)


def test_frame_reference_must_exist_before_citation():
    script = Script(version="26.12")
    script.declare_existing(actuators=1)
    with pytest.raises(ScriptReferenceError, match="declare_existing"):
        script.emit("SET_ACTUATOR_AXIS", 1, 2, "X", 0.0)
    script.emit("CREATE_NEW_COORDINATE_SYSTEM")
    script.emit("SET_ACTUATOR_AXIS", 1, 2, "X", 0.0)


def test_actuator_and_motion_references_are_checked():
    script = Script(version="26.12")
    with pytest.raises(ScriptReferenceError, match="cites actuator 1"):
        script.emit("SET_PROP_ACTUATOR_RPM", 1, 900.0)
    with pytest.raises(ScriptReferenceError, match="cites motion 1"):
        script.emit("SET_MOTION_ROTOR_RPM", 1, 900.0)


def test_the_reference_frame_is_always_valid():
    script = Script(version="26.12")
    helpers.probes_from_file(script, "C:/probes/lattice.txt", units="METER", frame=1)
    assert "FRAME 1" in script.render()


def test_deleting_shrinks_the_reference_ledger():
    script = Script(version="26.12")
    script.emit("CREATE_NEW_ACTUATOR", "PROPELLER", name="prop")
    script.emit("DELETE_ACTUATOR", 1)
    with pytest.raises(ScriptReferenceError, match="cites actuator 1"):
        script.emit("ENABLE_ACTUATOR", 1)


def test_actuator_disc_needs_exactly_one_thrust_specification():
    script = Script(version="26.12")
    script.emit("CREATE_NEW_COORDINATE_SYSTEM")
    common = dict(frame=2, axis="X", offset=0.0, r_tip=0.9, r_hub=0.1, rpm=2000.0)
    with pytest.raises(CommandArgumentError, match="exactly one thrust specification"):
        helpers.actuator_disc(script, "p", **common)
    with pytest.raises(CommandArgumentError, match="exactly one thrust specification"):
        helpers.actuator_disc(script, "p", thrust=500.0, profile="C:/p.txt", **common)
    with pytest.raises(CommandArgumentError, match="needs n_blades"):
        helpers.actuator_disc(script, "p", profile="C:/p.txt", **common)
    with pytest.raises(CommandArgumentError, match="between 0 and 1"):
        helpers.actuator_disc(script, "p", thrust=500.0, swirl=1.2, **common)


def test_actuator_disc_returns_sequential_indices():
    script = Script(version="26.12")
    script.emit("CREATE_NEW_COORDINATE_SYSTEM")
    common = dict(axis="X", offset=0.0, r_tip=0.9, r_hub=0.1, rpm=2000.0, thrust=500.0)
    assert helpers.actuator_disc(script, "left", frame=2, **common) == 1
    assert helpers.actuator_disc(script, "right", frame=2, **common) == 2


def test_rotary_motion_all_boundaries_form_and_index():
    script = Script(version="26.12")
    script.emit("CREATE_NEW_COORDINATE_SYSTEM")
    motion_id = helpers.rotary_motion(script, frame=2, axis="X", rpm=1200.0)
    assert motion_id == 1
    assert "SET_MOTION_BOUNDARIES 1 -1" in script.render()


def test_sweep_requires_an_axis():
    script = Script(version="26.12")
    with pytest.raises(CommandArgumentError, match="at least one axis"):
        helpers.sweep(script)


def test_export_results_warns_on_the_deprecated_cp_variable():
    script = Script(version="26.12")
    with pytest.warns(UserWarning, match=r"CP_REFERENCE or CP_FREESTREAM \(SRC-003 p\.352\)"):
        helpers.export_results(script, vtk="C:/out/a.vtk", vtk_variables=["CP", "VX"])


# --- the solver's own on/off vocabulary in the helpers ----------------------


@pytest.mark.parametrize("written", ["DISABLE", "disable", " Disable "])
def test_a_toggle_written_in_the_solver_words_emits_that_state(written):
    # 'DISABLE' is a truthy Python string: read as a bare bool it would
    # emit ENABLE and invert the physics of the run in silence.
    script = Script(version="26.12")
    setup = helpers.solver_settings(script, viscous_coupling=written)
    assert "SET_SOLVER_VISCOUS_COUPLING DISABLE" in script.render()
    assert setup.flags["SET_SOLVER_VISCOUS_COUPLING"].value is False


#: Every solver_settings toggle, with the command it switches. The
#: helper unpacks them one by one, so a transposed line would invert two
#: flags of a real run; each pair is asserted rather than one sample.
SETTINGS_TOGGLES = [
    ("forced_iterations", "SOLVER_SET_FORCED_ITERATIONS"),
    ("viscous_coupling", "SET_SOLVER_VISCOUS_COUPLING"),
    ("reynolds_averaged_drag", "REYNOLDS_AVERAGED_DRAG_FORCES"),
    ("mesh_induced_wake_velocity", "SOLVER_SET_MESH_INDUCED_WAKE_VELOCITY"),
    ("unsteady_pressure_and_kutta", "SOLVER_UNSTEADY_PRESSURE_AND_KUTTA"),
    ("wake_on_wake_induction", "SET_WAKE_ON_WAKE_INDUCTION"),
    ("additional_wake_relaxation", "ADDITIONAL_WAKE_RELAXATION_ITERATION"),
]


@pytest.mark.parametrize(("argument", "command"), SETTINGS_TOGGLES)
def test_every_settings_toggle_reaches_its_own_command(argument, command):
    script = Script(version="26.12")
    setup = helpers.solver_settings(script, **{argument: "DISABLE"})
    assert f"{command} DISABLE" in script.render()
    assert setup.flags[command].value is False


#: One toggle per helper that takes them, with the arguments the helper
#: needs to reach its emissions, and a call state that already has
#: something in the script (so a late refusal would be visible).
HELPER_TOGGLES = [
    ("solver_settings", "viscous_coupling", {}),
    ("analysis_setup", "symmetry_loads", {}),
    ("initialize_solver", "wall_collision_avoidance", {}),
    ("sweep", "clear_solution", {"aoa": [0.0, 2.0]}),
    ("export_results", "vtk_wake", {"spreadsheet": "loads.txt"}),
    ("export_probes", "update", {"path": "C:/out/probes.txt"}),
    ("sweep", "start", {"aoa": [0.0]}),
    (
        "actuator_disc",
        "enable",
        {
            "name": "prop",
            "frame": 1,
            "axis": "X",
            "offset": 0.0,
            "r_tip": 0.9,
            "r_hub": 0.1,
            "rpm": 2400.0,
        },
    ),
]


@pytest.mark.parametrize(("helper", "argument", "arguments"), HELPER_TOGGLES)
def test_a_toggle_outside_both_vocabularies_refuses_before_emitting(helper, argument, arguments):
    script = Script(version="26.12")
    with pytest.raises(
        CommandArgumentError,
        match=rf"{helper}: {argument} takes True or False, or the solver's "
        r"own ENABLE or DISABLE; got 'YES'",
    ):
        getattr(helpers, helper)(script, **{argument: "YES"}, **arguments)
    assert script.render() == "\n"  # nothing was emitted


def test_analysis_setup_reads_the_solver_words_too():
    script = Script(version="26.12")
    # symmetry_loads is an init-phase setting, so it goes before the
    # solver starts and the analysis selections after it.
    helpers.analysis_setup(script, symmetry_loads="ENABLE")
    script.emit("START_SOLVER")
    helpers.analysis_setup(script, inviscid_only="DISABLE")
    text = script.render()
    assert "SET_ANALYSIS_SYMMETRY_LOADS ENABLE" in text
    assert "SET_INVISCID_LOADS DISABLE" in text


def test_the_export_refusal_does_not_consume_the_deferred_selection():
    # export_results flushes the induced-drag selection; a refusal after
    # that flush would leave the selection unrecoverable on a retry.
    script = Script(version="26.12")
    helpers.solver_settings(script, vorticity_drag_boundaries="all")
    script.emit("START_SOLVER")
    with pytest.raises(CommandArgumentError, match="vtk_wake"):
        helpers.export_results(script, spreadsheet="loads.txt", vtk_wake="YES")
    helpers.export_results(script, spreadsheet="loads.txt")
    assert "SET_VORTICITY_DRAG_BOUNDARIES -1" in script.render()


# --- the toggle resolver itself ---------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [(True, True), (False, False), ("ENABLE", True), ("disable", False), (" Enable ", True)],
)
def test_resolve_toggle_accepts_both_vocabularies(value, expected):
    assert resolve_toggle(value, context="x") is expected


@pytest.mark.parametrize("value", [1, 0, None, "", "true", "yes", "on", "MAYBE", 1.0])
def test_resolve_toggle_refuses_everything_else(value):
    # 1 and 0 are refused deliberately: accepting them would put the
    # decision back on truthiness, which is what inverted 'DISABLE'.
    with pytest.raises(ValueError, match="takes True or False, or the solver's own"):
        resolve_toggle(value, context="a flag")


def test_the_vocabulary_cannot_be_extended_at_runtime():
    # A writable vocabulary would let one caller change what every
    # helper and every settings field accepts, process wide.
    with pytest.raises(TypeError):
        SOLVER_TOGGLE_WORDS["ON"] = True


@pytest.mark.parametrize(
    ("call", "expected"),
    [
        (lambda script: helpers.sweep(script, aoa=[0.0], start="DISABLE"), "SWEEPER_START"),
        (
            lambda script: helpers.export_probes(script, "C:/out/p.txt", update="DISABLE"),
            "UPDATE_PROBE_POINTS",
        ),
    ],
)
def test_a_gate_written_in_the_solver_words_gates(call, expected):
    # These two decide whether a command is emitted at all, so reading
    # them as bare truthiness would run what the caller switched off.
    script = Script(version="26.12")
    call(script)
    assert expected not in script.render()


def test_a_per_surface_flag_in_the_solver_words_renders_that_state():
    script = Script(version="26.12")
    helpers.initialize_solver(script, surfaces=[(1, "DISABLE"), (2, True)])
    assert "1,DISABLE" in script.render() and "2,ENABLE" in script.render()


def test_a_per_surface_flag_outside_both_vocabularies_refuses():
    script = Script(version="26.12")
    with pytest.raises(CommandArgumentError, match="initialize_solver: surfaces"):
        helpers.initialize_solver(script, surfaces=[(1, "YES")])
    assert script.render() == "\n"
