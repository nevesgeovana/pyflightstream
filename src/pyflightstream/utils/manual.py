"""Read FlightStream manuals and compare their command coverage.

Maintainer tooling at the bottom layer: dependencies are its errors module
and the optional PDF extra, loaded lazily. It extracts command names,
pages, signatures and differences against the database.

Grammar proposals are drafts requiring human review (CONTRIBUTING.md
invariant 3). A variable-length list, keyword block or alternative sample
form cannot be reduced reliably to one inline signature. Database argument
names can also differ from the manual's placeholders. Each proposal states
why it was made; an unknown type is None and renders as ???, which the
schema refuses.

Parameter tables supply type proposals. Counting and indexing rules run
before enum rules, and enum rules read only the sentence introducing the
set. sample_contradiction checks each proposal against the printed sample;
render_entry discards a contradicted type. Agreement between two readings
of the same parameter table is not independent validation.

This module can draft entries and insert a version row into an existing
entry. The registration transaction belongs to utils.database. It carries
a documented row forward only when two editions parse identically, citing
both pages; differences require a person's reading.

Pages form one stream so command samples can cross page boundaries. Tests
use synthetic fixtures reproducing layout without licensed manual text.
They check rules and ordering, not population-wide accuracy; the licensed
manuals remain under _private/ and never enter Git (invariant 1).
"""

from __future__ import annotations

import enum
import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

import yaml

import pyflightstream._textio as _textio
from pyflightstream._yamlflow import flow_mapping, flow_scalar
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
    "EditionDelta",
    "EditionVerdict",
    "coverage_against",
    "documentation_delta",
    "edition_surfaces",
    "parse_script_index",
    "parse_signatures",
    "propose_layout",
    "propose_type",
    "insert_version_row",
    "manual_editions",
    "read_edition",
    "read_edition_manifest",
    "read_pdf_pages",
    "render_chapter",
    "render_entry",
    "sample_contradiction",
    "stale_citations",
    "surface_changes",
    "unreachable_commands",
    "write_chapter",
]

#: A Script Index line pairs a command with the section that documents
#: it. Four characters minimum, so a two-letter enum value on its own
#: line cannot pass for a command name.
_INDEX_LINE = re.compile(r"^([A-Z][A-Z0-9_]{3,})\s+(\S.*?)\s*$")

#: Command headings introduce inline argument placeholders in order.
#: Do not anchor the pattern to the line start: layout extraction can
#: preserve a margin glyph before the heading.
_SIGNATURE = re.compile(r"(?:^|\s)Function name:\s*([A-Z][A-Z0-9_]{2,})\s*(.*)$")
_PLACEHOLDER = re.compile(r"<([^>]+)>")

