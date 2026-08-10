"""Tier 1: script builder validation, phase ordering, and goldens."""

import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from pyflightstream.commands import (
    ArgSpec,
    CommandEntry,
    CommandNotInVersionError,
    CommandRegistry,
    Status,
)
from pyflightstream.script import (
    BrokenCommandError,
    CommandArgumentError,
    Script,
    ScriptLineBreakError,
    ScriptOrderError,
    ScriptReferenceError,
    _check_list,
)
from pyflightstream.versions import known_versions

GOLDENS = Path(__file__).parent / "goldens"


def classify_count_spellings(label, args):
    """Report count-versus-list defects in one argument grammar.

    Extracted from the walk below so a FIXTURE can reach it. The walk
    itself cannot prove the rule: every count in the live database is
    correctly spelled, so the `unspelled` branch has no positive case
    and blinding it left the whole suite green. A guard whose only
    witness is data that happens not to exercise it is not a guard.

    Returns the unspelled findings, the interleaved findings, and how
    many list arguments were seen.
    """
    from pyflightstream.commands import ArgType
    from pyflightstream.script import _COUNT_ARG_NAMES

    unspelled: list[str] = []
    interleaved: list[str] = []
    lists = 0
    governing: str | None = None
    pending: list[ArgSpec] = []
    for spec in args:
        if spec.is_list:
            lists += 1
            # An ENTITY id before a list is not a count that went
            # unspelled, and naming it in _COUNT_ARG_NAMES would make the
            # emitter compare a motion index against the payload length.
            # SET_MOTION_6DOF_ACTIVE_VARIABLES is the case: six
            # preformatted toggle lines that nothing counts.
            #
            # The exemption reads the argument's OWN declaration and not
            # its name. It used to test membership of
            # _SCALAR_REFERENCE_ARGS, and the 2026-08-07 QA pass proved
            # that blind: renaming a real count to 'surface' left the
            # whole suite green while the emitter stopped checking it,
            # because 'surface' is a reference spelling somewhere else.
            # A name is a guess about an argument; `cites` is the
            # argument saying so.
            genuine = [held for held in pending if held.cites is None]
            if governing is None:
                if genuine:
                    unspelled.append(f"{label}: {genuine[-1].name!r} introduces {spec.name!r}")
            else:
                for candidate in genuine:
                    interleaved.append(
                        f"{label}: {candidate.name!r} sits between {governing!r} and {spec.name!r}"
                    )
            governing, pending = None, []
        elif spec.name in _COUNT_ARG_NAMES:
            governing, pending = spec.name, []
        elif spec.type is ArgType.INT:
            pending.append(spec)
    return unspelled, interleaved, lists


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

    One divergence from the emitter is left standing and is asserted
    dormant rather than described. `_check_counts` never resets its
    governing count after consuming a list, and this walk does, so on a
    grammar with TWO list arguments the emitter would check the second
    list against the first list's count while the walk reports nothing.
    No such grammar exists today, and the floor below fails the moment
    one is written, which is the point at which the two behaviours have
    to be reconciled deliberately.
    """
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
            found_unspelled, found_interleaved, lists = classify_count_spellings(label, args)
            unspelled += found_unspelled
            interleaved += found_interleaved
            lists_walked += lists
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
    # The walk is the guard, so its extent is asserted against a number
    # DERIVED FROM THE DATABASE rather than against a frozen literal.
    # The frozen form was measured to be worthless: `grammars_walked`
    # counts 162 commands plus 3 overrides, so the whole margin above a
    # literal floor of 165 is the override population, and three new
    # commands satisfy the floor with the override walk deleted. A
    # repository whose roadmap is 386 commands erases a frozen floor by
    # working.
    registry = CommandRegistry.load()
    expected_overrides = sum(
        1
        for entry in registry.commands.values()
        for record in entry.versions.values()
        if record.args
    )
    assert grammars_walked == len(registry.commands) + expected_overrides, (
        f"the walk reached {grammars_walked} grammars where the database holds "
        f"{len(registry.commands)} commands and {expected_overrides} per-version argument "
        "overrides; the overrides are the half that is easy to drop silently, and the "
        "emitter runs against them"
    )
    assert lists_walked == sum(
        1
        for entry in registry.commands.values()
        for args in [entry.args, *(r.args for r in entry.versions.values() if r.args)]
        for spec in args
        if spec.is_list
    ), "the walk did not reach every list argument the database declares"
    multi_list = sorted(
        name
        for name, entry in registry.commands.items()
        for args in [entry.args, *(r.args for r in entry.versions.values() if r.args)]
        if sum(1 for spec in args if spec.is_list) > 1
    )
    assert not multi_list, (
        f"grammars {multi_list} declare more than one list argument, where this walk and "
        "Script._check_counts diverge: the emitter keeps the governing count across a "
        "list and this walk resets it. Reconcile the two before the first such command "
        "ships, or the emitter checks the second list against the first list's count"
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
    assert "reports/compat/CMP-26120_2026-08-08_full.yaml" in message, message
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
    assert use.report == "reports/compat/CMP-26120_2026-08-08_full.yaml"
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


# --- the CAD body family ----------------------------------------------------
#
# The first chapter entered from a manual reading rather than from a case
# that needed it, so the tests are shaped by what could go wrong in that
# route: a per-edition citation carried across editions, an enum token
# read out of prose, and a phase that lets a geometry command follow the
# solver.


@pytest.mark.parametrize("version", ["26.100", "26.101", "26.120", "26.121"])
def test_the_cad_body_family_emits_on_every_registered_build(version):
    """Documented unchanged in all four editions, so all four must emit.

    A family recorded from one edition and cited from another is the
    defect the per-edition notes exist to prevent, and the cheapest way
    to notice it is to build the same script on every build.
    """
    script = Script(version=version)
    script.emit("CAD_BODY_DELETE", -1)
    script.emit("CAD_BODY_MIRROR", 1, "XZ")
    script.emit("CAD_BODY_ROTATE", 1, "Z", 15.0)
    script.emit("CAD_BODY_SCALE", 1, 0.001)
    script.emit("CAD_BODY_TRANSLATE", 1, 0.0, 0.5, 0.0, "METER")
    script.emit("CAD_BODY_SELECT_BY_THRESHOLD", 1, "Z", 0.0, "BELOW", "DELETE")
    text = script.render()
    assert "CAD_BODY_ROTATE 1 Z 15.0" in text
    assert "CAD_BODY_TRANSLATE 1 0.0 0.5 0.0 METER" in text
    assert "CAD_BODY_SELECT_BY_THRESHOLD 1 Z 0.0 BELOW DELETE" in text


@pytest.mark.parametrize(
    ("command", "args", "expected"),
    [
        ("CAD_BODY_MIRROR", (1, "XY_PLANE"), "XY, XZ, YZ"),
        ("CAD_BODY_ROTATE", (1, "W", 15.0), "X, Y, Z"),
        ("CAD_BODY_SELECT_BY_THRESHOLD", (1, "Z", 0.0, "OVER", "DELETE"), "ABOVE, BELOW"),
        ("CAD_BODY_SELECT_BY_THRESHOLD", (1, "Z", 0.0, "ABOVE", "KEEP"), "SELECT, DELETE"),
    ],
)
def test_a_cad_token_outside_the_documented_set_is_refused(command, args, expected):
    """The token lists were read from the manual's parameter table.

    Two of them (LOGIC and ACTION) were drafted with an extra token by
    the reading tool, which took CAD out of the sentence after the one
    that lists them, so these rows are the shape that defect would take
    if it reached a committed entry.
    """
    script = Script(version="26.120")
    with pytest.raises(CommandArgumentError, match=expected):
        script.emit(command, *args)


def test_a_cad_body_command_is_refused_after_the_solver_is_initialized():
    """Phase geometry: a CAD body exists before the mesh does."""
    script = Script(version="26.120")
    script.emit(
        "INITIALIZE_SOLVER",
        solver_model="INCOMPRESSIBLE",
        surfaces=-1,
        wake_termination_x="DEFAULT",
        symmetry="NONE",
    )
    with pytest.raises(ScriptOrderError, match="geometry"):
        script.emit("CAD_BODY_ROTATE", 1, "Z", 15.0)


def test_the_threshold_command_can_only_cite_the_reference_frame():
    """A narrowing this package chose, pinned so it is not a surprise.

    The command's FRAME argument is a coordinate system, and under the
    phase ordering it can only ever be the reference one: the CAD family
    is phase geometry, CREATE_NEW_COORDINATE_SYSTEM is phase setup, so a
    local frame created before the threshold command is refused and one
    created after cannot be cited by a line already emitted.

    Whether the SOLVER allows the other order is unmeasured
    (PLN-20260806-0900). Until it is, this is what the library does, and
    a test says so rather than a comment.
    """
    script = Script(version="26.120")
    script.emit("CAD_BODY_SELECT_BY_THRESHOLD", 1, "Z", 0.0, "BELOW", "DELETE")
    assert "CAD_BODY_SELECT_BY_THRESHOLD 1 Z 0.0 BELOW DELETE" in script.render()

    ordered = Script(version="26.120")
    ordered.emit("CREATE_NEW_COORDINATE_SYSTEM", label="body_axes")
    with pytest.raises(ScriptOrderError, match="geometry"):
        ordered.emit("CAD_BODY_SELECT_BY_THRESHOLD", "body_axes", "Z", 0.0, "BELOW", "DELETE")


# --- CAD Create: the pane settings and the basic shapes ---------------------


@pytest.mark.parametrize("version", ["26.100", "26.101", "26.120", "26.121"])
def test_the_cad_create_basics_emit_on_every_registered_build(version):
    """Documented unchanged in all four editions, so all four must emit."""
    script = Script(version=version)
    script.emit("CAD_CREATE_INITIALIZE")
    script.emit("SET_CAD_CREATE_MERGE_TOLERANCE", 10.0)
    script.emit("SET_CAD_CREATE_SPLINE_SEGMENTS", 250)
    script.emit("SET_CAD_CREATE_SPLINE_LOFT", "C0")
    script.emit("SET_CAD_CURVATURE_REFINEMENT", 120)
    script.emit("CAD_CREATE_BOX", 1, 0.5, 0.5, 0.5, 2.0, 2.0, 1.0)
    script.emit("CAD_CREATE_SPHERE", 1, 0.0, 0.0, 0.0, 2.0)
    script.emit("CAD_CREATE_CYLINDER", 1, 0.0, 0.0, 0.0, 0.1, 1.0, 3.0)
    script.emit("CAD_CREATE_SHEET", 1, "XZ", -0.5, 2.0, 3.0)
    text = script.render()
    assert "CAD_CREATE_BOX 1 0.5 0.5 0.5 2.0 2.0 1.0" in text
    assert "CAD_CREATE_CYLINDER 1 0.0 0.0 0.0 0.1 1.0 3.0" in text
    # A negative offset is documented and must survive rendering: the
    # sheet sits on either side of its plane.
    assert "CAD_CREATE_SHEET 1 XZ -0.5 2.0 3.0" in text


@pytest.mark.parametrize(
    ("command", "expected_default"),
    [
        ("SET_CAD_CREATE_MERGE_TOLERANCE", 1.0),
        ("SET_CAD_CREATE_SPLINE_SEGMENTS", 200),
        ("SET_CAD_CREATE_SPLINE_LOFT", "C2"),
        ("SET_CAD_CURVATURE_REFINEMENT", 80),
    ],
)
def test_the_cad_create_settings_record_the_default_the_manual_states(command, expected_default):
    """A documented default is evidence and is recorded with its citation.

    The four pane settings are the first CAD entries to carry `default`,
    and the field is only ever written where the manual states the value
    (invariant 3), which is why the citation travels with it.
    """
    entry = CommandRegistry.load().commands[command]
    assert entry.default == expected_default
    assert entry.default_ref, f"{command} records a default with no citation"
    assert entry.default_ref.startswith("SRC-")


def test_the_loft_type_takes_the_two_documented_tokens_and_no_other():
    script = Script(version="26.120")
    script.emit("SET_CAD_CREATE_SPLINE_LOFT", "C2")
    with pytest.raises(CommandArgumentError, match="C2, C0"):
        script.emit("SET_CAD_CREATE_SPLINE_LOFT", "C1")


def test_a_basic_shape_is_refused_after_the_solver_is_initialized():
    """Phase geometry: a CAD primitive is built before the mesh exists."""
    script = Script(version="26.120")
    script.emit(
        "INITIALIZE_SOLVER",
        solver_model="INCOMPRESSIBLE",
        surfaces=-1,
        wake_termination_x="DEFAULT",
        symmetry="NONE",
    )
    with pytest.raises(ScriptOrderError, match="geometry"):
        script.emit("CAD_CREATE_SPHERE", 1, 0.0, 0.0, 0.0, 1.0)


# --- CAD Create: virtual curves ---------------------------------------------


@pytest.mark.parametrize("version", ["26.100", "26.101", "26.120", "26.121"])
def test_the_virtual_curve_family_emits_on_every_registered_build(version):
    script = Script(version=version)
    script.emit("CAD_CREATE_CURVE_POINT", 0.0, 1.0, 0.0)
    script.emit("CAD_CREATE_CURVE_LINE", 0.0, 1.0, 0.0, 0.0, 2.0, 1.0)
    script.emit("CAD_CREATE_CURVE_ARC", 0.0, 0.0, 0.0, -1.0, 0.0, 0.0, 0.0, 1.0, 0.0)
    script.emit("CAD_CREATE_CURVE_SELECT", 2)
    script.emit("CAD_CREATE_CURVE_UNSELECT", -1)
    script.emit("CAD_CREATE_CURVE_REVERSE", 1)
    script.emit("CAD_CREATE_CURVE_DELETE_UNSELECTED")
    text = script.render()
    # The arc's nine coordinates in the manual's own sample order, whose
    # first triple is the ORIGIN and not a vertex.
    assert "CAD_CREATE_CURVE_ARC 0.0 0.0 0.0 -1.0 0.0 0.0 0.0 1.0 0.0" in text
    assert "CAD_CREATE_CURVE_SELECT 2" in text


@pytest.mark.parametrize(
    "command",
    ["CAD_CREATE_CURVE_SELECT", "CAD_CREATE_CURVE_UNSELECT", "CAD_CREATE_CURVE_REVERSE"],
)
def test_the_curve_index_commands_take_minus_one_for_every_curve(command):
    """-1 is the documented all-form and must not be refused as an index.

    Nothing in the emitter treats a curve index as an entity citation,
    deliberately: a virtual curve is not a mesh boundary and no
    inventory tracks it, so the value passes as an integer and the
    solver owns the range.
    """
    script = Script(version="26.120")
    script.emit(command, -1)
    assert f"{command} -1" in script.render()


@pytest.mark.parametrize(
    "command",
    [
        "CAD_CREATE_CURVE_DELETE_ALL",
        "CAD_CREATE_CURVE_DELETE_SELECTED",
        "CAD_CREATE_CURVE_DELETE_UNSELECTED",
    ],
)
def test_the_three_curve_deletes_take_no_argument(command):
    """They differ only in the set they act on, which is why none has one."""
    script = Script(version="26.120")
    script.emit(command)
    assert script.render().strip() == command
    with pytest.raises(CommandArgumentError, match="at most 0 arguments"):
        Script(version="26.120").emit(command, 1)


def test_the_curve_constructors_take_no_frame():
    """Unlike the basic shapes, which all take one.

    Pinned because the difference is invisible in the argument names and
    a reader coming from CAD_CREATE_BOX would reasonably pass a frame
    first, which would then be read as the X coordinate.
    """
    entries = CommandRegistry.load().commands
    for name in ("CAD_CREATE_CURVE_POINT", "CAD_CREATE_CURVE_LINE", "CAD_CREATE_CURVE_ARC"):
        assert not any(arg.name == "frame" for arg in entries[name].args), name
    for name in ("CAD_CREATE_BOX", "CAD_CREATE_SPHERE", "CAD_CREATE_CYLINDER"):
        assert entries[name].args[0].name == "frame", name


# --- CAD Create: transforming virtual curves ---------------------------------


@pytest.mark.parametrize("version", ["26.100", "26.101", "26.120", "26.121"])
def test_the_curve_transform_family_emits_on_every_registered_build(version):
    """Eight commands, one grammar, four editions.

    Each line here is the manual's own sample for that command, so the
    test doubles as the record that the emitter reproduces them.
    """
    script = Script(version=version)
    script.emit("CAD_CREATE_ROTATE_CURVES", 1, "2", 20.0, "DELETE")
    script.emit("CAD_CREATE_TRANSLATE_CURVES", 0.5, 0.5, -2.0, "DELETE")
    script.emit("CAD_CREATE_SCALE_CURVES", 2.5, "DELETE")
    script.emit("CAD_CREATE_PROJECT_CURVE", 6, 1, "XZ", 0.0, -1.0, 0.0, "RETAIN")
    script.emit("CAD_CREATE_PROJECT_MULTI_CURVE", 2, 3, 1, "XZ", "RETAIN")
    script.emit("CAD_CREATE_REORDER_CURVES", 1, "+Y")
    script.emit("CAD_CREATE_SELF_MEDIAN_FROM_CURVES")
    script.emit("CAD_CREATE_CONNECT_CURVES")
    text = script.render()
    assert "CAD_CREATE_PROJECT_MULTI_CURVE 2 3 1 XZ RETAIN" in text
    assert "CAD_CREATE_REORDER_CURVES 1 +Y" in text


def test_the_reorder_direction_is_signed_and_a_bare_axis_is_refused():
    """Six tokens, not three: the sign is half the instruction.

    Every other axis argument in this family takes a bare letter, so a
    caller reaching for consistency writes Y and means +Y. The manual
    lists only the signed forms, and a sort direction with no direction
    is not a thing the command can do.
    """
    script = Script(version="26.120")
    script.emit("CAD_CREATE_REORDER_CURVES", 1, "-Z")
    assert "CAD_CREATE_REORDER_CURVES 1 -Z" in script.render()
    with pytest.raises(CommandArgumentError, match="expects one of"):
        Script(version="26.120").emit("CAD_CREATE_REORDER_CURVES", 1, "Y")


def test_the_curve_rotation_takes_the_axis_index_as_well_as_the_letter():
    """The manual's own sample passes the index; the table names letters.

    Same reading as CAD_BODY_ROTATE, and pinned separately because the
    two entries are in different files and a later narrowing of one
    would not touch the other.
    """
    for axis in ("Y", "2"):
        script = Script(version="26.120")
        script.emit("CAD_CREATE_ROTATE_CURVES", 1, axis, 20.0, "RETAIN")
        assert f"CAD_CREATE_ROTATE_CURVES 1 {axis} 20.0 RETAIN" in script.render()


def test_the_projection_direction_is_not_optional():
    """Seven arguments, and the three in the middle are the vector.

    A caller who reads PROJECT_MULTI_CURVE first, which takes no vector
    because its guide curve supplies one, would reasonably try the same
    five-argument shape here and get a projection onto the plane along
    an unstated direction.

    Bound BY KEYWORD deliberately. Written positionally, the fourth
    value lands on `nx` and what fires is the float type check on the
    string, not the required-ness check this test is named for: marking
    nx, ny and nz optional would leave it green. The keyword form has no
    other argument to land on, and the match pins which refusal ran.
    """
    with pytest.raises(CommandArgumentError, match="requires argument 'nx'"):
        Script(version="26.120").emit(
            "CAD_CREATE_PROJECT_CURVE",
            curve_index=6,
            frame=1,
            plane="XZ",
            retain_curve="RETAIN",
        )


def test_exporting_curves_does_not_close_the_geometry_phase():
    """The judgement behind CAD_CREATE_CURVE_EXPORT_CCS carrying phase geometry.

    A phase is the position the ordering rule assigns a command, not a
    description of what it does. Filing a curve export under `export`
    because its name says EXPORT would let a script emit it once and
    then refuse every remaining CAD Create command, which is backwards
    for curves: export a set, build more, export another. The precedent
    is EXPORT_SURFACE_MESH, which writes a file at geometry time and is
    filed the same way.
    """
    script = Script(version="26.120")
    script.emit("CAD_CREATE_CURVE_SELECT", -1)
    script.emit("CAD_CREATE_CURVE_EXPORT_CCS", "first.csv")
    script.emit("CAD_CREATE_CURVE_LINE", 0.0, 0.0, 0.0, 1.0, 0.0, 0.0)
    script.emit("CAD_CREATE_CURVE_EXPORT_CCS", "second.csv")
    text = script.render()
    assert text.index("first.csv") < text.index("CAD_CREATE_CURVE_LINE") < text.index("second.csv")
    entries = CommandRegistry.load().commands
    assert entries["CAD_CREATE_CURVE_EXPORT_CCS"].phase == entries["EXPORT_SURFACE_MESH"].phase


def test_the_two_projections_disagree_about_where_their_curves_come_from():
    """Everything else in the family acts on the selection; these take indices.

    Pinned as a pair because the difference is the reason both exist,
    and because a reader who has just written CAD_CREATE_CURVE_SELECT
    would expect the projection to honour it.

    The selection-driven set is DERIVED rather than listed. Written as a
    six-name tuple it excluded whatever was added next, and the mirror
    command is already known to be coming: a transform landing outside
    the tuple would be silently unchecked by a test whose name claims to
    cover the family.
    """
    entries = CommandRegistry.load().commands
    transforms = {
        name
        for name in entries
        if name.startswith("CAD_CREATE_")
        and any(
            token in name
            for token in ("ROTATE", "TRANSLATE", "SCALE", "MIRROR", "PROJECT", "REORDER")
        )
    }
    projections = {"CAD_CREATE_PROJECT_CURVE", "CAD_CREATE_PROJECT_MULTI_CURVE"}
    assert projections <= transforms, "the derivation stopped finding the projections"
    for name in sorted(transforms - projections):
        assert not any("curve_index" in arg.name for arg in entries[name].args), (
            f"{name} names a curve by index; every transform but the two projections "
            "acts on the selection, and this one is outside that rule"
        )
    assert [arg.name for arg in entries["CAD_CREATE_PROJECT_CURVE"].args][0] == "curve_index"
    assert [arg.name for arg in entries["CAD_CREATE_PROJECT_MULTI_CURVE"].args][:2] == [
        "curve_index_1",
        "curve_index_2",
    ]


def test_every_cad_command_is_available_on_every_registered_build():
    """The four-build claim, walked from the chapter rather than listed.

    Three chapter tests above name their commands by hand, which is what
    a readable emission test should do. What they cannot do is carry the
    claim the chapter headers and the CHANGELOG make about the WHOLE
    chapter, and three of the entries entered with them
    (CAD_CREATE_CURVE_DELETE_ALL, CAD_CREATE_CURVE_DELETE_SELECTED,
    CAD_CREATE_CURVE_EXPORT_CCS) are exercised on 26.120 alone. An entry
    added tomorrow joins no hand-written list at all.

    So this derives the set from the chapter field and asserts the claim
    directly. It is not a duplicate of the emission tests: those check
    what a command renders, this checks that the chapter says what it
    says about every member of itself.
    """
    registry = CommandRegistry.load()
    members = sorted(
        name for name, entry in registry.commands.items() if entry.chapter in {"cad", "cad_create"}
    )
    assert len(members) >= 33, (
        f"the CAD chapters hold {len(members)} entries; the walk found fewer than the "
        "33 entered by 2026-08-06, so the chapter filter has stopped matching"
    )
    # The claim is about the builds the chapter ARRIVED on, and the
    # chapter arrived at 26.100: the CAD and cross-section families are
    # 75 of the commands 26.100 gained over 26.000 (RPT-024). So the
    # builds split in two and each half is pinned, rather than one being
    # skipped by name.
    #
    # Twice now a wider skip would have hidden something. The first
    # version skipped 26.000 by name and would have skipped three more
    # when they were registered. The second asserted the three carried
    # NO command at all, which was true for one day and stopped being
    # true the moment their own editions were read.
    available: dict[str, list[str]] = {}
    for version in known_versions():
        view = registry.for_version(version.canonical)
        available[version.canonical] = [name for name in members if name in view]

    whole = sorted(c for c, names in available.items() if len(names) == len(members))
    assert whole == ["26.100", "26.101", "26.120", "26.121", "26.122"], (
        "the builds carrying the CAD chapter WHOLE are " + ", ".join(whole) + "; the "
        "chapter arrives at 26.100 and every build from there on documents all of it"
    )

    # The older half carries a PART, and the part is pinned by size so
    # that a build losing rows shows up here. Zero would mean the build
    # was never read; the full 45 would mean the chapter did not arrive
    # at 26.100 after all.
    # 25.000 went from 15 to 16 when CAD_CREATE_AUTO_CROSS_SECTIONS was
    # read page against page. The mechanical sweep had withheld that row
    # because the declared arity disagreed with the heading, and the
    # disagreement was the finding rather than the error: that edition
    # takes one argument fewer, and the row it now carries states so.
    partial = {c: len(names) for c, names in available.items() if c not in whole}
    assert partial == {"25.000": 16, "25.100": 16, "26.000": 16}, (
        f"the pre-26.100 builds carry {partial} of the {len(members)} CAD commands; "
        "each of those counts is a measured edition surface, so a change here is "
        "either a sweep that found more or a row that was lost"
    )

    # And what they carry must be a SUBSET of the whole chapter, not a
    # different set: a command on an old build and on no new one would
    # mean the chapter is not simply growing.
    for canonical, names in available.items():
        assert set(names) <= set(members), canonical


# --- CAD Create: imports, cross-sections and the lofted meshes --------------


@pytest.mark.parametrize("version", ["26.100", "26.101", "26.120", "26.121"])
def test_the_remaining_cad_create_families_emit_on_every_registered_build(version):
    """Every line below is the manual's own sample for that command.

    The frame is declared rather than created: the samples cite frame 2
    and CREATE_NEW_COORDINATE_SYSTEM is a setup command, so a geometry
    command cannot follow one (PLN-20260806-0900).
    """
    script = Script(version=version)
    script.declare_existing(frames=2)
    script.emit("CAD_CREATE_IMPORT_CURVE_TXT", "METER", "2D", 2, "XZ", "curve.txt")
    script.emit("CAD_CREATE_IMPORT_CURVE_CCS", "FEET", 1, -1, "model.csv")
    script.emit("CAD_CREATE_IMPORT_CURVE_P3D", "METER", "FALSE", 2, -1, "grid.p3d")
    script.emit("CAD_CREATE_CROSS_SECTION", 1, "XZ", 0.0, 1, 3)
    script.emit("CAD_CREATE_AUTO_CROSS_SECTIONS", 1, "Y", 20, 1, "3", 1.2, "NONE", "MESH")
    script.emit("CAD_CREATE_AUTO_ANNULAR_CROSS_SECTIONS", 1, 20, 2)
    script.emit("CAD_CREATE_WING_MESH_FROM_CCS", "Wing", "TRUE", "BLUNT", "TRUE", "C2", "C0")
    script.emit("CAD_CREATE_FUSELAGE_MESH_FROM_CCS", "Fuselage", "TRUE", "C2", "C0")
    script.emit("CAD_CREATE_REVOLVE_MESH_FROM_CCS", "Pod", 1, "X", 0.0, 360.0, "TRUE", "C2", "C0")
    text = script.render()
    assert "CAD_CREATE_AUTO_CROSS_SECTIONS 1 Y 20 1 3 1.2 NONE MESH" in text
    assert "CAD_CREATE_IMPORT_CURVE_TXT METER 2D 2 XZ\ncurve.txt" in text


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("CAD_CREATE_AUTO_CROSS_SECTIONS", 8),
        ("CAD_CREATE_REVOLVE_MESH_FROM_CCS", 8),
    ],
)
def test_the_two_wrapped_signatures_carry_all_eight_arguments(command, expected):
    """Their manual headings WRAP, and the signature parser reports seven.

    `CAD_CREATE_AUTO_CROSS_SECTIONS` puts CAD_MESH alone on the second
    line and `CAD_CREATE_REVOLVE_MESH_FROM_CCS` puts LOFT_TYPE_V there,
    so a database drafted from the parsed signature would be one
    argument short on both and the shortfall would be silent: the
    emitter would accept a seven-token call and the solver would read
    the line differently. Both samples pass eight tokens, which is what
    settles it, and this pins the count against a future redraft.
    """
    entry = CommandRegistry.load().commands[command]
    assert len(entry.args) == expected, [arg.name for arg in entry.args]


def test_the_loft_direction_names_mean_different_things_per_command():
    """U and V index the component's parametric directions, not the model's.

    On the wing they are chordwise and spanwise; on the fuselage and the
    body of revolution they are radial and axial. The argument names are
    identical across the three, so a value carried across from one to
    another means something else, which is the reason this is a test and
    not only a note.
    """
    entries = CommandRegistry.load().commands
    for name in (
        "CAD_CREATE_WING_MESH_FROM_CCS",
        "CAD_CREATE_FUSELAGE_MESH_FROM_CCS",
        "CAD_CREATE_REVOLVE_MESH_FROM_CCS",
    ):
        names = [arg.name for arg in entries[name].args]
        assert names[-2:] == ["loft_type_u", "loft_type_v"], name
    assert "CHORDWISE" in entries["CAD_CREATE_WING_MESH_FROM_CCS"].notes.upper()
    assert "RADIAL" in entries["CAD_CREATE_FUSELAGE_MESH_FROM_CCS"].notes.upper()
    assert "RADIAL" in entries["CAD_CREATE_REVOLVE_MESH_FROM_CCS"].notes.upper()


def test_close_ends_accepts_the_documented_pair_and_the_printed_token():
    """The tables say OPEN or CLOSED and all three samples pass TRUE.

    Refusing either side would refuse something the manual states, so
    all three are accepted and the note records that only TRUE is
    evidenced by a printed call. Pinned because a later narrowing to the
    table's pair alone would silently reject every sample in the
    chapter.
    """
    for value in ("TRUE", "OPEN", "CLOSED"):
        script = Script(version="26.120")
        script.emit("CAD_CREATE_FUSELAGE_MESH_FROM_CCS", "Fuselage", value, "C2", "C0")
        assert f"CAD_CREATE_FUSELAGE_MESH_FROM_CCS Fuselage {value} C2 C0" in script.render()


def test_close_ends_does_not_accept_the_neighbouring_arguments_token():
    """FALSE belongs to MARK_TRAILING_EDGES and was pasted into CLOSE_ENDS.

    It shipped in the commit that entered these three commands, in the
    same file whose CAD_MESH argument refuses an invented token by name.
    No CLOSE_ENDS table and no CLOSE_ENDS sample carries FALSE in any of
    the four editions; MARK_TRAILING_EDGES, two rows above on the wing
    command, is where it comes from and legitimately keeps it.
    """
    entries = CommandRegistry.load().commands
    for name in (
        "CAD_CREATE_WING_MESH_FROM_CCS",
        "CAD_CREATE_FUSELAGE_MESH_FROM_CCS",
        "CAD_CREATE_REVOLVE_MESH_FROM_CCS",
    ):
        close_ends = next(a for a in entries[name].args if a.name == "close_ends")
        assert "FALSE" not in (close_ends.values or ()), name
    wing = entries["CAD_CREATE_WING_MESH_FROM_CCS"]
    marks = next(a for a in wing.args if a.name == "mark_trailing_edges")
    assert set(marks.values or ()) == {"TRUE", "FALSE"}, (
        "the control: the argument the token really belongs to must keep it"
    )
    with pytest.raises(CommandArgumentError, match="expects one of"):
        Script(version="26.120").emit(
            "CAD_CREATE_FUSELAGE_MESH_FROM_CCS", "Fuselage", "FALSE", "C2", "C0"
        )


def test_the_cad_mesh_selector_is_not_given_an_invented_token_set():
    """Only MESH is ever printed; the other spelling is a probe question.

    The manual describes the argument in prose and enumerates nothing,
    so an enum here would mean inventing the CAD token. This chapter
    made that mistake twice before the entries were reviewed, which is
    why the absence is pinned rather than left to a reader's judgement.
    """
    entry = CommandRegistry.load().commands["CAD_CREATE_AUTO_CROSS_SECTIONS"]
    cad_mesh = next(arg for arg in entry.args if arg.name == "cad_mesh")
    assert cad_mesh.values is None, (
        "cad_mesh was given a value set; the manual enumerates none and only MESH "
        "is printed, so any set here is invented rather than cited"
    )
    script = Script(version="26.120")
    script.emit("CAD_CREATE_AUTO_CROSS_SECTIONS", 1, "Y", 20, 1, "3", 1.2, "NONE", "CAD")
    assert "NONE CAD" in script.render()


# --- Mesh Operations --------------------------------------------------------


@pytest.mark.parametrize("version", ["26.100", "26.101", "26.120", "26.121"])
def test_the_mesh_operations_chapter_emits_on_every_registered_build(version):
    """Each line is the manual's own sample, including the two blocks.

    The frame is declared because the samples cite frame 3 and a
    coordinate system is created in the setup phase, which cannot
    precede a geometry command (PLN-20260806-0900).
    """
    script = Script(version=version)
    script.declare_existing(frames=3)
    script.emit(
        "SURFACE_ROTATE",
        frame=3,
        axis="X",
        angle=-20.0,
        surfaces=1,
        surface_indices=[2],
        split_vertices="DISABLE",
        adaptive_mesh="DISABLE",
        detach_normal_to_axis="ENABLE",
    )
    script.emit("TRANSLATE_SURFACE_IN_FRAME", 1, 0.0, 1.0, 1.4, "INCH", 3, "ENABLE")
    script.emit("TRANSLATE_SURFACE_BY_FRAME", 1, 3, 2)
    script.emit("SURFACE_SCALE", 1, 1.0, 0.5, 0.5, 2)
    script.emit("SURFACE_MIRROR", 1, 2, 2, "TRUE", "FALSE")
    script.emit("SURFACE_LINEAR_COPY_PASTE", 1, 4, 2, "METER", 0.5, -2.0, 0.0)
    script.emit("SURFACE_CIRCULAR_COPY_PASTE", 1, 2, "1", 10, 90.0)
    script.emit("SURFACE_COMBINE", 2, [1, 3])
    script.emit("SURFACE_AUTO_HOLE_FILL", 2)
    script.emit("SURFACE_INVERT", 2)
    script.emit("SURFACE_RENAME", 2, "Fuselage")
    script.emit("SELECT_MESH_NODE", 3)
    script.emit("TRANSFORM_SELECTED_NODES", 1, "TRANSLATION", -1.0, 0.0, 0.0)
    # Byte-exact, not spot checks. Three substrings out of thirteen
    # emitted commands left ten of the manual's own sample lines
    # asserted only for "does not raise", and the 2026-08-07 QA pass
    # measured what that costs: flipping SURFACE_SCALE to keyword_block
    # rendered a six-line block where the manual prints one inline line,
    # and the whole suite stayed green. These are deterministic ASCII.
    #
    # One golden for all four builds is the stronger claim: the four
    # editions document this chapter with the same grammar throughout,
    # so a per-version difference appearing here is itself the finding.
    golden = (GOLDENS / "mesh_operations_chapter.txt").read_text(encoding="utf-8")
    assert script.render() == golden


def test_the_all_surfaces_sentinel_is_zero_on_the_two_translations():
    """Minus one everywhere else, zero on these two, per the manual.

    The chapter never contrasts them, so a script reaching for -1 out of
    habit translates surface -1 rather than every surface.

    This test asserted only that the notes SAID so, on the reasoning
    that "nothing can refuse it, since both are valid integers". That
    reasoning was wrong and the 2026-08-07 review measured how wrong:
    the emitter refused the documented 0 and accepted the meaningless
    -1, exactly inverted, and the refusal message steered the caller to
    -1. The sentinel is a per-command fact, so it now lives on the
    argument (ArgSpec.all_sentinel) instead of being fixed per entity
    kind in the emitter, and this asserts the behaviour rather than the
    prose.
    """
    entries = CommandRegistry.load().commands

    for name, args in (
        ("TRANSLATE_SURFACE_IN_FRAME", (1, 0.0, 1.0, 1.4, "INCH")),
        ("TRANSLATE_SURFACE_BY_FRAME", (1, 2)),
    ):
        assert entries[name].args[-1 if name.endswith("BY_FRAME") else -2].all_sentinel == 0
        tail = ("ENABLE",) if name.endswith("IN_FRAME") else ()
        script = Script(version="26.120")
        script.declare_existing(boundaries=6, frames=2)
        script.emit(name, *args, 0, *tail)
        assert f"{name} " in script.render(), f"{name} must accept its documented 0"

        script = Script(version="26.120")
        script.declare_existing(boundaries=6, frames=2)
        with pytest.raises(ScriptReferenceError, match="0 selecting all boundaries"):
            script.emit(name, *args, -1, *tail)

    # The converse, so the two are not both simply permissive: every
    # other surface argument in the chapter keeps -1 and refuses 0.
    # Every command whose page states the -1 form, so none of the nine
    # declarations rests on the inventory literal in test_command_db
    # alone. The 2026-08-07 QA pass showed that literal is not a guard:
    # editing a declaration and its row together left the suite green
    # while the documented all-form became refused.
    for version, name, args, rendered in (
        ("26.120", "SURFACE_SCALE", (1, 2.0, 2.0, 2.0), "SURFACE_SCALE 1 2.0 2.0 2.0 -1"),
        ("26.120", "SURFACE_CUT_BY_PLANE", (1, "XZ", 0.5), "SURFACE -1"),
        ("26.120", "SURFACE_SELECT_BY_ID", (), "SURFACE_SELECT_BY_ID -1"),
        ("26.120", "SURFACE_INVERT", (), "SURFACE_INVERT -1"),
        ("26.100", "SELECT_GEOMETRY_BY_ID", (), "SELECT_GEOMETRY_BY_ID -1"),
        ("26.121", "DELETE_SURFACES", (), "DELETE_SURFACES -1"),
    ):
        script = Script(version=version)
        script.declare_existing(boundaries=6, frames=2)
        script.emit(name, *args, -1)
        assert rendered in script.render(), f"{name} must accept its documented -1"

        script = Script(version=version)
        script.declare_existing(boundaries=6, frames=2)
        with pytest.raises(ScriptReferenceError, match="-1 selecting all boundaries"):
            script.emit(name, *args, 0)

    # EXPORT_SURFACE_MESH separately: its path argument follows the
    # index, so it does not fit the trailing-index shape above.
    exporting = Script(version="26.120")
    exporting.declare_existing(boundaries=6)
    exporting.emit("EXPORT_SURFACE_MESH", "STL", -1, "all_surfaces.stl")
    assert "EXPORT_SURFACE_MESH STL -1" in exporting.render()
    refusing = Script(version="26.120")
    refusing.declare_existing(boundaries=6)
    with pytest.raises(ScriptReferenceError, match="-1 selecting all boundaries"):
        refusing.emit("EXPORT_SURFACE_MESH", "STL", 0, "x.stl")


def test_the_mirror_plane_is_an_index_and_refuses_a_plane_name():
    """The one plane argument in the database that is not a letter pair.

    SRC-003 p.311 gives 1 for YZ, 2 for XZ and 3 for XY. Every
    neighbouring command spells a plane with letters, so passing XZ here
    is the natural mistake and it must not silently become something
    else.
    """
    script = Script(version="26.120")
    script.declare_existing(boundaries=6, frames=2)
    script.emit("SURFACE_MIRROR", 1, 2, 2, "TRUE", "FALSE")
    assert "SURFACE_MIRROR 1 2 2 TRUE FALSE" in script.render()
    with pytest.raises(CommandArgumentError, match="expects an integer"):
        Script(version="26.120").emit("SURFACE_MIRROR", 1, 2, "XZ", "TRUE", "FALSE")


def test_the_renamed_selection_command_is_recorded_once_per_edition():
    """A rename the manual performs without ever stating a removal.

    SELECT_GEOMETRY_BY_ID is documented up to and including the February
    edition and SURFACE_SELECT_BY_ID in every edition after it, with the
    same argument and the same sample. Each carries only the versions
    that document it, so emitting the wrong one for a build is refused
    rather than silently accepted.

    The earlier half of that sentence was written as "the February
    edition alone" while 26.100 was the OLDEST registered build, which
    made a fact about the registry read as a fact about the vendor. The
    25 series and 26.000 document it too, so the boundary is where it
    STOPS, and that is what is asserted now.
    """
    registry = CommandRegistry.load()
    assert sorted(registry.commands["SELECT_GEOMETRY_BY_ID"].versions) == [
        "25.000",
        "25.100",
        "26.000",
        "26.100",
    ]
    assert sorted(registry.commands["SURFACE_SELECT_BY_ID"].versions) == [
        "26.101",
        "26.120",
        "26.121",
    ]
    Script(version="26.100").emit("SELECT_GEOMETRY_BY_ID", 2)
    Script(version="26.120").emit("SURFACE_SELECT_BY_ID", 2)
    with pytest.raises(CommandNotInVersionError):
        Script(version="26.120").emit("SELECT_GEOMETRY_BY_ID", 2)
    with pytest.raises(CommandNotInVersionError):
        Script(version="26.100").emit("SURFACE_SELECT_BY_ID", 2)


def test_the_two_surface_deletes_stop_at_the_edition_that_replaced_them():
    """SURFACE_DELETE and SURFACE_CLEARALL give way to DELETE_SURFACES.

    Six editions document the pair and the seventh documents the
    replacement instead. Neither is `removed`: this database promotes to
    that status only when a manual STATES a removal, and SRC-740 states
    nothing, it simply stops printing them.

    "Three editions" here meant the three registered when it was
    written. The 25 series and 26.000 document the pair too, so the fact
    is older than the registry was, and the boundary that matters is
    unchanged: the replacement arrives at 26.121.

    AND THE EMITTER STILL ACCEPTS THEM ON 26.121, which is asserted here
    rather than wished away. 26.121 is a real hotfix of 26.120 and
    inherits its records; inheritance is per version and cannot be
    denied per command, so a database that knows the 26.121 manual
    dropped these two has no way to say so (PLN-20260807-1010). Pinning
    the permissive behaviour is what makes the plan row's fix visible
    when it lands: this test will have to change.
    """
    registry = CommandRegistry.load()
    for name in ("SURFACE_DELETE", "SURFACE_CLEARALL"):
        entry = registry.commands[name]
        assert sorted(entry.versions) == [
            "25.000",
            "25.100",
            "26.000",
            "26.100",
            "26.101",
            "26.120",
        ], name
        assert all(r.status is Status.DOCUMENTED for r in entry.versions.values()), name
        evidence = entry.evidence_in(next(v for v in known_versions() if v.canonical == "26.121"))
        assert evidence is not None and evidence.inherited, (
            f"{name} reaches 26.121 by inheritance; if that stops being true the "
            "plan row has landed and this test states the old behaviour"
        )
    # Its replacement is documented by the two editions from 26.121 on,
    # which is the whole life of the command so far. The list is pinned
    # rather than counted so that a build joining it is a decision.
    assert sorted(registry.commands["DELETE_SURFACES"].versions) == ["26.121", "26.122"]


def test_the_untyped_axis_of_the_circular_pattern_has_no_invented_value_set():
    """Its parameter table enumerates nothing and only the index 1 is printed.

    SURFACE_ROTATE four entries above documents the dual letter-or-index
    form outright, so the likely set is not a mystery; it is uncited for
    THIS command, and this database has already shipped one invented
    token set by accident.
    """
    entry = CommandRegistry.load().commands["SURFACE_CIRCULAR_COPY_PASTE"]
    axis = next(arg for arg in entry.args if arg.name == "axis")
    assert axis.values is None
    rotate = CommandRegistry.load().commands["SURFACE_ROTATE"]
    rotate_axis = next(arg for arg in rotate.args if arg.name == "axis")
    assert set(rotate_axis.values or ()) == {"X", "Y", "Z", "1", "2", "3"}, (
        "the control: the sibling whose table DOES enumerate must carry the set"
    )


# --- Motion Definitions -----------------------------------------------------


def test_the_6dof_family_emits_the_manual_samples():
    """Every line here is the manual's own printed call."""
    script = Script(version="26.120")
    script.declare_existing(motions=1)
    script.emit("SET_MOTION_MASS_PROPERTIES", 1, 1200.5, 12.5, 45.3, 0.3, 0.0, 12.4, 13.5)
    script.emit("SET_MOTION_GRAVITY", 1, 0.0, 0.0, -9.81)
    script.emit("SET_MOTION_CUSTOM_TABLE", "VELOCITY-TIME", 1, "motion.txt")
    script.emit("SET_MOTION_6DOF_INITIAL_VELOCITY", 1, 10.0, 0.0, -25.0)
    script.emit("SET_MOTION_6DOF_INITIAL_ANGULAR_VELOCITY", 1, 0.0, 0.0, -0.25)
    script.emit(
        "SET_MOTION_6DOF_ACTIVE_VARIABLES",
        1,
        ["U DISABLE", "V DISABLE", "W DISABLE", "P DISABLE", "Q ENABLE", "R ENABLE"],
    )
    script.emit("SET_6DOF_MOTION_SYMMETRY_LOADS", 1, "ENABLE")
    script.emit("CREATE_NEW_6DOF_EXTERNAL_FORCE", 1, 0.0, -0.2, 1.2, 0.0, 0.25, -3000.0, 0.0, 0.0)
    script.emit("CREATE_NEW_6DOF_CUSTOM_FORCE", 1, "FORCE_VS_TIME", "profile.txt")
    script.emit(
        "CREATE_NEW_6DOF_SPRING_FORCE", 1, 0.0, -0.2, 1.2, 0.0, 0.0, -1.0, 0.1, 0.05, 0.06, 1e5
    )
    script.emit("DELETE_6DOF_EXTERNAL_FORCE", 1, 1)
    script.emit("EXPORT_6DOF_TRAJECTORY", 1, "traj.txt")
    # Byte-exact for the same reason as the Mesh Operations chapter
    # above: two substrings out of twelve commands checked two lines and
    # left ten asserted only for "does not raise".
    golden = (GOLDENS / "motion_6dof_family_26.120.txt").read_text(encoding="utf-8")
    assert script.render() == golden


