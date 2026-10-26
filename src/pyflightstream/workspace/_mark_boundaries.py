"""Plan and apply one boundary-marking pass, with saved-state admission before promotion."""

from __future__ import annotations

import json
import math
import re
import shutil
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

import pyflightstream._textio as _textio
from pyflightstream._digest import file_sha256
from pyflightstream._errors import InputArtifactError, PyflightstreamError
from pyflightstream._fsm import (
    boundary_names,
    saved_base_regions,
    saved_termination_count,
    saved_trailing_edge_groups,
)
from pyflightstream._lengths import METRES_PER_UNIT
from pyflightstream.cases.mesh import BoundaryDeclarations, MeshImport, WakeTerminationMarking
from pyflightstream.commands import CommandRegistry, Status
from pyflightstream.script import Script, helpers
from pyflightstream.versions import resolve
from pyflightstream.workspace.sidecars import (
    boundaries_for_marking,
    inventory_sidecar,
    load_toml,
    obj_boundary_names,
    obj_face_counts,
    read_boundary_declarations,
    read_inventory,
    read_mesh_import,
)
from pyflightstream.workspace.wake_edges import (
    matched_trailing_edge_sets,
    matched_wake_termination_nodes,
    saved_wake_edge_verdict,
)


class BoundaryMarkingError(PyflightstreamError):
    """A marking pass failed its solver execution or saved-state read-back."""


@dataclass
class BoundaryMarkingPlan:
    """Validated inputs, rendered script and the outputs admitted together."""

    mesh: Path
    sidecar: Path
    declarations: BoundaryDeclarations
    work: Path
    script: str
    pending: dict[str, bytes]
    awaiting_evidence: tuple[str, ...]
    names: tuple[str, ...]
    faces: tuple[int, ...]
    sets: list[dict[str, Any]]
    nodes: dict[str, tuple[int, ...]]
    inputs: dict[str, str]
    steps: tuple[str, ...]

    @property
    def outputs(self) -> tuple[Path, ...]:
        """Return the five products promoted only after read-back succeeds."""
        return (
            self.mesh.with_suffix(".fsm"),
            inventory_sidecar(self.mesh, "fsm"),
            self.mesh.with_suffix(".mark.txt"),
            self.mesh.with_suffix(".mark.log"),
            self.mesh.with_suffix(".mark.json"),
        )


def _obj_edges(mesh: Path, unit: str) -> list[tuple[str, tuple[float, ...]]]:
    """Read polygon perimeter midpoints, retaining their surface ownership."""
    vertices: list[np.ndarray] = []
    edges: list[tuple[str, tuple[float, ...]]] = []
    family = "Boundary-1"
    for line in mesh.read_text(encoding="utf-8").splitlines():
        words = line.split("#", 1)[0].split()
        if not words:
            continue
        if words[0] == "v":
            vertices.append(np.asarray(words[1:4], dtype=float) * METRES_PER_UNIT[unit])
        elif words[0] in {"g", "o"}:
            family = words[1]
        elif words[0] == "f":
            ids = [int(word.split("/")[0]) for word in words[1:]]
            ids = [i - 1 if i > 0 else len(vertices) + i for i in ids]
            for a, b in zip(ids, ids[1:] + ids[:1], strict=True):
                edges.append((family, tuple((vertices[a] + vertices[b]) / 2)))
    return edges


def _move_copies(copies, operation: Any, unit: str):
    """Apply one affine operation to all copies of a point, in metres."""
    if operation.op == "mirror":
        axis = {"YZ": 0, "XZ": 1, "XY": 2}[operation.plane]
        reflected = [xyz.copy() for xyz in copies]
        for xyz in reflected:
            xyz[axis] *= -1
        return copies + reflected
    if operation.op == "scale":
        return [xyz * operation.factors for xyz in copies]
    if operation.op == "translate":
        shift = np.asarray(operation.vector) * METRES_PER_UNIT[unit]
        return [xyz + shift for xyz in copies]
    axis = np.eye(3)[{"X": 0, "Y": 1, "Z": 2}[operation.axis]]
    angle = math.radians(operation.angle_deg)
    return [
        xyz * math.cos(angle)
        + np.cross(axis, xyz) * math.sin(angle)
        + axis * np.dot(axis, xyz) * (1 - math.cos(angle))
        for xyz in copies
    ]


