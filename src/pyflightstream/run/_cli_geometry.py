"""The ``pyfs-workspace geometry`` command group (FR-471 to FR-477).

Pipeline role: the run row, because ``build --apply`` runs the solver and the
executor is the run layer's. The group is registered into ``pyfs-workspace``
at import (:func:`pyflightstream.workspace.cli.register_command_group`), the
way the post stages are registered, so the workspace layer never imports this
one. The work itself is the workspace layer's:
:mod:`pyflightstream.workspace._geometry_build` plans, builds, reads back and
records, :mod:`pyflightstream.workspace._geometry_convert` converts a sidecar.

``refine``, ``audit``, ``inventory`` and ``degenerate`` are the parsers and the
handlers of ``pyfs-matrix refine``, ``audit-mesh``, ``inventory`` and
``degenerate``, unchanged (FR-477): the parsers are copied as parents, the
handler is the one ``pyfs-matrix`` runs.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import tempfile
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from pyflightstream._deprecations import MATRIX_GEOMETRY_ALIASES
from pyflightstream._errors import InputArtifactError, PyflightstreamError
from pyflightstream.run._cli_mesh import (
    add_degenerate_parser,
    add_inventory_parser,
    add_mesh_parsers,
)
from pyflightstream.run._executors import (
    ExecutorConfigurationError,
    LocalExecutor,
    SurfaceMeshExportError,
    _surface_mesh_script,
    export_surface_mesh,
)
from pyflightstream.script import Script
from pyflightstream.versions import resolve
from pyflightstream.workspace import (
    BoundaryMarkingError,
    apply_mark_boundaries,
    plan_mark_boundaries,
    refuse_mark_boundaries,
)
from pyflightstream.workspace._geometry_build import (
    GeometryBuildError,
    GeometryBuildPlan,
    SolverOutcome,
    accept_geometries,
    apply_geometry_build,
    plan_geometry_build,
    plan_surface_mesh_export,
    refuse_before_running,
)
from pyflightstream.workspace._geometry_convert import (
    conversion_lines,
    instruction_from_sidecar,
    rows_for_built_geometries,
)
from pyflightstream.workspace.builds import resolve_build
from pyflightstream.workspace.cli import register_command_group
from pyflightstream.workspace.trailing_edges import DEFAULT_SECTIONS

__all__ = [
    "GEOMETRY_VERBS",
    "PYFS_MATRIX_ALIASES",
    "add_geometry_commands",
    "alias_warning",
    "matrix_parsers",
    "run_geometry",
]

#: The verbs of ``pyfs-matrix`` that join the group, by their name in the group.
PYFS_MATRIX_ALIASES = {
    "refine": "refine",
    "audit": "audit-mesh",
    "inventory": "inventory",
    "degenerate": "degenerate",
}

#: Every verb of the group.
GEOMETRY_VERBS = (
    "mark-boundaries",
    "build",
    "accept",
    "from-sidecar",
    "trailing-edge",
    "export-surface-mesh",
    *PYFS_MATRIX_ALIASES,
)

#: How long one build may run; a build makes a body and solves nothing.
_TIMEOUT_S = 1800.0

_NOTHING = "Nothing was written."


def matrix_parsers() -> dict[str, argparse.ArgumentParser]:
    """Return the four ``pyfs-matrix`` geometry parsers, built afresh, to copy as parents."""
    holder = argparse.ArgumentParser(add_help=False)
    sub = holder.add_subparsers(dest="subcommand")
    add_mesh_parsers(sub)
    add_inventory_parser(sub)
    add_degenerate_parser(sub)
    return dict(sub.choices)


def add_geometry_commands(subparsers: Any) -> None:
    """Add ``pyfs-workspace geometry`` and its verbs to a subparsers action."""
    geometry = subparsers.add_parser(
        "geometry",
        help="build a geometry from its instruction file, and inspect or refine a mesh",
        description=(
            "Builds a body outside the run matrix from <name>.geometry.toml, previewing by "
            "default and running the solver once with --apply; accepts a built body after "
            "inspection; writes the instruction of a geometry a matrix builds in the row; "
            "and refines, audits, inventories and derives meshes (docs/geometry.md)."
        ),
    )
    verbs = geometry.add_subparsers(dest="geometry_command", required=True)
    marking = verbs.add_parser(
        "mark-boundaries", help="mark an OBJ's declared boundaries into an FSM"
    )
    marking.add_argument("mesh", metavar="OBJ")
    marking.add_argument("--apply", action="store_true")
    marking.add_argument("--overwrite", action="store_true")
    marking.add_argument("--fs-exe", metavar="PATH")
    export = verbs.add_parser(
        "export-surface-mesh",
        help="preview a saved body's surface export for probes, or run it with --apply",
        description=(
            "Exports all surfaces of a saved workspace .fsm to <stem>.surface.stl beside it, "
            "where probe planning reads them. Preview prints the script and target without "
            "running or writing. --apply needs a licensed solver. Existing meshes require "
            "--overwrite; a failed export preserves them. See docs/geometry.md."
        ),
    )
    export.add_argument("target", metavar="FSM", help="saved file under inputs/geometries")
    export.add_argument("--build", metavar="ID", help="build id, over the instruction's fs_build")
    export.add_argument("--fs-exe", metavar="PATH", help="executable, over the registry")
    export.add_argument("--apply", action="store_true", help="run the solver and export the mesh")
    export.add_argument("--overwrite", action="store_true", help="replace an existing surface mesh")
    edge = verbs.add_parser("trailing-edge", help="extract trailing-edge midpoint coordinates")
    edge.add_argument("mesh", nargs="?")
    edge.add_argument("output", nargs="?")
    edge.add_argument("--from-nodes", help="ordered ANSA SET node-window export; no mesh needed")
    edge.add_argument("--out", help="destination for --from-nodes; default: <input stem>.te.txt")
    edge.add_argument("--axis", nargs=3, type=float)
    edge.add_argument("--hub", nargs=3, type=float)
    edge.add_argument("--unit", help="coordinate unit; METER by default for --from-nodes")
    edge.add_argument("--sections", type=int)
    edge.add_argument("--overwrite", action="store_true")
    midnodes = verbs.add_parser(
        "convert2midnodes",
        help="write a .te.txt from an ANSA SET node list, in any node order; no mesh needed",
        description=(
            "Reads the node list ANSA saves from a SET (Id, Name, X, Y, Z), puts the nodes in "
            "order along their lines (a long jump starts a new line, so one list may hold "
            "every trailing edge) and writes one mid-point per neighbouring pair."
        ),
    )
    midnodes.add_argument("nodes", metavar="NODES", help="the node list saved from the SET")
    midnodes.add_argument("output", metavar="OUTPUT", help="the .te.txt to write")
    midnodes.add_argument("--unit", default="METER", help="the coordinates' unit (default: METER)")
    midnodes.add_argument("--overwrite", action="store_true", help="replace an existing OUTPUT")
    midnodes.add_argument(
        "--per-family",
        metavar="MESH",
        help="the OBJ the nodes belong to: write <OUTPUT stem>.<family>.te.txt per family from "
        "its edges joining two listed nodes, in place of OUTPUT",
    )
    identify = verbs.add_parser(
        "identify-te",
        help="find the trailing edges of an OBJ and write them in the solver's node-file format",
        description=(
            "A trailing edge is a family's rearmost line: the edges its surface lies forward of. "
            "Without NODES they are found from the mesh alone (each family cut at its sharp "
            "edges, an edge kept when it makes --min-angle or more with the xz plane) and the "
            "nodes are also written as <mesh stem>.nodes.txt, the ANSA node list a refine file "
            "reads. With "
            "NODES (an ANSA SET node list, every perimeter in one file, any order) they are "
            "taken among its lines, on the OBJ or a refined level of it. Written beside the "
            "mesh in the format the solver imports: <mesh stem>.nodes.te.txt for every family, "
            "or <mesh stem>.<family>.fs.te.txt per family with --families."
        ),
    )
    identify.add_argument("mesh", metavar="OBJ", help="the mesh, with its families")
    identify.add_argument(
        "nodes",
        metavar="NODES",
        nargs="?",
        help="the node list saved from the SET (default: the edges are found from the mesh)",
    )
    identify.add_argument(
        "--families",
        metavar="A,B",
        help="the families, one file each (default: every family, in one file)",
    )
    identify.add_argument(
        "--min-angle",
        type=float,
        default=20.0,
        metavar="DEG",
        help="without NODES, the least angle of an edge with the xz plane (default 20)",
    )
    identify.add_argument(
        "--aft", nargs=3, type=float, metavar=("X", "Y", "Z"), help="the aft direction (default +x)"
    )
    identify.add_argument("--unit", help="the coordinates' unit (default: the mesh's, else METER)")
    identify.add_argument(
        "--simulation-unit", help="the unit the solver reads the file in (default: --unit)"
    )
    identify.add_argument("--overwrite", action="store_true", help="replace existing files")
    prepare = verbs.add_parser(
        "prepare-to-refine",
        help="split an OBJ's families into grid and mixed patches and write a refine file for them",
        description=(
            "Optional step before refine. Writes beside the mesh <stem>_patches.obj (each family "
            "cut into <family>_<NNN>_grid or _mixed patches, numbered within the family from the "
            "largest extent along y), <stem>_patches.refine.toml (each patch at factor 1, grid "
            "or remesh, [components] putting each family back together) and "
            "<stem>_patches.nodes.txt (the rearmost line of each grid patch, its edges at "
            "--min-angle or more from the xz plane, as an ANSA SET node list)."
        ),
    )
    prepare.add_argument("mesh", metavar="OBJ", help="the source mesh; it is not modified")
    prepare.add_argument(
        "--min-angle",
        type=float,
        default=20.0,
        metavar="DEG",
        help="the least angle of a listed edge with the xz plane (default 20)",
    )
    prepare.add_argument(
        "--aft", nargs=3, type=float, metavar=("X", "Y", "Z"), help="the aft direction (default +x)"
    )
    prepare.add_argument("--overwrite", action="store_true", help="replace the prepared files")
    build = verbs.add_parser(
        "build",
        help="preview a geometry's build, or run it with --apply",
        description=(
            "Reads <name>.geometry.toml (the one of the current folder, or of the folder or "
            "file TARGET names) and prints the script, the boundaries after each step and "
            "what would be written. With --apply it runs the solver once with no solve, saves "
            "the body, reads it back, audits it, and writes the preview and the record. Exit "
            "0 built, 1 built with a failed audit gate, 2 refused, 3 the solver or the "
            "read-back failed."
        ),
    )
    build.add_argument(
        "target", nargs="?", metavar="TARGET", help="an instruction file or a geometry folder"
    )
    build.add_argument("--apply", action="store_true", help="run the solver and write the geometry")
    build.add_argument(
        "--build", metavar="ID", help="the build id, over the instruction's fs_build"
    )
    build.add_argument(
        "--fs-exe", dest="fs_exe", metavar="PATH", help="the executable, over the registry"
    )
    build.add_argument(
        "--png", action="store_true", help="also draw <name>.preview.png (the plot extra)"
    )
    build.add_argument(
        "--overwrite",
        action="store_true",
        help="replace the outputs of an earlier build. Unlike post, a build refuses to replace "
        "outputs unless asked: its outputs are inputs of runs",
    )
    build.add_argument(
        "--only",
        metavar="TAG[,TAG...]",
        help="build only these variants of a [sweep], such as AIL+100",
    )
    build.add_argument(
        "--parallel",
        type=int,
        default=1,
        metavar="N",
        help="run up to N variants of a [sweep] at once, 1 or 2 (default: 1); a variant "
        "that fails beside another is run again alone",
    )
    build.add_argument(
        "--rows",
        metavar="POL",
        help="print, per built geometry, the row POL of --matrix with its CONFIGURATION, "
        "GEOMETRY and POL cells set for it; nothing is written into the matrix",
    )
    build.add_argument("--matrix", metavar="FILE", help="the run matrix --rows copies from")
    accept = verbs.add_parser(
        "accept",
        help="record that a built geometry was inspected",
        description="Writes who and when into each named geometry's <name>.build.json.",
    )
    accept.add_argument(
        "names", metavar="NAME[,NAME...]", help="geometry folders of inputs/geometries"
    )
    accept.add_argument(
        "--workspace", default=".", help="the workspace root (default: the current directory)"
    )
    convert = verbs.add_parser(
        "from-sidecar",
        help="write the instruction of a geometry a matrix builds in the row",
        description=(
            "Reads the sidecar of a CCS, IGES or raw-mesh geometry of inputs/geometries and "
            "prints the instruction file that builds the same body; --apply writes it. The "
            "sidecar and the matrices are never edited."
        ),
    )
    convert.add_argument("geometry", metavar="GEOMETRY", help="the file a GEOMETRY cell names")
    convert.add_argument("--apply", action="store_true", help="write <stem>.geometry.toml")
    convert.add_argument("--build", metavar="ID", help="the build id; else the rows' newest")
    convert.add_argument(
        "--workspace", default=".", help="the workspace root (default: the current directory)"
    )
    for verb, source in matrix_parsers().items():
        name = next(
            (group for group, matrix in PYFS_MATRIX_ALIASES.items() if matrix == verb), None
        )
        if name is None:
            continue
        verbs.add_parser(
            name,
            parents=[source],
            add_help=False,
            help=f"as pyfs-matrix {verb}, whose home this group is",
            description=source.description,
        )


def _package_version() -> str:
    try:
        return version("pyflightstream")
    except PackageNotFoundError:
        return "unknown"


def _print_plan(plan: GeometryBuildPlan) -> None:
    for variant in plan.variants:
        title = variant.instruction.name + (f" (variant {variant.tag})" if variant.tag else "")
        print(f"geometry {title} on build {plan.build_id} (FlightStream {plan.version})")
        for label, names in variant.script.steps:
            print(f"  after {label}: {', '.join(names)}")
        print(f"  writes into {variant.folder}")
        if variant.tag is not None:
            print(
                f"  matrix cells: CONFIGURATION {variant.tag} | GEOMETRY {_geometry_cell(variant)}"
            )
        print("  script:")
        for line in variant.script.text.splitlines():
            print(f"    {line}")
    if plan.awaiting_evidence:
        print(
            f"refused with --apply on FlightStream {plan.version}: "
            f"{', '.join(plan.awaiting_evidence)} "
            "awaits a licensed probe on that build (the command database records it unverified)"
        )


def _runner(executable: Path):  # noqa: ANN202
    executor = LocalExecutor(executable)

    def run(script: Path, work: Path) -> SolverOutcome:
        result = executor.run_script(script, working_dir=work, timeout_s=_TIMEOUT_S)
        log = "\n".join(text for text in (result.log_text, result.stdout, result.stderr) if text)
        return SolverOutcome(
            failed=result.failed,
            return_code=result.return_code,
            wall_s=result.wall_time_s,
            log=log,
            diagnosis="failed: " + result.diagnosis() if result.failed else "",
            executable=str(executable),
        )

    return run


def _geometry_cell(variant: Any) -> str:
    """Return the promoted filename a matrix GEOMETRY cell can name."""
    extension = "fsm" if "fsm" in variant.instruction.outputs else "obj"
    return f"{variant.instruction.name}.{extension}"


def _print_rows(plan: GeometryBuildPlan, args: argparse.Namespace) -> None:
    """Print the matrix rows of --rows (FR-1116); refuse --rows without --matrix."""
    if args.rows is None and args.matrix is None:
        return
    if args.rows is None or args.matrix is None:
        raise InputArtifactError(
            "--rows needs --matrix FILE, and --matrix needs --rows POL; give both or neither."
        )
    cells = [
        (
            variant.tag,
            _geometry_cell(variant),
        )
        for variant in plan.variants
    ]
    print(f"rows copied from POL {args.rows} of {args.matrix} (place them yourself):")
    for row in rows_for_built_geometries(args.matrix, args.rows, cells):
        print(f"  {row}")


def _cmd_build(args: argparse.Namespace) -> int:
    only = tuple(tag.strip() for tag in (args.only or "").split(",") if tag.strip())
    try:
        if args.only is not None and not only:
            # AN EMPTY --only IS A REFUSAL (F-1564): it read as no restriction, a full build.
            raise InputArtifactError(
                "--only names no variant; give TAG[,TAG...] such as AIL+100, or leave --only out "
                "to build every variant."
            )
        plan = plan_geometry_build(args.target, build=args.build, only=only)
        _print_plan(plan)
        _print_rows(plan, args)
        if not args.apply:
            print("preview only: nothing was run and nothing was written; add --apply to build")
            return 0
        refuse_before_running(plan, overwrite=args.overwrite, png=args.png)
        executable = (
            Path(args.fs_exe)
            if args.fs_exe
            else resolve_build(plan.root / "inputs", plan.build_id).fs_exe
        )
        built = apply_geometry_build(
            plan,
            runner=_runner(executable),
            overwrite=args.overwrite,
            png=args.png,
            package_version=_package_version(),
            parallel=args.parallel,
        )
    except (InputArtifactError, ExecutorConfigurationError) as error:
        print(f"{error} {_NOTHING}", file=sys.stderr)
        return 2
    except GeometryBuildError as error:
        print(str(error), file=sys.stderr)
        return 3
    status = 0
    failed = [item.record.name.removesuffix(".build.json") for item in built if not item.passed]
    for item in built:
        print(
            f"built {item.folder.name}: {item.record}; open "
            f"{item.record.with_name(item.record.name.replace('.build.json', '.preview.vtk'))} "
            "in ParaView"
        )
        for note in item.notes:
            print(f"  {note}")
        if not item.passed:
            print(
                f"  the audit failed: {', '.join(item.failed_gates)}; nothing was promoted; "
                f"built outputs are kept in {item.folder}",
                file=sys.stderr,
            )
            status = 1
        elif not item.promoted:
            print(
                f"  the audit passed, and it is not promoted: {', '.join(failed)} failed its "
                "audit, and a build promotes all its geometries or none; kept in "
                f"{item.folder} until the build passes whole",
                file=sys.stderr,
            )
            status = 1
    accepted = [item.folder.name for item in built if item.promoted]
    if accepted:
        print("accept after inspection: pyfs-workspace geometry accept " + ",".join(accepted))
    return status


def _promote_without_clobbering(exported: Path, target: Path, *, overwrite: bool) -> None:
    """Move the exported mesh to ``target``, never over a file that appeared meanwhile (F-713).

    The earlier existence check can be outrun by another export that finished first, so the
    move itself refuses to replace: a hard link fails if the name is taken. Where links are not
    supported the existence check is repeated at the move.
    """
    if overwrite:
        exported.replace(target)
        return
    taken = (
        f"{target} appeared while the export ran, so it was not replaced; use --overwrite to "
        f"replace it. The export is kept as {exported}."
    )
    try:
        os.link(exported, target)
    except FileExistsError as error:
        raise InputArtifactError(taken) from error
    except OSError:
        if target.exists():
            raise InputArtifactError(taken) from None
        exported.replace(target)
        return
    exported.unlink()


def _cmd_export_surface_mesh(args: argparse.Namespace) -> int:
    try:
        source, root, build, version_id = plan_surface_mesh_export(args.target, args.build)
        target = source.with_suffix(".surface.stl")
        work = source.with_suffix(".surface-export")
        ordinal = 1
        while work.exists():
            ordinal += 1
            work = source.with_suffix(f".surface-export.{ordinal}")
        print(f"surface mesh of {source} on build {build} (FlightStream {version_id})")
        print(f"exports to {work / 'surface_mesh.stl'}, then writes {target}")
        print(_surface_mesh_script(source, work / "surface_mesh.stl", version_id, "STL", -1))
        if target.exists() and not args.overwrite:
            if not args.apply:
                print(
                    f"preview only: nothing was run and nothing was written; {target} exists, "
                    "so --apply will refuse unless --overwrite is added"
                )
                return 0
            raise InputArtifactError(
                f"{target} exists; use --overwrite to replace the surface mesh"
            )
        if not args.apply:
            print("preview only: nothing was run and nothing was written; add --apply to export")
            return 0
        executable = (
            Path(args.fs_exe) if args.fs_exe else resolve_build(root / "inputs", build).fs_exe
        )
        executor = LocalExecutor(executable)
        work.mkdir()
        exported = export_surface_mesh(
            source,
            work,
            version=version_id,
            executor=executor,
            file_type="STL",
            timeout_s=_TIMEOUT_S,
        )
        _promote_without_clobbering(exported, target, overwrite=bool(args.overwrite))
        # Keep the script and log as evidence; the next export needs a fresh directory.
        print(f"wrote {target}; export script and logs kept in {work}")
        return 0
    except SurfaceMeshExportError as error:
        print(
            f"{error} Nothing promoted; inspect the export directory before retrying.",
            file=sys.stderr,
        )
        return 3
    except (PyflightstreamError, OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2


def _cmd_accept(args: argparse.Namespace) -> int:
    names = [name.strip() for name in args.names.split(",") if name.strip()]
    try:
        records = accept_geometries(
            names, geometries=Path(args.workspace) / "inputs" / "geometries"
        )
    except InputArtifactError as error:
        print(str(error), file=sys.stderr)
        return 2
    for record in records:
        print(f"accepted {record.parent.name}: {record}")
    return 0


def _cmd_from_sidecar(args: argparse.Namespace) -> int:
    try:
        conversion = instruction_from_sidecar(
            args.geometry, root=Path(args.workspace).resolve(), build=args.build, apply=args.apply
        )
    except InputArtifactError as error:
        print(f"{error} {_NOTHING}", file=sys.stderr)
        return 2
    print(conversion.text, end="")
    print(f"{'wrote' if args.apply else 'would write'} {conversion.path}")
    for line in conversion_lines(conversion):
        print(line)
    return 0


def _cmd_midnodes(args: argparse.Namespace) -> int:
    """Write a points file from an ANSA SET node list in any node order."""
    from pyflightstream.workspace.wake_edges import (
        write_trailing_edge_midnodes,
        write_trailing_edge_midnodes_per_family,
    )

    try:
        if args.per_family:
            paths = write_trailing_edge_midnodes_per_family(
                args.nodes, args.per_family, args.output, unit=args.unit, overwrite=args.overwrite
            )
        else:
            paths = [
                write_trailing_edge_midnodes(
                    args.nodes, args.output, unit=args.unit, overwrite=args.overwrite
                )
            ]
    except (PyflightstreamError, OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2
    for path in paths:
        print(path)
    return 0


def _cmd_identify_te(args: argparse.Namespace) -> int:
    """Write each named family's trailing edge in the solver's node-file format."""
    from pyflightstream.workspace.wake_edges import write_trailing_edges_identified

    try:
        paths = write_trailing_edges_identified(
            args.mesh,
            args.nodes,
            None
            if args.families is None
            else [n.strip() for n in args.families.split(",") if n.strip()],
            aft=args.aft or (1.0, 0.0, 0.0),
            min_angle=args.min_angle,
            unit=args.unit,
            simulation_unit=args.simulation_unit,
            overwrite=args.overwrite,
        )
    except (PyflightstreamError, OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2
    for path in paths:
        print(path)
    return 0


def _cmd_prepare_to_refine(args: argparse.Namespace) -> int:
    """Write the patches OBJ, its refine file and its node list."""
    from pyflightstream.workspace import prepare_to_refine

    try:
        x, y, z = args.aft or (1.0, 0.0, 0.0)
        prepared = prepare_to_refine(
            args.mesh, min_angle=args.min_angle, aft=(x, y, z), overwrite=args.overwrite
        )
    except (PyflightstreamError, OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2
    for family, patches in prepared.patches.items():
        print(f"{family}: {', '.join(patches)}")
    for path in (prepared.obj, prepared.config, prepared.nodes):
        print(path)
    return 0


def _cmd_trailing_edge(args: argparse.Namespace) -> int:
    """Keep the ordered-node conversion and existing mesh extraction routes explicit."""
    from pyflightstream.workspace.trailing_edges import write_trailing_edge_node_file
    from pyflightstream.workspace.wake_edges import write_trailing_edge_points_from_nodes

    try:
        if args.from_nodes:
            if any(
                value is not None
                for value in (args.mesh, args.output, args.axis, args.hub, args.sections)
            ):
                raise ValueError(
                    "--from-nodes takes no mesh, output positional, --axis, --hub or --sections; "
                    "use --out"
                )
            path = write_trailing_edge_points_from_nodes(
                args.from_nodes,
                args.out or Path(args.from_nodes).with_suffix(".te.txt"),
                unit=args.unit or "METER",
                overwrite=args.overwrite,
            )
        else:
            if args.out is not None or any(
                value is None for value in (args.mesh, args.output, args.axis, args.hub, args.unit)
            ):
                raise ValueError(
                    "mesh extraction needs mesh output --axis --hub --unit; "
                    "--out belongs to --from-nodes"
                )
            path = write_trailing_edge_node_file(
                args.mesh,
                args.output,
                axis=args.axis,
                hub=args.hub,
                unit=args.unit,
                sections=args.sections if args.sections is not None else DEFAULT_SECTIONS,
                overwrite=args.overwrite,
            )
    except (PyflightstreamError, OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2
    print(path)
    return 0


def _check_marking_executable(executable: Path, build: str, parent: Path) -> None:
    """Read the executable's banner before allowing a marking pass on that build."""
    with tempfile.TemporaryDirectory(prefix=".mark-identity-", dir=parent) as folder:
        work = Path(folder)
        script = Script(build)
        script.emit("EXPORT_LOG", str(work / "identity.log"))
        script.emit("CLOSE_FLIGHTSTREAM")
        from pyflightstream._textio import write_text

        path = work / "identity.txt"
        write_text(path, script.render())
        outcome = _runner(executable)(path, work)
        found = re.search(r"\bbuild\s*#\s*(\d+)", outcome.log, re.IGNORECASE)
        expected = resolve(build).build
        if outcome.failed or found is None or found.group(1) != expected:
            actual = found.group(1) if found else "unreadable"
            raise InputArtifactError(
                f"{executable}: build #{actual}, requested {build} (#{expected}); "
                "select the matching --fs-exe. No boundary marking ran."
            )