def test_the_spring_force_carries_all_eleven_arguments():
    """Its heading wraps with SPRING_RATE alone on the second line.

    The third of the five wrapped signatures in the scripting reference
    and the largest shortfall of them after the rectangle volume
    section. A ten-argument entry would load and the emitter would
    accept a ten-token call.
    """
    entry = CommandRegistry.load().commands["CREATE_NEW_6DOF_SPRING_FORCE"]
    assert len(entry.args) == 11, [arg.name for arg in entry.args]
    rate = entry.args[-1]
    assert rate.name == "spring_rate" and rate.unit == "N/m"


def test_the_custom_table_takes_its_type_before_the_motion_id():
    """The only command in the chapter that does not open with MOTION_ID.

    Every sibling opens with the motion index, so writing it first here
    is the natural mistake. It is refused rather than misread, because
    an integer is not one of the two type tokens, and this pins that the
    order is the manual's and not a transcription slip.
    """
    entry = CommandRegistry.load().commands["SET_MOTION_CUSTOM_TABLE"]
    assert [arg.name for arg in entry.args][:2] == ["type", "motion_id"]
    script = Script(version="26.120")
    script.declare_existing(motions=1)
    with pytest.raises(CommandArgumentError, match="expects one of"):
        script.emit("SET_MOTION_CUSTOM_TABLE", 1, "VELOCITY-TIME", "motion.txt")


