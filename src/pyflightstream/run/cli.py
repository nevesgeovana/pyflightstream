"""The ``pyfs-matrix`` command line.

Pipeline role: drives the run matrix as a first-class interface
of the file-managed modality from a terminal. The matrix is the campaign
declaration; campaign-file conversion is refused. ``pyfs-matrix plan`` binds the matrix codes
to the workspace input library and pre-flights every point without
executing anything; ``pyfs-matrix run`` takes the same matrix all the
way to manifest records and a sweep table.

The assessor is :class:`pyflightstream.run.LoadsAssessor`; no flag selects
another one. ``--workflow CODE=NAME`` names a run type from the package's
table (:mod:`pyflightstream.cases.workflows`), so a study built from those
types needs no Python (PFS-2025.09).

``--recipe CODE=REFERENCE`` still points at a function of your own on
``plan`` and ``run``; what it may not do is
name the same code a ``--workflow`` names, which is refused before
anything is read.

The command-line entry point belongs to the run layer because it binds planning and execution.

The console entry point is ``pyfs-matrix`` (FR-44). Plan's human output uses
titled blocks; its machine-readable outputs are exit codes and ``plan.json``.

The dispatcher of every pyfs-matrix subcommand, each command's logic beside it.
The argument parser is :mod:`pyflightstream.run._cli_parsers` (AD-14, built by family (AD-18))
and the console printing of plan and storage is :mod:`pyflightstream.run._cli_print`; what
stays is the commands themselves, which share the workspace, matrix and records helpers.
"""

from __future__ import annotations

import argparse
import sys
import warnings
from pathlib import Path
from typing import NoReturn

from pyflightstream._cli import cli_entrypoint, note_post_ran, post_warning_policy

# Re-export the console helpers and plan types at this public dotted path
# (parity arm R1, AD-15): blocks, table, wrap, print_held_warnings,
# CampaignPlan, format_cost_table, inflow_harmonics_line,
# qsteady_validity_line and continuation_block. Printing lives in _cli_print.
from pyflightstream._console import blocks as blocks
from pyflightstream._console import (
    command_help,
    held_warnings,
    release_warnings,
)
from pyflightstream._console import table as table
from pyflightstream._console import wrap as wrap
from pyflightstream._errors import PyflightstreamError, PyflightstreamWarning
from pyflightstream._progress import (
    LIVE_LOG_COMMANDS,
    command_console,
    say_data,
    say_summary,
    stage_progress,
)
from pyflightstream._progress import print_held_warnings as print_held_warnings
from pyflightstream.cases import CampaignConfigError
from pyflightstream.cases.matrix import MatrixError
from pyflightstream.cases.workflows import (
    WorkflowCoverageError,
    workflow_registry,
)

# Re-export the parser's public name at this dotted path.
from pyflightstream.cases.workflows import read_a_choice as read_a_choice
from pyflightstream.cases.workflows import resolve_workflow as resolve_workflow
from pyflightstream.cases.workflows import workflow_names as workflow_names
from pyflightstream.results import MalformedOutputError
from pyflightstream.results.tables import LoadsNotFoundError, sweep_table, write_table
from pyflightstream.run import (
    SWEEP_TABLE_NAME,
    CampaignErrors,
    LoadsAssessor,
    plan_receipt_error,
)
from pyflightstream.run import CampaignPlan as CampaignPlan
from pyflightstream.run import format_cost_table as format_cost_table
from pyflightstream.run import inflow_harmonics_line as inflow_harmonics_line
from pyflightstream.run import qsteady_validity_line as qsteady_validity_line
from pyflightstream.run import records as run_records
from pyflightstream.run._alias import failure_alias_lines, listed_ids, split_typed_ids
from pyflightstream.run._cli_parsers import (
    GEOMETRY_COMMANDS,
    _build_parser,
    cmd_geometry,
    cmd_mark_converged,
    collect_interval_error,
    parsed,
    resume_hint,
    watch_interval_error,
)
from pyflightstream.run._cli_parsers import _parse_workflows as _parse_workflows
from pyflightstream.run._cli_parsers import _whole_sims as _whole_sims
from pyflightstream.run._cli_print import (
    _print_collect,
    _print_delete_sims,
    _print_free_space,
    _print_plan,
    _print_sync,
)
from pyflightstream.run._cli_query import QUERY_COMMANDS, run_query
from pyflightstream.run._continuation_frame import continuation_block as continuation_block
from pyflightstream.run._grouped import planner_for, runner_for
from pyflightstream.run._ids import _AlreadyRecordedError
from pyflightstream.run.matrix import plan_matrix, run_matrix
from pyflightstream.workspace import (
    CampaignWorkspace,
    InputArtifactError,
    RunStatus,
    WorkspaceError,
    post_diagnostics,
    selected_sims,
)
from pyflightstream.workspace import (
    derive_thin_blade as derive_thin_blade,
)
from pyflightstream.workspace._matrix_homes import matrix_stem, resolve_matrix_arguments
from pyflightstream.workspace.ledger import listed_sims
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
        code, reference = code.strip(), reference.strip()
        if not separator or not code or not reference:
            raise ValueError(
                f"--recipe expects CODE=module:function (the FS_SCRIPT code and the "
                f"recipe it maps to), got {item!r}"
            )
        recipes[code] = reference
    return recipes


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


