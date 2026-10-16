"""The ``pyfs-matrix`` argument parser: every subcommand, option and help text.

Size exemption: a declarative catalogue of command options and their argument readers.

Private to :mod:`pyflightstream.run.cli`, which builds the parser through
:func:`_build_parser` and dispatches the parsed command. The builders live
apart from the commands they parse for so that the command line's own module
stays within the review lens (GOAL-038, AD-14): the parser is declarative
and long, the commands are the logic. The storage and records subcommands
(``space-in-use``, ``free-space``, ``delete-sims``, ``sync``, ``restore``,
``rebuild``, ``mark-failed``) are added by their own builders, and every
command that reads a manifest takes ``--runs NAME`` from one list.

:mod:`pyflightstream.run.cli` parses through (FR-436)
:func:`parsed`: an option the command line does not state takes its default
from ``pyfs.local.toml``, else ``pyfs.toml``, else the package. The parse is
this family's (FR-1002); the parser adaptation it runs inside is the command-line
side of :mod:`pyflightstream.workspace.cli`, and the schema, the precedence and
the provenance are :mod:`pyflightstream.workspace._settings_file`'s.
"""

from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from pyflightstream._cli import _SELECTED_COST_FILE, _SELECTED_HPC, for_this_invocation
from pyflightstream._console import CONSOLE_LEVELS
from pyflightstream.cases import CampaignConfigError
from pyflightstream.cases.workflows import (
    read_a_choice,
    resolve_workflow,
    workflow_names,
)
from pyflightstream.run import records as run_records
from pyflightstream.run._alias import split_typed_ids
from pyflightstream.run._cli_mesh import GEOMETRY_COMMANDS as GEOMETRY_COMMANDS
from pyflightstream.run._cli_mesh import (
    add_degenerate_parser,
    add_inventory_parser,
    add_mesh_parsers,
)
from pyflightstream.run._cli_mesh import cmd_geometry as cmd_geometry
from pyflightstream.run._cli_parsers_storage import (
    add_storage_parsers as _add_storage_parsers,
)
from pyflightstream.run._cli_query import add_query_parsers
from pyflightstream.run._cli_selectors import _add_sim_ids
from pyflightstream.run._grouped import GROUPED_LEFT_OUT_HELP
from pyflightstream.run._mark_converged import add_mark_converged_parser, add_mark_parsers
from pyflightstream.run._mark_converged import cmd_mark_converged as cmd_mark_converged
from pyflightstream.workspace.cli import take_settings, withhold_defaults

# Re-exported through this public import path.
from pyflightstream.workspace.costs import select_cost_file as select_cost_file

# Re-exported through this public import path.
from pyflightstream.workspace.hpc import select_hpc_profile as select_hpc_profile
from pyflightstream.workspace.ledger import SIMS_IDS_HELP, listed_sims
from pyflightstream.workspace.naming import MATRIX_POINT_NAME


def _whole_sims(args: argparse.Namespace) -> list[str]:
    """Read the ids of ``delete-sims``, refusing a run id alias (FR-395)."""
    manifest = getattr(args, "runs", None) or "runs.json"
    legacy = getattr(args, "legacy_sims", None)
    if legacy is not None:
        from pyflightstream._deprecations import DELETE_SIMS_POSITIONAL
        from pyflightstream._errors import PyflightstreamDeprecationWarning, warn

        if args.sims is not None:
            raise ValueError("choose --sims or the deprecated positional selector, not both")
        warn(DELETE_SIMS_POSITIONAL.message(), PyflightstreamDeprecationWarning, stacklevel=2)
    selected = args.sims if args.sims is not None else legacy
    if not selected:
        raise ValueError("delete-sims requires --sims ID [ID ...]")
    return split_typed_ids(
        listed_sims(selected), args.workspace, manifest=manifest, whole_only=True
    )[0]


def _parse_workflows(pairs: list[str]) -> dict[str, str]:
    """Resolve repeated ``CODE=NAME`` options before any input file is opened."""
    workflows: dict[str, str] = {}
    for item in pairs:
        code, separator, name = item.partition("=")
        if not separator or not code.strip() or not name.strip():
            raise CampaignConfigError(
                "workflow (CLI: --workflow) expects CODE=NAME (the FS_SCRIPT code and the "
                f"run type it maps to), got {item!r}; the registered types are "
                f"{', '.join(workflow_names())}"
            )
        resolve_workflow(name.strip())
        workflows[code.strip()] = name.strip()
    return workflows


