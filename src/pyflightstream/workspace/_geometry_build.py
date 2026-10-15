"""Building a geometry from its instruction: preview, one solver run, read-back (FR-471).

Pipeline role: the workspace row. :func:`plan_geometry_build` finds the
instruction a target names, reads it, resolves the build and renders one script
per geometry (one per angle of a ``[sweep]``), running nothing;
:func:`apply_geometry_build` runs each script once through the runner the
command line hands it (the run layer owns the executor; this module never
imports it), in ``<folder>.partial/``, then reads the saved file back, audits
the exported mesh, writes the preview and the record, and only then moves the
outputs into place.

THE BUILD IS ONE TRANSACTION (FR-1104, FR-1109; FR-472). Every geometry of the
plan is built and judged in its partial folder first, where it holds a record
whose every path resolves in that folder. Only when every geometry passed its
audit and the sweep overlay is written in full does anything move: each
geometry's records are withdrawn, its files moved, its record written last and
its partial folder removed after that; the overlay is published after every
geometry. So whatever stops the build, a solver, an audit, the overlay or an
interruption, no record names a file that is not beside it, no overlay claims
a geometry that was not promoted, and no built byte is lost: each file is in
its partial folder or in its geometry folder. The partial folder's ownership
record lists the destinations of a promotion under way, so a rebuild with
overwrite completes an interrupted one.

Exit codes of the command (FR-1109): 0 built, audited and promoted, 1 built
and kept in the partial folders because an audit gate failed, 2 refused with
nothing written (:class:`InputArtifactError`), 3 the solver, read-back or sweep
overlay failed (:class:`GeometryBuildError`), nothing promoted either.
"""

from __future__ import annotations

import getpass
import json
import os
import re
import shutil
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, NamedTuple

import pyflightstream._textio as _textio
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
from pyflightstream.extras import missing_extra
from pyflightstream.versions import resolve
from pyflightstream.workspace._geometry_instruction import (
    checked_trailing_edge_points,
    read_geometry_instruction,
    refuse_foreign_source_names,
    refuse_moved_nodes,
)
from pyflightstream.workspace._geometry_sidecar import carried_tables, sidecar_text
from pyflightstream.workspace._geometry_vtk import (
    PREVIEW_SUFFIX,
    SWEEP_SUFFIX,
    write_preview_vtk,
    write_sweep_vtk,
)
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
    "plan_surface_mesh_export",
    "refuse_before_running",
]


#: The schema of the record; a key removed or retyped needs a new one.
BUILD_SCHEMA_VERSION = 1
#: The folder a build works in, beside the folder it builds into.
PARTIAL_SUFFIX = ".partial"
#: The ownership record of a partial folder: the instruction that made it, and
#: the destinations of a promotion under way.
_MARKER = ".pyfs-build.json"

_PAGE = GEOMETRY_PAGE


