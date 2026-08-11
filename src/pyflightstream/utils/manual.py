"""Read a FlightStream manual and report what the command database is missing.

Pipeline role: maintainer utility, outside the run pipeline. Imports
nothing ABOVE the bottom layer (its own errors module, and
``pyflightstream.extras`` lazily for the optional pdf dependency), so it
can be used from any layer.

WHAT THIS IS FOR. When the vendor ships a build, its manual documents
some commands the database does not have and, less obviously, sometimes
stops documenting ones it does. Finding that by reading is the work this
replaces: point these functions at the new manual and get the command
list, each command's page and signature, and the difference against the
database.

WHAT THIS IS NOT FOR, and the distinction is the whole design. It does
not write database entries. Measured on 2026-08-04 against the 147
entries the database then held, authored by hand from these same manuals
over several weeks, it reproduced 77 percent of their argument lists.
The other 23 percent are not parser bugs to be fixed later; they are
places where the entry encodes a JUDGEMENT the manual does not state:

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

RELIABILITY, measured rather than asserted, and every number below is a
measurement of one day against one corpus rather than a standing
property. On 2026-08-04, against the 34 entries then citing a page of
the edition being scanned, the signature scan found 33 and put 30 on the
exact cited page; against the 147 entries then recorded it reproduced 77
percent of argument counts.

Argument TYPES are read from a third source, the manual's own parameter
table, which :func:`propose_type` reads and the signature and sample do
not carry. Measured on 2026-08-05 against 148 arguments whose type this
repository authored by hand: **57 percent agreed, 43 percent proposed
nothing, and none disagreed.** The second number and the third are the
design. A rule that cannot read a type returns None and the draft writes
``???``, which the schema refuses, so more than two fifths of a tranche
are still a person's work; what the tool must never do is propose a type
that is wrong, because that one loads.

**That last measurement was not independent, and on 2026-08-06 the
property it certified turned out to be false.** Read what it compared:
proposals against types a person had authored FROM THE SAME PARAMETER
TABLE. Where the table is wrong, the tool and the author read one source
and agree with each other about it, and the agreement measures their
common source rather than either of them. Checking the proposals against
the manual's own printed SAMPLE instead found 19 positions across seven
commands, in this database and in the tool's output alike, where the
declared token set refuses the token the sample passes.
:func:`sample_contradiction` is that second reading, and
:func:`render_entry` now discards a type the sample contradicts rather
than writing it, which turns a proposal that would have loaded into a
``???`` that cannot. The lesson generalises past this module: a
validation set drawn from the thing being validated measures nothing.

The corpus is the other reason to distrust these numbers, since it is
not a sample of the manual: it is the commands somebody chose to write
first. Reading the drafts of the CAD chapter, which nobody has written,
found the rule that reads a token LIST taking words out of the sentences
after the one that lists them, so a threshold with two values drafted
three. It reads one sentence now. The counting openings run before both
enum rules, because a count whose sentence happens to spell two file
formats ("Number of boundaries in the STL or OBJ import") is a
count and not a choice.

A SAMPLE THAT CROSSES A PAGE BREAK IS INVISIBLE, and the consequence is
worth stating because it is silent. Pages are parsed one at a time, so
a command whose ``Sample:`` banner ends a page and whose printed call
begins the next one comes back with an empty sample.
:func:`sample_contradiction` then answers None for it, which is one of
its three documented silent cases and reads exactly like agreement.
Measured on 2026-08-07: ``CAD_CREATE_REVOLVE_MESH_FROM_CCS`` in the
February 2026 edition is such a command, and it is one of the two whose
argument count the printed sample is what settles. Closing this means
parsing with overlapping page windows
(PLN-20260807-0900).

The rules and the ordering are held by ``tests/test_utils_manual.py`` on
synthetic fixtures; the percentages are not, and cannot be, since a
fixture set is not a corpus. The manual itself is licensed, lives in
``_private/`` and never enters Git, so the fixtures imitate its SHAPE and
carry none of its text (invariant 1).
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

import yaml

from pyflightstream.utils.errors import ManualDraftError

__all__ = [
    "TYPE_RULES",
    "Coverage",
    "Edition",
    "ManualCommand",
    "StaleCitation",
    "CommandEntryLike",
    "VersionRowLike",
    "RegistryLike",
    "SurfaceChange",
    "Reachability",
    "UnreachableCommand",
    "SweptCommand",
    "TypeRule",
    "coverage_against",
    "edition_surfaces",
    "parse_script_index",
    "parse_signatures",
    "propose_layout",
    "propose_type",
    "read_edition_manifest",
    "read_pdf_pages",
    "render_chapter",
    "render_entry",
    "sample_contradiction",
    "stale_citations",
    "surface_changes",
    "sweep_editions",
    "unreachable_commands",
    "write_chapter",
]

#: A Script Index line pairs a command with the section that documents
#: it. Four characters minimum, so a two-letter enum value on its own
#: line cannot pass for a command name.
_INDEX_LINE = re.compile(r"^([A-Z][A-Z0-9_]{3,})\s+(\S.*?)\s*$")

#: The scripting reference introduces each command the same way, and the
#: placeholders after the name are its inline arguments in order.
#:
#: NOT anchored at the start of the line, and the difference is a
#: margin. Under layout extraction a glyph sitting in the left margin
#: keeps its column, so the line reads as that glyph, a run of spaces,
#: then the heading; anchored, the match fails and the command is
#: invisible. Measured on 2026-08-10 across the six pdf editions in the
#: manifest at that hour, which was before 25.000's conversion and
#: before 26.122 was registered the same day: the
#: tolerant form finds exactly what the anchored one finds and nothing
#: more, so it costs no precision, and it recovers two commands of 272
#: in a pdf converted from a compiled help archive.
_SIGNATURE = re.compile(r"(?:^|\s)Function name:\s*([A-Z][A-Z0-9_]{2,})\s*(.*)$")
_PLACEHOLDER = re.compile(r"<([^>]+)>")

#: A signature heading that WRAPS: the line after it is placeholders and
#: nothing else, so those placeholders belong to the signature above.
#:
#: Five commands do this, identically in all four registered editions,
#: and the parser reported every one of them short until 2026-08-07:
#: CAD_CREATE_AUTO_CROSS_SECTIONS and CREATE_NEW_CIRCLE_VOLUME_SECTION
#: by one, CREATE_NEW_6DOF_SPRING_FORCE and
#: CAD_CREATE_REVOLVE_MESH_FROM_CCS by one, and
#: CREATE_NEW_RECTANGLE_VOLUME_SECTION by THREE. A short signature is
#: the worst shape this module can produce, because the draft it feeds
#: LOADS: the schema accepts an entry with fewer arguments, the emitter
#: then accepts a call with fewer tokens, and the solver reads the line
#: differently with nothing between the two to object.
#:
#: The rule is deliberately strict. A continuation line holds ONLY
#: placeholders, so a following sentence, a parameter-table heading or a
#: sample line cannot be absorbed into a signature.
_WRAPPED_SIGNATURE = re.compile(r"^\s*(?:<[^>]+>\s*)+$")

#: A parameter-table row of a command with no inline signature begins
#: with the keyword it documents. Two capitals minimum and a following
#: space or glued lowercase, so a wrapped line beginning with a normal
#: capitalised word cannot pass for a row key.
_TABLE_KEY = re.compile(r"^([A-Z][A-Z0-9_]{2,})(?=\s|[a-z]|$)")

#: Tokens a parameter description offers as the accepted values. Read as
#: grammar, never as prose: the token list is a fact about the command,
#: the sentence around it is licensed manual text and stays in the pdf.
_ENUM_TOKEN = re.compile(r"\b([A-Z][A-Z0-9_]{2,})\b")

#: The other way a description spells a closed set: the tokens joined by
#: "or", optionally comma separated before it ("FEET or METERS",
#: "X, Y or Z"). Single letters count here, which is why this is a
#: separate pattern from the one above rather than a looser version of
#: it: a lone capital elsewhere in a sentence is not a token.
_ENUM_ALTERNATIVES = re.compile(
    r"\b[A-Z][A-Z0-9_]*(?:\s*,\s*[A-Z][A-Z0-9_]*)*\s+or\s+[A-Z][A-Z0-9_]*\b"
)

#: The phrase a description uses to introduce a closed set. Only the
#: sentence carrying it is read for tokens, so a following sentence
#: about something else cannot contribute one.
_ENUM_PHRASE = re.compile(r"one of the following|can be one of", re.IGNORECASE)

#: A sentence ends at a period followed by a space and a capital, or at
#: the end of the text. A bare period is not enough: the manual writes
#: decimals and abbreviations, and cutting at those loses real tokens.
_SENTENCE_END = re.compile(r"\.\s+(?=[A-Z])")

#: A leading article, stripped before the opening rules read the
#: description: "The number of boundaries" and "Number of boundaries"
#: are the same statement, and only the second was being read.
_ARTICLE = re.compile(r"^(?:the|a|an)\s+", re.IGNORECASE)

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
    parameters : mapping of str to str
        The manual's own parameter table, placeholder name to the prose
        describing it, for the commands that carry one. This is the
        third source, after the signature and the sample, and it is the
        only one that says anything about an argument's TYPE. The prose
        is licensed manual text: it is read at run time from the pdf the
        caller passes and is never written into anything this module
        renders (invariant 1), which is why :func:`propose_type` returns
        a conclusion and a structural reason rather than a quotation.
    """

    name: str
    page: int
    inline_args: tuple[str, ...] = ()
    sample: tuple[str, ...] = ()
    section: str | None = None
    parameters: Mapping[str, str] = field(default_factory=dict)

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
    is preferred over scanning the chapter. Measured on 2026-08-04, 142
    of the 147 commands this database then recorded appeared in one.

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
            # search, not match: the pattern already requires the heading
            # to start a line or follow whitespace, and anchoring at
            # position zero as well would defeat the margin tolerance the
            # pattern was widened for.
            match = _SIGNATURE.search(line.strip())
            if match is None:
                continue
            name = match.group(1)
            if name in found:
                continue
            signature = match.group(2)
            if i + 1 < len(lines) and _WRAPPED_SIGNATURE.match(lines[i + 1]):
                signature += " " + lines[i + 1].strip()
            placeholders = tuple(a.strip() for a in _PLACEHOLDER.findall(signature))
            found[name] = ManualCommand(
                name=name,
                page=page,
                inline_args=placeholders,
                sample=_sample_after(lines, i, name),
                section=sections.get(name),
                parameters=_parameters_after(lines, i, placeholders),
            )
    return found