def test_the_three_motion_frames_are_each_recorded_where_they_apply():
    """Gravity is in the reference frame, the 6DOF state in the body frame.

    Three coordinate systems appear in this chapter and no argument name
    distinguishes them, so the notes are the only carrier. A script that
    sets gravity and an initial velocity writes two vectors into two
    different systems.
    """
    entries = CommandRegistry.load().commands
    assert "REFERENCE" in entries["SET_MOTION_GRAVITY"].notes.upper()
    for name in (
        "SET_MOTION_6DOF_INITIAL_VELOCITY",
        "SET_MOTION_6DOF_INITIAL_ANGULAR_VELOCITY",
        "CREATE_NEW_6DOF_EXTERNAL_FORCE",
    ):
        assert "BODY" in entries[name].notes.upper(), name
    assert "MOTION DEFINITION" in entries["SET_MOTION_VELOCITY"].notes.upper()


def test_the_pre_may_kinematic_family_stops_at_the_february_build():
    """Five commands with no successor, because the capability changed.

    The EUCLIDEAN motion of every edition up to February is set by
    velocity and acceleration directly; May's ROTARY motion is set by
    axis and RPM. So these are not renamed, they are gone, and the two
    rotor commands that replace the capability exist in no earlier
    edition.

    The name of this test said "that build alone" and meant it about
    26.100, which was the oldest registered build when it was written.
    Registering the 25 series and 26.000 showed the family reaching back
    through all of them, so the fact was never about February: it is
    about where the capability STOPS, which is unchanged.
    """
    registry = CommandRegistry.load()
    pre_may = (
        "SET_MOTION_VELOCITY",
        "SET_MOTION_ACCELERATION",
        "SET_MOTION_ANGULAR_VELOCITY",
        "SET_MOTION_ANGULAR_ACCELERATION",
        "SET_MOTION_IS_ROTOR",
    )
    for name in pre_may:
        assert sorted(registry.commands[name].versions) == [
            "25.000",
            "25.100",
            "26.000",
            "26.100",
        ], name
        Script(version="26.100").declare_existing(motions=1)
        with pytest.raises(CommandNotInVersionError):
            Script(version="26.120").emit(name, 1)
    for name in ("SET_MOTION_ROTOR_AXIS", "SET_MOTION_ROTOR_RPM"):
        assert "26.100" not in registry.commands[name].versions, name


