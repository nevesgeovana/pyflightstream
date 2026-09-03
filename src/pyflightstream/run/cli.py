"""The ``pyfs-matrix`` command line.

Pipeline role: drives the run matrix as a first-class interface
of the file-managed modality from a terminal. ``pyfs-matrix convert``
emits the native ``campaign.toml`` equivalent of a matrix (FR-11), the
canonical internal form; ``pyfs-matrix plan`` binds the matrix codes
to the workspace input library and pre-flights every point without
executing anything; ``pyfs-matrix run`` takes the same matrix all the
way to manifest records and a sweep table.

WHY THERE IS A ``run`` SUBCOMMAND NOW, since this file used to say
there deliberately was not, and a reader who finds only the new
sentence will reconstruct the old reasoning wrongly. The refusal said
that execution stays a Python-API decision because the solver quality
judgment and the recipe registry are code, not command-line strings.
Both halves of that survive here rather than being overturned: the
assessor is HARD-WIRED to
:class:`pyflightstream.run.LoadsAssessor` and no flag selects another
one, and there is NO recipe-registry option, so no function reaches
this tool from a shell. What changed is that a run no longer needs
either of them to be supplied: ``--workflow CODE=NAME`` names a run
type from this package's OWN table
(:mod:`pyflightstream.cases.workflows`), which is code, and a study
built out of those types needs no Python at all (PFS-2025.09). The
reversal is the author's decision; the reasoning it replaces is kept
above so the change reads as a decision rather than as drift.

``--recipe CODE=REFERENCE`` still points at a function of your own on
``convert`` and ``plan``, and on ``run`` too; what it may not do is
name the same code a ``--workflow`` names, which is refused before
anything is read.

WHY IT LIVES IN THE RUN LAYER, since it used to sit under ``cases`` and
the module path is the only thing about it that changed. A command line
that plans a campaign is an ORCHESTRATION surface: ``plan`` composes the
workspace input library with the campaign pre-flight, so it belongs at
or above both, and it sat two layers below what it drove. That was
invisible only because the imports were deferred into the function
bodies. It moved with the matrix hoist rather than after it, because
between the two the tree carries a module-level cases-to-run import and
no commit can be green on its own (OPS-2007.01, and the lane's own
determination of 2026-08-18).

The console entry point is unchanged: the command is still
``pyfs-matrix``, with the same subcommands, the same flags and the same
output, so FR-44's contract is untouched. What moved is the dotted
module path, which a user never writes.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pyflightstream.cases import CampaignConfigError
from pyflightstream.cases.matrix import MatrixError, convert_matrix, upgrade_matrix
from pyflightstream.cases.workflows import (
    WorkflowCoverageError,
    resolve_workflow,
    workflow_names,
    workflow_registry,
)
from pyflightstream.results import MalformedOutputError
from pyflightstream.results.tables import LoadsNotFoundError, sweep_table, write_table
from pyflightstream.run import CampaignErrors, LoadsAssessor
from pyflightstream.run.matrix import plan_matrix, run_matrix
from pyflightstream.workspace import CampaignWorkspace, InputArtifactError
from pyflightstream.workspace.naming import MATRIX_POINT_NAME, NamingTemplate, NamingTemplateError


def _parse_recipes(pairs: list[str]) -> dict[str, str]:
    """Turn repeated ``CODE=module:function`` options into the mapping."""
    recipes: dict[str, str] = {}
    for item in pairs:
        code, separator, reference = item.partition("=")
        if not separator or not code or not reference:
            raise ValueError(
                f"--recipe expects CODE=module:function (the FS_SCRIPT code and the "
                f"recipe it maps to), got {item!r}"
            )
        recipes[code.strip()] = reference.strip()
    return recipes


def _parse_workflows(pairs: list[str]) -> dict[str, str]:
    """Turn repeated ``CODE=NAME`` options into the mapping.

    Each name is resolved against the workflow table HERE, so a typo is
    refused before a file is opened rather than per point.
    """
    workflows: dict[str, str] = {}
    for item in pairs:
        code, separator, name = item.partition("=")
        if not separator or not code.strip() or not name.strip():
            # CampaignConfigError rather than a bare ValueError: FR-39 says
            # a refusal raised from an exported public name is catalogued,
            # and this one keeps ValueError as its standard-library base, so
            # `except ValueError` around main() catches exactly what it did.
            raise CampaignConfigError(
                f"--workflow expects CODE=NAME (the FS_SCRIPT code and the run type it "
                f"maps to), got {item!r}; the registered types are "
                f"{', '.join(workflow_names())}"
            )
        resolve_workflow(name.strip())
        workflows[code.strip()] = name.strip()
    return workflows


def _one_builder_per_code(recipes: dict[str, str], workflows: dict[str, str]) -> dict[str, str]:
    """Merge the two mappings, refusing a code that names both.

    The command-line face of PFS-2025.02's rule: one case builds its
    script one way. A code given both would leave which one runs to the
    order the merge happens to take.
    """
    both = sorted(set(recipes) & set(workflows))
    if both:
        listed = "; ".join(
            f"code {code}: the workflow {workflows[code]!r} and the recipe {recipes[code]!r}"
            for code in both
        )
        raise CampaignConfigError(
            f"the FS_SCRIPT code(s) {', '.join(both)} were given BOTH a --workflow and a "
            f"--recipe ({listed}). One code builds its script one way: a workflow is a "
            "run type this package builds and a recipe is a function you wrote. Drop "
            "one of the two options for each code."
        )
    return {**recipes, **workflows}


def _add_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("matrix", help="the pipe-delimited run matrix file")
    parser.add_argument(
        "--name",
        required=True,
        help="campaign name; the matrix has none, so it is explicit input",
    )
    parser.add_argument(
        "--fs-version",
        default=None,
        help="the FlightStream version rows whose FS_BUILD cell is empty fall back "
        "to: canonical identifier (for example 26.120); a vendor release name works "
        "only where it names exactly one registered build. A matrix whose every "
        "active row fills FS_BUILD needs none (PFS-2029.01)",
    )
    parser.add_argument(
        "--recipe",
        action="append",
        default=[],
        metavar="CODE=MODULE:FUNCTION",
        help="FS_SCRIPT code to recipe reference (repeatable); replaces the "
        "import-by-number system",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pyfs-matrix",
        description=(
            "Run-matrix tooling: the matrix is a first-class interface of the "
            "file-managed modality, with campaign.toml as the canonical internal form."
        ),
    )
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    # FIRST, because it is the subcommand a user meets when a matrix they
    # already have stops being readable. An independent review found the
    # only migration path was a Python call, which a matrix user is
    # precisely the person who does not write: the format broke and the
    # remedy was addressed to somebody else.
    upgrade = subparsers.add_parser(
        "upgrade",
        help=(
            "convert a matrix written under an older layout to the current one "
            "(the file converts losslessly; the RESULTS move, see --help)"
        ),
        description=_UPGRADE_NOTICE,
    )
    upgrade.add_argument("matrix", help="path of the run matrix to upgrade")
    upgrade.add_argument(
        "--in-place",
        action="store_true",
        help="rewrite the file; without it the upgraded matrix goes to standard output",
    )
    upgrade.add_argument(
        "--inputs",
        metavar="DIR",
        default=None,
        help=(
            "the workspace inputs/ directory whose groups library moves to pproc "
            "(inputs/groups/e001.toml becomes inputs/pproc/p001.toml under [groups]); "
            "needs --in-place, because the matrix cells that name the files are "
            "rewritten with them"
        ),
    )

    convert = subparsers.add_parser(
        "convert",
        help="emit the native campaign.toml equivalent of a matrix (FR-11)",
    )
    _add_common_arguments(convert)
    convert.add_argument(
        "--fs-exe",
        required=True,
        help="explicit path of the FlightStream executable (never guessed)",
    )
    convert.add_argument(
        "-o",
        "--output",
        help="write the campaign.toml here instead of standard output",
    )

    plan = subparsers.add_parser(
        "plan",
        help="bind the matrix to the workspace input library and pre-flight every "
        "point, executing nothing",
    )
    _add_common_arguments(plan)
    plan.add_argument(
        "--workflow",
        action="append",
        default=[],
        metavar="CODE=NAME",
        help="FS_SCRIPT code to WORKFLOW type (repeatable); the same mapping `run` "
        "takes, so a workflow matrix can be pre-flighted before a seat is spent",
    )
    plan.add_argument(
        "--workspace",
        default=".",
        help="managed campaign root carrying the inputs/ library (default: the current directory)",
    )
    plan.add_argument(
        "--point-name",
        default=MATRIX_POINT_NAME,
        help="the template that names each point's script and exports; the default "
        "is the author's convention, POLAR-<sim>_M<mach*100>AL<alpha*10>BE<beta*10>"
        "[J<J*100>], fixed width; {point}, {alpha}, {beta}, {mach}, {advance_ratio}, "
        "{sim} and {campaign} are the other placeholders (PFS-2029.19)",
    )
    plan.add_argument(
        "--fs-exe",
        help="explicit executable override; mandatory for MANUAL rows, otherwise the "
        "FS_BUILD column resolves through inputs/executables.toml",
    )

    run = subparsers.add_parser(
        "run",
        help="run every active point of the matrix and write the sweep table",
    )
    _add_common_arguments(run)
    run.add_argument(
        "--workflow",
        action="append",
        default=[],
        metavar="CODE=NAME",
        help="FS_SCRIPT code to WORKFLOW type (repeatable); a run type this package "
        f"builds itself, so no Python is written. Registered: {', '.join(workflow_names())}",
    )
    run.add_argument(
        "--workspace",
        default=".",
        help="managed campaign root carrying the inputs/ library (default: the current directory)",
    )
    run.add_argument(
        "--point-name",
        default=MATRIX_POINT_NAME,
        help="the template that names each point's script and exports; the default "
        "is the author's convention, POLAR-<sim>_M<mach*100>AL<alpha*10>BE<beta*10>"
        "[J<J*100>], fixed width; {point}, {alpha}, {beta}, {mach}, {advance_ratio}, "
        "{sim} and {campaign} are the other placeholders (PFS-2029.19)",
    )
    run.add_argument(
        "--fs-exe",
        help="explicit executable override; mandatory for MANUAL rows, otherwise the "
        "FS_BUILD column resolves through inputs/executables.toml",
    )
    run.add_argument(
        "--resume",
        action="store_true",
        help="skip points already in the manifest, so a grown matrix runs only its new "
        "points; without it an already-recorded point refuses before anything executes",
    )
    run.add_argument(
        "--sweep-csv",
        help="write the campaign sweep table here (default: sweep.csv in the workspace root)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run ``pyfs-matrix``; returns the process exit code."""
    args = _build_parser().parse_args(argv)
    # Before the recipe parsing below, deliberately: upgrading a file
    # needs no recipes, no version and no executable, and requiring them
    # would refuse the one user this subcommand exists for.
    if args.subcommand == "upgrade":
        return _cmd_upgrade(args)
    try:
        recipes = _parse_recipes(args.recipe)
        if args.subcommand in ("run", "plan"):
            # BOTH, since 2026-08-19. `plan` is the zero-cost rehearsal of
            # `run`, and a rehearsal that refuses what the run accepts is
            # not a rehearsal: a workflow matrix could be run and not
            # planned, so the one user who writes no Python had no way to
            # check a study before spending a licensed seat on it.
            recipes = _one_builder_per_code(recipes, _parse_workflows(args.workflow))
    except (ValueError, CampaignConfigError) as error:
        print(str(error), file=sys.stderr)
        return 2
    if args.subcommand == "convert":
        return _cmd_convert(args, recipes)
    if args.subcommand == "run":
        return _cmd_run(args, recipes)
    return _cmd_plan(args, recipes)