def _listed_sims(text: str | list[str]) -> list[str]:
    """Read simulation ids as ``delete-sims`` spells them: ``4001,2009`` or ``[4001,2009]``.

    Read by ``--sims`` of ``delete-sims``, ``rebuild``,
    ``mark-failed``, ``post``, ``collect`` and ``status`` (FR-307); ``mark-converged``
    reads its ``--sims`` words through the same reader. The form's one home is
    :func:`pyflightstream.workspace.ledger.listed_sims`.
    """
    return listed_sims(text)


def _confirmed_destruction(yes: bool) -> bool:
    """Ask before the explicit-confirmation rebuild path.

    Rebuilds overwrite in place by default without an archive; ``--archive``
    opts into keeping a copy. ``--force-overwrite`` and ``--yes`` are retained
    as confirmation controls and do not change that archive policy.

    A NON-INTERACTIVE SESSION IS A NO. If there is nobody to ask, the
    answer is not "assume yes": that is how a flag in a saved command line
    quietly destroys a rebuild's evidence on a machine with no terminal.
    """
    if yes:
        return True
    if not sys.stdin or not sys.stdin.isatty():
        return False
    answer = input(
        "--force-overwrite confirms a rebuild. The default "
        "writes no archive; --archive keeps a copy. Type 'rebuild' to go on: "
    )
    return answer.strip().lower() == "rebuild"