def collect_interval_error(value: float | None) -> str | None:
    """Return the refusal for an invalid settle interval from arguments or settings."""
    if value is not None and not 0.0 < value < float("inf"):
        return f"interval (CLI: --interval) takes a number of seconds above 0, not {value}"
    return None


def _a_word_that_means_false(word: str) -> bool:
    """Read a flag's word as a choice, so `false` at the shell means False.

    A THREE-STATE FLAG WRITTEN AS ONE, because the requirement asks to be able to
    pass FALSE and argparse's ``store_true`` cannot: bare, the flag is
    true; with a word, the word decides; absent, the default stands.

    A WORD OUTSIDE THE VOCABULARY IS REFUSED, through the same reader the
    row variable uses. argparse turns the ArgumentTypeError into a usage
    error naming the flag and the word, so `--ignore-missing-families off`
    and `--ignore-missing-families flase` say what is wrong instead of
    quietly meaning yes. It is also what turns
    `--ignore-missing-families matrix.fs`, where the optional value eats
    the positional, from "the following arguments are required: matrix"
    into a message about the word that was eaten.
    """
    try:
        return read_a_choice(word, context="--ignore-missing-families")
    except ValueError as error:
        raise argparse.ArgumentTypeError(str(error)) from None


def _batch_count(text: str) -> int:
    """Parse the N of ``--batch N``: a whole number of at least 1."""
    try:
        value = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"batch (CLI: --batch) takes a whole number, not {text!r}"
        ) from None
    if value < 1:
        raise argparse.ArgumentTypeError(
            f"batch (CLI: --batch) takes a whole number of at least 1, not {value}"
        )
    return value


def _rounds(text: str) -> int:
    """Parse the N of ``collect --rounds N``: a whole number of at least 1 (PFS-2097.009)."""
    try:
        value = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"rounds (CLI: --rounds) takes a whole number, not {text!r}"
        ) from None
    if value < 1:
        raise argparse.ArgumentTypeError(
            f"rounds (CLI: --rounds) takes a whole number of at least 1, not {value}"
        )
    return value


def _matrix_stem(text: str) -> str:
    """Read ``restore --matrix`` as rebuild and post read it: a matrix path or its stem."""
    return Path(text).stem


def _add_grouping_arguments(parser: argparse.ArgumentParser) -> None:
    """Declare --polar-sweep and --batch N of ``plan`` and ``run``.

    Mutually exclusive: a run is one grouping or the other, never both.
    """
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--polar-sweep",
        action="store_true",
        help="run each simulation's points as ONE solver job (one polar per job). Combines "
        "with --local; " + GROUPED_LEFT_OUT_HELP,
    )
    group.add_argument(
        "--batch",
        type=_batch_count,
        metavar="N",
        help="run the simulations' points as N solver jobs, polars split across them. "
        "Combines with --local; " + GROUPED_LEFT_OUT_HELP,
    )


def _add_selection_arguments(parser: argparse.ArgumentParser) -> None:
    """Declare --sims and --points of ``plan`` and ``run`` (FR-326, P0340-RUN-ONE-POINT).

    The one home of the spelling, so the two commands take the same selection: a
    simulation (POL), or a simulation and some of its points, planned or run without
    the matrix being edited.
    """
    _add_sim_ids(
        parser,
        help="plan or run only these simulations, by their ids as the matrix spells them "
        "(for example --sims 2031 2032 2033); every other simulation is left untouched. "
        "With `run --force-rerun-all`, the simulations to redo. An id the matrix does not "
        "carry is refused before anything runs",
    )
    parser.add_argument(
        "--points",
        dest="points",
        nargs="+",
        metavar="POINT",
        default=None,
        help="with --sims, plan or run only these points of those simulations, by the "
        "point name the plan prints for each, or by its run id alias <sim>_<index> (2006_3, "
        "which names its simulation; the plan prints each); the matrix file is not edited and "
        "no other point is planned, staged or run. A point the matrix does not carry is refused "
        "before anything runs",
    )


