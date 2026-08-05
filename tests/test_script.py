"""Tier 1: script builder validation, phase ordering, and goldens."""

from pathlib import Path

import pytest

from pyflightstream.commands import CommandNotInVersionError, CommandRegistry, Status
from pyflightstream.script import (
    BrokenCommandError,
    CommandArgumentError,
    Script,
    ScriptLineBreakError,
    ScriptOrderError,
    _check_list,
)
from pyflightstream.versions import known_versions

GOLDENS = Path(__file__).parent / "goldens"


def build_steady_polar(script: Script) -> None:
    script.comment("Golden: minimal steady polar point for FlightStream 26.120")
    script.emit("OPEN", "C:/cases/wing.fsm")
    script.emit("SET_SIMULATION_LENGTH_UNITS", "METER")
    script.emit("AUTO_DETECT_TRAILING_EDGES")
    script.emit("AUTO_DETECT_WAKE_TERMINATION_NODES")
    script.emit("SET_FREESTREAM", "CONSTANT")
    # AIR_ALTITUDE is recorded broken on 26.120, so the emitter refuses
    # it without a waiver (FR-48). Waived here at zero, the one altitude
    # the recorded METERS-as-FEET defect cannot change. The golden text
    # is unchanged by this call, which is the point of asserting it
    # below: a waiver records a fact about the run and emits no line.
    script.allow_broken(
        "AIR_ALTITUDE",
        reason="sea level, where the recorded units defect changes nothing",
    )
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
    script = Script(version="26.120")
    build_steady_polar(script)
    golden = (GOLDENS / "steady_polar_26.120.txt").read_text(encoding="utf-8")
    assert script.render() == golden
    assert not script.raw_flag


def test_removed_command_raises_with_citation():
    script = Script(version="26.120")
    with pytest.raises(CommandNotInVersionError, match=r"SRC-003 p\.328"):
        script.emit("SONIC_VELOCITY", 340.0)


def test_phase_order_is_enforced_with_a_didactic_message():
    script = Script(version="26.120")
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
    script = Script(version="26.120")
    script.emit("START_SOLVER")
    script.emit("PRINT", "solver finished")
    script.emit("SAVEAS", "C:/cases/wing_done.fsm")
    assert "PRINT solver finished" in script.render()


def test_enum_membership_and_case_normalization():
    script = Script(version="26.120")
    script.emit("SET_SOLVER_STEADY")
    script.emit("SET_BOUNDARY_LAYER_TYPE", "transitional")
    assert "SET_BOUNDARY_LAYER_TYPE TRANSITIONAL" in script.render()
    with pytest.raises(CommandArgumentError, match="LAMINAR, TRANSITIONAL, TURBULENT"):
        script.emit("SET_BOUNDARY_LAYER_TYPE", "INVISCID")


def test_argument_type_errors_cite_the_manual():
    script = Script(version="26.120")
    with pytest.raises(CommandArgumentError, match=r"SRC-003 p\.339"):
        script.emit("SOLVER_SET_ITERATIONS", "many")
    with pytest.raises(CommandArgumentError, match="requires argument"):
        script.emit("SET_TRAILING_EDGE_TYPE", 1)
    with pytest.raises(CommandArgumentError, match="no argument"):
        script.emit("SOLVER_SET_AOA", angle_of_attack=2.0)


def test_count_versus_list_consistency():
    script = Script(version="26.120")
    with pytest.raises(CommandArgumentError, match="declared count is 2"):
        script.emit("SET_VTK_EXPORT_VARIABLES", 2, "DISABLE", ["VX", "VY", "VZ"])


def test_payload_lines_rendering_with_newline_separator():
    script = Script(version="26.120")
    script.emit("SET_VTK_EXPORT_VARIABLES", 3, "DISABLE", ["CP_REFERENCE", "VX", "VTOT"])
    assert script.render() == ("SET_VTK_EXPORT_VARIABLES 3 DISABLE\nCP_REFERENCE\nVX\nVTOT\n\n")


