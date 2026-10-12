"""P0400 script lane: the emitter's ledgers, its atomicity and its one-line reader.

One test per review finding of the script package's ``Script`` (0.40.0), each
named for its planning node: P0400-NEWMODEL (PFS-2088.009), P0400-EMITLINE
(PFS-2095.054, PFS-2093.012), P0400-ATOMIC (PFS-2103.035, PFS-2104.019),
P0400-RAWFRAMES (PFS-2104.021), P0400-FRAMECOPY (PFS-2104.017), P0400-MOTION25
(PFS-2104.018), P0400-SURFACEOPS (PFS-2104.020), and P0400-ALLNOLIST (PFS-2104.022).
"""

from __future__ import annotations

import pytest

import pyflightstream.script as script_module
from pyflightstream.commands import CommandEntry, CommandRegistry, Layout
from pyflightstream.script import (
    CommandArgumentError,
    Script,
    ScriptReferenceError,
    helpers,
)


def _frame(script: Script, name: str, origin: tuple[float, float, float]) -> int:
    return helpers.coordinate_frame(
        script, name=name, origin=origin, x_axis=(1, 0, 0), y_axis=(0, 1, 0)
    )


# --- P0400-NEWMODEL (PFS-2088.009) -----------------------------------------


@pytest.mark.parametrize("command, arguments", [("OPEN", ("second.fsm",)), ("NEW_SIMULATION", ())])
def test_p0400_newmodel_a_second_model_is_refused_once_entities_exist(command, arguments):
    """P0400-NEWMODEL (PFS-2088.009): a populated model belongs to one Script."""
    script = Script(version="26.124")
    script.emit("OPEN", "first.fsm")
    script.declare_existing(frames=2, actuators=1, motions=1, boundaries={"wing": 1, "tail": 2})
    script.record_opened_length_unit("MILLIMETER")
    before = script.render()
    with pytest.raises(CommandArgumentError, match="cannot replace a model"):
        script.emit(command, *arguments)
    assert script.render() == before
    assert script.num_local_frames == 2
    assert script.num_actuators == 1
    assert script.simulation_length_unit == "MILLIMETER"


# --- P0400-EMITLINE (PFS-2095.054, PFS-2093.012) ------------------------------


@pytest.mark.parametrize(
    "arguments",
    [("CUSTOM", [0.0, 2.0, 4.0]), ("CUSTOM", [5.0]), ("UNIFORM", [-10.0, 20.0, 1.0])],
)
def test_p0400_emitline_a_rendered_sweep_line_round_trips(arguments):
    """P0400-EMITLINE (PFS-2095.054, PFS-2093.012): The inline renderer joins a list with spaces;
    emit_line reads it back.
    """
    curated = Script(version="26.124")
    curated.emit("SWEEPER_SET_AOA_SWEEP", *arguments)
    line = curated.render().splitlines()[0]
    carried = Script(version="26.124")
    carried.emit_line(line)
    assert carried.render() == curated.render()


def test_p0400_emitline_a_token_after_an_omitted_list_reaches_its_own_argument():
    """P0400-EMITLINE (PFS-2095.054, PFS-2093.012): the helper preserves its declared contract."""
    curated = Script(version="26.124")
    curated.emit("SWEEPER_SET_AOA_SWEEP", "CUSTOM", filename="aoa.txt")
    carried = Script(version="26.124")
    carried.emit_line(curated.render().splitlines()[0])
    assert carried.render() == curated.render()


def test_p0400_emitline_left_over_tokens_are_refused_naming_the_cause():
    """P0400-EMITLINE (PFS-2095.054, PFS-2093.012): the helper preserves its declared contract."""
    script = Script(version="26.124")
    with pytest.raises(CommandArgumentError) as refused:
        script.emit_line("SWEEPER_EXPORT_SPREADSHEET C:/Program Files/sweep.txt")
    message = str(refused.value)
    assert "'Files/sweep.txt'" in message
    assert "a value containing a space" in message
    assert "Script.emit" in message
    assert "takes at most" not in message
    assert script.render() == "\n"


def test_p0400_emitline_reads_a_bool_token_as_a_bool():
    """P0400-EMITLINE (PFS-2095.054, PFS-2093.012): the helper preserves its declared contract."""
    entry = CommandEntry(
        name="BOOL_FIXTURE",
        chapter="fixture",
        layout="keyword_block",
        phase="geometry",
        args=[{"name": "flag", "type": "bool"}],
        manual_ref="SRC-003 p.1",
        versions={"26.124": {"status": "documented"}},
    )
    # Isolate the line reader from the database rule that today's bools are
    # presence keywords. A future inline bool must still read a bool token.
    entry = entry.model_copy(update={"layout": Layout.INLINE})
    registry = CommandRegistry({entry.name: entry})
    for token, flag in (("ENABLE", True), ("false", False)):
        curated, carried = Script("26.124", registry), Script("26.124", registry)
        curated.emit(entry.name, flag)
        carried.emit_line(f"{entry.name} {token}")
        assert carried.render() == curated.render()
    with pytest.raises(CommandArgumentError, match="ENABLE or DISABLE"):
        Script("26.124", registry).emit_line("BOOL_FIXTURE maybe")