def _placed_points(points, mesh: Path, spec: MeshImport, tolerance: float):
    """Carry source midpoints through the same ordered family transforms as the OBJ."""
    edges = _obj_edges(mesh, spec.units)
    placed: list[tuple[float, ...]] = []
    for point in points:
        families = {
            name for name, xyz in edges if np.linalg.norm(np.asarray(xyz) - point) <= tolerance
        }
        if not families:
            raise InputArtifactError(f"{mesh}: point {point} is not on an OBJ polygon edge")
        for family in sorted(families):
            copies = [np.asarray(point, dtype=float)]
            for operation in spec.operations:
                if operation.surface not in ("all", family):
                    continue
                if operation.op == "rename":
                    assert operation.to is not None
                    family = operation.to
                else:
                    copies = _move_copies(copies, operation, spec.units)
            placed.extend(tuple(float(v) for v in xyz) for xyz in copies)
    return tuple(dict.fromkeys(placed))


def _import_operations(
    script: Script, spec: MeshImport, names: list[str], faces: list[int]
) -> None:
    for operation in spec.operations:
        if operation.surface != "all" and operation.surface not in names:
            raise InputArtifactError(
                f"import operation names {operation.surface!r}; available: {names}"
            )
        index = None if operation.surface == "all" else names.index(operation.surface) + 1
        if operation.op == "rename":
            if operation.to in names and operation.to != operation.surface:
                raise InputArtifactError(f"rename would duplicate boundary {operation.to!r}")
            script.emit("SURFACE_RENAME", index, operation.to)
            assert index is not None and operation.to is not None
            names[index - 1] = operation.to
        elif operation.op == "scale":
            assert operation.factors is not None
            script.emit("SURFACE_SCALE", 1, *operation.factors, index or -1)
        elif operation.op == "mirror":
            assert operation.plane is not None
            assert index is not None
            faces[index - 1] *= 2
            script.emit(
                "SURFACE_MIRROR",
                index,
                1,
                {"YZ": 1, "XZ": 2, "XY": 3}[operation.plane],
                "TRUE",
                "FALSE",
            )
        elif operation.op == "rotate":
            assert operation.axis is not None and operation.angle_deg is not None
            helpers.rotate_surfaces(
                script,
                frame=1,
                axis=operation.axis,
                angle_deg=operation.angle_deg,
                boundaries="all" if index is None else [index],
            )
        else:
            assert operation.vector is not None
            script.emit(
                "TRANSLATE_SURFACE_IN_FRAME",
                1,
                *operation.vector,
                spec.units,
                index or 0,
                "DISABLE" if index is None else "ENABLE",
            )


def _marking_inputs(mesh):
    source = Path(mesh).resolve()
    if source.suffix.lower() != ".obj" or not source.is_file():
        raise InputArtifactError(f"{source}: mark-boundaries requires an existing .obj")
    sidecar = boundaries_for_marking(source)
    declarations = read_boundary_declarations(sidecar)
    if declarations.fs_build is None:
        raise InputArtifactError(f"{sidecar}: mark-boundaries requires fs_build")
    spec = read_mesh_import(sidecar)
    if spec is None:
        raise InputArtifactError(f"{sidecar}: mark-boundaries requires [import] units")
    names = list(read_inventory(sidecar))
    if tuple(names) != obj_boundary_names(source) or len(set(names)) != len(names):
        raise InputArtifactError(f"{sidecar}: boundaries must equal the OBJ's unique family order")
    data = load_toml(sidecar, "boundary")
    faces = data.get("boundary_faces")
    if (
        not isinstance(faces, list)
        or len(faces) != len(names)
        or any(type(count) is not int or count < 0 for count in faces)
        or data.get("mesh_faces") != sum(faces)
        or tuple(faces) != obj_face_counts(source)
    ):
        raise InputArtifactError(f"{sidecar}: supply boundary_faces and their total mesh_faces")
    if data.get("mesh_sha256") != file_sha256(source):
        raise InputArtifactError(f"{sidecar}: mesh_sha256 is stale; refresh the OBJ inventory")
    if (
        not declarations.trailing_edges
        and not declarations.base_regions
        and not declarations.no_trailing_edges
    ):
        raise InputArtifactError(
            f"{sidecar}: declare trailing edges or [trailing_edges] none = true"
        )
    return source, sidecar, declarations, spec, names, faces


