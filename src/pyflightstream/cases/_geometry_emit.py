"""The script of a geometry build: source, operations, save and export (FR-471, FR-474, FR-475).

Pipeline role: the cases row. :func:`render_geometry_script` turns one
:class:`~pyflightstream.cases._geometry_instruction.GeometryInstruction` into
the script one solver execution runs to make the body, with no solve::

    NEW_SIMULATION
    <the source: the CCS route of the run, IMPORT_CAD and its body operations,
     the CAD Create recipe, or IMPORT of a raw mesh>
    <the [[operations]], in the order written>
    SET_SIMULATION_LENGTH_UNITS METER
    <the trailing edges>
    SAVEAS <work>/<name>.fsm
    EXPORT_SURFACE_MESH OBJ -1 <work>/<name>.obj
    CLOSE_FLIGHTSTREAM

The OBJ is written in the simulation length unit in force at export, so the
unit is set explicitly before marking, saving and exporting (FR-471 R2).
An OBJ carries no trailing-edge marks; they are saved in the simulation.
The CCS source is emitted by the run's own emitter
(:func:`pyflightstream.cases.ccs_wing.emit_ccs_geometry`), so the stage adds no
second CCS emitter.

THE EVIDENCE GATE (FR-471 R9). :data:`EVIDENCE_GATED` lists the commands the
run did not emit before 0.40.0 and the lofts the stage now runs on every build;
each one used and not ``verified`` on the build is named in
:attr:`GeometryScript.awaiting_evidence`, and the build refuses to run the
script there. The preview still renders it.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from pyflightstream.cases import SimCase, SweepAxis
from pyflightstream.cases._ccs import CCS_SHEDDING_VARIABLE
from pyflightstream.cases._geometry_instruction import (
    CadBodyOperation,
    CreateSource,
    GeometryInstruction,
    GeometryOperation,
    names_after,
    source_names,
)
from pyflightstream.cases.ccs_wing import REFERENCE_FRAME, emit_ccs_geometry
from pyflightstream.cases.mesh import MeshImport
from pyflightstream.commands import CommandRegistry, Status
from pyflightstream.script import Script, helpers

__all__ = [
    "EVIDENCE_GATED",
    "GeometryScript",
    "render_geometry_script",
]

#: The commands a build runs only where a licensed probe verified them on the
#: build: the mesh operations of FR-474, the CAD and CAD Create commands of
#: FR-475, the CCS lofts and the surface-mesh export. Every other command the
#: build emits is one the run already emitted before 0.40.0.
EVIDENCE_GATED: frozenset[str] = frozenset(
    {
        "EXPORT_SURFACE_MESH",
        "CAD_CREATE_WING_MESH_FROM_CCS",
        "CAD_CREATE_FUSELAGE_MESH_FROM_CCS",
        "CAD_CREATE_REVOLVE_MESH_FROM_CCS",
        "SURFACE_CIRCULAR_COPY_PASTE",
        "SURFACE_LINEAR_COPY_PASTE",
        "SURFACE_CUT_BY_PLANE",
        "SURFACE_AUTO_HOLE_FILL",
        "DELETE_DEGENERATE_FACES",
        "SURFACE_SELECT_BY_ID",
        "SURFACE_SELECT_BY_THRESHOLD",
        "CREATE_NEW_SURFACE_FROM_SELECTION",
        "DELETE_SELECTED_FACES",
        "SELECT_MESH_NODE",
        "TRANSFORM_SELECTED_NODES",
        "CAD_BODY_DELETE",
        "CAD_BODY_MIRROR",
        "CAD_BODY_SCALE",
        "CAD_BODY_TRANSLATE",
        "CAD_BODY_ROTATE",
        "CAD_BODY_SELECT_BY_THRESHOLD",
        "SET_CAD_CREATE_MERGE_TOLERANCE",
        "SET_CAD_CREATE_SPLINE_SEGMENTS",
        "SET_CAD_CREATE_SPLINE_LOFT",
        "SET_CAD_CURVATURE_REFINEMENT",
        "CAD_CREATE_BOX",
        "CAD_CREATE_SPHERE",
        "CAD_CREATE_CYLINDER",
        "CAD_CREATE_SHEET",
        "CAD_CREATE_IMPORT_CURVE_TXT",
        "CAD_CREATE_SCALE_CURVES",
        "CAD_CREATE_ROTATE_CURVES",
        "CAD_CREATE_TRANSLATE_CURVES",
        "CAD_CREATE_CURVE_UNSELECT",
        "CAD_CREATE_CURVE_EXPORT_CCS",
    }
)

#: The simulation's length unit after the build; every row reads the saved body in it.
SIMULATION_UNIT = "METER"

#: An axis of the reference frame as the copy and rotate commands number it
#: (a proposed reading the P1-1 probe confirms: the manual prints only the 1).
_AXIS_INDEX = {"X": "1", "Y": "2", "Z": "3"}

#: The mirror plane as SURFACE_MIRROR numbers it (SRC-003 p.311), the run's own table.
_MIRROR_PLANE_INDEX = {"YZ": 1, "XZ": 2, "XY": 3}

_RAW_MESH_TYPES = {".obj": "OBJ", ".stl": "STL"}


@dataclass(frozen=True)
class GeometryScript:
    """The rendered script of one build and what it rests on.

    Attributes
    ----------
    text : str
        The script, as the solver reads it.
    steps : tuple of (str, tuple of str)
        The boundary names after the source and after each operation.
    commands : tuple of str
        Every command the script emits, in first-use order.
    awaiting_evidence : tuple of str
        The gated commands used and not verified on the build (FR-471 R9).
    pending_files : mapping of str to bytes
        Files the script reads that the build writes first (a CCS copy in a
        shedding direction, a trailing-edge node file), by absolute path.
    fsm : str
        The saved simulation the script writes.
    obj : str
        The mesh the script exports.
    """

    text: str
    steps: tuple[tuple[str, tuple[str, ...]], ...]
    commands: tuple[str, ...]
    awaiting_evidence: tuple[str, ...]
    pending_files: Mapping[str, bytes] = field(default_factory=dict)
    fsm: str = ""
    obj: str = ""


def render_geometry_script(
    instruction: GeometryInstruction,
    *,
    folder: Path,
    work: Path,
    version: str,
    trailing_edge_points_m: Sequence[Sequence[float]] = (),
    registry: CommandRegistry | None = None,
) -> GeometryScript:
    """Render the build script of one instruction for one build.

    Parameters
    ----------
    instruction : GeometryInstruction
        The instruction, a variant's already resolved.
    folder : Path
        The folder holding the instruction and its source files.
    work : Path
        The folder the solver runs in and writes into (the partial folder).
    version : str
        The solver build's version; emission is validated against it.
    trailing_edge_points_m : sequence of (x, y, z)
        The points of a ``[trailing_edges]`` file route, in metres, already
        checked against the source mesh.
    registry : CommandRegistry, optional
        The command database the emission and the evidence gate read; the
        package's own by default.

    Returns
    -------
    GeometryScript
        The script and what it rests on.

    Raises
    ------
    CampaignConfigError, CommandArgumentError, ValueError
        A source the run's emitter refuses, or a command the build's
        database does not carry.
    """
    script = Script(version, registry)
    script.working_dir = str(work)
    names = source_names(instruction)
    steps = tuple(names_after(instruction, names))
    script.emit("NEW_SIMULATION")
    _emit_source(script, instruction, folder, names)
    _emit_operations(script, instruction, folder, names)
    obj = str(work / f"{instruction.name}.obj")
    fsm = str(work / f"{instruction.name}.fsm")
    script.emit("SET_SIMULATION_LENGTH_UNITS", SIMULATION_UNIT)
    script.declare_existing(
        boundaries={name: index for index, name in enumerate(instruction.boundaries, start=1)}
    )
    _emit_trailing_edges(script, instruction, work, trailing_edge_points_m)
    script.emit("SAVEAS", fsm)
    script.emit("EXPORT_SURFACE_MESH", "OBJ", -1, obj)
    script.emit("CLOSE_FLIGHTSTREAM")
    commands = _commands(script)
    return GeometryScript(
        text=script.render(),
        steps=steps,
        commands=commands,
        awaiting_evidence=_awaiting_evidence(script, commands),
        pending_files={
            path: data if isinstance(data, bytes) else data.encode("utf-8")
            for path, data in script.pending_input_files.items()
        },
        fsm=fsm,
        obj=obj,
    )


def _commands(script: Script) -> tuple[str, ...]:
    """Return the command names of a rendered script, in first-use order.

    A keyword block and a parameter-line command run to the next blank line,
    so their keywords and paths are never read as commands.
    """
    found: list[str] = []
    in_block = False
    for line in script.render().splitlines():
        if not line.strip():
            in_block = False
            continue
        if in_block:
            continue
        word = line.split(" ", 1)[0]
        entry = script.registry.commands.get(word)
        if entry is None:
            continue
        if word not in found:
            found.append(word)
        in_block = str(entry.layout) in ("keyword_block", "param_lines")
    return tuple(found)


def _awaiting_evidence(script: Script, commands: Sequence[str]) -> tuple[str, ...]:
    """Return the gated commands used that the build's database does not record verified."""
    waiting = []
    for name in commands:
        if name not in EVIDENCE_GATED or name not in script.registry.commands:
            continue
        evidence = script.registry.commands[name].evidence_in(script.version)
        if evidence is None or evidence.record.status is not Status.VERIFIED:
            waiting.append(name)
    return tuple(waiting)