def _add_the_missing_family_choice(parser: argparse.ArgumentParser) -> None:
    """Declare --ignore-missing-families and its refusal alternative.

    The choice is a property of this plan or run invocation, not a stored
    campaign declaration (PFS-2035.13).
    """
    parser.add_argument(
        "--ignore-missing-families",
        type=_a_word_that_means_false,
        nargs="?",
        const=True,
        # NOT STATED IS `None`, NOT `True`. With `True` as the default, a
        # command writing `--no-ignore-missing-families --ignore-missing-families
        # true` states two contradicting choices and the reader could not
        # tell the second one from silence, so it resolved the contradiction
        # instead of refusing it. The default the USER sees is still true;
        # it is applied by `_the_missing_family_choice`, which is the one
        # reader of the pair.
        default=None,
        metavar="true|false",
        help="whether a family the opened mesh does not carry is left out "
        "(the default, true) or REFUSES the point (false). One artifact "
        "serves a wing-body and an isolated rotor because a family the "
        "geometry lacks is skipped; pass false when you believe this "
        "geometry carries every family the artifact names and want to hear "
        "about it if it does not (PFS-2035.13)",
    )
    # Provide a bare refusal flag for the effect-changing choice. The
    # positive flag defaults true, so its false value remains another
    # way to request the same missing-family refusal.
    parser.add_argument(
        "--no-ignore-missing-families",
        dest="refuse_missing_families",
        action="store_true",
        help="the same choice as --ignore-missing-families false, written as "
        "a flag: a family the opened mesh does not carry REFUSES the point "
        "instead of being left out. Stating both is refused",
    )


def _add_console_arguments(parser: argparse.ArgumentParser, verbose_help: str) -> None:
    """Add ``--verbose`` and ``--log-level`` (FR-997), one choice of the console level."""
    console = parser.add_mutually_exclusive_group()
    console.add_argument("--verbose", action="store_true", help=verbose_help)
    console.add_argument(
        "--log-level",
        dest="log_level",
        choices=CONSOLE_LEVELS,
        default=None,
        help="how much the console says: quiet (the errors, the final summary line and the "
        "signature), normal (the default) or verbose (as --verbose); logs/activity.log keeps "
        "the full detail at every level. Default: [log] console of pyfs.local.toml or "
        "pyfs.toml, else normal",
    )


def _add_switch(
    parser: argparse.ArgumentParser, flag: str, help_text: str, *, no_help: str = ""
) -> None:
    """Add a settable switch and its ``--no-`` form, one choice of it (FR-996)."""
    name = flag.removeprefix("--").replace("-", "_")
    switch = parser.add_mutually_exclusive_group()
    switch.add_argument(flag, dest=name, action="store_true", help=help_text)
    switch.add_argument(
        f"--no-{flag.removeprefix('--')}",
        dest=name,
        action="store_false",
        default=False,
        help=no_help
        or f"the opposite of {flag} for this command, whatever pyfs.toml or pyfs.local.toml states",
    )


#: The help of ``--no-accept-unregistered-build``, the one negation two routes answer to.
_NO_ACCEPT_HELP = (
    "refuse an installed build other than the registered one for this command, whatever "
    "pyfs.toml, pyfs.local.toml or a build entry of inputs/executables.local.toml states"
)


