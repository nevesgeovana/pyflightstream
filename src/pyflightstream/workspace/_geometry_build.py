"""Building a geometry from its instruction: preview, one solver run, read-back (FR-471).

Pipeline role: the workspace row. :func:`plan_geometry_build` finds the
instruction a target names, reads it, resolves the build and renders one script
per geometry (one per angle of a ``[sweep]``), running nothing;
:func:`apply_geometry_build` runs each script once through the runner the
command line hands it (the run layer owns the executor; this module never
imports it), in ``<folder>.partial/``, then reads the saved file back, audits
the exported mesh, writes the preview and the record, and only then moves the
outputs into place.

Exit codes of the command (FR-471 R8): 0 built and audited, 1 built with a
failed audit gate, 2 refused with nothing written (:class:`InputArtifactError`),
3 the solver or the read-back failed with nothing promoted
(:class:`GeometryBuildError`).
"""

from __future__ import annotations

import getpass
import json
import os
import shutil
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, NamedTuple

from pyflightstream import _textio
from pyflightstream._digest import file_sha256
from pyflightstream._errors import InputArtifactError, PyflightstreamError
from pyflightstream._fsm import (
    MeshReadError,
    boundary_names,
    mesh_face_counts,
    saved_mesh_coordinate_unit,
    trailing_edge_midpoints,
)
from pyflightstream.cases._geometry_emit import GeometryScript, render_geometry_script
from pyflightstream.cases._geometry_instruction import (
    BUILD_RECORD_SUFFIX,
    GEOMETRY_PAGE,
    INSTRUCTION_SUFFIX,
    GeometryInstruction,
    variant_tag,
)
from pyflightstream.commands import CommandRegistry
from pyflightstream.versions import resolve
from pyflightstream.workspace._geometry_instruction import (
    checked_trailing_edge_points,
    read_geometry_instruction,
    refuse_foreign_source_names,
    refuse_moved_nodes,
)
from pyflightstream.workspace._geometry_vtk import PREVIEW_SUFFIX, write_preview_vtk
from pyflightstream.workspace._refine._audit import audit_mesh
from pyflightstream.workspace.builds import resolve_build

__all__ = [
    "BUILD_RECORD_SUFFIX",
    "BUILD_SCHEMA_VERSION",
    "GeometryBuildError",
    "GeometryBuildPlan",
    "GeometryBuilt",
    "GeometryVariant",
    "SolverOutcome",
    "accept_geometries",
    "apply_geometry_build",
    "plan_geometry_build",
    "refuse_before_running",
]


#: The schema of the record; a key removed or retyped needs a new one.
BUILD_SCHEMA_VERSION = 1
#: The folder a build works in, beside the folder it builds into.
PARTIAL_SUFFIX = ".partial"

_PAGE = GEOMETRY_PAGE


class GeometryBuildError(PyflightstreamError, RuntimeError):
    """The solver failed, or the saved body is not the one the instruction states (exit 3).

    Nothing is promoted; the partial folder is kept with the script and the log.
    """


class SolverOutcome(NamedTuple):
    """What one solver execution returned, as the runner reports it."""

    failed: bool
    return_code: int | None
    wall_s: float
    log: str
    diagnosis: str
    executable: str = ""


Runner = Callable[[Path, Path], SolverOutcome]


@dataclass(frozen=True)
class GeometryVariant:
    """One geometry of a build: the base, or one angle of a sweep."""

    tag: str | None
    angle_deg: float | None
    instruction: GeometryInstruction
    folder: Path
    script: GeometryScript
    trailing_edge_points: tuple[tuple[float, float, float], ...] = ()


@dataclass(frozen=True)
class GeometryBuildPlan:
    """What a build would do: the instruction, the build, one script per geometry."""

    path: Path
    instruction: GeometryInstruction
    root: Path
    build_id: str
    version: str
    variants: tuple[GeometryVariant, ...]
    inputs: tuple[dict[str, str], ...]

    @property
    def awaiting_evidence(self) -> tuple[str, ...]:
        """The gated commands the build needs and the database does not record verified."""
        found: list[str] = []
        for variant in self.variants:
            found += [name for name in variant.script.awaiting_evidence if name not in found]
        return tuple(found)


