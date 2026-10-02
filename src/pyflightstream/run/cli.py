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
reversal is the design decision; the reasoning it replaces is kept
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
``pyfs-matrix``, with the same subcommands and the same flags, so FR-44's contract is
untouched. The human output of ``plan`` is laid out in titled blocks since
0.31.0; its exit codes and ``plan.json`` did not change. What moved is the dotted
module path, which a user never writes.

The dispatcher of every pyfs-matrix subcommand, each command's logic beside it.
The argument parser is :mod:`pyflightstream.run._cli_parsers` (AD-14, built by family since 0.34.0
(AD-18)) and the console printing of plan and storage is :mod:`pyflightstream.run._cli_print`; what
stays is the commands themselves, which share the workspace, matrix and records helpers.
"""

from __future__ import annotations

import argparse
import sys
import warnings
from pathlib import Path
from typing import NoReturn

import pyflightstream._textio as _textio
from pyflightstream._cli import cli_entrypoint, note_post_ran, post_warning_policy
from pyflightstream._console import (
    command_help,
    held_warnings,
    release_warnings,
)
from pyflightstream._errors import PyflightstreamError, PyflightstreamWarning
from pyflightstream._progress import (
    LIVE_LOG_COMMANDS,
    command_console,
    stage_progress,
)
from pyflightstream.cases import CampaignConfigError
from pyflightstream.cases.matrix import MatrixError, convert_matrix, upgrade_matrix
from pyflightstream.cases.workflows import (
    WorkflowCoverageError,
    resolve_workflow,
    workflow_names,
    workflow_registry,
)

# Offered here by 0.32.0, whose parser read it; the parser is _cli_parsers now.
from pyflightstream.cases.workflows import read_a_choice as read_a_choice
from pyflightstream.results import MalformedOutputError
from pyflightstream.results.tables import LoadsNotFoundError, sweep_table, write_table
from pyflightstream.run import (
    SWEEP_TABLE_NAME,
    CampaignErrors,
    LoadsAssessor,
    plan_receipt_error,
)
from pyflightstream.run import records as run_records
from pyflightstream.run._cli_parsers import _build_parser
from pyflightstream.run._cli_print import (
    _print_delete_sims,
    _print_free_space,
    _print_plan,
    _print_sync,
)
from pyflightstream.run.matrix import plan_matrix, run_matrix
from pyflightstream.workspace import (
    CampaignWorkspace,
    InputArtifactError,
    RunStatus,
    WorkspaceError,
    post_diagnostics,
    selected_sims,
)
from pyflightstream.workspace._matrix_homes import resolve_matrix_arguments
from pyflightstream.workspace.matrix import renumber_repeated_pols
from pyflightstream.workspace.naming import (
    MATRIX_POINT_NAME,
    NamingTemplate,
    NamingTemplateError,
    is_portable_name,
)


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


def _listed_sims(text: str) -> list[str]:
    """Read simulation ids as ``delete-sims`` spells them: ``4001,2009`` or ``[4001,2009]``.

    The one home of that form, read by ``delete-sims``, ``rebuild --sims``,
    ``post --sims`` and ``collect --sims`` (FR-307).
    """
    listed = text.replace(" ", "").strip("[]")
    return [item for item in listed.split(",") if item]


def _confirmed_destruction(yes: bool) -> bool:
    """Ask before a product is destroyed rather than archived.

    `--force-overwrite` is named so it
    cannot be reached by habit, and it asks. `--yes` answers it, for the
    script that means it.

    A NON-INTERACTIVE SESSION IS A NO. If there is nobody to ask, the
    answer is not "assume yes": that is how a flag in a saved command line
    quietly destroys a rebuild's evidence on a machine with no terminal.
    """
    if yes:
        return True
    if not sys.stdin or not sys.stdin.isatty():
        return False
    answer = input(
        "--force-overwrite DESTROYS the products that are there and keeps no copy. "
        "The default archives them instead. Type 'destroy' to go on: "
    )
    return answer.strip().lower() == "destroy"


@cli_entrypoint
def main(argv: list[str] | None = None) -> int:
    """Run ``pyfs-matrix``; returns the process exit code.

    Parameters
    ----------
    argv : list of str, optional
        The command line without the program name; None reads
        ``sys.argv``.

    Returns
    -------
    int
        The process exit code: 0 on success, 2 for a refused argument or
        recipe, and the code the chosen subcommand returns otherwise.
    """
    parser = _build_parser()
    args = parser.parse_args(_storage_flag_form(argv))
    # THE CONSOLE CONTRACT (0.32.0, FR-200 to FR-204): a titled opening block,
    # the warnings at the end, a live log for a long command. `plan` keeps the
    # header and the warnings block of 0.31.0, after its header.
    with command_console(
        "pyfs-matrix",
        args.subcommand,
        what=command_help(parser, [args.subcommand]),
        workspace=getattr(args, "workspace", None),
        # `post --diagnostics` reads and changes no file of the workspace.
        live_log=args.subcommand in LIVE_LOG_COMMANDS and not getattr(args, "diagnostics", False),
        header=args.subcommand == "plan",
        hold=args.subcommand != "plan",
    ):
        # FR-310: every matrix argument over the two homes, before any command reads it.
        if (refused := _refuse_runs_manifest(args) or resolve_matrix_arguments(args)) is not None:
            return refused
        if args.subcommand in _RECORDS_COMMANDS:
            return _cmd_records(args)
        if args.subcommand in _STORAGE_COMMANDS:
            return _cmd_storage(args)
        # Before the recipe parsing below, deliberately: upgrading a file
        # needs no recipes, no version and no executable, and requiring them
        # would refuse the one user this subcommand exists for.
        if args.subcommand == "post":
            note_post_ran()
            return _cmd_post(args)
        if args.subcommand == "collect":
            return _cmd_collect(args)
        if args.subcommand == "inventory":
            return _cmd_inventory(args)
        if args.subcommand == "upgrade":
            return _cmd_upgrade(args)
        if args.subcommand == "rename":
            return _cmd_rename(args)
        try:
            recipes = _parse_recipes(args.recipe)
            if args.subcommand in ("run", "plan", "inspect-setups"):
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
#:
#: IT IS ABOUT THE v0.8.x LAYOUT AND NOTHING ELSE, and saying so is the
#: 0.15.0 release review's severity-one finding. It used to print on every
#: upgrade of every layout, so a user converting a 14-column file was told
#: their RESULTS ARE NOT PRESERVED by the one surface they read at the
#: moment of committing, while this release's own guarantee is the exact
#: opposite: the sweep fold carries a held angle at every point, so every
#: existing run_id resolves and a resume finds its records. A user who
#: believed the notice would discard a recorded campaign and spend a
#: licensed seat re-running it, which is the resource this whole package
#: exists to ration.
_RE_NOTICE = (
    "This file entered at the v0.8.x layout, and across that boundary your "
    "RESULTS are not preserved: the RE column was recorded metadata that "
    "reached no emitted line, and from v0.9.0 REmi is a CONSTRAINT that "
    "solves for density, so every upgraded row emits an explicit fluid state "
    "it never emitted before and its numbers will differ. To keep the "
    "previous behaviour, state the condition without REmi. See "
    "docs/flight-conditions.md."
)


#: Printed when no stage that moves a number fired, so the user is not
#: left wondering which of the two paragraphs above was withheld.
_NO_STAGE_NOTICE = (
    "The file is converted. No stage that moves a number fired, so your results stand as they are."
)

#: Printed when the fourth stage folded a SWEEP_TYPE cell, which is the
#: 0.15.0 migration. It says the OPPOSITE of the notice above, and it is
#: the sentence that stops a user re-running a campaign they still have.
_SWEEP_NOTICE = (
    "The SWEEP_TYPE column is folded into FLIGHT_CONDITION. THIS DOES NOT "
    "RENAME A RUN: a held angle is carried at every point, so the point tags "
    "that end every run_id in your manifests are the ones the converted file "
    "plans under, and a resume after this upgrade finds its records."
)


def _campaign_name(args: argparse.Namespace) -> tuple[str, str]:
    """Return the campaign name and where it came from: the option, or the workspace directory."""
    if args.name is not None:
        return args.name, "option"
    derived = Path(args.workspace).resolve().name
    if not is_portable_name(derived):
        _refuse(
            f"the workspace directory is named {derived!r}, which is not a legal campaign "
            "name (a plain token: no separators, no whitespace, not empty), and no name "
            "was given; pass name (CLI: --name) to name the campaign yourself."
        )
    return derived, "directory"


def _refuse(message: str) -> NoReturn:
    """Refuse the way every other refusal of this command line does: stderr and exit 2."""
    print(message, file=sys.stderr)
    raise SystemExit(2)


#: The storage commands of 0.30.0 (`pyflightstream.workspace.storage`).
_STORAGE_COMMANDS = ("space-in-use", "free-space", "delete-sims", "sync")


def _storage_flag_form(argv: list[str] | None) -> list[str] | None:
    """Accept the flag-form spelling, ``pyfs-matrix --workspace W --free-space m001``.

    Each storage command is also a subcommand; written as a leading flag, it
    is moved to the front and its value (the recipe, the ids or the level)
    becomes the positional argument. Anything else passes through unchanged.
    """
    tokens = list(sys.argv[1:] if argv is None else argv)
    if not tokens or not tokens[0].startswith("-") or tokens[0] in ("-h", "--help", "--version"):
        return argv
    for index, token in enumerate(tokens):
        name, _, inline = token.partition("=")
        if name[2:] not in _STORAGE_COMMANDS or not name.startswith("--"):
            continue
        rest = tokens[:index] + tokens[index + 1 :]
        if name == "--space-in-use":
            return [name[2:], *rest]
        if inline:
            return [name[2:], inline, *rest]
        if index + 1 < len(tokens):
            value = tokens[index + 1]
            return [name[2:], value, *tokens[:index], *tokens[index + 2 :]]
        return [name[2:], *rest]
    return argv


def _cmd_storage(args: argparse.Namespace) -> int:
    """Run one storage command and print what it did or would do."""
    from pyflightstream.workspace import storage

    try:
        if args.subcommand == "space-in-use":
            report = storage.space_in_use(args.workspace)
            print("\n".join(report.lines(top=args.top)))
            return 0
        if args.subcommand == "free-space":
            entry = storage.free_space(
                args.workspace, args.recipe, apply=args.apply, runs=args.runs
            )
            _print_free_space(entry, list_paths=args.list_paths)
            return 0
        if args.subcommand == "delete-sims":
            # "4001,2009" or the bracketed "[4001,2009]" both read as two ids.
            entry = storage.delete_sims(
                args.workspace,
                _listed_sims(args.sims),
                matrix_products=args.matrix_products,
                apply=args.apply,
                runs=args.runs,
                force=args.force,
            )
            _print_delete_sims(entry)
            return 0
        entries = storage.sync_workspaces(
            args.workspace,
            args.level,
            source=args.source,
            apply=args.apply,
            prefer_other=args.prefer_other,
            overwrite=args.overwrite,
            restore=args.restore,
            include_archives=args.include_archives,
            runs=args.runs,
        )
        for entry in entries:
            _print_sync(entry)
        if not args.apply:
            print("preview only: run again with --apply to sync")
        return 0
    except (WorkspaceError, OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2


#: The records commands of 0.32.0 (:mod:`pyflightstream.run.records`, package B1).
_RECORDS_COMMANDS = ("restore", "rebuild", "mark-failed")


def _cmd_records(args: argparse.Namespace) -> int:
    """Run ``restore``, ``rebuild`` or ``mark-failed`` through :mod:`pyflightstream.run.records`."""
    if args.subcommand == "mark-failed":
        return _cmd_mark_failed(args)
    try:
        if args.subcommand == "restore":
            entry = run_records.restore(
                args.workspace, args.kind, stamp=args.stamp, apply=args.apply, matrix=args.matrix
            )
        else:
            aliases: dict[str, str] = {}
            for item in args.build_alias:
                build, separator, alias = item.partition("=")
                if not separator or not build.strip() or not alias.strip():
                    _refuse(f"--build-alias expects BUILD=ALIAS, got {item!r}")
                aliases[build.strip()] = alias.strip()
            entry = run_records.rebuild(
                args.workspace,
                out=args.out,
                all_sims=args.all_sims,
                sims=None if args.sims is None else _listed_sims(args.sims),
                build_alias=aliases or None,
                matrix=args.matrix,
                apply=args.apply,
                inputs_from=args.inputs_from,
            )
    except (PyflightstreamError, OSError) as error:
        print(str(error), file=sys.stderr)
        return 2
    for line in run_records.summary_lines(entry):
        print(line)
    return 0


def _cmd_mark_failed(args: argparse.Namespace) -> int:
    """Mark the named simulations' records FAILED_MARKED (FR-309)."""
    try:
        entry = run_records.mark_failed(
            args.workspace, _listed_sims(args.sims), reason=args.reason, apply=args.apply
        )
    except (PyflightstreamError, OSError) as error:
        print(str(error), file=sys.stderr)
        return 2
    verb = "marked" if entry["applied"] else "would mark"
    for item in entry["marked"]:
        print(f"{verb} FAILED_MARKED: sim {item['sim_id']} {item['run_id']} (was {item['from']})")
    for run_id in entry["already"]:
        print(f"already FAILED_MARKED, left as it is: {run_id}")
    if entry["applied"]:
        print(f"runs.json as it was: {entry['runs_archived_as']}")
    elif entry["marked"]:
        print("preview: nothing was written; run again with --apply")
    return 0