def _print_marking_readback(plan, readback: dict[str, Any]) -> None:
    """Print the checked marking result without changing its recorded mapping."""
    print(f"marked {plan.outputs[0]}")
    for entry in readback["entries"]:
        termination = entry["termination"] or "none"
        explicit = len(entry["explicit_nodes"])
        print(
            f"  entry {entry['label']}: type {entry['type']}, group {entry['group']}; "
            f"termination {termination}, {explicit} explicit nodes"
        )
    print(f"  termination nodes: {readback['termination_nodes']} (saved total)")
    if not readback["base_regions"]:
        print("  base regions: none")
    models = {0: "USER", 1: "EMPIRICAL", 2: "AXISYMMETRIC"}
    for index, (family, cp, model) in enumerate(readback["base_regions"]):
        group = readback["groups"][len(readback["entries"]) + index]
        print(f"  base region {family}: model {models[model]}, Cp {cp:g}, rim group {group}")
    merges = [r for r in plan.declarations.base_regions if r.merge_into is not None]
    if not merges:
        print("  merges: none")
    for region in merges:
        index = readback["boundaries"].index(region.merge_into)
        print(
            f"  merge {region.family} into {region.merge_into}: "
            f"{readback['boundary_faces'][index]} final OBJ faces"
        )
    for output in plan.outputs:
        print(f"  wrote {output}")