@dataclass(frozen=True)
class GeometryBuilt:
    """One built geometry: where it went, its record and its audit verdict."""

    folder: Path
    record: Path
    passed: bool
    failed_gates: tuple[str, ...] = ()
    files: tuple[Path, ...] = field(default_factory=tuple)


def _refuse(text: str) -> InputArtifactError:
    return InputArtifactError(f"{text} ({_PAGE}).", kind="geometry")


def _instructions_in(folder: Path) -> list[Path]:
    return sorted(path for path in folder.glob(f"*{INSTRUCTION_SUFFIX}") if path.is_file())


def locate_instruction(target: str | Path | None, cwd: Path) -> tuple[Path, bool]:
    """Return the instruction a target names and whether the command runs from the level above.

    Raises
    ------
    InputArtifactError
        No target from the level above; a folder holding no instruction or two;
        an instruction outside ``inputs/geometries/`` of a workspace.
    """
    cwd = cwd.resolve()
    if target is None:
        found = _instructions_in(cwd)
        if not found:
            below = sorted(
                p for sub in cwd.iterdir() if sub.is_dir() for p in _instructions_in(sub)
            )
            if below:
                raise _refuse(
                    f"{cwd} holds no instruction itself, and its folders hold "
                    f"{', '.join(str(p.relative_to(cwd)) for p in below)}; name the one to "
                    "build, such as `pyfs-workspace geometry build "
                    f"{below[0].parent.name}`"
                )
            raise _refuse(f"{cwd} holds no {INSTRUCTION_SUFFIX} file to build")
        path = found[0] if len(found) == 1 else None
        if path is None:
            raise _refuse(
                f"{cwd} holds {len(found)} instructions ({', '.join(p.name for p in found)}); "
                "a folder holds one"
            )
    else:
        path = (cwd / target).resolve()
        if path.is_dir():
            found = _instructions_in(path)
            if len(found) != 1:
                raise _refuse(
                    f"the folder {path} holds {len(found)} instructions; a geometry folder "
                    "holds exactly one"
                )
            path = found[0]
        elif not path.is_file():
            raise _refuse(
                f"{target} is neither an instruction file nor a geometry folder under {cwd}"
            )
        elif len(_instructions_in(path.parent)) > 1:
            names = ", ".join(p.name for p in _instructions_in(path.parent))
            raise _refuse(
                f"the folder {path.parent} holds several instructions ({names}); a folder holds one"
            )
    geometries = path.parent.parent
    if geometries.name != "geometries" or geometries.parent.name != "inputs":
        raise _refuse(
            f"{path} is not in a geometry folder of a workspace; an instruction lives in "
            "inputs/geometries/<folder>/, where its build id resolves through "
            "inputs/executables.toml"
        )
    return path, cwd == geometries.resolve()


def _version_of(root: Path, build_id: str) -> str:
    try:
        registered = resolve_build(root / "inputs", build_id)
    except InputArtifactError:
        registered = None
    version = (
        registered.fs_version if registered is not None and registered.fs_version else build_id
    )
    try:
        return resolve(version).canonical
    except (ValueError, LookupError, PyflightstreamError) as error:
        raise _refuse(
            f"the build id {build_id!r} names no solver version this package knows, and "
            f"inputs/executables.toml declares none for it: {error}"
        ) from error


def _variant_instruction(instruction: GeometryInstruction, angle: float) -> GeometryInstruction:
    assert instruction.ccs is not None and instruction.sweep is not None
    surfaces = tuple(
        surface.model_copy(update={"angle_deg": angle})
        if surface.name == instruction.sweep.control_surface
        else surface
        for surface in instruction.ccs.options.control_surfaces
    )
    options = instruction.ccs.options.model_copy(update={"control_surfaces": surfaces})
    return instruction.model_copy(
        update={
            "name": f"{instruction.name}_{variant_tag(instruction.sweep.control_surface, angle)}",
            "ccs": instruction.ccs.model_copy(update={"options": options}),
            "sweep": None,
        }
    )


