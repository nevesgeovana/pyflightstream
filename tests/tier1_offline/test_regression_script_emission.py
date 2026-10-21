"""Regression coverage grouped by subject."""

from __future__ import annotations

import math
import warnings

import pytest

import pyflightstream.script as script_module
from pyflightstream._errors import PyflightstreamWarning
from pyflightstream.commands import CommandEntry, CommandRegistry, Layout
from pyflightstream.script import (
    CommandArgumentError,
    Script,
    ScriptOrderError,
    ScriptReferenceError,
    helpers,
)
from pyflightstream.script.entities import ScriptDeclarationTypeError
from pyflightstream.script.solver_setup import build_setup


def _script_emit___frame(script: Script, name: str, origin: tuple[float, float, float]) -> int:
    return helpers.coordinate_frame(
        script, name=name, origin=origin, x_axis=(1, 0, 0), y_axis=(0, 1, 0)
    )


class TestScriptEmit:
    """P0400 script lane: the emitter's ledgers, its atomicity and its one-line reader.

    One test per review finding of the script package's ``Script`` (0.40.0), each
    named for its planning node: P0400-NEWMODEL (PFS-2088.009), P0400-EMITLINE
    (PFS-2095.054, PFS-2093.012), P0400-ATOMIC (PFS-2103.035, PFS-2104.019),
    P0400-RAWFRAMES (PFS-2104.021), P0400-FRAMECOPY (PFS-2104.017), P0400-MOTION25
    (PFS-2104.018), P0400-SURFACEOPS (PFS-2104.020), and P0400-ALLNOLIST (PFS-2104.022).
    """

    @staticmethod
    # --- P0400-NEWMODEL (PFS-2088.009) -----------------------------------------
    @pytest.mark.parametrize(
        "command, arguments", [("OPEN", ("second.fsm",)), ("NEW_SIMULATION", ())]
    )
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

    @staticmethod
    # --- P0400-EMITLINE (PFS-2095.054, PFS-2093.012) ------------------------------
    @pytest.mark.parametrize(
        "arguments",
        [("CUSTOM", [0.0, 2.0, 4.0]), ("CUSTOM", [5.0]), ("UNIFORM", [-10.0, 20.0, 1.0])],
    )
    def test_p0400_emitline_a_rendered_sweep_line_round_trips(arguments):
        """P0400-EMITLINE (PFS-2095.054, PFS-2093.012): The inline renderer joins a list with spaces;
        emit_line reads it back.
        """  # noqa: E501
        curated = Script(version="26.124")
        curated.emit("SWEEPER_SET_AOA_SWEEP", *arguments)
        line = curated.render().splitlines()[0]
        carried = Script(version="26.124")
        carried.emit_line(line)
        assert carried.render() == curated.render()

    @staticmethod
    def test_p0400_emitline_a_token_after_an_omitted_list_reaches_its_own_argument():
        """P0400-EMITLINE (PFS-2095.054, PFS-2093.012): the helper preserves its declared contract."""  # noqa: E501
        curated = Script(version="26.124")
        curated.emit("SWEEPER_SET_AOA_SWEEP", "CUSTOM", filename="aoa.txt")
        carried = Script(version="26.124")
        carried.emit_line(curated.render().splitlines()[0])
        assert carried.render() == curated.render()

    @staticmethod
    def test_p0400_emitline_left_over_tokens_are_refused_naming_the_cause():
        """P0400-EMITLINE (PFS-2095.054, PFS-2093.012): the helper preserves its declared contract."""  # noqa: E501
        script = Script(version="26.124")
        with pytest.raises(CommandArgumentError) as refused:
            script.emit_line("SWEEPER_EXPORT_SPREADSHEET C:/Program Files/sweep.txt")
        message = str(refused.value)
        assert "'Files/sweep.txt'" in message
        assert "a value containing a space" in message
        assert "Script.emit" in message
        assert "takes at most" not in message
        assert script.render() == "\n"

    @staticmethod
    def test_p0400_emitline_reads_a_bool_token_as_a_bool():
        """P0400-EMITLINE (PFS-2095.054, PFS-2093.012): the helper preserves its declared contract."""  # noqa: E501
        entry = CommandEntry(
            name="BOOL_FIXTURE",
            chapter="fixture",
            layout="keyword_block",
            phase="geometry",
            args=[{"name": "flag", "type": "bool"}],
            manual_ref="FSM-26.120 p.1",
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

    @staticmethod
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

    @staticmethod
    def test_p0400_atomic_a_refused_emission_moves_no_phase():
        """P0400-ATOMIC (PFS-2103.035, PFS-2104.019): the helper preserves its declared contract."""
        script = Script(version="26.124")
        with pytest.raises(ScriptReferenceError):
            script.emit("SET_SOLVER_ANALYSIS_LOADS_FRAME", 5)
        script.emit("CREATE_NEW_COORDINATE_SYSTEM")
        assert script.num_local_frames == 1

    @staticmethod
    # --- P0400-RAWFRAMES (PFS-2104.021) -----------------------------------------
    def test_p0400_rawframes_raw_text_forgets_every_placement_but_the_reference():
        """P0400-RAWFRAMES (PFS-2104.021): the helper preserves its declared contract."""
        script = Script(version="26.124")
        nacelle = _script_emit___frame(script, "NAC", (1.0, 2.0, 3.0))
        script.emit("SET_SOLVER_ANALYSIS_LOADS_FRAME", nacelle)
        script.raw("TRANSLATE_COORDINATE_SYSTEM 2 1.0 0.0 0.0 METER")
        held = script.frame_placements[nacelle]
        assert held.origin is None and held.axes is None
        assert script.frame_placements[1].origin == (0.0, 0.0, 0.0)
        record = script.loads_frame_record()
        assert record["origin"] is None and record["axes"] is None

    @staticmethod
    # --- P0400-FRAMECOPY (PFS-2104.017) -----------------------------------------
    def test_p0400_framecopy_a_duplicate_is_counted_so_the_next_frame_is_not_it():
        """P0400-FRAMECOPY (PFS-2104.017): the helper preserves its declared contract."""
        script = Script(version="26.124")
        _script_emit___frame(script, "NAC", (1.0, 0.0, 0.0))
        script.emit("DUPLICATE_COORDINATE_SYSTEM", 2)
        script.emit("MIRROR_COORDINATE_SYSTEM", 2, "XZ")
        assert script.frame_placements[2].origin == (1.0, 0.0, 0.0)
        assert script.num_local_frames == 3
        assert 3 not in script.frame_placements and 4 not in script.frame_placements
        tail = _script_emit___frame(script, "TAIL", (9.0, 0.0, 0.0))
        assert tail == 5, "the solver appends the new frame after the two copies, at 5"
        assert script.frame_placements[5].origin == (9.0, 0.0, 0.0)

    @staticmethod
    def test_p0400_framecopy_a_frame_delete_renumbers_the_labels_above_it():
        """P0400-FRAMECOPY (PFS-2104.017): RPT-021 section 3: the survivors keep their names and take
        the indices below.
        """  # noqa: E501
        script = Script(version="26.124")
        for label in ("a", "b", "c"):
            script.emit("CREATE_NEW_COORDINATE_SYSTEM", label=label)
        script.emit("DELETE_COORDINATE_SYSTEM", 2)
        assert script.num_local_frames == 2
        assert script.entities.labels("frames") == {"b": 2, "c": 3}
        with pytest.raises(ScriptReferenceError):
            script.emit("NORMALIZE_COORDINATE_SYSTEM", 4)

    @staticmethod
    @pytest.mark.parametrize(
        "command, arguments",
        [("DUPLICATE_COORDINATE_SYSTEM", (2,)), ("MIRROR_COORDINATE_SYSTEM", (2, "XZ"))],
    )
    def test_p0400_framecopy_each_copy_appends_one_frame(command, arguments):
        """P0400-FRAMECOPY (PFS-2104.017): the next frame follows the copy in the registry."""
        script = Script("26.124")
        _script_emit___frame(script, "NAC", (1.0, 0.0, 0.0))
        script.emit(command, *arguments)
        assert script.num_local_frames == 2
        assert _script_emit___frame(script, "TAIL", (9.0, 0.0, 0.0)) == 4

    @staticmethod
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

    @staticmethod
    def test_p0400_motion25_every_creation_command_of_the_database_is_classified():
        """P0400-MOTION25 (PFS-2104.018): the helper preserves its declared contract."""
        commands = CommandRegistry.load().commands
        creations = sorted(name for name in commands if name.startswith("CREATE_NEW_"))
        counted = set(script_module._CREATION_COMMANDS)
        uncounted = set(getattr(script_module, "_UNCOUNTED_CREATIONS", ()))
        assert not counted & uncounted
        assert [name for name in creations if name not in counted | uncounted] == []

    @staticmethod
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

    @staticmethod
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

    @staticmethod
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


class TestScriptEntities:
    """P0400 script lane: the entity registry.

    P0400-LABELSHIFT (PFS-2104.025, PFS-2104.026) and P0400-DECLARETYPE (PFS-2097.011).
    """

    @staticmethod
    # --- P0400-LABELSHIFT (PFS-2104.025, PFS-2104.026) ---------------------------
    def test_p0400_labelshift_deleting_the_first_of_two_keeps_the_survivor_label():
        """P0400-LABELSHIFT (PFS-2104.025, PFS-2104.026): the helper preserves its declared contract."""  # noqa: E501
        script = Script(version="26.124")
        script.emit(
            "CREATE_NEW_ACTUATOR", "PROPELLER", "ELLIPTICAL", name="left_prop", label="left"
        )
        script.emit(
            "CREATE_NEW_ACTUATOR", "PROPELLER", "ELLIPTICAL", name="right_prop", label="right"
        )
        script.emit("DELETE_ACTUATOR", 1)
        assert script.entities.labels("actuators") == {"right": 1}
        script.emit("ENABLE_ACTUATOR", "right")
        assert script.render().splitlines()[-1] == "ENABLE_ACTUATOR 1"
        with pytest.raises(ScriptReferenceError, match="unknown actuator label 'left'"):
            script.emit("ENABLE_ACTUATOR", "left")

    @staticmethod
    def test_p0400_labelshift_deleting_one_of_three_renumbers_the_survivors():
        """P0400-LABELSHIFT (PFS-2104.025, PFS-2104.026): the helper preserves its declared contract."""  # noqa: E501
        script = Script(version="26.124")
        for label in ("a", "b", "c"):
            script.emit("CREATE_NEW_MOTION", "ROTARY", label=label)
        script.emit("DELETE_MOTION", 1)
        assert script.entities.labels("motions") == {"b": 1, "c": 2}
        script.emit("SET_MOTION_START_TIME", "c", 0.5)
        assert script.render().splitlines()[-1] == "SET_MOTION_START_TIME 2 0.5"

    @staticmethod
    # --- P0400-DECLARETYPE (PFS-2097.011) ---------------------------------------
    @pytest.mark.parametrize("count", ["2", 1.5, True, None])
    def test_p0400_declaretype_a_count_that_is_not_an_integer_is_refused(count):
        """P0400-DECLARETYPE (PFS-2097.011): the helper preserves its declared contract."""
        script = Script(version="26.124")
        with pytest.raises(ScriptDeclarationTypeError, match="whole count"):
            script.declare_existing(frames=count)
        assert script.num_local_frames == 0


def _script_helpers___rotor_frame(script: Script) -> int:
    return helpers.coordinate_frame(
        script, name="HUB", origin=(0.0, 0.0, 0.0), x_axis=(1, 0, 0), y_axis=(0, 1, 0)
    )


class TestScriptHelpers:
    """P0400 script lane: the curated helpers.

    One test per review finding, each named for its planning node: P0400-VTKVARS
    (PFS-2085.009), P0400-VTKWAKE (PFS-2104.047), P0400-EMPTYSEL (PFS-2085.018),
    P0400-AXISCASE (PFS-2095.055), P0400-ROTORUNIT (PFS-2088.010), P0400-WAKEUNITS
    (PFS-2104.027), P0400-WAKEX (PFS-2104.024, the sweep axes) and P0400-EXPORTS
    (PFS-2093.004, PFS-2093.011).
    """

    @staticmethod
    # --- P0400-VTKVARS (PFS-2085.009) and P0400-VTKWAKE (PFS-2104.047) -----------
    @pytest.mark.parametrize("variables", ["CP", "X"])
    def test_p0400_vtkvars_a_bare_variable_string_is_refused(variables):
        """P0400-VTKVARS (PFS-2085.009): the helper preserves its declared contract."""
        script = Script(version="26.124")
        with pytest.raises(CommandArgumentError, match=r"for example \["):
            helpers.export_results(script, vtk="a.vtk", vtk_variables=variables)
        assert script.render() == "\n"

    @staticmethod
    def test_p0400_vtkwake_the_wake_flag_without_a_variable_selection_is_refused():
        """P0400-VTKWAKE (PFS-2104.047): the helper preserves its declared contract."""
        script = Script(version="26.124")
        with pytest.raises(CommandArgumentError, match="vtk_variables"):
            helpers.export_results(script, vtk="a.vtk", vtk_wake=True)
        assert script.render() == "\n"
        helpers.export_results(script, vtk="a.vtk", vtk_variables="all", vtk_wake=True)
        assert "SET_VTK_EXPORT_VARIABLES -1 ENABLE" in script.render().splitlines()

    @staticmethod
    # --- P0400-EMPTYSEL (PFS-2085.018) ------------------------------------------
    @pytest.mark.parametrize("argument", ["boundaries", "moving_frames"])
    def test_p0400_emptysel_rotary_motion_refuses_an_empty_selection(argument):
        """P0400-EMPTYSEL (PFS-2085.018): the helper preserves its declared contract."""
        script = Script(version="26.124")
        frame = _script_helpers___rotor_frame(script)
        before = script.render()
        with pytest.raises(CommandArgumentError, match="empty sequence"):
            helpers.rotary_motion(script, frame=frame, axis="X", rpm=1200.0, **{argument: []})
        assert script.render() == before

    @staticmethod
    def test_p0400_emptysel_analysis_setup_refuses_an_empty_selection():
        """P0400-EMPTYSEL (PFS-2085.018): the helper preserves its declared contract."""
        script = Script(version="26.124")
        with pytest.raises(CommandArgumentError, match="empty sequence"):
            helpers.analysis_setup(script, boundaries=[])
        assert script.render() == "\n"

    @staticmethod
    # --- P0400-AXISCASE (PFS-2095.055) ------------------------------------------
    @pytest.mark.parametrize("version", ["26.000", "26.124"])
    def test_p0400_axiscase_a_lowercase_axis_is_read_on_every_vocabulary(version):
        """P0400-AXISCASE (PFS-2095.055): the helper preserves its declared contract."""
        lower, upper = Script(version=version), Script(version=version)
        for script, axis in ((lower, "z"), (upper, "Z")):
            helpers.rotary_motion(
                script, frame=_script_helpers___rotor_frame(script), axis=axis, rpm=600.0
            )
        assert lower.render() == upper.render()

    @staticmethod
    # --- P0400-ROTORUNIT (PFS-2088.010) -----------------------------------------
    def test_p0400_rotorunit_a_rotor_on_the_unmarked_build_uses_measured_rpm():
        """PFS-2004.01 supersedes the unproved-unit refusal with batch-8 evidence."""
        script = Script(version="26.100")
        frame = _script_helpers___rotor_frame(script)
        helpers.rotary_motion(script, frame=frame, axis="X", rpm=1200.0)
        velocity = next(
            line.split()
            for line in script.render().splitlines()
            if line.startswith("SET_MOTION_ANGULAR_VELOCITY")
        )
        assert [float(value) for value in velocity[2:]] == [1200.0, 0.0, 0.0]
        assert "SET_MOTION_IS_ROTOR" not in script.render()

    @staticmethod
    def test_p0400_rotorunit_a_rotor_on_a_rotary_build_does_not_warn():
        """P0400-ROTORUNIT (PFS-2088.010): the helper preserves its declared contract."""
        script = Script(version="26.124")
        frame = _script_helpers___rotor_frame(script)
        with warnings.catch_warnings():
            warnings.simplefilter("error", PyflightstreamWarning)
            helpers.rotary_motion(script, frame=frame, axis="X", rpm=1200.0)

    @staticmethod
    # --- P0400-WAKEUNITS (PFS-2104.027) -----------------------------------------
    def test_p0400_wakeunits_points_in_another_unit_are_converted_to_the_simulations():
        """P0400-WAKEUNITS (PFS-2104.027): the helper preserves its declared contract."""
        script = Script(version="26.124")
        script.emit("SET_SIMULATION_LENGTH_UNITS", "MILLIMETER")
        helpers.mark_wake_edges(
            script,
            edge_type="STANDARD",
            tolerance=0.1,
            units="METER",
            node_file="wing.wake_nodes.txt",
            midpoints=[(1.0, -3.75, 0.0)],
        )
        assert "IMPORT_WAKE_EDGES_FROM_FILE STANDARD 0.1 MILLIMETER" in script.render().splitlines()
        rows = script.pending_input_files["wing.wake_nodes.txt"].splitlines()
        assert rows[-1] == "1000.0,-3750.0,0.0"

    @staticmethod
    def test_p0400_wakeunits_points_in_the_simulations_unit_are_written_as_given():
        """P0400-WAKEUNITS (PFS-2104.027): the helper preserves its declared contract."""
        script = Script(version="26.124")
        script.emit("SET_SIMULATION_LENGTH_UNITS", "METER")
        helpers.mark_wake_edges(
            script,
            edge_type="STANDARD",
            tolerance=0.0001,
            units="METER",
            node_file="wing.wake_nodes.txt",
            midpoints=[(1.0, -3.75, 0.0)],
        )
        assert "IMPORT_WAKE_EDGES_FROM_FILE STANDARD 0.0001 METER" in script.render().splitlines()
        assert script.pending_input_files["wing.wake_nodes.txt"].splitlines()[-1] == "1.0,-3.75,0.0"

    @staticmethod
    @pytest.mark.parametrize("axis", ["aoa", "beta"])
    def test_p0400_wakex_an_empty_sweep_axis_is_refused(axis):
        """P0400-WAKEX (PFS-2097.010, PFS-2104.024): the helper preserves its declared contract."""
        script = Script(version="26.124")
        with pytest.raises(CommandArgumentError, match="empty sequence"):
            helpers.sweep(script, **{axis: []}, start=False)
        assert script.render() == "\n"

    @staticmethod
    # --- P0400-EXPORTS (PFS-2093.004, PFS-2093.011) ------------------------------
    def test_p0400_exports_export_results_refuses_a_path_the_script_exports_to():
        """P0400-EXPORTS (PFS-2093.004, PFS-2093.011): the helper preserves its declared contract."""  # noqa: E501
        script = Script(version="26.124")
        helpers.export_results(script, spreadsheet="out/loads.txt")
        with pytest.raises(CommandArgumentError, match="already exports to") as refused:
            helpers.export_results(script, tecplot="out/sub/../LOADS.txt")
        assert "from export_results" in str(refused.value)
        assert script.render().count("EXPORT_SOLVER_ANALYSIS_TECPLOT") == 0

    @staticmethod
    def test_p0400_exports_one_call_naming_one_file_twice_writes_nothing():
        """P0400-EXPORTS (PFS-2093.004, PFS-2093.011): the helper preserves its declared contract."""  # noqa: E501
        script = Script(version="26.124")
        with pytest.raises(CommandArgumentError, match="are one file"):
            helpers.export_results(script, spreadsheet="a.txt", tecplot="./A.txt")
        assert script.render() == "\n"

    @staticmethod
    def test_p0400_exports_the_two_export_helpers_share_one_key():
        """P0400-EXPORTS (PFS-2093.004, PFS-2093.011): export_probes keyed the raw path; one file
        through a parent folder or a case change was two keys.
        """
        script = Script(version="26.124")
        helpers.export_probes(script, "probes.txt", update=False)
        with pytest.raises(CommandArgumentError, match="from export_probes"):
            helpers.export_probes(script, "sub/../PROBES.txt", update=False)
        with pytest.raises(CommandArgumentError, match="from export_probes"):
            helpers.export_results(script, spreadsheet="Probes.txt")
        assert script.render().count("EXPORT_") == 1

    @staticmethod
    def test_p0400_exports_an_action_script_and_an_input_file_never_share_a_path():
        """P0400-EXPORTS (PFS-2093.004, PFS-2093.011): the helper preserves its declared contract."""  # noqa: E501
        script = Script(version="26.124")
        helpers.mark_wake_edges(
            script,
            edge_type="STANDARD",
            tolerance=0.0001,
            units="METER",
            node_file="shared.txt",
            midpoints=[(1.0, 0.0, 0.0)],
        )
        with pytest.raises(CommandArgumentError, match="input file"):
            helpers.unsteady_action(
                script, name="post", kind="SCRIPT", filename="SHARED.txt", action_script="X\n"
            )
        other = Script(version="26.124")
        helpers.unsteady_action(
            other, name="post", kind="SCRIPT", filename="shared.txt", action_script="X\n"
        )
        with pytest.raises(CommandArgumentError, match="action script"):
            helpers.mark_wake_edges(
                other,
                edge_type="STANDARD",
                tolerance=0.0001,
                units="METER",
                node_file="shared.txt",
                midpoints=[(1.0, 0.0, 0.0)],
            )

    @staticmethod
    def test_p0400_exports_direct_commands_share_the_helpers_register():
        """P0400-EXPORTS (PFS-2093.011): every EXPORT path participates at emit."""
        script = Script("26.124")
        script.emit("EXPORT_SOLVER_ANALYSIS_SPREADSHEET", "loads.txt")
        before = script.render()
        with pytest.raises(CommandArgumentError, match="already exports to"):
            script.emit("EXPORT_SOLVER_ANALYSIS_TECPLOT", "sub/../LOADS.txt")
        with pytest.raises(CommandArgumentError, match="already exports to"):
            helpers.export_probes(script, "./Loads.txt")
        assert script.render() == before

    @staticmethod
    @pytest.mark.parametrize("workflow", ["unsteady_rotor", "qsteady_rotor", "steady"])
    def test_p0400_rotorunit_workflow_rehearsal_uses_the_measured_unit(workflow):
        """PFS-2004.01 restores rotor builds without accepting foreign workflow keys."""
        from pyflightstream.cases import CampaignConfigError
        from pyflightstream.cases.workflows import build_script
        from tests.tier1_offline.test_workflows import qsteady_case, rotor_case, steady_case

        factories = {
            "unsteady_rotor": rotor_case,
            "qsteady_rotor": qsteady_case,
            "steady": steady_case,
        }
        case = factories[workflow]()
        if workflow == "steady":
            case = case.model_copy(update={"variables": {**case.variables, "RPM": "1200"}})
        script = Script("26.100")
        if workflow == "steady":
            with pytest.raises(CampaignConfigError, match="RPM"):
                build_script(case, script)
        else:
            build_script(case, script)
            assert "START_SOLVER" in script.render()


class TestScriptRelaxedTe:
    """P0400-RELAXEDTE (PFS-2097.017, PFS-2097.018): RelaxedTrailingEdge resolves and refuses."""

    @staticmethod
    # --- P0400-RELAXEDTE (PFS-2097.017, PFS-2097.018) ----------------------------
    @pytest.mark.parametrize(
        ("direction", "token"),
        [(0, "AXIAL"), (1, "AZIMUTH"), ("azimuth", "AZIMUTH"), ("1", "AZIMUTH")],
    )
    def test_p0400_relaxedte_the_constructor_takes_the_directions_its_refusal_names(
        direction, token
    ):
        """P0400-RELAXEDTE (PFS-2097.017, PFS-2097.018): the helper preserves its declared contract."""  # noqa: E501
        edge = helpers.RelaxedTrailingEdge(fields=("0.5", "0.1", "0.9"), direction=direction)
        assert edge.direction == token
        assert helpers.parse_relaxed_trailing_edge(edge.render()) == edge

    @staticmethod
    @pytest.mark.parametrize("direction", [2, -1, True, "SIDEWAYS"])
    def test_p0400_relaxedte_a_third_direction_is_still_refused(direction):
        """P0400-RELAXEDTE (PFS-2097.017, PFS-2097.018): the helper preserves its declared contract."""  # noqa: E501
        with pytest.raises(CommandArgumentError, match="neither"):
            helpers.RelaxedTrailingEdge(fields=("0.5", "0.1", "0.9"), direction=direction)

    @staticmethod
    @pytest.mark.parametrize(
        "fields", [("0.5", "", "0.9"), ("0.5", "  ", "0.9"), ("0.5", "0.1;0.9", "1")]
    )
    def test_p0400_relaxedte_a_field_that_cannot_render_is_refused(fields):
        """P0400-RELAXEDTE (PFS-2097.017, PFS-2097.018): the helper preserves its declared contract."""  # noqa: E501
        with pytest.raises(CommandArgumentError, match="blank or hold"):
            helpers.RelaxedTrailingEdge(fields=fields)


class TestScriptReview:
    """Review regressions for frame deletion, export identity and version defaults.

    Reproductions: delete reference frame 1, export a sweep over a loads file,
    and build a 26.125 solver snapshot without an explicit jet decay length.
    """

    @staticmethod
    @pytest.mark.parametrize(
        "locals_count", [0, 2], ids=["P0400-REFDELETE-empty", "P0400-REFDELETE-local"]
    )
    def test_p0400_reference_frame_cannot_be_deleted(locals_count):
        script = Script("26.124")
        script.declare_existing(frames=locals_count)
        before = script.render()
        with pytest.raises(CommandArgumentError, match="reference frame"):
            script.emit("DELETE_COORDINATE_SYSTEM", 1)
        assert script.render() == before
        assert script.num_local_frames == locals_count
        script.emit("CREATE_NEW_COORDINATE_SYSTEM", label="next")
        assert script.entities.labels("frames")["next"] == locals_count + 2

    @staticmethod
    @pytest.mark.parametrize(
        "sweep_first", [True, False], ids=["P0400-SWEEPEXPORT-first", "P0400-SWEEPEXPORT-last"]
    )
    def test_p0400_sweep_exports_share_output_identity(sweep_first):
        script = Script("26.124")
        commands = ["SWEEPER_EXPORT_SPREADSHEET", "EXPORT_SOLVER_ANALYSIS_SPREADSHEET"]
        if not sweep_first:
            commands.reverse()
        script.emit(commands[0], "results.txt")
        before = script.render()
        with pytest.raises(CommandArgumentError, match="already exports to"):
            script.emit(commands[1], "sub/../RESULTS.txt")
        assert script.render() == before

    @staticmethod
    @pytest.mark.parametrize(
        "command",
        ["CAD_CREATE_CURVE_EXPORT_CCS", "STABILITY_TOOLBOX_EXPORT", "UNSTEADY_SOLVER_EXPORT_PLOTS"],
        ids=["P0400-EXPORT-cad", "P0400-EXPORT-stability", "P0400-EXPORT-unsteady"],
    )
    def test_p0400_exports_with_other_prefixes_share_output_identity(command):
        script = Script("26.124")
        script.emit(command, "results.txt")
        before = script.render()
        with pytest.raises(CommandArgumentError, match="already exports to"):
            script.emit(command, "sub/../RESULTS.txt")
        assert script.render() == before

    @staticmethod
    @pytest.mark.parametrize(
        "version",
        ["26.124", "26.125"],
        ids=["P0400-JETDEFAULT-earlier", "P0400-JETDEFAULT-changed"],
    )
    def test_p0400_jet_default_never_claims_the_wrong_editions_value(version):
        script = Script(version)
        setup = helpers.solver_settings(script)
        record = setup.flags["SET_JET_WAKE_DECAY_NORMALIZED_LENGTH"]
        if version == "26.124":
            assert (record.provenance, record.value) == ("default", 100.0)
        else:
            assert (record.provenance, record.value, record.evidence) == (
                "default",
                10.0,
                "FSM-26.125 p.358",
            )
        assert not record.emitted
        setup = helpers.solver_settings(script, jet_wake_decay_normalized_length=17.0)
        explicit = setup.flags["SET_JET_WAKE_DECAY_NORMALIZED_LENGTH"]
        assert (explicit.provenance, explicit.value, explicit.emitted) == ("explicit", 17.0, True)


_SCRIPT_SETTINGS__FLUID = {
    "density": 1.2,
    "pressure": 101325.0,
    "temperature": 288.15,
    "viscosity": 1.8e-5,
    "specific_heat_ratio": 1.4,
}


class TestScriptSettings:
    """P0400 script lane: the settings helpers, their snapshot, and the relaxed trailing edge.

    One test per review finding, each named for its planning node: P0400-ALTUNITS
    (PFS-2085.019), P0400-WAKEX (PFS-2097.010, PFS-2104.024), P0400-FREESTREAM
    (PFS-2097.016), P0400-ENUMSNAP (PFS-2103.012), P0400-FLUSH (PFS-2104.045),
    P0400-REFREQUEST (PFS-2104.046), P0400-SNAPMERGE (PFS-2103.011), P0400-UNSTEADYSNAP
    (PFS-2103.037) and P0400-MINCP (PFS-2104.023).
    """

    @staticmethod
    # --- P0400-ALTUNITS (PFS-2085.019) ------------------------------------------
    def test_p0400_altunits_an_altitude_unit_without_an_altitude_is_refused():
        """P0400-ALTUNITS (PFS-2085.019): the helper preserves its declared contract."""
        script = Script(version="26.124")
        with pytest.raises(CommandArgumentError, match="has no meaning"):
            helpers.atmosphere(script, altitude_units="FEET", **_SCRIPT_SETTINGS__FLUID)
        assert script.render() == "\n"
        helpers.atmosphere(script, **_SCRIPT_SETTINGS__FLUID)
        assert script.render().startswith("FLUID_PROPERTIES")

    @staticmethod
    # --- P0400-WAKEX (PFS-2097.010, PFS-2104.024) --------------------------------
    @pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf, "nan", "inf", "banana"])
    def test_p0400_wakex_a_wake_termination_that_is_not_a_finite_number_is_refused(value):
        """P0400-WAKEX (PFS-2097.010, PFS-2104.024): the helper preserves its declared contract."""
        script = Script(version="26.124")
        with pytest.raises(CommandArgumentError, match="wake_termination_x"):
            helpers.initialize_solver(script, wake_termination_x=value)
        assert script.render() == "\n"

    @staticmethod
    @pytest.mark.parametrize(
        ("value", "token"),
        [
            ("default", "DEFAULT"),
            ("DEFAULT", "DEFAULT"),
            (12.5, "12.5"),
            (1e-05, "0.00001"),
            ("3", "3"),
        ],
    )
    def test_p0400_wakex_a_finite_or_default_wake_termination_renders_one_token(value, token):
        """P0400-WAKEX (PFS-2097.010, PFS-2104.024): the helper preserves its declared contract."""
        script = Script(version="26.124")
        helpers.initialize_solver(script, wake_termination_x=value)
        assert f"WAKE_TERMINATION_X {token}" in script.render().splitlines()

    @staticmethod
    @pytest.mark.parametrize("surfaces", [[], [(-1, True)]])
    def test_p0400_wakex_an_empty_or_all_form_per_surface_list_is_refused(surfaces):
        """P0400-WAKEX (PFS-2097.010, PFS-2104.024): the helper preserves its declared contract."""
        script = Script(version="26.124")
        script.declare_existing(boundaries=3)
        with pytest.raises(CommandArgumentError, match="surfaces"):
            helpers.initialize_solver(script, surfaces=surfaces)
        assert script.render() == "\n"

    @staticmethod
    # --- P0400-FREESTREAM (PFS-2097.016) ----------------------------------------
    def test_p0400_freestream_an_unknown_kind_is_refused_by_name():
        """P0400-FREESTREAM (PFS-2097.016): the helper preserves its declared contract."""
        script = Script(version="26.124")
        with pytest.raises(CommandArgumentError) as refused:
            helpers.free_stream(script, "ROTATING", frame=2, axis="X", rpm=900.0)
        message = str(refused.value)
        assert "'ROTATING'" in message
        assert all(kind in message for kind in ("CONSTANT", "ROTATION", "CUSTOM"))
        assert "takes no further input" not in message

    @staticmethod
    # --- P0400-ENUMSNAP (PFS-2103.012) ------------------------------------------
    def test_p0400_enumsnap_the_snapshot_records_the_member_the_script_wrote():
        """P0400-ENUMSNAP (PFS-2103.012): the helper preserves its declared contract."""
        script = Script(version="25.000")
        setup = helpers.solver_settings(script, solver_model="incompressible")
        assert "SET_SOLVER_MODEL INCOMPRESSIBLE" in script.render().splitlines()
        assert setup.flags["SET_SOLVER_MODEL"].value == "INCOMPRESSIBLE"

    @staticmethod
    # --- P0400-FLUSH (PFS-2104.045) ---------------------------------------------
    def test_p0400_flush_a_refused_flush_keeps_the_selection_pending():
        """P0400-FLUSH (PFS-2104.045): the helper preserves its declared contract."""
        script = Script(version="26.124")
        script.declare_existing(boundaries=2)
        helpers.solver_settings(script, vorticity_drag_boundaries=[1])
        script.emit("START_SOLVER")
        script.emit("EXPORT_SOLVER_ANALYSIS_SPREADSHEET", "first.txt")
        with pytest.raises(ScriptOrderError):
            helpers.export_results(script, spreadsheet="second.txt")
        assert script._pending_vorticity == [1]

    @staticmethod
    # --- P0400-REFREQUEST (PFS-2104.046) ----------------------------------------
    @pytest.mark.parametrize("value", ["DISABLE", "false", "ENABLE", 0, 1, None])
    def test_p0400_refrequest_a_non_bool_request_is_refused(value):
        """P0400-REFREQUEST (PFS-2104.046): the helper preserves its declared contract."""
        script = Script(version="26.124")
        with pytest.raises(CommandArgumentError, match="Pass True to request it"):
            helpers.solver_settings(script, disable_ref_velocity=value)
        assert "DISABLE_SOLVER_REF_VELOCITY" not in script.render()

    @staticmethod
    def test_p0400_refrequest_the_snapshot_refuses_a_non_bool_request_too():
        """P0400-REFREQUEST (PFS-2104.046): the helper preserves its declared contract."""
        with pytest.raises(CommandArgumentError, match="Pass True to request it"):
            build_setup(
                version="26.124",
                passed={"disable_ref_velocity": "DISABLE"},
                minimum_cp_default_emitted=False,
            )

    @staticmethod
    def test_p0400_refrequest_true_requests_it():
        """P0400-REFREQUEST (PFS-2104.046): the helper preserves its declared contract."""
        script = Script(version="26.124")
        setup = helpers.solver_settings(script, disable_ref_velocity=True)
        assert "DISABLE_SOLVER_REF_VELOCITY" in script.render().splitlines()
        assert setup.flags["DISABLE_SOLVER_REF_VELOCITY"].provenance == "explicit"

    @staticmethod
    # --- P0400-SNAPMERGE (PFS-2103.011) -----------------------------------------
    def test_p0400_snapmerge_a_second_call_keeps_the_flags_the_first_one_wrote():
        """P0400-SNAPMERGE (PFS-2103.011): the helper preserves its declared contract."""
        script = Script(version="26.124")
        helpers.solver_settings(script, velocity=30.0, iterations=500, disable_ref_velocity=True)
        setup = helpers.solver_settings(script, aoa=5.0)
        for command, value in (("SOLVER_SET_VELOCITY", 30.0), ("SOLVER_SET_ITERATIONS", 500)):
            record = setup.flags[command]
            assert (record.provenance, record.value, record.emitted) == ("explicit", value, True)
        assert setup.flags["DISABLE_SOLVER_REF_VELOCITY"].emitted is True
        assert setup.flags["SOLVER_SET_AOA"].value == 5.0

    @staticmethod
    def test_p0400_snapmerge_a_keyword_the_second_call_passes_is_its_own_record():
        """P0400-SNAPMERGE (PFS-2103.011): the helper preserves its declared contract."""
        script = Script(version="26.124")
        script.declare_existing(boundaries=2)
        helpers.solver_settings(script, viscous_excluded=[1])
        setup = helpers.solver_settings(script, viscous_excluded=[])
        assert setup.flags["SET_VISCOUS_EXCLUDED_BOUNDARIES"].provenance != "explicit"
        assert setup.flags["DELETE_VISCOUS_EXCLUDED_BOUNDARIES"].provenance == "explicit"

    @staticmethod
    # --- P0400-UNSTEADYSNAP (PFS-2103.037) --------------------------------------
    def test_p0400_unsteadysnap_the_regime_unsteady_solver_wrote_is_recorded():
        """P0400-UNSTEADYSNAP (PFS-2103.037): the helper preserves its declared contract."""
        script = Script(version="26.124")
        helpers.unsteady_solver(script, time_iterations=120, delta_time=0.01)
        setup = helpers.solver_settings(script, velocity=10.0)
        record = setup.flags["SET_SOLVER_UNSTEADY"]
        assert (record.provenance, record.emitted) == ("explicit", True)
        assert record.value == {"time_iterations": 120, "delta_time": 0.01}

    @staticmethod
    def test_p0400_unsteadysnap_an_existing_snapshot_is_restamped():
        """P0400-UNSTEADYSNAP (PFS-2103.037): the helper preserves its declared contract."""
        script = Script(version="26.124")
        helpers.solver_settings(script, mode="STEADY", velocity=10.0)
        helpers.unsteady_solver(script, time_iterations=120, delta_time=0.01)
        assert script.solver_setup is not None
        record = script.solver_setup.flags["SET_SOLVER_UNSTEADY"]
        assert (record.provenance, record.emitted) == ("explicit", True)
        assert script.solver_setup.flags["SET_SOLVER_STEADY"].provenance != "explicit"

    @staticmethod
    # --- P0400-MINCP (PFS-2104.023) ---------------------------------------------
    def test_p0400_mincp_a_second_call_does_not_write_the_default_over_an_explicit_value():
        """P0400-MINCP (PFS-2104.023): the helper preserves its declared contract."""
        script = Script(version="26.124")
        helpers.solver_settings(script, minimum_cp=-3.0, aoa=0.0)
        setup = helpers.solver_settings(script, aoa=4.0)
        lines = [
            line for line in script.render().splitlines() if line.startswith("SOLVER_MINIMUM_CP")
        ]
        assert lines == ["SOLVER_MINIMUM_CP -3.0"]
        record = setup.flags["SOLVER_MINIMUM_CP"]
        assert (record.provenance, record.value, record.emitted) == ("explicit", -3.0, True)

    @staticmethod
    def test_p0400_mincp_the_library_default_is_written_once():
        """P0400-MINCP (PFS-2104.023): the helper preserves its declared contract."""
        script = Script(version="26.124")
        helpers.solver_settings(script, aoa=0.0)
        setup = helpers.solver_settings(script, aoa=4.0)
        assert script.render().count("SOLVER_MINIMUM_CP") == 1
        record = setup.flags["SOLVER_MINIMUM_CP"]
        assert (record.provenance, record.emitted) == ("default", True)

    @staticmethod
    def test_p0400_mincp_a_limiter_emitted_by_hand_is_not_overwritten_or_guessed():
        """P0400-MINCP (PFS-2104.023): the helper preserves its declared contract."""
        script = Script(version="26.124")
        script.emit("SOLVER_MINIMUM_CP", -7.0)
        setup = helpers.solver_settings(script, aoa=4.0)
        assert script.render().count("SOLVER_MINIMUM_CP") == 1
        record = setup.flags["SOLVER_MINIMUM_CP"]
        assert (record.provenance, record.value, record.emitted) == ("unknown", None, True)