# --- P0400-ATOMIC (PFS-2103.035, PFS-2104.019) -------------------------------


def test_p0400_atomic_a_refused_waived_emission_records_no_waiver():
    """P0400-ATOMIC (PFS-2103.035, PFS-2104.019): the helper preserves its declared contract."""
    script = Script(version="26.120")
    script.allow_broken("AIR_ALTITUDE", reason="re-probe at sea level")
    with pytest.raises(CommandArgumentError):
        script.emit("AIR_ALTITUDE", "oops", "METERS")
    assert script.waived_commands == ()
    script.emit("AIR_ALTITUDE", 0.0, "METERS")
    assert [use.first_line for use in script.waived_commands] == ["AIR_ALTITUDE 0.0 METERS"]


def test_p0400_atomic_a_refused_emission_moves_no_phase():
    """P0400-ATOMIC (PFS-2103.035, PFS-2104.019): the helper preserves its declared contract."""
    script = Script(version="26.124")
    with pytest.raises(ScriptReferenceError):
        script.emit("SET_SOLVER_ANALYSIS_LOADS_FRAME", 5)
    script.emit("CREATE_NEW_COORDINATE_SYSTEM")
    assert script.num_local_frames == 1


# --- P0400-RAWFRAMES (PFS-2104.021) -----------------------------------------


def test_p0400_rawframes_raw_text_forgets_every_placement_but_the_reference():
    """P0400-RAWFRAMES (PFS-2104.021): the helper preserves its declared contract."""
    script = Script(version="26.124")
    nacelle = _frame(script, "NAC", (1.0, 2.0, 3.0))
    script.emit("SET_SOLVER_ANALYSIS_LOADS_FRAME", nacelle)
    script.raw("TRANSLATE_COORDINATE_SYSTEM 2 1.0 0.0 0.0 METER")
    held = script.frame_placements[nacelle]
    assert held.origin is None and held.axes is None
    assert script.frame_placements[1].origin == (0.0, 0.0, 0.0)
    record = script.loads_frame_record()
    assert record["origin"] is None and record["axes"] is None


# --- P0400-FRAMECOPY (PFS-2104.017) -----------------------------------------


def test_p0400_framecopy_a_duplicate_is_counted_so_the_next_frame_is_not_it():
    """P0400-FRAMECOPY (PFS-2104.017): the helper preserves its declared contract."""
    script = Script(version="26.124")
    _frame(script, "NAC", (1.0, 0.0, 0.0))
    script.emit("DUPLICATE_COORDINATE_SYSTEM", 2)
    script.emit("MIRROR_COORDINATE_SYSTEM", 2, "XZ")
    assert script.frame_placements[2].origin == (1.0, 0.0, 0.0)
    assert script.num_local_frames == 3
    assert 3 not in script.frame_placements and 4 not in script.frame_placements
    tail = _frame(script, "TAIL", (9.0, 0.0, 0.0))
    assert tail == 5, "the solver appends the new frame after the two copies, at 5"
    assert script.frame_placements[5].origin == (9.0, 0.0, 0.0)


def test_p0400_framecopy_a_frame_delete_renumbers_the_labels_above_it():
    """P0400-FRAMECOPY (PFS-2104.017): RPT-021 section 3: the survivors keep their names and take
    the indices below.
    """
    script = Script(version="26.124")
    for label in ("a", "b", "c"):
        script.emit("CREATE_NEW_COORDINATE_SYSTEM", label=label)
    script.emit("DELETE_COORDINATE_SYSTEM", 2)
    assert script.num_local_frames == 2
    assert script.entities.labels("frames") == {"b": 2, "c": 3}
    with pytest.raises(ScriptReferenceError):
        script.emit("NORMALIZE_COORDINATE_SYSTEM", 4)


@pytest.mark.parametrize(
    "command, arguments",
    [("DUPLICATE_COORDINATE_SYSTEM", (2,)), ("MIRROR_COORDINATE_SYSTEM", (2, "XZ"))],
)
def test_p0400_framecopy_each_copy_appends_one_frame(command, arguments):
    """P0400-FRAMECOPY (PFS-2104.017): the next frame follows the copy in the registry."""
    script = Script("26.124")
    _frame(script, "NAC", (1.0, 0.0, 0.0))
    script.emit(command, *arguments)
    assert script.num_local_frames == 2
    assert _frame(script, "TAIL", (9.0, 0.0, 0.0)) == 4