def _inputs(path: Path, instruction: GeometryInstruction) -> tuple[dict[str, str], ...]:
    """Return every file the build reads, with its role and sha256."""
    found = [(path, "instruction")]
    source = instruction.source_file()
    if source is not None:
        found.append((path.parent / source, instruction.kind))
    for section in instruction.create.sections if instruction.create is not None else ():
        found.append((path.parent / section.file, "section"))
    marking = instruction.trailing_edges
    if marking is not None and marking.points_file:
        found.append((Path(marking.points_file), "trailing_edges"))
    seen: dict[Path, dict[str, str]] = {}
    for file, role in found:
        named = Path(os.path.relpath(file, path.parent)).as_posix()
        seen.setdefault(file, {"file": named, "role": role, "sha256": file_sha256(file)})
    return tuple(seen.values())


def plan_geometry_build(
    target: str | Path | None = None,
    *,
    cwd: str | Path | None = None,
    build: str | None = None,
    only: Sequence[str] = (),
    registry: CommandRegistry | None = None,
) -> GeometryBuildPlan:
    """Plan one build: find, read and check the instruction, and render its scripts (FR-471 R1).

    Runs nothing and writes nothing.

    Raises
    ------
    InputArtifactError
        Every refusal of FR-470 and FR-471 R9 that needs no executable, and
        those of FR-472 R4 about where a sweep runs and which tags it builds.
    """
    path, from_above = locate_instruction(target, Path(cwd) if cwd is not None else Path.cwd())
    instruction = read_geometry_instruction(path)
    refuse_moved_nodes(instruction, path)
    refuse_foreign_source_names(instruction, path)
    points = checked_trailing_edge_points(instruction, path)
    build_id = build or instruction.fs_build
    if not build_id:
        raise _refuse(
            f"{path} states no fs_build and the command no --build; name the build id to run"
        )
    root = path.parents[3]
    version = _version_of(root, build_id)
    folder = path.parent
    work = folder.with_name(folder.name + PARTIAL_SUFFIX)
    variants: list[GeometryVariant] = []
    if instruction.sweep is None:
        if only:
            raise _refuse("--only chooses variants of a [sweep], and the instruction states none")
        script = render_geometry_script(
            instruction,
            folder=folder,
            work=work,
            version=version,
            trailing_edge_points_m=points,
            registry=registry,
        )
        variants.append(GeometryVariant(None, None, instruction, folder, script, points))
    else:
        if not from_above:
            raise _refuse(
                f"{path.name} varies {instruction.sweep.control_surface} over a [sweep], whose "
                "variants are sibling geometries; run the build from the level above: "
                f"cd .. then `pyfs-workspace geometry build {folder.name} --apply`"
            )
        tags = {
            variant_tag(instruction.sweep.control_surface, a): a
            for a in instruction.sweep.angle_deg
        }
        unknown = sorted(set(only) - set(tags))
        if unknown:
            raise _refuse(
                f"--only names {', '.join(unknown)}, and the sweep builds {', '.join(tags)}"
            )
        for tag, angle in tags.items():
            if only and tag not in only:
                continue
            variant = _variant_instruction(instruction, angle)
            out = folder.with_name(variant.name)
            script = render_geometry_script(
                variant,
                folder=folder,
                work=out.with_name(out.name + PARTIAL_SUFFIX),
                version=version,
                registry=registry,
            )
            variants.append(GeometryVariant(tag, angle, variant, out, script))
    return GeometryBuildPlan(
        path=path,
        instruction=instruction,
        root=root,
        build_id=build_id,
        version=version,
        variants=tuple(variants),
        inputs=_inputs(path, instruction),
    )


def _outputs_of(variant: GeometryVariant) -> list[Path]:
    """Return the paths a variant promotes, for the refusal of an existing one."""
    name = variant.instruction.name
    folder = variant.folder
    paths = [folder / f"{name}{BUILD_RECORD_SUFFIX}", folder / f"{name}{PREVIEW_SUFFIX}"]
    outputs = variant.instruction.outputs
    if "fsm" in outputs:
        paths.append(folder / f"{name}.fsm")
    if outputs == ("obj",):
        paths.append(folder / f"{name}.obj")
    elif "obj" in outputs:
        paths.append(folder.with_name(f"{name}_obj"))
    return paths