def _add_common_arguments(parser: argparse.ArgumentParser, *, hpc: bool = False) -> None:
    if hpc:
        _add_hpc_argument(parser)
    parser.add_argument("matrix", help="the pipe-delimited run matrix file")
    parser.add_argument(
        "--name",
        default=None,
        help="campaign name; without it the workspace directory's name is the campaign's "
        "(PFS-2029.03)",
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


class _InvokedParser(argparse.ArgumentParser):
    """The parser, which keeps the command line it was given as ``invoked_argv`` (FR-327)."""

    def parse_args(  # type: ignore[override]
        self, args: Sequence[str] | None = None, namespace: argparse.Namespace | None = None
    ) -> argparse.Namespace:
        """Parse as :class:`argparse.ArgumentParser` does, and record what was parsed."""
        parsed = super().parse_args(args, namespace)
        parsed.invoked_argv = list(sys.argv[1:] if args is None else args)
        return parsed


def parsed(parser: argparse.ArgumentParser, argv: Sequence[str] | None) -> argparse.Namespace:
    """Parse a ``pyfs-matrix`` command line, taking what it does not state from the files (FR-436).

    An option typed wins over ``pyfs.local.toml``, which wins over ``pyfs.toml``,
    which wins over the package default; a file the reader refuses stops the
    command, exit 2, before anything is written.
    """
    with withhold_defaults(parser, argv) as held:
        args = parser.parse_args(argv)
    take_settings(parser, args, held)
    _select_for_this_invocation(args)
    return args


def _select_for_this_invocation(args: argparse.Namespace) -> None:
    """Select ``--hpc`` and ``--cost-file`` for THIS command alone (PFS-2094.008).

    After the parse and the settings files, never as a side effect of argparse
    reading the flag: the selection is restored when the command ends, so a
    later command in the same process does not inherit it.
    """
    hpc = getattr(args, "hpc", None)
    if hpc is not None:
        for_this_invocation(_SELECTED_HPC, hpc)
    cost_file = getattr(args, "cost_file", None)
    if cost_file is not None:
        for_this_invocation(_SELECTED_COST_FILE, Path(cost_file).stem)


def resume_hint(argv: Sequence[str]) -> str:
    """Return the sentence naming the command that continues a refused second run (FR-327).

    The command is the one invoked, every argument kept, with ``--resume`` added, quoted for
    the shell it was typed in: the Windows command-line rule on Windows and the POSIX rule
    elsewhere. Nothing is asked of the user; a run may be detached or scripted.
    """
    words = ["pyfs-matrix", *argv, "--resume"]
    line = subprocess.list2cmdline(words) if os.name == "nt" else shlex.join(words)
    return f"To continue with the points that are new, run:\n  {line}"


def _build_parser() -> argparse.ArgumentParser:
    parser = _InvokedParser(
        prog="pyfs-matrix",
        description=(
            "Run-matrix tooling: the matrix is a first-class interface of the "
            "file-managed modality, with the matrix as the sole campaign declaration."
        ),
    )
    subparsers = parser.add_subparsers(dest="subcommand", required=True)
    _add_workspace_parsers(subparsers)
    _add_storage_parsers(subparsers)
    _add_records_parsers(subparsers)
    _add_plan_parsers(subparsers)
    _add_run_parsers(subparsers)
    _add_run_option_parsers(subparsers)
    _add_collect_parsers(subparsers)
    _add_post_parsers(subparsers)
    _add_post_selection_parsers(subparsers)
    _add_degenerate_parsers(subparsers)
    _add_query_parsers(subparsers)
    add_mark_converged_parser(subparsers)  # FR-414
    add_mesh_parsers(subparsers)  # FR-426
    return parser


#: The commands that take ``--runs NAME``, the manifest they read.
_RUNS_COMMANDS = ("post", "collect", "free-space", "delete-sims", "sync")


def _add_records_parsers(subparsers: Any) -> None:
    """Register ``restore``, ``rebuild``, ``mark-failed`` and ``mark-converged``."""
    workspace_help = "the workspace root carrying runs.json (default: the current directory)"
    apply_help = "change files; without it the command previews and changes nothing"
    restore = subparsers.add_parser(
        "restore",
        help="restore runs.json or another records file from archive/ (preview unless --apply)",
    )
    restore.add_argument("kind", choices=run_records.RESTORE_KINDS, help="the file to restore")
    restore.add_argument("--workspace", default=".", help=workspace_help)
    restore.add_argument("--stamp", default=None, help="the archive stamp to restore from")
    restore.add_argument(
        "--matrix",
        type=_matrix_stem,
        default=None,
        metavar="MATRIX",
        help="for products and plan: the matrix whose file to restore, when several have "
        "archives; its file path or its stem, as rebuild and post read it",
    )
    restore.add_argument("--apply", action="store_true", help=apply_help)
    rebuild = subparsers.add_parser(
        "rebuild",
        help="rebuild run records from the folders under sims/ (preview unless --apply)",
    )
    rebuild.add_argument("--workspace", default=".", help=workspace_help)
    rebuild.add_argument(
        "--out",
        metavar="NAME",
        default=None,
        help="the manifest file the rebuilt records go to, directly in the workspace root",
    )
    rebuild.add_argument(
        "--all-sims",
        dest="all_sims",
        action="store_true",
        help="rebuild every simulation folder on disk, recorded or not",
    )
    _add_sim_ids(rebuild, help=SIMS_IDS_HELP)
    rebuild.add_argument(
        "--build-alias",
        dest="build_alias",
        action="append",
        default=[],
        metavar="BUILD=ALIAS",
        help="the scheduler name of a solver build (repeatable)",
    )
    rebuild.add_argument("--matrix", default=None, help="the matrix the simulations ran from")
    rebuild.add_argument(
        "--inputs-from",
        dest="inputs_from",
        default=None,
        metavar="FOLDER",
        help="another origin's inputs/ folder, laid over this workspace's for inputs that "
        "changed after the run; each record names the inputs taken from it",
    )
    rebuild.add_argument("--apply", action="store_true", help=apply_help)
    add_mark_parsers(subparsers, workspace_help=workspace_help, apply_help=apply_help)


def _add_query_parsers(subparsers: Any) -> None:
    """Register read-only query verbs whose options live beside their commands."""
    add_query_parsers(subparsers)


def _add_workspace_parsers(subparsers: Any) -> None:
    """Add the workspace inventory command."""
    add_inventory_parser(subparsers)


def _add_degenerate_parsers(subparsers: Any) -> None:
    """Add the subcommand that derives a degenerate geometry from a mesh: degenerate (FR-330)."""
    add_degenerate_parser(subparsers)


def _hpc_profile_name(name: str) -> str:
    """Read the HPC profile ``name``; :func:`parsed` selects it for the command alone."""
    if not name.strip():
        raise argparse.ArgumentTypeError(
            "names no profile; give the stem of inputs/hpc/<NAME>.toml"
        )
    return name


def _cost_file_name(name: str) -> str:
    """Read the cost file ``name``; :func:`parsed` selects it for the command alone."""
    if not name.strip():
        raise argparse.ArgumentTypeError("names no file; give the stem of inputs/costs/<NAME>.toml")
    return name


def _add_hpc_argument(parser: argparse.ArgumentParser) -> None:
    """Add ``--hpc NAME``: which HPC profile a several-profile workspace uses."""
    parser.add_argument(
        "--hpc",
        type=_hpc_profile_name,
        default=None,
        metavar="NAME",
        help="the HPC profile inputs/hpc/<NAME>.toml to use when the workspace holds several",
    )


def _add_the_cost_arguments(plan: Any) -> None:
    """Add the cost options of the plan subcommand."""
    plan.add_argument(
        "--cost",
        action="store_true",
        help="also table what each polar is expected to cost: mesh size, marked "
        "trailing edges, farfield layers, viscous coupling, steady or unsteady, "
        "time iterations, processors set, and an EXPECTED wall time fitted from "
        "this workspace's own recorded runs. The time is an extrapolation and the "
        "table says so, carrying the number of samples behind it; a point with no "
        "comparable recorded run reads 'unknown' rather than a number with no basis",
    )
    plan.add_argument(
        "--cost-file",
        type=_cost_file_name,
        default=None,
        metavar="NAME",
        help="the cost file inputs/costs/<NAME>.toml that prices the points when the "
        "workspace holds several; a single file needs no name",
    )


def _add_plan_parsers(subparsers: Any) -> None:
    """Add the plan subcommand."""
    plan = subparsers.add_parser(
        "plan",
        aliases=["inspect-setups"],
        help="bind the matrix to the workspace input library and pre-flight every "
        "point, executing nothing. REQUIRED BEFORE `run`: it writes "
        "the receipt that command asks for, pinned to the digest of the matrix it "
        "read",
    )
    _add_common_arguments(plan, hpc=True)
    plan.add_argument(
        "--setup-guidelines",
        action="store_true",
        help="write inputs/setups/SETUP_GUIDELINES.md, preserving existing edits",
    )
    plan.add_argument(
        "--setup-standards",
        action="store_true",
        help="write commented s9XX setup standards, preserving existing edits",
    )
    _add_the_missing_family_choice(plan)
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
        "is P<sim>-<point name>, the point name writing every variable the row's "
        "flight condition declares, in its order; {point}, {alpha}, {beta}, "
        "{mach}, {advance_ratio}, {sim} and {campaign} are the other placeholders "
        "(PFS-2029.19)",
    )
    plan.add_argument(
        "--fs-exe",
        help="explicit executable override; mandatory for MANUAL rows, otherwise the "
        "FS_BUILD column resolves through inputs/executables.toml",
    )
    _add_the_cost_arguments(plan)
    plan.add_argument(
        "--inflow-fft",
        action="store_true",
        help="for every qsteady_rotor WHEEL point in a custom inflow, read the inflow's "
        "harmonic content as ONE BLADE meets it over a revolution (nP counts how many times "
        "one blade meets the perturbation per turn, in the blade's frame; not the N P a fixed "
        "surface or a balance under the whole rotor sees, where only multiples of N P "
        "survive): per point k_eff = n95 k_1P (min, max, mean, per cent of the span above "
        "0.1), n_max and the suggested PASSAGE_POSITIONS >= n_max / N + 1, WARNED when the "
        "row states fewer; the reduced-frequency warning then reads k_eff",
    )
    plan.add_argument(
        "--update-ids",
        "--updateIDs",
        dest="update_ids",
        action="store_true",
        help="before planning, REWRITE THIS MATRIX so that none of its POLs repeats one "
        "stated elsewhere in the workspace or earlier in this file: each repeated row takes "
        "the next free POL above every POL, run record and sims/ folder of the workspace, "
        "and every other matrix is left as it is. Each change is printed. A row whose POL "
        "already has runs of this matrix is refused rather than moved. THE RENUMBERING IS "
        "WRITTEN BEFORE THE PLAN RUNS and stays written if the plan then refuses",
    )
    _add_switch(plan, "--accept-unregistered-build", _ACCEPT_HELP, no_help=_NO_ACCEPT_HELP)
    _add_selection_arguments(plan)
    _add_grouping_arguments(plan)
    _add_console_arguments(
        plan,
        "print every warning in Python's full format (file, line and source) and the "
        "started and finished lines of the stages printed only on request, such as "
        "[continuation]; logs/activity.log holds them either way",
    )


