"""The ``pyfs-matrix`` argument parser: every subcommand, option and help text.

Private to :mod:`pyflightstream.run.cli`, which builds the parser through
:func:`_build_parser` and dispatches the parsed command. The builders live
apart from the commands they parse for so that the command line's own module
stays within the review lens (GOAL-038, AD-14): the parser is declarative
and long, the commands are the logic. The storage and records subcommands
(``space-in-use``, ``free-space``, ``delete-sims``, ``sync``, ``restore``,
``rebuild``, ``mark-failed``) are added by their own builders, and every
command that reads a manifest takes ``--runs NAME`` from one list.
"""

from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys
from collections.abc import Sequence
from typing import Any

from pyflightstream.cases.workflows import (
    read_a_choice,
    workflow_names,
)
from pyflightstream.run import records as run_records
from pyflightstream.workspace.hpc import select_hpc_profile
from pyflightstream.workspace.naming import (
    MATRIX_POINT_NAME,
)


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


def _add_grouping_arguments(parser: argparse.ArgumentParser) -> None:
    """Declare --polar-sweep and --batch N of ``plan`` and ``run`` (0.35.0).

    Mutually exclusive: a run is one grouping or the other, never both.
    """
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--polar-sweep",
        action="store_true",
        help="run each simulation's points as ONE solver job (one polar per job). Combines "
        "with --local; unsteady rows only",
    )
    group.add_argument(
        "--batch",
        type=_batch_count,
        metavar="N",
        help="run the simulations' points as N solver jobs, polars split across them. "
        "Combines with --local; unsteady rows only",
    )


def _add_selection_arguments(parser: argparse.ArgumentParser) -> None:
    """Declare --sims and --points of ``plan`` and ``run`` (FR-326, P0340-RUN-ONE-POINT).

    The one home of the spelling, so the two commands take the same selection: a
    simulation (POL), or a simulation and some of its points, planned or run without
    the matrix being edited.
    """
    parser.add_argument(
        "--sims",
        dest="sims",
        nargs="+",
        metavar="SIM",
        default=None,
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
        "point name the plan prints for each; the matrix file is not edited and no other "
        "point is planned, staged or run. A point the matrix does not carry is refused "
        "before anything runs",
    )


