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

from pyflightstream.utils.errors import ManualDraftError

__all__ = [
    "ManualCommand",
    "coverage_against",
    "parse_script_index",
    "parse_signatures",
    "propose_layout",
    "read_pdf_pages",
    "render_chapter",
    "render_entry",
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
    if command.inline_args:
        lines.append("  args:")
        for raw in command.inline_args:
            lines.append(f"    - name: {_argument_name(raw)}")
            lines.append("      type: ???")
    else:
        lines.append("  args: []")
    lines.append(f'  manual_ref: "{source} p.{command.page}"')
    lines.append("  versions:")
    for canonical, status in versions.items():
        lines.append(f'    "{canonical}": {{status: {status}}}')
    lines.append(
        f"  drafted: >-\n"
        f"    Drafted by pyflightstream.utils.manual from {source} p.{command.page}"
        f"{f' ({command.section})' if command.section else ''}. Layout proposed because "
        f"{why}. Argument TYPES and any argument written on a continuation line are "
        f"not readable from the signature and are left unanswered on purpose. Review "
        f"against the manual page, then delete this line."
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