def _cmd_mark_boundaries(args: argparse.Namespace) -> int:
    try:
        plan = plan_mark_boundaries(args.mesh)
        print(f"mark boundaries of {plan.mesh} on {plan.declarations.fs_build}")
        for step in plan.steps:
            print(f"  {step}")
        for output in plan.outputs:
            print(f"  writes {output}")
        print(f"awaiting_evidence: {', '.join(plan.awaiting_evidence) or 'none'}")
        print(plan.script)
        if not args.apply:
            print("preview only: nothing was run and nothing was written")
            return 0
        refuse_mark_boundaries(plan, overwrite=args.overwrite)
        assert plan.declarations.fs_build is not None
        inputs = next((p for p in plan.mesh.parents if p.name == "inputs"), plan.mesh.parent)
        executable = (
            Path(args.fs_exe)
            if args.fs_exe
            else resolve_build(inputs, plan.declarations.fs_build).fs_exe
        )
        _check_marking_executable(executable, plan.declarations.fs_build, plan.mesh.parent)
        record = apply_mark_boundaries(
            plan,
            runner=_runner(executable),
            overwrite=args.overwrite,
            package_version=_package_version(),
        )
        _print_marking_readback(plan, record["read_back"])
        return 0
    except BoundaryMarkingError as error:
        print(str(error), file=sys.stderr)
        return 3
    except (PyflightstreamError, OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2


def run_geometry(args: argparse.Namespace) -> int:
    """Run the ``pyfs-workspace geometry`` verb ``args`` names and return its exit code."""
    verb = args.geometry_command
    if verb == "mark-boundaries":
        return _cmd_mark_boundaries(args)
    if verb == "export-surface-mesh":
        return _cmd_export_surface_mesh(args)
    if verb == "trailing-edge":
        return _cmd_trailing_edge(args)
    if verb == "convert2midnodes":
        return _cmd_midnodes(args)
    if verb == "identify-te":
        return _cmd_identify_te(args)
    if verb == "prepare-to-refine":
        return _cmd_prepare_to_refine(args)
    if verb == "build":
        return _cmd_build(args)
    if verb == "accept":
        return _cmd_accept(args)
    if verb == "from-sidecar":
        return _cmd_from_sidecar(args)
    # THE pyfs-matrix HANDLER ITSELF, named by the copied parser (FR-477).
    args.subcommand = PYFS_MATRIX_ALIASES[verb]
    try:
        return int(args.mesh_command(args))
    except PyflightstreamError as error:
        print(str(error), file=sys.stderr)
        return 2


def alias_warning(verb: str) -> str:
    """Return the warning a ``pyfs-matrix`` geometry verb prints once per invocation (FR-1136)."""
    group = next(name for name, matrix in PYFS_MATRIX_ALIASES.items() if matrix == verb)
    promise = next(
        entry for entry in MATRIX_GEOMETRY_ALIASES if entry.subject == f"pyfs-matrix {verb}"
    )
    return (
        f"pyfs-matrix {verb} is an alias of `pyfs-workspace geometry {group}`, the home of "
        "every geometry command; the alias gives the identical result. "
        f"{promise.message()} See docs/geometry.md."
    )


def _registered() -> None:
    """Register the group into ``pyfs-workspace`` (module import does it once)."""
    register_command_group("geometry", add_geometry_commands, run_geometry)


_registered()