def _add_run_parsers(subparsers: Any) -> None:
    """Add the run subcommand."""
    run = subparsers.add_parser(
        "run",
        help="run every active point of the matrix and write the sweep table",
        description=(
            "Runs every active point of the matrix and writes the sweep table. "
            "THIS NEEDS A PLAN: run `pyfs-matrix plan <matrix>` "
            "first and this command will not release without it. The plan is "
            "where the warning is, and it is pinned to the matrix it read, so a "
            "matrix edited after it was planned is planned again rather than run "
            "against a receipt about a different study. The plan spends no "
            "solver time."
        ),
    )
    _add_common_arguments(run, hpc=True)
    _add_the_missing_family_choice(run)
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
        "is P<sim>-<point name>, the point name writing every variable the row's "
        "flight condition declares, in its order; {point}, {alpha}, {beta}, "
        "{mach}, {advance_ratio}, {sim} and {campaign} are the other placeholders "
        "(PFS-2029.19)",
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
        "--force-rerun",
        dest="force_rerun",
        action="append",
        default=[],
        metavar="POINT",
        help="REDO this point, which is already in the manifest, for a row that was "
        "wrong. Name it by its point name, by the full run_id the refusal printed, or "
        "by the JOB id of a swept steady row, which is what that refusal prints for "
        "one and which names every point of it, because a job is indivisible; "
        "repeat the flag for several. The manifest is copied to archive/runs-<stamp>.json, "
        "the named records leave it, and each point's collected outputs move into that "
        "point's own archive/<stamp>/ before it runs; NOTHING IS DELETED. It names points "
        "rather than being a switch because redoing a whole matrix over one wrong row "
        "spends a licensed seat per point, and a seat is what archiving cannot give back. "
        "A name no recorded point carries is refused. This is NOT --resume, which SKIPS "
        "such a point instead of redoing it, and the two together are refused",
    )
    run.add_argument(
        "--force-rerun-all",
        dest="force_rerun_all",
        action="store_true",
        help="REDO every recorded point of the matrix, or of the simulations --sims names: "
        "each is archived as --force-rerun archives it and runs again, a recorded steady "
        "job as one job. The count of points and jobs, which is the licences it spends, is "
        "printed before anything runs. Refused with --resume and with --force-rerun",
    )