def _add_the_missing_family_choice(parser: argparse.ArgumentParser) -> None:
    """Declare --ignore-missing-families, the design of 2026-09-10.

    ON `plan` AND `run` ONLY, and deliberately not on `convert`. The
    choice is a property of THIS INVOCATION and not of an artifact:
    `convert` writes a campaign file that outlives the command that
    wrote it, and a per-invocation choice frozen into a file stops being
    one (PFS-2035.13).
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
    # THE SAME CHOICE, SPELLED SO THE EFFECT-BEARING FORM IS THE BARE ONE.
    # The positive flag's default is already true, so writing it bare does
    # nothing and only `--ignore-missing-families false` acts: a positive
    # name carrying a negative word, which a reader unpicks at the shell and
    # which does not match `post --strict` beside it (the interface lens of
    # the 0.15.0 release review). Both spellings stay, because the reference
    # instruction was that a user be able to pass false.
    parser.add_argument(
        "--no-ignore-missing-families",
        dest="refuse_missing_families",
        action="store_true",
        help="the same choice as --ignore-missing-families false, written as "
        "a flag: a family the opened mesh does not carry REFUSES the point "
        "instead of being left out. Stating both is refused",
    )


def _add_common_arguments(parser: argparse.ArgumentParser, *, hpc: bool = False) -> None:
    if hpc:
        _add_hpc_argument(parser)
    parser.add_argument("matrix", help="the pipe-delimited run matrix file")
    parser.add_argument(
        "--name",
        default=None,
        help="campaign name; without it the workspace directory's name is the campaign's "
        "(PFS-2029.03), and `convert`, which has no workspace, still needs it",
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
            "file-managed modality, with campaign.toml as the canonical internal form."
        ),
    )
    subparsers = parser.add_subparsers(dest="subcommand", required=True)
    _add_workspace_parsers(subparsers)
    _add_storage_parsers(subparsers)
    _add_records_parsers(subparsers)
    _add_convert_parsers(subparsers)
    _add_plan_parsers(subparsers)
    _add_run_parsers(subparsers)
    _add_run_option_parsers(subparsers)
    _add_collect_parsers(subparsers)
    _add_post_parsers(subparsers)
    _add_post_selection_parsers(subparsers)
    _add_degenerate_parsers(subparsers)
    return parser


#: The subcommand's own help, which is read BEFORE a file is named and so
#: cannot know which stages will fire. It says both directions rather than
#: one, because the single unconditional paragraph it replaces said only
#: the frightening one.
_HELP_NOTICE = (
    "What an upgrade moves depends on the layout the file entered at. A file "
    "at the v0.8.x layout crosses the REmi boundary and its numbers will "
    "differ; a file whose SWEEP_TYPE column is folded keeps every run "
    "identity, so a resume still finds its records. The command says which "
    "applied to the file you named."
)


def _add_storage_parsers(subparsers: Any) -> None:
    """Register the four storage subcommands; each also reads as a flag."""
    workspace_help = "the workspace root carrying runs.json (default: the current directory)"
    apply_help = "change files; without it the command previews and changes nothing"
    space = subparsers.add_parser(
        "space-in-use",
        help="report the sizes on disk: by top-level folder, by sims/sim_*, by extension",
        description=(
            "Prints the workspace's sizes in three groupings, in this order: by top-level "
            "folder, by simulation (sims/sim_*, compacted ones included) and by extension. "
            "Changes no file; the call is recorded in storage_management.json."
        ),
    )
    space.add_argument("--workspace", default=".", help=workspace_help)
    space.add_argument("--top", type=int, default=15, help="rows shown per grouping (default: 15)")
    free = subparsers.add_parser(
        "free-space",
        help="run a storage recipe inputs/management/m<id>.toml (preview unless --apply)",
        description=(
            "Runs the recipe's steps in order: [[prune_step_exports]] deletes an unsteady "
            "point's per-step exports (the *_iteration=<step> files) except the last step of "
            "each export, and a later post refuses a product that needs a deleted step, "
            "naming it; [[compact_sims]] zips a simulation folder "
            "into sims/sim_<id>.zip (post, collect and a continuation restore it "
            "automatically), [[delete_extensions]] deletes files of the named extensions "
            "under sims/ except what a later post needs (saved simulations, scripts, logs, "
            "and every file a run record names or hashes), [[post_archives]] compacts or "
            "deletes the archive/<stamp>/ folders the post wrote. Nothing outside sims/ "
            "and the post archives is touched. Every call is recorded in "
            "storage_management.json."
        ),
    )
    free.add_argument("recipe", help="the recipe id, m<id> (inputs/management/m<id>.toml)")
    free.add_argument("--workspace", default=".", help=workspace_help)
    free.add_argument("--apply", action="store_true", help=apply_help)
    free.add_argument(
        "--list",
        dest="list_paths",
        action="store_true",
        help="after each step, print every path it would touch (preview) or touched "
        "(--apply) with its size and what happens to it",
    )
    delete = subparsers.add_parser(
        "delete-sims",
        help="delete simulations, their post products and their records (preview unless --apply)",
        description=(
            "Deletes each named simulation: its sims/sim_<id> folder (or zip), its own post "
            "products and its records in runs.json, which keeps one note row per "
            "simulation saying its id belonged to a deleted one. The full mention (id, "
            "matrix, run ids, statuses, dates, sizes and hashes, caller) is recorded in "
            "storage_management.json. The id may be reused afterwards. A product that "
            "mixes the deleted points with others needs --matrix-products: points-only "
            "leaves it, recorded stale; regenerate reruns that matrix's post without them."
        ),
    )
    delete.add_argument("sims", help="simulation ids, comma separated: 4001,2009")
    delete.add_argument("--workspace", default=".", help=workspace_help)
    delete.add_argument(
        "--matrix-products",
        dest="matrix_products",
        choices=("points-only", "regenerate"),
        default=None,
        help="what happens to a matrix product that also holds the deleted points",
    )
    delete.add_argument(
        "--force",
        action="store_true",
        help="delete a simulation whatever the status of its records; without it a "
        "simulation with a run still SUBMITTED is refused",
    )
    delete.add_argument("--apply", action="store_true", help=apply_help)
    sync = subparsers.add_parser(
        "sync",
        help="bring runs and results from the workspaces in inputs/sync-workspaces.toml",
        description=(
            "Levels are cumulative: runs (runs.json and run provenance: scripts/ and the "
            "datapoint logs), post (+ post/), fsm (+ the datapoints' saved simulations), all "
            "(+ everything else under sims/). Run on the main workspace. A record only in "
            "the other workspace is added; a main record still SUBMITTED takes the other's; "
            "any other difference is a conflict where main wins unless --prefer-other. A "
            "simulation still SUBMITTED there syncs its record only. A file conflict keeps "
            "main's copy unless --overwrite, which archives it first. Nothing in main is "
            "deleted and inputs/ is never touched, except a declared matrix. MATRICES: "
            "each is declared in sync-workspaces.toml by the one workspace that owns it "
            '(matrices = ["<stem>", ...]); a difference is always reported as a MERGE '
            "CONFLICT and the owning workspace's copy wins. A synced simulation's "
            "inputs/ is linked into main's own geometry library, never copied. "
            "Every call is recorded in storage_management.json."
        ),
    )
    sync.add_argument("level", choices=("runs", "post", "fsm", "all"), help="what to bring")
    sync.add_argument("--workspace", default=".", help=workspace_help)
    sync.add_argument(
        "--from",
        dest="source",
        default=None,
        help="one workspace name from sync-workspaces.toml (default: every non-main one)",
    )
    sync.add_argument("--apply", action="store_true", help=apply_help)
    sync.add_argument(
        "--prefer-other",
        dest="prefer_other",
        action="store_true",
        help="on a runs.json conflict, take the other workspace's record",
    )
    sync.add_argument(
        "--overwrite",
        action="store_true",
        help="on a file conflict, archive main's copy and take the other's",
    )
    # 0.32.0 (package B2): both off by default.
    sync.add_argument(
        "--restore",
        action="store_true",
        help="with --apply, rebuild the records of the sims/ folders no record carries",
    )
    sync.add_argument(
        "--include-archives",
        dest="include_archives",
        action="store_true",
        help="also bring the files under folders named archive (skipped by default)",
    )


#: The commands that take ``--runs NAME``, the manifest they read (0.32.0).
_RUNS_COMMANDS = ("post", "collect", "free-space", "delete-sims", "sync")


def _add_records_parsers(subparsers: Any) -> None:
    """Register ``restore`` and ``rebuild`` (0.32.0) and ``mark-failed`` (0.33.0, FR-309)."""
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
        default=None,
        metavar="STEM",
        help="for products and plan: the matrix whose file to restore, when several have archives",
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
    rebuild.add_argument("--sims", default=None, help="simulation ids, comma separated: 4001,2009")
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
    mark = subparsers.add_parser(
        "mark-failed",
        help="mark every run record of the named simulations FAILED_MARKED, whatever it "
        "ended in (preview unless --apply)",
        description=(
            "A run can end CONVERGED and be found wrong later. Its records become "
            "FAILED_MARKED, which the post, the re-run and delete-sims treat as any "
            "failure, and each keeps the status it had, when and why under 'marked'; "
            "runs.json is copied to archive/ first (FR-309)."
        ),
    )
    mark.add_argument("--sims", required=True, help="simulation ids, comma separated: 2006,2007")
    mark.add_argument("--reason", default=None, help="why, recorded as given")
    mark.add_argument("--workspace", default=".", help=workspace_help)
    mark.add_argument("--apply", action="store_true", help=apply_help)


def _add_workspace_parsers(subparsers: Any) -> None:
    """Add the subcommands that act on a matrix or a workspace: upgrade, rename, inventory."""
    # FIRST, because it is the subcommand a user meets when a matrix they
    # already have stops being readable. An independent review found the
    # only migration path was a Python call, which a matrix user is
    # precisely the person who does not write: the format broke and the
    # remedy was addressed to somebody else.
    upgrade = subparsers.add_parser(
        "upgrade",
        help=(
            "convert a matrix written under an older layout to the current one "
            "(what moves depends on the layout it entered at, see --help)"
        ),
        description=_HELP_NOTICE,
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

    rename = subparsers.add_parser(
        "rename",
        help="rename a workspace written under 0.20.x to the 0.21.0 point names",
        description=(
            "A point is named by its flight condition since 0.21.0, and a workspace "
            "written before it carries the earlier tag in every run_id, folder and file. "
            "This reads the matrices beside runs.json, works out the new name of every "
            "record from its row and its recorded point, and moves ALL of it: the "
            "datapoint folders, the scripts, the collected files, the manifest and the "
            "plan. It prints every change and a second run makes none. It refuses, "
            "before touching anything, a record whose row is gone, a record whose point "
            "the matrix no longer holds, two records that would share a name, and a "
            "SUBMITTED record whose folder would move: collect those first. See "
            "docs/migrating-to-0.21.0.md."
        ),
    )
    rename.add_argument(
        "--workspace",
        default=".",
        help="managed campaign root carrying runs.json (default: the current directory)",
    )
    rename.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        help="print what would move and change nothing, which is the rehearsal to read "
        "before the workspace is rewritten",
    )

    inventory = subparsers.add_parser(
        "inventory",
        help=(
            "write <stem>.boundaries.toml beside a saved simulation, from its mesh block, "
            "or beside an OBJ, from its groups"
        ),
        description=(
            "Reads the mesh block of a saved simulation and writes its boundary order as "
            "a sidecar beside it; a run whose sidecar disagrees with the file is refused "
            "before the solver starts. Needs no executable (PFS-2029.06.02). For an OBJ "
            "the order is its groups that hold a face, in the order of the file, which is "
            "what a plan writes when the OBJ has no sidecar (G30, RPT-078); an OBJ's "
            "existing sidecar is never rewritten."
        ),
    )
    inventory.add_argument("geometry", help="a saved simulation or an OBJ under inputs/geometries/")
    inventory.add_argument(
        "--overwrite",
        action="store_true",
        help=(
            "rewrite a saved simulation's sidecar that already exists; without it an "
            "existing one is refused"
        ),
    )
    inventory.add_argument(
        "--clean",
        action="store_true",
        help=(
            "remove the unsteady solver actions saved in the simulation, which inventory "
            "otherwise names as a warning, keeping a copy <file>.bak-<stamp> beside it; an "
            "existing sidecar is then kept unless --overwrite (FR-308)"
        ),
    )


def _add_degenerate_parsers(subparsers: Any) -> None:
    """Add the subcommand that derives a degenerate geometry from a mesh: degenerate (FR-330)."""
    degenerate = subparsers.add_parser(
        "degenerate",
        help=(
            "derive a degenerate geometry, the thin blade first, from a blade mesh and write "
            "it beside the source"
        ),
        description=(
            "Derives the thin blade of a blade mesh, the sheet midway between its two sides "
            "from the root to the tip, with the root moved outward along the span by "
            "--root-offset so it does not cross the spinner, and writes it beside the source "
            "as <stem>_thin_blade.obj with its boundary inventory "
            "<stem>_thin_blade.boundaries.toml. The root is the end of the blade nearer the "
            "origin of the mesh's own coordinates. The source is read only; a file holding "
            "more than one boundary needs --boundary. The derived geometry is a modelling "
            "choice: a run confirms what the solver makes of it. Needs no executable."
        ),
    )
    degenerate.add_argument("geometry", help="a blade mesh: a saved simulation or an OBJ")
    degenerate.add_argument(
        "--kind",
        choices=["thin-blade"],
        default="thin-blade",
        help="the degenerate geometry to derive; thin-blade is the one kind of 0.34.0 "
        "(default: %(default)s)",
    )
    degenerate.add_argument(
        "--root-offset",
        type=float,
        required=True,
        metavar="LENGTH",
        help="how far the root of the thin blade is moved outward along the span, a positive "
        "length in the mesh's own unit, shorter than the blade",
    )
    degenerate.add_argument(
        "--boundary",
        metavar="NAME",
        help=(
            "the boundary (an OBJ's group) that is the blade, for a file that also holds a "
            "spinner, a nacelle or other bodies; only its faces are read and the output is "
            "named <stem>_<NAME>_thin_blade; without it a file holding more than one "
            "boundary is refused"
        ),
    )
    degenerate.add_argument(
        "--overwrite",
        action="store_true",
        help="rewrite a thin blade and its inventory that already exist; without it an "
        "existing one is refused",
    )


def _add_convert_parsers(subparsers: Any) -> None:
    """Add the convert subcommand."""
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


def _hpc_profile_name(name: str) -> str:
    """Select the HPC profile ``name`` as argparse reads it, and return it."""
    select_hpc_profile(name)
    return name


def _add_hpc_argument(parser: argparse.ArgumentParser) -> None:
    """Add ``--hpc NAME`` (0.35): which HPC profile a several-profile workspace uses."""
    parser.add_argument(
        "--hpc",
        type=_hpc_profile_name,
        default=None,
        metavar="NAME",
        help="the HPC profile inputs/hpc/<NAME>.toml to use when the workspace holds "
        "several (0.35)",
    )


def _add_plan_parsers(subparsers: Any) -> None:
    """Add the plan subcommand."""
    plan = subparsers.add_parser(
        "plan",
        aliases=["inspect-setups"],
        help="bind the matrix to the workspace input library and pre-flight every "
        "point, executing nothing. REQUIRED BEFORE `run` since v0.17.0: it writes "
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
        "flight condition declares, in its order (0.21.0); {point}, {alpha}, {beta}, "
        "{mach}, {advance_ratio}, {sim} and {campaign} are the other placeholders "
        "(PFS-2029.19)",
    )
    plan.add_argument(
        "--fs-exe",
        help="explicit executable override; mandatory for MANUAL rows, otherwise the "
        "FS_BUILD column resolves through inputs/executables.toml",
    )
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
    plan.add_argument(
        "--accept-unregistered-build",
        dest="accept_unregistered_build",
        action="store_true",
        help="run on an installed FlightStream build other than the one registered for the "
        "version a row names, instead of refusing it: its compatibility is then YOUR "
        "responsibility, the run warns, and every record says the flag was used and carries "
        "the build the solver printed. `plan` launches no solver and records the flag in "
        "plan.json, so it rehearses the same command line `run` executes",
    )
    _add_selection_arguments(plan)
    _add_grouping_arguments(plan)
    plan.add_argument(
        "--verbose",
        action="store_true",
        help="print every warning in Python's full format (file, line and source) and the "
        "started and finished lines of the stages printed only on request, such as "
        "[continuation]; logs/activity.log holds them either way (0.31.0)",
    )


def _add_run_parsers(subparsers: Any) -> None:
    """Add the run subcommand."""
    run = subparsers.add_parser(
        "run",
        help="run every active point of the matrix and write the sweep table",
        description=(
            "Runs every active point of the matrix and writes the sweep table. "
            "SINCE v0.17.0 THIS NEEDS A PLAN: run `pyfs-matrix plan <matrix>` "
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
        "flight condition declares, in its order (0.21.0); {point}, {alpha}, {beta}, "
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
    run.add_argument(
        "--local",
        action="store_true",
        help="run every point on THIS machine instead of submitting it. Linux is the "
        "cluster (FR-99): a workspace carrying a submission profile submits from Linux "
        "and runs locally on Windows, with no cell to remember. This flag keeps a Linux "
        "run local, for a workstation or a smoke test on the machine itself; the "
        "executable resolves as on Windows (the FS_BUILD column through "
        "inputs/executables.toml, or --fs-exe) and every record's executor entry says "
        "forced_local. It changes nothing on a machine that would not have submitted",
    )
    run.add_argument(
        "--accept-unregistered-build",
        dest="accept_unregistered_build",
        action="store_true",
        help="run on an installed FlightStream build other than the one registered for the "
        "version a row names, instead of refusing it: its compatibility is then YOUR "
        "responsibility, the run warns, and every record says the flag was used and carries "
        "the build the solver printed. `plan` launches no solver and records the flag in "
        "plan.json, so it rehearses the same command line `run` executes",
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
    collect.add_argument(
        "--check-frozen",
        action="store_true",
        help=(
            "REFUSE instead of WARN for averages touched by a frozen solve or "
            "an unread native-log block. By default computable products are written "
            "and post.log warns. Both modes write post.log and post.log.json with the "
            "point, product, step and remedy; refusals are also named in products.json"
        ),
    )
    collect.add_argument(
        "--watch",
        action="store_true",
        help="keep sweeping until no submitted point is outstanding, instead of once",
    )
    collect.add_argument(
        "--discard-walltime",
        action="store_true",
        help="mark each WALLTIME_REACHED point FAILED_MARKED after every sweep, before post; "
        "keep its outputs. A grouped plan takes it again from the start automatically; "
        "a default-mode plan needs --force-rerun",
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
        type=int,
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
    collect.add_argument(
        "--sims",
        dest="sims",
        default=None,
        metavar="IDS",
        help="sweep only the SUBMITTED records of these simulations, comma separated as "
        "delete-sims takes them (2006,2007 or [2006,2007]); every other record is left "
        "untouched and is not counted as outstanding, and the post that follows is limited "
        "to the same simulations. An id no record carries is refused before anything is swept",
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
            "and records it in additional.json; runs.json is never written."
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
    post.add_argument(
        "--local",
        action="store_true",
        help="with --additional-pproc: reopen the saved simulations on THIS machine, as "
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
    post.add_argument(
        "--check-frozen",
        action="store_true",
        help=(
            "REFUSE instead of WARN for averages touched by a frozen solve or "
            "an unread native-log block. By default computable products are written "
            "and post.log warns. Both modes write post.log and post.log.json with the "
            "point, product, step and remedy; refusals are also named in products.json"
        ),
    )
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
    post.add_argument(
        "--force-overwrite",
        dest="force_overwrite",
        action="store_true",
        help="DESTROY an existing product instead of archiving it. Since v0.17.0 a "
        "rebuild MOVES what is there into post/<matrix>/archive/<day and hour>/ and "
        "then writes, so nothing is lost and nothing is refused; this is the escape "
        "from that, it keeps no copy, and it asks for a confirmation first. Pass "
        "--yes to answer that confirmation in a script",
    )
    post.add_argument(
        "--yes",
        action="store_true",
        help="answer the --force-overwrite confirmation. Only meaningful with it, and "
        "refused without it: a flag that answers a question nobody asked is a flag "
        "somebody will carry into the run that did ask",
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
        command_parser.add_argument(
            "--pproc-warnings", action="store_true", help="print grouped post-processing warnings"
        )
        command_parser.add_argument(
            "--verbose",
            action="store_true",
            help="print every warning in Python's full format (file, line and source) and "
            "one line per item where a repeated warning is otherwise counted in one line, "
            "and the [continuation] started and finished lines (0.31.0); "
            "logs/activity.log holds the full detail either way",
        )
    post.add_argument(
        "--diagnostics",
        action="store_true",
        help="print recorded post diagnostics as Markdown without changing products",
    )
    post.add_argument(
        "--sims",
        dest="sims",
        default=None,
        metavar="IDS",
        help="rebuild only these simulations' products of the matrix, comma separated as "
        "delete-sims takes them (2006,2007 or [2006,2007]), in place: their files are "
        "archived and rewritten, every other simulation's files and products.json entries "
        "stay as they were, and the super files, whose columns are the union over every "
        "simulation, are left as the last whole post wrote them and named under "
        "partial.not_rebuilt in products.json and in post.log. An id with no record of the "
        "matrix is refused before anything is written",
    )
    for name in _RUNS_COMMANDS:  # 0.32.0 hook: the manifest a command reads (B1, B3)
        subparsers.choices[name].add_argument(
            "--runs",
            metavar="NAME",
            default=None,
            help="the manifest file to read, directly in the workspace root (default: runs.json)",
        )
    post.add_argument(  # 0.32.0 hook: the post from the simulation folders (B3)
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
