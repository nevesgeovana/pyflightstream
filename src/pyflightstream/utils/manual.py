"""Read a FlightStream manual and report what the command database is missing.

Pipeline role: maintainer utility, outside the run pipeline. Imports
nothing from this package, so it can be used from any layer.

WHAT THIS IS FOR. When the vendor ships a build, its manual documents
some commands the database does not have and, less obviously, sometimes
stops documenting ones it does. Finding that by reading is the work this
replaces: point these functions at the new manual and get the command
list, each command's page and signature, and the difference against the
database.

WHAT THIS IS NOT FOR, and the distinction is the whole design. It does
not write database entries. It was measured against the 147 entries this
database already holds, which were authored by hand from these same
manuals over several weeks, and it reproduces their argument lists for
77 percent of them. The other 23 percent are not parser bugs to be fixed
later; they are places where the entry encodes a JUDGEMENT the manual
does not state:

* a variable-length list is one ``int_list`` argument in the database and
  N separate lines in the manual's sample;
* a keyword block (``EDIT_COORDINATE_SYSTEM``) has no inline signature at
  all, and its arguments are keyword lines;
* some commands document ALTERNATIVE forms in one sample block
  (``SET_FREESTREAM`` shows both a constant and a custom profile), so
  there is no single argument list to read;
* the manual names arguments ``value`` and ``enable / disable`` where the
  database names them ``layers`` and ``mode``, and the database is the
  better document for it.

So the output is a DRAFT and a coverage report for a person to work
from, and every proposal carries why it was proposed. A tool that wrote
entries directly would be inventing grammar the emitter then uses to
validate other people's scripts, which is the one thing the evidence
rules exist to prevent (CLAUDE.md invariant 3).

RELIABILITY, measured rather than asserted. Against the 34 commands whose
manual page citation is already recorded in the database, the signature
scan finds 33 and puts 30 on the exact cited page. Against all 147
entries it reproduces 77 percent of argument counts. Both numbers are
reproduced by ``tests/test_utils_manual.py`` on synthetic fixtures; the
manual itself is licensed, lives in ``_private/`` and never enters Git,
so the fixtures imitate its SHAPE and carry none of its text
(invariant 1).
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

__all__ = [
    "ManualCommand",
    "coverage_against",
    "parse_script_index",
    "parse_signatures",
    "propose_layout",
    "read_pdf_pages",
]

#: A Script Index line pairs a command with the section that documents
#: it. Four characters minimum, so a two-letter enum value on its own
#: line cannot pass for a command name.
_INDEX_LINE = re.compile(r"^([A-Z][A-Z0-9_]{3,})\s+(\S.*?)\s*$")

#: The scripting reference introduces each command the same way, and the
#: placeholders after the name are its inline arguments in order.
_SIGNATURE = re.compile(r"^Function name:\s*([A-Z][A-Z0-9_]{2,})\s*(.*)$")
_PLACEHOLDER = re.compile(r"<([^>]+)>")

#: Sections my line pattern invents when an argument value happens to be
#: followed by prose. Kept as data so a reader can check the list rather
#: than reverse-engineer a rule, and so a new one can be added without
#: touching the parser.
_NOT_A_SECTION = frozenset({"-1", "FEET", "MIRROR", "MODIFIED_NEWTONIAN", "STL", "INCH", "METER"})


@dataclass(frozen=True)
class ManualCommand:
    """One command as the manual describes it, before any judgement.

    Attributes
    ----------
    name : str
        Command name as printed.
    page : int
        Page of the manual that introduces it, one-based, as a reader
        would cite it in a ``manual_ref``.
    inline_args : tuple of str
        Placeholder names from the signature line, in order. These are
        the arguments written on the command's own line. Arguments that
        continue onto following lines do not appear here, which is the
        single largest reason a proposal needs review.
    sample : tuple of str
        The lines of the sample block, comment lines removed. The first
        is the command with its inline arguments; any further line is a
        continuation, and the shape of those lines is what
        :func:`propose_layout` reads.
    section : str or None
        Section the Script Index files it under, when an index was
        parsed and named it.
    """

    name: str
    page: int
    inline_args: tuple[str, ...] = ()
    sample: tuple[str, ...] = ()
    section: str | None = None

    @property
    def continuation_lines(self) -> tuple[str, ...]:
        """Sample lines after the first, which the signature never shows."""
        if not self.sample:
            return ()
        head = self.sample[0]
        return self.sample[1:] if head.startswith(self.name) else ()


def parse_script_index(pages: Mapping[int, str]) -> dict[str, str]:
    """Read the manual's own Script Index into command and section.

    The index is the authoritative command list: it is the vendor's
    enumeration rather than a heuristic over headings, which is why it
    is preferred over scanning the chapter. Measured against this
    repository's database, 142 of 147 recorded commands appear in one.

    Parameters
    ----------
    pages : mapping of int to str
        Extracted text of the index pages, keyed by one-based page
        number. Pass only the index pages; passing the whole manual
        would admit body text that happens to match the line shape.

    Returns
    -------
    dict of str to str
        Command name to the section naming it, first occurrence winning.
    """
    found: dict[str, str] = {}
    for text in pages.values():
        for line in text.splitlines():
            match = _INDEX_LINE.match(line.strip())
            if match is None:
                continue
            section = match.group(2).strip()
            if section in _NOT_A_SECTION or section[:1].isdigit() or ":" in section[:3]:
                continue
            found.setdefault(match.group(1), section)
    return found


def parse_signatures(
    pages: Mapping[int, str], *, sections: Mapping[str, str] | None = None
) -> dict[str, ManualCommand]:
    """Read every command's signature and sample from the scripting chapter.

    Parameters
    ----------
    pages : mapping of int to str
        Extracted text of the scripting reference pages, keyed by
        one-based page number.
    sections : mapping of str to str, optional
        Output of :func:`parse_script_index`, used only to fill
        :attr:`ManualCommand.section`.

    Returns
    -------
    dict of str to ManualCommand
        Command name to what the manual states about it. First
        definition wins, so a later cross-reference cannot overwrite the
        page a reader should cite.
    """
    sections = sections or {}
    found: dict[str, ManualCommand] = {}
    for page in sorted(pages):
        lines = [line.rstrip() for line in pages[page].splitlines()]
        for i, line in enumerate(lines):
            match = _SIGNATURE.match(line.strip())
            if match is None:
                continue
            name = match.group(1)
            if name in found:
                continue
            found[name] = ManualCommand(
                name=name,
                page=page,
                inline_args=tuple(a.strip() for a in _PLACEHOLDER.findall(match.group(2))),
                sample=_sample_after(lines, i, name),
                section=sections.get(name),
            )
    return found


def _sample_after(lines: list[str], start: int, name: str) -> tuple[str, ...]:
    """Lines of the sample block that follows a signature, comments dropped."""
    for j in range(start, min(start + 40, len(lines))):
        if not lines[j].strip().startswith("Sample"):
            continue
        block: list[str] = []
        for k in range(j + 1, min(j + 16, len(lines))):
            candidate = lines[k].strip()
            if candidate.startswith("Function name:"):
                break
            if not candidate or candidate.startswith("#"):
                continue
            block.append(candidate)
        return tuple(block)
    return ()


def propose_layout(command: ManualCommand) -> tuple[str, str]:
    """Suggest a database layout for a command, with the reason.

    A PROPOSAL, and the second element says what it was read from so a
    reviewer can disagree cheaply. The five layouts are the database's
    own vocabulary: ``bare``, ``inline``, ``param_lines``,
    ``payload_lines`` and ``keyword_block``.

    Returns
    -------
    tuple of str
        ``(layout, why)``. ``why`` is a sentence naming the evidence,
        and is never empty, including when the answer is a guess.
    """
    continuation = command.continuation_lines
    if not command.inline_args and not continuation:
        return "bare", "the signature has no placeholder and the sample is one line"
    if not continuation:
        return (
            "inline",
            f"the signature has {len(command.inline_args)} placeholder(s) "
            "and the sample is one line",
        )
    keyworded = sum(1 for line in continuation if re.match(r"^[A-Z][A-Z0-9_]+\s+\S", line))
    if keyworded and keyworded == len(continuation):
        return (
            "keyword_block",
            f"every one of the {len(continuation)} continuation lines starts with a keyword",
        )
    if len(continuation) == 1:
        return (
            "param_lines",
            "one continuation line, which is the shape a path or a single value takes",
        )
    return (
        "payload_lines",
        f"{len(continuation)} continuation lines carrying values rather than keywords; "
        "check whether they are one variable-length argument rather than several",
    )


@dataclass(frozen=True)
class Coverage:
    """What one manual says that the database does not, and the reverse.

    Attributes
    ----------
    absent : tuple of str
        Documented by the manual and not recorded in the database.
    recorded : tuple of str
        In both.
    undocumented : tuple of str
        Recorded in the database and not found in this manual. Not an
        error by itself: a command removed by a later build, or one
        documented only in another edition, lands here.
    """

    absent: tuple[str, ...] = ()
    recorded: tuple[str, ...] = ()
    undocumented: tuple[str, ...] = ()
    details: dict[str, ManualCommand] = field(default_factory=dict)

    def summary(self) -> str:
        """One sentence a maintainer can paste into a session note."""
        return (
            f"{len(self.recorded) + len(self.absent)} commands documented, "
            f"{len(self.recorded)} already recorded, {len(self.absent)} absent from the "
            f"database, {len(self.undocumented)} recorded here but not in this manual"
        )


def coverage_against(manual: Mapping[str, ManualCommand], recorded: Iterable[str]) -> Coverage:
    """Compare a parsed manual against the names the database records.

    Parameters
    ----------
    manual : mapping of str to ManualCommand
        Output of :func:`parse_signatures`.
    recorded : iterable of str
        Command names the database holds, typically
        ``CommandRegistry.load().commands``.

    Returns
    -------
    Coverage
        The three sets, each sorted, plus the parsed detail of every
        absent command so a maintainer can start writing entries without
        re-reading the manual.
    """
    known = set(recorded)
    documented = set(manual)
    absent = tuple(sorted(documented - known))
    return Coverage(
        absent=absent,
        recorded=tuple(sorted(documented & known)),
        undocumented=tuple(sorted(known - documented)),
        details={name: manual[name] for name in absent},
    )


def read_pdf_pages(path, first: int, last: int) -> dict[int, str]:
    """Extract the text of a page range from a manual pdf.

    Separated from every function above so the parsing is testable
    without a pdf and without the optional dependency: everything else in
    this module takes text.

    Parameters
    ----------
    path : str or Path
        The manual. It is licensed vendor material, lives in
        ``_private/`` and never enters Git (CLAUDE.md invariant 1); only
        paraphrases and page citations derived from it are committed.
    first, last : int
        One-based, inclusive page range.

    Returns
    -------
    dict of int to str
        Extracted text keyed by one-based page number.

    Raises
    ------
    MissingExtraError
        When the ``manual`` extra is not installed.
    """
    try:
        import pypdf
    except ImportError as error:  # pragma: no cover - exercised by the extras test
        from pyflightstream.extras import missing_extra

        raise missing_extra(
            "manual", package="pypdf", purpose="reading a FlightStream manual pdf"
        ) from error

    reader = pypdf.PdfReader(path)
    upper = min(last, len(reader.pages))
    return {i + 1: (reader.pages[i].extract_text() or "") for i in range(first - 1, upper)}