def _add_run_option_parsers(subparsers: Any) -> None:
    """Add the later options of the run subcommand."""
    run = subparsers.choices["run"]
    run.add_argument(
        "--progress-every",
        dest="progress_every",
        type=int,
        default=10,
        metavar="N",
        help="on a local unsteady point, say how far the run is every N completed time "
        "steps, read from the run's own step counter (default 10; 0 says nothing)",
    )
    _add_selection_arguments(run)
    _add_grouping_arguments(run)
    run.add_argument(
        "--sweep-csv",
        help="write the campaign sweep table here (default: "
        "post/<matrix stem>/campaign_sweep.csv in the workspace, so each matrix of a "
        "workspace keeps its own; the run writes that one file and never a second copy "
        "of it under another name)",
    )
    _add_switch(
        run,
        "--local",
        "run every point on THIS machine instead of submitting it. Linux is the "
        "cluster (FR-99): a workspace carrying a submission profile submits from Linux "
        "and runs locally on Windows, with no cell to remember. This flag keeps a Linux "
        "run local, for a workstation or a smoke test on the machine itself; the "
        "executable resolves as on Windows (the FS_BUILD column through "
        "inputs/executables.toml, or --fs-exe) and every record's executor entry says "
        "forced_local. It changes nothing on a machine that would not have submitted",
    )
    _add_switch(run, "--accept-unregistered-build", _ACCEPT_HELP, no_help=_NO_ACCEPT_HELP)


#: The help of ``--accept-unregistered-build``, which ``plan`` and ``run`` share.
_ACCEPT_HELP = (
    "run on an installed FlightStream build other than the one registered for the "
    "version a row names, instead of refusing it: its compatibility is then YOUR "
    "responsibility, the run warns, and every record says the flag was used and carries "
    "the build the solver printed. `plan` launches no solver and records the flag in "
    "plan.json, so it rehearses the same command line `run` executes"
)