def _refuse_runs_manifest(args: argparse.Namespace) -> int | None:
    """Validate ``--runs NAME``; an exit code when its name is refused.

    The name is checked by :func:`pyflightstream.run.records.resolve_manifest`
    (a file name directly in the workspace root, ending in ``.json``). Every
    command that takes the flag reads the manifest it names, so a valid name
    is passed on and the command resolves it again where it reads.
    """
    name = getattr(args, "runs", None)
    if name is None:
        return None
    try:
        run_records.resolve_manifest(args.workspace, name)
    except PyflightstreamError as error:
        print(str(error), file=sys.stderr)
        return 2
    return None


def _records_workspace(args: argparse.Namespace) -> CampaignWorkspace | None:
    """Return the workspace post and collect read (0.32.0, B3); None after a refusal.

    runs.json, the manifest ``--runs NAME`` names, or, for ``post --from-sims``,
    records assembled in memory from sims/, each refusal of which is printed.
    """
    from_sims = getattr(args, "from_sims", False)
    clock = getattr(args, "steps_per_revolution", None)
    runs = getattr(args, "runs", None)
    idle = None
    if clock is not None and not from_sims:
        idle = "--steps-per-revolution only means something to --from-sims"
    elif from_sims and args.matrix is None:
        idle = "--from-sims names the matrix it assembles: pyfs-matrix post <matrix> --from-sims"
    elif from_sims and runs is not None:
        idle = "--from-sims reads no manifest, so --runs cannot name one beside it"
    elif getattr(args, "additional_pproc", False) and (from_sims or runs is not None):
        idle = (
            "--additional-pproc reopens the simulations of runs.json and records them in "
            "additional.json; --from-sims and --runs post other records apart. Drop one"
        )
    if idle is not None:
        print(idle, file=sys.stderr)
        return None
    try:
        if not from_sims:
            return run_records.manifest_workspace(args.workspace, runs)
        workspace = run_records.from_sims_workspace(
            args.workspace, Path(args.matrix).stem, steps_per_revolution=clock
        )
    except PyflightstreamError as error:
        print(str(error), file=sys.stderr)
        return None
    for where, reason in workspace.refusals.items():
        print(f"refused, {where}: {reason}", file=sys.stderr)
    return workspace