def _node_routes(sidecar, declarations, spec):
    termination = [entry for entry in declarations.trailing_edges if entry.wake_termination_nodes]
    explicit = [entry for entry in termination if entry.wake_termination_nodes != "auto"]
    if explicit and any(
        operation.op == "mirror" or (operation.op == "translate" and operation.surface != "all")
        for operation in spec.operations
    ):
        raise InputArtifactError(
            f"{sidecar}: explicit nodes after a vertex-changing import operation "
            "have unmeasured numbering"
        )
    if explicit and any(region.merge_into for region in declarations.base_regions):
        raise InputArtifactError(
            f"{sidecar}: explicit termination nodes across a merge await saved-node evidence"
        )
    return termination, explicit


def _work_path(source: Path) -> Path:
    work = source.with_name(f".{source.stem}.mark-work")
    ordinal = 0
    while work.exists():
        ordinal += 1
        work = source.with_name(f".{source.stem}.mark-work.{ordinal}")
    return work


def _renamed_declarations(declarations, before, after):
    """Keep declarations bound to their source families through import renames."""
    names = dict(zip(before, after, strict=True))
    bases = tuple(
        region.model_copy(
            update={
                "family": names.get(region.family, region.family),
                "merge_into": names.get(region.merge_into, region.merge_into),
            }
        )
        for region in declarations.base_regions
    )
    trailing = tuple(
        entry.model_copy(
            update={
                "marking": entry.marking.model_copy(
                    update={
                        "detect_surfaces": tuple(
                            names.get(name, name) for name in entry.marking.detect_surfaces
                        ),
                    }
                )
            }
        )
        for entry in declarations.trailing_edges
    )
    return declarations.model_copy(update={"base_regions": bases, "trailing_edges": trailing})


def _awaiting(script: Script) -> tuple[str, ...]:
    commands = dict.fromkeys(
        line.split()[0]
        for line in script.render().splitlines()
        if line.split() and line.split()[0] in script.registry.commands
    )
    return tuple(
        name
        for name in commands
        if (evidence := script.registry.commands[name].evidence_in(script.version)) is None
        or evidence.record.status is not Status.VERIFIED
    )