def _add_collect_parsers(subparsers: Any) -> None:
    """Add the collect subcommand."""
    collect = subparsers.add_parser(
        "collect",
        help="collect a submitted job's outputs when they land, then post (FR-99)",
        description=(
            "Sweeps every SUBMITTED record of runs.json and, for each, waits until the "
            "outputs that point declared are PRESENT AND SETTLED, then collects them, "
            "assesses the run and rewrites the record with what it did. It watches the "
            "WORKSPACE and not the scheduler, so it needs no status command in the "
            "submission profile and serves a cluster job, a local run somebody "
            "interrupted, and outputs dropped in by hand alike. A file EXISTS BEFORE IT "
            "IS FINISHED, so settled means size and modification time stable across two "
            "observations AND every declared output present, the last of which is the "
            "log. One sweep by default; --watch loops until nothing is outstanding."
        ),
    )
    _add_hpc_argument(collect)
    collect.add_argument(
        "--workspace",
        default=".",
        help="managed campaign root carrying runs.json (default: the current directory)",
    )
    _add_switch(collect, "--check-frozen", _CHECK_FROZEN_HELP)
    collect.add_argument(
        "--watch",
        action="store_true",
        help="keep sweeping until no submitted point is outstanding, instead of once",
    )
    collect.add_argument(
        "--discard-walltime",
        action="store_true",
        help="mark each WALLTIME_REACHED point FAILED_MARKED, outputs kept. A grouped plan takes "
        "it again from the start automatically; a default-mode plan needs --force-rerun",
    )
    collect.add_argument(
        "--interval",
        type=float,
        default=None,
        help="seconds between the two observations that decide settled (default: 2)",
    )
    collect.add_argument(
        "--watch-interval",
        dest="watch_interval",
        type=float,
        default=None,
        help="seconds between sweeps under --watch (default: 60)",
    )
    collect.add_argument(
        "--rounds",
        type=_rounds,
        default=None,
        help="stop a watch after this many sweeps, whatever is still outstanding",
    )
    collect.add_argument(
        "--no-post",
        dest="post",
        action="store_false",
        help="collect and do NOT rebuild the products, which is the half a reader wants "
        "when the products are built somewhere else",
    )
    _add_sim_ids(
        collect,
        help="sweep only the SUBMITTED records of these simulations, comma separated as "
        "delete-sims takes them (2006,2007 or [2006,2007]); every other record is left "
        "untouched and is not counted as outstanding, and the post that follows is limited "
        "to the same simulations. An id no record carries is refused before anything is swept",
    )
    collect.add_argument(
        "--archive",
        action="store_true",
        help="keep replaced post products in archive/; without it overwrite in place (FR-397)",
    )


#: The help of ``--check-frozen``, which ``collect`` and ``post`` share.
_CHECK_FROZEN_HELP = (
    "REFUSE instead of WARN for averages touched by a frozen solve or "
    "an unread native-log block. By default computable products are written "
    "and post.log warns. Both modes write post.log and post.log.json with the "
    "point, product, step and remedy; refusals are also named in products.json"
)


def _add_post_parsers(subparsers: Any) -> None:
    """Add the post subcommand."""
    post = subparsers.add_parser(
        "post",
        help="rebuild the post-processed CSV products from the manifest, with no solver",
        description=(
            "Reads runs.json and the collected exports of every successful point and writes "
            "the polar, section and plot tables under post/<matrix stem>/, exactly as `run` "
            "left them; needs no executable and spends no seat (PFS-2029.15.03). Given a "
            "matrix, rebuilds that matrix's products; given none, every matrix the manifest "
            "names, and the records naming none under post/products. EXCEPT with "
            "--additional-pproc, which first reopens the final saved simulation of every "
            "recorded point whose row states ADDITIONAL_PPROC, one solver launch per point "
            "and no solve, extracts that pproc into datapoints/DP-<point>/additional/<pid>/ "
            "and records it in additional.json; runs.json is never written. "
            "By default, rebuilds overwrite products in place without an archive."
        ),
    )
    post.add_argument(
        "--additional-pproc",
        dest="additional_pproc",
        action="store_true",
        help="before the products, reopen the final .fsm of every recorded point whose row "
        "states ADDITIONAL_PPROC: p<id>, with no solve, and extract that pproc: its section "
        "distributions, the sections and their sectional loads, the loads, the surface "
        "exports it selects, the log, and on an unsteady point the plots history (one "
        "instant, the last). A point without the key, without its .fsm, or whose .fsm does "
        "not hash as its record says is skipped by name. Needs the matrix and the "
        "executable its rows name; one solver launch per point. 26.124 only (RPT-062)",
    )
    post.add_argument(
        "--fs-version",
        default=None,
        help="with --additional-pproc: the version rows whose FS_BUILD cell is empty fall "
        "back to, as for `run`",
    )
    post.add_argument(
        "--fs-exe",
        default=None,
        help="with --additional-pproc: the explicit executable override, as for `run`",
    )
    _add_switch(
        post,
        "--local",
        "with --additional-pproc: reopen the saved simulations on THIS machine, as "
        "`run --local` runs there; the submitting half of the additional post is not built, "
        "so a workspace that submits from here is refused without it",
    )
    post.add_argument(
        "--recipe",
        action="append",
        default=[],
        metavar="CODE=MODULE:FUNCTION",
        help="with --additional-pproc: a LEGACY row's recipe code (repeatable), so a matrix "
        "mixing LEGACY rows with rows naming a run type binds as it did for `run`",
    )
    _add_switch(post, "--check-frozen", _CHECK_FROZEN_HELP)
    post.add_argument(
        "matrix",
        nargs="?",
        help="the run matrix whose products to rebuild, matched by its file stem against "
        "the records of runs.json (default: every matrix the manifest names)",
    )
    post.add_argument(
        "--workspace",
        default=".",
        help="managed campaign root carrying runs.json and the inputs/ library (default: "
        "the current directory)",
    )