def test_param_lines_rendering_mixes_keys_and_bare_paths():
    script = Script(version="26.120")
    script.emit("PROBE_POINTS_IMPORT", "INCH", 1, "C:/probes/lattice.txt")
    assert script.render() == (
        "PROBE_POINTS_IMPORT\nUNITS INCH\nFRAME 1\nC:/probes/lattice.txt\n\n"
    )


def test_inline_own_line_path_renders_after_the_command():
    script = Script(version="26.120")
    script.declare_existing(actuators=2)
    script.emit("SET_PROP_ACTUATOR_PROFILE", 2, "NEWTONS", 4, "C:/props/thrust.txt")
    assert script.render() == ("SET_PROP_ACTUATOR_PROFILE 2 NEWTONS 4\nC:/props/thrust.txt\n\n")


def test_comma_separated_payload_list():
    script = Script(version="26.120")
    script.declare_existing(motions=1)
    script.emit("SET_MOTION_BOUNDARIES", 1, 4, [1, 2, 3, 5])
    assert script.render() == "SET_MOTION_BOUNDARIES 1 4\n1,2,3,5\n\n"


def test_import_renders_the_manual_keyword_block():
    script = Script(version="26.120")
    script.emit("IMPORT", "METER", "STL", "C:/geometry/wing.stl", clear=True)
    assert script.render() == (
        "IMPORT\nUNITS METER\nFILE_TYPE STL\nFILE C:/geometry/wing.stl\nCLEAR\n\n"
    )


def test_import_without_clear_omits_the_presence_keyword():
    script = Script(version="26.120")
    script.emit("IMPORT", "METER", "TRI", "C:/geometry/wing.tri")
    rendered = script.render()
    assert "CLEAR" not in rendered
    assert "FILE_TYPE TRI" in rendered


def test_import_clear_must_be_a_bool():
    script = Script(version="26.120")
    with pytest.raises(CommandArgumentError, match="True or False"):
        script.emit("IMPORT", "METER", "STL", "C:/geometry/wing.stl", clear="CLEAR")


def test_ccs_import_renders_its_toggles_and_path():
    script = Script(version="26.120")
    script.emit("CCS_IMPORT", "ENABLE", "DISABLE", "ENABLE", "C:/geometry/model.csv")
    assert script.render() == (
        "CCS_IMPORT\nCLOSE_COMPONENT_ENDS ENABLE\nUPDATE_PROPERTIES DISABLE\n"
        "CLEAR_EXISTING ENABLE\nFILE C:/geometry/model.csv\n\n"
    )


def test_export_surface_mesh_takes_the_path_on_its_own_line():
    script = Script(version="26.120")
    script.emit("EXPORT_SURFACE_MESH", "OBJ", -1, "C:/geometry/all.obj")
    assert script.render() == "EXPORT_SURFACE_MESH OBJ -1\nC:/geometry/all.obj\n\n"


def test_raw_bypasses_validation_and_sets_the_flag():
    script = Script(version="26.120")
    script.raw("SOME_UNKNOWN_COMMAND 1 2")
    assert script.raw_flag
    assert "SOME_UNKNOWN_COMMAND 1 2" in script.render()


def test_two_scripts_do_not_share_state():
    first = Script(version="26.120")
    second = Script(version="26.120")
    first.emit("START_SOLVER")
    second.emit("CREATE_NEW_COORDINATE_SYSTEM")
    assert "CREATE_NEW_COORDINATE_SYSTEM" not in first.render()


def test_unsteady_monitoring_commands_render_the_manual_grammar():
    # 2026-07-21 case-reproduction backfill (SRC-003 pp.344-348, 355): the
    # unsteady plot blocks render exactly as the manual samples.
    script = Script(version="26.120")
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
    later = Script(version="26.120")
    later.emit("CREATE_BULK_SEPARATION", "GEAR", "FLAT_PLATE", 3, 0.2, [1, 3, 5])
    assert later.render() == "CREATE_BULK_SEPARATION GEAR FLAT_PLATE 3 0.2\n1,3,5\n\n"
    earlier = Script(version="26.101")
    earlier.emit("CREATE_BULK_SEPARATION", "GEAR", -1, 0.2)
    assert earlier.render() == "CREATE_BULK_SEPARATION GEAR -1 0.2\n\n"
    with pytest.raises(CommandArgumentError, match="no argument 'separation_type'"):
        Script(version="26.101").emit(
            "CREATE_BULK_SEPARATION",
            "GEAR",
            separation_type="FLAT_PLATE",
            num_boundaries=-1,
            diameter=0.2,
        )