def _parameters_after(
    lines: list[str], start: int, placeholders: tuple[str, ...]
) -> dict[str, str]:
    """Read the parameter table that follows a signature, if it has one.

    The table is bounded by its own heading and the sample block. Its
    rows are keyed by the placeholder names of the signature, which is
    why they are passed in rather than guessed: a row's prose wraps onto
    following lines, and the pdf extraction sometimes glues the key to
    the first word of its description, so the known keys are what makes
    the split reliable. A command with no inline signature (a keyword
    block) has no such list, and there the line-initial capitalised
    tokens are taken as the keys instead, because for those commands the
    table IS the argument list.

    Parameters
    ----------
    lines : list of str
        Lines of the page.
    start : int
        Index of the signature line.
    placeholders : tuple of str
        Inline placeholder names from that signature, in order.

    Returns
    -------
    dict of str to str
        Parameter name to its description, empty when the command
        documents no table.
    """
    opening = None
    for j in range(start, min(start + 6, len(lines))):
        if lines[j].strip().startswith("Function parameters"):
            opening = j
            break
    if opening is None:
        return {}
    block: list[str] = []
    for k in range(opening + 1, min(opening + 40, len(lines))):
        candidate = lines[k].strip()
        if candidate.startswith(("Sample", "Function name:")):
            break
        if not candidate or candidate == "Parameter Value":
            continue
        block.append(candidate)
    if not block:
        return {}
    keys = [p.upper() for p in placeholders] or [
        match.group(1) for line in block if (match := _TABLE_KEY.match(line)) is not None
    ]
    rows: dict[str, list[str]] = {}
    current: str | None = None
    for line in block:
        opened = next((key for key in keys if line.startswith(key)), None)
        if opened is not None and opened not in rows:
            current = opened
            rows[current] = [line[len(opened) :].strip()]
        elif current is not None:
            rows[current].append(line)
    return {key: " ".join(parts).strip() for key, parts in rows.items()}


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


def coverage_against(manual: Mapping[str, ManualCommand], *, recorded: Iterable[str]) -> Coverage:
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


@dataclass(frozen=True, kw_only=True)
class Edition:
    """One manual to read, and where its two chapters sit in it.

    A registered FlightStream build and the pdf that documents it. The
    page ranges are per edition because they MOVE: the scripting
    reference of the four editions registered on 2026-08-08 starts on
    four different pages, so a single range shared by all of them reads
    the wrong pages of three.

    KEYWORD-ONLY, and that is about ``chapter`` and ``index``
    specifically. They are two page ranges of the same type, so
    positionally they are interchangeable and swapping them constructs
    cleanly: the sweep then reads the Script Index as the scripting
    reference, reports hundreds of false absences, and nothing anywhere
    can detect it. Named arguments are the only thing that separates
    them.

    Attributes
    ----------
    label : str
        Canonical version identifier, for example ``"26.121"``. Used
        only to name the edition in the report; nothing resolves it
        against the version registry, so an unregistered build can be
        swept before it is added.
    manual : Path
        Path of the manual pdf. Licensed vendor material, given
        explicitly and never guessed, and never committed.
    chapter : tuple of int
        First and last page of the scripting reference, one-based
        inclusive.
    index : tuple of int or None
        First and last page of the Script Index, if the edition has
        one. It supplies the section label only, so an edition without
        one is swept with its commands unlabelled rather than skipped.
    source : str or None
        Citation id of this edition, for example ``"SRC-741"``, as a
        ``manual_ref`` would spell it.
    """

    label: str
    manual: Path
    chapter: tuple[int, int]
    index: tuple[int, int] | None = None
    source: str | None = None


@dataclass(frozen=True)
class SweptCommand:
    """One command as the whole set of editions describes it.

    Attributes
    ----------
    name : str
        Command name as printed.
    editions : tuple of str
        Labels of the editions whose chapter body documents it, in the
        order the editions were given. A command absent from this tuple
        for a given edition is one that edition does not document, which
        is the fact a version row must reflect.
    pages : dict of str to int
        Page carrying the signature, per edition label. The pages
        differ per edition and each version row cites its own.
    section : str or None
        Section that documents it, from the first edition whose index
        names it.
    detail : ManualCommand
        What the newest edition given states about it, for drafting.
    """

    name: str
    editions: tuple[str, ...]
    pages: dict[str, int]
    section: str | None
    detail: ManualCommand