def plan_mark_boundaries(
    mesh: str | Path, *, registry: CommandRegistry | None = None
) -> BoundaryMarkingPlan:
    """Validate declarations and render a marking pass without writing any file.

    Parameters
    ----------
    mesh : str or Path
        OBJ with a kind-qualified or legacy boundary sidecar.
    registry : CommandRegistry, optional
        Command evidence and grammar, injectable for offline tests.

    Returns
    -------
    BoundaryMarkingPlan
        Preview, input digests and staging destinations.
    """
    source, sidecar, declarations, spec, names, faces = _marking_inputs(mesh)
    termination, explicit = _node_routes(sidecar, declarations, spec)
    work = _work_path(source)
    script = Script.for_marking(declarations.fs_build, registry)
    script.working_dir = str(work)
    pending: dict[str, bytes] = {}
    sets: list[dict[str, Any]] = []
    nodes: dict[str, tuple[int, ...]] = {}
    inputs = {str(source): file_sha256(source), str(sidecar): file_sha256(sidecar)}
    steps: list[str] = []

    emit = script.emit
    emit("NEW_SIMULATION")
    emit("IMPORT", spec.units, "OBJ", str(source), clear=True)
    before = tuple(names)
    _import_operations(script, spec, names, faces)
    declarations = _renamed_declarations(declarations, before, names)
    script.declare_existing(boundaries={name: i for i, name in enumerate(names, 1)})
    emit("SET_SIMULATION_LENGTH_UNITS", "METER")

    def mark(label: str, marking: Any) -> None:
        if marking.route == "detect":
            if marking.sweep_angle_deg is not None:
                emit("SET_TRAILING_EDGE_SWEEP_ANGLE", marking.sweep_angle_deg)
            if marking.detect_surfaces:
                indices = [names.index(name) + 1 for name in marking.detect_surfaces]
                emit("DETECT_TRAILING_EDGES_BY_SURFACE", len(indices), indices)
            else:
                helpers.detect_every_boundary(script, "trailing_edges")
            steps.append(f"{label}: STANDARD detected trailing edges")
            return
        bound = matched_trailing_edge_sets(marking, source, spec.units)
        entry = bound.sets[0]
        assert entry.points_file is not None
        path = Path(entry.points_file)
        inputs[str(path)] = file_sha256(path)
        token = work / f"edges-{len(sets) + 1}.txt"
        points = _placed_points(entry.points_m, source, spec, bound.tolerance)
        helpers.mark_wake_edges(
            script,
            edge_type=entry.edge_type,
            tolerance=bound.tolerance,
            units="METER",
            node_file=str(token),
            midpoints=points,
        )
        body = script.pending_input_files[str(token)]
        pending[str(token)] = body.encode("utf-8") if isinstance(body, str) else body
        sets.append(
            {
                "label": label,
                "type": entry.edge_type,
                "file": str(path),
                "points_m": points,
                "tolerance": bound.tolerance,
            }
        )
        steps.append(f"{label}: {entry.edge_type}, {len(points)} trailing-edge points")

    for entry in declarations.trailing_edges:
        mark(entry.label, entry.marking)
    _emit_bases(emit, mark, declarations, names, steps)
    _emit_nodes(
        emit,
        termination,
        explicit,
        source=source,
        spec=spec,
        inputs=inputs,
        nodes=nodes,
        steps=steps,
    )
    _emit_merges(emit, declarations, names, faces, steps)
    emit("SAVEAS", str(work / source.with_suffix(".fsm").name))
    emit("EXPORT_LOG", str(work / source.with_suffix(".mark.log").name))
    emit("CLOSE_FLIGHTSTREAM")
    plan = BoundaryMarkingPlan(
        source,
        sidecar,
        declarations,
        work,
        script.render(),
        pending,
        _awaiting(script),
        tuple(names),
        tuple(faces),
        sets,
        nodes,
        inputs,
        tuple(steps),
    )
    _input_output_collisions(plan)
    return plan


def _emit_bases(emit, mark, declarations, names, steps):
    for index, region in enumerate(declarations.base_regions, 1):
        emit("CREATE_NEW_BASE_REGION", names.index(region.family) + 1, region.model, region.cp)
        emit(
            "SET_BASE_REGION_CP",
            index,
            "CUSTOM" if region.model == "USER" else region.model,
            region.cp,
        )
        if region.trailing_edges == "auto":
            emit("SET_BASE_REGION_TRAILING_EDGES", index)
        else:
            mark(region.family, region.trailing_edges)
        steps.append(
            f"base {region.family}: {region.model}, Cp {region.cp}, rim {region.trailing_edges}"
        )


def _emit_nodes(emit, termination, explicit, *, source, spec, inputs, nodes, steps):
    if any(entry.wake_termination_nodes == "auto" for entry in termination):
        emit("AUTO_DETECT_WAKE_TERMINATION_NODES")
        steps.append("autodetect wake-termination nodes once")
    for entry in explicit:
        assert entry.wake_termination_nodes is not None
        path = Path(entry.wake_termination_nodes)
        inputs[str(path)] = file_sha256(path)
        bound_nodes = matched_wake_termination_nodes(
            WakeTerminationMarking(points_file=str(path), tolerance=entry.marking.tolerance),
            source,
            spec.units,
        )
        nodes[entry.label] = bound_nodes.nodes
        for node in bound_nodes.nodes:
            emit("SELECT_MESH_NODE", node)
        emit("MARK_WAKE_TERMINATION_NODES")
        steps.append(f"{entry.label}: {len(bound_nodes.nodes)} explicit termination nodes")


def _emit_merges(emit, declarations, names, faces, steps):
    for region in declarations.base_regions:
        if region.merge_into is None:
            continue
        base, parent = names.index(region.family), names.index(region.merge_into)
        lower, upper = sorted((base, parent))
        emit("SURFACE_COMBINE", 2, [base + 1, parent + 1])
        emit("SURFACE_RENAME", lower + 1, region.merge_into)
        names[lower] = region.merge_into
        faces[lower] += faces[upper]
        del names[upper], faces[upper]
        steps.append(f"merge {region.family} into {region.merge_into}: {faces[lower]} OBJ faces")


