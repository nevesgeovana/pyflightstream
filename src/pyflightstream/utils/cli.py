"""``pyfs-manual``: compare a FlightStream manual against the command database.

Pipeline role: maintainer entry point, outside the run pipeline. It reads
licensed vendor documentation from a path the caller gives and writes
nothing unless told to.

Five subcommands, and the split between them is the point.

``sweep`` answers "what do the registered builds document that we do not
have", reading every edition named in a manifest and reporting the
union. That is the question a coverage push asks, and it is not the same
question as the one below: a command absent from one edition may be
recorded from another.

``surface`` reads the same manifest and asks the other multi-edition
question: what each build documents, and what changed between one build
and the next. ``sweep`` measures this package against the manuals;
``surface`` measures the manuals against each other, and answers nothing
about the database at all.

``coverage`` answers the sweep's question of ONE manual, which is what a
single new release raises before it has a manifest row.

``citations`` asks the one question the other four do not: not what the
manual holds, but whether what the database already SAYS about the
manual is still true. It re-reads every version row's page citation
against the edition it names. It is the only one that exits non-zero on
a finding, because a sweep's findings are work remaining while a
citation that does not hold is a shipped statement that is wrong.

``draft`` turns either answer into entries to review, and only writes
when ``--write`` is passed with a destination.

The default of ``draft`` is a dry run for a measured reason, stated in
:mod:`pyflightstream.utils.manual`: the drafts reproduce 77 percent of
the argument lists this database already holds by hand. The other
quarter are judgements the manual does not state, so a draft written
unreviewed would put invented grammar in front of the emitter that
validates other people's scripts.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from pyflightstream.commands import CommandRegistry
from pyflightstream.utils.errors import ManualDraftError
from pyflightstream.utils.manual import (
    SurfaceChange,
    SweptCommand,
    citation_reach,
    coverage_against,
    edition_surfaces,
    parse_script_index,
    parse_signatures,
    propose_layout,
    read_edition_manifest,
    read_pdf_pages,
    render_chapter,
    stale_citations,
    surface_changes,
    sweep_editions,
    unreachable_commands,
    write_chapter,
)
from pyflightstream.versions import known_versions

#: Shown as the epilog of ``sweep --help``. A maintainer writing their
#: first manifest should not have to read the library to learn its shape,
#: and the shape cannot be shown by a committed sample file: a real one
#: names licensed manual paths (invariant 1).
_MANIFEST_EXAMPLE = """The --editions manifest is a YAML list, one row per registered build:

  - label: "26.121"
    source: SRC-740
    manual: _private/manual/user-manual-26121.pdf
    chapter: 284-379
    index: 380-386