# --- P0400-MOTION25 (PFS-2104.018) ------------------------------------------


@pytest.mark.parametrize(
    "command",
    [
        "CREATE_NEW_MOTION_EUCLIDEAN",
        "CREATE_NEW_MOTION_CUSTOM",
        "CREATE_NEW_MOTION_6DOF",
        "CREATE_NEW_MOTION_FSI",
    ],
)
def test_p0400_motion25_a_type_specific_creation_is_a_motion(command):
    """P0400-MOTION25 (PFS-2104.018): the helper preserves its declared contract."""
    script = Script(version="25.000")
    script.emit(command, label="rotor")
    assert script.num_motions == 1
    script.emit("SET_MOTION_START_TIME", "rotor", 0.0)
    assert script.render().splitlines()[-1] == "SET_MOTION_START_TIME 1 0.0"


def test_p0400_motion25_every_creation_command_of_the_database_is_classified():
    """P0400-MOTION25 (PFS-2104.018): the helper preserves its declared contract."""
    commands = CommandRegistry.load().commands
    creations = sorted(name for name in commands if name.startswith("CREATE_NEW_"))
    counted = set(script_module._CREATION_COMMANDS)
    uncounted = set(getattr(script_module, "_UNCOUNTED_CREATIONS", ()))
    assert not counted & uncounted
    assert [name for name in creations if name not in counted | uncounted] == []


# --- P0400-SURFACEOPS (PFS-2104.020) ----------------------------------------


@pytest.mark.parametrize(
    ("version", "command", "arguments"),
    [
        ("25.000", "SURFACE_SCALE", (1, 2.0, 2.0, 2.0, -1)),
        ("25.000", "SURFACE_MIRROR", (1, 1, 2, "TRUE", "FALSE")),
        (
            "26.120",
            "SURFACE_ROTATE",
            {
                "frame": 1,
                "axis": "X",
                "angle": 10.0,
                "surfaces": -1,
                "split_vertices": "DISABLE",
                "adaptive_mesh": "DISABLE",
                "detach_normal_to_axis": "DISABLE",
            },
        ),
        ("26.124", "SURFACE_SCALE", (1, 2.0, 2.0, 2.0, -1)),
        ("26.124", "SURFACE_MIRROR", (1, 1, 2, "TRUE", "FALSE")),
        ("26.124", "ROTATE_SURFACE", (1, "X", 10.0, -1, "DISABLE")),
    ],
)
def test_p0400_surfaceops_every_mesh_transform_is_recorded(version, command, arguments):
    """P0400-SURFACEOPS (PFS-2104.020): the helper preserves its declared contract."""
    script = Script(version=version)
    if isinstance(arguments, dict):
        script.emit(command, **arguments)
    else:
        script.emit(command, *arguments)
    assert [operation["command"] for operation in script.surface_operations] == [command]


def test_p0400_surfaceops_every_transform_of_the_mesh_chapter_is_in_the_set():
    """P0400-SURFACEOPS (PFS-2104.020): the helper preserves its declared contract."""
    commands = CommandRegistry.load().commands
    verbs = ("ROTATE", "TRANSLATE", "SCALE", "MIRROR", "TRANSFORM", "COPY_PASTE")
    transforms = sorted(
        name
        for name, entry in commands.items()
        if entry.chapter == "mesh_operations" and any(verb in name for verb in verbs)
    )
    assert len(transforms) >= 9, transforms
    assert (
        sorted(set(transforms) - set(getattr(script_module, "_SURFACE_TRANSFORM_COMMANDS", ())))
        == []
    )


# --- P0400-ALLNOLIST (PFS-2104.022) -----------------------------------------


def test_p0400_allnolist_a_payload_under_the_all_count_is_refused():
    """P0400-ALLNOLIST (PFS-2104.022): the helper preserves its declared contract."""
    script = Script(version="26.124")
    with pytest.raises(CommandArgumentError, match="takes no payload"):
        script.emit("SOLVER_PROXIMAL_BOUNDARIES", -1, [1, 2, 3])
    script.emit("CREATE_NEW_MOTION", "ROTARY")
    with pytest.raises(CommandArgumentError, match="takes no payload"):
        script.emit("SET_MOTION_MOVING_FRAMES", 1, -1, [1])
    script.emit("SET_MOTION_MOVING_FRAMES", 1, -1)
    assert script.render().splitlines()[-2:] == ["SET_MOTION_MOVING_FRAMES 1 -1", ""]