def _refuse_existing(plan: GeometryBuildPlan, overwrite: bool) -> None:
    """Refuse an existing output without --overwrite, and a foreign variant folder always."""
    for variant in plan.variants:
        if variant.tag is not None and variant.folder.exists():
            record = variant.folder / f"{variant.instruction.name}{BUILD_RECORD_SUFFIX}"
            ours = record.is_file() and json.loads(record.read_text(encoding="utf-8")).get(
                "instruction", {}
            ).get("file", "").endswith(plan.path.name)
            if not ours:
                raise _refuse(
                    f"the variant {variant.tag} would be built into {variant.folder}, which exists "
                    "and was not built from this instruction; rename that geometry or the "
                    "instruction"
                )
        existing = [str(path) for path in _outputs_of(variant) if path.exists()]
        if existing and not overwrite:
            raise _refuse(f"{', '.join(existing)} exist; rebuild with --overwrite to replace them")


def refuse_before_running(plan: GeometryBuildPlan, *, overwrite: bool, png: bool) -> None:
    """Refuse, before any executable is looked up, what ``--apply`` would refuse (FR-471 R9).

    Raises
    ------
    InputArtifactError
        A command awaiting evidence on the build, an existing output without
        ``overwrite``, a foreign variant folder, or ``png`` without the plot extra.
    """
    waiting = plan.awaiting_evidence
    if waiting:
        raise _refuse(
            f"the build needs {', '.join(waiting)}, which the command database does not record "
            f"as verified on FlightStream {plan.version}; a licensed probe on that build settles "
            "it, and until then the build is not run there"
        )
    _refuse_existing(plan, overwrite)
    if png:
        _require_the_plot_extra()


def apply_geometry_build(
    plan: GeometryBuildPlan,
    *,
    runner: Runner,
    overwrite: bool = False,
    png: bool = False,
    package_version: str = "",
) -> tuple[GeometryBuilt, ...]:
    """Run each geometry of a plan once, read it back, audit it and promote it (FR-471 R2 to R8).

    Raises
    ------
    InputArtifactError
        A command awaiting evidence on the build, or an existing output without
        ``overwrite``: nothing is run or written.
    GeometryBuildError
        The solver failed, or the saved boundaries or trailing edges are not
        the ones stated; nothing of that geometry is promoted.
    """
    refuse_before_running(plan, overwrite=overwrite, png=png)
    return tuple(
        _build_one(
            plan,
            variant,
            runner=runner,
            overwrite=overwrite,
            png=png,
            package_version=package_version,
        )
        for variant in plan.variants
    )


def _require_the_plot_extra() -> None:
    try:
        import matplotlib  # noqa: F401
    except ImportError as error:
        raise _refuse(
            "--png draws with the plot extra; install it with pip install pyflightstream[plot]"
        ) from error


def _build_one(
    plan: GeometryBuildPlan,
    variant: GeometryVariant,
    *,
    runner: Runner,
    overwrite: bool,
    png: bool,
    package_version: str,
) -> GeometryBuilt:
    instruction = variant.instruction
    name = instruction.name
    work = Path(variant.script.fsm).parent
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    for pending, data in variant.script.pending_files.items():
        Path(pending).write_bytes(data)
    script_path = work / f"{name}.build.txt"
    _textio.write_text(script_path, variant.script.text)
    outcome = runner(script_path, work)
    _textio.write_text(work / f"{name}.build.log", outcome.log)
    fsm, obj = Path(variant.script.fsm), Path(variant.script.obj)
    if outcome.failed or not fsm.is_file():
        raise GeometryBuildError(
            f"the build of {name} {outcome.diagnosis or 'failed'}; the saved simulation "
            f"{fsm.name} {'exists' if fsm.is_file() else 'was not written'}. Nothing was "
            f"promoted; the script and the log are kept in {work}."
        )
    saved = _read_back(variant, fsm)
    mesh_name = name if instruction.outputs == ("obj",) else f"{name}_obj"
    mesh_dir = work / "mesh"
    mesh_dir.mkdir()
    audited = _audit(
        variant,
        obj,
        mesh_dir=mesh_dir,
        mesh_name=mesh_name,
        midpoints=saved["midpoints"],
        unit=saved["unit"],
    )
    write_preview_vtk(
        work / f"{name}{PREVIEW_SUFFIX}",
        fsm=fsm,
        obj=mesh_dir / f"{mesh_name}.obj",
        names=instruction.boundaries,
    )
    if png:
        _write_png(work / f"{name}.preview.png", mesh_dir / f"{mesh_name}.obj")
    record = _record(
        plan,
        variant,
        outcome=outcome,
        saved=saved,
        audit=audited,
        script_path=script_path,
        package_version=package_version,
        fsm=fsm,
        obj=mesh_dir / f"{mesh_name}.obj",
    )
    _textio.write_json(work / f"{name}{BUILD_RECORD_SUFFIX}", record)
    files = _promote(variant, work, mesh_dir, mesh_name, overwrite)
    shutil.rmtree(work, ignore_errors=True)
    failed = tuple(record["audit"]["failed"])
    return GeometryBuilt(
        folder=variant.folder,
        record=variant.folder / f"{name}{BUILD_RECORD_SUFFIX}",
        passed=not failed,
        failed_gates=failed,
        files=files,
    )