def sweep_editions(
    editions: Iterable[Edition],
    *,
    recorded: Iterable[str],
    reader: Callable[..., Mapping[int, str]] | None = None,
) -> tuple[SweptCommand, ...]:
    """Read every edition and report what none of them has an entry for.

    The multi-edition form of :func:`coverage_against`, and it exists
    because the single-edition one answers a question no sweep asks. A
    command absent from one edition may be recorded from another, and a
    command the database lacks must be entered for EVERY edition that
    documents it at once (the chapter rule in ``docs/srs/data-model.md``).
    Both need the union, so reading the editions one at a time and
    comparing four reports by eye is the step this removes.

    Reading is body-driven: the signature headings of the chapter are
    the command set, and the Script Index is consulted only for section
    labels. That is not interchangeable with reading the index, which
    is incomplete: ``NEW_CCS_WING_FLAP_COVE`` has a heading on p.299 of
    one edition and no index row, so an index-driven sweep reports it
    covered forever.

    Parameters
    ----------
    editions : iterable of Edition
        The manuals to read, oldest first by convention so that
        :attr:`SweptCommand.detail` carries the newest statement.
    recorded : iterable of str
        Command names the database holds, typically
        ``CommandRegistry.load().commands``. Keyword-only, so a call
        cannot pass the two collections the wrong way round.
    reader : callable, optional
        What turns a manual and a page range into text, defaulting to
        :func:`read_pdf_pages`. It is a parameter because this module
        keeps its parsing testable without a pdf and without the
        ``[manual]`` extra, which is the seam :func:`read_pdf_pages`
        documents about itself; this is the first function above that
        line to need a manual, so it takes the reader rather than
        reaching for it and leaving the seam to be maintained by
        monkeypatching.

    Returns
    -------
    tuple of SweptCommand
        Every command documented by at least one edition and recorded by
        none, sorted by name.

    Raises
    ------
    ManualDraftError
        If no edition is given. With no manual read, nothing can be
        documented and the answer is zero absent, which is
        indistinguishable from the complete database this is run to
        confirm. A configuration error that reads as the good outcome is
        the one shape worth refusing outright.
    """
    # Defaulted here rather than in the signature: read_pdf_pages is
    # defined below this function, the module being ordered parse-first
    # with the pdf reader at the bottom behind its optional dependency.
    read = reader if reader is not None else read_pdf_pages
    editions = tuple(editions)
    if not editions:
        raise ManualDraftError(
            "a sweep needs at least one edition; with none it reports zero commands "
            "absent, which is indistinguishable from a complete database. Add a row "
            "to the manifest with label, manual and chapter"
        )
    known = set(recorded)
    seen: dict[str, list[str]] = {}
    pages: dict[str, dict[str, int]] = {}
    sections: dict[str, str] = {}
    detail: dict[str, ManualCommand] = {}
    for edition in editions:
        labels = (
            parse_script_index(read(edition.manual, first=edition.index[0], last=edition.index[1]))
            if edition.index is not None
            else {}
        )
        parsed = parse_signatures(
            read(edition.manual, first=edition.chapter[0], last=edition.chapter[1]),
            sections=labels,
        )
        for name, command in parsed.items():
            if name in known:
                continue
            seen.setdefault(name, []).append(edition.label)
            pages.setdefault(name, {})[edition.label] = command.page
            if command.section and name not in sections:
                sections[name] = command.section
            detail[name] = command
    return tuple(
        SweptCommand(
            name=name,
            editions=tuple(labels),
            pages=pages[name],
            section=sections.get(name),
            detail=detail[name],
        )
        for name, labels in sorted(seen.items())
    )


@dataclass(frozen=True, kw_only=True)
class SurfaceChange:
    """What one build's scripting surface gained and lost against the one before it.

    Attributes
    ----------
    older : str
        Label of the earlier edition.
    newer : str
        Label of the later edition.
    gained : tuple of str
        Commands the later edition documents and the earlier one does
        not, sorted.
    lost : tuple of str
        Commands the earlier edition documents and the later one does
        not, sorted. Lost means the later manual stops printing the
        command, which is not the same as the solver refusing it: a
        command can disappear from a manual and keep working. Deciding
        which happened needs a probe, so this is evidence for a
        question rather than an answer to it.
    """

    older: str
    newer: str
    gained: tuple[str, ...]
    lost: tuple[str, ...]


def edition_surfaces(
    editions: Iterable[Edition],
    *,
    reader: Callable[..., Mapping[int, str]] | None = None,
) -> dict[str, tuple[str, ...]]:
    """Read each edition and return the command names it documents.

    The whole surface, not the part the database lacks, which is what
    :func:`sweep_editions` reports. Both read the chapter body the same
    way, and the difference is the question: a sweep asks what is
    missing from the database, this asks what each build documents so
    two builds can be compared.

    Parameters
    ----------
    editions : iterable of Edition
        The manuals to read. Order is preserved in the result and is
        the caller's to choose; :func:`surface_changes` compares
        consecutive entries, so the intended order is release order.
    reader : callable, optional
        What turns a manual and a page range into text, defaulting to
        :func:`read_pdf_pages`. Same seam as :func:`sweep_editions`,
        for the same reason.

    Returns
    -------
    dict of str to tuple of str
        Command names per edition label, sorted within each edition,
        with the editions in the order given.

    Raises
    ------
    ManualDraftError
        If no edition is given, or if two editions share a label. A
        duplicate label would silently overwrite the first reading and
        report a build compared against itself.
    """
    read = reader if reader is not None else read_pdf_pages
    editions = tuple(editions)
    if not editions:
        raise ManualDraftError(
            "reading the command surface needs at least one edition; with none there "
            "is nothing to compare. Add a row to the manifest with label, manual and "
            "chapter"
        )
    labels = [edition.label for edition in editions]
    duplicated = sorted({label for label in labels if labels.count(label) > 1})
    if duplicated:
        raise ManualDraftError(
            f"the manifest gives more than one edition the label(s) {', '.join(duplicated)}; "
            "each label names one build and a repeat would overwrite the first reading, "
            "reporting a build compared against itself"
        )

    surfaces: dict[str, tuple[str, ...]] = {}
    for edition in editions:
        parsed = parse_signatures(
            read(edition.manual, first=edition.chapter[0], last=edition.chapter[1])
        )
        surfaces[edition.label] = tuple(sorted(parsed))
    return surfaces


def surface_changes(surfaces: Mapping[str, Iterable[str]]) -> tuple[SurfaceChange, ...]:
    """Compare each edition's command surface with the one before it.

    Parameters
    ----------
    surfaces : mapping of str to iterable of str
        Command names per edition label, in release order. Python
        mappings preserve insertion order and this relies on it, so a
        caller that sorts the labels as strings gets the wrong
        neighbours: "26.100" sorts before "26.101" by luck and "26.12"
        would sort before both.

    Returns
    -------
    tuple of SurfaceChange
        One entry per consecutive pair, empty when fewer than two
        editions are given.
    """
    labels = list(surfaces)
    changes = []
    for older, newer in zip(labels, labels[1:], strict=False):
        before = set(surfaces[older])
        after = set(surfaces[newer])
        changes.append(
            SurfaceChange(
                older=older,
                newer=newer,
                gained=tuple(sorted(after - before)),
                lost=tuple(sorted(before - after)),
            )
        )
    return tuple(changes)


#: What a version view raises for a command it does not carry. Matched
#: by CLASS NAME rather than imported, because this module sits below
#: `commands` in the dependency order. A bare `except Exception` was
#: measured reporting a patched-in TypeError as "this build has no row",
#: which would send a maintainer to add rows that already exist, so
#: anything that is not the refusal propagates.
_REFUSAL_NAME = "CommandNotInVersionError"

#: The two refusals a version registry makes for a label it cannot turn
#: into exactly one build: the name is unregistered, or it is a vendor
#: alias several builds share. Both are ordinary in the read-before-you-
#: register workflow and neither is a program error, so both are
#: reported rather than raised out of a CLI. Matched by class name for
#: the same layering reason as the refusal above.
_UNRESOLVED_LABEL = frozenset({"UnknownVersionError", "AmbiguousVersionAliasError"})


@dataclass(frozen=True, kw_only=True)
class UnreachableCommand:
    """A command an edition documents that its build cannot emit.

    Attributes
    ----------
    command : str
        Command name as the edition prints it.
    edition : str
        Label of the edition that documents it.
    reason : str
        ``"no entry"`` when the database has no entry of that name at
        all, or ``"refused"`` when it has one and the version view
        refuses it, which means no row for this build and none reachable
        by hotfix inheritance. Those two and no others: an edition whose
        label cannot be resolved is not a command and is reported
        through :attr:`Reachability.unmeasured` instead, having been a
        third value of this field for one commit.
    """

    command: str
    edition: str
    reason: str