def _naming(args: argparse.Namespace) -> NamingTemplate:
    """Build the point-name template the command line was given.

    Absent one, the default is the convention this package ships with.
    """
    try:
        return NamingTemplate(point_name=args.point_name)
    except NamingTemplateError as error:
        _refuse(
            f"point_name (CLI: --point-name): {error} The placeholders a template may "
            f"use are listed under `pyfs-matrix run --help`; the default is {MATRIX_POINT_NAME!r}."
        )


def _cmd_rename(args: argparse.Namespace) -> int:
    """Rename a 0.20.x workspace to the 0.21.0 names, or rehearse it."""
    from pyflightstream.run.rename import rename_workspace

    workspace = CampaignWorkspace(Path(args.workspace))
    try:
        report = rename_workspace(workspace, apply=not args.dry_run)
    except (WorkspaceError, CampaignConfigError) as error:
        print(str(error), file=sys.stderr)
        return 2
    for line in report.lines():
        print(line)
    print(report.summary())
    # EVERY ARM ENDS WITH THE NEXT STEP. The first writing wrote one only for
    # the nothing-to-do arm, so a user who had just read forty rehearsed
    # changes was told nothing about how to make them happen (the interface
    # lens, 2026-09-16).
    if not report.changes:
        # NOTHING TO DO IS A SUCCESS and says so in words, because this
        # command is run twice by anybody who is careful: once to see, once
        # to move. A silent zero reads as "it did not run".
        print("every record is already at the 0.21.0 names; nothing moved.")
    elif args.dry_run:
        print("nothing was changed. Run the same command without --dry-run to move them.")
    else:
        print("the workspace is at the 0.21.0 names; pyfs-matrix collect and post read it now.")
    return 0


