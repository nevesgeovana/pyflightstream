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

import pyflightstream._textio as _textio
from pyflightstream._digest import file_sha256
from pyflightstream._errors import (
    InputArtifactError,
    NotApplicableWarning,
    PyflightstreamError,
    PyflightstreamWarning,
    warn,
)
from pyflightstream._fsm import (
    boundary_names,
    saved_base_regions,
    saved_termination_count,
    saved_trailing_edge_groups,
)
from pyflightstream.cases.mesh import BoundaryDeclarations, MeshImport, WakeTerminationMarking
from pyflightstream.commands import CommandRegistry, Status
from pyflightstream.script import Script, helpers
from pyflightstream.script.helpers import (
    VERTEX_FILE_BUILD,
    VERTEX_IMPORT_ROUTE,
    mark_trailing_edge_vertices,
)
from pyflightstream.versions import resolve
from pyflightstream.workspace._mark_rims import (
    _ObjEdges,
    _placed_points,
    _placed_rim,
    rim_edges,
    saved_cross_edges,
)
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

EVIDENCE_GATED: frozenset[str] = frozenset(
    {
        "IMPORT_WAKE_EDGES_FROM_FILE",
        "TRAILING_EDGES_IMPORT",
        "DETECT_TRAILING_EDGES_BY_SURFACE",
        "AUTO_DETECT_TRAILING_EDGES",
        "SET_TRAILING_EDGE_SWEEP_ANGLE",
        "AUTO_DETECT_WAKE_TERMINATION_NODES",
        "SELECT_MESH_NODE",
        "MARK_WAKE_TERMINATION_NODES",
        "CREATE_NEW_BASE_REGION",
        "SET_BASE_REGION_CP",
        "SET_BASE_REGION_TRAILING_EDGES",
        "SURFACE_COMBINE",
        "SURFACE_RENAME",
    }
)
"""Marking commands requiring verified evidence; session and mesh import are excluded."""


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


#: The command that refreshes the counted fields of a generated OBJ's sidecar (FR-3479).
_REFRESH_COMMAND = "pyfs-workspace geometry inventory {mesh} --refresh"


def _marking_inputs(mesh):
    source = Path(mesh).resolve()
    if source.suffix.lower() != ".obj" or not source.is_file():
        raise InputArtifactError(
            f"{source}: mark-boundaries requires an existing .obj; name the OBJ file to mark"
        )
    sidecar = boundaries_for_marking(source)
    declarations = read_boundary_declarations(sidecar)
    if declarations.fs_build is None:
        raise InputArtifactError(
            f"{sidecar}: mark-boundaries requires fs_build; "
            "state the FlightStream build in that file"
        )
    spec = read_mesh_import(sidecar)
    if spec is None:
        raise InputArtifactError(
            f"{sidecar}: mark-boundaries requires [import] units; "
            "state the mesh length unit in that file"
        )
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
        raise InputArtifactError(
            f"{sidecar}: supply boundary_faces and their total mesh_faces; for a generated "
            f"OBJ run `{_REFRESH_COMMAND.format(mesh=source)}`, which rewrites "
            "mesh_faces, boundary_faces and mesh_sha256 and keeps every other line"
        )
    if data.get("mesh_sha256") != file_sha256(source):
        raise InputArtifactError(
            f"{sidecar}: mesh_sha256 is stale; the OBJ changed after its inventory. For a "
            f"generated OBJ run `{_REFRESH_COMMAND.format(mesh=source)}`, which refreshes "
            "mesh_faces, boundary_faces and mesh_sha256 and keeps every other line"
        )
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
        if line.split() and line.split()[0] in EVIDENCE_GATED
    )
    return tuple(
        name
        for name in commands
        if (evidence := script.registry.commands[name].evidence_in(script.version)) is None
        or evidence.record.status is not Status.VERIFIED
    )