class GeometryBuildError(PyflightstreamError, RuntimeError):
    """The solver failed, or the saved body is not the one the instruction states (exit 3).

    A solver, read-back or sweep overlay failure promotes nothing of the build.
    Partial folders are retained for diagnosis, each record true to its folder.
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
    ordinal: int | None = None


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
    """One built geometry: where it is, its record, its audit verdict and whether it was promoted.

    ``passed`` is the audit's verdict and ``promoted`` whether the geometry is in
    its geometry folder: a geometry that passed is kept in its partial folder,
    not promoted, when another geometry of the build failed its audit. Only a
    promoted geometry is accepted (FR-1120).
    """

    folder: Path
    record: Path
    passed: bool
    failed_gates: tuple[str, ...] = ()
    files: tuple[Path, ...] = field(default_factory=tuple)
    notes: tuple[str, ...] = ()
    promoted: bool = False


@dataclass(frozen=True)
class _Staged:
    """One geometry built and judged in its partial folder, not yet promoted."""

    variant: GeometryVariant
    work: Path
    mesh_dir: Path
    mesh_name: str
    #: The record of the promoted layout, written last when the geometry is promoted.
    record: dict[str, Any]
    #: What the build reports while the geometry stays in its partial folder.
    kept: GeometryBuilt


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


def plan_surface_mesh_export(target: str, build: str | None) -> tuple[Path, Path, str, str]:
    """Resolve a saved workspace body and the build, without creating files.

    Parameters
    ----------
    target : str
        Saved .fsm path under the workspace's inputs/geometries directory.
        Export retains its simulation length units and reference frame.
    build : str or None
        Explicit build id, or None to read the sibling instruction's fs_build.

    Returns
    -------
    tuple of Path, Path, str, str
        Resolved body path, workspace root, build id and canonical solver version.

    Raises
    ------
    InputArtifactError
        The saved body, workspace location or build declaration is invalid.
    """
    source = Path(target).resolve()
    if source.suffix.lower() != ".fsm" or not source.is_file():
        raise _refuse(f"{source} is not a saved .fsm geometry; name an existing saved body")
    library = next(
        (p for p in source.parents if p.name == "geometries" and p.parent.name == "inputs"),
        None,
    )
    if library is None:
        raise _refuse(f"{source} is outside inputs/geometries; name a workspace geometry")
    root = library.parent.parent
    if not build:
        instruction = source.with_suffix(INSTRUCTION_SUFFIX)
        if instruction.is_file():
            build = read_geometry_instruction(instruction).fs_build
    if not build:
        raise _refuse(
            "surface mesh export needs build (CLI: --build) or fs_build in the body's instruction"
        )
    return source, root, build, _version_of(root, build)


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
    """Plan one build: find, read and check the instruction, and render its scripts (FR-1102).

    Runs nothing and writes nothing.

    Raises
    ------
    InputArtifactError
        Every refusal of FR-470 and FR-1110 that needs no executable, and
        those of FR-1115 about where a sweep runs and which tags it builds.
    """
    path, from_above = locate_instruction(target, Path(cwd) if cwd is not None else Path.cwd())
    instruction = read_geometry_instruction(path)
    refuse_moved_nodes(instruction, path)
    refuse_foreign_source_names(instruction, path)
    points = checked_trailing_edge_points(instruction, path)
    build_id = build or instruction.fs_build
    if not build_id:
        raise _refuse(
            f"{path} states no fs_build and no build (CLI: --build); name the build id to run"
        )
    root = path.parents[3]
    version = _version_of(root, build_id)
    folder = path.parent
    work = folder.with_name(folder.name + PARTIAL_SUFFIX)
    variants: list[GeometryVariant] = []
    if instruction.sweep is None:
        if only:
            raise _refuse(
                "only (CLI: --only) chooses variants of a [sweep], and the instruction states none"
            )
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
                "variants are sibling geometries; set apply (CLI: --apply) from the level above: "
                f"cd .. then `pyfs-workspace geometry build {folder.name} --apply`"
            )
        tags = {
            variant_tag(instruction.sweep.control_surface, a): a
            for a in instruction.sweep.angle_deg
        }
        unknown = sorted(set(only) - set(tags))
        if unknown:
            raise _refuse(
                f"only (CLI: --only) names {', '.join(unknown)}, "
                f"and the sweep builds {', '.join(tags)}"
            )
        for ordinal, (tag, angle) in enumerate(tags.items(), start=1):
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
            variants.append(GeometryVariant(tag, angle, variant, out, script, ordinal=ordinal))
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
    paths = [
        folder / f"{name}{suffix}"
        for suffix in (
            BUILD_RECORD_SUFFIX,
            PREVIEW_SUFFIX,
            ".build.txt",
            ".build.log",
            ".audit.json",
            ".preview.png",
        )
    ]
    outputs = variant.instruction.outputs
    if "fsm" in outputs:
        paths += [folder / f"{name}.fsm", folder / f"{name}.boundaries.toml"]
    if outputs == ("obj",):
        paths += [folder / f"{name}{suffix}" for suffix in (".obj", ".boundaries.toml", ".te.txt")]
    elif "obj" in outputs:
        paths.append(folder.with_name(f"{name}_obj"))
    return paths


def _refuse_existing(plan: GeometryBuildPlan, overwrite: bool) -> None:
    """Refuse an existing output without --overwrite, and a foreign variant folder always."""
    overlay = plan.path.parent / f"{plan.instruction.name}{SWEEP_SUFFIX}"
    if plan.instruction.sweep is not None and overlay.exists() and not overwrite:
        raise _refuse(f"{overlay} exists; set overwrite (CLI: --overwrite) to replace it")
    for variant in plan.variants:
        work = Path(variant.script.fsm).parent
        if work.exists():
            marker = work / _MARKER
            if not _owned_instruction(marker, plan.path):
                raise _refuse(
                    f"{work} exists without this build's ownership record; "
                    "preserve it elsewhere before building"
                )
        # The destinations an interrupted promotion of this build was moving into.
        promoting = _promoting(work, plan.path)
        if "obj" in variant.instruction.outputs and variant.instruction.outputs != ("obj",):
            target = variant.folder.with_name(f"{variant.instruction.name}_obj")
            target_record = target / f"{target.name}{BUILD_RECORD_SUFFIX}"
            if (
                target.exists()
                and not promoting
                and not _owned_instruction(target_record, plan.path)
            ):
                raise _refuse(
                    f"{target} exists without this build's ownership record; "
                    "rename it before building"
                )
            if target.exists():
                owned: set[str] = set()
                if target_record.is_file():
                    old = json.loads(target_record.read_text(encoding="utf-8"))
                    owned = set(old.get("owned_files", []))
                    owned.update(Path(item["file"]).name for item in old.get("outputs", []))
                for suffix in (".obj", ".boundaries.toml", ".te.txt", ".audit.json"):
                    destination = target / f"{target.name}{suffix}"
                    if (
                        destination.exists()
                        and destination.name not in owned
                        and destination.resolve() not in promoting
                    ):
                        raise _refuse(
                            f"{destination} is not a recorded owned output; nothing was removed"
                        )
        if variant.tag is not None and variant.folder.exists():
            record = variant.folder / f"{variant.instruction.name}{BUILD_RECORD_SUFFIX}"
            ours = bool(promoting) or _owned_instruction(record, plan.path)
            if not ours:
                raise _refuse(
                    f"the variant {variant.tag} would be built into {variant.folder}, which exists "
                    "and was not built from this instruction; rename that geometry or the "
                    "instruction"
                )
        existing = [str(path) for path in _outputs_of(variant) if path.exists()]
        if existing and not overwrite:
            raise _refuse(
                f"{', '.join(existing)} exist; set overwrite (CLI: --overwrite) to replace them"
            )


def _owned_instruction(record: Path, instruction: Path) -> bool:
    """Check ownership by the resolved instruction path, never just its basename."""
    try:
        data = json.loads(record.read_text(encoding="utf-8"))
        source = data["instruction"]["file"]
        return (
            isinstance(source, str) and (record.parent / source).resolve() == instruction.resolve()
        )
    except (OSError, ValueError, KeyError, TypeError):
        return False


def _promoting(work: Path, instruction: Path) -> frozenset[Path]:
    """Return the destinations a promotion of this instruction was moving into when it stopped."""
    marker = work / _MARKER
    if not _owned_instruction(marker, instruction):
        return frozenset()
    stated = json.loads(marker.read_text(encoding="utf-8")).get("promoting", [])
    return frozenset((work / item).resolve() for item in stated if isinstance(item, str))


def refuse_before_running(plan: GeometryBuildPlan, *, overwrite: bool, png: bool) -> None:
    """Refuse, before any executable is looked up, what ``--apply`` would refuse (FR-1110).

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