def _read_back(variant: GeometryVariant, fsm: Path) -> dict[str, Any]:
    """Read the saved file's boundaries and trailing edges, failing on a mismatch (FR-471 R5)."""
    instruction = variant.instruction
    try:
        names = boundary_names(fsm)
    except MeshReadError as error:
        raise GeometryBuildError(
            f"{fsm.name} cannot be read back: {error}; nothing was promoted"
        ) from error
    if tuple(names or ()) != instruction.boundaries:
        raise GeometryBuildError(
            f"the saved {fsm.name} carries the boundaries "
            f"{', '.join(names or ()) or 'none'}, and the "
            f"instruction states {', '.join(instruction.boundaries)}; the body is not the one "
            "stated, so nothing was promoted. Correct the names the operations state, or the "
            "boundaries list, and build again."
        )
    try:
        midpoints: tuple[tuple[float, float, float], ...] | None = trailing_edge_midpoints(fsm)
    except MeshReadError:
        midpoints = None
    if instruction.marks_trailing_edges() and midpoints is not None and not midpoints:
        raise GeometryBuildError(
            f"the instruction marks trailing edges and the saved {fsm.name} carries none; a "
            "body without a marked trailing edge makes no wake, so nothing was promoted"
        )
    counts = mesh_face_counts(fsm)
    return {
        "boundaries": list(names or ()),
        "midpoints": midpoints,
        "faces": None if counts is None else counts[0],
        "unit": saved_mesh_coordinate_unit(fsm) or "METER",
    }


def _sidecar_text(names: Sequence[str], units: str | None, te_file: str | None) -> str:
    rows = [
        "# Written by pyfs-workspace geometry build.",
        "boundaries = [" + ", ".join(f'"{n}"' for n in names) + "]",
    ]
    if units is not None:
        rows += ["", "[import]", f'units = "{units}"']
    if te_file is not None:
        rows += ["", "[trailing_edges]", f'file = "{te_file}"']
    return "\n".join(rows) + "\n"


def _audit(
    variant: GeometryVariant,
    obj: Path,
    *,
    mesh_dir: Path,
    mesh_name: str,
    midpoints: tuple[tuple[float, float, float], ...] | None,
    unit: str,
) -> dict[str, Any]:
    """Audit the exported mesh beside the sidecar and points file a built OBJ carries (FR-426)."""
    import numpy

    from pyflightstream.workspace._refine._obj import write_te

    target = mesh_dir / f"{mesh_name}.obj"
    if not obj.is_file():
        raise GeometryBuildError(f"the build exported no {obj.name}; nothing was promoted")
    shutil.move(str(obj), target)
    te_file = None
    if midpoints:
        te_file = f"{mesh_name}.te.txt"
        write_te(mesh_dir / te_file, unit, numpy.asarray(midpoints, dtype=float))
    export_unit = variant.instruction.mesh.units if variant.instruction.mesh is not None else unit
    _textio.write_text(
        mesh_dir / f"{mesh_name}.boundaries.toml",
        _sidecar_text(variant.instruction.boundaries, export_unit, te_file),
    )
    try:
        audit = audit_mesh(target)
    except InputArtifactError as error:
        return {"file": None, "passed": False, "failed": [f"not audited: {error}"]}
    return {
        "file": f"{variant.instruction.name}.audit.json",
        "passed": audit.passed,
        "failed": [f"{item.name} on {item.family}" for item in audit.failures],
    }