def _cmd_collect(args: argparse.Namespace) -> int:
    """Sweep the submitted points and collect the ones whose outputs settled."""
    # A FLAG THAT BOUNDS A WATCH IS REFUSED WITHOUT THE WATCH, at parse time,
    # rather than accepted and ignored. Both facts are known here and the
    # information to refuse exists, so silence is the wrong answer: `--rounds
    # 5` alone reads as "sweep five times" to anybody who has not read the
    # source, and it ran once. Found by the interface lens of the 0.18.0
    # release round, 2026-09-14.
    idle = [
        name
        for name, value in (("--rounds", args.rounds), ("--watch-interval", args.watch_interval))
        if value is not None and not args.watch
    ]
    if idle:
        print(
            f"{', '.join(idle)} only mean something to a watch, and this is a single sweep. "
            "Add --watch to loop, or drop "
            f"{'them' if len(idle) > 1 else 'it'} to sweep once.",
            file=sys.stderr,
        )
        return 2
    # THE POST STAGE IS REACHED THROUGH THE WORKSPACE REGISTRY, exactly as
    # `_cmd_post` reaches it, and not by importing the products writer here.
    # Dependencies flow downward and a function-body import does not make an
    # upward one legal: deferring it to call time hides the direction from
    # every module-level reader without changing it. The layering guard
    # carries no allowlist, deliberately, and it refused the first writing
    # of this command.
    from pyflightstream.workspace import post_stages

    from .collect import (
        DEFAULT_SETTLE_INTERVAL_S,
        DEFAULT_WATCH_INTERVAL_S,
        collect_and_post,
    )

    if (workspace := _records_workspace(args)) is None:  # 0.32.0: --runs NAME (B3)
        return 2
    interval = DEFAULT_SETTLE_INTERVAL_S if args.interval is None else args.interval
    watch_interval = (
        DEFAULT_WATCH_INTERVAL_S if args.watch_interval is None else args.watch_interval
    )

    def _post(ws: CampaignWorkspace, matrix: str | None, sims: list[str] | None = None) -> None:
        # THE PRODUCTS ARE REBUILT ONLY WHERE SOMETHING WAS COLLECTED, which
        # `collect_and_post` decides: a rebuild ARCHIVES what it replaces, so
        # a watch that posted on every sweep would fill the archive with
        # copies of an unchanged answer.
        #
        # PER MATRIX, AND AS `post` DOES IT (0.24.0). This called `stage(ws)`:
        # no matrix, so the stage selected the records that name none and left
        # every named-matrix record out, which is every record a matrix run
        # writes, and the command exited 0 having written nothing. And no
        # `overwrite`, so where products of that matrix already stood, the
        # second sweep of a watch among them, the stage refused them instead
        # of archiving them as the paragraph above says it does.
        note_post_ran()
        for stage in post_stages():
            # THE FLAG TRAVELS ONLY WHEN SET: a stage registered before
            # 0.25.1 takes no `check_frozen`, and the bare command must keep
            # running it (the fourth independent reading of GitHub main).
            stage(
                ws,
                overwrite=True,
                archive=True,
                matrix_stem=matrix,
                **({"check_frozen": True} if args.check_frozen else {}),
                # FR-307: the post of `collect --sims` is limited to the same simulations.
                **({"sims": sims} if sims is not None else {}),
            )

    try:
        with stage_progress("collect"):
            report = collect_and_post(
                workspace,
                watch=args.watch,
                interval=interval,
                watch_interval=watch_interval,
                rounds=args.rounds,
                post_matrix=_post if args.post else None,
                sims=None if args.sims is None else _listed_sims(args.sims),
            )
    except (WorkspaceError, CampaignConfigError) as error:
        print(str(error), file=sys.stderr)
        return 2

    for line in report.lines():
        print(line)
    print(
        f"collected {len(report.collected)}, failed {len(report.failed)}, "
        f"outstanding {report.outstanding}, unknown {len(report.unknown)}"
    )
    # THREE OUTCOMES AND THREE STATUSES, because a cron job reads the status
    # and nothing else. 0 is everything settled and collected; 1 is a point
    # this stage tried to complete and could not; 3 is "still outstanding",
    # which a `--rounds` watch that ran out of rounds reaches and which a
    # single status shared with success would hide. A point whose record
    # declares nothing is neither: it is reported and does not decide the
    # status, because it is not a failure of this run.
    if report.failed:
        return 1
    return 3 if report.outstanding else 0