def _emit_source(
    script: Script, instruction: GeometryInstruction, folder: Path, names: Sequence[str]
) -> None:
    """Emit the source table of the instruction."""
    if instruction.ccs is not None:
        _emit_ccs(script, instruction, folder, names)
    elif instruction.cad is not None:
        cad = instruction.cad
        script.emit(
            "IMPORT_CAD",
            cad.options.tessellation_density,
            "TRUE" if cad.options.unreferenced_patches else "FALSE",
            cad.options.num_curvature,
            str(folder / cad.file),
        )
        for operation in cad.operations:
            _emit_cad_operation(script, operation)
        script.emit("CONVERT_CAD_TO_MESH", cad.options.body_index)
    elif instruction.create is not None:
        _emit_create(script, instruction.create, folder, instruction, names)
    else:
        assert instruction.mesh is not None  # the model holds exactly one source
        path = folder / instruction.mesh.file
        script.emit(
            "IMPORT",
            instruction.mesh.units,
            _RAW_MESH_TYPES[path.suffix.lower()],
            str(path),
            clear=True,
        )


def _emit_ccs(
    script: Script, instruction: GeometryInstruction, folder: Path, names: Sequence[str]
) -> None:
    """Emit the CCS source through the run's own emitter, on a case built for it."""
    ccs = instruction.ccs
    assert ccs is not None
    variables: dict[str, str | float | int | bool] = {}
    if ccs.shedding is not None:
        variables[CCS_SHEDDING_VARIABLE] = ccs.shedding
    case = SimCase(
        sim_id=instruction.name,
        aircraft=instruction.name,
        sweep=SweepAxis(type="alpha", values=[0.0]),
        recipe="geometry",
        geometry=str(folder / ccs.file),
        mesh_import=MeshImport(units=ccs.units, ccs=ccs.options),
        inventory=tuple(names),
        variables=variables,
    )
    emit_ccs_geometry(script, case)