def test_the_slipstream_stabilization_takes_two_arguments_in_february():
    """NUM_BLADES arrives with the rotary motion in the May edition.

    The entry carried the three-argument form and a 26.120 row alone, so
    the February grammar was neither recorded nor reachable. Emitting
    the blade count onto a February script passes an argument that build
    does not read.
    """
    february = Script(version="26.100")
    february.declare_existing(motions=1)
    february.emit("SET_MOTION_SLIPSTREAM_WAKE_STABILIZATION", 1, "ENABLE")
    assert february.render().strip() == "SET_MOTION_SLIPSTREAM_WAKE_STABILIZATION 1 ENABLE"
    with pytest.raises(CommandArgumentError, match="at most 2"):
        second = Script(version="26.100")
        second.declare_existing(motions=1)
        second.emit("SET_MOTION_SLIPSTREAM_WAKE_STABILIZATION", 1, "ENABLE", 4)

    current = Script(version="26.120")
    current.declare_existing(motions=1)
    current.emit("SET_MOTION_SLIPSTREAM_WAKE_STABILIZATION", 1, "ENABLE", 4)
    assert current.render().strip().endswith("ENABLE 4")


def test_the_count_spelling_rule_catches_a_real_unspelled_count():
    """The fixture the live walk cannot supply.

    Every count in the database is correctly spelled, so the walk's
    `unspelled` branch has no positive case and blinding it left the
    whole suite green. These two grammars are the two sides of the rule.
    """
    from pyflightstream.commands import ArgSpec

    unspelled, _, lists = classify_count_spellings(
        "X_CMD",
        [
            ArgSpec(name="how_many", type="int"),
            ArgSpec(name="values", type="int_list"),
        ],
    )
    assert lists == 1
    assert unspelled == ["X_CMD: 'how_many' introduces 'values'"], (
        "an int with an unrecognised name introducing a list is the defect this "
        "rule exists for, and it must be reported"
    )


def test_an_entity_id_before_a_list_is_not_an_unspelled_count():
    """The control, and the reason the rule was widened on 2026-08-07.

    SET_MOTION_6DOF_ACTIVE_VARIABLES puts a motion id before six
    preformatted toggle lines that nothing counts. Naming motion_id in
    _COUNT_ARG_NAMES to quiet the guard would have made the emitter
    compare a motion index against the payload length.

    The exemption is earned by the DECLARATION, not by the name: the
    same argument without ``cites`` is reported, which is the assertion
    below it.
    """
    from pyflightstream.commands import ArgSpec

    unspelled, interleaved, _ = classify_count_spellings(
        "X_CMD",
        [
            ArgSpec(name="motion_id", type="int", cites="motions"),
            ArgSpec(name="variables", type="str_list", separator="newline"),
        ],
    )
    assert unspelled == [] and interleaved == []


def test_an_undeclared_int_before_a_list_is_reported_whatever_it_is_called():
    """The hole the 2026-08-07 QA pass proved, now closed.

    The exemption used to test the argument's NAME against
    _SCALAR_REFERENCE_ARGS, so renaming a genuine count to a spelling
    that cites an entity somewhere else in the database silenced the
    guard while the emitter stopped comparing the count to its list. The
    mutation left the whole suite green.

    Both spellings below are entity-reference names. Neither declares
    ``cites``, so neither is exempt.
    """
    from pyflightstream.commands import ArgSpec

    for spelling in ("surface", "motion_id"):
        unspelled, _, _ = classify_count_spellings(
            "X_CMD",
            [
                ArgSpec(name=spelling, type="int"),
                ArgSpec(name="boundary_indices", type="int_list"),
            ],
        )
        assert unspelled, (
            f"an int named {spelling!r} introducing a list is exempt only when the "
            "argument declares the entity it cites; a name is a guess"
        )


def test_a_recognised_count_still_governs_its_list():
    """The other control: a correct grammar must report nothing.

    Without this the two tests above pass under a rule that reported
    every list, or none.
    """
    from pyflightstream.commands import ArgSpec

    unspelled, interleaved, _ = classify_count_spellings(
        "X_CMD",
        [
            ArgSpec(name="num_boundaries", type="int"),
            ArgSpec(name="boundary_indices", type="int_list"),
        ],
    )
    assert unspelled == [] and interleaved == []


# --- Solver Settings: the last three ----------------------------------------


@pytest.mark.parametrize("version", ["26.101", "26.120", "26.121"])
def test_the_thin_boundary_commands_emit_both_documented_forms(version):
    """The counted list and the -1 form, which takes no index line."""
    script = Script(version=version)
    script.declare_existing(boundaries=6)
    script.emit("SET_THIN_BOUNDARIES", 3, [1, 2, 4])
    script.emit("SET_THIN_BOUNDARIES", -1)
    script.emit("DELETE_THIN_BOUNDARIES")
    text = script.render()
    assert "SET_THIN_BOUNDARIES 3\n1,2,4\n" in text
    assert "SET_THIN_BOUNDARIES -1\n\n" in text


def test_thin_boundaries_are_absent_from_the_february_build():
    """They arrive with the May separation redesign, like the rest of it."""
    registry = CommandRegistry.load()
    for name in ("SET_THIN_BOUNDARIES", "DELETE_THIN_BOUNDARIES"):
        assert "26.100" not in registry.commands[name].versions, name
        with pytest.raises(CommandNotInVersionError):
            Script(version="26.100").emit(name)


def test_the_surface_roughness_height_is_recorded_in_nanometres():
    """Every other length in this database is metres or a frame's own unit.

    The manual states nanometres and the sample passes 23.5. Read as
    millimetres that is a roughness forty million times too large, and
    nothing downstream would object, so the unit is the fact worth
    pinning rather than the range.
    """
    entry = CommandRegistry.load().commands["SET_SURFACE_ROUGHNESS"]
    assert entry.args[0].unit == "nm"
    script = Script(version="26.120")
    script.emit("SET_SURFACE_ROUGHNESS", 23.5)
    assert script.render().strip() == "SET_SURFACE_ROUGHNESS 23.5"


def test_the_index_misspelling_is_not_mistaken_for_a_missing_command():
    """The Script Index spells the Stratford separation STARTFORD.

    A coverage sweep driven from the index reports that name as absent
    in every edition. The command is present under the spelling its
    chapter body and its sample use, which RPT-015 measured the solver
    accepting, so the gap is the index's and entering the misspelling
    would put a command that does not exist into the public surface.
    """
    registry = CommandRegistry.load()
    assert "CREATE_STRATFORD_BULK_SEPARATION" in registry.commands
    assert "CREATE_STARTFORD_BULK_SEPARATION" not in registry.commands


def test_the_entity_kinds_the_database_declares_are_the_ones_the_tracker_tracks():
    """Two enumerations of one set, across a layer boundary that cannot import.

    ``ArgSpec.cites`` names an entity kind, and the emitter looks that
    name up in the tracker. The dependency runs script -> commands and
    never the other way (CLAUDE.md layout rule), so ``EntityKind``
    restates the tracker's own tuple rather than importing it, and two
    restatements of one set drift.

    This is the assertion ``EntityKind``'s docstring promises. It did
    not exist when that docstring was written, which is the defect
    class this repository keeps finding and is why it is written down
    here rather than trusted: a kind added to the tracker and not to the
    enum is unusable from the database, and a kind added to the enum and
    not to the tracker is a validated ``cites`` that raises
    ScriptReferenceError at emission time instead of at load time.
    """
    from pyflightstream.commands import EntityKind
    from pyflightstream.script.entities import ENTITY_KINDS

    assert {kind.value for kind in EntityKind} == set(ENTITY_KINDS), (
        "commands.EntityKind and script.entities.ENTITY_KINDS name different sets; "
        "they are one set written twice because the layering forbids the import, "
        "so a kind added to either must be added to both in the same change"
    )


def test_every_declared_citation_reaches_a_kind_the_tracker_accepts():
    """The database half of the same agreement, on live entries.

    The test above compares two literals. This one walks what the
    database actually declares, so a `cites` value that validates
    against the enum and still fails at emission is caught at rest.
    """
    from pyflightstream.script.entities import EntityRegistry

    tracker = EntityRegistry()
    for entry in CommandRegistry.load().commands.values():
        grammars = [entry.args]
        grammars += [record.args for record in entry.versions.values() if record.args]
        for args in grammars:
            for spec in args:
                if spec.cites is None:
                    continue
                # Raises ScriptReferenceError for an unknown kind, which
                # is the failure this asserts cannot happen at emission.
                tracker.count(str(spec.cites))


# --- what the 2026-08-07 QA pass proved untested -----------------------------


def test_a_declared_citation_resolves_labels_and_checks_ranges():
    """The four `cites` declarations, asserted as behaviour.

    Deleting all four from the yaml left the whole suite green when the
    QA pass measured it, which is the commit's own headline defect
    reinstated silently: SURFACE_INVERT refusing a declared label while
    SURFACE_DELETE accepted one, and SURFACE_COMBINE's index list range
    checked against nothing.

    Both halves are asserted per command, because a declaration that
    resolves labels but skips the range check, or the reverse, is half a
    fix.
    """
    labelled = {"wing": 1, "tail": 2, "fin": 3}

    # Scalar surface citations under three different spellings.
    for name, args, expected in (
        ("SURFACE_INVERT", ("tail",), "SURFACE_INVERT 2"),
        ("SURFACE_RENAME", ("tail", "Fuselage"), "SURFACE_RENAME 2 Fuselage"),
        ("SURFACE_AUTO_HOLE_FILL", ("fin",), "SURFACE_AUTO_HOLE_FILL 3"),
    ):
        script = Script(version="26.120")
        script.declare_existing(boundaries=labelled)
        script.emit(name, *args)
        assert expected in script.render(), f"{name} must resolve a declared label"

        script = Script(version="26.120")
        script.declare_existing(boundaries=labelled)
        with pytest.raises(ScriptReferenceError, match="mesh boundary"):
            script.emit(name, *(99, *args[1:]))

    # The list spelling, which reached neither map before.
    script = Script(version="26.120")
    script.declare_existing(boundaries=labelled)
    script.emit("SURFACE_COMBINE", 2, ["wing", "fin"])
    assert "SURFACE_COMBINE 2\n1,3\n" in script.render()

    script = Script(version="26.120")
    script.declare_existing(boundaries=labelled)
    with pytest.raises(ScriptReferenceError, match="mesh boundary"):
        script.emit("SURFACE_COMBINE", 2, [1, 99])

    # And a frame citation, so the fix is not surface-only.
    script = Script(version="26.120")
    script.declare_existing(boundaries=labelled, frames=2)
    with pytest.raises(ScriptReferenceError, match="local coordinate system"):
        script.emit("TRANSLATE_SURFACE_BY_FRAME", 1, 99, 1)


def test_a_payload_of_the_wrong_length_is_refused_naming_the_corruption():
    """The six toggle lines, asserted as behaviour.

    Deleting the whole `fixed_length` branch left the suite green when
    the QA pass measured it. The defect it lets through is not an arity
    complaint: nothing counts these lines, so a short payload makes the
    solver read the NEXT COMMAND as data, and the message has to say so
    rather than report a number.
    """
    six = ["U DISABLE", "V DISABLE", "W DISABLE", "P DISABLE", "Q ENABLE", "R ENABLE"]

    for payload in (six[:5], [*six, "S ENABLE"]):
        script = Script(version="26.120")
        script.declare_existing(motions=1)
        with pytest.raises(CommandArgumentError, match="read the NEXT COMMAND as data"):
            script.emit("SET_MOTION_6DOF_ACTIVE_VARIABLES", 1, payload)

    control = Script(version="26.120")
    control.declare_existing(motions=1)
    control.emit("SET_MOTION_6DOF_ACTIVE_VARIABLES", 1, six)
    assert "U DISABLE\nV DISABLE\nW DISABLE\nP DISABLE\nQ ENABLE\nR ENABLE\n" in control.render()

    # The residue, asserted as residue rather than left to be assumed:
    # str_list validates the SHAPE and not the content, so six lines
    # naming the wrong variables still emit. The entry notes say so and
    # this pins which half of that sentence is true.
    loose = Script(version="26.120")
    loose.declare_existing(motions=1)
    loose.emit("SET_MOTION_6DOF_ACTIVE_VARIABLES", 1, ["U ENABLE"] * 6)
    assert "U ENABLE\nU ENABLE\n" in loose.render()


@pytest.mark.parametrize(
    ("command", "version", "args"),
    [
        ("SET_MOTION_BOUNDARIES", "26.100", (1, 4, [1, 2, 3, 5])),
        ("SET_MOTION_MOVING_FRAMES", "26.100", (1, -1)),
        ("SET_MOTION_COORDINATE_SYSTEM", "26.100", (1, 1)),
        ("SET_MOTION_START_TIME", "26.100", (1, 0.5)),
        ("SET_MOTION_FSI_EXECUTABLE", "26.100", (1, "DISABLE", "ENABLE", "beam.exe")),
        ("SET_MOTION_FSI_STRUCTURAL_NODES", "26.100", (1, "nodes.txt")),
        ("DELETE_MOTION", "26.100", (1,)),
        ("SET_MOTION_ROTOR_AXIS", "26.101", (1, "X")),
        ("SET_MOTION_ROTOR_RPM", "26.101", (1, -1000.0)),
        ("SET_SOLVER_STEADY", "26.100", ()),
        ("SET_SOLVER_UNSTEADY", "26.100", (200, 0.001)),
        ("SET_BOUNDARY_LAYER_TYPE", "26.100", ("TRANSITIONAL",)),
        ("SET_SOLVER_VISCOUS_COUPLING", "26.100", ("ENABLE",)),
    ],
)
def test_the_backfilled_early_build_rows_are_emittable(command, version, args):
    """Thirteen rows added on 2026-08-07, asserted one by one.

    Each is a command the February or May 2026 manual documents whose
    entry carried no row for that build, so the emitter refused it
    there. Deleting the rows again left the suite green when the QA pass
    measured it, which made the repair as invisible as the defect had
    been.

    The version named is the EARLIEST the command is documented in, so
    the assertion is that the earliest documented build emits, not
    merely that some build does.
    """
    script = Script(version=version)
    script.declare_existing(boundaries=6, frames=3, motions=1)
    script.emit(command, *args)
    assert command in script.render()