def unreachable_commands(
    editions: Iterable[Edition],
    *,
    recorded: RegistryLike,
    reader: Callable[..., Mapping[int, str]] | None = None,
) -> Reachability:
    """Report, per edition, the documented commands its build cannot emit.

    This is the row-level half of the coverage question, and it exists
    because the entry-level half cannot answer it.
    :func:`sweep_editions` compares the manuals against the set of entry
    NAMES, so an entry that exists but carries no row for one edition is
    invisible to it: the sweep reports zero absent while that build's
    emitter refuses a command the caller's own manual documents. That is
    not a hypothetical. On 2026-08-10 the sweep reported zero across
    eight editions while three editions could not emit
    ``EXPORT_ALL_SURFACE_STREAMLINES``, whose two family siblings on the
    same manual pages did carry the rows.

    Reachability, not row presence, is the measure, because a genuine
    hotfix inherits its base release's records: 26.122 carries twenty
    direct rows and reaches 375, and counting rows would report it as
    missing hundreds.

    Parameters
    ----------
    editions : iterable of Edition
        The manuals to read.
    recorded : RegistryLike
        The loaded database. Typed loosely because this module sits
        below ``commands`` in the dependency order (CLAUDE.md Layout)
        and must not import it; it is used through ``.commands`` and
        ``.for_version``.
    reader : callable, optional
        What turns a manual and a page range into text, defaulting to
        :func:`read_pdf_pages`.

    Returns
    -------
    Reachability
        Its ``findings`` are sorted by edition then command and empty
        means every command every readable edition documents can be
        emitted for that build. Its ``unmeasured`` names the editions
        whose label the registry could not resolve, about which nothing
        was learned either way.

    Raises
    ------
    ManualDraftError
        If no edition is given, or if two editions share a label. Same
        two refusals as :func:`edition_surfaces` and for the same
        reason: with no edition every command is vacuously reachable,
        which is a configuration error reading as the good outcome.
    """
    read = reader if reader is not None else read_pdf_pages
    editions = tuple(editions)
    unmeasured: list[str] = []
    if not editions:
        raise ManualDraftError(
            "measuring reachability needs at least one edition; with none every "
            "command is vacuously reachable and the answer would be a clean report "
            "over nothing. Add a row to the manifest with label, manual and chapter"
        )
    labels = [edition.label for edition in editions]
    duplicated = sorted({label for label in labels if labels.count(label) > 1})
    if duplicated:
        raise ManualDraftError(
            f"the manifest gives more than one edition the label(s) {', '.join(duplicated)}; "
            "each label names one build and a repeat would measure that build twice while "
            "leaving another unmeasured"
        )

    entries = recorded.commands
    found = []
    for edition in editions:
        printed = parse_signatures(
            read(edition.manual, first=edition.chapter[0], last=edition.chapter[1])
        )
        # AN UNREGISTERED BUILD IS SWEPT, NOT REFUSED. Reading a new
        # vendor manual before the build is registered is this tool's
        # first workflow and `Edition.label` promises it: nothing
        # resolves the label against the version registry. Asking for a
        # version view does resolve it, so an unregistered label is
        # reported as unmeasurable rather than raised out of a CLI,
        # which is what it did for one commit.
        try:
            view = recorded.for_version(edition.label)
        except Exception as unresolved:  # noqa: BLE001 - the types live a layer above
            # TWO refusals reach here and the first version of this
            # matched the wording of one. A label the registry cannot
            # turn into exactly one build is either unregistered or an
            # ALIAS naming several, and the alias is the likelier of the
            # two in this workflow: a maintainer holding a new manual
            # writes the name the pdf prints, which is the vendor name.
            # That raised out of the CLI.
            if type(unresolved).__name__ not in _UNRESOLVED_LABEL:
                raise
            unmeasured.append(edition.label)
            continue
        for name in sorted(printed):
            if name not in entries:
                found.append(
                    UnreachableCommand(command=name, edition=edition.label, reason="no entry")
                )
                continue
            try:
                view[name]
            except Exception as refusal:  # noqa: BLE001 - the type lives a layer above
                if type(refusal).__name__ != _REFUSAL_NAME:
                    raise
                found.append(
                    UnreachableCommand(command=name, edition=edition.label, reason="refused")
                )
    return Reachability(findings=tuple(found), unmeasured=tuple(unmeasured))


@dataclass(frozen=True, kw_only=True)
class Reachability:
    """What a reachability sweep found, and what it could not look at.

    Two fields rather than one tuple, because an edition whose label the
    registry cannot resolve is not a command and was being reported as
    one: it entered the findings with the string ``(every command)`` in
    the command field, so the CLI counted it in "N command(s) an edition
    documents that its build cannot emit" and ``--fail-if-absent``
    failed on it. That is a build nobody has registered yet, which
    ``Edition.label`` explicitly promises can be swept.

    Attributes
    ----------
    findings : tuple of UnreachableCommand
        One per command an edition documents that its build cannot
        emit. Empty when every edition read is complete.
    unmeasured : tuple of str
        Labels the version registry could not turn into exactly one
        build, either unregistered or a vendor alias several builds
        share. Nothing is known about their commands, which is a
        different statement from knowing they cannot be emitted.
    """

    findings: tuple[UnreachableCommand, ...]
    unmeasured: tuple[str, ...]


@dataclass(frozen=True, kw_only=True)
class StaleCitation:
    """A version row whose cited page does not hold the command.

    Attributes
    ----------
    command : str
        Command name the row belongs to.
    edition : str
        Label of the edition the row cites.
    cited : int
        Page number written in the row's note.
    found : int or None
        Page the edition actually prints the signature on, or None.
    reason : str
        Which finding this is, because ``found is None`` alone carried
        two of them and the report printed one: ``"moved"`` when the
        edition prints the command elsewhere, ``"absent"`` when it does
        not print it at all, and ``"wrong source"`` when the note names
        another edition's source id. The three want different repairs.
        A moved page is a citation to correct, an absent command is a
        row that should not exist, and a wrong source is a row read
        against the wrong document.
    """

    command: str
    edition: str
    cited: int
    found: int | None
    reason: str


@runtime_checkable
class VersionRowLike(Protocol):
    """The two fields :func:`stale_citations` reads off a version row.

    Declared as a protocol rather than left implicit, because this
    module sits below ``commands`` in the dependency order and cannot
    import the real type. Every read of that type was a ``getattr`` with
    a swallowing default, so renaming ``VersionStatus.note`` would have
    made the check return no findings forever with a green suite; the
    tier-1 test asserting the real registry satisfies this is what turns
    that silence into a red.
    """

    @property
    def note(self) -> str | None:
        """Paraphrased justification, where the row carries one."""

    @property
    def status(self) -> object:
        """The row's evidence status, read through its ``value``."""


@runtime_checkable
class CommandEntryLike(Protocol):
    """The one field :func:`stale_citations` reads off a command entry."""

    @property
    def versions(self) -> Mapping[str, VersionRowLike]:
        """Evidence per canonical version identifier."""


@runtime_checkable
class RegistryLike(Protocol):
    """What the citation and reachability checks need of the database.

    Both attributes, because the two checks need different halves:
    :func:`stale_citations` walks ``commands`` and
    :func:`unreachable_commands` also asks ``for_version`` what a build
    can emit. An earlier version of this docstring named both checks
    while declaring only the first one's half, so the protocol would not
    have typed the function it claimed to cover.
    """

    @property
    def commands(self) -> Mapping[str, CommandEntryLike]:
        """Every entry, keyed by command name."""

    def for_version(self, version: Any) -> Any:
        """Return the per-version view of the database."""


#: Rows seen and rows actually checked, per edition, from the last
#: :func:`stale_citations` run. It exists because a clean report is not
#: a clean bill and the caller cannot tell the two apart from the
#: findings alone.
#:
#: 26.120 is the build that makes the point, and its figure was written
#: here as 18 of 381 before being measured again: it is ZERO of 381.
#: 363 of those rows cite no page of their own, because that build is
#: the flagship whose entries carry the citation at entry level, and the
#: 18 that do cite a page are every one of them `removed` rows, which
#: this check skips by design since their citation addresses an absence.
#: Eighteen is the number of rows SKIPPED, not checked, and the two are
#: easy to swap when neither is printed.
citation_reach: dict[str, list[int]] = {}