#: At most this many variants run at once: the standing rule for native runs.
MAX_PARALLEL = 2

#: The free memory, in GB, below which a second variant does not start.
_MEMORY_FLOOR_GB = 0.5


def apply_geometry_build(
    plan: GeometryBuildPlan,
    *,
    runner: Runner,
    overwrite: bool = False,
    png: bool = False,
    package_version: str = "",
    parallel: int = 1,
) -> tuple[GeometryBuilt, ...]:
    """Run each geometry of a plan once, read it back, audit it and promote it (FR-1103 to FR-1109).

    ``parallel`` (1 or 2) runs up to that many variants of a sweep at once; a
    variant that fails while another runs beside it is run again alone
    (FR-1117). After a sweep, ``<name>.sweep.vtk`` overlays the swept control
    surface of every variant built (FR-1118).

    Raises
    ------
    InputArtifactError
        A command awaiting evidence on the build, an existing output without
        ``overwrite``, or ``parallel`` outside 1 to 2: nothing is run or written.
    GeometryBuildError
        The solver failed, the saved boundaries or trailing edges are not the
        ones stated, the sweep overlay could not be written, or a destination
        appeared while the build ran: nothing of the build is promoted, and
        each geometry built so far is kept in its partial folder with a record
        true to that folder. A failed audit gate is not raised: every geometry
        is returned kept, not promoted, its own verdict in ``passed``.
    """
    if not 1 <= parallel <= MAX_PARALLEL:
        raise _refuse(
            f"parallel (CLI: --parallel) {parallel}: write 1 or {MAX_PARALLEL}, "
            "the native-run limit"
        )
    refuse_before_running(plan, overwrite=overwrite, png=png)
    if plan.instruction.sweep is not None:
        # Keep the old bytes as noncurrent evidence, including after a failed run.
        target = _overlay_path(plan)
        if target.exists():
            archive = target.with_name(target.name + ".previous")
            number = 1
            while archive.exists():
                archive = target.with_name(f"{target.name}.previous.{number}")
                number += 1
            target.rename(archive)

    def build(variant: GeometryVariant) -> _Staged:
        return _build_one(
            plan,
            variant,
            runner=runner,
            png=png,
            package_version=package_version,
        )

    if parallel == 1 or len(plan.variants) < 2 or not _room_for_a_second_run():
        staged = tuple(build(variant) for variant in plan.variants)
    else:
        staged = _built_two_at_a_time(plan.variants, build, parallel)
    if any(not item.kept.passed for item in staged):
        # FR-1109: one failed gate promotes nothing of the build.
        return tuple(item.kept for item in staged)
    _verify_destinations(staged, overwrite)
    pending = _stage_the_overlay(plan, staged)
    try:
        built = tuple(_promote(plan, item, overwrite) for item in staged)
        if pending is not None:
            # Published last: the overlay exists only over a sweep promoted whole.
            os.replace(pending, _overlay_path(plan))
    finally:
        if pending is not None:
            pending.unlink(missing_ok=True)
    return built