#: Index arguments that name an object the entity tracker does NOT model.
#: Each is a real 1-based index the solver keeps, but of a kind the
#: script builder has no inventory for, so there is nothing to resolve a
#: label against or bound the value by. Listing them is the point: the
#: guard below reports every entity-looking index argument that neither
#: declares `cites` nor appears here, so a new one is a decision rather
#: than an omission. Extending the tracker to a new kind is what removes
#: a row from this list.
_INDEXES_OF_UNTRACKED_OBJECTS = {
    ("CAD_BODY_DELETE", "body_index"),
    ("CAD_BODY_MIRROR", "body_index"),
    ("CAD_BODY_ROTATE", "body_index"),
    ("CAD_BODY_SCALE", "body_index"),
    ("CAD_BODY_TRANSLATE", "body_index"),
    ("CAD_CREATE_AUTO_ANNULAR_CROSS_SECTIONS", "body_index"),
    ("CAD_CREATE_AUTO_CROSS_SECTIONS", "body_index"),
    ("CAD_CREATE_CROSS_SECTION", "body_index"),
    ("CAD_CREATE_CURVE_REVERSE", "curve_index"),
    ("CAD_CREATE_CURVE_SELECT", "curve_index"),
    ("CAD_CREATE_CURVE_UNSELECT", "curve_index"),
    ("CAD_CREATE_IMPORT_CURVE_CCS", "component_index"),
    ("CAD_CREATE_IMPORT_CURVE_P3D", "component_index"),
    ("CAD_CREATE_PROJECT_CURVE", "curve_index"),
    ("CAD_CREATE_PROJECT_MULTI_CURVE", "curve_index_1"),
    ("CAD_CREATE_PROJECT_MULTI_CURVE", "curve_index_2"),
    ("DELETE_SEPARATION", "index"),
    ("DELETE_SURFACE_SECTION", "index"),
    ("DELETE_VOLUME_SECTION", "index"),
    ("DISABLE_WAKE_NODES_ON_TRAILING_EDGE", "te_index"),
    ("EXPORT_SURFACE_SECTIONS", "index"),
    ("EXPORT_VOLUME_SECTION_TECPLOT", "index"),
    ("EXPORT_VOLUME_SECTION_VTK", "index"),
    ("SET_TRAILING_EDGE_TYPE", "te_index"),
    ("VOLUME_SECTION_BOUNDARY_LAYER", "index"),
    # Caught by the widened stems on 2026-08-07, each read and kept:
    # a count of sections to create rather than a citation of one,
    # a mesh VERTEX (the tracker counts boundaries, not nodes),
    # a plane selector whose 1, 2, 3 name YZ, XZ, XY rather than an
    # object (SRC-003 p.311), and a force index within a motion.
    ("CAD_CREATE_AUTO_CROSS_SECTIONS", "sections"),
    ("CAD_CREATE_AUTO_ANNULAR_CROSS_SECTIONS", "sections"),
    ("SELECT_MESH_NODE", "node_id"),
    ("SURFACE_MIRROR", "mirror_plane"),
    ("DELETE_6DOF_EXTERNAL_FORCE", "force_id"),
    # The CCS wing definition's own objects, added 2026-08-08 with that
    # chapter: a spanwise refinement zone and a control surface belong to
    # a parametric wing definition, not to the loaded geometry, so the
    # builder has no inventory of either. Both document -1 to delete all,
    # which is recorded in their notes rather than declared as a sentinel,
    # for the same reason: with no kind to resolve, nothing reads it.
    ("DELETE_CCS_WING_REFINEMENT_ZONES", "zone_index"),
    ("DELETE_CCS_WING_CONTROL_SURFACE", "control_index"),
    # The same objects of the other two CCS components, added later the
    # same day with their chapters. The guard found all four the moment
    # the chapters landed, which is the point of it: an untracked index
    # is a deliberate exemption in every case and never a default.
    ("DELETE_CCS_FUSELAGE_REFINEMENT_ZONES", "zone_index"),
    ("DELETE_CCS_FUSELAGE_RELAXED_TE", "index"),
    ("DELETE_CCS_REVOLVE_REFINEMENT_ZONES", "zone_index"),
    ("DELETE_CCS_REVOLVE_RELAXED_TE", "index"),
    # A mesh-wrapper local control, added 2026-08-08 with that chapter.
    # Nothing creates one with a name and nothing reports how many exist,
    # so the id is a number the caller counted and there is no inventory
    # to resolve it against.
    ("WRAPPER_EDIT_LOCAL_CONTROL", "control_id"),
    # An acoustic observer, added 2026-08-08 with that chapter. The
    # manual defines the index as the observer's position in the
    # application's own tree, which is a statement about the user
    # interface rather than about anything a script can read back.
    ("DELETE_ACOUSTIC_OBSERVER", "observer_index"),
    # A base region, added 2026-08-08 with that chapter. Boundaries ARE
    # tracked, and the two commands here that take a boundary index
    # declare it; these four take a base-region index instead, which is
    # a separate 1-based sequence over the boundaries already marked and
    # which nothing reports back. Two of them document -1 for all, kept
    # in their notes for the usual reason.
    ("DELETE_BASE_REGION", "base_region_boundary"),
    ("SET_BASE_REGION_TRAILING_EDGES", "base_region_boundary"),
    ("SELECT_BASE_REGION_FACES", "base_index"),
    ("SET_BASE_REGION_CP", "base_index"),
    # An inlet, added 2026-08-08 with the Inlets and Outlets chapter. The
    # two CREATE commands there take a BOUNDARY index and declare it;
    # this is the separate 1-based sequence over the boundaries already
    # marked as inlets, which nothing reports back. Its DELETE siblings
    # are not here because their argument names carry no citation stem.
    ("SET_INLET_CUSTOM_PROFILE", "inlet_id"),
    # The tail chapters of 2026-08-08. A CAD BODY is not a mesh boundary
    # and the builder tracks only boundaries, so the unite list and the
    # CAD transfer index resolve to nothing; both document -1 for all,
    # kept in their notes. A volume section and a transition trip are
    # likewise untracked, and the trip is the sharper case: no edition
    # documents a command that CREATES one, so its index has no scripted
    # source at all.
    ("BOOLEAN_UNITE_MESH", "body_indices"),
    ("CONVERT_CAD_TO_MESH", "body_index"),
    ("DELETE_TRANSITION_TRIP", "transition_trip_index"),
    ("EXPORT_VOLUME_SECTION_2D_VTK", "index"),
    ("VOLUME_SECTION_WIREFRAME", "index"),
}

#: Name stems that suggest an argument cites something by index. This
#: is a HEURISTIC over names, not a closure over arguments: 53 of the
#: database's 206 integer arguments are neither a citation nor a count,
#: and classifying all of them is the only thing that would close the
#: set (registered as part of PLN-20260807-1410). The 2026-08-07 QA
#: pass got 17 invented spellings past the first version of this list,
#: so the stems below are broad, and the test name and docstring say
#: heuristic rather than closed.
_LOOKS_LIKE_A_CITATION = re.compile(
    r"index|indices|id|_id|frame|surface|surf|coordinate_system|cs|motion"
    r"|actuator|boundar|body|component|part|section|curve|node|vertex|group|owner"
    r"|target|wake|probe|plane|system"
)


def test_an_index_argument_whose_name_suggests_a_citation_resolves_to_one():
    """An unresolved index argument is silence, not a refusal.

    Omitting `cites` on a new ambiguous index produces no error: the
    entity check is simply skipped, so a declared label is not resolved
    and an out-of-range index is not caught. The 2026-08-07 review found
    five such arguments shipped in one chapter, which is what made the
    field necessary; nothing then stopped the sixth.

    So every int or int_list argument whose NAME suggests a citation
    must either declare what it cites, be a count, or be named above as
    an index of an object the tracker does not model. The middle option
    used to include "be a spelling the emitter's own maps resolve"; the
    maps went on 2026-08-08 (PLN-20260807-1410) and the 101 arguments
    they covered declare it themselves now, so the guard has one fewer
    way to be satisfied and the database says what the emitter does.

    STATED HONESTLY, because the first version of this docstring said
    the vocabulary was closed and it is not: the rule is a heuristic
    over name stems, and the 2026-08-07 QA pass got 17 invented
    spellings past it. The stems were widened with all 17. Real closure
    means classifying every integer argument, 53 of which are today
    neither a citation nor a count, and that is registered rather than
    claimed here.

    Running it found five the review did not, each then read on its own
    page before being declared: DELETE_SURFACES (SRC-740 p.315) and the
    two surface-section commands (SRC-003 p.364, where SURFACES is a
    count of geometry surfaces followed by their indices) cite mesh
    boundaries; ROTATE_COORDINATE_SYSTEM's ROTATION_FRAME (SRC-003
    p.330) and IMPORT_AEROELASTIC_STRUCTURAL_NODES's
    STRUCTURAL_COORDINATE_SYSTEM (SRC-003 p.375) cite local coordinate
    systems, both stating 1 as the reference system.
    """
    from pyflightstream.commands import ArgType
    from pyflightstream.script import _COUNT_ARG_NAMES, _COUNT_REFERENCE_ARGS

    unresolved = set()
    for name, entry in CommandRegistry.load().commands.items():
        grammars = [entry.args]
        grammars += [record.args for record in entry.versions.values() if record.args]
        for args in grammars:
            for spec in args:
                if spec.type not in (ArgType.INT, ArgType.INT_LIST) or spec.cites is not None:
                    continue
                if spec.name in _COUNT_ARG_NAMES or spec.name in _COUNT_REFERENCE_ARGS:
                    continue
                if _LOOKS_LIKE_A_CITATION.search(spec.name):
                    unresolved.add((name, spec.name))

    assert unresolved <= _INDEXES_OF_UNTRACKED_OBJECTS, (
        "these index arguments look like entity citations and resolve to nothing, so a "
        "declared label is not resolved there and an out-of-range index is not caught: "
        f"{sorted(unresolved - _INDEXES_OF_UNTRACKED_OBJECTS)}. Add `cites:` with the "
        "entity kind, or list the pair in _INDEXES_OF_UNTRACKED_OBJECTS with the reason"
    )
    stale = _INDEXES_OF_UNTRACKED_OBJECTS - unresolved
    assert not stale, (
        f"these exceptions no longer describe anything in the database: {sorted(stale)}. "
        "An exemption outliving its site is how a guard quietly stops guarding"
    )


def test_the_sentinel_holds_before_any_inventory_is_declared():
    """An inventory bounds an index from above, 1-based bounds it below.

    `check_index` used to return the moment the boundary inventory was
    unknown, which is right for the upper bound and threw away the lower
    one with it. So -1 on a zero-sentinel command emitted silently on any
    script that had not called declare_existing, which is most scripts
    at the point these geometry commands run (2026-08-07 API pass).

    Both directions, because a check that refuses everything below 1
    would pass the first half of this and break every documented
    all-form.
    """
    for name, args, tail in (
        ("TRANSLATE_SURFACE_IN_FRAME", (1, 0.0, 1.0, 1.4, "INCH"), ("ENABLE",)),
        ("TRANSLATE_SURFACE_BY_FRAME", (1, 2), ()),
    ):
        accepted = Script(version="26.120")
        accepted.declare_existing(frames=2)
        accepted.emit(name, *args, 0, *tail)
        assert name in accepted.render(), "the documented 0 must still emit"
        refused = Script(version="26.120")
        refused.declare_existing(frames=2)
        with pytest.raises(ScriptReferenceError, match="1-based"):
            refused.emit(name, *args, -1, *tail)

    accepted = Script(version="26.120")
    accepted.emit("SURFACE_SCALE", 1, 2.0, 2.0, 2.0, -1)
    assert "SURFACE_SCALE" in accepted.render(), "the documented -1 must still emit"
    with pytest.raises(ScriptReferenceError, match="1-based"):
        Script(version="26.120").emit("SURFACE_SCALE", 1, 2.0, 2.0, 2.0, 0)


def test_only_the_boundary_inventory_can_be_unknown():
    """What lets the undeclared-inventory refusal name its sentinel.

    That message interpolates the sentinel, which is None for a kind
    with no documented all-form. It is unreachable for those kinds
    because their limit is an int from the start, and this pins the
    reason rather than leaving the message one entity kind away from
    printing the word None at a user.
    """
    from pyflightstream.script.entities import ENTITY_KINDS, EntityRegistry

    registry = EntityRegistry()
    unknown = [kind for kind in ENTITY_KINDS if registry.limit(kind) is None]
    assert unknown == ["boundaries"], (
        "a second entity kind can now have an unknown limit; the undeclared-inventory "
        "refusal in _reject_index names a sentinel that is None for any kind without a "
        "documented all-form, so give that kind one or branch the message"
    )


def test_a_command_with_no_documented_all_form_refuses_minus_one():
    """Absent means the page states no all-form, not "the default".

    The emitter treated -1 as the all-surfaces value for every boundary
    index, so SURFACE_RENAME renamed "all surfaces" to one name,
    SURFACE_MIRROR mirrored them, and the refusal text OFFERED -1 on
    pages that never mention it. That is the same inversion the sentinel
    was introduced to fix, and the 2026-08-07 API pass found it a third
    time, in the commit whose changelog entry claimed it closed.

    SRC-003 pp.309-313 were read command by command. Six boundary
    indices in this chapter state no all-form and each is asserted here;
    the ones that do state one are asserted in the sentinel test above,
    so neither half can be satisfied by a rule that simply says yes or
    simply says no.
    """
    for name, args in (
        ("SURFACE_RENAME", (-1, "Wing")),
        ("SURFACE_MIRROR", (-1, 2, 2, "TRUE", "FALSE")),
        ("SURFACE_AUTO_HOLE_FILL", (-1,)),
        ("SURFACE_LINEAR_COPY_PASTE", (-1, 4, 2, "METER", 0.5, -2.0, 0.0)),
        ("SURFACE_CIRCULAR_COPY_PASTE", (-1, 2, "1", 10, 90.0)),
        ("SURFACE_DELETE", (-1,)),
    ):
        script = Script(version="26.120")
        script.declare_existing(boundaries=6, frames=3)
        with pytest.raises(ScriptReferenceError, match="mesh boundary -1"):
            script.emit(name, *args)

        # And with NO inventory declared, which is the state most
        # scripts are in when these geometry commands run. The 2026-08-07
        # QA pass proved this branch untested: every case above declared
        # an inventory first, so restoring the early return left the
        # whole suite green while -1 emitted silently again.
        undeclared = Script(version="26.120")
        undeclared.declare_existing(frames=3)
        with pytest.raises(ScriptReferenceError) as caught:
            undeclared.emit(name, *args)
        message = str(caught.value)
        assert "None" not in message, f"{name}: the refusal must not print None"
        assert "-1 selecting" not in message and "0 selecting" not in message, (
            f"{name}: the refusal must not offer an all-form this page does not state"
        )

        # The control, so this is not passing because the command is
        # broken in some unrelated way: a real index emits.
        working = Script(version="26.120")
        working.declare_existing(boundaries=6, frames=3)
        working.emit(name, *(2, *args[1:]))
        assert name in working.render()


def test_the_refusal_never_offers_an_all_form_the_page_does_not_state():
    """The message is where the previous inversion did its damage.

    A caller who passes 0 to SURFACE_RENAME was told to try -1, which
    the emitter then accepted. So the wording is asserted, not only the
    accept-or-refuse decision.
    """
    quiet = Script(version="26.120")
    quiet.declare_existing(boundaries=6)
    with pytest.raises(ScriptReferenceError) as caught:
        quiet.emit("SURFACE_RENAME", 0, "Wing")
    message = str(caught.value)
    assert "-1 selecting" not in message and "0 selecting" not in message, (
        "SURFACE_RENAME states no all-form, so its refusal must not offer a VALUE for "
        f"one; the caller would pass it and the emitter would accept it. Got: {message}"
    )
    assert "no value selecting all of them" in message, (
        "and it must say so positively, rather than leaving the caller to infer it"
    )

    loud = Script(version="26.120")
    loud.declare_existing(boundaries=6)
    with pytest.raises(ScriptReferenceError) as caught:
        loud.emit("SURFACE_INVERT", 0)
    assert "-1 selecting all boundaries" in str(caught.value), (
        "SURFACE_INVERT does state one (SRC-003 p.310), so its refusal must name it"
    )


def test_no_golden_carries_a_carriage_return():
    """ "Byte-exact" is a claim, and read_text was quietly not honouring it.

    Every golden comparison in this suite reads with read_text, whose
    universal-newline translation turns CRLF into LF before the string
    is compared. So a checkout that rewrote the line endings passed for
    a reason unrelated to the emitter being right, and the phrase
    byte-exact was not true of any of them. `.gitattributes` pins the
    directory to LF, but a git setting is a checkout property rather
    than a guard, and the 2026-08-07 QA pass found three goldens sitting
    CRLF on disk in a worktree checked out before the pin.

    This asserts the property directly, so the pin is checked rather
    than trusted.
    """
    offenders = [path.name for path in sorted(GOLDENS.iterdir()) if b"\r" in path.read_bytes()]
    assert not offenders, (
        f"these goldens carry a carriage return: {offenders}. Their bytes are the "
        "assertion, and read_text hides the difference, so a line-ending rewrite would "
        "pass while changing the file. Re-save as LF; .gitattributes pins the directory"
    )


def test_the_rotate_all_form_takes_no_index_line():
    """The one all-form in the chapter carried on a COUNT, not an index.

    SRC-003 p.309 states -1 in SURFACE_ROTATE's count row selects every
    surface for rotation, and the index line then has nothing to list.
    The list argument was required, so the documented call was refused
    outright; supplying an empty list instead emitted a stray blank line
    into the middle of the keyword block, which is a malformed script
    rather than a refusal (2026-08-07 V&V pass).
    """
    script = Script(version="26.120")
    script.declare_existing(frames=3)
    script.emit(
        "SURFACE_ROTATE",
        frame=3,
        axis="X",
        angle=-20.0,
        surfaces=-1,
        split_vertices="DISABLE",
        adaptive_mesh="DISABLE",
        detach_normal_to_axis="ENABLE",
    )
    assert "SURFACES -1\nSPLIT_VERTICES DISABLE" in script.render(), (
        "the all-form must be followed by the next keyword, with no index line "
        "and no blank line between them"
    )

    # The counted form still carries its list, so making the argument
    # optional did not make the count meaningless.
    counted = Script(version="26.120")
    counted.declare_existing(frames=3)
    counted.emit(
        "SURFACE_ROTATE",
        frame=3,
        axis="X",
        angle=-20.0,
        surfaces=2,
        surface_indices=[1, 3],
        split_vertices="DISABLE",
        adaptive_mesh="DISABLE",
        detach_normal_to_axis="ENABLE",
    )
    assert "SURFACES 2\n1,3\n" in counted.render()

    # And a count that disagrees with its list is still refused, which
    # the same pass found `>= 0` had disabled for every negative.
    with pytest.raises(CommandArgumentError, match="declared count"):
        wrong = Script(version="26.120")
        wrong.declare_existing(frames=3)
        wrong.emit(
            "SURFACE_ROTATE",
            frame=3,
            axis="X",
            angle=-20.0,
            surfaces=-2,
            surface_indices=[1, 3],
            split_vertices="DISABLE",
            adaptive_mesh="DISABLE",
            detach_normal_to_axis="ENABLE",
        )


