"""The probe catalog, seventh part: the command gaps of 0.40.0 (PFS-2081.13 to .17).

Pipeline role: the licensed probes that settle what the five command-gap use
cases of 0.40.0 leave to measurement before any of them is coded: the mesh
operations (P1), the CAD bodies and CAD Create (P2), the streamlines (P3), the
6DOF motion (P4) and the external FSI executable (P5). Every gap command is
recorded ``documented`` and unprobed on 26.124 and 26.125, so each one gets a
probe here before a workflow emits it.

TWO REGISTRIES, BECAUSE ONE COMMAND CAN CARRY SEVERAL QUESTIONS. The shared
``PROBE_SPECS`` is keyed by command, and its entry is the probe whose verdict
may promote that command's status through ``pyfs-qa apply-compat``. Several
gap commands need more than one run to answer what the use cases ask (the
motion type an FSI executable attaches to, an export placed before and after
the march, a selection read with and without a subset), and some runs are
controls that only make another run's reading discriminating. Those live in
the ordered battery :func:`gap_probes` returns, keyed by probe id, and only the
entries marked ``primary`` register into ``PROBE_SPECS``.

EVERY JUDGE IS LAX WHERE NOTHING IS MEASURED YET, and strict only where the
instrument is a file the solver wrote and the target is the one command that
could have changed it (a saved simulation whose face count does not move across
a copy that was asked for three copies). Each spec carries an ``observe``
reading, because most of these probes answer a question (how a copy is named,
what a scale is about, which unit a rate is in) rather than a yes or no, and the
answer is the reading, kept beside the verdict in the compat report.

THE INPUTS ARE SYNTHETIC: a wing meshed from the public four-digit thickness law,
a box with a known hole and a known degenerate face, a two-sheet IGES file and
section files written here, and a stand-in structural program that only logs
its call and answers with zero displacements. No research geometry is read; the
inputs, readers and judges live in ``pyflightstream.qa._spec_0400_gapkit``.

The module is imported by ``pyflightstream.qa.specs`` and registers its primary
entries into the shared registry of ``pyflightstream.qa._spec_kit``.

Size exemption: one declarative battery of 103 probe entries, each a question with its control.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path

from pyflightstream.fsi.state import LOADS_FILE
from pyflightstream.qa._spec_0400_gapkit import (
    _CCS_WING_CURVES,
    _DEFLECTED,
    _NODES,
    _PITCH_ONLY,
    _ROOT_3D,
    _SECTION_TXT,
    _SMALL_WING,
    _SOLVE_TIMEOUT_S,
    _TIP_3D,
    _TRAJECTORY,
    _aero_frame,
    _after_the_march_trajectory,
    _boundaries_at_least,
    _boundaries_grew,
    _cad_session,
    _cad_session_ccs,
    _called,
    _calls_read,
    _ccs_moved,
    _ccs_written,
    _collapsed_edge,
    _convert,
    _custom_force,
    _declined_export,
    _deflected,
    _drag_read,
    _edges_read,
    _emit_export_all,
    _export,
    _export_ccs,
    _export_format,
    _exports,
    _face_order_read,
    _faces_moved,
    _file_written,
    _flow,
    _groups_read,
    _iges_import,
    _import_box,
    _import_marks,
    _import_p3d,
    _import_txt,
    _import_txt_as,
    _import_wing,
    _loft_exported,
    _march,
    _march_then_trajectory,
    _marks_read,
    _marks_reproduced,
    _motion,
    _moved_read,
    _naca_points,
    _nodes_only,
    _not_called,
    _nothing_converted,
    _obj_range_moved,
    _obj_source,
    _obj_spans,
    _offbody_export,
    _offbody_file,
    _only_sheet_a,
    _pitch_kick,
    _pitch_only,
    _pod_import,
    _primitive_exists,
    _read_back_and_loft,
    _reimport_with_marks,
    _reversed_first_point,
    _save,
    _saved_names_file,
    _sections_in_frame_then_start,
    _seed_line,
    _selection_took,
    _selection_took_all,
    _seq_read,
    _sixdof_body,
    _solved_wing,
    _sphere_row_read,
    _start,
    _state_or_faces_moved,
    _state_still,
    _states_read,
    _streamline_table,
    _surface_export,
    _surface_lines_deleted,
    _threshold,
    _trajectory_export,
    _two_meshes_differ,
    _units_and_edges,
    _windowless_python,
    _wing_and_sphere,
    _write_post,
    _write_standin,
    _write_standin_build,
    edges_kept,
    emptied,
    file_rows,
    one_vertex_moved,
    reordered,
    trajectory_moved,
    trajectory_read,
)
from pyflightstream.qa._spec_ccs_noise import (
    _REFERENCE_WING,
    _ccs_assign,
    _ccs_select,
    _export_obj,
    _mesh_differs,
    _mesh_read,
    _wing_loft,
)
from pyflightstream.qa._spec_kit import PROBE_SPECS, _emit, _seq
from pyflightstream.qa.errors import QaEvidenceError
from pyflightstream.qa.probes import ProbeSpec, Requires, fsm_changed
from pyflightstream.script import Script

__all__: list[str] = []


#: The planning node of each capability.
NODES = {
    "G": "PFS-2081.14",
    "P1": "PFS-2081.13",
    "P2": "PFS-2081.14",
    "P3": "PFS-2081.15",
    "P4": "PFS-2081.16",
    "P5": "PFS-2081.17",
    "D": "PFS-2085.021",
}


@dataclass(frozen=True)
class GapProbe:
    """One licensed run of the 0.40.0 command-gap batch.

    Attributes
    ----------
    probe_id : str
        Stable identifier, ordered within its capability (``P5-A2``, ``P1-03``).
    capability : str
        ``P1`` to ``P5``, or ``G`` for what a saved geometry must keep (owner
        decision of 2026-10-12: geometry is built outside the matrix and saved).
    question : str
        What the run settles, in the use case's words.
    control : str
        What makes the reading discriminating: the bracketing state, or the
        battery probe that is this one's control.
    spec : ProbeSpec
        The probe itself; ``spec.command`` is the command under test.
    primary : bool
        The entry registered into ``PROBE_SPECS`` for ``spec.command``.
    stage : str
        ``first`` for the runs the owner ordered ahead of the rest (P5 probe A),
        ``main`` otherwise.
    opens : str or None
        The probe id whose saved simulation (``saved.fsm``) this one opens
        (``Requires.SIM``); the batch runner passes that file as the probe's ``fsm``.
    opens_other_build : bool
        The file opened is the one the other build saved (26.124 opens what
        26.125 saved, and the reverse), so the runner schedules it last.
    solves : bool
        Whether the run starts the solver (used for the time estimate).
    """

    probe_id: str
    capability: str
    question: str
    control: str
    spec: ProbeSpec
    primary: bool = False
    stage: str = "main"
    opens: str | None = None
    solves: bool = False
    opens_other_build: bool = False

    @property
    def node(self) -> str:
        """Return the planning node the probe serves."""
        return NODES[self.capability]


def _g(
    probe_id: str,
    capability: str,
    question: str,
    control: str,
    *,
    primary: bool = False,
    stage: str = "main",
    opens: str | None = None,
    solves: bool = False,
    opens_other_build: bool = False,
    **spec: object,
) -> GapProbe:
    if solves and "timeout_s" not in spec:
        spec["timeout_s"] = _SOLVE_TIMEOUT_S
    return GapProbe(
        probe_id=probe_id,
        capability=capability,
        question=question,
        control=control,
        spec=ProbeSpec(**spec),  # type: ignore[arg-type]
        primary=primary,
        stage=stage,
        opens=opens,
        solves=solves,
        opens_other_build=opens_other_build,
    )


def _p5_first(standin: Path | None) -> list[GapProbe]:
    """P5 probe A: the FSI executable after each documented motion type, and its control."""

    def executable(script: Script, workdir: Path) -> None:
        _write_standin(workdir)
        target = standin if standin is not None else _windowless_python()
        script.emit("SET_MOTION_FSI_EXECUTABLE", 1, "DISABLE", "ENABLE", target)

    name = (standin or _windowless_python()).name
    probes = []
    for index, kind in enumerate(("ROTARY", "6DOF", "CUSTOM"), start=1):
        probes.append(
            _g(
                f"P5-A{index}",
                "P5",
                f"is SET_MOTION_FSI_EXECUTABLE recognised after CREATE_NEW_MOTION {kind}, does the "
                "saved simulation keep the executable, and is the executable called during a "
                "three-step march",
                "the saved state before the command (no executable named), and P5-A0 (the same "
                "march with no FSI command, so a call can only come from the command)",
                primary=kind == "6DOF",
                stage="first",
                solves=True,
                command="SET_MOTION_FSI_EXECUTABLE",
                build_target=executable,
                prelude=_seq(_import_wing(), _units_and_edges, _motion(kind)),
                save_state=True,
                epilogue=_march(steps=3),
                assert_effect=_saved_names_file(name),
                observe=_seq_read(_states_read(), _calls_read),
                effect_note=(
                    f"the saved simulation names the executable {name} after the command, on a "
                    f"{kind} motion; the reading says whether the march called it"
                ),
            )
        )
    probes.insert(
        0,
        _g(
            "P5-A0",
            "P5",
            "control of probe A: a 6DOF march with the stand-in written but no FSI command; the "
            "stand-in must not be called",
            "this run is the control of P5-A1 to P5-A3",
            stage="first",
            solves=True,
            command="CREATE_NEW_MOTION",
            build_target=_emit("CREATE_NEW_MOTION", "6DOF"),
            prelude=_seq(_import_wing(), _units_and_edges, _write_standin_build),
            epilogue=_seq(_emit("SET_MOTION_BOUNDARIES", 1, -1), _march(steps=3)),
            assert_effect=_not_called,
            observe=_calls_read,
            effect_note="with no FSI command the stand-in is never called",
        ),
    )
    return probes


def _p1() -> list[GapProbe]:
    blade = _import_wing("Blade", translation=(0.0, 2.5, 0.0))
    states = _states_read
    return [
        _g(
            "P1-01",
            "P1",
            "circular copy of one blade, three copies of 90: does it run, are the copies new "
            "surfaces, how are they named and numbered, and is the angle the step or the sweep",
            "the saved state before the copy (one surface)",
            primary=True,
            command="SURFACE_CIRCULAR_COPY_PASTE",
            build_target=_emit("SURFACE_CIRCULAR_COPY_PASTE", 1, 1, "X", 3, 90.0),
            prelude=blade,
            save_state=True,
            epilogue=_exports(4),
            assert_effect=_faces_moved("up", strict=True),
            observe=states(*(f"surface_{i}.obj" for i in range(1, 5))),
            effect_note=(
                "the saved face count grows across a copy asked for three copies; the azimuth "
                "of each surface about X says whether 90 is the step or the sweep"
            ),
        ),
        _g(
            "P1-02",
            "P1",
            "linear copy, two copies of a 500 MILLIMETER step in y: naming, numbering, and whether "
            "the vector follows the UNITS argument (0.5 m) or the simulation's unit (500 m)",
            "the saved state before the copy",
            primary=True,
            command="SURFACE_LINEAR_COPY_PASTE",
            build_target=_emit("SURFACE_LINEAR_COPY_PASTE", 1, 2, 1, "MILLIMETER", 0.0, 500.0, 0.0),
            prelude=_import_wing(),
            save_state=True,
            epilogue=_exports(3),
            assert_effect=_faces_moved("up", strict=True),
            observe=states(*(f"surface_{i}.obj" for i in range(1, 4))),
            effect_note="the saved face count grows across a copy asked for two copies",
        ),
        _g(
            "P1-03",
            "P1",
            "cut of the wing by the XZ plane at y = 0.75, between two mesh stations (the first "
            "batch cut at y = 0.5, on a station line, and nothing moved): how many surfaces it "
            "leaves, their names and positions",
            "the saved state before the cut",
            primary=True,
            command="SURFACE_CUT_BY_PLANE",
            build_target=_emit("SURFACE_CUT_BY_PLANE", frame=1, plane="XZ", offset=0.75, surface=1),
            prelude=_import_wing(),
            save_state=True,
            epilogue=_exports(3),
            assert_effect=_state_or_faces_moved,
            observe=states(*(f"surface_{i}.obj" for i in range(1, 4))),
            effect_note="the saved boundary list or face count changes across the cut",
        ),
        _g(
            "P1-04",
            "P1",
            "threshold on X (0.5 to 2.0, every face) then a new surface from the selection: is the "
            "selection made",
            "the saved state before the threshold, against the state after the new surface",
            primary=True,
            command="SURFACE_SELECT_BY_THRESHOLD",
            build_target=_threshold(0.5, 2.0),
            prelude=_import_wing(),
            save_state=True,
            epilogue=_seq(_emit("CREATE_NEW_SURFACE_FROM_SELECTION"), _save("saved.fsm")),
            assert_effect=_boundaries_grew("saved.fsm"),
            observe=states("saved.fsm"),
            effect_note=(
                "a surface made from the selection after the threshold adds a boundary to the "
                "saved simulation"
            ),
        ),
        _g(
            "P1-05",
            "P1",
            "new surface from a threshold selection: its name and position, and whether the "
            "source keeps the faces not selected",
            "P1-05c, the same command with nothing selected",
            primary=True,
            command="CREATE_NEW_SURFACE_FROM_SELECTION",
            build_target=_emit("CREATE_NEW_SURFACE_FROM_SELECTION"),
            prelude=_seq(_import_wing(), _threshold(0.5, 2.0)),
            save_state=True,
            epilogue=_exports(2),
            assert_effect=_boundaries_grew(),
            observe=states("surface_1.obj", "surface_2.obj"),
            effect_note="the saved simulation gains a boundary made of the selected faces",
        ),
        _g(
            "P1-05c",
            "P1",
            "control of P1-05: a new surface from an empty selection",
            "this run is the control of P1-05",
            command="CREATE_NEW_SURFACE_FROM_SELECTION",
            build_target=_emit("CREATE_NEW_SURFACE_FROM_SELECTION"),
            prelude=_import_wing(),
            save_state=True,
            assert_effect=_state_still,
            observe=states(),
            effect_note="with nothing selected the saved simulation does not move",
        ),
        _g(
            "P1-06",
            "P1",
            "selection by surface id then a threshold restricted to SELECTED_FACES: does the "
            "subset read the surface selection",
            "P1-06c, the same with subset ALL_FACES",
            primary=True,
            command="SURFACE_SELECT_BY_ID",
            build_target=_emit("SURFACE_SELECT_BY_ID", 2),
            prelude=_seq(
                _import_wing(),
                _import_wing("Small", _SMALL_WING, (3.0, 0.0, 0.0), new=False),
            ),
            save_state=True,
            epilogue=_seq(
                _threshold(-100.0, 100.0, subset="SELECTED_FACES"),
                _emit("CREATE_NEW_SURFACE_FROM_SELECTION"),
                _save("saved.fsm"),
            ),
            assert_effect=_selection_took(2),
            observe=states("saved.fsm"),
            effect_note=(
                "the surface made from a SELECTED_FACES threshold has the face count of "
                "surface 2, the one selected by id"
            ),
        ),
        _g(
            "P1-06c",
            "P1",
            "control of P1-06: the same selection by id, then a threshold over ALL_FACES",
            "this run is the control of P1-06",
            command="SURFACE_SELECT_BY_ID",
            build_target=_emit("SURFACE_SELECT_BY_ID", 2),
            prelude=_seq(
                _import_wing(),
                _import_wing("Small", _SMALL_WING, (3.0, 0.0, 0.0), new=False),
            ),
            save_state=True,
            epilogue=_seq(
                _threshold(-100.0, 100.0, subset="ALL_FACES"),
                _emit("CREATE_NEW_SURFACE_FROM_SELECTION"),
                _save("saved.fsm"),
            ),
            assert_effect=_selection_took_all,
            observe=states("saved.fsm"),
            effect_note="over ALL_FACES the new surface takes every face of both surfaces",
        ),
        _g(
            "P1-07",
            "P1",
            "automatic hole fill on a box missing its top: face counts before and after",
            "the saved state before the fill (ten triangles)",
            primary=True,
            command="SURFACE_AUTO_HOLE_FILL",
            build_target=_emit("SURFACE_AUTO_HOLE_FILL", 1),
            prelude=_import_box(hole=True, degenerate=False),
            save_state=True,
            assert_effect=_faces_moved("up", strict=False),
            observe=states(),
            effect_note="the saved face count grows when the hole is filled",
        ),
        _g(
            "P1-08",
            "P1",
            "degenerate face deletion on the wing after node 1 is moved to 0.1 mm from its "
            "trailing-edge neighbour (the importer drops a zero-area triangle, and a node moved "
            "onto its neighbour takes its two faces out before the delete): face counts",
            "the saved state before the deletion, holding the two sliver faces",
            primary=True,
            command="DELETE_DEGENERATE_FACES",
            build_target=_emit("DELETE_DEGENERATE_FACES"),
            prelude=_collapsed_edge,
            save_state=True,
            assert_effect=_faces_moved("down", strict=False),
            observe=states(),
            effect_note="the saved face count drops by the degenerate triangle",
        ),
        _g(
            "P1-09",
            "P1",
            "deletion of the faces a threshold selected: face counts",
            "the saved state before the deletion",
            primary=True,
            command="DELETE_SELECTED_FACES",
            build_target=_emit("DELETE_SELECTED_FACES"),
            prelude=_seq(_import_wing(), _threshold(0.5, 2.0)),
            save_state=True,
            assert_effect=_faces_moved("down", strict=False),
            observe=states(),
            effect_note="the saved face count drops by the selected faces",
        ),
        _g(
            "P1-10",
            "P1",
            "node selection by id: which vertex node 1 is, read by moving it 0.25 m in z",
            "the surface exported before the selection",
            primary=True,
            command="SELECT_MESH_NODE",
            build_target=_emit("SELECT_MESH_NODE", 1),
            prelude=_seq(_import_wing(), _export(1, "before.obj")),
            epilogue=_seq(
                _emit("TRANSFORM_SELECTED_NODES", 1, "TRANSLATION", 0.0, 0.0, 0.25),
                _export(1, "after.obj"),
            ),
            assert_effect=one_vertex_moved(None),
            observe=_moved_read,
            effect_note="one vertex of the exported surface moves after the selected node is moved",
        ),
        _g(
            "P1-11",
            "P1",
            "node transform by TRANSLATION 0.25 m in z of the selected node: is the move a "
            "translation in the reference frame",
            "the surface exported before the transform",
            primary=True,
            command="TRANSFORM_SELECTED_NODES",
            build_target=_emit("TRANSFORM_SELECTED_NODES", 1, "TRANSLATION", 0.0, 0.0, 0.25),
            prelude=_seq(_import_wing(), _export(1, "before.obj"), _emit("SELECT_MESH_NODE", 1)),
            epilogue=_export(1, "after.obj"),
            assert_effect=one_vertex_moved((0.0, 0.0, 0.25)),
            observe=_moved_read,
            effect_note="exactly one vertex moves, by 0.25 m in z",
        ),
        _g(
            "P1-12",
            "P1",
            "node transform ABSOLUTE to (5, 5, 5): does the selected node land there",
            "P1-11, the TRANSLATION form",
            command="TRANSFORM_SELECTED_NODES",
            build_target=_emit("TRANSFORM_SELECTED_NODES", 1, "ABSOLUTE", 5.0, 5.0, 5.0),
            prelude=_seq(_import_wing(), _export(1, "before.obj"), _emit("SELECT_MESH_NODE", 1)),
            epilogue=_export(1, "after.obj"),
            assert_effect=one_vertex_moved(None),
            observe=_moved_read,
            effect_note="exactly one vertex moves, to (5, 5, 5) if ABSOLUTE is a position",
        ),
    ]


def _p2() -> list[GapProbe]:
    iges_read = _states_read("saved.fsm", "surface_1.obj", "surface_2.obj")
    probes = [
        _g(
            "P2-01",
            "P2",
            "CAD body delete of body 1, then every body converted: the two-sheet IGES imports "
            "as one CAD body (P2-05c converts it to one surface spanning both sheets), so the "
            "delete leaves nothing to convert",
            "P2-05c, the same conversion of every body with no delete (one surface)",
            primary=True,
            command="CAD_BODY_DELETE",
            build_target=_emit("CAD_BODY_DELETE", 1),
            prelude=_iges_import,
            epilogue=_seq(_convert(-1), _save("saved.fsm"), _export(1, "surface_1.obj")),
            assert_effect=_nothing_converted("saved.fsm"),
            observe=iges_read,
            effect_note="after deleting body 1, converting every body makes no surface",
        ),
        _g(
            "P2-02",
            "P2",
            "CAD body mirror about XZ then conversion of every body: one surface or two, and names",
            "sheet A spans y 0 to 1 before the mirror",
            primary=True,
            command="CAD_BODY_MIRROR",
            build_target=_emit("CAD_BODY_MIRROR", 1, "XZ"),
            prelude=_iges_import,
            epilogue=_seq(
                _convert(-1),
                _save("saved.fsm"),
                _export(1, "surface_1.obj"),
                _export(2, "surface_2.obj"),
            ),
            assert_effect=_obj_range_moved("surface_1.obj", 1, (0.0, 1.0)),
            observe=iges_read,
            effect_note="the converted sheet A no longer spans y 0 to 1",
        ),
        _g(
            "P2-03",
            "P2",
            "CAD body scale 2: about the origin (x 0 to 2) or about the body's centre (x -0.5 to "
            "1.5)",
            "sheet A spans x 0 to 1 before the scale",
            primary=True,
            command="CAD_BODY_SCALE",
            build_target=_emit("CAD_BODY_SCALE", 1, 2.0),
            prelude=_iges_import,
            epilogue=_seq(_convert(1), _save("saved.fsm"), _export(1, "surface_1.obj")),
            assert_effect=_obj_range_moved("surface_1.obj", 0, (0.0, 1.0)),
            observe=iges_read,
            effect_note="the converted sheet A no longer spans x 0 to 1",
        ),
        _g(
            "P2-04",
            "P2",
            "CAD body translate 250 MILLIMETER in z: does the shift follow its UNITS (0.25 m)",
            "sheet A sits at z = 0 before the translation",
            primary=True,
            command="CAD_BODY_TRANSLATE",
            build_target=_emit("CAD_BODY_TRANSLATE", 1, 0.0, 0.0, 250.0, "MILLIMETER"),
            prelude=_iges_import,
            epilogue=_seq(_convert(1), _save("saved.fsm"), _export(1, "surface_1.obj")),
            assert_effect=_obj_range_moved("surface_1.obj", 2, (0.0, 0.0)),
            observe=iges_read,
            effect_note="the converted sheet A leaves z = 0",
        ),
        _g(
            "P2-05",
            "P2",
            "CAD body threshold Z above 1 with action DELETE: is sheet B (z = 2) deleted",
            "P2-05c, the same threshold with action SELECT",
            primary=True,
            command="CAD_BODY_SELECT_BY_THRESHOLD",
            build_target=_emit("CAD_BODY_SELECT_BY_THRESHOLD", 1, "Z", 1.0, "ABOVE", "DELETE"),
            prelude=_iges_import,
            epilogue=_seq(
                _convert(-1),
                _save("saved.fsm"),
                _export(1, "surface_1.obj"),
                _export(2, "surface_2.obj"),
            ),
            assert_effect=_only_sheet_a,
            observe=iges_read,
            effect_note="converting every body after the deletion leaves one surface, at z = 0",
        ),
        _g(
            "P2-05c",
            "P2",
            "control of P2-05: the same threshold with action SELECT keeps both bodies",
            "this run is the control of P2-05",
            command="CAD_BODY_SELECT_BY_THRESHOLD",
            build_target=_emit("CAD_BODY_SELECT_BY_THRESHOLD", 1, "Z", 1.0, "ABOVE", "SELECT"),
            prelude=_iges_import,
            epilogue=_seq(
                _convert(-1),
                _save("saved.fsm"),
                _export(1, "surface_1.obj"),
                _export(2, "surface_2.obj"),
            ),
            assert_effect=_obj_spans("surface_1.obj", 2, 0.0, 2.0),
            observe=iges_read,
            effect_note="with SELECT both bodies convert, into one surface spanning z 0 to 2",
        ),
        _g(
            "P2-06",
            "P2",
            "curvature refinement 48 between two spheres: does it change the converted sphere's "
            "faces",
            "the sphere created before the setting",
            primary=True,
            command="SET_CAD_CURVATURE_REFINEMENT",
            build_target=_emit("SET_CAD_CURVATURE_REFINEMENT", 48),
            prelude=_seq(
                _emit("NEW_SIMULATION"), _emit("CAD_CREATE_SPHERE", 1, 0.0, 0.0, 0.0, 0.5)
            ),
            epilogue=_seq(
                _emit("CAD_CREATE_SPHERE", 1, 3.0, 0.0, 0.0, 0.5),
                _convert(-1),
                _save("saved.fsm"),
                _export(1, "surface_1.obj"),
                _export(2, "surface_2.obj"),
            ),
            assert_effect=_two_meshes_differ("surface_1.obj", "surface_2.obj"),
            observe=_states_read("saved.fsm", "surface_1.obj", "surface_2.obj"),
            effect_note="the sphere made after the setting has another face count than the first",
        ),
    ]
    for loft_setting, args in (
        ("SET_CAD_CREATE_SPLINE_SEGMENTS", (60,)),
        ("SET_CAD_CREATE_SPLINE_LOFT", ("C0",)),
        # 0.01 m merged the 200 points of each curve (their spacing is about 0.01 m)
        # and the loft came out empty on 26.124 (second batch); 0.002 m is below it.
        ("SET_CAD_CREATE_MERGE_TOLERANCE", (0.002,)),
    ):
        probes.append(
            _g(
                f"P2-0{7 + len(probes) - 7}",
                "P2",
                f"{loft_setting} between two CCS lofts of one synthetic wing: does it reach the "
                f"loft",
                "the wing lofted before the setting",
                primary=True,
                command=loft_setting,
                build_target=_emit(loft_setting, *args),
                prelude=_seq(_REFERENCE_WING, _export_obj(1, "reference.obj")),
                epilogue=_seq(
                    _ccs_select,
                    _ccs_assign(1),
                    _loft_exported("PYFS_VARIANT", 2, "variant.obj"),
                ),
                assert_effect=_mesh_differs,
                observe=_mesh_read,
                effect_note="the wing lofted after the setting differs from the one lofted before",
            )
        )
    for index, (primitive, values) in enumerate(
        (
            ("CAD_CREATE_BOX", (1, 0.0, 0.0, 0.0, 1.0, 0.5, 0.25)),
            ("CAD_CREATE_SPHERE", (1, 0.0, 0.0, 0.0, 0.5)),
            ("CAD_CREATE_CYLINDER", (1, 0.0, 0.0, 0.0, 0.3, 0.2, 1.0)),
            ("CAD_CREATE_SHEET", (1, "XY", 0.0, 1.0, 0.5)),
        ),
        start=10,
    ):
        probes.append(
            _g(
                f"P2-{index}",
                "P2",
                f"{primitive} alone: a CAD body that needs CONVERT_CAD_TO_MESH, or a mesh surface "
                "directly; its name and face count",
                "the saved state before the primitive (empty)",
                primary=True,
                command=primitive,
                build_target=_emit(primitive, *values),
                prelude=_emit("NEW_SIMULATION"),
                save_state=True,
                epilogue=_seq(_convert(-1), _save("saved.fsm"), _export(1, "surface_1.obj")),
                assert_effect=_primitive_exists,
                observe=_states_read("saved.fsm", "surface_1.obj"),
                effect_note=(
                    "a boundary exists right after the primitive (a mesh) or after converting "
                    "every body (a CAD body)"
                ),
            )
        )
    return probes + _p2_curves()


def _p2_curves() -> list[GapProbe]:
    """Return the CAD Create curve probes of P2: import, select, transform, export, loft."""
    probes: list[GapProbe] = []
    curve = "curve.ccs"
    reference = "reference.ccs"
    first_point = _naca_points()[0]
    probes += [
        _g(
            "P2-14",
            "P2",
            "import of the two-column section text (x and the out-of-plane coordinate, no header, "
            "trailing edge to leading edge and back): is the layout read as the draft assumes",
            "the file's own points",
            primary=True,
            command="CAD_CREATE_IMPORT_CURVE_TXT",
            build_target=_import_txt(_SECTION_TXT),
            prelude=_cad_session(select=False),
            epilogue=_seq(_emit("CAD_CREATE_CURVE_SELECT", -1), _export_ccs(curve)),
            assert_effect=_ccs_written(curve),
            observe=_states_read(curve),
            effect_note="the curves exported after the import hold the section",
        ),
        _g(
            "P2-14c",
            "P2",
            "the P2-14 section written with a comma between its two columns: does the text "
            "route read that layout",
            "P2-14, the same points separated by a space",
            command="CAD_CREATE_IMPORT_CURVE_TXT",
            build_target=_import_txt_as("comma"),
            prelude=_cad_session(select=False),
            epilogue=_seq(_emit("CAD_CREATE_CURVE_SELECT", -1), _export_ccs(curve)),
            assert_effect=_ccs_written(curve),
            observe=_states_read(curve),
            effect_note="the curves exported after the comma-layout import hold the section",
        ),
        _g(
            "P2-14n",
            "P2",
            "the P2-14 section opened by a line holding its point count: does the text route "
            "read that layout",
            "P2-14, the same points with no count line",
            command="CAD_CREATE_IMPORT_CURVE_TXT",
            build_target=_import_txt_as("count"),
            prelude=_cad_session(select=False),
            epilogue=_seq(_emit("CAD_CREATE_CURVE_SELECT", -1), _export_ccs(curve)),
            assert_effect=_ccs_written(curve),
            observe=_states_read(curve),
            effect_note="the curves exported after the counted-layout import hold the section",
        ),
        _g(
            "P2-15",
            "P2",
            "import of a one-curve Plot3D file: is it read, and as which component",
            "the file's own points",
            primary=True,
            command="CAD_CREATE_IMPORT_CURVE_P3D",
            build_target=_import_p3d,
            prelude=_cad_session(select=False),
            epilogue=_seq(_emit("CAD_CREATE_CURVE_SELECT", -1), _export_ccs(curve)),
            assert_effect=_ccs_written(curve),
            observe=_states_read(curve),
            effect_note="the curves exported after the import hold the curve",
        ),
        _g(
            "P2-16",
            "P2",
            "curve unselect after select all: does the export carry only the selected curves",
            "the export before the unselect",
            primary=True,
            command="CAD_CREATE_CURVE_UNSELECT",
            build_target=_emit("CAD_CREATE_CURVE_UNSELECT", 1),
            prelude=_seq(_cad_session_ccs(_ROOT_3D, _TIP_3D), _export_ccs(reference)),
            epilogue=_export_ccs(curve),
            assert_effect=_ccs_moved(curve, reference),
            observe=_states_read(reference, curve),
            effect_note="the export after the unselect differs from the one before",
        ),
        _g(
            "P2-17",
            "P2",
            "curve scale 2 on the selected section: about the origin (x 0 to 2) or about the "
            "curve's centroid",
            "the export before the scale",
            primary=True,
            command="CAD_CREATE_SCALE_CURVES",
            build_target=_emit("CAD_CREATE_SCALE_CURVES", 2.0, "DELETE"),
            prelude=_seq(_cad_session_ccs(_SECTION_TXT), _export_ccs(reference)),
            # The curve an operation makes is not selected, and an export with nothing
            # selected stops on a dialog (second batch, both builds).
            epilogue=_seq(_emit("CAD_CREATE_CURVE_SELECT", -1), _export_ccs(curve)),
            assert_effect=_ccs_moved(curve, reference),
            observe=_states_read(reference, curve),
            effect_note="the exported section changes across the scale",
        ),
        _g(
            "P2-17n",
            "P2",
            "curve scale with no explicit selection: is an imported curve selected on import",
            "P2-17, the same scale after CAD_CREATE_CURVE_SELECT -1",
            command="CAD_CREATE_SCALE_CURVES",
            build_target=_emit("CAD_CREATE_SCALE_CURVES", 2.0, "DELETE"),
            prelude=_seq(_cad_session_ccs(_SECTION_TXT, select=False), _export_ccs(reference)),
            epilogue=_export_ccs(curve),
            assert_effect=_ccs_moved(curve, reference),
            observe=_states_read(reference, curve),
            effect_note="the exported section changes across a scale with no explicit selection",
        ),
        _g(
            "P2-18",
            "P2",
            "curve rotation 10 deg about Y of the reference frame (twist)",
            "the export before the rotation",
            primary=True,
            command="CAD_CREATE_ROTATE_CURVES",
            build_target=_emit("CAD_CREATE_ROTATE_CURVES", 1, "Y", 10.0, "DELETE"),
            prelude=_seq(_cad_session_ccs(_SECTION_TXT), _export_ccs(reference)),
            # The curve an operation makes is not selected, and an export with nothing
            # selected stops on a dialog (second batch, both builds).
            epilogue=_seq(_emit("CAD_CREATE_CURVE_SELECT", -1), _export_ccs(curve)),
            assert_effect=_ccs_moved(curve, reference),
            observe=_states_read(reference, curve),
            effect_note="the exported section changes across the rotation",
        ),
        _g(
            "P2-19",
            "P2",
            "curve translation 2 m in y with RETAIN: a moved copy beside the original, or a move",
            "the export before the translation",
            primary=True,
            command="CAD_CREATE_TRANSLATE_CURVES",
            build_target=_emit("CAD_CREATE_TRANSLATE_CURVES", 0.0, 2.0, 0.0, "RETAIN"),
            prelude=_seq(_cad_session_ccs(_SECTION_TXT), _export_ccs(reference)),
            epilogue=_seq(_emit("CAD_CREATE_CURVE_SELECT", -1), _export_ccs(curve)),
            assert_effect=_ccs_moved(curve, reference),
            observe=_states_read(reference, curve),
            effect_note="the exported curves change across the translation",
        ),
        _g(
            "P2-20",
            "P2",
            "curve reorder +Y on a tip imported before its root: spanwise order before the loft",
            "the export before the reorder (tip first)",
            primary=True,
            command="CAD_CREATE_REORDER_CURVES",
            build_target=_emit("CAD_CREATE_REORDER_CURVES", 1, "+Y"),
            prelude=_seq(_cad_session_ccs(_TIP_3D, _ROOT_3D), _export_ccs(reference)),
            epilogue=_export_ccs(curve),
            assert_effect=reordered(curve),
            observe=_states_read(reference, curve),
            effect_note="the exported sections run in increasing y after the reorder",
        ),
        _g(
            "P2-21",
            "P2",
            "export of root and tip sections to CCS, read back through the CCS curve route and "
            "lofted: the whole wing-from-sections path",
            "the loft name is absent before the epilogue's loft",
            primary=True,
            command="CAD_CREATE_CURVE_EXPORT_CCS",
            build_target=_export_ccs(curve),
            prelude=_cad_session_ccs(_ROOT_3D, _TIP_3D),
            epilogue=_seq(_read_back_and_loft(curve), _save("saved.fsm")),
            assert_effect=_ccs_written(curve),
            observe=_states_read(curve, "saved.fsm"),
            effect_note=(
                "the export holds the sections; the reading says whether the CCS route lofted "
                "them into PYFS_LOFTED"
            ),
        ),
        _g(
            "P2-22",
            "P2",
            "curve reverse of the first section: does the point order flip",
            "the file's first point",
            primary=True,
            command="CAD_CREATE_CURVE_REVERSE",
            build_target=_emit("CAD_CREATE_CURVE_REVERSE", 1),
            prelude=_cad_session_ccs(_SECTION_TXT),
            # The curve an operation makes is not selected, and an export with nothing
            # selected stops on a dialog (second batch, both builds).
            epilogue=_seq(_emit("CAD_CREATE_CURVE_SELECT", -1), _export_ccs(curve)),
            assert_effect=_reversed_first_point(curve, first_point),
            observe=_states_read(curve),
            effect_note="the exported section no longer starts at the file's first point",
        ),
        _g(
            "P2-23",
            "P2",
            "curve mirror about XZ with RETAIN of the tip at y = 2 (the spelling the database "
            "records)",
            "the export before the mirror",
            primary=True,
            command="CAD_CREATE_MIRROR_CURVES",
            build_target=_emit("CAD_CREATE_MIRROR_CURVES", 1, "XZ", "RETAIN"),
            prelude=_seq(_cad_session_ccs(_TIP_3D), _export_ccs(reference)),
            epilogue=_seq(_emit("CAD_CREATE_CURVE_SELECT", -1), _export_ccs(curve)),
            assert_effect=_ccs_moved(curve, reference),
            observe=_states_read(reference, curve),
            effect_note="the exported curves gain the mirrored tip at y = -2",
        ),
    ]
    return probes


def _p3() -> list[GapProbe]:
    offbody = "offbody.txt"
    read = _states_read(offbody)
    solved = _solved_wing()
    tube = _emit("NEW_OFF_BODY_STREAMTUBE", 2, "X", -1.0, 0.5, 0.0, 0.2, 2, 4)

    def _numeric_axis_tube(script: Script, workdir: Path) -> None:
        # The database records AXIS as X, Y or Z; the manual's sample writes 1. The
        # line is the one P3-01 emits with the axis token alone changed, so it is
        # written unvalidated and the probe stays out of the registry.
        script.raw("NEW_OFF_BODY_STREAMTUBE 2 1 -1.0 0.5 0.0 0.2 2 4")

    def _closed_tube(script: Script, workdir: Path) -> None:
        # Both axis forms read the next script line as a further argument (26.124:
        # "Unexpected argument PRINT"); a blank line closes a keyword block.
        script.raw("NEW_OFF_BODY_STREAMTUBE 2 X -1.0 0.5 0.0 0.2 2 4\n\n")

    framed = _seq(
        _import_wing(),
        _units_and_edges,
        _emit("CREATE_NEW_COORDINATE_SYSTEM"),
        _flow(steady=True),
        _emit("SOLVER_SET_AOA", 4.0),
        _start(),
    )
    return [
        _g(
            "P3-01",
            "P3",
            "a streamtube about the X axis of a frame the script created, two radial by four "
            "circular: does it run, and does the export hold eight lines; the export grammar whole",
            "P3-01c, the export of a three-seed line with no streamtube",
            primary=True,
            solves=True,
            command="NEW_OFF_BODY_STREAMTUBE",
            build_target=tube,
            prelude=framed,
            epilogue=_offbody_export(offbody),
            assert_effect=file_rows(offbody),
            observe=read,
            effect_note="the off-body export after the streamtube holds numeric rows",
        ),
        _g(
            "P3-01a",
            "P3",
            "the P3-01 streamtube with the axis written as the number 1, the form of the manual's "
            "own sample (NEW_OFF_BODY_STREAMTUBE 1 1 0 0 0 1.5 2 4): on 26.124 the X form read "
            "the next script line as a further argument",
            "P3-01, the same streamtube with the axis written X",
            solves=True,
            command="NEW_OFF_BODY_STREAMTUBE",
            build_target=_numeric_axis_tube,
            prelude=framed,
            epilogue=_offbody_export(offbody),
            assert_effect=file_rows(offbody),
            observe=read,
            effect_note="the off-body export after the numeric-axis streamtube holds numeric rows",
        ),
        _g(
            "P3-01b",
            "P3",
            "the P3-01 streamtube line followed by a blank line: both the X and the numeric "
            "axis forms read the next line as an argument, so does a blank line end the "
            "command",
            "P3-01, the same line with no blank line after it",
            solves=True,
            command="NEW_OFF_BODY_STREAMTUBE",
            build_target=_closed_tube,
            prelude=framed,
            epilogue=_offbody_export(offbody),
            assert_effect=file_rows(offbody),
            observe=read,
            effect_note="the off-body export after the closed streamtube line holds numeric rows",
        ),
        _g(
            "P3-01c",
            "P3",
            "control of P3-01: the same solved point with a three-seed line and no streamtube",
            "this run is the control of P3-01",
            solves=True,
            command="NEW_STREAMLINE_DISTRIBUTION",
            build_target=_seed_line,
            prelude=solved,
            epilogue=_offbody_export(offbody),
            assert_effect=file_rows(offbody),
            observe=read,
            effect_note="the off-body export holds the three seeds' lines",
        ),
        _g(
            "P3-02",
            "P3",
            "SET_LENGTH 0.5 on a three-seed line: the exported line lengths",
            "P3-01c (default length) and P3-02u (unrestricted)",
            primary=True,
            solves=True,
            command="SET_OFF_BODY_STREAMLINE_LENGTH",
            build_target=_emit("SET_OFF_BODY_STREAMLINE_LENGTH", set_length=0.5),
            prelude=_seq(solved, _seed_line),
            epilogue=_offbody_export(offbody),
            assert_effect=file_rows(offbody),
            observe=read,
            effect_note="the export after the setting holds lines; the reading gives their extent",
        ),
        _g(
            "P3-02u",
            "P3",
            "SET_UNRESTRICTED_LENGTH on a three-seed line: the exported line lengths",
            "P3-02 (length 0.5)",
            solves=True,
            command="SET_OFF_BODY_STREAMLINE_LENGTH",
            build_target=_emit("SET_OFF_BODY_STREAMLINE_LENGTH", set_unrestricted_length=True),
            prelude=_seq(solved, _seed_line),
            epilogue=_offbody_export(offbody),
            assert_effect=file_rows(offbody),
            observe=read,
            effect_note="the export after the unrestricted setting holds the lines",
        ),
        _g(
            "P3-03",
            "P3",
            "every off-body line traced upstream from the seed line: the x range against the seed "
            "at x = -1",
            "P3-04 (downstream)",
            primary=True,
            solves=True,
            command="SET_ALL_OFF_BODY_STREAMLINES_UPSTREAM",
            build_target=_emit("SET_ALL_OFF_BODY_STREAMLINES_UPSTREAM"),
            prelude=_seq(solved, _seed_line),
            epilogue=_offbody_export(offbody),
            assert_effect=file_rows(offbody),
            observe=read,
            effect_note="the export holds lines; the reading's x range says which way they run",
        ),
        _g(
            "P3-04",
            "P3",
            "every off-body line traced downstream from the seed line: the x range",
            "P3-03 (upstream)",
            primary=True,
            solves=True,
            command="SET_ALL_OFF_BODY_STREAMLINES_DOWNSTREAM",
            build_target=_emit("SET_ALL_OFF_BODY_STREAMLINES_DOWNSTREAM"),
            prelude=_seq(solved, _seed_line),
            epilogue=_offbody_export(offbody),
            assert_effect=file_rows(offbody),
            observe=read,
            effect_note="the export holds lines; the reading's x range says which way they run",
        ),
        _g(
            "P3-05",
            "P3",
            "surface streamlines generated on a steady point, then exported: runs, file, grammar",
            "the export is absent without a generation (P3-06 starts from one)",
            primary=True,
            solves=True,
            command="GENERATE_ALL_SURFACE_STREAMLINES",
            build_target=_emit("GENERATE_ALL_SURFACE_STREAMLINES"),
            prelude=solved,
            epilogue=_surface_export(),
            assert_effect=file_rows("surface_lines.txt"),
            observe=_states_read("surface_lines.txt"),
            effect_note="the surface streamline export after the generation holds numeric rows",
        ),
        _g(
            "P3-06",
            "P3",
            "export of the surface streamlines: the file and its grammar",
            "P3-05",
            primary=True,
            solves=True,
            command="EXPORT_ALL_SURFACE_STREAMLINES",
            build_target=_surface_export(),
            prelude=_seq(solved, _emit("GENERATE_ALL_SURFACE_STREAMLINES")),
            assert_effect=_streamline_table("surface_lines.txt"),
            observe=_states_read("surface_lines.txt"),
            effect_note=(
                "the export writes the file it names, with the streamline table (no line in a "
                "batch run: no script command seeds an on-body streamline)"
            ),
        ),
        _g(
            "P3-07",
            "P3",
            "delete every off-body line after generating them: the export after it",
            "P3-01c (the same lines kept)",
            primary=True,
            solves=True,
            command="DELETE_ALL_OFF_BODY_STREAMLINES",
            build_target=_emit("DELETE_ALL_OFF_BODY_STREAMLINES"),
            prelude=_seq(solved, _seed_line, _emit("GENERATE_ALL_OFF_BODY_STREAMLINES")),
            epilogue=_offbody_file(offbody),
            assert_effect=emptied(offbody),
            observe=read,
            effect_note="the off-body export after the deletion holds no line",
        ),
        _g(
            "P3-08",
            "P3",
            "delete every surface streamline after generating them: the export after it (the "
            "generation makes no line in a batch run, so zero lines after the delete cannot "
            "verify it)",
            "P3-06 (the same lines kept)",
            primary=True,
            solves=True,
            command="DELETE_ALL_SURFACE_STREAMLINES",
            build_target=_emit("DELETE_ALL_SURFACE_STREAMLINES"),
            prelude=_seq(solved, _emit("GENERATE_ALL_SURFACE_STREAMLINES")),
            epilogue=_surface_export(),
            assert_effect=_surface_lines_deleted("surface_lines.txt"),
            observe=_states_read("surface_lines.txt"),
            effect_note="the surface streamline export after the deletion counts no line",
        ),
        _g(
            "P3-09",
            "P3",
            "one unsteady point: the off-body family traced after a ten-step march",
            "P3-01c (the steady point)",
            solves=True,
            command="GENERATE_ALL_OFF_BODY_STREAMLINES",
            build_target=_emit("GENERATE_ALL_OFF_BODY_STREAMLINES"),
            prelude=_seq(
                _import_wing(),
                _units_and_edges,
                _flow(steady=False, steps=10, dt=0.01),
                _emit("SOLVER_SET_AOA", 4.0),
                _start(),
                _seed_line,
            ),
            epilogue=_offbody_file(offbody),
            assert_effect=file_rows(offbody),
            observe=read,
            effect_note="the off-body export after the march holds numeric rows",
        ),
        _g(
            "P3-10a",
            "P3",
            "the run half of the reopen question: one seed line traced on the solved point, "
            "exported, and the solved simulation saved for P3-10b",
            "P3-10b traces the same line on the reopened file",
            solves=True,
            command="GENERATE_ALL_OFF_BODY_STREAMLINES",
            build_target=_emit("GENERATE_ALL_OFF_BODY_STREAMLINES"),
            prelude=_seq(solved, _seed_line),
            epilogue=_seq(_offbody_file(offbody), _save("saved.fsm")),
            assert_effect=file_rows(offbody),
            observe=read,
            effect_note="the off-body export of the run holds numeric rows",
        ),
        _g(
            "P3-10b",
            "P3",
            "the reopen half: the saved solved point of P3-10a opened, the same seed line traced "
            "again; the batch compares the two exports",
            "P3-10a, the lines the run traced",
            opens="P3-10a",
            command="GENERATE_ALL_OFF_BODY_STREAMLINES",
            build_target=_emit("GENERATE_ALL_OFF_BODY_STREAMLINES"),
            requires=Requires.SIM,
            prelude=_seed_line,
            epilogue=_offbody_file(offbody),
            assert_effect=file_rows(offbody),
            observe=read,
            effect_note="the off-body export of the reopened point holds numeric rows",
            timeout_s=_SOLVE_TIMEOUT_S,
        ),
    ]


def _p4() -> list[GapProbe]:
    read = trajectory_read(_TRAJECTORY)
    moved = trajectory_moved(_TRAJECTORY)
    spec_common = {"solves": True, "observe": read, "assert_effect": moved}
    probes = [
        _g(
            "P4-01",
            "P4",
            "free fall, every freedom on, gravity only and a one metre per second stream: the "
            "trajectory against z = -g t^2 / 2 fixes the gravity and trajectory units and the "
            "file grammar",
            "P4-09 and P4-02 run the same body without gravity",
            primary=True,
            command="SET_MOTION_GRAVITY",
            build_target=_emit("SET_MOTION_GRAVITY", 1, 0.0, 0.0, -9.81),
            prelude=_sixdof_body(),
            epilogue=_march_then_trajectory(),
            effect_note="the trajectory moves under gravity; the reading gives the 0.4 s drop",
            **spec_common,  # type: ignore[arg-type]
        ),
        _g(
            "P4-02",
            "P4",
            "a known spin: 10 per second about X, every force off: degrees or radians per second",
            "P4-01 (no spin)",
            primary=True,
            command="SET_MOTION_6DOF_INITIAL_ANGULAR_VELOCITY",
            build_target=_emit("SET_MOTION_6DOF_INITIAL_ANGULAR_VELOCITY", 1, 10.0, 0.0, 0.0),
            prelude=_sixdof_body(),
            epilogue=_march_then_trajectory(),
            effect_note="the roll angle changes; 4 after 0.4 s means degrees, 229 means radians",
            **spec_common,  # type: ignore[arg-type]
        ),
        _g(
            "P4-03",
            "P4",
            "pitch only under gravity, the body started with a pitch rate (the first batch's "
            "off-centre pulse aborted the script, P4-06): the other five freedoms stay at their "
            "initial values",
            "P4-01 (every freedom on)",
            primary=True,
            command="SET_MOTION_6DOF_ACTIVE_VARIABLES",
            build_target=_emit("SET_MOTION_6DOF_ACTIVE_VARIABLES", 1, list(_PITCH_ONLY)),
            prelude=_seq(_sixdof_body(gravity=True, active=None), _pitch_kick),
            epilogue=_march_then_trajectory(),
            solves=True,
            observe=read,
            assert_effect=_pitch_only(_TRAJECTORY),
            effect_note="theta moves and z stays under gravity: only the pitch is free",
        ),
        _g(
            "P4-04",
            "P4",
            "trajectory export placed before the solve (its recorded phase): which file is "
            "written and when",
            "P4-04m, the export placed after the march",
            primary=True,
            command="EXPORT_6DOF_TRAJECTORY",
            build_target=_trajectory_export,
            prelude=_sixdof_body(gravity=True),
            epilogue=_march(),
            effect_note="the trajectory file is written by the march",
            **spec_common,  # type: ignore[arg-type]
        ),
        _g(
            "P4-04m",
            "P4",
            "trajectory export placed after the march, the placement the phase order refuses: "
            "is the file written then (an evidence change, not a code workaround)",
            "P4-04, the export placed before the solve",
            command="EXPORT_6DOF_TRAJECTORY",
            build_target=_after_the_march_trajectory,
            prelude=_seq(_sixdof_body(gravity=True), _march()),
            effect_note="the trajectory file is written when the export follows the march",
            **spec_common,  # type: ignore[arg-type]
        ),
        _g(
            "P4-05",
            "P4",
            "symmetry loads on a mirrored half model, the name the heading prints: accepted, and "
            "the trajectory of the half body",
            "the same half body without the command is not run; recognition is the question",
            primary=True,
            command="SET_6DOF_MOTION_SYMMETRY_LOADS",
            build_target=_emit("SET_6DOF_MOTION_SYMMETRY_LOADS", 1, "ENABLE"),
            prelude=_sixdof_body(gravity=True, half=True),
            epilogue=_march_then_trajectory(symmetry="MIRROR"),
            effect_note="the half body moves with the symmetry loads enabled",
            **spec_common,  # type: ignore[arg-type]
        ),
        _g(
            "P4-06",
            "P4",
            "an external force of 500 N up at the centre from 0.1 s for 0.1 s on 100 kg: the "
            "vertical velocity gained (0.5 m/s if newtons and seconds)",
            "P4-09 (the same body, no force)",
            primary=True,
            command="CREATE_NEW_6DOF_EXTERNAL_FORCE",
            build_target=_emit(
                "CREATE_NEW_6DOF_EXTERNAL_FORCE", 1, 0.25, 0.0, 0.0, 0.1, 0.1, 0.0, 0.0, 500.0
            ),
            prelude=_sixdof_body(),
            epilogue=_march_then_trajectory(),
            effect_note="the body rises after the pulse",
            **spec_common,  # type: ignore[arg-type]
        ),
        _g(
            "P4-06s",
            "P4",
            "the manual's own sample line of the external force (CREATE_NEW_6DOF_EXTERNAL_FORCE "
            "1 0.0 -0.2 1.2 0 0.25 -3000 0 0) on the P4-06 body: is the form P4-06 used the "
            "reason it aborted",
            "P4-06, the stated pulse on the same body",
            command="CREATE_NEW_6DOF_EXTERNAL_FORCE",
            build_target=_emit(
                "CREATE_NEW_6DOF_EXTERNAL_FORCE", 1, 0.0, -0.2, 1.2, 0.0, 0.25, -3000.0, 0.0, 0.0
            ),
            prelude=_sixdof_body(),
            epilogue=_march_then_trajectory(),
            effect_note="the body moves under the sample force",
            **spec_common,  # type: ignore[arg-type]
        ),
        _g(
            "P4-07",
            "P4",
            "a custom force against time from a two-column file (the use case's pulse): read, and "
            "in which direction it acts",
            "P4-06 (the stated pulse)",
            primary=True,
            command="CREATE_NEW_6DOF_CUSTOM_FORCE",
            build_target=_custom_force,
            prelude=_sixdof_body(),
            epilogue=_march_then_trajectory(),
            effect_note="the body moves under the tabulated force",
            **spec_common,  # type: ignore[arg-type]
        ),
        _g(
            "P4-08",
            "P4",
            "mass 50 kg on the 6DOF body: is it kept by the simulation (the first batch's steady "
            "500 N force aborted the script, P4-06)",
            "the saved state before the setting",
            primary=True,
            command="SET_MOTION_MASS_PROPERTIES",
            build_target=_emit("SET_MOTION_MASS_PROPERTIES", 1, 50.0, 5.0, 5.0, 5.0, 0.0, 0.0, 0.0),
            prelude=_sixdof_body(mass=False, gravity=True),
            save_state=True,
            epilogue=_march_then_trajectory(),
            solves=True,
            observe=read,
            assert_effect=fsm_changed(strict=False),
            effect_note=(
                "the saved simulation changes across the mass setting; the trajectory under "
                "gravity is read after the march"
            ),
        ),
        _g(
            "P4-09",
            "P4",
            "an initial velocity of 2 m/s along x, every force off: the x travel after 0.4 s",
            "P4-01 (no initial velocity)",
            primary=True,
            command="SET_MOTION_6DOF_INITIAL_VELOCITY",
            build_target=_emit("SET_MOTION_6DOF_INITIAL_VELOCITY", 1, 2.0, 0.0, 0.0),
            prelude=_sixdof_body(),
            epilogue=_march_then_trajectory(),
            effect_note="the body travels along x",
            **spec_common,  # type: ignore[arg-type]
        ),
        _g(
            "P4-10",
            "P4",
            "a spring along z from the centre, free length 1, initial length 0.8, rate 1000: does "
            "the body oscillate",
            "P4-09 (no spring)",
            primary=True,
            command="CREATE_NEW_6DOF_SPRING_FORCE",
            build_target=_emit(
                "CREATE_NEW_6DOF_SPRING_FORCE",
                1,
                0.25,
                0.0,
                0.0,
                0.0,
                0.0,
                1.0,
                1.0,
                0.1,
                0.8,
                1000.0,
            ),
            prelude=_sixdof_body(),
            epilogue=_march_then_trajectory(),
            effect_note="the body moves under the spring",
            **spec_common,  # type: ignore[arg-type]
        ),
        _g(
            "P4-11",
            "P4",
            "the reference case, free to pitch: the wing on a quarter-chord pivot, pitch only, "
            "4.2 kg and the draft's inertias, gravity, 25 m/s at 4 deg, started with a pitch "
            "rate (the 40 N pulse of the draft needs the external force, which aborts the "
            "script, P4-06): does the pitch respond and settle",
            "P4-03 (pitch only at one metre per second)",
            command="SET_MOTION_6DOF_ACTIVE_VARIABLES",
            build_target=_emit("SET_MOTION_6DOF_ACTIVE_VARIABLES", 1, list(_PITCH_ONLY)),
            prelude=_seq(
                _sixdof_body(mass=False, gravity=True, active=None),
                _emit("SET_MOTION_MASS_PROPERTIES", 1, 4.2, 0.05, 0.31, 0.33, 0.0, 0.0, 0.0),
                _pitch_kick,
            ),
            epilogue=_seq(
                _flow(steady=False, velocity=25.0, steps=40, dt=0.002),
                _emit("SOLVER_SET_AOA", 4.0),
                _start(),
                _after_the_march_trajectory,
            ),
            solves=True,
            observe=read,
            assert_effect=_pitch_only(_TRAJECTORY),
            effect_note="theta responds to the initial pitch rate while z stays",
        ),
    ]
    return _registered_forms(probes)


#: The P4 measurement runs whose primary twin reads the saved simulation instead.
_SAVED_STATE_TWINS = (
    "P4-01",
    "P4-02",
    "P4-03",
    "P4-05",
    "P4-06",
    "P4-07",
    "P4-08",
    "P4-09",
    "P4-10",
)


def _registered_forms(probes: list[GapProbe]) -> list[GapProbe]:
    """Split each P4 setter into its registered probe and its trajectory run.

    The trajectory export written before the march holds its header and no row
    on both builds (P4-04), so the second round reads it after the march, a
    placement the phase order refuses and that is appended unvalidated. A
    registered probe builds a validated script, so the run that reads the
    trajectory is kept in the battery as ``<id>m`` and the registered probe of
    the same command reads the saved simulation across the target instead, with
    the same prelude and no march: the setters keep their value in the
    simulation file.
    """
    out: list[GapProbe] = []
    for probe in probes:
        if probe.probe_id not in _SAVED_STATE_TWINS:
            out.append(probe)
            continue
        out.append(
            replace(
                probe,
                solves=False,
                spec=replace(
                    probe.spec,
                    epilogue=None,
                    save_state=True,
                    assert_effect=fsm_changed(strict=False),
                    observe=_states_read(),
                    effect_note=(
                        "the saved simulation changes across the command; the trajectory is "
                        f"read by {probe.probe_id}m"
                    ),
                    timeout_s=None,
                ),
            )
        )
        out.append(replace(probe, probe_id=f"{probe.probe_id}m", primary=False))
    return out


def _p5_rest(standin: Path | None) -> list[GapProbe]:
    def route_b(script: Script, workdir: Path) -> None:
        path = _write_standin(workdir)
        script.emit(
            "SET_AEROELASTIC_STRUCTURAL_EXECUTION_COMMAND", f'"{_windowless_python()}" "{path}"'
        )

    def coupling(script: Script, workdir: Path) -> None:
        _write_standin(workdir)
        script.emit("DELETE_AEROELASTIC_STRUCTURAL_NODES")
        script.emit("ASSIGN_AEROELASTIC_SURFACES", 1, [1])
        script.emit("ASSIGN_AEROELASTIC_COORDINATE_SYSTEMS", 1, [2])
        script.emit("IMPORT_AEROELASTIC_STRUCTURAL_NODES", 2, "DISABLE", workdir / _NODES)
        script.emit("SET_AEROELASTIC_WORKING_DIRECTORY", workdir)
        _write_post(script, workdir)

    return [
        _g(
            "P5-2",
            "P5",
            "the structural node file named on a 6DOF motion, alone: is the command recognised "
            "and does the saved simulation keep the file. Probe A found the executable of the "
            "pair refused on 26.124 and stopping the script on 26.125, so the coupled march "
            "the first batch chained after it can run on neither build",
            "the saved state before the command (no node file named)",
            primary=True,
            command="SET_MOTION_FSI_STRUCTURAL_NODES",
            build_target=_nodes_only,
            prelude=_seq(_import_wing(), _units_and_edges, _motion("6DOF")),
            save_state=True,
            assert_effect=_saved_names_file(_NODES),
            observe=_states_read(),
            effect_note="the saved simulation names the node file after the command",
        ),
        _g(
            "P5-3",
            "P5",
            "route B, the route if the motion pair is unrecognised: the user's program as the "
            "aeroelastic structural execution command on an unsteady coupled wing, three steps, "
            "with the package's post-processing script exporting the sectional loads file the "
            "PyNite beam reads: is it called, in which folder, with which files, and does the "
            "march continue on the zero displacements it answers",
            "P5-A0 (no coupling, no call)",
            primary=True,
            solves=True,
            command="SET_AEROELASTIC_STRUCTURAL_EXECUTION_COMMAND",
            build_target=route_b,
            prelude=_seq(
                _import_wing(),
                _units_and_edges,
                _aero_frame,
                _flow(steady=False, velocity=30.0, steps=3, dt=0.01),
                _emit("SOLVER_SET_AOA", 4.0),
                coupling,
            ),
            epilogue=_seq(
                _emit("SET_AEROELASTIC_ITERATIONS", 1),
                _emit("SET_AEROELASTIC_COUPLING_IN_UNSTEADY", "ENABLE"),
                _sections_in_frame_then_start(2),
            ),
            assert_effect=_called,
            observe=_calls_read,
            effect_note=(
                "the stand-in is called by the coupling and finds the sectional loads file "
                f"{LOADS_FILE} in its folder"
            ),
        ),
        _g(
            "P5-3f",
            "P5",
            "route B, the route if the motion pair is unrecognised: the user's program as the "
            "aeroelastic structural execution command on an unsteady coupled wing, three steps, "
            "with the package's post-processing script exporting the sectional loads file the "
            "PyNite beam reads: is it called, in which folder, with which files, and does the "
            "march continue on the zero displacements it answers",
            "P5-3, the same coupling with its sections cut in frame 2, which stopped the "
            "script at the end of the section block (second batch, 26.124)",
            solves=True,
            command="SET_AEROELASTIC_STRUCTURAL_EXECUTION_COMMAND",
            build_target=route_b,
            prelude=_seq(
                _import_wing(),
                _units_and_edges,
                _aero_frame,
                _flow(steady=False, velocity=30.0, steps=3, dt=0.01),
                _emit("SOLVER_SET_AOA", 4.0),
                coupling,
            ),
            epilogue=_seq(
                _emit("SET_AEROELASTIC_ITERATIONS", 1),
                _emit("SET_AEROELASTIC_COUPLING_IN_UNSTEADY", "ENABLE"),
                _sections_in_frame_then_start(1),
            ),
            assert_effect=_called,
            observe=_calls_read,
            effect_note=(
                "the stand-in is called by the coupling and finds the sectional loads file "
                f"{LOADS_FILE} in its folder"
            ),
        ),
    ]


def _geometry_stage() -> list[GapProbe]:
    """Return the runs the geometry-stage design adds (its probes page, 2026-10-12)."""
    obj_read = ("surface_1.obj", "surface_2.obj", "surface_3.obj")
    resave = _save("resaved.fsm")
    three = _seq(
        _import_wing("PYFS_A"),
        _import_wing("PYFS_B", _SMALL_WING, (3.0, 0.0, 0.0), new=False),
        _import_wing("PYFS_C", _SMALL_WING, (6.0, 0.0, 0.0), new=False),
    )
    probes = [
        _g(
            f"G-03{tag}",
            "G",
            f"the G-03a wing with the control surface at {angle:g} deg: {what}",
            "G-03a (20 deg); the batch compares the control surface's export and the wing's",
            command="NEW_CCS_WING_CONTROL_SURFACE",
            build_target=_deflected(angle),
            prelude=_CCS_WING_CURVES,
            epilogue=_seq(_wing_loft("PYFS_WING"), _save("saved.fsm"), _exports(3)),
            assert_effect=_boundaries_at_least("saved.fsm", 2),
            observe=_states_read("saved.fsm", *obj_read),
            effect_note="the saved simulation holds the wing and its control surface boundary",
        )
        for tag, angle, what in (
            ("x", 0.0, "the control of G-03a, whose control surface must differ and wing must not"),
            ("y", -20.0, "the sign convention, read from the control surface's centroid height"),
        )
    ]
    probes += [
        _g(
            f"G-05{tag}",
            "G",
            f"the OBJ export of {source} imported in a new run with the points file written from "
            f"{source}'s saved marks, type {edge_type}, saved: is the marked set the same",
            f"{source}, the marks as first saved",
            opens=source,
            command="IMPORT_WAKE_EDGES_FROM_FILE",
            build_target=_import_marks(edge_type),
            requires=Requires.SIM,
            prelude=_reimport_with_marks("surface_1.obj", edge_type),
            epilogue=_save("saved.fsm"),
            assert_effect=_marks_reproduced,
            observe=_marks_read,
            effect_note=f"the {edge_type} import marks as many edges as {source} saved",
        )
        for tag, source, edge_type in (("r", "G-01a", "RELAXED"), ("s", "G-02a", "STANDARD"))
    ]
    probes += [
        _g(
            "G-06",
            "G",
            "one OBJ export of every boundary (surface -1) of a body with three named boundaries: "
            "are they written as groups, with the saved names, in the saved order",
            "the saved simulation's boundary list",
            command="EXPORT_SURFACE_MESH",
            build_target=_emit_export_all("all.obj"),
            prelude=_seq(three, _save("saved.fsm")),
            assert_effect=_file_written("all.obj"),
            observe=_groups_read("all.obj"),
            effect_note="one OBJ file holds every boundary",
        ),
        _g(
            "G-07",
            "G",
            "an OBJ written in millimetres imported with UNITS MILLIMETER, saved and exported: in "
            "which unit are the exported coordinates (chord 1 or 1000)",
            "the source OBJ's own coordinates (chord 1000)",
            command="EXPORT_SURFACE_MESH",
            build_target=_export(1, "exported.obj"),
            prelude=_seq(_obj_source("source.obj", scale=1000.0), _save("saved.fsm")),
            assert_effect=_file_written("exported.obj"),
            observe=_states_read("saved.fsm", "source.obj", "exported.obj"),
            effect_note="the export of the millimetre import is written",
        ),
        _g(
            "G-08",
            "G",
            "an OBJ imported with no operation and exported: is the face order the source's",
            "the source OBJ's face order (written reversed from the mesher's, so it is not the "
            "default)",
            command="EXPORT_SURFACE_MESH",
            build_target=_export(1, "exported.obj"),
            prelude=_obj_source("source.obj", reverse=True),
            assert_effect=_file_written("exported.obj"),
            observe=_face_order_read("source.obj", "exported.obj"),
            effect_note="the export of the imported OBJ is written",
        ),
        _g(
            "G-09",
            "G",
            "the loft G-02a saved on the other build opened on this one and saved again: does an "
            "FSM cross builds, with its trailing edges",
            "G-02b, the same file reopened on the build that made it",
            opens="G-02a",
            opens_other_build=True,
            command="SAVEAS",
            build_target=resave,
            requires=Requires.SIM,
            epilogue=_exports(1),
            assert_effect=edges_kept("resaved.fsm"),
            observe=_edges_read("resaved.fsm", "surface_1.obj"),
            effect_note="the file opened from the other build saves again with its trailing edges",
        ),
    ]
    return probes


def _geometry_kept() -> list[GapProbe]:
    """Return what a geometry built once, saved and reopened by a later run must keep (G).

    Owner decision of 2026-10-12: geometry is built by its own command into a
    saved simulation or a mesh file, and a run opens it. Each ``a`` probe builds
    and saves; its ``b`` probe opens that file in a new process and saves it
    again, and the batch compares the two (the ``opens`` link). The OBJ exports
    beside them say what a mesh file would lose.
    """
    obj_read = ("surface_1.obj", "surface_2.obj", "surface_3.obj")
    resave = _seq(_save("resaved.fsm"))
    return [
        _g(
            "G-01a",
            "G",
            "a CCS file whose Relaxed_TE line sheds AZIMUTH (1), imported and saved: the saved "
            "simulation and an OBJ export of it, for G-01b to reopen",
            "G-01x, the same file shedding AXIAL (0): the saved files must differ where the marks "
            "are",
            command="CCS_IMPORT",
            build_target=_pod_import(1),
            epilogue=_seq(_save("saved.fsm"), _exports(1)),
            assert_effect=_boundaries_at_least("saved.fsm", 1),
            observe=_states_read("saved.fsm", "surface_1.obj"),
            effect_note="the saved simulation holds the pod",
        ),
        _g(
            "G-01x",
            "G",
            "control of G-01a: the same pod shedding AXIAL (0), saved",
            "this run is the control of G-01a",
            command="CCS_IMPORT",
            build_target=_pod_import(0),
            epilogue=_seq(_save("saved.fsm"), _exports(1)),
            assert_effect=_boundaries_at_least("saved.fsm", 1),
            observe=_states_read("saved.fsm", "surface_1.obj"),
            effect_note="the saved simulation holds the pod",
        ),
        _g(
            "G-01b",
            "G",
            "the saved pod of G-01a opened by a later run and saved again: do the relaxed "
            "trailing-edge marks survive (the batch compares the two saved files)",
            "G-01a, the file as first saved",
            opens="G-01a",
            command="SAVEAS",
            build_target=resave,
            requires=Requires.SIM,
            epilogue=_exports(1),
            assert_effect=_boundaries_at_least("resaved.fsm", 1),
            observe=_states_read("resaved.fsm", "surface_1.obj"),
            effect_note="the reopened simulation saves again with the pod",
        ),
        _g(
            "G-02a",
            "G",
            "a CCS wing lofted with its trailing edges marked, saved: the marked edges in the "
            "saved simulation and what an OBJ export keeps",
            "G-02b, the same file reopened",
            command="CAD_CREATE_WING_MESH_FROM_CCS",
            build_target=_wing_loft("PYFS_WING"),
            prelude=_CCS_WING_CURVES,
            epilogue=_seq(_save("saved.fsm"), _exports(1)),
            assert_effect=edges_kept("saved.fsm"),
            observe=_edges_read("saved.fsm", "surface_1.obj"),
            effect_note="the saved simulation marks the loft's trailing edges",
        ),
        _g(
            "G-02b",
            "G",
            "the lofted wing of G-02a opened by a later run and saved again: do the marked "
            "trailing edges survive",
            "G-02a, the edges as first saved",
            opens="G-02a",
            command="SAVEAS",
            build_target=resave,
            requires=Requires.SIM,
            epilogue=_exports(1),
            assert_effect=edges_kept("resaved.fsm"),
            observe=_edges_read("resaved.fsm", "surface_1.obj"),
            effect_note="the reopened simulation still marks trailing edges",
        ),
        _g(
            "G-03a",
            "G",
            "a CCS wing lofted with a control surface deflected 20 deg (the ten-argument "
            "PARAMETRIC form), saved and exported",
            "G-03b, the same file reopened; the batch compares the OBJ exports",
            command="NEW_CCS_WING_CONTROL_SURFACE",
            build_target=_DEFLECTED,
            prelude=_CCS_WING_CURVES,
            epilogue=_seq(_wing_loft("PYFS_WING"), _save("saved.fsm"), _exports(3)),
            assert_effect=_boundaries_at_least("saved.fsm", 2),
            observe=_states_read("saved.fsm", *obj_read),
            effect_note="the saved simulation holds the wing and its control surface boundary",
        ),
        _g(
            "G-03b",
            "G",
            "the deflected wing of G-03a opened by a later run: does the saved file keep the "
            "deflection (the batch compares the surfaces exported before and after)",
            "G-03a, the surfaces as first exported",
            opens="G-03a",
            command="SAVEAS",
            build_target=resave,
            requires=Requires.SIM,
            epilogue=_exports(3),
            assert_effect=_boundaries_at_least("resaved.fsm", 2),
            observe=_states_read("resaved.fsm", *obj_read),
            effect_note="the reopened simulation still holds the control surface boundary",
        ),
    ] + [
        _g(
            f"G-04{fmt.lower()}",
            "G",
            f"which mesh export formats the build offers after a CCS loft: {fmt}",
            "the other two formats of the same loft",
            command="EXPORT_SURFACE_MESH",
            build_target=_export_format(fmt),
            prelude=_REFERENCE_WING,
            assert_effect=_file_written(f"wing.{fmt.lower()}"),
            observe=_states_read(f"wing.{fmt.lower()}"),
            effect_note=f"the {fmt} export of the lofted wing is written",
        )
        for fmt in ("OBJ", "STL", "TRI")
    ]


def gap_probes(fsi_standin: Path | None = None) -> tuple[GapProbe, ...]:
    """Return the ordered battery of the 0.40.0 command-gap probes.

    The order is the owner's: P5 probe A first (stage ``first``), then what a
    saved geometry must keep (``G``), P1, P2, P3 and P4, then the rest of P5,
    which depends on probe A's answer.

    Parameters
    ----------
    fsi_standin : Path, optional
        A windowless executable that runs :func:`fsi_standin_source`, handed to
        ``SET_MOTION_FSI_EXECUTABLE`` so the march can show whether the solver
        calls it. Without one the command is handed the windowless interpreter
        itself, which settles recognition but cannot show a call.

    Returns
    -------
    tuple of GapProbe
        Every probe, controls included, in run order.
    """
    probes = (
        _p5_first(fsi_standin)
        + _geometry_kept()
        + _geometry_stage()
        + _p1()
        + _p2()
        + _p3()
        + _p4()
        + _p5_rest(fsi_standin)
    )
    seen: set[str] = set()
    for probe in probes:
        if probe.probe_id in seen:
            raise QaEvidenceError(f"gap probe id {probe.probe_id} is declared twice")
        seen.add(probe.probe_id)
    return tuple(probes)


def _register() -> None:
    """Register each primary probe into ``PROBE_SPECS``; a collision is refused."""
    for probe in gap_probes():
        if not probe.primary:
            continue
        if probe.spec.command in PROBE_SPECS:
            raise QaEvidenceError(
                f"gap probe {probe.probe_id} would replace the catalog's probe of "
                f"{probe.spec.command}; a command keeps one registered probe"
            )
        PROBE_SPECS[probe.spec.command] = probe.spec


_register()


def declined_surface_probes() -> tuple[GapProbe, ...]:
    """Return the licensed probe of a declined surface on 26.125 (PFS-2085.021).

    A surface on the vorticity induced-drag list with no trailing edge is not
    computed, and builds up to 26.124 print its CDi as zero (SRC-003 p.202);
    the polar declines it there. Whether 26.125, which prints CDp and CDv in
    place of CDi and CDo, prints the same zero was never measured, so the
    package declines nothing on 26.125. Two runs settle it: a wing and a sphere
    (a closed body with no trailing edge) solved, then the list set with the
    sphere on it, and the same run with the wing alone on the list. Both builds
    run both, so 26.124 shows the zero the manual describes beside whatever
    26.125 prints. Neither run is registered: the command keeps its catalog
    probe, and the reading is the answer.
    """
    common: dict[str, object] = {
        "solves": True,
        "command": "SET_VORTICITY_DRAG_BOUNDARIES",
        "prelude": _seq(
            _wing_and_sphere, _flow(steady=True), _emit("SOLVER_SET_AOA", 4.0), _start()
        ),
        "epilogue": _declined_export,
        "assert_effect": _sphere_row_read,
        "observe": _drag_read,
    }
    return (
        _g(
            "D-01",
            "D",
            "a sphere with no trailing edge on the vorticity induced-drag list beside a wing: "
            "what the loads export prints in the sphere's drag columns",
            "D-01c, the same solve with the wing alone on the list",
            build_target=_emit("SET_VORTICITY_DRAG_BOUNDARIES", 2, [1, 2]),
            effect_note="the loads export after the list holds the sphere's row",
            **common,  # type: ignore[arg-type]
        ),
        _g(
            "D-01c",
            "D",
            "control of D-01: the wing alone on the vorticity list, the sphere integrated by "
            "surface pressure",
            "this run is the control of D-01",
            build_target=_emit("SET_VORTICITY_DRAG_BOUNDARIES", 1, [1]),
            effect_note="the loads export after the list holds the sphere's row",
            **common,  # type: ignore[arg-type]
        ),
    )


def gap_commands(probes: Sequence[GapProbe]) -> dict[str, list[str]]:
    """Return the commands under test per capability, in order, each named once."""
    found: dict[str, list[str]] = {}
    for probe in probes:
        names = found.setdefault(probe.capability, [])
        if probe.spec.command not in names:
            names.append(probe.spec.command)
    return found