def plan_mark_boundaries(
    mesh: str | Path,
    *,
    registry: CommandRegistry | None = None,
    progress: Callable[[str], None] | None = None,
) -> BoundaryMarkingPlan:
    r"""Validate declarations and render a marking pass without writing any file.

    Parameters
    ----------
    mesh : str or Path
        OBJ with a kind-qualified or legacy boundary sidecar.
    registry : CommandRegistry, optional
        Command evidence and grammar, injectable for offline tests.
    progress : callable, optional
        Receives one line at each stage of the preview (reading, matching and placing each
        entry, rendering), so a long preview on a fine mesh is not silent (FR-3478). The
        command line prints them through the console's own progress route.

    Returns
    -------
    BoundaryMarkingPlan
        Preview, input digests and staging destinations.

    Examples
    --------
    >>> from pathlib import Path
    >>> from tempfile import TemporaryDirectory
    >>> from pyflightstream.workspace import plan_mark_boundaries
    >>> from pyflightstream.workspace.sidecars import write_inventory
    >>> with TemporaryDirectory() as folder:
    ...     mesh = Path(folder) / "wing.obj"
    ...     _ = mesh.write_text("v 0 0 0\nv 1 0 0\nv 0 1 0\ng Wing\nf 1 2 3\n")
    ...     with write_inventory(mesh).open("a") as stream:
    ...         _ = stream.write('\nfs_build = "26.125"\n[import]\nunits = "METER"\n')
    ...         _ = stream.write("[trailing_edges]\nnone = true\n")
    ...     plan = plan_mark_boundaries(mesh)
    ...     print(plan.outputs[0].name, plan.work.exists())
    wing.fsm False
    """
    say = progress or _no_progress
    say(f"reading {Path(mesh).name} and its sidecar")
    inputs = _marking_inputs(mesh)
    _, sidecar, declarations, spec, _, _ = inputs
    routes = _node_routes(sidecar, declarations, spec)
    return _plan_mark_boundaries(inputs, routes, registry, say)


def _no_progress(line: str) -> None:
    """Take a progress line and say nothing."""


def _plan_mark_boundaries(inputs, routes, registry, say=_no_progress) -> BoundaryMarkingPlan:
    """Render a preview from one validated input snapshot and node-route resolution."""
    source, sidecar, declarations, spec, names, faces = inputs
    names, faces = list(names), list(faces)
    work = _work_path(source)
    script = Script.for_marking(declarations.fs_build, registry)
    script.working_dir = str(work)
    script.emit("NEW_SIMULATION")
    declarations, pending, sets, nodes, inputs, steps = _emit_marking(
        script,
        source,
        sidecar,
        declarations=declarations,
        spec=spec,
        names=names,
        faces=faces,
        work=work,
        routes=routes,
        say=say,
    )
    say("rendering the marking script")
    emit = script.emit
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


def _mark_rims_26100(script, label, bound, *, source, spec, work, book, say=_no_progress):
    """Mark an entry on 26.100, one vertex file and one import per rim (FR-3470).

    The matched mid-points name mesh edges, which are split into rims and written as the
    vertices of each rim. A file that named two sides of a blunt trailing edge could mark the
    edges between them, so no file does, and those edges are kept (``cross_m``) for the
    read-back to prove that none was marked. An edge type other than STANDARD has no argument
    on this import, so that file is warned as not applicable and skipped.
    """
    inputs, pending, sets, steps = book
    index = _ObjEdges(source, spec.units)
    for entry in bound.sets:
        if entry.edge_type != "STANDARD":
            warn(
                f"{label}: {Path(str(entry.points_file)).name} states the edge type "
                f"{entry.edge_type}, and {VERTEX_IMPORT_ROUTE} on FlightStream "
                f"{script.version.canonical} takes no edge type, so the file is not applicable "
                "and its edges are not marked",
                NotApplicableWarning,
                stacklevel=2,
            )
            continue
        assert entry.points_file is not None
        path = Path(entry.points_file)
        inputs[str(path)] = file_sha256(path)
        say(f"{label}: splitting {len(entry.points_m)} edges into rims")
        rims, between = rim_edges(entry.points_m, source, spec.units)
        counts, crossed = [], ()
        for number, rim in enumerate(rims):
            # The edges between the rims belong to the entry; the first rim carries them.
            vertices, crossed_here = _placed_rim(
                rim, between if number == 0 else between[:0], index, spec, bound.tolerance
            )
            token = work / f"edges-{len(pending) + 1}.txt"
            mark_trailing_edge_vertices(script, node_file=str(token), vertices=vertices)
            body = script.pending_input_files[str(token)]
            pending[str(token)] = body.encode("utf-8") if isinstance(body, str) else body
            counts.append(len(vertices))
            crossed += crossed_here
        say(f"{label}: placing {len(entry.points_m)} points through the import operations")
        points = _placed_points(entry.points_m, source, spec, bound.tolerance)
        sets.append(
            {
                "label": label,
                "type": entry.edge_type,
                "file": str(path),
                "points_m": points,
                "tolerance": bound.tolerance,
                "rim_vertices": tuple(counts),
                "cross_m": crossed,
            }
        )
        steps.append(
            f"{label}: {entry.edge_type}, {len(rims)} rim file(s) of {counts} vertices, "
            f"{len(points)} trailing-edge points"
        )