def _room_for_a_second_run() -> bool:
    """Return whether the machine has the memory floor free; False where it cannot be read.

    ``psutil`` is not a dependency of the package (NFR-06), so a second solver run is
    started only on a measured floor: without it the builds run one at a time, and a
    warning says why.
    """
    try:
        import psutil
    except ImportError:
        import warnings

        from pyflightstream._errors import PyflightstreamWarning

        warnings.warn(
            "--parallel 2 runs the variants one at a time: free memory cannot be measured "
            "without the psutil package (pip install psutil), and a second solver run starts "
            "only above the "
            f"{_MEMORY_FLOOR_GB} GB floor.",
            PyflightstreamWarning,
            stacklevel=2,
        )
        return False
    return bool(psutil.virtual_memory().available / 2**30 >= _MEMORY_FLOOR_GB)


def _built_two_at_a_time(
    variants: Sequence[GeometryVariant],
    build: Callable[[GeometryVariant], _Staged],
    parallel: int,
) -> tuple[_Staged, ...]:
    """Build the variants ``parallel`` at a time, and each failed one again alone (FR-1117)."""
    from concurrent.futures import ThreadPoolExecutor

    done: dict[int, _Staged] = {}
    again: list[int] = []
    with ThreadPoolExecutor(max_workers=parallel) as pool:
        futures = {position: pool.submit(build, v) for position, v in enumerate(variants)}
        for position, future in futures.items():
            try:
                done[position] = future.result()
            except GeometryBuildError:
                again.append(position)
    for position in again:
        done[position] = build(variants[position])
    return tuple(done[position] for position in sorted(done))