def stale_citations(
    editions: Iterable[Edition],
    *,
    recorded: RegistryLike,
    reader: Callable[..., Mapping[int, str]] | None = None,
) -> tuple[StaleCitation, ...]:
    """Check every version row's page citation against the manual it names.

    A citation is written once, from a reading, and then nothing looks
    at it again. That is how ten rows came to cite a document that had
    moved underneath them: the 25.000 manual is a conversion of a help
    archive, the conversion was corrected to strip a generator footer,
    the correction shifted the document by five pages, and the rows
    written from the earlier conversion kept its numbers. Every one of
    the ten pointed at a real page of a real manual, which is why
    nothing looked wrong.

    Parameters
    ----------
    editions : iterable of Edition
        The manuals to check against. The manual side comes first and
        the database is keyword-only, matching
        :func:`sweep_editions` and :func:`coverage_against`; two
        adjacent positional parameters of unrelated kinds is a call
        nobody can read.
    recorded : RegistryLike
        The loaded database, used through ``.commands``. Typed loosely
        because this module sits below ``commands`` in the dependency
        order (CLAUDE.md Layout) and must not import it, which is also
        why the check cannot default to loading it.
    reader : callable, optional
        What turns a manual and a page range into text, defaulting to
        :func:`read_pdf_pages`. Same seam as :func:`edition_surfaces`.

    Returns
    -------
    tuple of StaleCitation
        One entry per disagreeing row, sorted by command then edition.

    Raises
    ------
    ManualDraftError
        If no edition is given, or if two editions share a label, or if
        the mapping exposes no version rows at all. All three are
        configuration errors that would otherwise return an empty tuple,
        and an empty tuple from this function reads as a clean bill.

    Notes
    -----
    Three classes of row are NOT checked, and silence about a row is
    therefore never a claim that the row is right.

    A ``removed`` row is skipped: its citation addresses an ABSENCE and
    names the pages the command is not on, so checking it the same way
    would report every honest removal record as a defect.

    A row whose note carries no page cannot be checked, and most rows do
    not carry one. So can a row whose edition the manifest does not
    list.

    A note citing a page RANGE is satisfied by any page in it. Twenty-six
    shipped rows cite one, and reading only the first page of a span
    reports a correct citation as wrong whenever the signature heading
    sits on the second.

    The SOURCE is checked too, where the manifest records one: a note
    citing SRC-003 on a row keyed to the edition SRC-740 was reading a
    different document, and page numbers between those two differ by a
    uniform three, so a coincidence is cheap.
    """
    read = reader if reader is not None else read_pdf_pages
    editions = tuple(editions)
    if not editions:
        raise ManualDraftError(
            "checking citations needs at least one edition; with none every citation "
            "holds vacuously and the report would be a clean bill over nothing. Add a "
            "row to the manifest with label, manual and chapter"
        )
    labels = [edition.label for edition in editions]
    duplicated = sorted({label for label in labels if labels.count(label) > 1})
    if duplicated:
        raise ManualDraftError(
            f"the manifest gives more than one edition the label(s) {', '.join(duplicated)}; "
            "each label names one build and a repeat would check every row of that label "
            "against the last reading while leaving another edition unread"
        )

    entries = recorded.commands
    if not any(getattr(entry, "versions", None) for entry in entries.values()):
        raise ManualDraftError(
            "the database given exposes no version rows, so there is nothing to check "
            "and the answer would be a clean bill. Pass a loaded CommandRegistry"
        )

    sources = {edition.label: edition.source for edition in editions}
    # CLEARED BEFORE THE READS, not after them. It sat after the loop
    # that opens the manuals, so a run whose reader raised left the
    # PREVIOUS manifest's numbers in place for a caller that caught the
    # error and printed the reach.
    reach = citation_reach
    reach.clear()
    for edition in editions:
        reach[edition.label] = [0, 0]
    surfaces: dict[str, dict[str, ManualCommand]] = {}
    for edition in editions:
        surfaces[edition.label] = dict(
            parse_signatures(
                read(edition.manual, first=edition.chapter[0], last=edition.chapter[1])
            )
        )

    stale = []
    for name, entry in entries.items():
        for label, row in getattr(entry, "versions", {}).items():
            parsed = surfaces.get(label)
            if parsed is None:
                continue
            reach[label][0] += 1
            note = getattr(row, "note", None)
            if not note:
                continue
            match = _CITED_PAGE.search(note)
            if match is None:
                continue
            if getattr(getattr(row, "status", None), "value", None) == "removed":
                continue
            reach[label][1] += 1
            source, first, last = match.group(1), int(match.group(2)), match.group(3)
            span = range(first, (int(last) if last else first) + 1)
            command = parsed.get(name)
            expected = sources.get(label)
            if expected and source != expected:
                stale.append(
                    StaleCitation(
                        command=name,
                        edition=label,
                        cited=first,
                        found=None,
                        reason="wrong source",
                    )
                )
                continue
            if command is not None and command.page in span:
                continue
            stale.append(
                StaleCitation(
                    command=name,
                    edition=label,
                    cited=first,
                    found=None if command is None else command.page,
                    reason="absent" if command is None else "moved",
                )
            )
    return tuple(sorted(stale, key=lambda item: (item.command, item.edition)))


#: A page citation inside a version-row note, source and page together,
#: for example "SRC-749 p.286" or "SRC-741 pp.312-313". The source is
#: captured because a page number alone checks half a citation: a note
#: naming another edition's source would otherwise be read against this
#: edition's pdf, and between SRC-003 and SRC-740 the pages differ by a
#: uniform three, so a coincidence is cheap. The optional second page is
#: captured because a span is satisfied by any page in it, and 26
#: shipped rows cite one.
_CITED_PAGE = re.compile(r"\b(SRC-\d{3})\s+pp?\.\s*(\d+)(?:\s*-\s*(\d+))?")

#: What an edition row may hold, and what each key is for. Kept as data
#: so the refusals can print it rather than restate it in prose.
_MANIFEST_KEYS = {
    "label": "canonical version identifier, for example 26.121",
    "manual": "path of the manual pdf",
    "chapter": "FIRST-LAST pages of the scripting reference",
    "index": "FIRST-LAST pages of the Script Index, optional",
    "source": "citation id, for example SRC-740, optional",
}
_MANIFEST_REQUIRED = ("label", "manual", "chapter")


def read_edition_manifest(path: str | Path) -> tuple[Edition, ...]:
    """Read an edition manifest, the file that makes a sweep repeatable.

    The manifest is a list of mappings with the keys of :class:`Edition`,
    ``chapter`` and ``index`` written as ``FIRST-LAST``. It is a file
    rather than repeated command-line flags because it is the thing a
    new build EDITS: registering one is adding a row, and the row is
    then under the maintainer's own version control rather than retyped
    from a session note.

    It is never committed here. It names paths of licensed manuals, and
    those live in ``_private/`` (CLAUDE.md invariant 1).

    Named for the manifest and not for the editions, unlike the
    neighbouring :func:`read_pdf_pages`: this opens a small text file and
    returns descriptors, and opens no manual at all.

    Parameters
    ----------
    path : str or Path
        Manifest file, YAML.

    Returns
    -------
    tuple of Edition
        In the order written.

    Raises
    ------
    ManualDraftError
        If the file is not a list of mappings, if a row lacks ``label``,
        ``manual`` or ``chapter``, carries a key outside the five, names
        a manual that does not exist, or writes a page range that is not
        ``FIRST-LAST`` with FIRST no greater than LAST. Every check names
        the offending row, because a manifest is edited rarely and by
        hand, and EVERY row is checked before any manual is opened: a
        typo in the fourth row used to surface after three manuals had
        been parsed.

    Examples
    --------
    A manifest with one edition, as it would be written by hand::

        - label: "26.121"
          source: SRC-740
          manual: _private/manual/user-manual-26121.pdf
          chapter: 284-379
          index: 380-386
    """
    text = Path(path).read_text(encoding="utf-8")
    rows = yaml.safe_load(text)
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise ManualDraftError(
            f"{path} must hold a list of edition mappings, not {type(rows).__name__}"
        )

    def _range(row: dict, key: str, where: str) -> tuple[int, int]:
        spec = str(row[key])
        first, _, last = spec.partition("-")
        if not last or not first.isdigit() or not last.isdigit():
            raise ManualDraftError(
                f"{where}: {key} must read FIRST-LAST in page numbers, got {spec!r}"
            )
        if int(first) > int(last):
            raise ManualDraftError(f"{where}: {key} ends before it starts, {spec!r}")
        return int(first), int(last)

    known = ", ".join(f"{key} ({why})" for key, why in _MANIFEST_KEYS.items())
    editions = []
    for position, row in enumerate(rows, start=1):
        where = f"{path} entry {position}"
        for key in _MANIFEST_REQUIRED:
            if key not in row:
                raise ManualDraftError(f"{where}: missing {key!r}. An edition row holds {known}")
        unknown = sorted(set(row) - set(_MANIFEST_KEYS))
        if unknown:
            # Refused rather than ignored, because the shape of the
            # degradation is misleading: a misspelled 'index' key leaves
            # every command unlabelled, and the report then says the
            # index does not name them, which is a statement about the
            # manual rather than about the typo that caused it.
            raise ManualDraftError(
                f"{where}: unknown key(s) {unknown}. An edition row holds {known}"
            )
        # Ranges before existence: both are checked before any manual is
        # opened, which is the point, and within a row a malformed page
        # range is the more specific complaint of the two.
        chapter = _range(row, "chapter", where)
        index = _range(row, "index", where) if "index" in row else None
        manual = Path(str(row["manual"]))
        if not manual.is_file():
            raise ManualDraftError(
                f"{where}: manual {str(manual)!r} is not a readable file. Manual paths are "
                "relative to the working directory and name licensed material this "
                "repository never carries, so a fresh clone has to point them at its own copy"
            )
        editions.append(
            Edition(
                label=str(row["label"]),
                manual=manual,
                chapter=chapter,
                index=index,
                source=str(row["source"]) if "source" in row else None,
            )
        )
    return tuple(editions)


