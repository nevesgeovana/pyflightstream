"""``pyfs-manual``: compare a FlightStream manual against the command database.

Pipeline role: maintainer entry point, outside the run pipeline. It reads
licensed vendor documentation from a path the caller gives and writes
nothing unless told to.

Two subcommands, and the split is the point. ``coverage`` answers "what
does this build document that we do not have", which is the question a
new release raises and which is safe to run at any time. ``draft`` turns
that answer into entries to review, and only writes when ``--write`` is
passed with a destination.

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
from pyflightstream.utils.manual import (
    coverage_against,
    parse_script_index,
    parse_signatures,
    propose_layout,
    read_pdf_pages,
    render_chapter,
    write_chapter,
)


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
            "--index-pages",
            required=True,
            metavar="FIRST-LAST",
            help="page range of the Script Index, one-based inclusive",
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

    # Every argument check happens before the manual is opened. The
    # --write refusal used to fire after two full pdf reads and a render,
    # so a mistyped invocation cost the whole run on a 400-page document.
    chapter_first, chapter_last = _pages(parser, "--chapter-pages", args.chapter_pages)
    index_first, index_last = _pages(parser, "--index-pages", args.index_pages)
    if args.command == "draft" and args.write and not args.out:
        parser.error("--write needs --out; refusing to guess where to put a draft")

    index = parse_script_index(read_pdf_pages(args.manual, first=index_first, last=index_last))
    manual = parse_signatures(
        read_pdf_pages(args.manual, first=chapter_first, last=chapter_last), sections=index
    )
    report = coverage_against(manual, CommandRegistry.load().commands)

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
    print(write_chapter(args.out, body, write=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