# --- CCS Wing Mesh ------------------------------------------------------------


@pytest.mark.parametrize("version", ["26.100", "26.101", "26.120", "26.121"])
def test_the_ccs_wing_chapter_emits_on_every_registered_build(version):
    """Each line is the manual's own printed sample.

    The gapped control surface is left out of this walk because its
    grammar differs by build (eight arguments before 26.120, ten from
    it), and it has its own test below.
    """
    script = Script(version=version)
    script.emit("DEFAULT_CCS_WING_MESH_SETTINGS", "SPAN")
    script.emit("CCS_WING_MESH_SUBDIVISIONS", "CHORD", 120)
    script.emit("CCS_WING_MESH_GROWTH_SCHEME", "CHORD", "DUAL-SIDED")
    script.emit("CCS_WING_MESH_GROWTH_RATE", "CHORD", 1.2)
    script.emit("CCS_WING_MESH_PERIODICITY", "SPAN", 2)
    script.emit("NEW_CCS_WING_REFINEMENT_ZONE", 0.2, 0.4, 20)
    script.emit("DELETE_CCS_WING_REFINEMENT_ZONES", -1)
    script.emit("NEW_CCS_WING_MORPHING_SURFACE", "Aileron", 0.5, 0.7, 0.15, 0.15, 0.5, 20.0)
    script.emit("NEW_CCS_WING_FLAP_COVE", "Cove", 0.1, 0.3, 0.15, 0.15, "1")
    script.emit("DELETE_CCS_WING_CONTROL_SURFACE", -1)
    script.emit("EXPORT_WING_CCS_FILE", "Wing", "TRUE", "BLUNT", "TRUE", "C2", "C0", "wing_ccs.csv")
    golden = (GOLDENS / "ccs_wing_chapter.txt").read_text(encoding="utf-8")
    assert script.render() == golden


def test_the_gapped_control_surface_has_two_arities_and_the_earlier_one_refuses_the_axis():
    """SPACE and AXIS arrive at 26.120 (SRC-003 p.299).

    Before that the spanwise limits are parametric only, so the two
    trailing arguments name a capability the older builds do not have,
    and passing them would send tokens the solver never reads.
    """
    for early in ("26.100", "26.101"):
        script = Script(version=early)
        script.emit(
            "NEW_CCS_WING_CONTROL_SURFACE", "Aileron", 0.5, 0.7, 0.15, 0.15, 0.5, 20.0, 0.001
        )
        assert "NEW_CCS_WING_CONTROL_SURFACE Aileron 0.5 0.7 0.15 0.15 0.5 20.0 0.001" in (
            script.render()
        )
        with pytest.raises(CommandArgumentError):
            Script(version=early).emit(
                "NEW_CCS_WING_CONTROL_SURFACE",
                "Aileron",
                0.5,
                0.7,
                0.15,
                0.15,
                0.5,
                20.0,
                0.001,
                "REAL",
                "Y",
            )

    late = Script(version="26.120")
    late.emit(
        "NEW_CCS_WING_CONTROL_SURFACE",
        "Aileron",
        0.5,
        0.7,
        0.15,
        0.15,
        0.5,
        20.0,
        0.001,
        "REAL",
        "Y",
    )
    assert "0.001 REAL Y" in late.render()

    # The two are optional even where they exist, which the manual's own
    # sample relies on: it prints eight arguments on the ten-argument
    # page. That is the sample-versus-heading class, and here the table
    # settles it by making both conditional on SPACE being REAL.
    parametric = Script(version="26.120")
    parametric.emit(
        "NEW_CCS_WING_CONTROL_SURFACE", "Aileron", 0.5, 0.7, 0.15, 0.15, 0.5, 20.0, 0.001
    )
    assert parametric.render().rstrip().endswith("0.001")


def test_the_flap_cove_type_is_an_index_and_refuses_a_word():
    """One numbered shape argument among a family of tokens.

    SRC-003 p.300 gives 1 for a blended Bezier cove and 2 for a
    rectangular one, while every neighbouring shape argument in the
    family is spelled as a word, so BEZIER is the natural mistake.
    """
    script = Script(version="26.120")
    with pytest.raises(CommandArgumentError, match="expects one of"):
        script.emit("NEW_CCS_WING_FLAP_COVE", "Cove", 0.1, 0.3, 0.15, 0.15, "BEZIER")


def test_the_ccs_wing_delete_commands_take_their_documented_minus_one():
    """The -1 is in the notes rather than declared, so this pins it.

    A refinement zone and a control surface belong to the parametric
    definition and not to the loaded geometry, so the builder tracks
    neither and nothing range checks these indices. That makes the
    manual's own all-form untested unless a test says so.
    """
    registry = CommandRegistry.load()
    for name, argument in (
        ("DELETE_CCS_WING_REFINEMENT_ZONES", "zone_index"),
        ("DELETE_CCS_WING_CONTROL_SURFACE", "control_index"),
    ):
        entry = registry.commands[name]
        assert [spec.name for spec in entry.args] == [argument]
        assert entry.args[0].all_sentinel is None, (
            f"{name} cites no tracked entity, so a declared sentinel would be inert; "
            "the -1 belongs in the notes until the object becomes tracked"
        )
        assert "-1" in entry.notes
        script = Script(version="26.120")
        script.emit(name, -1)
        assert f"{name} -1" in script.render()


# --- CCS Fuselage Mesh and CCS Body of Revolution Mesh ------------------------


@pytest.mark.parametrize("version", ["26.100", "26.101", "26.120", "26.121"])
def test_the_ccs_fuselage_chapter_emits_on_every_registered_build(version):
    """Each line is the manual's own printed sample, where it prints one.

    The two exports are not here: their samples are the neighbouring
    create command's, which is the finding the chapter records, so they
    have their own test below.
    """
    script = Script(version=version)
    script.emit("DEFAULT_CCS_FUSELAGE_MESH_SETTINGS", "AXIAL")
    script.emit("CCS_FUSELAGE_MESH_SUBDIVISIONS", "RADIAL", 80)
    script.emit("CCS_FUSELAGE_MESH_GROWTH_SCHEME", "AXIAL", "DUAL-SIDED")
    script.emit("CCS_FUSELAGE_MESH_GROWTH_RATE", "AXIAL", 1.2)
    script.emit("CCS_FUSELAGE_MESH_PERIODICITY", "RADIAL", 2)
    script.emit("NEW_CCS_FUSELAGE_REFINEMENT_ZONE", 0.2, 0.4, 20)
    script.emit("DELETE_CCS_FUSELAGE_REFINEMENT_ZONES", -1)
    script.emit("NEW_CCS_FUSELAGE_RELAXED_TE", 0.2, 0.4, 0.5)
    script.emit("DELETE_CCS_FUSELAGE_RELAXED_TE", -1)
    golden = (GOLDENS / "ccs_fuselage_chapter.txt").read_text(encoding="utf-8")
    assert script.render() == golden


@pytest.mark.parametrize("version", ["26.100", "26.101", "26.120", "26.121"])
def test_the_ccs_revolve_chapter_emits_on_every_registered_build(version):
    """The parallel walk, and the parallel is the point.

    The two chapters are line for line the same commands over a
    different second direction, so the same walk with AZIMUTH for
    RADIAL is what proves the enums were not shared by accident.
    """
    script = Script(version=version)
    script.emit("DEFAULT_CCS_REVOLVE_MESH_SETTINGS", "AXIAL")
    script.emit("CCS_REVOLVE_MESH_SUBDIVISIONS", "AZIMUTH", 80)
    script.emit("CCS_REVOLVE_MESH_GROWTH_SCHEME", "AXIAL", "DUAL-SIDED")
    script.emit("CCS_REVOLVE_MESH_GROWTH_RATE", "AXIAL", 1.2)
    script.emit("CCS_REVOLVE_MESH_PERIODICITY", "AZIMUTH", 2)
    script.emit("NEW_CCS_REVOLVE_REFINEMENT_ZONE", 0.2, 0.4, 20)
    script.emit("DELETE_CCS_REVOLVE_REFINEMENT_ZONES", -1)
    script.emit("NEW_CCS_REVOLVE_RELAXED_TE", 0.2, 0.4, 0.5)
    script.emit("DELETE_CCS_REVOLVE_RELAXED_TE", -1)
    golden = (GOLDENS / "ccs_revolve_chapter.txt").read_text(encoding="utf-8")
    assert script.render() == golden


@pytest.mark.parametrize(
    ("command", "wrong", "right"),
    [
        ("CCS_FUSELAGE_MESH_SUBDIVISIONS", "AZIMUTH", "RADIAL"),
        ("CCS_REVOLVE_MESH_SUBDIVISIONS", "RADIAL", "AZIMUTH"),
    ],
)
def test_the_two_ccs_components_do_not_share_a_second_direction(command, wrong, right):
    """AXIAL is common to both; the other direction is not.

    The two chapters are otherwise identical, which makes a value
    carried across from one to the other the easy mistake and an
    invisible one: RADIAL and AZIMUTH are both plausible words for a
    body of revolution, and only one is accepted.
    """
    script = Script(version="26.120")
    with pytest.raises(CommandArgumentError, match="expects one of"):
        script.emit(command, wrong, 80)
    script.emit(command, right, 80)
    assert f"{command} {right} 80" in script.render()


def test_the_ccs_exports_take_the_six_of_their_heading_not_the_four_of_their_table():
    """The three-way disagreement, pinned so a later reader cannot undo it quietly.

    On both pages the signature heading prints six placeholders, the
    parameter table documents four, and the sample is the neighbouring
    create command's with the name swapped. The heading is recorded, so
    the six-argument call must build and the four-argument one must
    refuse; without this test the entry could be trimmed to the table
    and every test would still pass.
    """
    registry = CommandRegistry.load()
    for name in ("EXPORT_FUSELAGE_CCS_FILE", "EXPORT_REVOLVE_CCS_FILE"):
        entry = registry.commands[name]
        assert [spec.name for spec in entry.args] == [
            "name",
            "mark_trailing_edges",
            "te_geometry",
            "close_ends",
            "loft_type_u",
            "loft_type_v",
            "file",
        ]
        script = Script(version="26.120")
        script.emit(name, "Body", "TRUE", "BLUNT", "TRUE", "C2", "C0", "body_ccs.csv")
        # Line-exact, not a substring: both substrings hold with or
        # without `own_line`, so the weaker form passed on an entry that
        # wrote the destination onto the command line.
        assert script.render().splitlines()[:2] == [
            f"{name} Body TRUE BLUNT TRUE C2 C0",
            "body_ccs.csv",
        ]
        with pytest.raises(CommandArgumentError):
            Script(version="26.120").emit(name, "Body", "TRUE", "C2", "C0")


def test_the_ccs_export_close_ends_accepts_the_word_its_own_sample_passes():
    """TRUE as well as OPEN and CLOSED, the contradiction the family carries.

    The table states two words and every sample in the family passes a
    third. Both readings are recorded because refusing the sample's own
    value would refuse the only form the vendor has written as a
    runnable line.
    """
    for token in ("TRUE", "OPEN", "CLOSED"):
        script = Script(version="26.120")
        script.emit("EXPORT_FUSELAGE_CCS_FILE", "Body", "TRUE", "BLUNT", token, "C2", "C0", "b.csv")
        assert f"BLUNT {token} C2 C0" in script.render()


# --- Scenes and Scene Settings ------------------------------------------------


@pytest.mark.parametrize("version", ["26.100", "26.101", "26.120", "26.121"])
def test_the_scenes_chapter_emits_on_every_registered_build(version):
    """Twelve display actions, eleven of which take nothing at all."""
    script = Script(version=version)
    script.emit("VIEW_RESIZE")
    for scene in ("CAD", "GEOMETRY", "SOLVER", "PLOTS"):
        script.emit(f"CHANGE_SCENE_TO_{scene}")
    script.emit("SET_SCENE_DEFAULTVIEW")
    for plane in ("XY", "XZ", "YZ"):
        script.emit(f"SET_SCENE_{plane}_POSITIVE")
        script.emit(f"SET_SCENE_{plane}_NEGATIVE")
    script.emit("SAVE_SCENE_AS_IMAGE", "Test.bmp")
    golden = (GOLDENS / "scenes_chapter.txt").read_text(encoding="utf-8")
    assert script.render() == golden


@pytest.mark.parametrize("version", ["26.100", "26.101", "26.120", "26.121"])
def test_the_scene_settings_chapter_emits_on_every_registered_build(version):
    """Six keyword blocks, each selecting its scale with the same first keyword."""
    script = Script(version=version)
    script.emit("SET_SCENE_COLORMAP_TYPE", colormap="PRIMARY", type="BLACKBODY_STANDARD")
    script.emit("SET_SCENE_COLORMAP_SIZE", colormap="PRIMARY", thickness=300, height=15)
    script.emit("SET_SCENE_COLORMAP_POSITION", colormap="PRIMARY", x=450, y=75)
    script.emit(
        "SET_SCENE_COLORMAP_SHADING", colormap="PRIMARY", reverse="DISABLE", smooth="ENABLE"
    )
    script.emit("SET_SCENE_COLORMAP_CUSTOM_MODE", colormap="PRIMARY", custom_range="ENABLE")
    script.emit(
        "SET_SCENE_COLORMAP_CUSTOM_RANGE",
        colormap="PRIMARY",
        cut_off_mode="ABOVE_MAX",
        maximum=1.0,
        minimum=-1.5,
    )
    golden = (GOLDENS / "scene_settings_chapter.txt").read_text(encoding="utf-8")
    assert script.render() == golden


def test_the_colormap_cut_off_mode_keeps_its_off_as_a_word():
    """YAML 1.1 reads a bare OFF as the boolean false.

    The schema refuses a non-string enum value, so the mistake is loud
    rather than silent, but a later edit that unquotes it would take the
    token out of the closed set. This is what would catch that.
    """
    entry = CommandRegistry.load().commands["SET_SCENE_COLORMAP_CUSTOM_RANGE"]
    (mode,) = [spec for spec in entry.args if spec.name == "cut_off_mode"]
    assert "OFF" in mode.values
    script = Script(version="26.120")
    script.emit(
        "SET_SCENE_COLORMAP_CUSTOM_RANGE",
        colormap="PRIMARY",
        cut_off_mode="OFF",
        maximum=1.0,
        minimum=0.0,
    )
    assert "CUT_OFF_MODE OFF" in script.render()


def test_the_bare_scene_commands_refuse_an_argument():
    """The manual prints these as a heading and nothing else.

    A bare command that quietly accepted an argument would let a caller
    write a line the solver reads as something other than what they
    meant, and twelve of the chapter's thirteen commands share the
    shape, so one test covers the class rather than each member.
    """
    registry = CommandRegistry.load()
    bare = [
        name
        for name, entry in registry.commands.items()
        if entry.chapter == "scenes" and not entry.args
    ]
    assert len(bare) == 12, bare
    for name in bare:
        with pytest.raises(CommandArgumentError):
            Script(version="26.120").emit(name, "PRIMARY")


# --- Mesh Wrapper -------------------------------------------------------------


@pytest.mark.parametrize("version", ["26.100", "26.101", "26.120", "26.121"])
def test_the_mesh_wrapper_chapter_emits_on_every_registered_build(version):
    """The whole chapter, every line the manual's own printed sample."""
    script = Script(version=version)
    script.emit("WRAPPER_SET_INPUT", 5, [1, 2, 3, 5, 6])
    script.emit("WRAPPER_SET_GLOBAL_SIZE", 0.15)
    script.emit("WRAPPER_SET_VERTEX_PROJECTION", "ENABLE")
    script.emit("WRAPPER_SET_ANISOTROPY", 2.0, 1.0, 1.0)
    script.emit("WRAPPER_CREATE_LOCAL_CONTROL")
    script.emit(
        "WRAPPER_EDIT_LOCAL_CONTROL",
        control_id=2,
        surfaces=3,
        surface_indices=[1, 2, 6],
        target_size=0.25,
    )
    script.emit("WRAPPER_DELETE_ALL_LOCAL_CONTROLS")
    script.emit(
        "WRAPPER_NEW_VOLUME_CONTROL",
        frame=1,
        vertex_1=0.5,
        vertex_1_y=0.3,
        vertex_1_z=1.0,
        vertex_2=1.5,
        vertex_2_y=0.6,
        vertex_2_z=2.3,
        target_size=0.25,
        name="Airplane_nose",
    )
    script.emit("WRAPPER_DELETE_ALL_VOLUME_CONTROLS")
    script.emit("WRAPPER_EXECUTE")
    script.emit("WRAPPER_TRANSFER", "REPLACE")
    golden = (GOLDENS / "mesh_wrapper_chapter.txt").read_text(encoding="utf-8")
    assert script.render() == golden