def _emit_cad_operation(script: Script, operation: CadBodyOperation) -> None:
    """Emit one CAD body operation, in the reference frame and in metres (FR-475 R1)."""
    if operation.op == "delete":
        script.emit("CAD_BODY_DELETE", operation.body)
    elif operation.op == "delete_by_threshold":
        above = operation.above_m is not None
        value = operation.above_m if above else operation.below_m
        script.emit(
            "CAD_BODY_SELECT_BY_THRESHOLD",
            REFERENCE_FRAME,
            operation.axis,
            value,
            "ABOVE" if above else "BELOW",
            "DELETE",
        )
    elif operation.op == "mirror":
        script.emit("CAD_BODY_MIRROR", operation.body, operation.plane)
    elif operation.op == "scale":
        script.emit("CAD_BODY_SCALE", operation.body, operation.factor)
    elif operation.op == "translate":
        assert operation.vector_m is not None
        script.emit("CAD_BODY_TRANSLATE", operation.body, *operation.vector_m, SIMULATION_UNIT)
    else:
        script.emit("CAD_BODY_ROTATE", operation.body, operation.axis, operation.angle_deg)


def _emit_create(
    script: Script,
    create: CreateSource,
    folder: Path,
    instruction: GeometryInstruction,
    names: Sequence[str],
) -> None:
    """Emit the CAD Create recipe: the settings, then the bodies or the section loft."""
    script.emit("CAD_CREATE_INITIALIZE")
    if create.merge_tolerance_pct is not None:
        script.emit("SET_CAD_CREATE_MERGE_TOLERANCE", create.merge_tolerance_pct)
    if create.spline_segments is not None:
        script.emit("SET_CAD_CREATE_SPLINE_SEGMENTS", create.spline_segments)
    if create.spline_loft is not None:
        script.emit("SET_CAD_CREATE_SPLINE_LOFT", create.spline_loft)
    if create.curvature_points_per_circle is not None:
        script.emit("SET_CAD_CURVATURE_REFINEMENT", create.curvature_points_per_circle)
    for body in create.bodies:
        if body.shape == "box":
            assert body.corner_m is not None and body.lengths_m is not None
            script.emit("CAD_CREATE_BOX", REFERENCE_FRAME, *body.corner_m, *body.lengths_m)
        elif body.shape == "sphere":
            assert body.center_m is not None
            script.emit("CAD_CREATE_SPHERE", REFERENCE_FRAME, *body.center_m, body.radius_m)
        elif body.shape == "cylinder":
            assert body.center_m is not None and body.radii_m is not None
            script.emit(
                "CAD_CREATE_CYLINDER",
                REFERENCE_FRAME,
                *body.center_m,
                *body.radii_m,
                body.length_m,
            )
        else:
            assert body.lengths_m is not None
            script.emit(
                "CAD_CREATE_SHEET",
                REFERENCE_FRAME,
                body.plane,
                body.offset_m,
                *body.lengths_m,
            )
    if create.sections:
        _emit_section_loft(script, create, folder, instruction, names)