def _emit_bases(emit, mark, declarations, names, steps, *, build):
    # Measured on 26.100, a six-blade wheel: a rim import between two CREATE_NEW_BASE_REGION lines
    # leaves only the last base saved, and all seven survive with every rim imported first.
    # The solver also stops the script at SET_BASE_REGION_CP <n> EMPIRICAL <cp> and accepts
    # <n> CUSTOM <cp>; CREATE_NEW_BASE_REGION has already stated the model and Cp.
    vertex_files = build == VERTEX_FILE_BUILD

    def rim(region):
        if region.trailing_edges == "auto":
            emit("SET_BASE_REGION_TRAILING_EDGES", declarations.base_regions.index(region) + 1)
        else:
            mark(region.family, region.trailing_edges)

    if vertex_files:
        for region in declarations.base_regions:
            rim(region)
    for index, region in enumerate(declarations.base_regions, 1):
        emit("CREATE_NEW_BASE_REGION", names.index(region.family) + 1, region.model, region.cp)
        if not vertex_files or region.model != "EMPIRICAL":
            emit(
                "SET_BASE_REGION_CP",
                index,
                "CUSTOM" if region.model == "USER" else region.model,
                region.cp,
            )
        if not vertex_files:
            rim(region)
        steps.append(
            f"base {region.family}: {region.model}, Cp {region.cp}, rim {region.trailing_edges}"
        )


