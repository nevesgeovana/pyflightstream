"""Tier 1: curated helper layer, cross references, and helper goldens."""

import math
from pathlib import Path

import pytest

from pyflightstream.commands import CommandNotInVersionError
from pyflightstream.script import (
    BrokenCommandError,
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
    # Explicit properties rather than altitude=1000.0, which is what this
    # golden pinned until FR-48 landed. AIR_ALTITUDE is recorded broken on
    # 26.120: the observed density at 5000 m was the 5000 FOOT standard
    # state, so the METERS argument read as ignored and the pinned script
    # would not have solved at the altitude it names. Pinning that
    # rendering taught the one call this library exists to prevent. The
    # altitude path is still covered, on the version where the command
    # is recorded verified, by
    # test_the_altitude_path_is_pinned_where_the_command_works.
    helpers.atmosphere(
        script,
        density=1.225,
        pressure=101325.0,
        temperature=288.15,
        viscosity=1.789e-5,
        specific_heat_ratio=1.4,
    )
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
        # start_time=0.05 was pinned here until FR-48 landed.
        # SET_MOTION_START_TIME is recorded broken on 26.120 AND on
        # 26.121: the solver ABORTS script processing at the line, so
        # every command after it never ran. This golden therefore pinned
        # the text of a script that stops a third of the way through,
        # and unlike the altitude case there is no registered version
        # where the pin would be valid. The refusal is pinned instead,
        # by test_the_motion_start_time_path_refuses_on_every_version.
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
    script = Script(version="26.120")
    build_actuator_polar(script)
    golden = (GOLDENS / "actuator_polar_26.120.txt").read_text(encoding="utf-8")
    assert script.render() == golden
    assert not script.raw_flag


def test_rotor_unsteady_matches_the_golden():
    script = Script(version="26.120")
    build_rotor_unsteady(script)
    golden = (GOLDENS / "rotor_unsteady_26.120.txt").read_text(encoding="utf-8")
    assert script.render() == golden
    assert not script.raw_flag


def test_initialize_solver_periodic_requires_copies_and_only_then():
    script = Script(version="26.120")
    with pytest.raises(CommandArgumentError, match="PERIODIC symmetry appends"):
        helpers.initialize_solver(script, symmetry="PERIODIC")
    with pytest.raises(CommandArgumentError, match="PERIODIC symmetry appends"):
        helpers.initialize_solver(script, symmetry="MIRROR", periodic_copies=4)
    with pytest.raises(CommandArgumentError, match="positive count"):
        helpers.initialize_solver(script, symmetry="PERIODIC", periodic_copies=0)


def test_periodic_copies_join_the_symmetry_line():
    script = Script(version="26.120")
    helpers.initialize_solver(script, symmetry="PERIODIC", periodic_copies=6)
    assert "SYMMETRY PERIODIC 6" in script.render()


def test_surface_toggles_render_one_line_per_surface():
    script = Script(version="26.120")
    helpers.initialize_solver(script, surfaces=[(1, True), (3, False)])
    assert "SURFACES 2\n1,ENABLE\n3,DISABLE\n" in script.render()


def test_surface_toggle_count_mismatch_is_rejected_at_emit_level():
    script = Script(version="26.120")
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
    script = Script(version="26.120")
    with pytest.raises(CommandArgumentError, match="ROTATION takes exactly"):
        helpers.free_stream(script, "ROTATION", frame=2, axis="X")
    with pytest.raises(CommandArgumentError, match="CUSTOM takes exactly"):
        helpers.free_stream(script, "CUSTOM", profile="C:/profiles/shear.txt", rpm=100.0)
    with pytest.raises(CommandArgumentError, match="CONSTANT takes no further input"):
        helpers.free_stream(script, "CONSTANT", rpm=100.0)
    helpers.free_stream(script, "CUSTOM", profile="C:/profiles/shear.txt", filetype="STRUCTURED")
    assert "SET_FREESTREAM CUSTOM STRUCTURED\nC:/profiles/shear.txt" in script.render()


def test_atmosphere_paths_are_mutually_exclusive():
    script = Script(version="26.120")
    with pytest.raises(CommandArgumentError, match="not both"):
        helpers.atmosphere(script, altitude=1000.0, density=1.2)
    with pytest.raises(CommandArgumentError, match="all five fluid properties"):
        helpers.atmosphere(script, density=1.2, pressure=101325.0)


def test_frame_reference_must_exist_before_citation():
    script = Script(version="26.120")
    script.declare_existing(actuators=1)
    with pytest.raises(ScriptReferenceError, match="declare_existing"):
        script.emit("SET_ACTUATOR_AXIS", 1, 2, "X", 0.0)
    script.emit("CREATE_NEW_COORDINATE_SYSTEM")
    script.emit("SET_ACTUATOR_AXIS", 1, 2, "X", 0.0)


def test_actuator_and_motion_references_are_checked():
    script = Script(version="26.120")
    with pytest.raises(ScriptReferenceError, match="cites actuator 1"):
        script.emit("SET_PROP_ACTUATOR_RPM", 1, 900.0)
    with pytest.raises(ScriptReferenceError, match="cites motion 1"):
        script.emit("SET_MOTION_ROTOR_RPM", 1, 900.0)


def test_the_reference_frame_is_always_valid():
    script = Script(version="26.120")
    helpers.probes_from_file(script, "C:/probes/lattice.txt", units="METER", frame=1)
    assert "FRAME 1" in script.render()


def test_deleting_shrinks_the_reference_ledger():
    script = Script(version="26.120")
    script.emit("CREATE_NEW_ACTUATOR", "PROPELLER", name="prop")
    script.emit("DELETE_ACTUATOR", 1)
    with pytest.raises(ScriptReferenceError, match="cites actuator 1"):
        script.emit("ENABLE_ACTUATOR", 1)


def test_actuator_disc_needs_exactly_one_thrust_specification():
    script = Script(version="26.120")
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
    script = Script(version="26.120")
    script.emit("CREATE_NEW_COORDINATE_SYSTEM")
    common = dict(axis="X", offset=0.0, r_tip=0.9, r_hub=0.1, rpm=2000.0, thrust=500.0)
    assert helpers.actuator_disc(script, "left", frame=2, **common) == 1
    assert helpers.actuator_disc(script, "right", frame=2, **common) == 2


def test_rotary_motion_all_boundaries_form_and_index():
    script = Script(version="26.120")
    script.emit("CREATE_NEW_COORDINATE_SYSTEM")
    motion_id = helpers.rotary_motion(script, frame=2, axis="X", rpm=1200.0)
    assert motion_id == 1
    assert "SET_MOTION_BOUNDARIES 1 -1" in script.render()


def test_sweep_requires_an_axis():
    script = Script(version="26.120")
    with pytest.raises(CommandArgumentError, match="at least one axis"):
        helpers.sweep(script)


def test_export_results_warns_on_the_deprecated_cp_variable():
    script = Script(version="26.120")
    with pytest.warns(UserWarning, match=r"CP_REFERENCE or CP_FREESTREAM \(SRC-003 p\.352\)"):
        helpers.export_results(script, vtk="C:/out/a.vtk", vtk_variables=["CP", "VX"])


# --- the solver's own on/off vocabulary in the helpers ----------------------


@pytest.mark.parametrize("written", ["DISABLE", "disable", " Disable "])
def test_a_toggle_written_in_the_solver_words_emits_that_state(written):
    # 'DISABLE' is a truthy Python string: read as a bare bool it would
    # emit ENABLE and invert the physics of the run in silence.
    script = Script(version="26.120")
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
    script = Script(version="26.120")
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
    script = Script(version="26.120")
    with pytest.raises(
        CommandArgumentError,
        match=rf"{helper}: {argument} takes True or False, or the solver's "
        r"own ENABLE or DISABLE; got 'YES'",
    ):
        getattr(helpers, helper)(script, **{argument: "YES"}, **arguments)
    assert script.render() == "\n"  # nothing was emitted


def test_analysis_setup_reads_the_solver_words_too():
    script = Script(version="26.120")
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
    script = Script(version="26.120")
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
    script = Script(version="26.120")
    call(script)
    assert expected not in script.render()


def test_a_per_surface_flag_in_the_solver_words_renders_that_state():
    script = Script(version="26.120")
    helpers.initialize_solver(script, surfaces=[(1, "DISABLE"), (2, True)])
    assert "1,DISABLE" in script.render() and "2,ENABLE" in script.render()


def test_a_per_surface_flag_outside_both_vocabularies_refuses():
    script = Script(version="26.120")
    with pytest.raises(CommandArgumentError, match="initialize_solver: surfaces"):
        helpers.initialize_solver(script, surfaces=[(1, "YES")])
    assert script.render() == "\n"


# --- FR-48 reaches the curated helpers, because that is where recipes ---
# --- meet these commands. The two goldens above used to pin the two   ---
# --- paths below; the coverage moved here rather than disappearing.   ---


def test_the_altitude_path_is_pinned_where_the_command_works():
    """26.121 records AIR_ALTITUDE verified, so the helper renders it there.

    The actuator golden stopped pinning this rendering on 26.120, where
    the command is recorded broken. Losing the pin entirely would have
    traded one defect for a coverage hole, so it is asserted on the
    version where the command is recorded verified. Not "where the
    hotfix repaired it": RPT-014 declines that attribution, because the
    harness and the session file moved between the two runs too.
    """
    script = Script(version="26.121")
    helpers.atmosphere(script, altitude=1000.0)
    assert script.render().splitlines() == ["AIR_ALTITUDE 1000.0 METERS"]
    assert script.broken_commands == ()


def test_the_altitude_path_refuses_on_the_version_that_reads_metres_as_feet():
    """The helper is a caller, so the refusal has to reach through it.

    This is the call PYFS-002 was about: `atmosphere(altitude=1000.0)`
    against 26.120 built a script whose altitude the solver was measured
    not to apply as metres, and said nothing. A user reaches the emitter
    through the helpers far more often than through emit(), so a refusal
    that only fired at emit()
    would miss the path that matters.
    """
    script = Script(version="26.120")
    with pytest.raises(BrokenCommandError) as caught:
        helpers.atmosphere(script, altitude=1000.0)
    assert "AIR_ALTITUDE" in str(caught.value)
    assert script.render() == "\n"


def test_the_altitude_path_still_works_under_a_waiver():
    """The waiver rides on the script, so every helper honours it.

    Registering it on the Script rather than passing it through each
    helper signature is what makes this true without every helper
    growing an argument for it.
    """
    script = Script(version="26.120")
    script.allow_broken("AIR_ALTITUDE", reason="reproducing an older run")
    helpers.atmosphere(script, altitude=1000.0)
    assert script.render().splitlines() == ["AIR_ALTITUDE 1000.0 METERS"]
    assert [use.command for use in script.broken_commands] == ["AIR_ALTITUDE"]


@pytest.mark.parametrize("canonical", ["26.120", "26.121"])
def test_the_motion_start_time_path_refuses_on_every_version(canonical):
    """No registered version accepts SET_MOTION_START_TIME.

    Both records say the solver ABORTS script processing at the line, so
    everything after it never ran. The rotor golden used to pin exactly
    that script. Parametrized over both versions because the hotfix
    repaired AIR_ALTITUDE and did not repair this one, and a reader
    could reasonably assume otherwise.
    """
    script = Script(version=canonical)
    script.emit("CREATE_NEW_COORDINATE_SYSTEM")
    with pytest.raises(BrokenCommandError) as caught:
        helpers.rotary_motion(
            script,
            frame=2,
            axis="X",
            rpm=1200.0,
            boundaries=[1, 2],
            start_time=0.05,
        )
    assert "SET_MOTION_START_TIME" in str(caught.value)


def test_rotary_motion_without_a_start_time_needs_no_waiver():
    """The control: only the broken argument path is refused.

    Without this, a mutation refusing the whole helper would leave the
    test above green while rotary_motion stopped working at all.
    """
    script = Script(version="26.120")
    script.emit("CREATE_NEW_COORDINATE_SYSTEM")
    helpers.rotary_motion(script, frame=2, axis="X", rpm=1200.0, boundaries=[1, 2])
    rendered = script.render()
    assert "SET_MOTION_ROTOR_RPM 1 1200.0" in rendered
    assert "SET_MOTION_START_TIME" not in rendered


def test_sweep_emits_every_keyword_it_documents():
    """Coverage floor for the helper's own signature, not a golden.

    `velocity_file` had no test at all, so when the sweeper chapter was
    redrafted on 2026-08-06 and the velocity command gained the inline
    value list its three siblings already had, the path stopped being
    the second positional and started binding to `values`. The helper
    raised for every caller using that keyword and 1425 tests stayed
    green.

    The golden script exercises three of the eight keywords, which is
    what a golden is for. This walks the signature instead, so a
    keyword added without a test fails here rather than in a user's
    script.
    """
    import inspect

    script = Script(version="26.120")
    helpers.sweep(
        script,
        aoa=[-5.0, 0.0, 5.0],
        beta=[0.0, 2.0],
        velocity_file="C:/cases/vel.txt",
        clear_solution=True,
        ref_velocity_same=False,
        post_run_script="C:/cases/post.txt",
        start=True,
        export_spreadsheet="C:/cases/out.txt",
    )
    text = script.render()
    assert "SWEEPER_SET_AOA_SWEEP CUSTOM -5.0 0.0 5.0" in text
    assert "SWEEPER_SET_BETA_SWEEP CUSTOM 0.0 2.0" in text
    assert "SWEEPER_SET_VELOCITY_SWEEP CUSTOM C:/cases/vel.txt" in text
    assert "SWEEPER_CLEAR_SOLUTION ENABLE" in text
    assert "SWEEPER_REF_VELOCITY_SAME DISABLE" in text
    assert "SWEEPER_POST_RUN_SCRIPT ENABLE C:/cases/post.txt" in text
    assert "SWEEPER_START" in text
    assert "SWEEPER_EXPORT_SPREADSHEET C:/cases/out.txt" in text

    exercised = {
        "aoa",
        "beta",
        "velocity_file",
        "clear_solution",
        "ref_velocity_same",
        "post_run_script",
        "start",
        "export_spreadsheet",
    }
    declared = {
        name
        for name, parameter in inspect.signature(helpers.sweep).parameters.items()
        if parameter.kind is inspect.Parameter.KEYWORD_ONLY
    }
    assert declared == exercised, (
        "sweep's keyword-only parameters and the set this test emits have diverged: "
        f"untested {sorted(declared - exercised)}, gone {sorted(exercised - declared)}. "
        "Every keyword the helper offers must appear in a rendered line here, because "
        "the one that did not is the one that broke."
    )


def test_the_atmosphere_helper_serves_both_fluid_property_grammars():
    """The three older builds take a sonic velocity and no heat ratio.

    Entering their grammar on 2026-08-10 closed both doors at once until
    this helper learned to read its script's version: passing the five
    the newer builds take was refused by the binder for a keyword the
    edition does not have, and omitting one was refused by the helper
    itself, quoting a page of a DIFFERENT edition to a caller who was
    not reading it. The 25 series is the series registered so published
    work can be reproduced, so the curated path has to serve it.
    """
    older = Script(version="25.000")
    helpers.atmosphere(
        older,
        density=1.225,
        pressure=101325.0,
        temperature=288.15,
        viscosity=1.7894e-05,
        sonic_velocity=340.29,
    )
    lines = [line for line in older.render().splitlines() if line and not line.startswith("#")]
    assert "SONIC_VELOCITY 340.29" in lines
    assert not any(line.startswith("SPECIFIC_HEAT_RATIO") for line in lines)

    newer = Script(version="26.120")
    helpers.atmosphere(
        newer,
        density=1.225,
        pressure=101325.0,
        temperature=288.15,
        viscosity=1.7894e-05,
        specific_heat_ratio=1.4,
    )
    lines = [line for line in newer.render().splitlines() if line and not line.startswith("#")]
    assert "SPECIFIC_HEAT_RATIO 1.4" in lines
    assert not any(line.startswith("SONIC_VELOCITY") for line in lines)


def test_the_atmosphere_helper_names_the_build_when_the_fifth_property_is_wrong():
    """Both refusals name the caller's build and its own vocabulary.

    The old message quoted SRC-003 p.328 at every caller, which is the
    right page for five of the eight builds and a page about another
    document for the other three.
    """
    with pytest.raises(CommandArgumentError, match=r"25\.000 takes sonic_velocity"):
        helpers.atmosphere(
            Script(version="25.000"),
            density=1.0,
            pressure=1.0,
            temperature=1.0,
            viscosity=1.0,
            specific_heat_ratio=1.4,
        )
    with pytest.raises(CommandArgumentError, match=r"viscosity, sonic_velocity\) for .*25\.000"):
        helpers.atmosphere(
            Script(version="25.000"),
            density=1.0,
            pressure=1.0,
            temperature=1.0,
            viscosity=1.0,
        )


def _builds_where_air_altitude_works() -> list[str]:
    """Every registered build whose AIR_ALTITUDE row is not `broken`.

    Derived rather than listed, because the list is exactly what moves:
    the command is broken on four builds today, one of them inheriting
    that from its base, and a hardcoded set would either go stale or
    silently stop covering a build.
    """
    from pyflightstream.commands import CommandRegistry, Status
    from pyflightstream.versions import known_versions

    entry = CommandRegistry.load().commands["AIR_ALTITUDE"]
    working = []
    for version in known_versions():
        evidence = entry.evidence_in(version)
        if evidence is None or evidence.record.status is Status.BROKEN:
            continue
        working.append(version.canonical)
    # A derived parametrisation that empties turns the test into a
    # SKIP, silently, under pytest's default empty-parameter handling.
    # The population is four today and the check costs a line.
    assert working, (
        "AIR_ALTITUDE is broken on every registered build, so the test this feeds "
        "would be skipped rather than run. If that is really true, the helper's "
        "altitude path is unreachable everywhere and wants deleting, not skipping"
    )
    return working


@pytest.mark.parametrize("canonical", _builds_where_air_altitude_works())
def test_the_altitude_path_pins_the_unit_each_build_reads(canonical):
    """Parametrised over the builds, which is what would have caught it.

    The version dispatch added on 2026-08-10 was tested only on the half
    of this helper's signature it touched, and the other half was broken
    on 25.000 the whole time: that build's AIR_ALTITUDE takes a bare
    value and the helper always passed a units token, so there was no
    call to `atmosphere(script, altitude=...)` that worked there at all.
    The database already recorded the one-argument grammar four lines
    from the one the fix was written for.
    """
    script = Script(version=canonical)
    takes_units = canonical != "25.000"
    if takes_units:
        helpers.atmosphere(script, altitude=1000.0)
    else:
        helpers.atmosphere(script, altitude=1000.0, altitude_units="FEET")
    lines = [line for line in script.render().splitlines() if line and not line.startswith("#")]
    # THE UNIT, not just the number. Asserting the prefix alone passed
    # while the same call emitted 1000 metres on seven builds and 1000
    # FEET on the eighth, a factor of 3.28 with nothing to notice it:
    # 25.000 reads the bare value in feet (SRC-749 p.286) and the token
    # arrives at 25.100.
    assert lines[0] == ("AIR_ALTITUDE 1000.0 METERS" if takes_units else "AIR_ALTITUDE 1000.0")


def test_the_build_with_no_units_token_requires_the_unit_it_reads():
    """FEET is accepted there and silence is not, which is the whole point.

    A first version of this refused FEET, on the written ground that
    the unit was undocumented. SRC-749 p.286 documents it on the
    parameter row: the bare value is in feet. So the refusal named the
    one unit the page states and permitted the call that crosses the
    boundary silently, which is the gate inverted with respect to both
    hazards.
    """
    # Accepted, and emitted as the bare value that build takes.
    script = Script(version="25.000")
    helpers.atmosphere(script, altitude=5000.0, altitude_units="FEET")
    assert "AIR_ALTITUDE 5000.0" in script.render()

    # Silence is refused, because the same call is metres everywhere else.
    with pytest.raises(CommandArgumentError, match="reads it in FEET"):
        helpers.atmosphere(Script(version="25.000"), altitude=5000.0)

    # And a unit that build cannot honour is refused rather than dropped.
    with pytest.raises(CommandArgumentError, match="cannot be emitted or honoured"):
        helpers.atmosphere(Script(version="25.000"), altitude=5000.0, altitude_units="METERS")


def test_the_solver_initializer_says_it_cannot_serve_the_oldest_build():
    """A refusal naming a keyword the caller never typed is not a refusal.

    25.000's INITIALIZE_SOLVER takes ten arguments, has no SOLVER_MODEL
    and spells symmetry SYMMETRY_TYPE with its own tokens. This helper
    binds `solver_model` and `symmetry` from defaults, so a bare call
    on that build died inside the binder on a name the caller had not
    written. It says what it cannot do, and where to go instead.
    """
    with pytest.raises(CommandArgumentError, match="cannot express the INITIALIZE_SOLVER grammar"):
        helpers.initialize_solver(Script(version="25.000"))

    # And the seven it does serve are untouched.
    script = Script(version="26.120")
    script.declare_existing(boundaries=2)
    helpers.initialize_solver(script)
    assert "INITIALIZE_SOLVER" in script.render()


# --- PFS-2025.04: one motion-following frame per blade -----------------------


def _frame_blocks(text):
    """Return one dict per EDIT_COORDINATE_SYSTEM block in a script."""
    blocks = []
    current = None
    for line in text.splitlines():
        if line.strip() == "EDIT_COORDINATE_SYSTEM":
            current = {}
            blocks.append(current)
            continue
        if current is None or not line.strip():
            continue
        key, _, value = line.strip().partition(" ")
        if key in {"CREATE_NEW_COORDINATE_SYSTEM", "SET_MOTION_BOUNDARIES"}:
            current = None
            continue
        current[key] = value
    return blocks


def _axis(block, letter):
    return [float(block[f"VECTOR_{letter}_{c}"]) for c in "XYZ"]


def test_blade_frames_places_n_frames_at_360_over_n_and_binds_them():
    """N blades, N frames, 360/N apart, anchored on the first blade.

    The placement is arithmetic and not geometry: nothing reads the mesh
    and nothing computes a centroid. The anchor is the angle the user
    measured for Blade1, and the other N-1 follow from the blade count.
    """
    script = Script(version="26.120")
    indices = helpers.blade_frames(
        script,
        hub_origin=(1.2, 0.0, 0.3),
        rotor_axis="Z",
        n_blades=3,
        blade1_azimuth_deg=90.0,
    )
    assert indices == [2, 3, 4], "the created frames must be cited by creation order"

    blocks = _frame_blocks(script.render())
    assert len(blocks) == 3
    assert [block["NAME"] for block in blocks] == ["Blade1", "Blade2", "Blade3"]

    # x is radial, at 90, 210 and 330 degrees of azimuth about +Z, with
    # azimuth zero along +X (the cyclic datum for a Z rotor axis).
    expected = [(90.0, 210.0, 330.0)[i] for i in range(3)]
    for block, azimuth_deg in zip(blocks, expected, strict=True):
        radians = math.radians(azimuth_deg)
        assert _axis(block, "X") == pytest.approx(
            [math.cos(radians), math.sin(radians), 0.0], abs=1e-9
        )
        # z closes the right-handed triad and IS the rotor axis, which is
        # what makes the frame follow the motion about it.
        assert _axis(block, "Z") == pytest.approx([0.0, 0.0, 1.0], abs=1e-9)
        assert [float(block[f"ORIGIN_{c}"]) for c in "XYZ"] == [1.2, 0.0, 0.3]

    # The frames are what the motion is told to carry.
    helpers.rotary_motion(script, frame=indices[0], axis="Z", rpm=2400.0, moving_frames=indices)
    assert "SET_MOTION_MOVING_FRAMES 1 3\n2,3,4" in script.render()


def test_a_first_blade_off_the_four_anchor_angles_is_refused_with_its_angle():
    """The measured angle is named, and nothing is emitted.

    A blade at 37 degrees is a configuration this placement cannot serve,
    and the refusal has to name the number that was measured: a message
    naming only the four accepted angles sends the reader looking for a
    value it never printed.
    """
    script = Script(version="26.120")
    with pytest.raises(CommandArgumentError) as raised:
        helpers.blade_frames(
            script,
            hub_origin=(0.0, 0.0, 0.0),
            rotor_axis="Z",
            n_blades=3,
            blade1_azimuth_deg=37.0,
        )
    message = str(raised.value)
    assert "37.0" in message
    for anchor in ("0", "90", "180", "270"):
        assert anchor in message
    assert script.render() == "\n", "the refusal must leave the script untouched"


def test_the_azimuth_datum_is_one_named_table_and_changing_it_is_one_edit(monkeypatch):
    """The convention is a NAMED object, not a rule spread through code.

    The datum is the author's call and the lane built under a proposal
    (RPT-036). What the code owes that decision is a single place to
    apply it, so this test changes the table and watches every emitted
    frame follow.
    """
    assert helpers.AZIMUTH_BASIS["X"] == ((0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
    assert helpers.AZIMUTH_BASIS["Y"] == ((0.0, 0.0, 1.0), (1.0, 0.0, 0.0))
    assert helpers.AZIMUTH_BASIS["Z"] == ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0))

    script = Script(version="26.120")
    helpers.blade_frames(
        script, hub_origin=(0.0, 0.0, 0.0), rotor_axis="Z", n_blades=1, blade1_azimuth_deg=0.0
    )
    assert _axis(_frame_blocks(script.render())[0], "X") == pytest.approx([1.0, 0.0, 0.0])

    # Azimuth zero moved to +Y, and the emitted radial direction with it.
    monkeypatch.setitem(helpers.AZIMUTH_BASIS, "Z", ((0.0, 1.0, 0.0), (-1.0, 0.0, 0.0)))
    moved = Script(version="26.120")
    helpers.blade_frames(
        moved, hub_origin=(0.0, 0.0, 0.0), rotor_axis="Z", n_blades=1, blade1_azimuth_deg=0.0
    )
    assert _axis(_frame_blocks(moved.render())[0], "X") == pytest.approx([0.0, 1.0, 0.0])


def test_the_rotation_sense_decides_which_way_the_blades_are_numbered():
    """Blade2 follows Blade1 in the sense the propeller record states.

    Counterclockwise about the rotor axis is the mathematically positive
    sense, so the azimuths increase; clockwise numbers them the other
    way. Which of the two a propeller descriptor's own word means is the
    author's call (RPT-036); what is tested here is that the two words
    produce mirror-image placements rather than the same one.
    """
    forward = Script(version="26.120")
    helpers.blade_frames(
        forward,
        hub_origin=(0.0, 0.0, 0.0),
        rotor_axis="Z",
        n_blades=4,
        blade1_azimuth_deg=0.0,
        rotation="counterclockwise",
    )
    reverse = Script(version="26.120")
    helpers.blade_frames(
        reverse,
        hub_origin=(0.0, 0.0, 0.0),
        rotor_axis="Z",
        n_blades=4,
        blade1_azimuth_deg=0.0,
        rotation="clockwise",
    )
    second_forward = _axis(_frame_blocks(forward.render())[1], "X")
    second_reverse = _axis(_frame_blocks(reverse.render())[1], "X")
    assert second_forward == pytest.approx([0.0, 1.0, 0.0], abs=1e-9)
    assert second_reverse == pytest.approx([0.0, -1.0, 0.0], abs=1e-9)


@pytest.mark.parametrize(
    ("kwargs", "fragment"),
    [
        ({"n_blades": 0}, "0 blades"),
        ({"rotor_axis": "W"}, "'W'"),
        ({"rotation": "widdershins"}, "'widdershins'"),
        ({"names": ["only_one"]}, "1 name"),
    ],
)
def test_blade_frames_refuses_what_it_cannot_place(kwargs, fragment):
    """Every refusal names the value it got, and emits nothing."""
    script = Script(version="26.120")
    call = {
        "hub_origin": (0.0, 0.0, 0.0),
        "rotor_axis": "Z",
        "n_blades": 3,
        "blade1_azimuth_deg": 0.0,
    }
    call.update(kwargs)
    with pytest.raises(CommandArgumentError) as raised:
        helpers.blade_frames(script, **call)
    assert fragment in str(raised.value)
    assert script.render() == "\n"


# --- PFS-2025.14: rotating the existing mesh about a named frame -------------


def _rotor_script(canonical):
    script = Script(version=canonical)
    script.declare_existing(frames=1, boundaries={"Blade_1": 1, "Blade_2": 2, "Fuselage": 3})
    return script


def test_rotate_surfaces_emits_the_command_the_build_documents():
    """One capability, two command names, and never both.

    SURFACE_ROTATE is a keyword block of eight arguments and is removed
    at 26.122; ROTATE_SURFACE is the payload-lines command of six that
    replaces it. Exactly one of the two resolves on every registered
    build, so the helper picks rather than the caller.
    """
    older = _rotor_script("26.120")
    helpers.rotate_surfaces(older, frame=1, axis="X", angle_deg=5.0)
    text = older.render()
    assert "SURFACE_ROTATE" in text and "ROTATE_SURFACE" not in text
    assert "ANGLE 5.0" in text and "SURFACES -1" in text

    newer = _rotor_script("26.123")
    helpers.rotate_surfaces(newer, frame=1, axis="X", angle_deg=5.0)
    assert newer.render().strip() == "ROTATE_SURFACE 1 X 5.0 -1 DISABLE"


def test_rotate_surfaces_turns_one_component_into_every_blade_that_carries_it():
    """Writing Blade means all N of them, which is the whole ask.

    The blades are declared boundaries whose labels differ only in a
    trailing index, so the component is the label with that index taken
    off, matched without regard to case.
    """
    script = _rotor_script("26.123")
    helpers.rotate_surfaces(script, frame=1, axis="Z", angle_deg=-3.5, component="blade")
    assert script.render().strip() == "ROTATE_SURFACE 1 Z -3.5 2 DISABLE\n1,2", (
        "the two blades must be selected and the fuselage left alone"
    )


def test_rotate_surfaces_names_the_component_it_could_not_find():
    """An unknown component is refused naming it and the labels declared."""
    script = _rotor_script("26.123")
    with pytest.raises(ScriptReferenceError) as raised:
        helpers.rotate_surfaces(script, frame=1, axis="Z", angle_deg=1.0, component="Vane")
    message = str(raised.value)
    assert "'Vane'" in message
    assert "Blade_1" in message and "Fuselage" in message
    assert script.render() == "\n", "a refused selection must emit nothing"


def test_the_two_options_the_newer_command_dropped_are_refused_and_not_dropped():
    """A port that loses an option loses it loudly.

    SPLIT_VERTICES and ADAPTIVE_MESH have no equivalent on
    ROTATE_SURFACE. Emitting the newer command with those arguments
    quietly discarded would give the caller a mesh operation that did
    something else, on a build chosen for them by the helper.
    """
    script = _rotor_script("26.123")
    with pytest.raises(CommandArgumentError) as raised:
        helpers.rotate_surfaces(script, frame=1, axis="Z", angle_deg=1.0, split_vertices=True)
    message = str(raised.value)
    assert "split_vertices" in message
    assert "ROTATE_SURFACE" in message and "26.123" in message
    assert script.render() == "\n"

    # The same call is fine on the build whose command takes the option.
    older = _rotor_script("26.120")
    helpers.rotate_surfaces(older, frame=1, axis="Z", angle_deg=1.0, split_vertices=True)
    assert "SPLIT_VERTICES ENABLE" in older.render()


def test_rotate_surfaces_refuses_a_component_and_a_boundary_list_at_once():
    """Two selections is a question with no answer, so it is refused."""
    script = _rotor_script("26.123")
    with pytest.raises(CommandArgumentError, match="component"):
        helpers.rotate_surfaces(
            script, frame=1, axis="Z", angle_deg=1.0, component="Blade", boundaries=[1]
        )
    assert script.render() == "\n"


# --- PFS-2025.07: an action that exports without pausing the solver ----------


def test_the_unsteady_action_registers_and_states_the_evidence_it_rests_on():
    """The action is registered, and its evidence is stated once.

    The command is DOCUMENTED and unprobed, on 26.122 and 26.123 alone.
    A workflow that leans on it has to say so where a reader meets the
    run rather than leave the status to be looked up, so the helper
    records the status the build carries at the moment it emits.
    """
    script = Script(version="26.122")
    helpers.unsteady_action(
        script,
        name="sections",
        kind="SCRIPT",
        filename="actions/sections.txt",
        action_script="EXPORT_SOLVER_ANALYSIS_SPREADSHEET\nout/step.txt\n",
    )
    assert script.render().strip() == (
        "SET_NEW_UNSTEADY_SOLVER_ACTION SCRIPT sections\nactions/sections.txt"
    )

    (recorded,) = script.unsteady_actions
    assert recorded.name == "sections"
    assert recorded.kind == "SCRIPT"
    assert recorded.filename == "actions/sections.txt"
    assert recorded.evidence == "documented", (
        "the run record must carry the status the database holds for this build, "
        "not the assumption that a documented command works"
    )
    assert recorded.inherited is False

    # The child script travels with the parent, keyed by the path the
    # registration line names, so the run layer writes it where the
    # solver will look.
    assert script.pending_action_scripts == {
        "actions/sections.txt": "EXPORT_SOLVER_ANALYSIS_SPREADSHEET\nout/step.txt\n"
    }


def test_the_unsteady_action_refuses_on_a_build_that_does_not_carry_it():
    """No silent degradation onto a build without the command.

    The command is first documented by the 26.122 edition. On anything
    older the workflow must stop, naming the command and the build,
    rather than run a case whose sections never come out.
    """
    script = Script(version="26.120")
    with pytest.raises(CommandNotInVersionError) as raised:
        helpers.unsteady_action(
            script, name="sections", kind="SCRIPT", filename="actions/sections.txt"
        )
    message = str(raised.value)
    assert "SET_NEW_UNSTEADY_SOLVER_ACTION" in message
    assert "26.120" in message
    assert script.unsteady_actions == ()
    assert script.pending_action_scripts == {}


def test_two_actions_may_be_registered_and_a_repeated_name_may_not():
    """Several actions run in creation order; two of one name do not.

    The solver runs registered actions in the order they were created
    and the order cannot be changed afterwards, so the creation order is
    the whole of the caller's control over it and a repeated name is a
    citation nobody can resolve.
    """
    script = Script(version="26.123")
    helpers.unsteady_action(script, name="surface", kind="SCRIPT", filename="a/surface.txt")
    helpers.unsteady_action(script, name="volume", kind="SCRIPT", filename="a/volume.txt")
    assert [action.name for action in script.unsteady_actions] == ["surface", "volume"]

    with pytest.raises(CommandArgumentError) as raised:
        helpers.unsteady_action(script, name="surface", kind="SCRIPT", filename="a/again.txt")
    assert "'surface'" in str(raised.value)
    assert len(script.unsteady_actions) == 2


def test_two_actions_writing_one_file_are_refused_before_the_second_replaces_it():
    """One path, one file: the second write would silently win."""
    script = Script(version="26.123")
    helpers.unsteady_action(
        script, name="first", kind="SCRIPT", filename="a/step.txt", action_script="A\n"
    )
    with pytest.raises(CommandArgumentError) as raised:
        helpers.unsteady_action(
            script, name="second", kind="SCRIPT", filename="a/step.txt", action_script="B\n"
        )
    assert "a/step.txt" in str(raised.value)
    assert script.pending_action_scripts == {"a/step.txt": "A\n"}


def test_a_shell_action_carries_no_child_script_and_says_why():
    """COMMAND_LINE runs a shell command; there is no file to write."""
    script = Script(version="26.123")
    with pytest.raises(CommandArgumentError, match="COMMAND_LINE"):
        helpers.unsteady_action(
            script,
            name="wrapper",
            kind="COMMAND_LINE",
            filename="wrap.bat",
            action_script="echo\n",
        )
    helpers.unsteady_action(script, name="wrapper", kind="COMMAND_LINE", filename="wrap.bat")
    assert script.render().strip() == (
        "SET_NEW_UNSTEADY_SOLVER_ACTION COMMAND_LINE wrapper\nwrap.bat"
    )
    assert script.pending_action_scripts == {}


# --- PFS-2025.13: marking the trailing edge from the mesh, not by angle ------


@pytest.mark.parametrize("canonical", ["26.122", "26.123"])
def test_marking_from_an_imported_node_list_replaces_the_angle_criterion(canonical):
    """The imported route is emitted, and the angle route is not.

    Replacing rather than running beside: two marking passes over one
    geometry would mark by angle first and then again from the file, and
    a blade whose trailing edge is not a geometric crease is exactly the
    case the angle pass gets wrong.
    """
    script = Script(version=canonical)
    route = helpers.mark_wake_edges(script, edge_type="VORTEX_SHEDDING", tolerance=0.0001)
    assert route == "IMPORT_WAKE_EDGES_FROM_FILE"
    text = script.render()
    assert text.strip() == "IMPORT_WAKE_EDGES_FROM_FILE VORTEX_SHEDDING 0.0001"
    assert "AUTO_DETECT_TRAILING_EDGES" not in text


@pytest.mark.parametrize("canonical", ["26.120", "26.121"])
def test_a_build_without_the_import_route_is_told_so_and_not_marked_by_angle(canonical):
    """No silent fallback to the criterion this route exists to replace.

    The refusal fires before anything is emitted and names three things:
    the build, the route it cannot carry, and the angle criterion this
    library will not substitute for it without being asked.
    """
    script = Script(version=canonical)
    with pytest.raises(CommandNotInVersionError) as raised:
        helpers.mark_wake_edges(script, edge_type="VORTEX_SHEDDING", tolerance=0.0001)
    message = str(raised.value)
    assert canonical in message
    assert "IMPORT_WAKE_EDGES_FROM_FILE" in message
    assert "AUTO_DETECT_TRAILING_EDGES" in message
    assert script.render() == "\n", "a refused route must leave the script untouched"


def test_the_marking_helper_takes_no_path_because_the_command_takes_none():
    """The grammar is two arguments, and this helper invents no third.

    Neither edition that documents the command says where the node list
    comes from: not on its own line, not as a third argument, and not
    through a prior command. A path parameter here would be this library
    inventing a grammar, so the signature carries none and the silence
    stays visible.
    """
    import inspect

    parameters = inspect.signature(helpers.mark_wake_edges).parameters
    assert "path" not in parameters and "file" not in parameters
    assert set(parameters) == {"script", "edge_type", "tolerance"}


def test_exactly_one_rotation_command_resolves_on_every_registered_build():
    """The property the helper's choice actually rests on.

    Found by the adversarial pass: reversing ROTATION_COMMANDS broke
    nothing, because the order is irrelevant while exactly one of the two
    resolves per build. The order was not the thing to test; THIS is. If
    a build ever documents both, or neither, the helper is choosing
    rather than resolving and this turns red where the choice is made
    rather than in a script somebody reads next year.
    """
    from pyflightstream.commands import CommandRegistry
    from pyflightstream.versions import known_versions

    registry = CommandRegistry.load()
    for version in known_versions():
        view = registry.for_version(version)
        resolving = [name for name in helpers.ROTATION_COMMANDS if name in view]
        assert len(resolving) == 1, (
            f"FlightStream {version.canonical} resolves {resolving} of "
            f"{list(helpers.ROTATION_COMMANDS)}; the helper picks the first that "
            "resolves, which is a choice rather than a resolution as soon as the "
            "count is not one"
        )