def _overlay_path(plan: GeometryBuildPlan) -> Path:
    return plan.path.parent / f"{plan.instruction.name}{SWEEP_SUFFIX}"


def _stage_the_overlay(plan: GeometryBuildPlan, staged: Sequence[_Staged]) -> Path | None:
    """Write the sweep overlay to a pending file beside its target, before any promotion (FR-1108).

    Returns the pending file, published by the caller after every variant is
    promoted, or None for a build without a sweep.
    """
    sweep = plan.instruction.sweep
    if sweep is None:
        return None
    pairs = []
    for item in staged:
        assert item.variant.ordinal is not None
        fsm = Path(item.variant.script.fsm)
        obj = item.mesh_dir / f"{item.mesh_name}.obj"
        pairs.append((item.variant.ordinal, item.variant.tag or "", fsm, obj))
    target = _overlay_path(plan)
    pending: Path | None = None
    try:
        descriptor, filename = tempfile.mkstemp(prefix=target.name + ".pending", dir=target.parent)
        os.close(descriptor)
        pending = Path(filename)
        result = write_sweep_vtk(pending, pairs, sweep.control_surface)
        if result is None:
            raise MeshReadError("no readable variants")
    except (MeshReadError, OSError) as error:
        if pending is not None:
            pending.unlink(missing_ok=True)
        raise GeometryBuildError(
            f"the sweep overlay {target.name} could not be produced: {error}; nothing was "
            "promoted, prior variant outputs are kept, every built variant stays in its "
            "partial folder, and no current overlay exists."
        ) from error
    return pending


def _require_the_plot_extra() -> None:
    try:
        import matplotlib  # noqa: F401
    except ImportError as error:
        raise missing_extra("plot", package="matplotlib", purpose="png (CLI: --png)") from error


def _build_one(
    plan: GeometryBuildPlan,
    variant: GeometryVariant,
    *,
    runner: Runner,
    png: bool,
    package_version: str,
) -> _Staged:
    """Build and judge one geometry in its partial folder; promote nothing (FR-1104)."""
    instruction = variant.instruction
    name = instruction.name
    work = Path(variant.script.fsm).parent
    if work.exists():
        if not _owned_instruction(work / _MARKER, plan.path):
            raise _refuse(f"{work} is not owned by this build; nothing was removed")
        archive = work.with_name(work.name + ".previous")
        number = 1
        while archive.exists():
            archive = work.with_name(f"{work.name}.previous.{number}")
            number += 1
        work.rename(archive)
    work.mkdir(parents=True)
    _textio.write_json(work / _MARKER, {"instruction": {"file": _relative(plan.path, work)}})
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
    failed = tuple(audited["failed"])
    # The audit and the saved body's sidecar sit beside the record in both layouts.
    audit_file = mesh_dir / f"{mesh_name}.audit.json"
    if audit_file.is_file():
        shutil.copyfile(audit_file, work / f"{name}.audit.json")
    if "fsm" in instruction.outputs:
        _textio.write_text(
            work / f"{name}.boundaries.toml", sidecar_text(instruction.boundaries, None, None)[0]
        )
    facts: dict[str, Any] = {
        "outcome": outcome,
        "saved": saved,
        "audit": audited,
        "script_path": script_path,
        "package_version": package_version,
        "fsm": fsm,
        "obj": mesh_dir / f"{mesh_name}.obj",
    }
    kept = _record(plan, variant, **facts, retained=True)
    record_path = work / f"{name}{BUILD_RECORD_SUFFIX}"
    _textio.write_json(record_path, kept)
    return _Staged(
        variant=variant,
        work=work,
        mesh_dir=mesh_dir,
        mesh_name=mesh_name,
        record=_record(plan, variant, **facts, retained=False),
        kept=GeometryBuilt(
            folder=work,
            record=record_path,
            passed=not failed,
            failed_gates=failed,
            files=tuple(sorted(path for path in work.rglob("*") if path.is_file())),
            notes=tuple(kept["notes"]),
        ),
    )


