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
``pyfs-matrix``, with the same subcommands, the same flags and the same
output, so FR-44's contract is untouched. What moved is the dotted
module path, which a user never writes.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import NoReturn

from pyflightstream._errors import PyflightstreamError
from pyflightstream.cases import CampaignConfigError
from pyflightstream.cases.matrix import MatrixError, convert_matrix, upgrade_matrix
from pyflightstream.cases.workflows import (
    WorkflowCoverageError,
    read_a_choice,
    resolve_workflow,
    workflow_names,
    workflow_registry,
)
from pyflightstream.results import MalformedOutputError
from pyflightstream.results.tables import LoadsNotFoundError, sweep_table, write_table
from pyflightstream.run import SWEEP_TABLE_NAME, CampaignErrors, LoadsAssessor
from pyflightstream.run.matrix import plan_matrix, run_matrix
from pyflightstream.workspace import CampaignWorkspace, InputArtifactError
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


def _add_common_arguments(parser: argparse.ArgumentParser) -> None:
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

    inventory = subparsers.add_parser(
        "inventory",
        help="write <stem>.boundaries.toml beside a saved simulation, from its mesh block",
        description=(
            "Reads the mesh block of a saved simulation and writes its boundary order as "
            "a sidecar beside it; a run whose sidecar disagrees with the file is refused "
            "before the solver starts. Needs no executable (PFS-2029.06.02)."
        ),
    )
    inventory.add_argument("geometry", help="a saved simulation under inputs/geometries/")
    inventory.add_argument(
        "--overwrite",
        action="store_true",
        help="rewrite a sidecar that already exists; without it an existing one is refused",
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
        "is the standard convention, POLAR-<sim>_M<mach*100>AL<alpha*10>BE<beta*10>"
        "[J<J*100>], fixed width; {point}, {alpha}, {beta}, {mach}, {advance_ratio}, "
        "{sim} and {campaign} are the other placeholders (PFS-2029.19)",
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

    run = subparsers.add_parser(
        "run",
        help="run every active point of the matrix and write the sweep table",
    )
    _add_common_arguments(run)
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
        "is the standard convention, POLAR-<sim>_M<mach*100>AL<alpha*10>BE<beta*10>"
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
        help="write the campaign sweep table here (default: "
        "post/<matrix stem>/campaign_sweep.csv in the workspace, so each matrix of a "
        "workspace keeps its own; the run writes that one file and never a second copy "
        "of it under another name)",
    )

    post = subparsers.add_parser(
        "post",
        help="rebuild the post-processed CSV products from the manifest, with no solver",
        description=(
            "Reads runs.json and the collected exports of every successful point and writes "
            "the polar, section and plot tables under post/<matrix stem>/, exactly as `run` "
            "left them; needs no executable and spends no seat (PFS-2029.15.03). Given a "
            "matrix, rebuilds that matrix's products; given none, every matrix the manifest "
            "names, and the records naming none under post/products."
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
    post.add_argument(
        "--overwrite",
        action="store_true",
        help="rewrite products that already exist; without it an existing product is refused",
    )
    post.add_argument(
        "--strict",
        action="store_true",
        help="exit 3 when any simulation's product was skipped by design (a polar under "
        "sideslip, for one), after every product is written in full; without it a "
        "recorded skip is printed and the exit is 0, since everything producible was "
        "produced. 2 stays the code of a refusal that wrote nothing",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run ``pyfs-matrix``; returns the process exit code."""
    args = _build_parser().parse_args(argv)
    # Before the recipe parsing below, deliberately: upgrading a file
    # needs no recipes, no version and no executable, and requiring them
    # would refuse the one user this subcommand exists for.
    if args.subcommand == "post":
        return _cmd_post(args)
    if args.subcommand == "inventory":
        return _cmd_inventory(args)
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


def _cmd_post(args: argparse.Namespace) -> int:
    """Rebuild the products from the manifest alone."""
    from pyflightstream.workspace import post_stages

    workspace = CampaignWorkspace(args.workspace)
    try:
        records = workspace.read_manifest()
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
        written: list[Path] = []
        for matrix in matrices:
            for stage in post_stages():
                written.extend(stage(workspace, overwrite=args.overwrite, matrix_stem=matrix))
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


def _report_skips(workspace: CampaignWorkspace, matrices: list[str | None]) -> int:
    """Print every recorded skip of the given matrices to stderr; return the count.

    Shared by ``post`` and ``run`` (PFS-2031.16, PFS-2031.19): the surface
    that spent the seat says what it skipped too, rather than leaving it
    for a later rebuild to discover.
    """
    import json

    skipped = 0
    for matrix in matrices:
        manifest = workspace.products_dir(matrix) / "products.json"
        if not manifest.is_file():
            continue
        # Keyed by the simulation refused whole, or by the reduction file the
        # row could not window (PFS-2015.04); the key says which.
        for key, reason in (
            json.loads(manifest.read_text(encoding="utf-8")).get("skipped", {}).items()
        ):
            what = key if "/" in key else f"simulation {key}"
            print(
                f"skipped {what} of {matrix or 'the matrix-less records'}: {reason}",
                file=sys.stderr,
            )
            skipped += 1
    return skipped


def _cmd_inventory(args: argparse.Namespace) -> int:
    """Write the boundary inventory sidecar of one saved simulation."""
    from pyflightstream.workspace.inputs import write_inventory

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
        with open(args.output, "w", encoding="utf-8") as handle:
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
    name, name_from = _campaign_name(args)
    try:
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
            ignore_missing_families=_the_missing_family_choice(args),
            cost=getattr(args, "cost", False),  # FR-82
        )
    except (MatrixError, InputArtifactError, OSError, ValueError) as error:
        print(f"matrix not planned: {error}", file=sys.stderr)
        return 2
    print(plan.summary())
    if getattr(args, "cost", False) and not plan.costs:
        # A FLAG THE USER PASSED MUST ANSWER. `point_costs` returns nothing
        # when no planned point resolves to a case, and printing nothing is
        # indistinguishable from not having passed the flag at all (the
        # interface lens, 2026-09-11).
        print()
        print(
            "no cost row: none of the planned points resolved to a case of this "
            "matrix, so there is nothing to table. The plan above still stands."
        )
    if plan.costs:
        # FR-82. The table goes to STDOUT beside the summary, because an
        # operator asked for it explicitly with a flag; the progress lines of
        # FR-78 go to stderr because nobody asked for those.
        from pyflightstream.run import format_cost_table

        print()
        print(format_cost_table(plan.costs))
    if plan.plan_file is not None:
        print(f"plan: {plan.plan_file}")
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
    try:
        run_matrix(
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
            ignore_missing_families=_the_missing_family_choice(args),
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
        write_table(sweep_table(workspace, require_loads=False, matrix_stem=stem), target)
    except (LoadsNotFoundError, MalformedOutputError, OSError, ValueError) as error:
        print(f"runs completed, sweep table not written: {error}", file=sys.stderr)
        return 2
    print(f"sweep table: {target}")
    _report_skips(workspace, [stem])
    return status


if __name__ == "__main__":
    raise SystemExit(main())
