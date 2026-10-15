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
import sys
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
from pyflightstream.run._executors import ExecutorConfigurationError, LocalExecutor
from pyflightstream.workspace._geometry_build import (
    GeometryBuildError,
    GeometryBuildPlan,
    SolverOutcome,
    accept_geometries,
    apply_geometry_build,
    plan_geometry_build,
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
GEOMETRY_VERBS = ("build", "accept", "from-sidecar", "trailing-edge", *PYFS_MATRIX_ALIASES)

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
    edge = verbs.add_parser("trailing-edge", help="extract trailing-edge midpoint coordinates")
    edge.add_argument("mesh")
    edge.add_argument("output")
    edge.add_argument("--axis", nargs=3, type=float, required=True)
    edge.add_argument("--hub", nargs=3, type=float, required=True)
    edge.add_argument("--unit", required=True)
    edge.add_argument("--sections", type=int, default=DEFAULT_SECTIONS)
    edge.add_argument("--overwrite", action="store_true")
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


def run_geometry(args: argparse.Namespace) -> int:
    """Run the ``pyfs-workspace geometry`` verb ``args`` names and return its exit code."""
    verb = args.geometry_command
    if verb == "trailing-edge":
        from pyflightstream.workspace.trailing_edges import write_trailing_edge_node_file

        try:
            path = write_trailing_edge_node_file(
                args.mesh,
                args.output,
                axis=args.axis,
                hub=args.hub,
                unit=args.unit,
                sections=args.sections,
                overwrite=args.overwrite,
            )
        except (PyflightstreamError, OSError, ValueError) as error:
            print(str(error), file=sys.stderr)
            return 2
        print(path)
        return 0
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
        "every geometry command since 0.40.0; the alias gives the identical result. "
        f"{promise.message()} See docs/geometry.md."
    )


def _registered() -> None:
    """Register the group into ``pyfs-workspace`` (module import does it once)."""
    register_command_group("geometry", add_geometry_commands, run_geometry)


_registered()