#: Printed by `upgrade` on both routes, because this subcommand is the
#: one point at which a user commits to the change, and a release review
#: found it was the only surface in the release carrying no warning: the
#: results-will-move paragraph was in the changelog, the docs page and
#: the guide, and in front of nobody who runs the command. This
#: subcommand exists precisely BECAUSE the previous migration path was a
#: Python call that a matrix user does not write, so it cannot assume
#: that user read any of the three.
_UPGRADE_NOTICE = (
    "The file is converted; your RESULTS are not preserved. Under v0.8.x the "
    "RE column was recorded metadata that reached no emitted line. From "
    "v0.9.0 REmi is a CONSTRAINT that solves for density, so every upgraded "
    "row emits an explicit fluid state it never emitted before and its "
    "numbers will differ. To keep the previous behaviour, state the condition "
    "without REmi. See docs/flight-conditions.md."
)


def _naming(args: argparse.Namespace) -> NamingTemplate:
    """Build the point-name template the command line was given, her convention by default."""
    try:
        return NamingTemplate(point_name=args.point_name)
    except NamingTemplateError as error:
        raise SystemExit(f"--point-name: {error}") from error


def _cmd_upgrade(args: argparse.Namespace) -> int:
    """Bring a matrix at an older layout up to the current one."""
    if args.inputs is not None and not args.in_place:
        print(
            "--inputs moves library files and rewrites the cells that name them, so it "
            "needs --in-place; without it the matrix would go to standard output naming "
            "files that no longer exist.",
            file=sys.stderr,
        )
        return 2
    try:
        upgraded = upgrade_matrix(args.matrix, in_place=args.in_place)
        if args.inputs is not None:
            from pyflightstream.workspace.inputs import InputArtifactError, migrate_groups_to_pproc

            try:
                moved = migrate_groups_to_pproc(Path(args.inputs))
            except InputArtifactError as error:
                print(str(error), file=sys.stderr)
                return 2
            for old, new in sorted(moved.items()):
                print(f"moved inputs/groups/{old}.toml to inputs/pproc/{new}.toml", file=sys.stderr)
            if not moved:
                print(f"no groups file under {args.inputs} to move", file=sys.stderr)
    except (OSError, MatrixError) as error:
        print(str(error), file=sys.stderr)
        return 2
    if args.in_place:
        print(f"upgraded {args.matrix}", file=sys.stderr)
    # On stderr on BOTH routes, so it never contaminates the bytes the
    # stdout route exists to hand back cleanly for a diff.
    print(_UPGRADE_NOTICE, file=sys.stderr)
    if args.in_place:
        return 0
    sys.stdout.buffer.write(upgraded)
    return 0