def read_pdf_pages(path: str | Path, *, first: int, last: int) -> dict[int, str]:
    """Extract the text of a page range from a manual pdf.

    Separated from every function above so the parsing is testable
    without a pdf and without the optional dependency: everything else in
    this module takes text.

    The range is keyword-only and validated, both for the same reason. A
    swapped pair of one-based page numbers used to return an empty
    mapping, and ``coverage_against`` reads an empty mapping as a manual
    that documents nothing: every database command lands under
    "recorded here but not in this manual" and none under "absent",
    which is a confident, clean-looking answer produced by a typo. A
    ``first`` of zero indexed the pdf at -1 and keyed the manual's LAST
    page as page 0, so a drafted entry cited ``p.0``.

    Parameters
    ----------
    path : str or Path
        The manual. It is licensed vendor material, lives in
        ``_private/`` and never enters Git (CLAUDE.md invariant 1); only
        paraphrases and page citations derived from it are committed.
    first, last : int
        One-based, inclusive page range. Keyword-only.

    Returns
    -------
    dict of int to str
        Extracted text keyed by one-based page number, one entry per
        page of the requested range.

    Raises
    ------
    ManualDraftError
        If the range is not one-based and ascending, or if it reaches
        past the end of the document. A short read is never returned.
    MissingExtraError
        When the ``manual`` extra is not installed.
    """
    if first < 1 or last < first:
        raise ManualDraftError(
            f"page range {first}-{last} is not a one-based ascending range. The manual's "
            "own page numbers are one-based, and a reversed pair reads no pages at all, "
            "which every caller here would report as a manual documenting nothing."
        )
    try:
        import pypdf
    except ImportError as error:  # pragma: no cover - exercised by the extras test
        from pyflightstream.extras import missing_extra

        raise missing_extra(
            "manual", package="pypdf", purpose="reading a FlightStream manual pdf"
        ) from error

    reader = pypdf.PdfReader(path)
    if last > len(reader.pages):
        raise ManualDraftError(
            f"page range {first}-{last} reaches past the end of {path}, which has "
            f"{len(reader.pages)} pages. Truncating would answer from a short read, and "
            "the page count is also the cheapest sign that this is the wrong edition: "
            "the registered manuals run between roughly 350 and 415 pages."
        )
    # LAYOUT mode, not the default. The default reconstructs a page as a
    # flowing string and, on some renderers, joins what were separate
    # visual lines: a sample block and the signature heading after it
    # come back as ONE line, and a parser that anchors on the start of a
    # line then sees neither. Measured on 2026-08-10 across all six pdf
    # editions this repository reads: the two modes find exactly the same
    # commands, 274, 276, 344, 363, 363 and 364, so nothing is traded
    # away. On a pdf converted from a compiled help archive the default
    # found 58 commands of 272 and layout found 270.
    return {
        i + 1: (reader.pages[i].extract_text(extraction_mode="layout") or "")
        for i in range(first - 1, last)
    }


# --- drafting -------------------------------------------------------------
#
# Turning a parsed command into a database entry is where judgement enters,
# so everything below is explicit about which parts are read and which are
# guessed. Two rules hold the shape:
#
#   * the default never writes. `render_chapter` returns text and touches
#     nothing; `write_chapter` writes only when told to, and says what it
#     did either way.
#   * every drafted entry carries a `drafted:` provenance line naming the
#     tool, the manual and the page. A machine-drafted entry is therefore
#     findable with one grep, which is what makes reviewing a tranche
#     possible at all, and what stops a draft from quietly becoming
#     evidence.

#: Argument names the manual writes generically. The database prefers a
#: name that says what the value MEANS, and mapping the common ones saves
#: a reviewer the most repetitive part of the work. Everything not here is
#: passed through lowercased, and a reviewer renames it.
_GENERIC_NAMES = {
    "value": "value",
    "enable / disable": "mode",
    "enable/disable": "mode",
    "index": "index",
    "name": "name",
}

#: Section of the Script Index to the database's phase vocabulary. A
#: section this does not name yields None, and the draft says `phase: ???`
#: rather than guessing, because emitting a wrong phase would make the
#: ordering checks refuse a correct script.
_PHASE_BY_SECTION = {
    "Script Controls": "control",
    "Opening  Closing    Saving": "init",
    "Mesh Import   Export": "init",
    "Coordinate Systems": "setup",
    "Actuators": "setup",
    "Motion Definitions": "setup",
    "Base Regions": "setup",
    "Trailing Edges": "setup",
    "Wake Termination Nodes": "setup",
    "Boundary Layer Transition Trips": "setup",
    "Inlets and Outlets": "setup",
    "Solver Settings": "init",
    "Advanced Settings": "init",
    "Runtime Settings": "init",
    "Fluid Properties": "init",
    "Free Stream Velocity": "init",
    "Solver Initialization   Execution": "solve",
    "Unsteady Solver": "solve",
    "Sweeper Toolbox": "solve",
    "Solver Analysis": "post",
    "Solver Data Export": "post",
    "Output Status": "post",
}


def _argument_name(raw: str) -> str:
    """Return the database-style name for a manual placeholder."""
    cleaned = raw.strip().lower()
    return _GENERIC_NAMES.get(cleaned, cleaned.replace(" ", "_").replace("-", "_"))


#: Words a parameter description opens with that decide a type on their
#: own, in the order they are tried. Data rather than a chain of ifs so a
#: reader can check the list, and so the reasons stay one per rule.
_TYPE_BY_OPENING: tuple[tuple[tuple[str, ...], str, str], ...] = (
    (("number of", "num of"), "int", "the description counts something"),
    (("index of", "1-based index", "index value"), "int", "the description names an index"),
    (
        ("file name with path", "filename with path", "name of the file", "path to file"),
        "path",
        "the description names a file path",
    ),
    (("assign name", "name of the", "name to"), "str", "the description names a label"),
)

#: Placeholder suffixes that carry a physical dimension, so the value is
#: real rather than whole. Checked after the openings above, because a
#: count of time steps ends in _STEPS and is still an integer.
_FLOAT_SUFFIXES = (
    "_ANGLE",
    "_AREA",
    "_DIAMETER",
    "_HEIGHT",
    "_LENGTH",
    "_RADIUS",
    "_RATE",
    "_TIME",
    "_TOLERANCE",
    "_VELOCITY",
)


@dataclass(frozen=True)
class TypeRule:
    """One rule of :func:`propose_type`, and its position in the order.

    The rules were a chain of ``if`` statements until 2026-08-06, and
    three consecutive review rounds each found one of them in the wrong
    place: the openings below the enum rules, then the toggle pair above
    the openings, then the dimension suffix below the enum rules. The
    order is not incidental to what the function means, so it is a LIST
    a reader sees at a glance and a test can walk, rather than a shape
    recovered by reading control flow.

    Attributes
    ----------
    name : str
        Short identifier, used by the tests that pin the order.
    reason : str
        What :func:`propose_type` reports when this rule answers.
    read : callable
        Takes the upper-cased placeholder and the description, and
        returns ``(type, values)`` or None for "this rule has nothing
        to say".
    """

    name: str
    reason: str
    read: Callable[[str, str], tuple[str, tuple[str, ...]] | None]


def _read_opening(_placeholder: str, text: str) -> tuple[str, tuple[str, ...]] | None:
    """Answer from the phrase a description OPENS with.

    First of all the rules, and the position is the fix rather than a
    preference: every rule below reads tokens out of a sentence, so a
    count whose description happens to spell an alternative ("Number of
    boundaries in the STL or OBJ import") was read as a closed set and
    drafted ``values: [STL, OBJ]``. A wrong ``???`` costs a reviewer a
    minute; an invented token list loads, and then validates other
    people's scripts.

    A leading article is stripped, because "The number of boundaries"
    and "Number of boundaries" are the same statement and only the
    second one used to be read.
    """
    lowered = _ARTICLE.sub("", text.lower(), count=1)
    for openings, proposed, _reason in _TYPE_BY_OPENING:
        if lowered.startswith(openings):
            return proposed, ()
    return None


