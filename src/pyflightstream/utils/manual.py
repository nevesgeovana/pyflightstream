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
enum rules, because "Number of boundaries in the CFD or FEM mesh" is a
count and not a choice.

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

from pyflightstream.utils.errors import ManualDraftError

__all__ = [
    "TYPE_RULES",
    "Coverage",
    "ManualCommand",
    "TypeRule",
    "coverage_against",
    "parse_script_index",
    "parse_signatures",
    "propose_layout",
    "propose_type",
    "read_pdf_pages",
    "render_chapter",
    "render_entry",
    "sample_contradiction",
    "write_chapter",
]

#: A Script Index line pairs a command with the section that documents
#: it. Four characters minimum, so a two-letter enum value on its own
#: line cannot pass for a command name.
_INDEX_LINE = re.compile(r"^([A-Z][A-Z0-9_]{3,})\s+(\S.*?)\s*$")

#: The scripting reference introduces each command the same way, and the
#: placeholders after the name are its inline arguments in order.
_SIGNATURE = re.compile(r"^Function name:\s*([A-Z][A-Z0-9_]{2,})\s*(.*)$")
_PLACEHOLDER = re.compile(r"<([^>]+)>")

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
            match = _SIGNATURE.match(line.strip())
            if match is None:
                continue
            name = match.group(1)
            if name in found:
                continue
            placeholders = tuple(a.strip() for a in _PLACEHOLDER.findall(match.group(2)))
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
            "the four registered manuals run 396, 409, 410 and 413 pages."
        )
    return {i + 1: (reader.pages[i].extract_text() or "") for i in range(first - 1, last)}


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
    boundaries in the CFD or FEM mesh") was read as a closed set and
    drafted ``values: [CFD, FEM]``. A wrong ``???`` costs a reviewer a
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
    description took tokens from the sentences after it: "The threshold
    logic. One of the following: ABOVE or BELOW. The CAD faces that meet
    this criterion..." proposed ABOVE, BELOW and CAD.
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
    that refuses the token the sample passes. ``CAD_BODY_ROTATE``
    documents its ``AXIS`` as "one of the following: X, Y or Z" and calls
    it with ``2`` on the same page, in every edition; three
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
        Zero-based position in ``command.inline_args``.
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
    """
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
            f"{command.name}: a manual supports the status 'documented' only, and "
            f"{bad} were requested. verified and broken are promoted from a committed "
            "probe report by pyfs-qa apply-compat (CLAUDE.md invariant 3)."
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
            refused = sample_contradiction(command, index, proposed, values)
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


def write_chapter(path, body: str, *, write: bool = False) -> str:
    """Write a drafted chapter, but only when asked.

    The default is a dry run, and the reason is the measurement in this
    module's own docstring: the drafts reproduce 77 percent of
    hand-authored argument lists, so writing them unreviewed into the
    database the emitter validates against would put invented grammar in
    front of other people's scripts.

    Parameters
    ----------
    path : str or Path
        Destination. Point it at a scratch file to review before moving
        anything into ``src/pyflightstream/commands/``.
    body : str
        Output of :func:`render_chapter`.
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