def _read_back(variant: GeometryVariant, fsm: Path) -> dict[str, Any]:
    """Read the saved file's boundaries and trailing edges, failing on a mismatch (FR-1106)."""
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


def _carried(variant: GeometryVariant, mesh_name: str) -> dict[str, Any]:
    """Return what the rebuilt mesh's sidecar, else the [mesh] source's, carries over (FR-1111)."""
    instruction = variant.instruction
    folder = variant.folder
    built = folder / f"{mesh_name}.boundaries.toml"
    if instruction.outputs != ("obj",):
        built = folder.with_name(mesh_name) / f"{mesh_name}.boundaries.toml"
    candidates = [built]
    if instruction.mesh is not None:
        candidates.append(folder / f"{Path(instruction.mesh.file).stem}.boundaries.toml")
    return carried_tables(candidates)


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
    # The export follows the saved simulation unit, not the source import unit (RPT-170).
    export_unit = unit
    text, notes = sidecar_text(
        variant.instruction.boundaries, export_unit, te_file, _carried(variant, mesh_name)
    )
    _textio.write_text(mesh_dir / f"{mesh_name}.boundaries.toml", text)
    try:
        audit = audit_mesh(target)
    except InputArtifactError as error:
        return {"file": None, "passed": False, "failed": [f"not audited: {error}"], "notes": notes}
    return {
        "notes": notes,
        "file": f"{variant.instruction.name}.audit.json",
        "passed": audit.passed,
        "failed": [f"{item.name} on {item.family}" for item in audit.failures],
    }