def _refused_campaign_file(argv: list[str] | None) -> bool:
    """Name the matrix replacement before parsing a retired convert invocation."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    if not arguments or arguments[0] != "convert":
        return False
    print(
        "Campaign-file conversion is not supported; the matrix is the sole campaign "
        "declaration. Use pyfs-matrix plan <matrix> --workspace <workspace>. "
        "See docs/upgrading.md.",
        file=sys.stderr,
    )
    return True


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
    if _refused_campaign_file(argv):
        return 2
    parser = _build_parser()
    # FR-436: what the command line does not state, the workspace files may.
    args = parsed(parser, _storage_flag_form(argv))
    # Console contract (FR-200 to FR-204): titled opening, final warnings,
    # and a live log for long commands. Plan prints its warnings after its header.
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
        try:
            # FR-310: every matrix argument over the two homes, before any command reads it.
            if (
                refused := _refuse_runs_manifest(args) or resolve_matrix_arguments(args)
            ) is not None:
                return refused
            if (code := _records_or_storage(args)) is not None:
                return code
            # Before the recipe parsing below, deliberately: upgrading a file
            # needs no recipes, no version and no executable, and requiring them
            # would refuse the one user this subcommand exists for.
            if args.subcommand == "post":
                note_post_ran()
                return _cmd_post(args)
            if args.subcommand == "collect":
                return _cmd_collect(args)
            if args.subcommand in GEOMETRY_COMMANDS:
                # FR-1136: the identical result, and one warning naming the home.
                from pyflightstream.run._cli_geometry import alias_warning

                warnings.warn(alias_warning(args.subcommand), PyflightstreamWarning, stacklevel=2)
                return cmd_geometry(args)
            try:
                recipes = _parse_recipes(args.recipe)
                if args.subcommand in ("run", "plan", "inspect-setups"):
                    # Plan rehearses run without solver time, including workflow matrices.
                    recipes = _one_builder_per_code(recipes, _parse_workflows(args.workflow))
            except (ValueError, CampaignConfigError) as error:
                print(str(error), file=sys.stderr)
                return 2
            if args.subcommand == "run":
                return _cmd_run(args, recipes)
            return _cmd_plan(args, recipes)
        except (PyflightstreamError, OSError) as error:
            return _failed(args.subcommand, error)


def _records_or_storage(args: argparse.Namespace) -> int | None:
    """Run the records or the storage command the arguments name, else return None."""
    if args.subcommand in _RECORDS_COMMANDS:
        return _cmd_records(args)
    if args.subcommand in _STORAGE_COMMANDS:
        return _cmd_storage(args)
    return None


def _failed(subcommand: str, error: Exception) -> int:
    """Say why a command failed and what to do, and return the failure exit code (NFR-48).

    A failure no command caught reaches the console as one diagnostic naming the cause
    and the remedy, never as an exception traceback.
    """
    print(
        f"pyfs-matrix {subcommand} failed: {type(error).__name__}: {error}\n"
        "Fix the cause named above and run the command again; "
        f"pyfs-matrix {subcommand} --help lists the options.",
        file=sys.stderr,
    )
    return 1


#: Print this layout-specific warning on both upgrade routes, where the user
#: commits to the change. Do not print it for a sweep fold: held angles keep
#: existing run_ids resolvable and resume can find their records.
_RE_NOTICE = (
    "This file entered at the v0.8.x layout, and across that boundary your "
    "RESULTS are not preserved: the RE column was recorded metadata that "
    "reached no emitted line. REmi is a CONSTRAINT that "
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
#: migration. It says the OPPOSITE of the notice above, and it is
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


#: The storage commands (`pyflightstream.workspace.storage`).
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
        # delete-sims names its simulations with --sims only (positional ids removed in 0.43.0).
        selector = ["--sims"] if name == "--delete-sims" else []
        if inline:
            return [name[2:], *selector, inline, *rest]
        if index + 1 < len(tokens):
            value = tokens[index + 1]
            return [name[2:], *selector, value, *tokens[:index], *tokens[index + 2 :]]
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
                _whole_sims(args),
                matrix_products=args.matrix_products,
                apply=args.apply,
                runs=args.runs,
                force=args.force,
                archive=args.archive,
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


#: The records commands (:mod:`pyflightstream.run.records`, package B1),
#: and the read-only query verbs (:mod:`pyflightstream.run._cli_query`).
_RECORDS_COMMANDS = ("restore", "rebuild", "mark-failed", "mark-converged", *QUERY_COMMANDS)


def _cmd_records(args: argparse.Namespace) -> int:
    """Run ``restore``, ``rebuild``, ``mark-failed``, ``mark-converged`` or a query verb."""
    if args.subcommand in QUERY_COMMANDS:
        return run_query(args)
    if args.subcommand == "mark-failed":
        return _cmd_mark_failed(args)
    if args.subcommand == "mark-converged":
        return cmd_mark_converged(args)  # FR-414
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
                # FR-794, PFS-2124.004: an alias resolves to the simulation that holds it, and
                # acts only when every point of that simulation is named.
                sims=None
                if args.sims is None
                else split_typed_ids(_listed_sims(args.sims), args.workspace, whole_only=True)[0],
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
        sims, points = split_typed_ids(listed_ids(args.sims), args.workspace)  # FR-395
        if args.points:
            points = {**points, **{sim: list(args.points) for sim in sims}}
            sims = []
        entry = run_records.mark_failed(
            args.workspace, sims, reason=args.reason, apply=args.apply, points=points
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
    """Return the workspace post and collect read (B3); None after a refusal.

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
            args.workspace, matrix_stem(args.matrix), steps_per_revolution=clock
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