def _cmd_post(args: argparse.Namespace) -> int:
    """Rebuild the products from the manifest alone, after the additional post when asked."""
    from pyflightstream.workspace import post_stages

    # FLAGS THAT ONLY MEAN SOMETHING TO THE ADDITIONAL POST ARE REFUSED WITHOUT
    # IT, in the form `--yes` is refused without `--force-overwrite`: accepted and
    # ignored, `post --fs-exe X` would read as though the rebuild ran something.
    idle = [
        flag
        for flag, value in (
            ("--fs-version", args.fs_version),
            ("--fs-exe", args.fs_exe),
            ("--local", args.local),
            ("--recipe", args.recipe),
        )
        if value and not args.additional_pproc
    ]
    if idle:
        print(
            f"{', '.join(idle)} only mean something to --additional-pproc, which reopens the "
            "saved simulations; the rebuild of the products launches nothing. Add "
            "--additional-pproc, or drop "
            f"{'them' if len(idle) > 1 else 'it'}.",
            file=sys.stderr,
        )
        return 2
    if args.additional_pproc and args.matrix is None:
        print(
            "--additional-pproc needs the matrix: the ADDITIONAL_PPROC key is read from its "
            "rows. Name it: pyfs-matrix post <matrix> --additional-pproc.",
            file=sys.stderr,
        )
        return 2
    if args.sims is not None and (args.additional_pproc or args.diagnostics):
        # FR-307: the additional post reopens every recorded point, and a rebuild
        # limited to some simulations would leave the others' extractions
        # unposted; --diagnostics changes nothing to limit.
        print(
            "--sims limits the rebuild of the products and cannot be combined with "
            "--additional-pproc or --diagnostics; run those without it.",
            file=sys.stderr,
        )
        return 2
    if (workspace := _records_workspace(args)) is None:  # 0.32.0: --runs, --from-sims (B3)
        return 2
    extraction_failed = 0
    extraction_skipped = 0
    try:
        # Assembled records are read here without announcing their refusals,
        # which the post's own first read writes into its log.
        assembled = getattr(workspace, "assembled", None)
        if assembled is not None and not assembled:
            # EVERY POINT WAS REFUSED, each already printed once above: the
            # points ran, so "records no run, run a matrix first" would be false.
            print(
                f"post --from-sims assembled no record of matrix {args.matrix} from "
                f"{workspace.manifest_path}; each refusal is printed above, and nothing "
                "was written.",
                file=sys.stderr,
            )
            return 2
        records = assembled if assembled is not None else workspace.read_manifest()
        if not records:
            print(
                f"the manifest {workspace.manifest_path} records no run, so there is nothing "
                "to rebuild products from; run a matrix first, or check --workspace.",
                file=sys.stderr,
            )
            return 2
        named = list(dict.fromkeys(record.matrix_stem for record in records))
        if args.matrix is not None:
            stem = Path(args.matrix).stem
            if stem not in named:
                stems = ", ".join(sorted(m for m in named if m)) or "none"
                print(
                    f"the manifest of {workspace.root} holds no record of matrix {stem!r}; "
                    f"the matrices it names are {stems}. Run that matrix first, or name one "
                    "of those.",
                    file=sys.stderr,
                )
                return 2
            matrices: list[str | None] = [stem]
        else:
            # Every matrix the manifest names, in first-seen order, and the
            # records naming none as their own group (PFS-2031.04).
            matrices = named
        sims_of: dict[str | None, list[str]] = {}
        if args.sims is not None:
            # FR-307: REFUSED BY NAME BEFORE ANY WORK. With a matrix, every id
            # must be a simulation of it; without one, each matrix holding a
            # named simulation is posted limited to the ones it holds.
            listed = _listed_sims(args.sims)
            scoped = [record for record in records if record.matrix_stem in matrices]
            scope = f"of matrix {matrices[0]!r}" if args.matrix is not None else "in the manifest"
            try:
                chosen = selected_sims(scoped, listed, scope=scope)
            except WorkspaceError as error:
                print(str(error), file=sys.stderr)
                return 2
            for matrix in matrices:
                held = {record.sim_id for record in scoped if record.matrix_stem == matrix}
                if chosen & held:
                    sims_of[matrix] = sorted(chosen & held)
            matrices = [matrix for matrix in matrices if matrix in sims_of]
        if getattr(args, "diagnostics", False):
            if args.additional_pproc or args.force_overwrite or args.yes or args.check_frozen:
                print(
                    "--diagnostics cannot be combined with post mutation or frozen checks",
                    file=sys.stderr,
                )
                return 2
            print(
                post_diagnostics(
                    [workspace.products_dir(matrix) / "post.log.json" for matrix in matrices]
                )
            )
            return 0
        # THE REFUSAL THE HELP TEXT PROMISES, and it was prose alone until
        # 2026-09-13 (the interface lens). `--yes` answers one question and
        # nothing else asks one, so alone it parses, runs, archives and
        # exits 0: a pre-authorisation sitting in a saved command line,
        # waiting for the day someone adds --force-overwrite beside it.
        if args.yes and not args.force_overwrite:
            print(
                "--yes answers the --force-overwrite confirmation and nothing else asks "
                "one, so on its own it would sit in a saved command line pre-authorising "
                "a destruction nobody has asked for yet. Drop it, or pass "
                "--force-overwrite if you mean to destroy what is there.",
                file=sys.stderr,
            )
            return 2
        if args.force_overwrite and not _confirmed_destruction(args.yes):
            print(
                "--force-overwrite was not confirmed; nothing was written. Run without "
                "it to archive what is there and rebuild, which loses nothing.",
                file=sys.stderr,
            )
            return 2
        if args.additional_pproc:
            outcome = _additional_post(args, workspace)
            if outcome is None:
                return 2
            extraction_failed, extraction_skipped = outcome
        written: list[Path] = []
        with stage_progress("post", total_files=len(matrices)) as progress:
            for matrix in matrices:
                for stage in post_stages():
                    written.extend(
                        stage(
                            workspace,
                            overwrite=True,
                            archive=not args.force_overwrite,
                            matrix_stem=matrix,
                            # Only when set, so a stage registered before 0.25.1
                            # keeps running under the bare command.
                            **({"check_frozen": True} if args.check_frozen else {}),
                            # FR-307, and only when set, for the same reason.
                            **({"sims": sims_of[matrix]} if matrix in sims_of else {}),
                        )
                    )
                progress.advance(files=1, current=workspace.products_dir(matrix))
    except (OSError, PyflightstreamError) as error:
        print(str(error), file=sys.stderr)
        return 2
    for path in written:
        print(path)
    folders = ", ".join(str(workspace.products_dir(matrix)) for matrix in matrices)
    print(f"{len(written)} product(s) written under {folders}")
    # A simulation whose product was refused by design is a skip the
    # manifest records (PFS-2031.16); say it where the user looks.
    skipped = _report_skips(workspace, matrices)
    if extraction_failed:
        # THE PRECEDENT OF `run` WITH FAILURES: the products of everything that
        # worked are written, and the exit says a launch failed.
        print(
            f"--additional-pproc: {extraction_failed} extraction(s) failed; the products of "
            "the rest were written. Each failure is in additional.json with its reason.",
            file=sys.stderr,
        )
        return 2
    skipped += extraction_skipped
    if skipped and args.strict:
        # The design decision of 2026-09-08: a skip is a success by default, since
        # everything producible was produced, and a wrapper that needs to
        # tell a partial rebuild apart asks for it. The code is 3, its own,
        # beside 2 for a refusal that wrote nothing (review round two).
        print(
            f"--strict: {skipped} simulation(s) skipped; the products of the rest were "
            f"written under {folders}; exit 3",
            file=sys.stderr,
        )
        return 3
    return 0


def _additional_post(
    args: argparse.Namespace, workspace: CampaignWorkspace
) -> tuple[int, int] | None:
    """Run the additional post of one matrix and print one line per recorded point (G12).

    Returns how many extractions failed and how many points were skipped for a
    reason that asks something of the user, or None for a refusal before any
    launch, which the caller turns into exit 2. A row without the key, a point
    already extracted and a run a continuation replaced are skips that ask
    nothing, so ``--strict`` does not count them.
    """
    from pyflightstream.run.matrix import AdditionalSkip, run_additional_post

    try:
        plans, records = run_additional_post(
            args.matrix,
            workspace,
            default_fs_version=args.fs_version,
            recipes=_parse_recipes(args.recipe),
            fs_exe=args.fs_exe,
            local=args.local,
        )
    except (
        MatrixError,
        InputArtifactError,
        CampaignConfigError,
        WorkflowCoverageError,
        PyflightstreamError,
        OSError,
        ValueError,
    ) as error:
        print(f"additional post not run: {error}", file=sys.stderr)
        return None
    by_run = {record.run_id: record for record in records}
    asks_nothing = {
        AdditionalSkip.NO_KEY,
        AdditionalSkip.ALREADY_EXTRACTED,
        AdditionalSkip.SUPERSEDED,
    }
    failed = skipped = 0
    for plan in plans:
        record = by_run.get(plan.run_id)
        if record is not None:
            if record.status == "SUBMITTED":
                print(f"{plan.run_id} [{plan.pproc}]: submitted; extraction pending collect")
            elif record.status == "EXTRACTED":
                print(f"{plan.run_id} [{plan.pproc}]: extracted into {record.working_dir}/")
            else:
                failed += 1
                print(f"{plan.run_id} [{plan.pproc}]: failed ({record.status}): {record.error}")
            continue
        print(f"{plan.run_id}: skipped ({plan.reason}): {plan.message}")
        if plan.reason not in asks_nothing:
            skipped += 1
    return failed, skipped