def _emit_section_loft(
    script: Script,
    create: CreateSource,
    folder: Path,
    instruction: GeometryInstruction,
    names: Sequence[str],
) -> None:
    """Emit each section placed at its station, then the CCS wing loft (FR-475 R2)."""
    loft = create.loft
    if loft is None:
        raise ValueError("[[create.sections]] are lofted by [create.loft]; the table is not stated")
    for index, section in enumerate(create.sections, start=1):
        script.emit(
            "CAD_CREATE_IMPORT_CURVE_TXT",
            section.units,
            "2D",
            REFERENCE_FRAME,
            section.plane,
            str(folder / section.file),
        )
        script.emit("CAD_CREATE_CURVE_SELECT", index)
        script.emit("CAD_CREATE_SCALE_CURVES", section.chord_m, "DELETE")
        if section.twist_deg:
            script.emit(
                "CAD_CREATE_ROTATE_CURVES", REFERENCE_FRAME, "Y", section.twist_deg, "DELETE"
            )
        script.emit("CAD_CREATE_TRANSLATE_CURVES", *section.leading_edge_m, "DELETE")
        script.emit("CAD_CREATE_CURVE_UNSELECT", index)
    script.emit("CAD_CREATE_CURVE_SELECT", -1)
    if loft.export_ccs:
        script.emit(
            "CAD_CREATE_CURVE_EXPORT_CCS",
            str(Path(script.working_dir or ".") / f"{instruction.name}.ccs.csv"),
        )
    script.emit(
        "CAD_CREATE_WING_MESH_FROM_CCS",
        names[0],
        "TRUE" if loft.mark_trailing_edges else "FALSE",
        loft.trailing_edge,
        loft.close_ends,
        loft.loft_u,
        loft.loft_v,
    )


def _emit_operations(
    script: Script, instruction: GeometryInstruction, folder: Path, names: Sequence[str]
) -> None:
    """Emit the ``[[operations]]`` in the order written, each surface cited by position."""
    current = list(names)
    unit = instruction.mesh.units if instruction.mesh is not None else SIMULATION_UNIT
    for position, operation in enumerate(instruction.operations, start=1):
        _emit_operation(script, operation, current, unit)
        operation.apply(current, position)


def _position(names: Sequence[str], surface: str | None) -> int:
    assert surface is not None and surface in names  # the names were checked by the model
    return list(names).index(surface) + 1


def _emit_operation(
    script: Script, operation: GeometryOperation, names: Sequence[str], unit: str
) -> None:
    """Emit one operation of the instruction (FR-470 R3, FR-474)."""
    if operation.op in ("scale", "rename", "mirror"):
        _emit_sidecar_operation(script, operation, names)
    else:
        _emit_new_operation(script, operation, names, unit)