def _emit_nodes(script, termination, explicit, *, source, spec, inputs, nodes, steps):
    if any(entry.wake_termination_nodes == "auto" for entry in termination):
        script.emit("AUTO_DETECT_WAKE_TERMINATION_NODES")
        steps.append("autodetect wake-termination nodes once")
    if explicit and script.version.canonical == VERTEX_FILE_BUILD:
        warn(
            "explicit wake-termination nodes are not applicable on FlightStream "
            f"{script.version.canonical}, whose solver has no MARK_WAKE_TERMINATION_NODES; "
            f"the nodes of {', '.join(entry.label for entry in explicit)} are not marked",
            NotApplicableWarning,
            stacklevel=2,
        )
        explicit = []
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
            script.emit("SELECT_MESH_NODE", node)
        script.emit("MARK_WAKE_TERMINATION_NODES")
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
    r"""Refuse unverified markings, stale inputs and an unapproved replacement before execution.

    Parameters
    ----------
    plan : BoundaryMarkingPlan
        Preview whose evidence, inputs and output paths are checked.
    overwrite : bool
        Whether replacement of an existing saved simulation is allowed.

    Raises
    ------
    InputArtifactError
        Evidence is missing, an input changed or output replacement is refused.

    Examples
    --------
    >>> from pathlib import Path
    >>> from tempfile import TemporaryDirectory
    >>> from pyflightstream._errors import InputArtifactError
    >>> from pyflightstream.workspace import plan_mark_boundaries, refuse_mark_boundaries
    >>> from pyflightstream.workspace.sidecars import write_inventory
    >>> with TemporaryDirectory() as folder:
    ...     mesh = Path(folder) / "wing.obj"
    ...     _ = mesh.write_text("v 0 0 0\nv 1 0 0\nv 0 1 0\ng Wing\nf 1 2 3\n")
    ...     with write_inventory(mesh).open("a") as stream:
    ...         _ = stream.write('\nfs_build = "26.125"\n[import]\nunits = "METER"\n')
    ...         _ = stream.write("[trailing_edges]\nnone = true\n")
    ...     plan = plan_mark_boundaries(mesh)
    ...     refuse_mark_boundaries(plan, overwrite=False)
    ...     _ = plan.outputs[0].write_text("")
    ...     try:
    ...         refuse_mark_boundaries(plan, overwrite=False)
    ...     except InputArtifactError as error:
    ...         print(str(error).endswith("pass overwrite=True (CLI: --overwrite) to replace it"))
    True
    """
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
    cross: dict[str, int] | None = None
    if plan.declarations.fs_build == VERTEX_FILE_BUILD:
        # One import per rim, so a unit marked from several files adds a group per extra file
        # (provisional until a probe on this build reads two imports back).
        expected += sum(len(entry["rim_vertices"]) - 1 for entry in plan.sets)
        cross = _cross_edges(plan, saved)
    if len(groups) != expected:
        raise BoundaryMarkingError(
            f"{saved}: {len(groups)} trailing-edge groups, expected {expected}"
        )
    termination = saved_termination_count(saved)
    required = len({node for values in plan.nodes.values() for node in values})
    if termination < required:
        raise BoundaryMarkingError(
            f"{saved}: {termination} termination nodes, expected at least {required}"
        )
    if termination == 0 and any(
        entry.wake_termination_nodes == "auto" for entry in plan.declarations.trailing_edges
    ):
        print(
            "warning: the autodetect marked no wake-termination node: "
            "no trailing-edge end meets another surface on this mesh"
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
    record = {
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
    if cross is not None:
        record["cross_edges"] = cross
    return record


def _cross_edges(plan: BoundaryMarkingPlan, saved: Path) -> dict[str, int]:
    """Prove that no saved trailing edge joins two rims of one blunt entry (FR-3470)."""
    counts = saved_cross_edges(plan.sets, saved)
    found = {label: number for label, number in counts.items() if number}
    if found:
        raise BoundaryMarkingError(
            f"{saved}: the saved simulation marks trailing edges that join two rims of one "
            f"entry ({', '.join(f'{label}: {number}' for label, number in found.items())}); "
            "the vertex files name one rim each, so the solver marked edges no file names"
        )
    return {entry["label"]: counts.get(entry["label"], 0) for entry in plan.sets}


def apply_mark_boundaries(
    plan: BoundaryMarkingPlan,
    *,
    runner: Callable,
    overwrite: bool = False,
    package_version: str = "unknown",
) -> dict[str, Any]:
    r"""Run once and admit all five outputs only after saved-state checks succeed.

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

    Raises
    ------
    BoundaryMarkingError
        Execution fails or the saved state does not match the declarations.

    Examples
    --------
    Running needs a licensed solver behind ``runner``. Offline, a runner that
    reports a failure shows the contract: nothing is promoted and the error
    names the staging directory to inspect.

    >>> from pathlib import Path
    >>> from tempfile import TemporaryDirectory
    >>> from types import SimpleNamespace
    >>> from pyflightstream.workspace import (
    ...     BoundaryMarkingError,
    ...     apply_mark_boundaries,
    ...     plan_mark_boundaries,
    ... )
    >>> from pyflightstream.workspace.sidecars import write_inventory
    >>> def unlicensed(script, working_directory):
    ...     return SimpleNamespace(log="", failed=True, diagnosis="no licence")
    >>> with TemporaryDirectory() as folder:
    ...     mesh = Path(folder) / "wing.obj"
    ...     _ = mesh.write_text("v 0 0 0\nv 1 0 0\nv 0 1 0\ng Wing\nf 1 2 3\n")
    ...     with write_inventory(mesh).open("a") as stream:
    ...         _ = stream.write('\nfs_build = "26.125"\n[import]\nunits = "METER"\n')
    ...         _ = stream.write("[trailing_edges]\nnone = true\n")
    ...     plan = plan_mark_boundaries(mesh)
    ...     try:
    ...         apply_mark_boundaries(plan, runner=unlicensed)
    ...     except BoundaryMarkingError as error:
    ...         print(str(error).split(";")[0])
    ...     print(plan.outputs[0].exists())
    mark-boundaries failed: no licence
    False
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


def _emit_marking(
    script, source, sidecar, *, declarations, spec, names, faces, work, routes, say=_no_progress
):
    """Emit the shared D3 import and marking pass, also used at each FSI import."""
    termination, explicit = routes
    pending: dict[str, bytes] = {}
    sets: list[dict[str, Any]] = []
    nodes: dict[str, tuple[int, ...]] = {}
    inputs = {str(source): file_sha256(source), str(sidecar): file_sha256(sidecar)}
    steps: list[str] = []

    emit = script.emit
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
        say(f"{label}: matching the points file to mesh edges")
        bound = matched_trailing_edge_sets(marking, source, spec.units)
        if script.version.canonical == VERTEX_FILE_BUILD:
            _mark_rims_26100(
                script,
                label,
                bound,
                source=source,
                spec=spec,
                work=work,
                book=(inputs, pending, sets, steps),
                say=say,
            )
            return
        entry = bound.sets[0]
        assert entry.points_file is not None
        path = Path(entry.points_file)
        inputs[str(path)] = file_sha256(path)
        token = work / f"edges-{len(sets) + 1}.txt"
        say(f"{label}: placing {len(entry.points_m)} points through the import operations")
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
    say("base regions")
    _emit_bases(emit, mark, declarations, names, steps, build=script.version.canonical)
    say("wake-termination nodes and merges")
    _emit_nodes(
        script,
        termination,
        explicit,
        source=source,
        spec=spec,
        inputs=inputs,
        nodes=nodes,
        steps=steps,
    )
    _emit_merges(emit, declarations, names, faces, steps)
    return declarations, pending, sets, nodes, inputs, steps


def _bind_fsi_marking(case):
    """Bind strict D2 inputs and inject D3 emission without a reverse layer import."""
    from functools import partial

    source, sidecar, declarations, spec, names, _ = _marking_inputs(case.geometry)
    _node_routes(sidecar, declarations, spec)
    case = case.model_copy(
        update={
            "inventory": tuple(names),
            "inventory_source": "sidecar",
            "boundaries_file": str(sidecar),
            "mesh_import": spec,
        }
    )
    case._fsi_geometry_emitter = partial(_emit_fsi_marking, source)
    return case


def _emit_fsi_marking(source, imported_mesh, script):
    """Reload declarations at each import and read the planner's verified command gate.

    A marking command documented and not verified on the row's build is warned,
    naming the commands and the build, and emitted (FR-3404): the build's
    database has not judged it, which a probe on that build settles; a command
    the build does not have is still refused by the emitter.
    """
    inputs = _marking_inputs(source)
    source, sidecar, declarations, spec, names, faces = inputs
    routes = _node_routes(sidecar, declarations, spec)
    if resolve(declarations.fs_build) != script.version:
        raise InputArtifactError(f"{sidecar}: FSI fs_build must match the row build")
    # The marking phase is scoped to the import; the ordinary solver phase guard resumes.
    preview = _plan_mark_boundaries(inputs, routes, script.registry)
    if preview.awaiting_evidence:
        warn(
            f"{sidecar.name}: the FSI boundary marking emits "
            f"{', '.join(preview.awaiting_evidence)}, documented and not verified on "
            f"FlightStream {script.version.canonical} in the command database; no probe on "
            "that build has judged them yet.",
            PyflightstreamWarning,
            stacklevel=2,
        )
    imported = Path(imported_mesh)
    if file_sha256(imported) != file_sha256(source):
        raise InputArtifactError(f"{imported}: staged FSI mesh differs from its declared source")
    with helpers.marking_import(script):
        _emit_marking(
            script,
            imported,
            sidecar,
            declarations=declarations,
            spec=spec,
            names=names,
            faces=faces,
            work=Path("."),
            routes=routes,
        )