def _report_skips(workspace: CampaignWorkspace, matrices: list[str | None]) -> int:
    """Say the recorded skips of the given matrices on stderr; return the count.

    Shared by ``post`` and ``run`` (PFS-2031.16, PFS-2031.19): the surface
    that spent the seat says what it skipped too, rather than leaving it
    for a later rebuild to discover. Since 0.29 every CLI surface, with or
    without ``--pproc-warnings``, names each skip with ``details:
    --diagnostics`` and prints ONE count line per matrix naming its
    manifest; the reasons stay in the manifest and the saved log, and
    ``--diagnostics`` renders the complete record (G59). Only an ordinary
    Python caller, outside the CLI, gets each skip with its reason.
    """
    import json

    skipped = 0
    detail = post_warning_policy() is None
    for matrix in matrices:
        manifest = workspace.products_dir(matrix) / "products.json"
        if not manifest.is_file():
            continue
        label = matrix or "the matrix-less records"
        # Keyed by the simulation refused whole, or by the reduction file the
        # row could not window (PFS-2015.04); the key says which.
        entries = json.loads(manifest.read_text(encoding="utf-8")).get("skipped", {})
        for key, reason in entries.items():
            what = key if "/" in key else f"simulation {key}"
            if detail:
                print(f"skipped {what} of {label}: {reason}", file=sys.stderr)
            else:
                # QUIET IS NOT SILENT (GOAL-034 Q4, Q0-tests-2-8): the reason stays in
                # the manifest, the log and --diagnostics, but each skip is still
                # named where the user looks.
                print(f"skipped {what} of {label}; details: --diagnostics", file=sys.stderr)
        if entries and not detail:
            # A skip is not a warning and is never silent: the count and
            # where its reasons are recorded are said even when quiet.
            print(
                f"{len(entries)} recorded skip(s) of {label}; reasons in {manifest} "
                "(--diagnostics prints them)",
                file=sys.stderr,
            )
        skipped += len(entries)
    return skipped


def _cmd_inventory(args: argparse.Namespace) -> int:
    """Write the boundary inventory sidecar of one saved simulation.

    A saved simulation that carries unsteady solver actions is named on
    standard error with each action and the ``--clean`` command, on every
    call (FR-308); ``--clean`` reduces the file to its meshes and boundary
    conditions first (FR-308, FR-312), and then an existing sidecar is kept,
    since the boundaries it lists did not change.
    """
    from datetime import UTC, datetime

    from pyflightstream.workspace._geometry_clean import saved_action_warning
    from pyflightstream.workspace.inputs import (
        OBJ_SUFFIX,
        clean_saved_actions,
        inventory_sidecar,
        write_inventory,
    )

    geometry = Path(args.geometry)
    saved = geometry.is_file() and geometry.suffix.lower() != OBJ_SUFFIX
    if saved and args.clean:
        stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        try:
            cleaned = clean_saved_actions(geometry, stamp=stamp)
        except (OSError, PyflightstreamError) as error:
            print(str(error), file=sys.stderr)
            return 2
        said = [f"removed saved action {n} [{k}] {c}" for n, c, k in cleaned.actions]
        said += [f"reset block {name} to its fresh-import content" for name in cleaned.blocks_reset]
        said += [cleaned.note] if cleaned.note else []
        said += [
            f"the file as it was is {cleaned.backup.name}"
            if cleaned.backup is not None
            else f"{geometry.name} carries no saved unsteady solver action"
            + ("" if cleaned.note else ", and each measured block holds its fresh-import content")
        ]
        for line in said:
            print(line, file=sys.stderr)
        if inventory_sidecar(geometry).exists() and not args.overwrite:
            print(inventory_sidecar(geometry))
            return 0
    elif saved and (warning := saved_action_warning(geometry, args.geometry)) is not None:
        print(f"warning: {warning}", file=sys.stderr)
    try:
        sidecar = write_inventory(args.geometry, overwrite=args.overwrite)
    except (OSError, PyflightstreamError) as error:
        print(str(error), file=sys.stderr)
        return 2
    print(sidecar)
    return 0


def _notices_for(before: str) -> list[str]:
    """Return the notices this upgrade owes, one per stage its INPUT needs.

    The single unconditional notice this replaces told every user, at every
    layout, that their RESULTS ARE NOT PRESERVED. That is true across the
    v0.8.x boundary and it is the OPPOSITE of what this release guarantees
    about its own stage, so a user converting a 14-column file read the one
    surface they meet at the moment of committing and were told to throw
    away a campaign that still resolves. The release review raised it at
    severity one, and the cost of believing it is a licensed seat.

    The header is what decides, because the header is what the reader
    refuses on: a file carrying an `RE` column entered at the v0.8.x layout
    and needs the REmi paragraph; a file carrying `SWEEP_TYPE` is the
    migration this release is for and needs the opposite sentence.
    """
    header = next((line for line in before.splitlines() if "|" in line), "")
    cells = [cell.strip().upper() for cell in header.split("|")]
    notices = []
    if "RE" in cells:
        notices.append(_RE_NOTICE)
    if "SWEEP_TYPE" in cells:
        notices.append(_SWEEP_NOTICE)
    if not notices:
        notices.append(_NO_STAGE_NOTICE)
    return notices