def test_a_keyword_block_argument_can_sit_on_the_command_line():
    """`on_command_line` exists because one command needs it and nothing else could say it.

    WRAPPER_EDIT_LOCAL_CONTROL takes its control id on the command's own
    line and everything else as keyword lines. Spelling that with
    `joins_previous` is refused by the schema, correctly: in first
    position there is no preceding argument line to append to. The two
    flags name two different lines and only one of them is true here.
    """
    script = Script(version="26.120")
    script.emit(
        "WRAPPER_EDIT_LOCAL_CONTROL",
        control_id=2,
        surfaces=1,
        surface_indices=[4],
        target_size=0.25,
    )
    lines = script.render().splitlines()
    assert lines[0] == "WRAPPER_EDIT_LOCAL_CONTROL 2", (
        "the id belongs on the command line; a CONTROL_ID keyword line would be a "
        "line the solver never reads"
    )
    assert lines[1] == "SURFACES 1"


@pytest.mark.parametrize(
    ("spec", "message"),
    [
        ({"name": "a", "type": "int_list", "on_command_line": True}, "is a list"),
        (
            {"name": "a", "type": "int", "on_command_line": True, "joins_previous": True},
            "two different lines",
        ),
    ],
)
def test_on_command_line_refuses_the_shapes_it_cannot_render(spec, message):
    """The argument-level half of the rule."""
    with pytest.raises(ValidationError, match=message):
        ArgSpec(**spec)


def test_on_command_line_must_lead_and_needs_a_keyword_block():
    """The entry-level half: the command line is written first and once.

    An `on_command_line` argument after a keyword line would have to
    append to a line already emitted, so the schema holds them to the
    leading positions rather than letting the renderer produce a script
    whose arguments are in an order nobody wrote.
    """
    leading = {"name": "id", "type": "int", "on_command_line": True}
    keyword = {"name": "size", "type": "float"}
    with pytest.raises(ValidationError, match="a keyword line precedes it"):
        CommandEntry(
            name="X_CMD",
            chapter="test",
            layout="keyword_block",
            phase="geometry",
            args=[keyword, leading],
            manual_ref="SRC-003 p.1",
            versions={"26.120": {"status": "documented"}},
        )
    with pytest.raises(ValidationError, match="only a keyword_block needs"):
        CommandEntry(
            name="X_CMD",
            chapter="test",
            layout="inline",
            phase="geometry",
            args=[leading],
            manual_ref="SRC-003 p.1",
            versions={"26.120": {"status": "documented"}},
        )


# --- Acoustics Toolbox and Base Regions ---------------------------------------


@pytest.mark.parametrize("version", ["26.100", "26.101", "26.120", "26.121"])
def test_the_acoustics_chapter_emits_on_every_registered_build(version):
    """Each line the manual's own sample, in the phase order the emitter holds."""
    script = Script(version=version)
    script.emit("ACOUSTIC_SOURCES", "ENABLE")
    script.emit("CREATE_NEW_ACOUSTIC_OBSERVER", "Observer-1", 0.0, -0.5, 2.0)
    script.emit("ACOUSTIC_OBSERVERS_IMPORT", "Observers.txt")
    script.emit("DELETE_ACOUSTIC_OBSERVER", 2)
    script.emit("DELETE_ALL_ACOUSTIC_OBSERVERS")
    script.emit("SET_ACOUSTIC_OBSERVER_TIME", 0.0, 0.2, 300)
    script.emit("COMPUTE_ACOUSTIC_SIGNALS")
    script.emit("EXPORT_ACOUSTIC_SIGNALS", "Acoustic_signals.txt")
    script.emit(
        "CREATE_ACOUSTIC_SECTION",
        frame=1,
        plane="XZ",
        offset=-2.0,
        radial_observers=20,
        azimuth_observers=40,
        inner_radius=0.0,
        outer_radius=3.0,
        storage_path="Acoustic_Output/",
    )
    golden = (GOLDENS / "acoustics_chapter.txt").read_text(encoding="utf-8")
    assert script.render() == golden


@pytest.mark.parametrize("version", ["26.100", "26.101", "26.120", "26.121"])
def test_the_base_regions_chapter_emits_on_every_registered_build(version):
    """The remesh leads, being the one geometry command in a setup chapter."""
    script = Script(version=version)
    script.emit(
        "REMESH_BASE_REGION",
        base_region=1,
        inner_radius=0.1,
        elements=10,
        growth_scheme="2",
        growth_rate=1.2,
    )
    script.emit("SET_BASE_REGION_BENDING_ANGLE", 25.0)
    script.emit("AUTO_DETECT_BASE_REGIONS")
    script.emit("DETECT_BASE_REGIONS_BY_SURFACE", 2)
    script.emit("CREATE_NEW_BASE_REGION", 3, "USER", -0.2)
    script.emit("SET_BASE_REGION_CP", 1, "CUSTOM", -0.2)
    script.emit("SET_BASE_REGION_TRAILING_EDGES", -1)
    script.emit("SELECT_BASE_REGION_FACES", -1)
    script.emit("DELETE_BASE_REGION", 2)
    golden = (GOLDENS / "base_regions_chapter.txt").read_text(encoding="utf-8")
    assert script.render() == golden


def test_the_base_region_cp_is_optional_only_where_a_sample_proves_it():
    """Two commands, one manual page, and only one prints the short form.

    Both say CP is ignored under the empirical model. Only
    SET_BASE_REGION_CP prints a sample passing two arguments, so only it
    records the argument as optional. CREATE_NEW_BASE_REGION's own
    sample passes three and no edition prints a shorter one, so dropping
    it there would be an inference rather than a reading.
    """
    short = Script(version="26.120")
    short.emit("SET_BASE_REGION_CP", 1, "EMPIRICAL")
    assert short.render().strip() == "SET_BASE_REGION_CP 1 EMPIRICAL"

    with pytest.raises(CommandArgumentError):
        Script(version="26.120").emit("CREATE_NEW_BASE_REGION", 3, "EMPIRICAL")


def test_the_two_base_region_commands_have_different_model_vocabularies():
    """Measured, and the asymmetry is real (RPT-021, 2026-08-08).

    The two pages spell the user-specified model differently, USER on
    the creator and CUSTOM on the setter, two commands apart. This test
    used to assert that each refuses the other's token, which was the
    reading of the pages; the probe found the creator taking EITHER
    word and the setter taking CUSTOM alone.

    So the manual is right about the setter and incomplete about the
    creator, and the asymmetry that looked like a documentation slip is
    the solver's own.
    """
    for token in ("USER", "CUSTOM"):
        Script(version="26.120").emit("CREATE_NEW_BASE_REGION", 3, token, -0.2)
    Script(version="26.120").emit("SET_BASE_REGION_CP", 1, "CUSTOM", -0.2)
    with pytest.raises(CommandArgumentError, match="expects one of"):
        Script(version="26.120").emit("SET_BASE_REGION_CP", 1, "USER", -0.2)


def test_the_bending_angle_is_read_from_the_page_that_documents_it():
    """One command, two pages, and the empty heading is not the evidence.

    The Base Regions chapter prints a signature heading with nothing
    beneath it, and p.284 gives the command a table, a range and a
    sample passing a value. An empty heading means a bare command only
    where nothing in the manual argues with it, and here the same manual
    does.
    """
    entry = CommandRegistry.load().commands["SET_BASE_REGION_BENDING_ANGLE"]
    assert [spec.name for spec in entry.args] == ["angle"]
    assert entry.manual_ref == "SRC-003 p.284"
    script = Script(version="26.120")
    script.emit("SET_BASE_REGION_BENDING_ANGLE", 25.0)
    assert "SET_BASE_REGION_BENDING_ANGLE 25.0" in script.render()
    with pytest.raises(CommandArgumentError):
        Script(version="26.120").emit("SET_BASE_REGION_BENDING_ANGLE")


def test_the_base_region_remesh_growth_scheme_is_a_number_and_refuses_the_word():
    """The one place this database spells a growth scheme numerically.

    The three CCS chapters spell the same two schemes SUCCESSIVE and
    DUAL-SIDED, so the word is the natural mistake and it would be
    written into a script the solver does not read.
    """
    with pytest.raises(CommandArgumentError, match="expects one of"):
        Script(version="26.120").emit(
            "REMESH_BASE_REGION",
            base_region=1,
            inner_radius=0.1,
            elements=10,
            growth_scheme="DUAL-SIDED",
            growth_rate=1.2,
        )


# --- Advanced Settings and Inlets and Outlets ---------------------------------


def test_the_advanced_settings_toggles_emit_on_the_editions_that_document_them():
    """The one chapter of the sweep whose version rows differ per command."""
    for version in ("26.100", "26.101", "26.120", "26.121"):
        script = Script(version=version)
        script.emit("KUTTA_JOUKOWSKI_LIFT_FORCES", "ENABLE")
        script.emit("PRINT_ROTOR_INDUCED_VELOCITIES", "ENABLE")
        script.emit("SET_ADAPTIVE_FIELD_GRID_REFINEMENT", "DISABLE")
        assert script.render().splitlines() == [
            "KUTTA_JOUKOWSKI_LIFT_FORCES ENABLE",
            "PRINT_ROTOR_INDUCED_VELOCITIES ENABLE",
            "SET_ADAPTIVE_FIELD_GRID_REFINEMENT DISABLE",
        ]

    # The four the February edition does not document. The count and the
    # tuple disagreed until the 2026-08-08 QA pass: SOLVER_STABILIZATION
    # is the fourth and was missing, so it shipped with no test at all.
    for name, value in (
        ("ROTOR_INDUCED_VELOCITY_BLENDING", 0.5),
        ("SET_WAKE_NUMERICAL_RELAXATION", 0.5),
        ("SET_JET_WAKE_DECAY_NORMALIZED_LENGTH", 25.5),
        ("SOLVER_STABILIZATION", 0.5),
    ):
        with pytest.raises(CommandNotInVersionError):
            Script(version="26.100").emit(name, value)
        later = Script(version="26.101")
        later.emit(name, value)
        assert name in later.render()


def test_the_wake_decay_constant_exists_in_the_hotfix_series_alone():
    """New in 26.121 and carried by 26.122; documented by no earlier edition.

    It was one row until 2026-08-10. The second hotfix of the same
    release documents it too, and that row is explicit rather than
    inherited: inheritance runs from the base release, and 26.120 is the
    edition that does not have this command.
    """
    entry = CommandRegistry.load().commands["SET_WAKE_DECAY_CONSTANT"]
    assert set(entry.versions) == {"26.121", "26.122"}
    assert entry.manual_ref.startswith("SRC-740"), (
        "a command the flagship edition does not document cites the edition that does"
    )
    assert entry.args[0].unit == "1/m", (
        "the unit is derived from the manual's formula and printed nowhere; a decay "
        "constant computed with the length scale in the wrong units is not detectable "
        "from the number"
    )
    for earlier in ("26.100", "26.101", "26.120"):
        with pytest.raises(CommandNotInVersionError):
            Script(version=earlier).emit("SET_WAKE_DECAY_CONSTANT", 120.125)


def test_a_command_the_hotfix_build_dropped_is_refused_there():
    """Measured: 26.121 does not know it (RPT-021, 2026-08-08).

    SET_JET_WAKE_FILAMENTS_GRID_INDUCTION is documented by 26.101 and
    26.120 and by neither neighbour. It had no 26.121 row and was NOT
    marked removed, because a document going quiet is not a statement
    about a solver, and this test asserted the consequence: the command
    emitted on 26.121 by hotfix inheritance.

    That was true and it was wrong. The probe emitted it against the
    26.121 build and the log answered with an unrecognised command, so
    the emitter had been building a line the solver rejects. The row is
    `removed` now, promoted from the report.

    Kept, inverted, because the pair of facts is the point: absence from
    a manual justified inheritance, and only a measurement could
    overturn it.
    """
    entry = CommandRegistry.load().commands["SET_JET_WAKE_FILAMENTS_GRID_INDUCTION"]
    assert set(entry.versions) == {"26.101", "26.120", "26.121", "26.122"}
    # 26.122 joined on 2026-08-10 and its row is the same lesson a step
    # further on. That build inherits from the BASE release, not from
    # the sibling hotfix, so without a row of its own it would have
    # resolved 26.120's documented record and the emitter would have
    # gone back to writing the line the 26.121 run refused. The row
    # rests on the newer edition's silence rather than on a run, because
    # no probe has asked this build; that is weaker evidence and it is
    # still the right way round.
    assert entry.versions["26.122"].status is Status.REMOVED
    assert entry.versions["26.121"].status is Status.REMOVED

    with pytest.raises(CommandNotInVersionError, match="removed"):
        Script(version="26.121").emit("SET_JET_WAKE_FILAMENTS_GRID_INDUCTION", "ENABLE")

    working = Script(version="26.120")
    working.emit("SET_JET_WAKE_FILAMENTS_GRID_INDUCTION", "ENABLE")
    assert "SET_JET_WAKE_FILAMENTS_GRID_INDUCTION ENABLE" in working.render()

    with pytest.raises(CommandNotInVersionError):
        Script(version="26.100").emit("SET_JET_WAKE_FILAMENTS_GRID_INDUCTION", "ENABLE")


@pytest.mark.parametrize("version", ["26.100", "26.101", "26.120", "26.121"])
def test_the_inlets_and_outlets_chapter_emits_on_every_registered_build(version):
    """Both halves, the remesh blocks first, being the geometry-phase pair."""
    script = Script(version=version)
    script.emit(
        "REMESH_INLET",
        inlet=1,
        inner_radius=0.1,
        elements=10,
        growth_scheme="2",
        growth_rate=1.2,
    )
    script.emit(
        "REMESH_OUTLET",
        outlet=1,
        inner_radius=0.1,
        elements=10,
        growth_scheme="2",
        growth_rate=1.2,
    )
    script.emit("CREATE_NEW_INLET", 3, 101.0)
    script.emit("SET_INLET_CUSTOM_PROFILE", 1, "custom_inlet_profile.txt")
    script.emit("DELETE_INLET", 1)
    script.emit("CREATE_NEW_OUTLET", 3, 101.0)
    script.emit("DELETE_OUTLET", 1)
    golden = (GOLDENS / "inlets_outlets_chapter.txt").read_text(encoding="utf-8")
    assert script.render() == golden


def test_an_outlet_has_no_custom_profile_command_in_any_edition():
    """The asymmetry is the manual's, and it bounds what a case can ask for.

    An inlet takes a profile from a file and an outlet is always
    uniform. Asserted rather than left implicit, because the natural
    reading of a symmetric chapter is that the symmetric command exists
    and was missed by the sweep.
    """
    commands = CommandRegistry.load().commands
    assert "SET_INLET_CUSTOM_PROFILE" in commands
    assert "SET_OUTLET_CUSTOM_PROFILE" not in commands


# --- Coordinate Systems, streamlines, Stability and Control -------------------


@pytest.mark.parametrize("version", ["26.100", "26.101", "26.120", "26.121"])
def test_the_coordinate_system_chapter_emits_on_every_registered_build(version):
    """The six that entered on 2026-08-08, on a script that made its frame."""
    script = Script(version=version)
    script.emit("CREATE_NEW_COORDINATE_SYSTEM")
    script.emit("SET_COORDINATE_SYSTEM_NAME", 2, "Propeller_Axis")
    script.emit("NORMALIZE_COORDINATE_SYSTEM", 2)
    script.emit("TRANSLATE_COORDINATE_SYSTEM", 2, 1.0, 0.0, 0.0, "METER")
    script.emit("DUPLICATE_COORDINATE_SYSTEM", 2)
    script.emit("MIRROR_COORDINATE_SYSTEM", 2, "XZ")
    script.emit("DELETE_COORDINATE_SYSTEM", 2)
    golden = (GOLDENS / "coordinate_systems_chapter.txt").read_text(encoding="utf-8")
    assert script.render() == golden


def test_normalize_coordinate_system_takes_the_index_its_sample_passes():
    """Heading with no placeholder, table reading N/A, sample passing 2.

    The same shape as ENABLE_ACTUATOR on the February edition, and read
    the same way: recording zero arguments would refuse the only
    runnable line the vendor prints for the command.
    """
    entry = CommandRegistry.load().commands["NORMALIZE_COORDINATE_SYSTEM"]
    assert [spec.name for spec in entry.args] == ["frame"]
    script = Script(version="26.120")
    script.emit("CREATE_NEW_COORDINATE_SYSTEM")
    script.emit("NORMALIZE_COORDINATE_SYSTEM", 2)
    assert "NORMALIZE_COORDINATE_SYSTEM 2" in script.render()