def _cmd_collect(args: argparse.Namespace) -> int:
    """Sweep the submitted points and collect the ones whose outputs settled."""
    # Refuse a watch-bounding flag without a watch at parse time; accepting it
    # would silently ignore the requested repetition limit.
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
    # THE SETTLE WAIT IS A NUMBER OF SECONDS ABOVE 0 (PFS-2081.28):
    # zero takes both observations at one instant, so nothing is ever seen to
    # settle, and a negative wait reached time.sleep mid-sweep. Checked here
    # rather than by the parser, so a value from pyfs.toml is held to it too.
    if (interval_error := collect_interval_error(args.interval)) is not None:
        print(interval_error, file=sys.stderr)
        return 2
    if (watch_error := watch_interval_error(args.watch_interval)) is not None:
        print(watch_error, file=sys.stderr)
        return 2
    # Reach the post stage through the workspace registry, as _cmd_post does.
    # Importing the products writer would point dependencies upward even if
    # deferred to call time.
    from pyflightstream.workspace import post_stages

    from .collect import (
        DEFAULT_SETTLE_INTERVAL_S,
        DEFAULT_WATCH_INTERVAL_S,
        collect_and_post,
    )

    if (workspace := _records_workspace(args)) is None:  # --runs NAME (B3)
        return 2
    interval = DEFAULT_SETTLE_INTERVAL_S if args.interval is None else args.interval
    watch_interval = (
        DEFAULT_WATCH_INTERVAL_S if args.watch_interval is None else args.watch_interval
    )

    def _post(ws: CampaignWorkspace, matrix: str | None, sims: list[str] | None = None) -> None:
        # THE PRODUCTS ARE REBUILT ONLY WHERE SOMETHING WAS COLLECTED, which
        # `collect_and_post` decides. With --archive, a watch that posted on
        # every sweep would fill the archive with unchanged answers.
        #
        # PER MATRIX, AND AS `post` DOES IT. This called `stage(ws)`:
        # no matrix, so the stage selected the records that name none and left
        # every named-matrix record out, which is every record a matrix run
        # writes, and the command exited 0 having written nothing. And no
        # `overwrite`, so where products of that matrix already stood, the
        # second sweep of a watch among them, the stage refused them instead
        # of replacing them under the chosen archive policy.
        note_post_ran()
        for stage in post_stages():
            # Pass check_frozen only when set, preserving stages that do not accept
            # that optional keyword under the bare command.
            stage(
                ws,
                overwrite=True,
                archive=args.archive,
                matrix_stem=matrix,
                **({"check_frozen": True} if args.check_frozen else {}),
                # FR-307: the post of `collect --sims` is limited to the same simulations.
                **({"sims": sims} if sims is not None else {}),
            )

    # A POST REFUSAL IS NOT A COLLECTION FAILURE (PFS-2095.052): the stages
    # raise what `post` catches, and here it escaped as a traceback after the
    # records were written. It is said as the post's own refusal and exits 2,
    # as `post` does, so 1 and 3 keep meaning what the collection found.
    try:
        with stage_progress("collect"):
            report = collect_and_post(
                workspace,
                watch=args.watch,
                discard_walltime=args.discard_walltime,
                interval=interval,
                watch_interval=watch_interval,
                rounds=args.rounds,
                post_matrix=_post if args.post else None,
                sims=None if args.sims is None else _listed_sims(args.sims),
            )
    except (OSError, PyflightstreamError) as error:
        print(str(error), file=sys.stderr)
        return 2

    _print_collect(report)
    say_summary(
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
    from pyflightstream.workspace.cli import typed_value

    # FLAGS THAT ONLY MEAN SOMETHING TO THE ADDITIONAL POST ARE REFUSED WITHOUT
    # IT, in the form `--yes` is refused without `--force-overwrite`: accepted and
    # ignored, `post --fs-exe X` would read as though the rebuild ran something.
    # Only what the COMMAND LINE typed is judged (FR-993): a value a workspace
    # settings file gave is left unused by a rebuild that does not take it.
    if idle := [
        flag
        for flag in ("--fs-version", "--fs-exe", "--local", "--recipe", "--hpc")
        if typed_value(args, flag) and not args.additional_pproc
    ]:
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
    if (workspace := _records_workspace(args)) is None:  # --runs, --from-sims (B3)
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
            stem = matrix_stem(args.matrix)
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
            # A --check-frozen a settings file gave is left unused here (FR-993).
            if (
                args.additional_pproc
                or args.force_overwrite
                or args.yes
                or typed_value(args, "--check-frozen")
            ):
                print(
                    "--diagnostics cannot be combined with post mutation or frozen checks",
                    file=sys.stderr,
                )
                return 2
            say_data(
                post_diagnostics(
                    [workspace.products_dir(matrix) / "post.log.json" for matrix in matrices]
                )
            )
            return 0
        # --yes answers the overwrite question only. Refuse it without
        # --force-overwrite so a saved command cannot carry unused authorisation.
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
                "--force-overwrite was not confirmed; nothing was written. Confirm the "
                "rebuild with --yes to overwrite without an archive, or remove "
                "--force-overwrite and pass --archive to keep the replaced products.",
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
                            archive=args.archive,
                            matrix_stem=matrix,
                            # Pass only when set; bare commands work with stages
                            # that do not accept this keyword.
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
    say_summary(f"{len(written)} product(s) written under {folders}")
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
        # A skip succeeds by default when everything producible was produced.
        # A caller requesting a distinct partial-rebuild result receives code 3;
        # code 2 denotes a refusal that wrote nothing.
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
        print(
            f"additional post stopped: {error}. Any extraction that finished before the stop keeps "
            "its record (additional.json); the ones not reached were not started.",
            file=sys.stderr,
        )
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
    for a later rebuild to discover. Every CLI surface, with or
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
        try:
            entries = json.loads(manifest.read_text(encoding="utf-8")).get("skipped", {})
        except (OSError, ValueError, AttributeError) as error:
            print(
                f"could not read the skipped list of {label} from {manifest}: {error}. "
                "Rebuild the products of that matrix to write the manifest again.",
                file=sys.stderr,
            )
            continue
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
    setup = getattr(args, "setup_guidelines", False) or getattr(args, "setup_standards", False)
    # EVERY REFUSAL THE ARGUMENTS ALONE DECIDE COMES BEFORE THE FIRST WRITE
    # (PFS-2096.023): the setup guides and the --update-ids renumbering were
    # written, and then a contradiction between two flags refused the plan.
    if setup and args.fs_version is None:
        print(
            "setup generation requires --fs-version to identify the target build",
            file=sys.stderr,
        )
        return 2
    name, name_from = _campaign_name(args)
    missing_families = _the_missing_family_choice(args)
    if setup:
        from pyflightstream.workspace.setup_standards import write_setup_library

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
    renumbered = 0
    if getattr(args, "update_ids", False):
        # PFS-2031.21. BEFORE the plan, so the receipt the plan writes is
        # pinned to the digest of the file as renumbered, and `run` does not
        # then refuse it as a matrix edited after it was planned.
        try:
            changes = renumber_repeated_pols(args.matrix, workspace, in_place=True)
        except (MatrixError, PyflightstreamError, OSError) as error:
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
    # THE WARNINGS ARE HELD while the plan is made and printed as one titled
    # block after its header, because a reader could not tell what
    # the warnings were about when they arrived first, unannounced. They are released
    # on every path, a refusal included, and still reach stderr.
    held: list[warnings.WarningMessage] = []
    try:
        with held_warnings() as held:
            plan = planner_for(args, plan_matrix)(
                args.matrix,
                workspace,
                name=name,
                name_from=name_from,
                # Pass the library's default_fs_version keyword for the --fs-version flag;
                # the deprecated Python keyword must not warn a command-line user.
                default_fs_version=args.fs_version,
                recipes=recipes,
                fs_exe=args.fs_exe,
                recipe_registry=workflow_registry(),
                ignore_missing_families=missing_families,
                cost=getattr(args, "cost", False),  # FR-82
                inflow_fft=getattr(args, "inflow_fft", False),
                write_plan=args.subcommand != "inspect-setups",
                accept_unregistered_build=args.accept_unregistered_build,
                sims=args.sims,  # FR-326
                points=args.points,
            )
    # Catch PyflightstreamError as _cmd_run does (PFS-2095.051). WorkspaceError
    # is neither ValueError nor OSError and must reach the user as a refusal.
    except (MatrixError, InputArtifactError, PyflightstreamError, OSError, ValueError) as error:
        release_warnings(held)
        print(f"matrix not planned: {error}", file=sys.stderr)
        if renumbered:
            # Tell the user when the file on disk differs from the one submitted.
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
    _print_plan(
        plan,
        Path(args.matrix).name,
        held,
        cost=getattr(args, "cost", False),
        rows=workspace.read_raw_manifest(),
    )
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
    stale = plan_receipt_error(workspace, args.matrix, matrix_stem(args.matrix), fs_exe=args.fs_exe)
    if stale is not None:
        print(stale, file=sys.stderr)
        return 2
    records: list = []
    try:
        records = runner_for(args, run_matrix)(
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
            points=args.points,  # FR-326
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
    except _AlreadyRecordedError as error:
        # FR-327: the refusal of a second run names the command that continues it.
        print(f"matrix not run: {error}\n{resume_hint(args.invoked_argv)}", file=sys.stderr)
        return 2
    except CampaignErrors as error:
        # SEPARATED FROM THE OTHERS on purpose. Every arm below this one
        # is a refusal BEFORE the campaign ran, and leaves nothing to
        # tabulate. CampaignErrors is raised AFTER the loop, by a run
        # that executed and had failing points, and those points have
        # records. Catching it with the rest returned 2 without writing
        # anything, so a sweep with one failed point left no table at
        # all, which is the acceptance of PFS-2014.03 exactly inverted.
        print(f"matrix run with failures: {error}", file=sys.stderr)
        for line in failure_alias_lines(
            error.failures, workspace.read_raw_manifest(), workspace.root
        ):
            print(line, file=sys.stderr)
        # The call's records ride on the error, so a run that also SUBMITTED a
        # point is still seen as one below (G43).
        records = error.records
        status = 2
    except (
        MatrixError,
        InputArtifactError,
        CampaignConfigError,
        WorkflowCoverageError,
        # Catch package refusals as messages, including WorkspaceError, which
        # inherits PyflightstreamError and RuntimeError rather than ValueError or
        # OSError (FIX-0212).
        PyflightstreamError,
        OSError,
        ValueError,
    ) as error:
        print(f"matrix not run: {error}", file=sys.stderr)
        return 2
    else:
        status = 0

    # G43: a run that submits anything posts nothing and writes no table.
    # The library reports what was submitted and what to run next.
    if any(record.status is RunStatus.SUBMITTED for record in records):
        return status

    # The matrix's own folder, so several matrices of one workspace keep
    # their own table (PFS-2031.04); the table holds this matrix's records.
    stem = matrix_stem(args.matrix)
    # FR-90: use run.SWEEP_TABLE_NAME, the same campaign_sweep.csv path the
    # library writes. Rewriting that path is deliberate: both writes derive
    # from the manifest, and this gives a library-side write failure another
    # attempt with this command's own refusal.
    target = args.sweep_csv or str(workspace.sweep_dir(stem) / SWEEP_TABLE_NAME)
    # Exclude records naming no matrix (PFS-2031.04) and announce their count.
    unnamed = sum(1 for record in workspace.read_manifest() if record.matrix_stem is None)
    if unnamed:
        print(
            f"{unnamed} recorded point(s) name no matrix and are "
            f"not in this table; their own products live under {workspace.products_dir(None)}",
            file=sys.stderr,
        )
    try:
        # require_loads=False retains identity rows when no run yields coefficients.
        # Use write_table to enforce tabular provenance instead of bypassing it with
        # a direct to_csv call.
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
        write_table(table, target, overwrite=True)
    except (LoadsNotFoundError, MalformedOutputError, OSError, ValueError) as error:
        print(f"runs completed, sweep table not written: {error}", file=sys.stderr)
        return 2
    print(f"sweep table: {target}")
    _report_skips(workspace, [stem])
    return status


if __name__ == "__main__":
    raise SystemExit(main())