def _add_post_selection_parsers(subparsers: Any) -> None:
    """Add the later options of post, and the options it shares with run and collect."""
    post = subparsers.choices["post"]
    # One keeps a copy of what a rebuild replaces and the other keeps none.
    keeping = post.add_mutually_exclusive_group()
    keeping.add_argument(
        "--archive",
        action="store_true",
        help="keep the files a rebuild replaces: MOVE them into "
        "post/<matrix>/archive/<day and hour>/ before writing",
    )
    keeping.add_argument(
        "--force-overwrite",
        dest="force_overwrite",
        action="store_true",
        help="Overwrite without an archive; this option adds a confirmation before rebuilding. "
        "Pass --yes to confirm in a script.",
    )
    post.add_argument(
        "--yes",
        action="store_true",
        help="Answer the --force-overwrite confirmation in a script; requires --force-overwrite.",
    )
    post.add_argument(
        "--strict",
        action="store_true",
        help="exit 3 when any simulation's product was skipped by design (a polar under "
        "sideslip, for one), after every product is written in full; without it a "
        "recorded skip is named on stderr with a count, its reasons printed by "
        "--diagnostics, and the exit is 0, since everything producible was "
        "produced. 2 stays the code of a refusal that wrote nothing",
    )
    run, collect = subparsers.choices["run"], subparsers.choices["collect"]
    for command_parser in (run, post, collect):
        _add_switch(command_parser, "--pproc-warnings", "print grouped post-processing warnings")
        _add_console_arguments(
            command_parser,
            "print every warning in Python's full format (file, line and source) and "
            "one line per item where a repeated warning is otherwise counted in one line, "
            "and the [continuation] started and finished lines; "
            "logs/activity.log holds the full detail either way",
        )
    post.add_argument(
        "--diagnostics",
        action="store_true",
        help="print recorded post diagnostics as Markdown without changing products",
    )
    _add_sim_ids(
        post,
        help="rebuild only these simulations' products of the matrix, comma separated as "
        "delete-sims takes them (2006,2007 or [2006,2007]), using the archive policy above; "
        "every other simulation's files and "
        "products.json entries "
        "stay as they were, and the super files, whose columns are the union over every "
        "simulation, are left as the last whole post wrote them and named under "
        "partial.not_rebuilt in products.json and in post.log. An id with no record of the "
        "matrix is refused before anything is written",
    )
    for name in _RUNS_COMMANDS:  # The manifest a command reads (B1, B3).
        subparsers.choices[name].add_argument(
            "--runs",
            metavar="NAME",
            default=None,
            help="the manifest file to read, directly in the workspace root (default: runs.json)",
        )
    post.add_argument(  # Post from the simulation folders (B3).
        "--from-sims",
        dest="from_sims",
        action="store_true",
        help="ignore runs.json and assemble the records in memory from sims/, for points run "
        "outside the package; the products go to post/<matrix>@sims/",
    )
    post.add_argument(
        "--steps-per-revolution",
        dest="steps_per_revolution",
        type=float,
        metavar="N",
        default=None,
        help="with --from-sims: the solver steps of one revolution, for a LAST_REVS_AVG window",
    )