def _cmd_convert(args: argparse.Namespace, recipes: dict[str, str]) -> int:
    try:
        text = convert_matrix(
            args.matrix,
            name=args.name,
            fs_version=args.fs_version,
            fs_exe=args.fs_exe,
            recipes=recipes,
        )
    except (MatrixError, OSError, ValueError) as error:
        print(f"matrix not converted: {error}", file=sys.stderr)
        return 2
    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            handle.write(text)
        print(f"campaign written: {args.output}")
    else:
        print(text, end="")
    return 0


def _cmd_plan(args: argparse.Namespace, recipes: dict[str, str]) -> int:
    workspace = CampaignWorkspace(args.workspace, naming=_naming(args))
    try:
        plan = plan_matrix(
            args.matrix,
            workspace,
            name=args.name,
            # The keyword the library takes, not the flag the user types:
            # the parameter renamed with PFS-2009.08.01 and `--fs-version`
            # deliberately did not. Passing the old spelling here fired a
            # deprecation warning at a user who had typed a shell command
            # and named a Python keyword they never wrote.
            default_fs_version=args.fs_version,
            recipes=recipes,
            fs_exe=args.fs_exe,
            recipe_registry=workflow_registry(),
        )
    except (MatrixError, InputArtifactError, OSError, ValueError) as error:
        print(f"matrix not planned: {error}", file=sys.stderr)
        return 2
    print(plan.summary())
    if plan.plan_file is not None:
        print(f"plan: {plan.plan_file}")
    return 1 if plan.blocked else 0