def _read_integer_word(_placeholder: str, text: str) -> tuple[str, tuple[str, ...]] | None:
    """Answer where the description says the value is whole."""
    lowered = text.lower()
    if "integer value" in lowered or "integer number" in lowered:
        return "int", ()
    return None


def _read_dimension(placeholder: str, text: str) -> tuple[str, tuple[str, ...]] | None:
    """Answer from a placeholder that names a physical quantity.

    Above the enum rules and below the openings. It sat at the very
    bottom, so a dimensioned placeholder whose prose happened to contain
    an "X or Y" pair was read as a closed set; and it must stay below the
    openings, because a count of time steps ends in ``_STEPS`` and is
    still an integer.
    """
    if placeholder.endswith(_FLOAT_SUFFIXES) or "units =" in text.lower():
        return "float", ()
    return None


def _read_toggle(_placeholder: str, text: str) -> tuple[str, tuple[str, ...]] | None:
    """Answer the ENABLE/DISABLE pair, matched AS PRINTED.

    Case-insensitively it read the ordinary words "enabled" and
    "disabled" out of a sentence about boundaries and proposed an enum
    for a count, which was the one disagreement against the corpus this
    rule set was measured on.

    Below the explicit enumeration, because a closed set that happens to
    contain both toggle tokens among others would otherwise be truncated
    to the two.
    """
    if "ENABLE" in text and "DISABLE" in text:
        return "enum", ("ENABLE", "DISABLE")
    return None


def _read_enumeration(_placeholder: str, text: str) -> tuple[str, tuple[str, ...]] | None:
    """Answer from the phrase that introduces a closed set.

    Reads only the SENTENCE carrying the phrase. Reading the whole
    description took tokens from the sentences after it, so a two-value
    threshold whose next sentence named the argument it feeds proposed
    three values instead of two.
    """
    phrase = _ENUM_PHRASE.search(text)
    if phrase is None:
        return None
    tokens = _tokens_in(_first_sentence(text[phrase.end() :]))
    return ("enum", tokens) if len(tokens) >= 2 else None


def _read_alternatives(_placeholder: str, text: str) -> tuple[str, tuple[str, ...]] | None:
    """Answer an ``X, Y or Z`` list, read from the whole description.

    Unlike the enumeration rule above, which is sentence-bounded. This
    pattern requires capitalised tokens joined by "or", which prose does
    not produce, and bounding it lost the coordinate planes.
    """
    tokens = _alternatives_in(text)
    return ("enum", tokens) if len(tokens) >= 2 else None


#: The rules in the order they are tried. THE ORDER IS THE SPECIFICATION:
#: read it top to bottom and each rule's docstring says why it sits where
#: it does. ``tests/test_utils_manual.py`` pins both the sequence and one
#: worked case per adjacent pair.
TYPE_RULES: tuple[TypeRule, ...] = (
    TypeRule("opening", "the description opens with what the value is", _read_opening),
    TypeRule("integer-word", "the description says the value is whole", _read_integer_word),
    TypeRule("dimension", "the parameter carries a physical dimension", _read_dimension),
    TypeRule("enumeration", "the description enumerates the accepted tokens", _read_enumeration),
    TypeRule(
        "alternatives", "the description spells the alternatives with 'or'", _read_alternatives
    ),
    TypeRule("toggle", "the description offers the two toggle tokens", _read_toggle),
)


def _first_sentence(text: str) -> str:
    """Return ``text`` up to its first sentence break, or all of it."""
    return _SENTENCE_END.split(text, maxsplit=1)[0]


def _alternatives_in(span: str) -> tuple[str, ...]:
    """Return the tokens of an ``X, Y or Z`` list, empty when there is none."""
    match = _ENUM_ALTERNATIVES.search(span)
    if match is None:
        return ()
    return tuple(dict.fromkeys(re.findall(r"[A-Z][A-Z0-9_]*", match.group(0))))


def _tokens_in(span: str) -> tuple[str, ...]:
    """Return the accepted tokens a span lists, by whichever shape it uses.

    The ``or`` form is tried first because it admits SHORT tokens: the
    coordinate planes are spelled ``XY , XZ or YZ`` and the loft types
    ``C2 or C0``, and the general token pattern needs three characters,
    deliberately, so that a capitalised ordinary word cannot pass for a
    token outside an explicit alternatives list.
    """
    alternatives = _alternatives_in(span)
    if len(alternatives) >= 2:
        return alternatives
    return tuple(dict.fromkeys(_ENUM_TOKEN.findall(span)))


def propose_type(placeholder: str, description: str) -> tuple[str | None, tuple[str, ...], str]:
    """Suggest an argument type from the manual's parameter table.

    The third source, after the signature line and the sample block, and
    the only one that says anything about a TYPE. It answered 57 percent
    of the 148 arguments measured on 2026-08-05 and proposed nothing for
    the rest, where the caller writes ``???`` rather than a guess.

    The rules are tried in a stated order and the order is load-bearing.
    A counting or indexing opening decides before either enum rule,
    because both enum rules read tokens out of a sentence and a count
    whose description mentions two alternatives is still a count. Both
    enum rules then read only the sentence carrying the phrase that
    introduces the set.

    Nothing of the description reaches the return value. The reason is a
    sentence about the SHAPE the rule matched, not a paraphrase of the
    manual, so a draft carries no licensed text (invariant 1).

    Parameters
    ----------
    placeholder : str
        Parameter name as the manual prints it, for example
        ``"NUM_BOUNDARIES"``.
    description : str
        The manual's prose for that parameter, as
        :attr:`ManualCommand.parameters` holds it.

    Returns
    -------
    tuple
        ``(type, values, reason)``. ``type`` is a database ``ArgType``
        value, or None when no rule matched. ``values`` is the token
        tuple of an ``enum`` and empty otherwise. ``reason`` says which
        rule answered, or why none did.
    """
    text = description.strip()
    upper = placeholder.upper()

    for rule in TYPE_RULES:
        answer = rule.read(upper, text)
        if answer is not None:
            proposed, values = answer
            return proposed, values, rule.reason
    if not text:
        return None, (), "the command documents no parameter table"
    return None, (), "no rule read a type from the description"