def _write_png(target: Path, obj: Path) -> None:
    """Draw three orthographic views and an isometric of the exported mesh, coloured by family."""
    try:
        import matplotlib

        matplotlib.use("Agg")
        from matplotlib import pyplot
    except ImportError as error:
        raise missing_extra("plot", package="matplotlib", purpose="png (CLI: --png)") from error

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
    retained: bool = False,
) -> dict[str, Any]:
    """Return ``<name>.build.json`` (FR-1108)."""
    folder = fsm.parent if retained else variant.folder
    rel = lambda path: Path(_relative(path, folder)).as_posix()  # noqa: E731
    outputs = []
    for path, kind in ((fsm, "fsm"), (obj, "obj")):
        if kind in variant.instruction.outputs:
            outputs.append(
                {
                    "file": rel(path)
                    if retained
                    else path.name
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
        "audit": {key: value for key, value in audit.items() if key != "notes"},
        "notes": list(audit.get("notes", [])),
        "control_surfaces": _control_surfaces(variant.instruction),
        "inspected": None,
    }


def _control_surfaces(instruction: GeometryInstruction) -> list[dict[str, Any]]:
    """Return the angle of every control surface of a [ccs] wing (FR-1124)."""
    if instruction.ccs is None:
        return []
    return [
        {"name": surface.name, "angle_deg": surface.angle_deg}
        for surface in instruction.ccs.options.control_surfaces
    ]


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


def _mesh_target(item: _Staged) -> Path | None:
    """Return the mesh's own geometry folder when the build has both outputs, else None."""
    outputs = item.variant.instruction.outputs
    if "obj" in outputs and outputs != ("obj",):
        return item.variant.folder.with_name(item.mesh_name)
    return None


def _moves(item: _Staged) -> list[tuple[Path, Path]]:
    """Return each staged file with where promotion moves it, the records apart (FR-1105)."""
    variant, work, mesh_dir = item.variant, item.work, item.mesh_dir
    name = variant.instruction.name
    folder = variant.folder
    suffixes = [".build.txt", ".build.log", PREVIEW_SUFFIX, ".preview.png", ".audit.json"]
    if "fsm" in variant.instruction.outputs:
        suffixes += [".fsm", ".boundaries.toml"]
    moves = [(work / f"{name}{suffix}", folder / f"{name}{suffix}") for suffix in suffixes]
    moves = [(source, destination) for source, destination in moves if source.is_file()]
    meshes = sorted(path for path in mesh_dir.iterdir() if path.is_file())
    target = _mesh_target(item)
    if variant.instruction.outputs == ("obj",):
        moves += [(s, folder / s.name) for s in meshes if not s.name.endswith(".audit.json")]
    elif target is not None:
        moves += [(source, target / source.name) for source in meshes]
    return moves


def _records_of(item: _Staged) -> list[Path]:
    """Return the records promotion writes: the geometry's, then its mesh folder's."""
    records = [item.variant.folder / f"{item.variant.instruction.name}{BUILD_RECORD_SUFFIX}"]
    target = _mesh_target(item)
    if target is not None:
        records.append(target / f"{item.mesh_name}{BUILD_RECORD_SUFFIX}")
    return records


def _verify_destinations(staged: Sequence[_Staged], overwrite: bool) -> None:
    """Refuse, before any geometry moves, a destination that appeared while the build ran."""
    if overwrite:
        return
    for item in staged:
        for destination in [*(d for _, d in _moves(item)), *_records_of(item)]:
            if destination.exists():
                raise GeometryBuildError(
                    f"{destination} appeared while the build ran; nothing was promoted and "
                    "every built geometry is kept in its partial folder. Move it away, or set "
                    "overwrite (CLI: --overwrite), and build again."
                )


def _promote(plan: GeometryBuildPlan, item: _Staged, overwrite: bool) -> GeometryBuilt:
    """Move one staged geometry into place, its records withdrawn first and written last.

    The partial folder's ownership record names every destination first, so a
    rebuild recognises a promotion an interruption stopped; the partial folder
    is removed only after the records are in place.
    """
    work = item.work
    moves = _moves(item)
    records = _records_of(item)
    _textio.write_json(
        work / _MARKER,
        {
            "instruction": {"file": _relative(plan.path, work)},
            "promoting": [
                Path(_relative(path, work)).as_posix()
                for path in [*(d for _, d in moves), *records]
            ],
        },
    )
    for record in [*records, item.kept.record]:
        record.unlink(missing_ok=True)
    by_folder: dict[Path, list[Path]] = {}
    for source, destination in moves:
        by_folder.setdefault(destination.parent, []).append(source)
    files: list[Path] = []
    for folder, sources in by_folder.items():
        folder.mkdir(parents=True, exist_ok=True)
        files += _move_into(sources, folder, overwrite)
    target = _mesh_target(item)
    if target is not None:
        owned = [destination.name for _, destination in moves if destination.parent == target]
        _textio.write_json(
            records[1],
            {**_rebased(item.record, item.variant.folder, target), "owned_files": owned},
        )
    _textio.write_json(records[0], item.record)
    shutil.rmtree(work, ignore_errors=True)
    return GeometryBuilt(
        folder=item.variant.folder,
        record=records[0],
        passed=True,
        files=tuple([*files, *records]),
        notes=item.kept.notes,
        promoted=True,
    )


def accept_geometries(
    names: Sequence[str], *, geometries: Path, by: str | None = None
) -> tuple[Path, ...]:
    """Record the inspection of built geometries in their records (FR-1120).

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
        A name with no build record, or a partial folder (a build kept for
        diagnosis, never promoted); nothing is written.
    """
    records = []
    for name in names:
        if re.search(rf"{re.escape(PARTIAL_SUFFIX)}(\.previous(\.\d+)?)?$", name):
            raise _refuse(
                f"{name} is a partial folder: a build kept for diagnosis and never promoted, "
                "so it is not a geometry a row can name. Correct what failed and build "
                "again; only a promoted geometry is accepted. Nothing was written"
            )
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