@pytest.mark.parametrize("version", ["26.100", "26.101", "26.120", "26.121"])
def test_the_streamline_chapter_emits_on_every_registered_build(version):
    """Both families: off-body seeds and on-body friction lines."""
    script = Script(version=version)
    script.emit("CREATE_NEW_COORDINATE_SYSTEM")
    script.emit("NEW_OFF_BODY_STREAMTUBE", 2, "X", 0.0, 0.0, 0.0, 0.5, 5, 8)
    script.emit("SET_OFF_BODY_STREAMLINE_LENGTH", set_length=5.0)
    script.emit("SET_ALL_OFF_BODY_STREAMLINES_UPSTREAM")
    script.emit("SET_ALL_OFF_BODY_STREAMLINES_DOWNSTREAM")
    script.emit("DELETE_ALL_OFF_BODY_STREAMLINES")
    script.emit("GENERATE_ALL_SURFACE_STREAMLINES")
    script.emit("EXPORT_ALL_SURFACE_STREAMLINES", "Test_streamlines.txt")
    script.emit("DELETE_ALL_SURFACE_STREAMLINES")
    golden = (GOLDENS / "streamline_families.txt").read_text(encoding="utf-8")
    assert script.render() == golden


def test_the_off_body_streamline_length_writes_one_alternative_or_the_other():
    """Two keywords the manual states as alternatives, so both are optional.

    SET_UNRESTRICTED_LENGTH is a bare presence keyword taking no value,
    which is what the bool type renders. Nothing refuses both at once:
    the manual states the alternation and not what the solver does when
    given both, so a refusal would be this database inventing a rule.
    """
    bounded = Script(version="26.120")
    bounded.emit("SET_OFF_BODY_STREAMLINE_LENGTH", set_length=5.0)
    assert bounded.render().splitlines()[1] == "SET_LENGTH 5.0"

    unbounded = Script(version="26.120")
    unbounded.emit("SET_OFF_BODY_STREAMLINE_LENGTH", set_unrestricted_length=True)
    assert unbounded.render().splitlines()[1] == "SET_UNRESTRICTED_LENGTH"

    off = Script(version="26.120")
    off.emit("SET_OFF_BODY_STREAMLINE_LENGTH", set_unrestricted_length=False)
    assert off.render().strip() == "SET_OFF_BODY_STREAMLINE_LENGTH", (
        "a false presence keyword writes nothing, rather than writing the keyword "
        "with a value the solver would read as a length"
    )


@pytest.mark.parametrize("version", ["26.100", "26.101", "26.120", "26.121"])
def test_the_stability_toolbox_emits_both_of_its_boundary_forms(version):
    """The two printed samples, which differ in how they name boundaries."""
    script = Script(version=version)
    script.emit("CREATE_NEW_COORDINATE_SYSTEM")
    script.emit("CREATE_NEW_COORDINATE_SYSTEM")
    script.emit("STABILITY_TOOLBOX_SETTINGS", 3, "PER_RADIAN", "DISABLE", 0.2)
    script.emit(
        "STABILITY_TOOLBOX_NEW_COEFFICIENT",
        name="CLq",
        numerator="CL",
        denominator="ROTY",
        frame=2,
        units="COEFFICIENTS",
        constant=208.7682672,
        boundaries=-1,
    )
    script.emit(
        "STABILITY_TOOLBOX_NEW_COEFFICIENT",
        name="CZq",
        numerator="FORCE_Z",
        denominator="ROTY",
        frame=2,
        units="COEFFICIENTS",
        constant=208.7682672,
        boundaries=3,
        boundary_indices=[1, 3, 4],
    )
    script.emit("COMPUTE_STABILITY_COEFFICIENTS")
    script.emit("STABILITY_TOOLBOX_EXPORT", "test_stability.txt")
    script.emit("STABILITY_TOOLBOX_DELETE_ALL")
    golden = (GOLDENS / "stability_toolbox_chapter.txt").read_text(encoding="utf-8")
    assert script.render() == golden


def test_the_stability_coefficient_keywords_follow_the_samples_not_the_table():
    """Two printed samples agree on an order the parameter table does not use.

    The table lists FRAME and UNITS before DENOMINATOR; both samples
    write DENOMINATOR first. Two agreeing runnable lines beat a table's
    layout, and the order is pinned here because it is a judgement:
    whether the solver reads keyword order at all is untested
    (PLN-20260808-2200).
    """
    entry = CommandRegistry.load().commands["STABILITY_TOOLBOX_NEW_COEFFICIENT"]
    assert [spec.name for spec in entry.args] == [
        "name",
        "numerator",
        "denominator",
        "frame",
        "units",
        "constant",
        "boundaries",
        "boundary_indices",
    ]


# --- The tail chapters of 2026-08-08 ------------------------------------------
#
# One walk per chapter file, as every other chapter of the sweep has. The
# tail landed as 28 commands across 21 sections with no emission test at
# all, which the QA pass caught: the schema walk sees an entry, and only
# a render sees the argument ORDER, the own_line placement and the
# count-and-list pairing.


@pytest.mark.parametrize("version", ["26.100", "26.101", "26.120", "26.121"])
def test_the_mesh_unite_chapter_emits_on_every_registered_build(version):
    """The path command first, which the manual says must precede the unite."""
    script = Script(version=version)
    script.emit("BOOLEAN_UNITE_PATH", openvsp_path="VSP/")
    script.emit("BOOLEAN_UNITE_MESH", 5, [1, 2, 3, 4, 5])
    script.emit("BOOLEAN_UNITE_MESH", -1)
    golden = (GOLDENS / "mesh_unite_chapter.txt").read_text(encoding="utf-8")
    assert script.render() == golden


def test_the_unite_list_is_space_separated_where_its_neighbours_use_commas():
    """The separator is emitted literally, so the difference is per command.

    Both samples on the Mesh Unite page print spaces, where SURFACE_COMBINE
    and WRAPPER_SET_INPUT print commas for the same count-then-payload
    shape. Harmonising them would send the solver a line it does not read.
    """
    unite = Script(version="26.120")
    unite.emit("BOOLEAN_UNITE_MESH", 3, [1, 3, 4])
    assert unite.render().splitlines()[1] == "1 3 4"

    combine = Script(version="26.120")
    combine.emit("SURFACE_COMBINE", 3, [1, 3, 4])
    assert combine.render().splitlines()[1] == "1,3,4"


@pytest.mark.parametrize("version", ["26.100", "26.101", "26.120", "26.121"])
def test_the_tail_of_the_cad_and_control_chapters_emits(version):
    """IMPORT_CAD through the log and index commands, in phase order."""
    script = Script(version=version)
    script.emit("IMPORT_CAD", "MEDIUM", "TRUE", 80, "sample.igs")
    script.emit("CONVERT_CAD_TO_MESH", -1)
    script.emit("CAD_CREATE_MIRROR_CURVES", 1, "XZ", "DELETE")
    script.emit("SET_TRAILING_EDGE_SWEEP_ANGLE", 45.0)
    script.emit("SET_TRAILING_EDGE_BLUNTNESS_ANGLE", 85.0)
    script.emit("SET_VERTEX_MERGE_TOLERANCE", 1e-5)
    script.emit("DELETE_TRANSITION_TRIP", 2)
    script.emit("CLEAR_LOG")
    script.emit("OUTPUT_SURFACE_INDICES", "indices.csv")
    golden = (GOLDENS / "tail_cad_and_controls.txt").read_text(encoding="utf-8")
    assert script.render() == golden


def test_the_surface_index_report_writes_to_the_log_when_given_no_path():
    """The rare own_line argument that is not required.

    The manual states the path is optional in as many words, and the two
    forms do different things: with a path the report is a file, without
    one it is log output. A required argument would make the second
    unreachable.
    """
    with_file = Script(version="26.120")
    with_file.emit("OUTPUT_SURFACE_INDICES", "indices.csv")
    assert with_file.render().splitlines()[:2] == ["OUTPUT_SURFACE_INDICES", "indices.csv"]

    to_log = Script(version="26.120")
    to_log.emit("OUTPUT_SURFACE_INDICES")
    assert to_log.render().strip() == "OUTPUT_SURFACE_INDICES"


@pytest.mark.parametrize("version", ["26.100", "26.101", "26.120", "26.121"])
def test_the_tail_of_the_edge_and_section_chapters_emits(version):
    """Trailing edges, wake nodes, and the section deletes and exports."""
    script = Script(version=version)
    script.emit("DETECT_TRAILING_EDGES_BY_SURFACE", surfaces=2, surface_indices=[2, 4])
    script.emit("TRAILING_EDGES_IMPORT", "trailing_edges.csv")
    script.emit("DETECT_WAKE_TERMINATION_NODES_BY_SURFACE", 2)
    script.emit("SET_VORTICITY_LIFT_MODEL", "ENABLE")
    script.emit("SET_SCENE_CONTOUR", "mach_number")
    script.emit("SET_PLOT_TYPE", "FORCE_Z_AXIS_Y")
    script.emit("SAVE_PLOT_TO_FILE", "Test_Plot.txt")
    script.emit("VOLUME_SECTION_WIREFRAME", 2, "ENABLE")
    script.emit("EXPORT_VOLUME_SECTION_2D_VTK", 2, "section_2d.vtk")
    script.emit("DELETE_ALL_SURFACE_SECTIONS")
    script.emit("DELETE_ALL_VOLUME_SECTIONS")
    golden = (GOLDENS / "tail_edges_and_sections.txt").read_text(encoding="utf-8")
    assert script.render() == golden


def test_the_scene_contour_emits_the_lower_case_spelling_its_page_prints():
    """The one lowercase closed set in the database, and it is the page's own.

    Every other closed set here is uppercase because that is how the
    manual prints it; this page prints these 33 in lower case. What
    reaches the script is the DECLARED spelling either way: enum
    matching is case-insensitive and normalises to the member, so a
    caller writing MACH_NUMBER still emits mach_number.

    Pinned because harmonising the values to uppercase is the natural
    tidying edit, and it would silently change what every one of these
    33 tokens puts in a script.
    """
    for written in ("mach_number", "MACH_NUMBER", "Mach_Number"):
        script = Script(version="26.120")
        script.emit("SET_SCENE_CONTOUR", written)
        assert script.render().strip() == "SET_SCENE_CONTOUR mach_number", written

    with pytest.raises(CommandArgumentError, match="expects one of"):
        Script(version="26.120").emit("SET_SCENE_CONTOUR", "not_a_contour")


def test_the_plot_type_list_holds_the_duplicate_only_once():
    """The page prints RESIDUALS twice, in every edition.

    A duplicate in a closed set is dropped rather than recorded, there
    being nothing a second identical token could mean, so the command
    takes 23 tokens and not the 24 rows printed.
    """
    entry = CommandRegistry.load().commands["SET_PLOT_TYPE"]
    (plot_type,) = entry.args
    assert len(plot_type.values) == len(set(plot_type.values)) == 23


@pytest.mark.parametrize("version", ["26.100", "26.101", "26.120", "26.121"])
def test_the_unsteady_animation_writes_both_of_its_printed_forms(version):
    """Two samples: four keyword lines when enabling, one bare line when not.

    Every keyword is optional because of that second sample, and the
    mode sits on the command line, which is the second use of
    `on_command_line` in the database.
    """
    enabling = Script(version=version)
    enabling.emit(
        "UNSTEADY_SOLVER_ANIMATION",
        mode="ENABLE",
        folder="animation_files",
        filetype="PARAVIEW_VTK",
        frequency=1,
        volume_sections="ENABLE",
        volume_sections_format="VTK2D",
    )
    assert enabling.render().rstrip().splitlines() == [
        "UNSTEADY_SOLVER_ANIMATION ENABLE",
        "FOLDER animation_files",
        "FILETYPE PARAVIEW_VTK",
        "FREQUENCY 1",
        "VOLUME_SECTIONS ENABLE VTK2D",
    ]

    disabling = Script(version=version)
    disabling.emit("UNSTEADY_SOLVER_ANIMATION", mode="DISABLE")
    assert disabling.render().strip() == "UNSTEADY_SOLVER_ANIMATION DISABLE"


def test_the_pre_may_commands_refuse_on_every_later_build():
    """Two commands every edition up to February documents and no later one does.

    Written as "the February edition" while 26.100 was the oldest build
    registered. Both reach back to 25.000; what the test is for, that
    they refuse on every build after February, is unchanged.
    """
    for name, args in (("DISABLE_ACTUATOR", (2,)), ("EXECUTE_SOLVER_SWEEPER", ())):
        entry = CommandRegistry.load().commands[name]
        assert sorted(entry.versions) == ["25.000", "25.100", "26.000", "26.100"], name
        for later in ("26.101", "26.120", "26.121"):
            with pytest.raises(CommandNotInVersionError):
                Script(version=later).emit(name, *args)

    early = Script(version="26.100")
    early.emit("CREATE_NEW_ACTUATOR", "PROPELLER", "ELLIPTICAL", "Prop-1")
    early.emit("CREATE_NEW_ACTUATOR", "PROPELLER", "ELLIPTICAL", "Prop-2")
    early.emit("DISABLE_ACTUATOR", 2)
    assert "DISABLE_ACTUATOR 2" in early.render(), (
        "its heading prints no placeholder and its own sample passes an index; "
        "recording zero arguments would refuse the only runnable line the edition has"
    )


def test_the_solver_sweeper_writes_its_two_paths_as_bare_lines():
    """The 21-parameter command, and the shape a reader cannot tell apart.

    Two paths are written unlabelled: a FOLDER after the per-step export
    format, and the results FILE last. Only their position distinguishes
    them, so the order is pinned.
    """
    script = Script(version="26.100")
    script.emit(
        "EXECUTE_SOLVER_SWEEPER",
        angle_of_attack="ENABLE",
        side_slip_angle="DISABLE",
        velocity="DISABLE",
        angle_of_attack_start=0.0,
        angle_of_attack_stop=10.0,
        angle_of_attack_delta=1.0,
        side_slip_angle_start=0.0,
        side_slip_angle_stop=0.0,
        side_slip_angle_delta=1.0,
        export_surface_data_per_step="VTK",
        export_folder="sweep_results/",
        clear_solution_after_each_run="ENABLE",
        reference_velocity_equals_freestream="ENABLE",
        append_to_existing_sweep="DISABLE",
        file="sweep_results/test_sweep.txt",
    )
    lines = script.render().rstrip().splitlines()
    assert lines[0] == "EXECUTE_SOLVER_SWEEPER"
    assert lines[lines.index("EXPORT_SURFACE_DATA_PER_STEP VTK") + 1] == "sweep_results/"
    assert lines[-1] == "sweep_results/test_sweep.txt"


def test_the_two_new_count_spellings_are_checked_against_their_own_lists():
    """The structural guard says the spelling is known; this says it is USED.

    A count disagreeing with its list makes the solver read the next
    command line as data, silently. `test_every_declared_count_is_a_known
    _count_name` would stay green if `_check_counts` regressed, which is
    why the behavioural half exists per spelling.
    """
    for name, kwargs in (
        ("WRAPPER_SET_INPUT", {"num_surfaces": 2, "surface_indices": [1, 2, 3]}),
        ("BOOLEAN_UNITE_MESH", {"num_bodies": 2, "body_indices": [1, 2, 3]}),
    ):
        with pytest.raises(CommandArgumentError):
            Script(version="26.120").emit(name, **kwargs)

    good = Script(version="26.120")
    good.emit("BOOLEAN_UNITE_MESH", num_bodies=3, body_indices=[1, 2, 3])
    assert good.render().splitlines()[:2] == ["BOOLEAN_UNITE_MESH 3", "1 2 3"]


def test_a_keyword_block_is_closed_by_a_blank_line():
    """The terminator, measured by breaking it (RPT-019, 2026-08-08).

    A keyword block ends at a blank line. Without one the solver reads
    the FOLLOWING command as another keyword line and desynchronises,
    and the error it logs names that following command rather than the
    block, so the diagnosis points at the wrong line.

    The emitter has always written the separator, which is why no script
    this library builds has hit it, and why nothing asserted it either.
    Two hand-written probe scripts hit it in the same hour.
    """
    script = Script(version="26.120")
    script.emit(
        "FLUID_PROPERTIES",
        density=1.179,
        pressure=98765.4,
        temperature=291.55,
        viscosity=1.85e-05,
        specific_heat_ratio=1.31,
    )
    script.emit("SOLVER_SET_AOA", 3.0)
    lines = script.render().splitlines()
    assert lines[-3] == "SPECIFIC_HEAT_RATIO 1.31"
    assert lines[-2] == "", (
        "a keyword block must be followed by a blank line; without it the solver "
        "reads the next command as a keyword line (RPT-019)"
    )
    assert lines[-1] == "SOLVER_SET_AOA 3.0"