def sample_contradiction(
    command: ManualCommand,
    *,
    index: int,
    proposed: str | None,
    values: tuple[str, ...] = (),
) -> str | None:
    """Report the sample token a proposed type would refuse.

    The parameter table is not the only thing the manual says about an
    argument: the page also PRINTS a call. A proposal read from the table
    alone is therefore a reading of one source that another source on the
    same page can already falsify, and this is that second reading.

    What it does NOT claim is that the manual contradicts itself. Four
    causes produce the same signal and only a person can tell them apart:
    the table offered "label or number" and only the labels were read;
    the table is genuinely incomplete; the sample is a typo; or the
    argument list is out of step with the signature so the compared token
    belongs to a different argument. All four mean the proposal must not
    be written, which is the only decision this function makes.

    Measured on 2026-08-06 across the four registered editions, 195
    enumeration positions in this database had a printed sample to check
    against and 19 of them, spanning seven commands, declared a value set
    that refuses the token the sample passes. ``CAD_BODY_ROTATE`` has a
    parameter table naming the three axis letters and a sample calling it
    with the index ``2``, on the same page, in every edition; three
    ``SWEEPER_SET_*_SWEEP`` commands omit a mode their own samples use.

    Why this belongs here rather than in a review checklist: both facts
    are already in :class:`ManualCommand`, so the tool had everything it
    needed and compared nothing. The earlier measurement that certified
    :func:`propose_type` as never disagreeing with a hand-authored type
    could not have caught this, because those entries were authored from
    the same parameter table; the tool and the reviewer read one source
    and agreed with each other about it.

    Parameters
    ----------
    command : ManualCommand
        Parsed entry. Its sample supplies the evidence and its
        ``inline_args`` the positions.
    index : int
        ZERO-based position in ``command.inline_args``. Keyword-only,
        along with everything after it, because a call reading
        ``sample_contradiction(cmd, 1, "enum", ("X", "Y"))`` says nothing
        about which of those is which.
    proposed : str or None
        Type :func:`propose_type` returned, or None when no rule
        answered. None is never contradicted: an unanswered argument
        refuses nothing.
    values : tuple of str, optional
        Token set of an enumeration proposal.

    Returns
    -------
    str or None
        The token the sample passes at that position, when the proposed
        type would refuse it. None when the proposal accepts the token,
        and also when the sample cannot answer: a command with no sample,
        a sample whose first line is not the call, or a call with fewer
        tokens than the signature has placeholders. Those three are
        silent rather than reported because the absence of a sample is
        not evidence of agreement, and a caller that treated None as
        confirmation would be reading it as one.

    Raises
    ------
    ManualDraftError
        If ``index`` is outside the command's own argument list. It used
        to index the sample tokens directly, so a caller passing the
        1-based position a person reads off the manual page got a
        confident report about the NEXT argument's token, phrased
        exactly like a real finding. A caller bug must not be able to
        produce a plausible sentence.
    """
    if not 0 <= index < len(command.inline_args):
        raise ManualDraftError(
            f"{command.name} declares {len(command.inline_args)} inline argument(s) and "
            f"index {index} is outside them. The index is ZERO-based and addresses "
            "the signature, not the sample: indexing the sample directly turns an "
            "off-by-one into a confident report about a different argument."
        )
    if proposed in ("enum", "enum_list") and not values:
        raise ManualDraftError(
            f"{command.name}: an {proposed} proposal was passed with no token set, so "
            "every sample token would be reported as refused and the draft would carry "
            "a page of confident findings. This is the caller-bug shape the index "
            "refusal above exists for, on the parameter beside it: pass the tokens "
            "propose_type returned alongside the type. An enumeration accepting "
            "nothing is not a state this database admits either (ArgSpec refuses it)."
        )
    if proposed is None or not command.sample:
        return None
    head = command.sample[0]
    if not head.startswith(command.name):
        return None
    tokens = head.split()[len(command.name.split()) :]
    if index >= len(tokens):
        return None
    token = tokens[index]
    if proposed in ("enum", "enum_list"):
        return None if token.upper() in {v.upper() for v in values} else token
    if proposed == "int":
        try:
            int(token)
        except ValueError:
            return token
        return None
    if proposed == "float":
        try:
            float(token)
        except ValueError:
            return token
        return None
    return None


def render_entry(
    command: ManualCommand,
    *,
    source: str,
    versions: Mapping[str, str],
    phase: str | None = None,
) -> str:
    """Render one command as a database entry, for a person to review.

    Parameters
    ----------
    command : ManualCommand
        Parsed entry, from :func:`parse_signatures`.
    source : str
        Manual source id for the citation, for example ``"SRC-741"``.
    versions : mapping of str to str
        Canonical version to status. Only ``documented`` is meaningful
        from a manual: ``verified`` and ``broken`` need a committed probe
        report and this function will not write them (invariant 3).
    phase : str, optional
        Overrides the phase proposed from the section.

    Returns
    -------
    str
        YAML for one entry, with ``???`` wherever the manual does not
        answer, so an unreviewed draft cannot load: the database schema
        refuses those values and the suite goes red rather than green
        over a guess.

    Raises
    ------
    ManualDraftError
        If a status other than ``documented`` is requested, since a
        manual is not probe evidence. A ``ValueError`` as well, so a
        caller written before the catalogue still catches it.
    """
    bad = sorted({s for s in versions.values() if s != "documented"})
    if bad:
        raise ManualDraftError(
            f"{command.name}: a DRAFT from a manual supports the status 'documented' "
            f"only, and {bad} were requested. Every status the harness measures "
            "(verified, broken, and a removed the solver refused) is promoted from a "
            "committed probe report by pyfs-qa apply-compat (CLAUDE.md invariant 3). "
            "A removed read off an edition instead is a hand-written row carrying a "
            "note and a page, not a drafted one."
        )

    layout, why = propose_layout(command)
    resolved = phase or _PHASE_BY_SECTION.get(command.section or "", "???")
    lines = [
        f"{command.name}:",
        f"  layout: {layout}",
        f"  phase: {resolved}",
    ]
    typed, unanswered = 0, 0
    contradicted: list[str] = []
    if command.inline_args:
        lines.append("  args:")
        for index, raw in enumerate(command.inline_args):
            proposed, values, _ = propose_type(raw, command.parameters.get(raw.upper(), ""))
            refused = sample_contradiction(command, index=index, proposed=proposed, values=values)
            if refused is not None:
                contradicted.append(f"{raw} (the sample passes {refused})")
                proposed, values = None, ()
            lines.append(f"    - name: {_argument_name(raw)}")
            lines.append(f"      type: {proposed or '???'}")
            if values:
                lines.append(f"      values: [{', '.join(values)}]")
            if proposed is None:
                unanswered += 1
            else:
                typed += 1
    else:
        lines.append("  args: []")
    lines.append(f'  manual_ref: "{source} p.{command.page}"')
    lines.append("  versions:")
    for canonical, status in versions.items():
        lines.append(f'    "{canonical}": {{status: {status}}}')
    if not command.parameters:
        typing_note = (
            "The command documents no parameter table, so no argument type could be "
            "read and every one is unanswered"
        )
    else:
        typing_note = (
            f"{typed} argument type(s) read from the parameter table and "
            f"{unanswered} left unanswered"
        )
    if contradicted:
        typing_note += (
            f". The type read from the table would REFUSE the token the sample "
            f"passes, for {', '.join(contradicted)}, so it was discarded and left "
            f"unanswered rather than written. Which of the two is wrong is the "
            f"reviewer's question and not this tool's: a table that enumerates "
            f"labels beside a sample passing an index is usually an incomplete "
            f"reading of a table that offered both, while a token in neither form "
            f"is usually an argument list out of step with the signature"
        )
    lines.append(
        f"  drafted: >-\n"
        f"    Drafted by pyflightstream.utils.manual from {source} p.{command.page}"
        f"{f' ({command.section})' if command.section else ''}. Layout proposed because "
        f"{why}. {typing_note}; a type this tool proposes is a reading of the manual's "
        f"own parameter table and not evidence, and an argument written on a "
        f"continuation line does not appear at all. Review against the manual page, "
        f"then delete this line."
    )
    return "\n".join(lines) + "\n"


def render_chapter(
    commands: Iterable[ManualCommand],
    *,
    source: str,
    versions: Mapping[str, str],
) -> str:
    """Render several entries as one chapter file body, sorted by name."""
    ordered = sorted(commands, key=lambda c: c.name)
    header = (
        f"# Drafted from {source} by pyflightstream.utils.manual.\n"
        f"# {len(ordered)} entries, none reviewed. Every '???' is a question the\n"
        f"# manual does not answer; the schema refuses them, so this file cannot\n"
        f"# load until a person has been through it.\n\n"
    )
    return header + "\n".join(render_entry(c, source=source, versions=versions) for c in ordered)


def write_chapter(body: str, *, path: str | Path, write: bool = False) -> str:
    """Write a drafted chapter, but only when asked.

    The default is a dry run, and the reason is the measurement in this
    module's own docstring: the drafts reproduce 77 percent of
    hand-authored argument lists, so writing them unreviewed into the
    database the emitter validates against would put invented grammar in
    front of other people's scripts.

    Parameters
    ----------
    body : str
        Output of :func:`render_chapter`.
    path : str or Path, keyword-only
        Destination. Point it at a scratch file to review before moving
        anything into ``src/pyflightstream/commands/``. Keyword-only,
        and it used to be the leading positional beside ``body``: two
        adjacent arguments of the same kind, where swapping them and
        taking the default ``write=False`` returned a well-formed dry
        run reporting zero entries drafted, with the whole chapter body
        printed back as the path it would have written to.
    write : bool, keyword-only
        False, the default, writes nothing. True writes ``body`` to
        ``path``, replacing it.

    Returns
    -------
    str
        A sentence saying what happened, for a caller to print.
    """
    from pathlib import Path as _Path

    target = _Path(path)
    entries = body.count("\n  layout: ")
    unanswered = body.count("???")
    if not write:
        return (
            f"dry run: {entries} entr(ies) drafted, {unanswered} unanswered field(s), "
            f"nothing written. Pass write=True to write {target}."
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8")
    return (
        f"wrote {entries} drafted entr(ies) to {target}, with {unanswered} unanswered "
        "field(s) still to review. They are drafts: the '???' values do not load."
    )