def _emit_sidecar_operation(
    script: Script, operation: GeometryOperation, names: Sequence[str]
) -> None:
    """Emit a scale, a rename or a mirror, the kinds the sidecar carried before 0.40.0."""
    op = operation.op
    if op == "scale":
        assert operation.factors is not None
        surface = -1 if operation.surface in (None, "all") else _position(names, operation.surface)
        script.emit(
            "SURFACE_SCALE",
            frame=REFERENCE_FRAME,
            scale_x=operation.factors[0],
            scale_y=operation.factors[1],
            scale_z=operation.factors[2],
            surface=surface,
        )
    elif op == "rename":
        script.emit("SURFACE_RENAME", index=_position(names, operation.surface), name=operation.to)
    elif op == "mirror":
        assert operation.plane is not None
        script.emit(
            "SURFACE_MIRROR",
            surface=_position(names, operation.surface),
            coordinate_system=REFERENCE_FRAME,
            mirror_plane=_MIRROR_PLANE_INDEX[operation.plane],
            combine_flag="TRUE",
            delete_source_flag="FALSE",
        )


def _emit_new_operation(
    script: Script, operation: GeometryOperation, names: Sequence[str], unit: str
) -> None:
    """Emit a mesh operation of FR-474: copies, cut, repair, selections, node moves."""
    op = operation.op
    if op == "circular_copy":
        assert operation.axis is not None
        script.emit(
            "SURFACE_CIRCULAR_COPY_PASTE",
            _position(names, operation.surface),
            REFERENCE_FRAME,
            _AXIS_INDEX[operation.axis],
            operation.count,
            operation.angle_deg,
        )
    elif op == "linear_copy":
        assert operation.vector is not None
        script.emit(
            "SURFACE_LINEAR_COPY_PASTE",
            _position(names, operation.surface),
            operation.count,
            REFERENCE_FRAME,
            unit,
            *operation.vector,
        )
    elif op == "cut":
        script.emit(
            "SURFACE_CUT_BY_PLANE",
            frame=REFERENCE_FRAME,
            plane=operation.plane,
            offset=operation.offset,
            surface=_position(names, operation.surface),
        )
    elif op == "fill_holes":
        script.emit("SURFACE_AUTO_HOLE_FILL", _position(names, operation.surface))
    elif op == "delete_degenerate_faces":
        script.emit("DELETE_DEGENERATE_FACES")
    elif op in ("extract_faces", "delete_faces"):
        _emit_selection(script, operation, names)
        script.emit(
            "CREATE_NEW_SURFACE_FROM_SELECTION"
            if op == "extract_faces"
            else "DELETE_SELECTED_FACES"
        )
    else:
        assert operation.nodes is not None and operation.vector is not None
        for node in operation.nodes:
            script.emit("SELECT_MESH_NODE", node)
        script.emit("TRANSFORM_SELECTED_NODES", REFERENCE_FRAME, "TRANSLATION", *operation.vector)


def _emit_selection(script: Script, operation: GeometryOperation, names: Sequence[str]) -> None:
    """Emit the selection an extraction or a deletion consumes on the next line."""
    restricted = operation.surface is not None and operation.surface != "all"
    if restricted:
        script.emit("SURFACE_SELECT_BY_ID", _position(names, operation.surface))
    if operation.min is not None and operation.max is not None:
        scope = "ABOVE_MIN_BELOW_MAX"
    elif operation.min is not None:
        scope = "ABOVE_MIN"
    else:
        scope = "BELOW_MAX"
    script.emit(
        "SURFACE_SELECT_BY_THRESHOLD",
        frame=REFERENCE_FRAME,
        threshold=operation.quantity,
        min_value=operation.min if operation.min is not None else 0.0,
        max_value=operation.max if operation.max is not None else 0.0,
        range=scope,
        subset="SELECTED_FACES" if restricted else "ALL_FACES",
    )


def _emit_trailing_edges(
    script: Script,
    instruction: GeometryInstruction,
    work: Path,
    points_m: Sequence[Sequence[float]],
) -> None:
    """Mark the trailing edges a ``[trailing_edges]`` table states, after the length unit."""
    marking = instruction.trailing_edges
    if marking is None or marking.route == "none":
        return
    if marking.route == "file":
        helpers.mark_wake_edges(
            script,
            edge_type=marking.edge_type,
            tolerance=marking.tolerance,
            units=SIMULATION_UNIT,
            node_file=str(work / f"{instruction.name}.wake_nodes.txt"),
            midpoints=points_m,
        )
        return
    if marking.sweep_angle_deg is not None:
        script.emit("SET_TRAILING_EDGE_SWEEP_ANGLE", marking.sweep_angle_deg)
    if not marking.detect_surfaces:
        helpers.detect_every_boundary(script, "trailing_edges")
        return
    indices = [_position(instruction.boundaries, name) for name in marking.detect_surfaces]
    script.emit("DETECT_TRAILING_EDGES_BY_SURFACE", len(indices), indices)