#: A wrapped signature continues onto a line containing only placeholders. The parser joins
#: that line to the signature; a sentence, parameter heading or sample cannot become an
#: argument.
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
    description : str
        The complete command block, ending at the next signature, with whitespace
        normalized and page-number footers removed. Compared at runtime only;
        renderers never reproduce this licensed text.
    """

    name: str
    page: int
    inline_args: tuple[str, ...] = ()
    sample: tuple[str, ...] = ()
    section: str | None = None
    parameters: Mapping[str, str] = field(default_factory=dict)
    #: Whitespace-normalized complete block, compared at runtime and never rendered.
    description: str = ""

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
    is preferred over scanning the chapter.

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

    Notes
    -----
    The pages are read as one stream, preserving samples and parameter tables across page
    boundaries.

    It was found by comparing two editions of one manual, where the
    consequence is sharp. The vendor repaginated one chapter by a page,
    which split ``DISABLE_WAKE_NODES_ON_TRAILING_EDGE`` across a break in
    the newer edition alone; the comparison then read a full record
    against a truncated one and reported a documentation change the
    vendor had not made. Worse in the other direction: with 22 commands
    of that edition truncated, three deliberately planted grammar edits
    below a break all compared EQUAL, so a real vendor change would have
    been carried forward as "same grammar".

    The page a command is CITED at is still the page carrying its
    signature line, which is what a reader turns to.

    A line that is nothing but its own page number is dropped while the
    stream is built. It is the extraction's footer, and joined into the
    stream it lands in the middle of a block and reads as content: 20
    commands had one as the first line of their sample.
    """
    sections = sections or {}
    lines: list[str] = []
    page_of: list[int] = []
    for page in sorted(pages):
        for raw in pages[page].splitlines():
            line = raw.rstrip()
            if line.strip() == str(page):
                continue
            lines.append(line)
            page_of.append(page)

    found: dict[str, ManualCommand] = {}
    headings = [
        (i, match) for i, line in enumerate(lines) if (match := _SIGNATURE.search(line.strip()))
    ]
    for position, (i, match) in enumerate(headings):
        # search, not match: the pattern already requires the heading
        # to start a line or follow whitespace, and anchoring at
        # position zero as well would defeat the margin tolerance the
        # pattern was widened for.
        name = match.group(1)
        if name in found:
            continue
        signature = match.group(2)
        if i + 1 < len(lines) and _WRAPPED_SIGNATURE.match(lines[i + 1]):
            signature += " " + lines[i + 1].strip()
        placeholders = tuple(a.strip() for a in _PLACEHOLDER.findall(signature))
        end = headings[position + 1][0] if position + 1 < len(headings) else len(lines)
        block = lines[i:end]
        found[name] = ManualCommand(
            name=name,
            page=page_of[i],
            inline_args=placeholders,
            sample=_sample_after(block, 0, name),
            section=sections.get(name),
            parameters=_parameters_after(block, 0, placeholders),
            description=" ".join(" ".join(block).split()),
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
    # The scan stops at the NEXT signature, so a command with no table of
    # its own cannot borrow the following command's. Measured before the
    # stop existed: five commands compared a neighbour's parameter table.
    opening = None
    for j in range(start + 1, len(lines)):
        if lines[j].strip().startswith("Function parameters"):
            opening = j
            break
    if opening is None:
        return {}
    block: list[str] = []
    for k in range(opening + 1, len(lines)):
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
    # LONGEST FIRST, so a FRAME_TYPE row opens FRAME_TYPE and is not read
    # as a continuation of FRAME, the placeholder its name starts with.
    longest_first = sorted(keys, key=len, reverse=True)
    for line in block:
        opened = next((key for key in longest_first if line.startswith(key)), None)
        if opened is not None and opened not in rows:
            current = opened
            rows[current] = [line[len(opened) :].strip()]
        elif current is not None:
            rows[current].append(line)
    return {key: " ".join(parts).strip() for key, parts in rows.items()}


def _sample_after(lines: list[str], start: int, name: str) -> tuple[str, ...]:
    """Lines of the sample block that follows a signature, comments dropped.

    The search for the ``Sample`` heading stops at the next signature. A command with no sample
    therefore cannot borrow the next command's example.
    """
    for j in range(start + 1, len(lines)):
        if lines[j].strip().startswith("Function name:"):
            return ()
        if not lines[j].strip().startswith("Sample"):
            continue
        block: list[str] = []
        for k in range(j + 1, len(lines)):
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

    Parameters
    ----------
    command : ManualCommand
        The command as the manual reader parsed it.

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
    page ranges are per edition because scripting-reference pagination
    differs between manuals.

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
        Citation id of this edition, for example ``"FSM-26.100"``, as a
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


def manual_editions(
    editions: Iterable[Edition],
    *,
    recorded: Iterable[str],
    reader: Callable[..., Mapping[int, str]] | None = None,
) -> tuple[SweptCommand, ...]:
    """Read every manual edition and report what none of them has an entry for.

    ``manual_editions`` is the public Python API; ``pyfs-manual sweep``
    is the CLI subcommand that calls it.

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
            read(edition.manual, first=edition.chapter[0], last=edition.chapter[1]), sections=labels
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
    editions: Iterable[Edition], *, reader: Callable[..., Mapping[int, str]] | None = None
) -> dict[str, tuple[str, ...]]:
    """Read each edition and return the command names it documents.

    The whole surface, not the part the database lacks, which is what
    :func:`manual_editions` reports. Both read the chapter body the same
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
        :func:`read_pdf_pages`. Same seam as :func:`manual_editions`,
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
        neighbours: "26.100" sorts before "26.101" by luck, and "26.12" sorts
        after both as a string.

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
    :func:`manual_editions` compares the manuals against the set of entry
    NAMES, so an entry that exists but carries no row for one edition is
    invisible to it: the sweep reports zero absent while that build's
    emitter refuses a command the caller's own manual documents.

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
        below ``commands`` in the dependency order (CONTRIBUTING.md Layout)
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
            # An unresolved label can be unregistered or an ambiguous vendor alias.
            # Handle both so the coverage report identifies the missing build.
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
    can emit. The protocol therefore requires both attributes.
    """

    @property
    def commands(self) -> Mapping[str, CommandEntryLike]:
        """Every entry, keyed by command name."""

    def for_version(self, version: Any) -> Any:
        """Return the per-version view of the database."""


#: The four outcomes a version row can have in a citation re-check, in
#: the order the loop decides them. They PARTITION the rows the run saw
#: for an edition: every row reaching the tally ends in exactly one, so
#: the four sum to the rows seen and no row is counted twice.
#:
#: A row the manifest does not cover is deliberately absent from this
#: list. Such a row drops out before the tally, because the run has no
#: reading of that edition to check it against, and folding it in here
#: would put a number about EDITIONS NOT READ inside a per-edition
#: total. The CLI names those builds on their own line instead.
CITATION_REACH_OUTCOMES: tuple[str, ...] = ("no_note", "no_page", "removed", "checked")

#: The summary accounts for every failure reason reported by the manual check.
citation_reach: dict[str, dict[str, int]] = {}


def stale_citations(
    editions: Iterable[Edition],
    *,
    recorded: RegistryLike,
    reader: Callable[..., Mapping[int, str]] | None = None,
) -> tuple[StaleCitation, ...]:
    """Check every version row's page citation against the manual it names.

    Check that cited pages still match the manual's command locations.
    A regenerated conversion can shift pagination while leaving a cited
    page number valid but pointing to the wrong command.

    Parameters
    ----------
    editions : iterable of Edition
        The manuals to check against. The manual side comes first and
        the database is keyword-only, matching
        :func:`manual_editions` and :func:`coverage_against`; two
        adjacent positional parameters of unrelated kinds is a call
        nobody can read.
    recorded : RegistryLike
        The loaded database, used through ``.commands``. Typed loosely
        because this module sits below ``commands`` in the dependency
        order (CONTRIBUTING.md Layout) and must not import it, which is also
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
    not carry one. Neither can a row whose edition the manifest does not
    list, and that one differs in kind from the other three: the run has
    no reading to check it against, so it is not an outcome of this
    check at all.

    Each run records how the rows it saw ended, in
    :data:`citation_reach`, one count per outcome of
    :data:`CITATION_REACH_OUTCOMES` per edition. Those four partition
    the rows seen for that edition, so a caller can say WHY a row went
    unchecked rather than inferring one reason for all of them
    (OPS-2003.10.02). Rows of an unlisted edition appear in none of the
    four, for the reason in the paragraph above.

    A note citing a page RANGE is satisfied by any page in it. Twenty-six
    shipped rows cite one, and reading only the first page of a span
    reports a correct citation as wrong whenever the signature heading
    sits on the second.

    The SOURCE is checked too, where the manifest records one: a note
    citing FSM-26.120 on a row keyed to the edition FSM-26.121 was reading a
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
        reach[edition.label] = dict.fromkeys((*CITATION_REACH_OUTCOMES, "range_cited"), 0)
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
                # No reading of this edition, so this row has no outcome
                # here at all and is not counted: the manifest decides
                # which editions were read, and the CLI names the builds
                # it left out on a line of its own.
                continue
            # From here every path below ends in exactly one of the four
            # outcomes, which is what makes them a partition of the rows
            # seen rather than four numbers that happen to be printed
            # together (OPS-2003.10.02).
            counted = reach[label]
            note = getattr(row, "note", None)
            if not note:
                counted["no_note"] += 1
                continue
            match = _CITED_PAGE.search(note)
            if match is None:
                counted["no_page"] += 1
                continue
            if getattr(getattr(row, "status", None), "value", None) == "removed":
                counted["removed"] += 1
                continue
            counted["checked"] += 1
            source, first, last = match.group(1), int(match.group(2)), match.group(3)
            if last:
                # A SUBSET of checked and never an addend: this row has
                # already been counted once, above.
                counted["range_cited"] += 1
            span = range(first, (int(last) if last else first) + 1)
            command = parsed.get(name)
            expected = sources.get(label)
            if expected and source != expected:
                stale.append(
                    StaleCitation(
                        command=name, edition=label, cited=first, found=None, reason="wrong source"
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
#: for example "FSM-25.000 p.286" or "FSM-26.100 pp.312-313". The source is
#: captured because a page number alone checks half a citation: a note
#: naming another edition's source would otherwise be read against this
#: edition's pdf, and between FSM-26.120 and FSM-26.121 the pages differ by a
#: uniform three, so a coincidence is cheap. The optional second page is
#: captured because a span is satisfied by any page in it, and 26
#: shipped rows cite one.
_CITED_PAGE = re.compile(r"\b(FSM-(?:\d{2}\.\d{3}|TEST))\s+pp?\.\s*(\d+)(?:\s*-\s*(\d+))?")

#: What an edition row may hold, and what each key is for. Kept as data
#: so the refusals can print it rather than restate it in prose.
_MANIFEST_KEYS = {
    "label": "canonical version identifier, for example 26.121",
    "manual": "path of the manual pdf",
    "chapter": "FIRST-LAST pages of the scripting reference",
    "index": "FIRST-LAST pages of the Script Index, optional",
    "source": "citation id, for example FSM-26.121, optional",
}
_MANIFEST_REQUIRED = ("label", "manual", "chapter")


def _manifest_range(row: dict, key: str, where: str) -> tuple[int, int]:
    """Return the FIRST-LAST page range ``row[key]`` states; refuse a malformed one."""
    spec = str(row[key])
    first, _, last = spec.partition("-")
    if not last or not first.isdigit() or not last.isdigit():
        raise ManualDraftError(f"{where}: {key} must read FIRST-LAST in page numbers, got {spec!r}")
    if int(first) > int(last):
        raise ManualDraftError(f"{where}: {key} ends before it starts, {spec!r}")
    return int(first), int(last)


def _edition_from_row(row: dict, where: str, known: str) -> Edition:
    """Check one manifest row and return its :class:`Edition`; refuse the first fault."""
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
        raise ManualDraftError(f"{where}: unknown key(s) {unknown}. An edition row holds {known}")
    # TEXT, OR REFUSED, the hazard the command loader refuses for its
    # version keys. YAML reads an unquoted 26.120 as the number 26.12
    # and a blank `source:` as null, and str() of either is a
    # different build or the four letters "None" as a citation.
    label = row["label"]
    if not isinstance(label, str) or not label.strip():
        raise ManualDraftError(
            f"{where}: label {label!r} parsed as {type(label).__name__}, not as the "
            'name of a build; quote it in the YAML (label: "26.120"), because an '
            "unquoted 26.120 is read as the number 26.12"
        )
    source = row.get("source")
    if "source" in row and (not isinstance(source, str) or not source.strip()):
        raise ManualDraftError(
            f"{where}: source {source!r} parsed as {type(source).__name__}, not as a "
            'citation id; write it (source: "FSM-26.123") or leave the key out'
        )
    # Ranges before existence: both are checked before any manual is
    # opened, which is the point, and within a row a malformed page
    # range is the more specific complaint of the two.
    chapter = _manifest_range(row, "chapter", where)
    index = _manifest_range(row, "index", where) if "index" in row else None
    manual = Path(str(row["manual"]))
    if not manual.is_file():
        raise ManualDraftError(
            f"{where}: manual {str(manual)!r} is not a readable file. Manual paths are "
            "relative to the working directory and name licensed material this "
            "repository never carries, so a fresh clone has to point them at its own copy"
        )
    return Edition(label=label, manual=manual, chapter=chapter, index=index, source=source)


def read_edition_manifest(path: str | Path) -> tuple[Edition, ...]:
    """Read an edition manifest, the file that makes a sweep repeatable.

    The manifest is a list of mappings with the keys of :class:`Edition`,
    ``chapter`` and ``index`` written as ``FIRST-LAST``. It is a file
    rather than repeated command-line flags because it is the thing a
    new build EDITS: registering one is adding a row, and the row is
    then under the maintainer's own version control rather than retyped
    from a session note.

    It is never committed here. It names paths of licensed manuals, and
    those live in ``_private/`` (CONTRIBUTING.md invariant 1).

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
        ``manual`` or ``chapter``, carries a key outside the five, has a
        ``label`` or ``source`` that YAML did not read as non-blank text
        (an unquoted ``26.120`` is the number 26.12, a blank ``source:``
        is null), names a manual that does not exist, or writes a page
        range that is not
        ``FIRST-LAST`` with FIRST no greater than LAST. Every check names
        the offending row, because a manifest is edited rarely and by
        hand. Check every row before opening any manual.

    Examples
    --------
    A manifest with one edition, as it would be written by hand::

        - label: "26.121"
          source: FSM-26.121
          manual: _private/manual/user-manual-26121.pdf
          chapter: 284-379
          index: 380-386
    """
    try:
        text = Path(path).read_text(encoding="utf-8")
        rows = yaml.safe_load(text)
    except (yaml.YAMLError, UnicodeDecodeError) as error:
        raise ManualDraftError(
            f"{path} is not a readable edition manifest ({error}); it is a UTF-8 YAML "
            "list of edition mappings"
        ) from error
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise ManualDraftError(
            f"{path} must hold a list of edition mappings, not {type(rows).__name__}"
        )

    known = ", ".join(f"{key} ({why})" for key, why in _MANIFEST_KEYS.items())
    editions = []
    for position, row in enumerate(rows, start=1):
        where = f"{path} entry {position}"
        editions.append(_edition_from_row(row, where, known))
    return tuple(editions)


def read_pdf_pages(path: str | Path, *, first: int, last: int) -> dict[int, str]:
    """Extract the text of a page range from a manual pdf.

    Separated from every function above so the parsing is testable
    without a pdf and without the optional dependency: everything else in
    this module takes text.

    Require a valid, keyword-only range of one-based page numbers.
    Reversed bounds must not produce an empty mapping that coverage
    would interpret as a manual documenting no commands; zero must not
    index the last PDF page or produce a p.0 citation.

    Parameters
    ----------
    path : str or Path
        The manual. It is licensed vendor material, lives in
        ``_private/`` and never enters Git (CONTRIBUTING.md invariant 1); only
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
    except ImportError as error:  # pragma: no cover - exercised only without the extra
        from pyflightstream.extras import missing_extra

        raise missing_extra(
            "manual", package="pypdf", purpose="reading a FlightStream manual pdf"
        ) from error

    try:
        reader = pypdf.PdfReader(path)
        page_count = len(reader.pages)
    except pypdf.errors.PyPdfError as error:
        raise ManualDraftError(
            f"{path} could not be read as a pdf ({error}). Name the manual's own pdf file "
            "(a truncated download or another kind of file is not one)."
        ) from error
    if last > page_count:
        raise ManualDraftError(
            f"page range {first}-{last} reaches past the end of {path}, which has "
            f"{page_count} pages. Truncating would answer from a short read, and "
            "the page count is also the cheapest sign that this is the wrong edition: "
            "compare it with the page count of the edition you meant to read."
        )
    # Use layout extraction to preserve visual lines. Flowing extraction can
    # join a sample block and the next signature heading, hiding both from
    # line-oriented parsing.
    try:
        return {
            i + 1: (reader.pages[i].extract_text(extraction_mode="layout") or "")
            for i in range(first - 1, last)
        }
    except TypeError as error:
        raise ManualDraftError(
            f"the installed pypdf does not accept extraction_mode='layout' ({error}); "
            "upgrade pypdf (pip install -U pypdf) and read the manual again"
        ) from error


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
#: ordering checks refuse a correct script. Every value is a Phase member,
#: read off the phase the chapter file of that section already gives all of
#: its entries; a section whose recorded entries span more than one phase
#: (Opening Closing Saving, Solver Initialization Execution, Unsteady
#: Solver, Sweeper Toolbox, Solver Analysis) or whose chapter is not one
#: file (Output Status) is left out, so it drafts as `???`.
_PHASE_BY_SECTION = {
    "Script Controls": "control",
    "Mesh Import   Export": "geometry",
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
    "Fluid Properties": "setup",
    "Free Stream Velocity": "init",
    "Solver Data Export": "export",
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

    Rules form an ordered list. Their precedence is part of the inference contract and is visible
    to both readers and tests.

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
    and "Number of boundaries" carry the same meaning.
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
#: it does. ``tests/tier1_offline/test_utils_manual.py`` pins both the sequence and one
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


def propose_type(*, placeholder: str, description: str) -> tuple[str | None, tuple[str, ...], str]:
    """Suggest an argument type from the manual's parameter table.

    Both strings are keyword-only (PFS-2022.05). A positional Python
    call raises TypeError; naming placeholder and description prevents
    accidentally exchanging two otherwise valid strings.

    The parameter table supplies type information absent from signatures
    and samples. An unknown type remains unresolved so the caller can
    write ``???`` rather than invent a type.

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

    Raises
    ------
    TypeError
        A positional call, which Python itself refuses on this signature.
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
    command: ManualCommand, *, index: int, proposed: str | None, values: tuple[str, ...] = ()
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

    A parameter table can disagree with its sample. ``CAD_BODY_ROTATE`` has a
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
    command: ManualCommand, *, source: str, versions: Mapping[str, str], phase: str | None = None
) -> str:
    """Render one command as a database entry, for a person to review.

    Parameters
    ----------
    command : ManualCommand
        Parsed entry, from :func:`parse_signatures`.
    source : str
        Manual source id for the citation, for example ``"FSM-26.100"``.
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
            "committed probe report by pyfs-qa apply-compat (CONTRIBUTING.md invariant 3). "
            "A removed read off an edition instead is a hand-written row carrying a "
            "note and a page, not a drafted one."
        )

    layout, why = propose_layout(command)
    resolved = phase or _PHASE_BY_SECTION.get(command.section or "", "???")
    lines = [f"{command.name}:", f"  layout: {layout}", f"  phase: {resolved}"]
    typed, unanswered = 0, 0
    contradicted: list[str] = []
    if command.inline_args:
        lines.append("  args:")
        for index, raw in enumerate(command.inline_args):
            proposed, values, _ = propose_type(
                placeholder=raw, description=command.parameters.get(raw.upper(), "")
            )
            refused = sample_contradiction(command, index=index, proposed=proposed, values=values)
            if refused is not None:
                contradicted.append(f"{raw} (the sample passes {refused})")
                proposed, values = None, ()
            lines.append(f"    - name: {_argument_name(raw)}")
            lines.append(f"      type: {proposed or '???'}")
            if values:
                # QUOTED, every token: YAML 1.1 reads a bare ON, OFF, YES or
                # NO as a boolean, and ArgSpec.values holds strings.
                lines.append(f"      values: {flow_scalar(list(values))}")
            if proposed is None:
                unanswered += 1
            else:
                typed += 1
    else:
        lines.append("  args: []")
    lines.append(f'  manual_ref: "{source} p.{command.page}"')
    lines.append("  versions:")
    for canonical, status in versions.items():
        lines.append(f'    "{canonical}": {flow_mapping({"status": status})}')
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
    commands: Iterable[ManualCommand], *, source: str, versions: Mapping[str, str]
) -> str:
    """Render several entries as one chapter file body, sorted by name.

    Parameters
    ----------
    commands : iterable of ManualCommand
        The entries to render.
    source : str
        Manual source id for the citation, for example ``FSM-26.100``.
    versions : mapping of str to str
        Canonical version to status, as :func:`render_entry` takes it.

    Returns
    -------
    str
        The chapter header, then one entry per command, sorted by name.
    """
    ordered = sorted(commands, key=lambda c: c.name)
    header = (
        f"# Drafted from {source} by pyflightstream.utils.manual.\n"
        f"# {len(ordered)} entries, none reviewed. Every '???' is a question the\n"
        f"# manual does not answer; the schema refuses them, so this file cannot\n"
        f"# load until a person has been through it.\n\n"
    )
    return header + "\n".join(render_entry(c, source=source, versions=versions) for c in ordered)


def write_chapter(
    body: str, *, path: str | Path, write: bool = False, overwrite: bool = False
) -> str:
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
        anything into ``src/pyflightstream/commands/``. Keyword-only to
        prevent exchanging the destination with the chapter body.
    write : bool, keyword-only
        False, the default, writes nothing. True writes ``body`` to
        ``path``.
    overwrite : bool, keyword-only
        False, the default, refuses a ``path`` that already exists, so a
        reviewed draft or a shipped chapter is never replaced by accident.
        True replaces it.

    Returns
    -------
    str
        A sentence saying what happened, for a caller to print.

    Raises
    ------
    ManualDraftError
        If ``write`` is True, ``path`` exists and ``overwrite`` is False.
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
    if target.exists() and not overwrite:
        raise ManualDraftError(
            f"{target} already exists, and a draft would replace it, which could be a "
            "reviewed draft or a shipped chapter. Nothing was written. Pass "
            "overwrite=True (--overwrite on the command line) to replace it, or choose "
            "another destination"
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    _textio.write_text(target, body)
    return (
        f"wrote {entries} drafted entr(ies) to {target}, with {unanswered} unanswered "
        "field(s) still to review. They are drafts: the '???' values do not load."
    )


class EditionVerdict(enum.StrEnum):
    """Closed vocabulary for one command's relationship to a predecessor edition.

    Five values distinguish unchanged, changed, arrived, dropped and absent
    commands. Callers can decide which rows to write without rechecking the
    predecessor mapping or reconstructing missing distinctions.
    """

    #: Both editions parse to the same record, so the new edition's page
    #: may be cited for a row written from the reading.
    UNCHANGED = "unchanged"
    #: Both document it and the new one documents it DIFFERENTLY, so a
    #: person owes it a reading before anything is written.
    CHANGED = "changed"
    #: The new edition documents it and the predecessor did not.
    ARRIVED = "arrived"
    #: The predecessor documented it and the new edition does not. This
    #: is the vendor silently removing or renaming something, and it is
    #: the state that breaks a user's script.
    DROPPED = "dropped"
    #: Neither edition documents it. A fact about the two documents and
    #: never about the solver, and it says nothing about this build.
    ABSENT = "absent"


@dataclass(frozen=True, kw_only=True)
class EditionDelta:
    """What a new edition says about one command, against its predecessor.

    Produced by :func:`documentation_delta`, one per command the database
    records, so a caller can tell the five states apart without
    re-deriving them.

    KEYWORD-ONLY, and that is about ``page`` and ``previous_page``
    specifically, exactly as it is for :class:`Edition`'s two page
    ranges. They are two fields of the same type sitting adjacent, so
    positionally they are interchangeable and swapping them constructs
    cleanly: :attr:`repaginated` still answers true, and the caller
    writes the PREDECESSOR's page into a row citing the new edition's
    source. That is a wrong citation in the shipped database with every
    guard green, and nothing but the keyword separates the two.

    Attributes
    ----------
    name : str
        Command name.
    verdict : EditionVerdict
        Which of the five states this command is in.
    page : int or None
        Page of the NEW edition, where it documents the command. None
        where this edition does not document it at all.
    previous_page : int or None
        Page of the predecessor, where it did. None where the
        predecessor did not document it.
    differs_in : tuple of str
        For ``changed`` only, which of ``args``, ``sample``,
        ``parameters`` and ``description`` moved. Empty for every other verdict, an
        arrival included: an arrival differs in nothing, it is new. It
        names the FIELDS and never their content: the parameter prose
        is licensed manual text and is read at run time, never carried
        into anything written (invariant 1).
    """

    name: str
    verdict: EditionVerdict
    page: int | None = None
    previous_page: int | None = None
    differs_in: tuple[str, ...] = ()

    @property
    def repaginated(self) -> bool:
        """True where the command moved page without changing."""
        return (
            self.verdict is EditionVerdict.UNCHANGED
            and self.previous_page is not None
            and self.page != self.previous_page
        )


def read_edition(
    edition: Edition, *, reader: Callable[..., Mapping[int, str]] | None = None
) -> dict[str, ManualCommand]:
    """Parse one edition's scripting reference, sections included.

    Parameters
    ----------
    edition : Edition
        A row of the edition manifest.
    reader : callable, optional
        Page reader, defaulting to :func:`read_pdf_pages`. It is a
        parameter for the same reason it is one on
        :func:`manual_editions` and :func:`edition_surfaces`: this
        module keeps its parsing testable without a pdf and without the
        ``[manual]`` extra. It was omitted when this function was
        written, which left the one code path in this repository that
        writes hundreds of database rows with no end-to-end test.

    Returns
    -------
    dict of str to ManualCommand
        What that edition states about each command it documents.
    """
    read = reader or read_pdf_pages
    pages = read(edition.manual, first=edition.chapter[0], last=edition.chapter[1])
    sections: Mapping[str, str] = {}
    if edition.index is not None:
        index_pages = read(edition.manual, first=edition.index[0], last=edition.index[1])
        sections = parse_script_index(index_pages)
    return parse_signatures(pages, sections=sections)


def documentation_delta(
    previous: Mapping[str, ManualCommand],
    current: Mapping[str, ManualCommand],
    *,
    recorded: Iterable[str],
) -> tuple[EditionDelta, ...]:
    """Classify every recorded command against two parsed editions.

    THE COMPARISON IS OF WHAT THE EDITION SAYS, not of where it says it,
    and that is the whole reason this function exists. A rule keyed on
    the page number cannot see a command that moved: a local reflow
    repaginates a run of commands by one, and under a page rule every
    one of them falls out of a bulk pass although most are word for word
    what they were. Comparing the parsed records handles it and is
    sensitive to changes anywhere in the command block. Whitespace and page-number
    footers are normalized; an unchanged page number is not evidence of unchanged text.

    Parameters
    ----------
    previous, current : mapping of str to ManualCommand
        Output of :func:`read_edition` for the predecessor and the new
        edition, in that order.
    recorded : iterable of str
        Command names the database holds. Commands the new edition
        documents that are not among these are not classified here; a
        caller reports them separately, because entering a new command
        is a different piece of work from carrying an existing one
        forward.

    Returns
    -------
    tuple of EditionDelta
        One per recorded command, sorted by name.
    """
    deltas = []
    for name in sorted(recorded):
        new = current.get(name)
        old = previous.get(name)
        if new is None:
            # Distinguish a command documented by the predecessor but dropped by
            # this edition from one documented by neither. The first identifies a
            # compatibility gap; the second carries no such evidence.
            deltas.append(
                EditionDelta(
                    name=name,
                    verdict=(EditionVerdict.ABSENT if old is None else EditionVerdict.DROPPED),
                    previous_page=None if old is None else old.page,
                )
            )
            continue
        if old is None:
            deltas.append(EditionDelta(name=name, verdict=EditionVerdict.ARRIVED, page=new.page))
            continue
        differs = tuple(
            field_name
            for field_name, same in (
                ("args", old.inline_args == new.inline_args),
                ("sample", old.sample == new.sample),
                ("parameters", dict(old.parameters) == dict(new.parameters)),
                ("description", old.description == new.description),
            )
            if not same
        )
        deltas.append(
            EditionDelta(
                name=name,
                verdict=EditionVerdict.UNCHANGED if not differs else EditionVerdict.CHANGED,
                page=new.page,
                previous_page=old.page,
                differs_in=differs,
            )
        )
    return tuple(deltas)


def insert_version_row(text: str, *, command: str, canonical: str, status: str, note: str) -> str:
    """Insert one single-line version row into a chapter file's text.

    The function renders its row through :func:`pyflightstream._yamlflow.flow_mapping`. It accepts
    no pre-rendered YAML, so escaping and validation remain within the library.

    KEYWORD-ONLY after the text, for the reason the neighbouring
    :class:`Edition` is: ``command``, ``canonical``, ``status`` and
    ``note`` are four strings, so positionally they are interchangeable
    and a swap of the middle two constructs cleanly.

    AT THE END OF THE BLOCK rather than in release order, and that is
    deliberate: the existing rows are NOT in release order in every
    entry, so inserting by order would reorder files this has no
    business reordering.

    Preserve all bytes outside the inserted row, including each line's
    existing terminator. In particular, do not normalize CRLF chapters
    to LF while inserting a version row.

    Parameters
    ----------
    text : str
        The chapter file, whole.
    command : str
        Entry to edit. Its ``versions:`` block is found under it.
    canonical : str
        Build the row is for. Refused if the entry already has one.
    status : str
        Evidence status for that build, written as a bare token. This
        function does NOT judge it: which statuses exist and which may
        be written from a reading is the command database's rule and
        the caller's to obey (CONTRIBUTING.md invariant 3).
    note : str
        Provenance of the row, quoted and escaped on the way in. A
        citation, for example ``"FSM-26.123 p.290, unchanged from FSM-26.122
        p.289"``.

    Returns
    -------
    str
        The edited text.

    Raises
    ------
    ManualDraftError
        If the entry is not in this file, has no ``versions:`` block, or
        already records that build in either shape. Refusing rather than
        rewriting: a block-form row carries a note and possibly an
        argument override, and writing a second key beside it makes YAML
        keep the last and drop the first, silently.
    """
    newline = "\r\n" if "\r\n" in text else "\n"
    # Split on CRLF and LF ONLY, each line keeping its own terminator.
    # str.splitlines also breaks on form feed, NEL, U+2028 and other
    # characters a note may hold, and rejoining with one newline rewrote
    # a file of mixed line ends.
    chunks = re.findall(r".*?(?:\r\n|\n)|.+\Z", text, flags=re.S)
    lines = [chunk.removesuffix("\n").removesuffix("\r") for chunk in chunks]
    ends = [chunk[len(line) :] for chunk, line in zip(chunks, lines, strict=True)]
    try:
        start = next(i for i, line in enumerate(lines) if line == f"{command}:")
    except StopIteration:
        raise ManualDraftError(f"{command} is not an entry of this file") from None

    # The entry runs to the next TOP-LEVEL KEY. A comment at column zero
    # does not end it: comments sit at every indentation in this database,
    # including inside a versions block, and treating one as the end of
    # the entry hid every row below it from the duplicate scan.
    end = next(
        (
            i
            for i in range(start + 1, len(lines))
            if lines[i] and not lines[i].startswith((" ", "#"))
        ),
        len(lines),
    )
    try:
        versions_at = next(i for i in range(start + 1, end) if lines[i].rstrip() == "  versions:")
    except StopIteration:
        raise ManualDraftError(f"{command} has no versions block") from None

    # Insert after the last nonblank, noncomment line of the versions block.
    # Comments do not end the block regardless of indentation; scan past
    # them to detect every existing build key and prevent duplicates.
    last_content = versions_at
    block_rows = []
    for i in range(versions_at + 1, end):
        stripped = lines[i].strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            continue
        if not lines[i].startswith("    "):
            break
        last_content = i
        block_rows.append(i)

    for i in block_rows:
        key = lines[i].strip().split(":", 1)[0].strip().strip('"').strip("'")
        if key == canonical:
            raise ManualDraftError(f"{command} already records {canonical}")

    row = flow_mapping({"status": status, "note": note})
    if not re.fullmatch(r"[0-9A-Za-z._-]+", canonical):
        raise ManualDraftError(
            f"{command}: the build key {canonical!r} is written between quotes in a "
            "chapter file, so it holds letters, digits, dots, dashes and underscores only"
        )
    # The new row takes the terminator of the line it follows; a last line
    # with none gains the file's own before it.
    original_end = ends[last_content]
    after = original_end or newline
    ends[last_content] = after
    lines.insert(last_content + 1, f'    "{canonical}": {row}')
    ends.insert(last_content + 1, original_end)
    return "".join(line + end for line, end in zip(lines, ends, strict=True))