def _write_png(target: Path, obj: Path) -> None:
    """Draw three orthographic views and an isometric of the exported mesh, coloured by family."""
    import matplotlib

    matplotlib.use("Agg")
    from matplotlib import pyplot

    from pyflightstream.workspace._refine._obj import read_obj

    mesh = read_obj(obj)
    figure = pyplot.figure(figsize=(10, 8))
    views = ((90, -90, "top"), (0, -90, "front"), (0, 0, "side"), (25, -60, "isometric"))
    for position, (elevation, azimuth, title) in enumerate(views, start=1):
        axes = figure.add_subplot(2, 2, position, projection="3d")
        for family, faces in mesh.families.items():
            for face in faces:
                corners = mesh.verts[list(face) + [face[0]]]
                axes.plot(corners[:, 0], corners[:, 1], corners[:, 2], linewidth=0.3, label=family)
        axes.view_init(elevation, azimuth)
        axes.set_title(title)
    figure.savefig(target, dpi=120)
    pyplot.close(figure)


def _record(
    plan: GeometryBuildPlan,
    variant: GeometryVariant,
    *,
    outcome: SolverOutcome,
    saved: dict[str, Any],
    audit: dict[str, Any],
    script_path: Path,
    package_version: str,
    fsm: Path,
    obj: Path,
) -> dict[str, Any]:
    """Return ``<name>.build.json`` (FR-471 R7)."""
    folder = variant.folder
    rel = lambda path: Path(_relative(path, folder)).as_posix()  # noqa: E731
    outputs = []
    for path, kind in ((fsm, "fsm"), (obj, "obj")):
        if kind in variant.instruction.outputs:
            outputs.append(
                {
                    "file": path.name
                    if kind == "fsm" or variant.instruction.outputs == ("obj",)
                    else f"../{obj.stem}/{obj.name}",
                    "sha256": file_sha256(path),
                    "boundaries": saved["boundaries"],
                    "faces": saved["faces"],
                    "trailing_edge_midpoints": None
                    if saved["midpoints"] is None
                    else len(saved["midpoints"]),
                }
            )
    instruction: dict[str, Any] = {"file": rel(plan.path), "sha256": file_sha256(plan.path)}
    if variant.tag is not None:
        assert plan.instruction.sweep is not None
        instruction["variant"] = {
            "control_surface": plan.instruction.sweep.control_surface,
            "angle_deg": variant.angle_deg,
        }
    return {
        "schema_version": BUILD_SCHEMA_VERSION,
        "name": variant.instruction.name,
        "package": {"version": package_version},
        "solver": {
            "build_id": plan.build_id,
            "version": plan.version,
            "executable": outcome.executable,
            "return_code": outcome.return_code,
            "wall_s": round(outcome.wall_s, 3),
        },
        "instruction": instruction,
        "inputs": [{**item, "file": rel(plan.path.parent / item["file"])} for item in plan.inputs],
        "script": {"file": script_path.name, "sha256": file_sha256(script_path)},
        "outputs": outputs,
        "audit": audit,
        "inspected": None,
    }


def _relative(path: Path, folder: Path) -> str:
    return os.path.relpath(path.resolve(), folder.resolve())


def _rebased(record: dict[str, Any], old: Path, new: Path) -> dict[str, Any]:
    """Return a record whose file paths are read from ``new`` instead of ``old``."""

    def moved(item: dict[str, Any]) -> dict[str, Any]:
        return {**item, "file": Path(_relative(old / item["file"], new)).as_posix()}

    outputs = [
        {**item, "file": Path(item["file"]).name} if item["file"].endswith(".obj") else moved(item)
        for item in record["outputs"]
    ]
    audit = {**record["audit"], "file": f"{new.name}.audit.json"}
    return {
        **record,
        "instruction": moved(record["instruction"]),
        "inputs": [moved(item) for item in record["inputs"]],
        "script": moved(record["script"]),
        "outputs": outputs,
        "audit": audit,
    }