def test_export_surface_sections_exists_only_from_26120():
    later = Script(version="26.120")
    later.emit("EXPORT_SURFACE_SECTIONS", 2)
    assert "EXPORT_SURFACE_SECTIONS 2" in later.render()
    with pytest.raises(CommandNotInVersionError, match="no recorded evidence"):
        Script(version="26.101").emit("EXPORT_SURFACE_SECTIONS", 2)


def test_volume_section_boundary_layer_is_removed_at_26120():
    earlier = Script(version="26.101")
    earlier.emit("VOLUME_SECTION_BOUNDARY_LAYER", 2, "DISABLE")
    assert "VOLUME_SECTION_BOUNDARY_LAYER 2 DISABLE" in earlier.render()
    with pytest.raises(CommandNotInVersionError, match=r"SRC-725 p\.365"):
        Script(version="26.120").emit("VOLUME_SECTION_BOUNDARY_LAYER", 2, "DISABLE")


def test_ccs_control_surface_space_axis_pair_is_26120_only():
    later = Script(version="26.120")
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
    earlier = Script(version="26.101")
    earlier.emit("NEW_CCS_WING_CONTROL_SURFACE", "Aileron", 0.5, 0.7, 0.15, 0.15, 0.5, 20.0, 0.001)
    with pytest.raises(CommandArgumentError, match="no argument 'space'"):
        Script(version="26.101").emit(
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
    script = Script(version="26.101")
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
    script = Script("26.120")
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
    script = Script("26.120")
    script.comment("hello\nSTART_SOLVER")
    lines = script.render().splitlines()
    assert lines == ["# hello", "# START_SOLVER"]
    assert script.raw_flag is False


def test_every_line_of_a_multi_line_comment_is_commented():
    """Including the blank one, which becomes a bare ``#`` and not a gap."""
    script = Script("26.120")
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
    script = Script("26.120")
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
    script = Script("26.120")
    with pytest.raises(ScriptLineBreakError):
        script.emit("IMPORT", "METER", "STL", "wing.stl\n")


def test_raw_remains_the_sanctioned_route_and_still_flags():
    """The refusal has an answer, and the answer is the one that records itself.

    This is the control for the whole group: if unvalidated text could not be
    appended at all, the fix would have removed a capability rather than
    closed a hole.
    """
    script = Script("26.120")
    script.raw("START_SOLVER")
    assert "START_SOLVER" in script.render()
    assert script.raw_flag is True


def test_an_ordinary_path_still_emits_unchanged():
    """The guard must not cost a legitimate call anything."""
    script = Script("26.120")
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
    script = Script("26.120")
    with pytest.raises(ScriptLineBreakError) as caught:
        script.emit("IMPORT", "METER", "STL", "wing.stl")
    assert "START_SOLVER" in str(caught.value)
    assert "START_SOLVER" not in script.render()


def test_every_declared_count_is_a_known_count_name():
    """A count argument the emitter does not recognise checks nothing.

    The count-versus-list consistency check keys on the ARGUMENT NAME
    (`_COUNT_ARG_NAMES`), because the vendor spells the count
    differently per command. So a command whose count carries a new
    spelling is emitted with no consistency check at all, and the
    solver, which reads the count and then that many tokens, consumes
    the following command line as data. That is a silent corruption of
    the script, not a syntax error, and nothing reported it.

    This walks the whole database and fails on any list argument the
    emitter would reach without a recognised count, so the next new
    spelling fails the suite instead of shipping unchecked. Two commands
    were escaping when it was written (PFS-8, 2026-08-02):
    UNSTEADY_SOLVER_NEW_FORCE_PLOT (`boundaries`) and
    ASSIGN_AEROELASTIC_COORDINATE_SYSTEMS (`num_index`).

    The walk mirrors `Script._check_counts` rather than approximating
    it, which is the correction of 2026-08-05. The approximation asked
    whether the LAST int before the list was a known count name, and the
    emitter asks whether a known count name was seen at all since the
    previous list; the two agree only while the count sits immediately
    before its list. CREATE_AXIAL_VORTEX_SEPARATION is the first entry
    where it does not (`num_boundaries` is the second argument and the
    index line is the last), so the approximation reported a defect the
    emitter does not have.

    Reading the emitter honestly opens a second question the
    approximation was accidentally answering, so it is asserted
    separately rather than folded in: an int scalar sitting BETWEEN the
    governing count and its list is a candidate for being the real
    count, in which case the emitter checks the list against the wrong
    number. Those are allowed only where the name is a recorded entity
    reference (`_SCALAR_REFERENCE_ARGS`, the frame and actuator indices),
    because that ledger is maintained for its own reasons and says what
    the argument is. An unrecognised int there fails.

    The walk covers the PER-VERSION argument overrides as well as the
    entry-level grammar, which the same pass added. The emitter runs
    against the per-version view, so an override is emitted and count
    checked like any other grammar, while the walk read only the
    entry-level tuple: a count spelled anew inside an override was the
    one shape of this defect the guard could not see.
    """
    from pyflightstream.commands import ArgType, CommandRegistry
    from pyflightstream.script import _COUNT_ARG_NAMES, _SCALAR_REFERENCE_ARGS

    unspelled: list[str] = []
    interleaved: list[str] = []
    lists_walked = 0
    grammars_walked = 0
    for name, entry in sorted(CommandRegistry.load().commands.items()):
        grammars = [(name, entry.args)]
        grammars += [
            (f"{name} ({version} override)", record.args)
            for version, record in sorted(entry.versions.items())
            if record.args
        ]
        for label, args in grammars:
            grammars_walked += 1
            governing: str | None = None
            pending: list[str] = []
            for spec in args:
                if spec.is_list:
                    lists_walked += 1
                    if governing is None:
                        if pending:
                            unspelled.append(f"{label}: {pending[-1]!r} introduces {spec.name!r}")
                    else:
                        for candidate in pending:
                            if candidate not in _SCALAR_REFERENCE_ARGS:
                                interleaved.append(
                                    f"{label}: {candidate!r} sits between {governing!r} "
                                    f"and {spec.name!r}"
                                )
                    governing, pending = None, []
                elif spec.name in _COUNT_ARG_NAMES:
                    governing, pending = spec.name, []
                elif spec.type is ArgType.INT:
                    pending.append(spec.name)
    assert not unspelled, (
        "these int arguments introduce a list with no recognised count before them, so "
        "their count is never checked against the list it declares; add the spelling to "
        "_COUNT_ARG_NAMES: " + "; ".join(unspelled)
    )
    assert not interleaved, (
        "these int arguments sit between a count and the list it governs, so if one of "
        "them is the real count the emitter is checking the list against the wrong "
        "number; name it in _COUNT_ARG_NAMES, or record it in _SCALAR_REFERENCE_ARGS if "
        "it cites an entity: " + "; ".join(interleaved)
    )
    # The walk is the guard, and it has two extents, so both are
    # floored: a refactor that stopped reaching list arguments, or one
    # that stopped reaching the per-version overrides, would satisfy
    # both assertions above by walking nothing.
    assert grammars_walked >= 165, (
        f"the walk reached {grammars_walked} grammars, fewer than the 165 the database "
        "carried when this floor was set (one per command plus one per version override); "
        "the overrides are the half that is easy to drop silently"
    )
    assert lists_walked >= 28, (
        f"the walk reached {lists_walked} list arguments, fewer than the 28 the database "
        "carried when this floor was set; the guard is no longer covering what it claims"
    )


@pytest.mark.parametrize(
    ("command", "kwargs", "list_arg"),
    [
        (
            "UNSTEADY_SOLVER_NEW_FORCE_PLOT",
            {
                "frame": 1,
                "units": "NEWTONS",
                "parameter": "CL",
                "name": "thrust",
                "boundaries": 2,
                "boundary_indices": [1, 2, 3],
            },
            "boundary_indices",
        ),
        (
            "ASSIGN_AEROELASTIC_COORDINATE_SYSTEMS",
            {"num_index": 2, "frame_indices": [2, 3, 4]},
            "frame_indices",
        ),
    ],
)
def test_the_two_commands_that_escaped_the_count_check_now_refuse(command, kwargs, list_arg):
    """The consequence of the fix, not just the shape of it.

    test_every_declared_count_is_a_known_count_name proves the argument
    NAME is in the checked set. That is the structural half and it would
    stay green if _check_counts itself regressed. These two pin the
    refusal on the exact commands that were escaping, so the check is
    tied to the commands rather than to a set literal.

    The consequence being prevented is not a syntax error: the solver
    reads the declared count and then that many tokens, so a short list
    makes it consume the following command line as data.
    """
    script = Script(version="26.120")
    script.entities.declare_boundaries(6)
    script.entities.declare("frames", 6)
    with pytest.raises(CommandArgumentError) as caught:
        script.emit(command, **kwargs)
    message = str(caught.value)
    assert "the declared count is 2" in message, message
    assert list_arg in message, message
    assert "SRC-003" in message, message


# --- FR-48: a command a probe measured broken is refused at emission ----
#
# PYFS-002 of the independent review. VersionView.__getitem__ refuses a
# REMOVED command and a command with no recorded evidence, and had no
# branch at all for BROKEN, so the one status backed by a probe that
# WATCHED the command fail was the one status the emitter ignored. The
# consequence is not a crash: the solver accepts the line, the run
# returns numbers, and nothing distinguishes them from right ones.


def _broken_pairs():
    """Every (canonical version, command) the database records broken.

    Read from the database rather than listed here, so a command
    promoted to broken by a future probe joins the guard on the day the
    promotion lands, with nobody remembering to add it.
    """
    registry = CommandRegistry.load()
    return [
        (version.canonical, name)
        for version in known_versions()
        for name, entry in sorted(registry.commands.items())
        if (record := entry.status_in(version)) is not None and record.status is Status.BROKEN
    ]


def test_the_broken_refusal_has_something_to_refuse():
    """Guard the guard: an empty parametrization passes silently.

    test_every_broken_record_is_refused_at_emission is parametrized from
    the database, so it would report green over zero cases if the last
    broken record were ever promoted away or lost in an edit. That is
    the failure mode where a guard stops guarding without failing, so
    the count is asserted separately.
    """
    pairs = _broken_pairs()
    assert len(pairs) >= 3, (
        "no command is recorded broken in any version, so the FR-48 refusal has "
        f"nothing to prove itself against; pairs found: {pairs}"
    )


@pytest.mark.requirement("FR-48")
@pytest.mark.parametrize(("canonical", "command"), _broken_pairs())
def test_every_broken_record_is_refused_at_emission(canonical, command):
    """The whole class, not the one command the review happened to name.

    Emitted with NO arguments on purpose. These commands share no
    grammar, and the refusal is a fact about the command rather than
    about the call, so it fires before argument binding; passing nothing
    is what lets one guard cover every one of them. If the check were
    ever moved below _bind, this test would report a
    CommandArgumentError instead and fail.

    The control at the end is not decoration. Without it, a mutation
    that refuses EVERY command (say, dropping the status test) leaves
    this test green while the emitter refuses to build anything.
    """
    script = Script(version=canonical)
    with pytest.raises(BrokenCommandError):
        script.emit(command)
    script.emit("NEW_SIMULATION")
    assert script.render().splitlines() == ["NEW_SIMULATION"], (
        "the refusal must not consume the script: nothing was appended for the "
        "refused command, and an unrelated command still emits"
    )
    assert script.broken_commands == ()


def test_the_broken_refusal_names_its_evidence_and_the_way_through():
    """A refusal the reader cannot act on is a refusal they will delete.

    Four things have to be in the message: which version (the same
    command is verified in 26.121), what was observed, the committed
    report that observed it, and the call that proceeds anyway. The
    manual citation comes along because every emission error carries
    one.
    """
    script = Script(version="26.120")
    with pytest.raises(BrokenCommandError) as caught:
        script.emit("AIR_ALTITUDE", 5000.0, "METERS")
    message = str(caught.value)
    assert "26.120" in message, message
    assert "reports/compat/CMP-26120_2026-07-23_pln012.yaml" in message, message
    assert "SRC-003 p.328" in message, message
    assert "allow_broken" in message, message


def test_the_same_command_emits_freely_in_the_version_that_fixed_it():
    """26.121 verified AIR_ALTITUDE, so 26.121 must not refuse it.

    The refusal reads the record of the TARGET version, not of the
    command. A guard keyed on the command name would pass every test
    above and quietly block the hotfix that repaired it.
    """
    script = Script(version="26.121")
    script.emit("AIR_ALTITUDE", 5000.0, "METERS")
    assert script.render().splitlines() == ["AIR_ALTITUDE 5000.0 METERS"]
    assert script.broken_commands == ()


def test_a_waiver_lets_the_command_emit_and_records_what_it_waived():
    """The second half of the assertion PYFS-002 owes.

    Refusing alone would be no fix: the probe layer must emit these
    commands, and an operator may know the defect misses their case. So
    the waiver emits, and what it emits is recorded with the evidence
    and the justification, which is what a manifest reader needs to
    judge the numbers later.
    """
    script = Script(version="26.120")
    script.allow_broken("AIR_ALTITUDE", reason="re-probing the units defect")
    script.emit("AIR_ALTITUDE", 5000.0, "METERS")
    assert script.render().splitlines() == ["AIR_ALTITUDE 5000.0 METERS"]
    (use,) = script.broken_commands
    assert use.command == "AIR_ALTITUDE"
    assert use.version == "26.120"
    assert use.report == "reports/compat/CMP-26120_2026-07-23_pln012.yaml"
    assert use.reason == "re-probing the units defect"
    assert use.note and "effect was not observed" in use.note


def test_a_waiver_records_one_entry_however_often_the_command_is_emitted():
    """One entry per command, and ``first_line`` holds the FIRST of them.

    The fields describing the breakage are properties of the command,
    the version and the waiver, so a second emission adds no fact.
    ``first_line`` is the exception and is why this test emits three
    different altitudes rather than the same one: the waiver is written
    for a particular call, a script-lifetime waiver covers every later
    one, and a reader who has only the reason cannot tell which emission
    it was written for. This assertion is what makes FIRST mean first;
    the field's other test emits once, so a last-wins implementation
    satisfies it.
    """
    script = Script(version="26.120")
    script.allow_broken("AIR_ALTITUDE", reason="re-probing the units defect")
    for altitude in (0.0, 1000.0, 5000.0):
        script.emit("AIR_ALTITUDE", altitude, "METERS")
    assert len(script.render().splitlines()) == 3
    assert len(script.broken_commands) == 1
    assert script.broken_commands[0].first_line == "AIR_ALTITUDE 0.0 METERS", (
        "first_line must hold the FIRST waived emission, not the latest; got "
        f"{script.broken_commands[0].first_line!r}"
    )


def test_a_waiver_needs_a_justification():
    """The reason is the only field nothing else can supply.

    A waiver without one records that the run leaned on a broken command
    and gives the reader no way to tell whether that was considered, so
    it is worth less than the refusal it replaces.
    """
    script = Script(version="26.120")
    with pytest.raises(CommandArgumentError, match="needs a reason"):
        script.allow_broken("AIR_ALTITUDE", reason="   ")
    with pytest.raises(BrokenCommandError):
        script.emit("AIR_ALTITUDE", 5000.0, "METERS")


def test_a_waiver_for_an_unknown_command_fails_where_the_typo_was_made():
    """Resolved through the version view, so a typo cannot sit silent.

    Left unchecked, `allow_broken("AIR_ALTITUD", ...)` would register a
    waiver nothing ever matches and the emission would refuse with a
    message about the command being broken, sending the reader to look
    at the database instead of at their own line.
    """
    script = Script(version="26.120")
    with pytest.raises(CommandNotInVersionError):
        script.allow_broken("AIR_ALTITUD", reason="typo")


def test_a_waiver_for_a_command_that_is_not_broken_here_records_nothing():
    """A recipe is version portable and the waiver has to be too.

    AIR_ALTITUDE is broken in 26.120 and verified in 26.121. One recipe
    is meant to run against both, so the waiver it carries for the first
    must be accepted by the second, and must NOT make the second report
    a dependency on a broken command that this version does not have.
    """
    script = Script(version="26.121")
    script.allow_broken("AIR_ALTITUDE", reason="broken in 26.120, harmless here")
    script.emit("AIR_ALTITUDE", 5000.0, "METERS")
    assert script.render().splitlines() == ["AIR_ALTITUDE 5000.0 METERS"]
    assert script.broken_commands == ()


# --- REV010-004: emit() type checked a FLOAT and NaN IS a float ------------
#
# Rendering is str(value), so the review's reproduction,
# Script("26.121").emit("SOLVER_SET_CONVERGENCE", math.nan), produced the
# line "SOLVER_SET_CONVERGENCE nan". SolverSettings guards finiteness at the
# layer above; emit is a documented public interface and goes past it.

_NON_FINITE = (float("nan"), float("inf"), float("-inf"))


@pytest.mark.parametrize("bad", _NON_FINITE)
def test_a_non_finite_float_argument_is_refused_at_emission(bad):
    script = Script("26.121")
    with pytest.raises(CommandArgumentError, match="not a finite number"):
        script.emit("SOLVER_SET_CONVERGENCE", bad)
    # And nothing reached the script: a refusal that still emitted would be
    # worse than no refusal, because the line would carry a reason for it.
    assert "nan" not in script.render().lower()
    assert "inf" not in script.render().lower()


@pytest.mark.parametrize("bad", _NON_FINITE)
def test_one_non_finite_element_of_a_float_list_is_refused(bad):
    """Per element: one NaN among finite neighbours is the case that reads
    as ordinary in the emitted line.

    Driven through the list validator with a REAL entry and a REAL spec
    taken from the command database, rather than through ``emit`` on a
    guessed argument order: the only FLOAT_LIST command in the registry
    takes an enum first, and a test that fought that would be testing
    argument dispatch instead of the finiteness rule.
    """
    entry, spec = _first_float_list_spec()
    assert spec is not None, "the registry has no FLOAT_LIST argument to drive"
    with pytest.raises(CommandArgumentError, match="not a finite number"):
        _check_list(entry, spec, [1.0, bad, 2.0])


def test_a_finite_float_list_passes_the_same_validator():
    """The control for the parametrized refusal above."""
    entry, spec = _first_float_list_spec()
    assert _check_list(entry, spec, [1.0, 2.0]) == [1.0, 2.0]


def _first_float_list_spec():
    """Return a real (entry, spec) pair with a FLOAT_LIST argument."""
    from pyflightstream.commands import ArgType

    for _, entry in sorted(CommandRegistry.load().commands.items()):
        for spec in entry.args:
            if spec.type is ArgType.FLOAT_LIST:
                return entry, spec
    return None, None


def test_a_finite_float_still_emits():
    """The control. Without it the refusals above would pass on a validator
    that rejected every float."""
    script = Script("26.121")
    script.emit("SOLVER_SET_CONVERGENCE", 1e-5)
    assert "SOLVER_SET_CONVERGENCE" in script.render()
    assert "1e-05" in script.render() or "0.00001" in script.render()