label, manual and chapter are required; index and source are not. Page
ranges are one-based and inclusive. Registering a new build is adding a
row."""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pyfs-manual",
        description=(
            "Read a FlightStream manual and compare it against the command "
            "database. The manual is licensed vendor material: pass its path "
            "explicitly, it is never guessed, and nothing from it is copied "
            "into anything this writes."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    for name, help_text in (
        ("coverage", "report what the manual documents and the database does not"),
        ("draft", "render database entries for the absent commands, for review"),
    ):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("--manual", required=True, help="path of the manual pdf")
        p.add_argument("--source", required=True, help='citation id, for example "SRC-741"')
        p.add_argument(
            "--chapter-pages",
            required=True,
            metavar="FIRST-LAST",
            help="page range of the scripting reference, one-based inclusive",
        )
        p.add_argument(
            # Optional, because the library treats the Script Index as
            # optional: it supplies the section label only, and
            # sweep_editions documents that an edition without one is
            # read unlabelled rather than skipped. Requiring it here
            # would leave the same maintainer unable to run `coverage`
            # against an edition that `sweep` handles.
            "--index-pages",
            default=None,
            metavar="FIRST-LAST",
            help=(
                "page range of the Script Index, one-based inclusive. Optional: "
                "without it the report carries no section labels, which is what "
                "an edition with no index gets"
            ),
        )

    # sweep takes a manifest instead of the four single-manual flags: it
    # reads every registered edition at once, and the page ranges differ
    # per edition, so there is nothing for those flags to mean here.
    swp = sub.add_parser(
        "sweep",
        help=(
            "report the commands at least one registered edition documents "
            "and the database does not"
        ),
        epilog=_MANIFEST_EXAMPLE,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    swp.add_argument(
        "--editions",
        required=True,
        metavar="MANIFEST",
        help=(
            "YAML manifest of the editions to read, one row per build, with "
            "page ranges written FIRST-LAST (see the example below). Never "
            "committed; it names licensed manual paths"
        ),
    )
    swp.add_argument(
        "--by-section",
        action="store_true",
        help="group the absent commands by the section that documents them",
    )
    swp.add_argument(
        "--fail-if-absent",
        action="store_true",
        help=(
            "exit 1 when anything is absent, for a check that asserts the "
            "database is complete. Without it the sweep always exits 0, "
            "because a maintainer reading the report is the ordinary use"
        ),
    )

    # surface answers the other multi-edition question. sweep asks what
    # the database is missing; this asks what each build documents, so
    # two builds can be compared. Same manifest, so registering a build
    # once serves both.
    surf = sub.add_parser(
        "surface",
        help="report the command surface of each edition and what changed between builds",
        epilog=_MANIFEST_EXAMPLE,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    surf.add_argument(
        "--editions",
        required=True,
        metavar="MANIFEST",
        help=(
            "YAML manifest of the editions to read, one row per build, in "
            "RELEASE order: consecutive rows are compared, so the order of "
            "the file decides which builds are neighbours"
        ),
    )
    surf.add_argument(
        "--names",
        action="store_true",
        help=(
            "list the gained and lost command names, not only the counts. "
            "Applies to both renderings; without it a long history stays "
            "readable as counts alone"
        ),
    )
    surf.add_argument(
        "--markdown",
        action="store_true",
        help=(
            "render as markdown on standard output, to paste into a report "
            "under reports/. This subcommand writes no file: it judges "
            "nothing and has no evidence to place, unlike draft"
        ),
    )

    # citations asks the question the other four do not: not what the
    # manual holds and the database lacks, but whether what the database
    # already SAYS about the manual is still true.
    cite = sub.add_parser(
        "citations",
        help="re-read the database's page citations against the manuals they name",
        description=(
            "Re-read every version-row page citation against the edition it "
            "names. EXITS 1 WHEN ONE DOES NOT HOLD, unlike sweep, whose "
            "findings are work remaining: a citation that does not hold is a "
            "statement already shipped. The report also says how many rows "
            "could be re-read at all, since most rows carry no page of their "
            "own and a count of editions would hide that."
        ),
        epilog=_MANIFEST_EXAMPLE,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    cite.add_argument(
        "--editions",
        required=True,
        metavar="MANIFEST",
        help=(
            "YAML manifest of the editions to check against. A row the "
            "manifest does not carry is not checked and is not reported: "
            "the check is against a document, and without the document "
            "there is nothing to check"
        ),
    )

    draft = sub.choices["draft"]
    draft.add_argument(
        # --fs-version, not --version: every other tool of this package
        # spells the FlightStream version that way (pyfs-qa, pyfs-cases),
        # and --version is what a reader expects to print the package's
        # own version.
        "--fs-version",
        required=True,
        dest="versions",
        action="append",
        metavar="CANONICAL",
        help="canonical version the drafted entries are documented for; repeatable",
    )
    draft.add_argument(
        "--only",
        default=None,
        help="substring filter on the command name, for drafting one family at a time",
    )
    draft.add_argument(
        "--out",
        default=None,
        help="destination file; required with --write, and named in the dry-run line without it",
    )
    draft.add_argument(
        "--write",
        action="store_true",
        help=(
            "actually write. Without it the draft is printed and nothing is "
            "touched, which is the default because a drafted entry is not "
            "evidence: it reproduces about three quarters of a hand-authored "
            "argument list and leaves the rest as '???'"
        ),
    )
    return parser


def _pages(parser: argparse.ArgumentParser, flag: str, spec: str) -> tuple[int, int]:
    """Read a FIRST-LAST page range, refusing anything else through the parser.

    Refusing through ``parser.error`` rather than raising keeps the exit
    code at 2, the usage code the rest of this package's CLIs return, and
    prints the flag the user typed. A non-numeric page reached ``int()``
    and surfaced as a raw traceback before.
    """
    first, _, last = spec.partition("-")
    if not last or not first.isdigit() or not last.isdigit():
        parser.error(f"{flag} takes FIRST-LAST in one-based page numbers, for example 273-370")
    return int(first), int(last)


def _citations(parser: argparse.ArgumentParser, args: argparse.Namespace) -> int:
    """Check the database's page citations against the manuals.

    Returns
    -------
    int
        0 when every citation the manifest can reach holds, 1 otherwise.
        This one FAILS on a finding, unlike ``sweep``, whose findings are
        remaining work: a citation that does not hold is not work left to
        do, it is a statement in a shipped file that is wrong.
    """
    try:
        editions = read_edition_manifest(args.editions)
        stale = stale_citations(editions, recorded=CommandRegistry.load())
    except FileNotFoundError as missing:
        parser.error(f"cannot read the manifest or a manual it names: {missing}")
    except ManualDraftError as error:
        parser.error(str(error))

    checked = sum(pair[1] for pair in citation_reach.values())
    seen = sum(pair[0] for pair in citation_reach.values())
    print(
        f"{len(editions)} edition(s) checked: {checked} of {seen} version rows carry a "
        f"citation this can re-read, and {len(stale)} of those do not hold"
    )
    for item in stale:
        where = (
            "the edition does not print it" if item.found is None else f"parses at p.{item.found}"
        )
        print(f"  {item.command:<48} {item.edition}  cites p.{item.cited}, {where}")

    # Reach per edition, because a total hides the shape. A build whose
    # rows carry no note of their own reads as fully checked inside a
    # total and is not checked at all; 26.120 is that build, its rows
    # resting on the entry's own manual_ref rather than on a page each.
    for label, (rows, able) in citation_reach.items():
        note = "" if able else "   <- no row of this build carries one"
        print(f"    {label}  {able} of {rows}{note}")

    # And the builds the manifest did not cover, the door `surface`
    # closed last release and this subcommand had left open: without
    # this line a one-build manifest prints a clean report and exits 0.
    unchecked = [v.canonical for v in known_versions() if v.canonical not in citation_reach]
    if unchecked:
        print(f"  no manifest row for {', '.join(unchecked)}; their rows were not checked")
    return 1 if stale else 0


def _sweep(parser: argparse.ArgumentParser, args: argparse.Namespace) -> int:
    """Run the multi-edition sweep and print it, grouped or flat.

    Reports BOTH halves of the coverage question, because for a long
    time it reported only one and the other was where the gap was. The
    first half asks which commands have no ENTRY; the second asks which
    commands an edition documents that its own build cannot emit, which
    is a different question and the sweep is structurally blind to it: it
    compares entry names, so an entry missing one edition's row reads as
    covered. On 2026-08-10 this command reported zero absent across eight
    editions while three of them could not emit
    ``EXPORT_ALL_SURFACE_STREAMLINES``.

    Returns
    -------
    int
        0, unless ``--fail-if-absent`` was passed and either half is
        non-empty. Reporting is the ordinary use and a maintainer runs it
        in a loop, so a finding is an answer rather than a failure; the
        flag is for the other use, asserting that the database is
        complete.
    """
    try:
        editions = read_edition_manifest(args.editions)
        registry = CommandRegistry.load()
        absent = sweep_editions(editions, recorded=registry.commands)
        unreachable = unreachable_commands(editions, recorded=registry)
    except FileNotFoundError as missing:
        parser.error(f"cannot read the manifest or a manual it names: {missing}")
    except ManualDraftError as error:
        parser.error(str(error))

    labels = " ".join(edition.label for edition in editions)
    print(f"{len(editions)} edition(s) read ({labels}): {len(absent)} command(s) absent")
    print(
        f"  and {len(unreachable)} command(s) an edition documents that its build cannot emit:"
        if unreachable
        else "  and every command every edition documents is emittable for that build"
    )
    for item in unreachable:
        print(f"    {item.edition}  {item.command:<44} {item.reason}")
    exit_code = 1 if ((absent or unreachable) and args.fail_if_absent) else 0
    if not args.by_section:
        for command in absent:
            pages = " ".join(f"{label}:p.{page}" for label, page in command.pages.items())
            print(f"  {command.name:<48} {command.section or '?':<28} {pages}")
        return exit_code

    # Grouped, because the database is written one chapter at a time and
    # the section is what a chapter file corresponds to. Largest first:
    # it is the order the remaining work is actually done in.
    groups: dict[str, list[SweptCommand]] = {}
    for command in absent:
        groups.setdefault(command.section or "(no section, the index does not name it)", []).append(
            command
        )
    for section, members in sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        print(f"\n{section}  [{len(members)}]")
        for command in members:
            editions_of = " ".join(command.editions)
            print(f"  {command.name:<48} {editions_of}")
    return exit_code


def _surface(parser: argparse.ArgumentParser, args: argparse.Namespace) -> int:
    """Report each edition's command surface and the changes between builds.

    Returns
    -------
    int
        0 always. This measures rather than judges: a build that gained
        or lost commands is the ordinary case, and there is no state of
        the manuals that makes this a failure.
    """
    try:
        editions = read_edition_manifest(args.editions)
        surfaces = edition_surfaces(editions)
    except FileNotFoundError as missing:
        parser.error(f"cannot read the manifest or a manual it names: {missing}")
    except ManualDraftError as error:
        parser.error(str(error))

    changes = surface_changes(surfaces)

    # Name what the manifest did NOT cover. The manifest is the whole
    # input, so a build missing a row is invisible: the tool would report
    # its two neighbours as consecutive and no reader could tell that
    # something sat between them. That is the wrong-neighbour failure
    # arriving through a door with no warning, so the door gets one.
    # A label that is not a registered build is reported rather than
    # refused, a fork's manifest being allowed to hold editions this
    # registry does not know.
    read = set(surfaces)
    registered = [version.canonical for version in known_versions()]
    # Not named `missing`: that is the `except FileNotFoundError as
    # missing` variable above, which Python deletes when the block ends,
    # so reusing it reads a deleted name (mypy caught this).
    unread = [canonical for canonical in registered if canonical not in read]
    unregistered = sorted(read - set(registered))

    lines = (
        _surface_markdown(surfaces, changes, names=args.names)
        if args.markdown
        else _surface_text(surfaces, changes, names=args.names)
    )
    coverage = f"{len(read)} of {len(registered)} registered build(s) read"
    if unread:
        coverage += "; no manifest row for " + ", ".join(unread)
    if unregistered:
        coverage += "; not a registered build: " + ", ".join(unregistered)
    lines.append("")
    lines.append(coverage if not args.markdown else f"Coverage: {coverage}.")
    print("\n".join(lines))
    return 0


def _surface_text(
    surfaces: dict[str, tuple[str, ...]],
    changes: Sequence[SurfaceChange],
    *,
    names: bool,
) -> list[str]:
    """Render the surface report for a terminal."""
    lines = [f"{len(surfaces)} edition(s) read"]
    for label, commands in surfaces.items():
        lines.append(f"  {label}  {len(commands):4d} commands documented")
    lines.append("")
    if not changes:
        lines.append("one edition, so there is nothing to compare")
    for change in changes:
        lines.append(
            f"{change.older} -> {change.newer}: +{len(change.gained)} / -{len(change.lost)}"
        )
        if names:
            if change.gained:
                lines.append("  gained: " + ", ".join(change.gained))
            if change.lost:
                lines.append("  lost:   " + ", ".join(change.lost))
    return lines


def _surface_markdown(
    surfaces: dict[str, tuple[str, ...]],
    changes: Sequence[SurfaceChange],
    *,
    names: bool = True,
) -> list[str]:
    """Render the surface report as a committable markdown section."""
    lines = [
        "## Command surface per edition",
        "",
        "| Build | Commands documented |",
        "|---|---|",
    ]
    lines += [f"| {label} | {len(commands)} |" for label, commands in surfaces.items()]
    lines += ["", "## What changed between consecutive builds", ""]
    for change in changes:
        lines.append(f"### {change.older} to {change.newer}")
        lines.append("")
        lines.append(f"Gained {len(change.gained)}, lost {len(change.lost)}.")
        lines.append("")
        if names and change.gained:
            lines += ["Gained: " + ", ".join(f"`{name}`" for name in change.gained), ""]
        if names and change.lost:
            lines += ["Lost: " + ", ".join(f"`{name}`" for name in change.lost), ""]
    return lines


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command line and return a process exit code.

    Returns
    -------
    int
        0 on success. A usage error exits 2 through ``argparse``, and a
        refusal from the library raises.
    """
    parser = _parser()
    args = parser.parse_args(argv)

    if args.command == "sweep":
        return _sweep(parser, args)

    if args.command == "surface":
        return _surface(parser, args)

    if args.command == "citations":
        return _citations(parser, args)

    # Every argument check happens before the manual is opened. The
    # --write refusal used to fire after two full pdf reads and a render,
    # so a mistyped invocation cost the whole run on a 400-page document.
    chapter_first, chapter_last = _pages(parser, "--chapter-pages", args.chapter_pages)
    index_range = _pages(parser, "--index-pages", args.index_pages) if args.index_pages else None
    if args.command == "draft" and args.write and not args.out:
        parser.error("--write needs --out; refusing to guess where to put a draft")

    # A library refusal is a usage error when it arrives here: the caller
    # typed a page range or a manual path. Letting it escape delivered
    # the two failure modes of one flag two different ways, a parser
    # error for a malformed range and a traceback for an out-of-range
    # one.
    try:
        index = (
            parse_script_index(
                read_pdf_pages(args.manual, first=index_range[0], last=index_range[1])
            )
            if index_range is not None
            else {}
        )
        manual = parse_signatures(
            read_pdf_pages(args.manual, first=chapter_first, last=chapter_last), sections=index
        )
    except ManualDraftError as error:
        parser.error(str(error))
    report = coverage_against(manual, recorded=CommandRegistry.load().commands)

    if args.command == "coverage":
        print(f"{args.source}: {report.summary()}")
        for name in report.absent:
            command = report.details[name]
            layout, _why = propose_layout(command)
            print(f"  ABSENT  p.{command.page:<4} {name:<48} {command.section or '?'} [{layout}]")
        for name in report.undocumented:
            print(f"  ONLY IN THE DATABASE   {name}")
        return 0

    wanted = [
        command
        for name, command in report.details.items()
        if args.only is None or args.only in name
    ]
    if not wanted:
        print(f"{args.source}: nothing absent matches {args.only!r}; nothing to draft")
        return 0

    body = render_chapter(
        wanted, source=args.source, versions=dict.fromkeys(args.versions, "documented")
    )
    if not args.write:
        print(body)
        # The CLI words its own closing line: write_chapter's dry-run
        # sentence names the Python keyword `write=True`, which a
        # command-line user cannot type, and printed the placeholder path
        # as though it were a destination.
        entries = body.count("\n  layout: ")
        unanswered = body.count("???")
        destination = f" --out {args.out}" if args.out else " --out PATH"
        print(
            f"dry run: {entries} entr(ies) drafted, {unanswered} unanswered field(s), "
            f"nothing written. Re-run with --write{destination} to write them."
        )
        return 0
    print(write_chapter(body, path=args.out, write=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