def _input_output_collisions(plan: BoundaryMarkingPlan) -> None:
    inputs = {Path(name).resolve() for name in plan.inputs}
    for output in plan.outputs:
        if output.resolve() in inputs:
            raise InputArtifactError(
                f"{output}: a marking output is also an input; rename the input"
            )


def refuse_mark_boundaries(plan: BoundaryMarkingPlan, *, overwrite: bool) -> None:
    """Refuse unverified commands, stale inputs and an unapproved replacement before execution."""
    _input_output_collisions(plan)
    if plan.awaiting_evidence:
        raise InputArtifactError(
            f"{plan.declarations.fs_build}: awaiting_evidence: {', '.join(plan.awaiting_evidence)}"
        )
    if plan.outputs[0].exists() and not overwrite:
        raise InputArtifactError(
            f"{plan.outputs[0]} exists; pass overwrite=True (CLI: --overwrite) to replace it"
        )
    for name, digest in plan.inputs.items():
        if not Path(name).is_file() or file_sha256(Path(name)) != digest:
            raise InputArtifactError(f"{name} changed; run geometry mark-boundaries again")


def _read_back(plan: BoundaryMarkingPlan, saved: Path) -> dict[str, Any]:
    assert plan.declarations.fs_build is not None
    if boundary_names(saved) != plan.names:
        raise BoundaryMarkingError(f"{saved}: saved boundary names differ from {plan.names}")
    verdict = saved_wake_edge_verdict(
        plan.sets, saved.parent, [saved.name], plan.declarations.fs_build
    )
    if verdict is not None:
        raise BoundaryMarkingError(verdict[1])
    groups = saved_trailing_edge_groups(saved)
    expected = len(plan.declarations.trailing_edges) + len(plan.declarations.base_regions)
    if len(groups) != expected:
        raise BoundaryMarkingError(
            f"{saved}: {len(groups)} trailing-edge groups, expected {expected}"
        )
    termination = saved_termination_count(saved)
    declared = any(entry.wake_termination_nodes for entry in plan.declarations.trailing_edges)
    required = len({node for values in plan.nodes.values() for node in values})
    if declared and termination < max(1, required):
        raise BoundaryMarkingError(
            f"{saved}: {termination} termination nodes, expected at least {max(1, required)}"
        )
    bases = saved_base_regions(saved)
    expected_bases = tuple(
        (r.family, r.cp, {"USER": 0, "EMPIRICAL": 1, "AXISYMMETRIC": 2}[r.model])
        for r in plan.declarations.base_regions
    )
    if len(bases) != len(expected_bases) or any(
        actual[0] != expected[0]
        or actual[2] != expected[2]
        or not math.isclose(actual[1], expected[1], rel_tol=1e-6, abs_tol=1e-9)
        for actual, expected in zip(bases, expected_bases, strict=False)
    ):
        raise BoundaryMarkingError(f"{saved}: saved base regions differ from {expected_bases}")
    return {
        "boundaries": plan.names,
        "boundary_faces": plan.faces,
        "groups": groups,
        "termination_nodes": termination,
        "base_regions": bases,
        "entries": [
            dict(
                label=entry.label,
                type=entry.marking.edge_type,
                group=groups[index],
                termination=entry.wake_termination_nodes,
                explicit_nodes=plan.nodes.get(entry.label, ()),
            )
            for index, entry in enumerate(plan.declarations.trailing_edges)
        ],
        "steps": plan.steps,
    }