def _cmd_run(args: argparse.Namespace, recipes: dict[str, str]) -> int:
    """Run every active point, then write the sweep table.

    The assessor is hard-wired and the recipe registry is this
    package's own workflow table; neither reaches this function from
    the command line, which is what keeps the author's recorded
    reasoning intact while the subcommand exists (see the module
    docstring).
    """
    workspace = CampaignWorkspace(args.workspace, naming=_naming(args))
    try:
        run_matrix(
            args.matrix,
            workspace,
            name=args.name,
            # The command line's own flag is still --fs-version, and the
            # keyword it feeds is the DEFAULT a row whose FS_BUILD names
            # no build falls back to; a row that names a build wins.
            default_fs_version=args.fs_version,
            recipes=recipes,
            assess=LoadsAssessor(),
            fs_exe=args.fs_exe,
            recipe_registry=workflow_registry(),
            resume=args.resume,
        )
    except CampaignErrors as error:
        # SEPARATED FROM THE OTHERS on purpose. Every arm below this one
        # is a refusal BEFORE the campaign ran, and leaves nothing to
        # tabulate. CampaignErrors is raised AFTER the loop, by a run
        # that executed and had failing points, and those points have
        # records. Catching it with the rest returned 2 without writing
        # anything, so a sweep with one failed point left no table at
        # all, which is the acceptance of PFS-2014.03 exactly inverted.
        print(f"matrix run with failures: {error}", file=sys.stderr)
        status = 2
    except (
        MatrixError,
        InputArtifactError,
        CampaignConfigError,
        WorkflowCoverageError,
        OSError,
        ValueError,
    ) as error:
        print(f"matrix not run: {error}", file=sys.stderr)
        return 2
    else:
        status = 0

    target = args.sweep_csv or str(workspace.root / "sweep.csv")
    try:
        # `require_loads=False` is the keyword written for exactly this
        # condition: a sweep in which no run yielded coefficients still
        # has identity rows, and printing "sweep table not written" over
        # them discards work the campaign already did. `write_table` is
        # the one write path of the tabular layer and refuses a frame
        # that cannot say what produced its numbers; `to_csv` bypassed
        # that and was correct only by coincidence.
        write_table(sweep_table(workspace, require_loads=False), target)
    except (LoadsNotFoundError, MalformedOutputError, OSError, ValueError) as error:
        print(f"runs completed, sweep table not written: {error}", file=sys.stderr)
        return 2
    print(f"sweep table: {target}")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