def _cmd_upgrade(args: argparse.Namespace) -> int:
    """Bring a matrix at an older layout up to the current one."""
    if args.inputs is not None and not args.in_place:
        print(
            "inputs (CLI: --inputs) moves library files and rewrites the cells that name "
            "them, so it needs in_place (CLI: --in-place); without it the matrix would go "
            "to standard output naming files that no longer exist.",
            file=sys.stderr,
        )
        return 2
    try:
        # READ BEFORE THE CONVERSION, because the notices are decided by the
        # layout the file ENTERED at and `--in-place` overwrites it.
        original = Path(args.matrix).read_text(encoding="utf-8", errors="replace")
        upgraded = upgrade_matrix(args.matrix, in_place=args.in_place)
        if args.inputs is not None:
            from pyflightstream.workspace.inputs import (
                InputArtifactError,
                migrate_groups_to_pproc,
                strip_rotor_facts,
            )

            try:
                moved = migrate_groups_to_pproc(Path(args.inputs))
            except InputArtifactError as error:
                print(str(error), file=sys.stderr)
                return 2
            for old, new in sorted(moved.items()):
                print(f"moved inputs/groups/{old}.toml to inputs/pproc/{new}.toml", file=sys.stderr)
            if not moved:
                print(f"no groups file under {args.inputs} to move", file=sys.stderr)
            for name, keys in sorted(strip_rotor_facts(Path(args.inputs)).items()):
                print(
                    f"stripped {', '.join(keys)} from inputs/references/{name}; the row "
                    "states the rotor speed's sign and axis (PFS-2029.08)",
                    file=sys.stderr,
                )
    except (OSError, MatrixError) as error:
        print(str(error), file=sys.stderr)
        return 2
    if args.in_place:
        print(f"upgraded {args.matrix}", file=sys.stderr)
    # ONE NOTICE PER STAGE THAT ACTUALLY FIRED, on stderr on BOTH routes so
    # it never contaminates the bytes the stdout route hands back for a diff.
    # A file that never carried an RE column is not told about REmi, and a
    # file whose sweep cell was folded is told the thing that matters to it.
    for notice in _notices_for(original):
        print(notice, file=sys.stderr)
    if args.in_place:
        return 0
    sys.stdout.buffer.write(upgraded)
    return 0


def _cmd_convert(args: argparse.Namespace, recipes: dict[str, str]) -> int:
    if args.name is None:
        print(
            "convert has no workspace to name the campaign after; pass name (CLI: --name).",
            file=sys.stderr,
        )
        return 2
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
        with _textio.open_text(args.output, "w") as handle:
            handle.write(text)
        print(f"campaign written: {args.output}")
    else:
        print(text, end="")
    return 0


def _the_missing_family_choice(args: argparse.Namespace) -> bool:
    """Read the one choice its two spellings state, refusing a contradiction.

    `--no-ignore-missing-families` is a flag and `--ignore-missing-families
    false` is a word, and they say the same thing. A command stating BOTH is
    refused rather than resolved by precedence: two statements of one intent
    cannot both be the one obeyed, which is the rule this package applies to
    a row that states a rotor twice.
    """
    word = args.ignore_missing_families
    if args.refuse_missing_families and word is not None:
        _refuse(
            "--no-ignore-missing-families and --ignore-missing-families were both "
            "stated. They are the same choice, and two statements of one choice "
            "cannot both be the one obeyed. Write one of them: the flag, or the word."
        )
    if args.refuse_missing_families:
        return False
    # ABSENT IS TRUE, which is the design and what every row written before
    # this flag means.
    return True if word is None else word


def _cmd_plan(args: argparse.Namespace, recipes: dict[str, str]) -> int:
    workspace = CampaignWorkspace(args.workspace, naming=_naming(args))
    if getattr(args, "setup_guidelines", False) or getattr(args, "setup_standards", False):
        from pyflightstream.workspace.setup_standards import write_setup_library

        if args.fs_version is None:
            print(
                "setup generation requires --fs-version to identify the target build",
                file=sys.stderr,
            )
            return 2
        try:
            generated = write_setup_library(
                workspace.root,
                fs_version=args.fs_version,
                guidelines=args.setup_guidelines,
                standards=args.setup_standards,
            )
        except (OSError, ValueError) as error:
            print(f"setup library not generated: {error}", file=sys.stderr)
            return 2
        for filename, status in generated.items():
            print(f"setup {status}: inputs/setups/{filename}")
    name, name_from = _campaign_name(args)
    renumbered = 0
    if getattr(args, "update_ids", False):
        # PFS-2031.21. BEFORE the plan, so the receipt the plan writes is
        # pinned to the digest of the file as renumbered, and `run` does not
        # then refuse it as a matrix edited after it was planned.
        try:
            changes = renumber_repeated_pols(args.matrix, workspace, in_place=True)
        except (MatrixError, OSError) as error:
            print(f"matrix not planned: {error}", file=sys.stderr)
            return 2
        matrix_name = Path(args.matrix).name
        if not changes:
            print(f"--update-ids: no POL of {matrix_name} is repeated; nothing was renumbered")
        renumbered = len(changes)
        for change in changes:
            print(
                f"--update-ids: {matrix_name} row {change.row_number}: "
                f"POL {change.old} -> {change.new}"
            )
    missing_families = _the_missing_family_choice(args)
    # THE WARNINGS ARE HELD while the plan is made and printed as one titled
    # block after its header (0.31.0), because a reader could not tell what
    # the warnings were about when they arrived first, unannounced. They are released
    # on every path, a refusal included, and still reach stderr.
    held: list[warnings.WarningMessage] = []
    try:
        with held_warnings() as held:
            plan = plan_matrix(
                args.matrix,
                workspace,
                name=name,
                name_from=name_from,
                # The keyword the library takes, not the flag the user types:
                # the parameter renamed with PFS-2009.08.01 and `--fs-version`
                # deliberately did not. Passing the old spelling here fired a
                # deprecation warning at a user who had typed a shell command
                # and named a Python keyword they never wrote.
                default_fs_version=args.fs_version,
                recipes=recipes,
                fs_exe=args.fs_exe,
                recipe_registry=workflow_registry(),
                ignore_missing_families=missing_families,
                cost=getattr(args, "cost", False),  # FR-82
                inflow_fft=getattr(args, "inflow_fft", False),  # 0.30.0
                write_plan=args.subcommand != "inspect-setups",
                accept_unregistered_build=args.accept_unregistered_build,
            )
    except (MatrixError, InputArtifactError, OSError, ValueError) as error:
        release_warnings(held)
        print(f"matrix not planned: {error}", file=sys.stderr)
        if renumbered:
            # SAID AT THE MOMENT IT MATTERS (the interface and V&V lenses,
            # 2026-09-14): the file on disk is not the one the user handed in.
            print(
                f"--update-ids: the {renumbered} renumbering(s) printed above are written to "
                f"{Path(args.matrix).name} and stay written; the plan refused for the reason "
                "above, not because of them.",
                file=sys.stderr,
            )
        return 2
    except BaseException:
        release_warnings(held)
        raise
    if args.subcommand == "inspect-setups":
        import json

        release_warnings(held)
        print(json.dumps(plan.setup_inspections, indent=2, ensure_ascii=False))
        return 1 if plan.blocked else 0
    _print_plan(plan, Path(args.matrix).name, held, cost=getattr(args, "cost", False))
    return 1 if plan.blocked else 0