def _move_into(sources: list[Path], folder: Path, overwrite: bool) -> list[Path]:
    """Move each existing file into a folder, replacing one there only with ``overwrite``."""
    moved = []
    for source in sources:
        if not source.is_file():
            continue
        destination = folder / source.name
        if destination.exists() and overwrite:
            destination.unlink()
        shutil.move(str(source), destination)
        moved.append(destination)
    return moved


def _promote(
    variant: GeometryVariant, work: Path, mesh_dir: Path, mesh_name: str, overwrite: bool
) -> tuple[Path, ...]:
    """Move the built files into place, and a mesh beside an FSM into its own folder."""
    name = variant.instruction.name
    folder = variant.folder
    folder.mkdir(parents=True, exist_ok=True)
    suffixes = [".build.txt", ".build.log", PREVIEW_SUFFIX, BUILD_RECORD_SUFFIX, ".preview.png"]
    audit = mesh_dir / f"{mesh_name}.audit.json"
    if audit.is_file():
        shutil.copyfile(audit, work / f"{name}.audit.json")
        suffixes.append(".audit.json")
    if "fsm" in variant.instruction.outputs:
        _textio.write_text(
            work / f"{name}.boundaries.toml",
            _sidecar_text(variant.instruction.boundaries, None, None),
        )
        suffixes += [".fsm", ".boundaries.toml"]
    moved = _move_into([work / f"{name}{suffix}" for suffix in suffixes], folder, overwrite)
    return tuple(moved + _promote_mesh(variant, mesh_dir, mesh_name, overwrite))


def _promote_mesh(
    variant: GeometryVariant, mesh_dir: Path, mesh_name: str, overwrite: bool
) -> list[Path]:
    """Move the built mesh: into the folder when it is the one output, else into ``<name>_obj/``."""
    folder = variant.folder
    if variant.instruction.outputs == ("obj",):
        sources = [s for s in sorted(mesh_dir.iterdir()) if not s.name.endswith(".audit.json")]
        return _move_into(sources, folder, overwrite)
    if "obj" not in variant.instruction.outputs:
        return []
    target = folder.with_name(mesh_name)
    if target.exists() and overwrite:
        shutil.rmtree(target)
    shutil.move(str(mesh_dir), target)
    name = variant.instruction.name
    record = json.loads((folder / f"{name}{BUILD_RECORD_SUFFIX}").read_text(encoding="utf-8"))
    _textio.write_json(
        target / f"{mesh_name}{BUILD_RECORD_SUFFIX}", _rebased(record, folder, target)
    )
    return [target]


def accept_geometries(
    names: Sequence[str], *, geometries: Path, by: str | None = None
) -> tuple[Path, ...]:
    """Record the inspection of built geometries in their records (FR-473 R1).

    Parameters
    ----------
    names : sequence of str
        Geometry names: a folder of ``geometries`` (``wing``, ``wing_AIL+100``).
    geometries : Path
        The ``inputs/geometries`` folder.
    by : str, optional
        Who inspected; the session's user name by default.

    Raises
    ------
    InputArtifactError
        A name with no build record; nothing is written.
    """
    records = []
    for name in names:
        record = geometries / name / f"{name}{BUILD_RECORD_SUFFIX}"
        if not record.is_file():
            found = (
                sorted((geometries / name).glob(f"*{BUILD_RECORD_SUFFIX}"))
                if (geometries / name).is_dir()
                else []
            )
            if len(found) != 1:
                raise _refuse(
                    f"{name} has no {BUILD_RECORD_SUFFIX} in {geometries / name}; only a built "
                    "geometry is accepted. Nothing was written"
                )
            record = found[0]
        records.append(record)
    stamp = {
        "at": datetime.now(UTC).isoformat(timespec="seconds"),
        "by": by or getpass.getuser(),
    }
    for record in records:
        data = json.loads(record.read_text(encoding="utf-8"))
        data["inspected"] = stamp
        _textio.write_json(record, data)
    return tuple(records)