def apply_mark_boundaries(
    plan: BoundaryMarkingPlan,
    *,
    runner: Callable,
    overwrite: bool = False,
    package_version: str = "unknown",
) -> dict[str, Any]:
    """Run once and admit all five outputs only after saved-state checks succeed.

    Parameters
    ----------
    plan : BoundaryMarkingPlan
        Validated preview to execute.
    runner : callable
        Higher-layer execution callback taking script and working directory.
    overwrite : bool
        Whether to replace an existing saved simulation.
    package_version : str
        Package version recorded with the solver outcome.

    Returns
    -------
    dict
        The promoted marking record.
    """
    refuse_mark_boundaries(plan, overwrite=overwrite)
    assert plan.declarations.fs_build is not None
    plan.work.mkdir()
    script = plan.work / plan.mesh.with_suffix(".mark.txt").name
    _textio.write_text(script, plan.script)
    for name, body in plan.pending.items():
        Path(name).write_bytes(body)
    try:
        outcome = runner(script, plan.work)
    except Exception as error:
        raise BoundaryMarkingError(
            f"mark-boundaries runner failed: {error}; inspect {plan.work}"
        ) from error
    log = plan.work / plan.mesh.with_suffix(".mark.log").name
    if not log.is_file():
        _textio.write_text(log, outcome.log)
    if outcome.failed:
        raise BoundaryMarkingError(
            f"mark-boundaries failed: {outcome.diagnosis}; inspect {plan.work}"
        )
    found = re.search(r"\bbuild\s*#\s*(\d+)", outcome.log, re.IGNORECASE)
    if found is None or found.group(1) != resolve(plan.declarations.fs_build).build:
        raise BoundaryMarkingError(
            f"{outcome.executable}: saved pass did not report the requested build "
            f"{plan.declarations.fs_build}; nothing promoted; inspect {plan.work}"
        )
    saved = plan.work / plan.outputs[0].name
    try:
        summary = _read_back(plan, saved)
        refuse_mark_boundaries(plan, overwrite=overwrite)
    except (OSError, ValueError, PyflightstreamError) as error:
        raise BoundaryMarkingError(
            f"read-back failed: {error}; nothing promoted; inspect {plan.work}"
        ) from error
    try:
        return _publish_record(plan, outcome, summary, package_version)
    except OSError as error:
        raise BoundaryMarkingError(
            f"publication failed: {error}; nothing promoted; inspect {plan.work}"
        ) from error


def _publish_record(plan, outcome, summary, package_version):
    """Stage inventory and provenance before promoting the complete output set."""
    assert plan.declarations.fs_build is not None
    saved = plan.work / plan.outputs[0].name
    script = plan.work / plan.outputs[2].name
    inventory = plan.work / plan.outputs[1].name
    _textio.write_text(
        inventory,
        "\n".join(
            (
                f"boundaries = {json.dumps(plan.names)}",
                f"boundary_faces = {json.dumps(plan.faces)}",
                f"mesh_faces = {sum(plan.faces)}",
                f"mesh_sha256 = {json.dumps(file_sha256(saved))}",
                f"marked_by = {json.dumps(plan.outputs[4].name)}",
            )
        )
        + "\n",
    )
    record = {
        "schema_version": 1,
        "package_version": package_version,
        "fs_build": plan.declarations.fs_build,
        "solver": {
            "build_id": resolve(plan.declarations.fs_build).build,
            "version": plan.declarations.fs_build,
            "executable": outcome.executable,
            "return_code": outcome.return_code,
            "wall_s": outcome.wall_s,
        },
        "inputs": plan.inputs,
        "script_sha256": file_sha256(script),
        "fsm_sha256": file_sha256(saved),
        "read_back": summary,
    }
    _textio.write_json(plan.work / plan.outputs[4].name, record)
    _promote(plan)
    return record


def _promote(plan: BoundaryMarkingPlan) -> None:
    """Back up destinations before replacing them, rolling back a failed promotion."""
    backups: dict[Path, Path | None] = {}
    promoted: list[Path] = []
    with tempfile.TemporaryDirectory(prefix="promote-", dir=plan.work) as directory:
        try:
            for index, destination in enumerate(plan.outputs):
                backup = Path(directory) / str(index) if destination.exists() else None
                if backup is not None:
                    shutil.copyfile(destination, backup)
                backups[destination] = backup
            for destination in plan.outputs:
                temporary = Path(directory) / (destination.name + ".new")
                shutil.copyfile(plan.work / destination.name, temporary)
                temporary.replace(destination)
                promoted.append(destination)
        except OSError as error:
            for destination in reversed(promoted):
                backup = backups[destination]
                if backup is None:
                    destination.unlink()
                else:
                    backup.replace(destination)
            raise BoundaryMarkingError(
                f"promotion failed; prior outputs restored: {error}"
            ) from error