def _cmd_run(args: argparse.Namespace, recipes: dict[str, str]) -> int:
    """Run every active point, then write the sweep table.

    The assessor is hard-wired and the recipe registry is this
    package's own workflow table; neither reaches this function from
    the command line, which is what keeps the recorded
    reasoning intact while the subcommand exists (see the module
    docstring).
    """
    workspace = CampaignWorkspace(args.workspace, naming=_naming(args))
    name, name_from = _campaign_name(args)
    # FR-97: `plan` carries
    # the warning and the confirmation, and this command does not release
    # without one. The stem is the matrix's own, which is how the plan
    # folder is named.
    stale = plan_receipt_error(workspace, args.matrix, Path(args.matrix).stem)
    if stale is not None:
        print(stale, file=sys.stderr)
        return 2
    records: list = []
    try:
        records = run_matrix(
            args.matrix,
            workspace,
            name=name,
            name_from=name_from,
            # The command line's own flag is still --fs-version, and the
            # keyword it feeds is the DEFAULT a row whose FS_BUILD names
            # no build falls back to; a row that names a build wins.
            default_fs_version=args.fs_version,
            recipes=recipes,
            assess=LoadsAssessor(),
            fs_exe=args.fs_exe,
            recipe_registry=workflow_registry(),
            resume=args.resume,
            force_rerun=args.force_rerun,
            force_rerun_all=args.force_rerun_all,
            sims=args.sims,
            progress_every=args.progress_every,
            ignore_missing_families=_the_missing_family_choice(args),
            accept_unregistered_build=args.accept_unregistered_build,
            local=args.local,
            # THE CHOSEN PATH GOES TO THE ONE WRITER. The library leaves the
            # table on its own, so choosing a path here and writing it below
            # left TWO: the default one from the library and the chosen one
            # from this command, against a help text promising one.
            sweep_csv=args.sweep_csv,
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
        # The call's records ride on the error, so a run that also SUBMITTED a
        # point is still seen as one below (G43).
        records = error.records
        status = 2
    except (
        MatrixError,
        InputArtifactError,
        CampaignConfigError,
        WorkflowCoverageError,
        # A REFUSAL IS NOT A CRASH. `WorkspaceError` is
        # `(PyflightstreamError, RuntimeError)` and is neither a ValueError nor
        # an OSError, so every refusal this package writes for a workspace --
        # the already-recorded point among them -- reached the user as a Python
        # traceback with the sentence at the bottom of it. `_cmd_post` has
        # caught `PyflightstreamError` since 0.17.0 (the interface lens,
        # FIX-0212).
        PyflightstreamError,
        OSError,
        ValueError,
    ) as error:
        print(f"matrix not run: {error}", file=sys.stderr)
        return 2
    else:
        status = 0

    # G43 of 0.28.0: a run that submitted anything posts nothing and writes no
    # table; the library has said what was submitted and what to run next.
    if any(record.status is RunStatus.SUBMITTED for record in records):
        return status

    # The matrix's own folder, so several matrices of one workspace keep
    # their own table (PFS-2031.04); the table holds this matrix's records.
    stem = Path(args.matrix).stem
    # FR-90: ONE NAME, AND IT IS THE ONE THE LIBRARY ALREADY WRITES.
    # `run_campaign` leaves `campaign_sweep.csv` under the same folder
    # (`run.SWEEP_TABLE_NAME`), so a default of `sweep.csv` here wrote the
    # same table a second time under a second name: measured in the
    # reference workspace, `post/matriz/sweep.csv` and
    # `post/matriz/campaign_sweep.csv` were 1012 bytes with one sha256
    # between them. A reader who found both could not know they were the
    # same without hashing them, and a reader who edited one had silently
    # disagreed with the other. `campaign_sweep.csv` is the name that
    # survives: it says the table is about the CAMPAIGN rather than about
    # one polar's sweep, and it is what FR-89 cites as one of its sources.
    #
    # WRITING IT AGAIN AT THE SAME PATH IS DELIBERATE and is not the
    # duplicate this fixes: the content is derived from the append-only
    # manifest, so the second write is the first one's own content, and
    # keeping it here means a campaign whose library-side write failed
    # still gets its table with this arm's own refusal.
    target = args.sweep_csv or str(workspace.sweep_dir(stem) / SWEEP_TABLE_NAME)
    # A record written before 0.13.0 names no matrix and is left out of
    # this table by design (PFS-2031.04); say so at the moment it happens
    # rather than leave a shorter table to be discovered.
    unnamed = sum(1 for record in workspace.read_manifest() if record.matrix_stem is None)
    if unnamed:
        print(
            f"{unnamed} recorded point(s) name no matrix (written before 0.13.0) and are "
            f"not in this table; their own products live under {workspace.products_dir(None)}",
            file=sys.stderr,
        )
    try:
        # `require_loads=False` is the keyword written for exactly this
        # condition: a sweep in which no run yielded coefficients still
        # has identity rows, and printing "sweep table not written" over
        # them discards work the campaign already did. `write_table` is
        # the one write path of the tabular layer and refuses a frame
        # that cannot say what produced its numbers; `to_csv` bypassed
        # that and was correct only by coincidence.
        Path(target).parent.mkdir(parents=True, exist_ok=True)
        # THE LIBRARY HAS ALREADY SAID IT. Every path that reaches this line
        # went through `run_matrix`, which left the same table from the same
        # manifest a moment ago and emitted whatever warning deriving it
        # raises; deriving it again here emitted each of those a second time
        # from a second location, so one invocation printed the same
        # complaint twice. The refusals below still speak, because they are
        # exceptions and not warnings.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", PyflightstreamWarning)
            table = sweep_table(workspace, require_loads=False, matrix_stem=stem)
        write_table(table, target)
    except (LoadsNotFoundError, MalformedOutputError, OSError, ValueError) as error:
        print(f"runs completed, sweep table not written: {error}", file=sys.stderr)
        return 2
    print(f"sweep table: {target}")
    _report_skips(workspace, [stem])
    return status


if __name__ == "__main__":
    raise SystemExit(main())
