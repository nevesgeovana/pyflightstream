"""Command reference and compatibility matrix rendered from the database.

Pipeline role: presentation layer sitting above ``commands`` and
``versions``; nothing imports it back. This module is the single
rendering source for both delivery layers of the reference:
``pyflightstream.help()`` renders a self-contained HTML page and opens
it in the default browser (layer 1, the offline fallback), and the
markdown generators feed the docs site at build time (layer 2, the
published docs). Both layers read the same database through the same
extraction helpers, so they can never disagree.
"""

from __future__ import annotations

import html
import re
import tempfile
import webbrowser
from importlib import metadata, resources
from pathlib import Path

from pyflightstream.commands import (
    ArgSpec,
    CommandEntry,
    CommandRegistry,
    Status,
    VersionStatus,
)
from pyflightstream.versions import FsVersion, known_versions, manual_editions, resolve

_STYLE = """
body { font-family: system-ui, sans-serif; margin: 2rem auto; max-width: 70rem;
       color: #1c2733; background: #ffffff; }
h1 { font-size: 1.5rem; } h2 { font-size: 1.15rem; margin-top: 2rem; }
table { border-collapse: collapse; width: 100%; font-size: 0.85rem; }
th, td { border: 1px solid #d4dbe3; padding: 0.4rem 0.6rem; text-align: left;
         vertical-align: top; }
th { background: #eef2f6; }
code { font-family: ui-monospace, monospace; }
.notes { color: #55636f; font-size: 0.8rem; margin-top: 0.3rem; }
.status-documented { color: #1a6e2f; }
.status-removed { color: #a33030; }
.status-verified { color: #14508a; }
.status-broken { color: #a33030; font-weight: bold; }
.meta { color: #55636f; font-size: 0.85rem; }
"""


# ---------------------------------------------------------------------------
# House conventions (PLN-032): single home, rendered by both layers.
# ---------------------------------------------------------------------------

#: The naming and nomenclature conventions of the package, one
#: (title, text) pair per rule. This tuple is the single home of the
#: conventions: ``help()`` renders it as a section, the docs site page
#: is meant to be generated from :func:`conventions_markdown` (wiring
#: the generator is with the docs build, not this module), and the
#: tier 1 adherence audit (``tests/test_conventions.py``) enforces the
#: mechanical rules against the code.
CONVENTIONS: tuple[tuple[str, str], ...] = (
    (
        "Units ride the names",
        "Every physical quantity carries its SI unit as a name suffix: "
        "area_m2, chord_m, pitch_deg, timeout_s, mass_per_length_kg_per_m; "
        "sectional line densities end in _per_m. A number without a unit "
        "suffix is dimensionless by declaration (mach, ratio, fraction, "
        "relaxation), never an unstated unit.",
    ),
    (
        "Reference frames are explicit",
        "Positions and axes name their frame: artifact points live in the "
        "simulation geometry frame, planar probe grids prescribe an "
        "explicit origin-plus-axes FrameDefinition, and the cylindrical "
        "probe lattice pins the z-up convention by test. No quantity "
        "changes frame silently.",
    ),
    (
        "Two name registers, never mixed",
        "FlightStream native commands keep the manual's exact UPPER_SNAKE "
        "spelling (SET_AOA, START_SOLVER) and are emitted, cited, and "
        "stored verbatim; everything the library itself owns (functions, "
        "parameters, artifact kinds) is lowercase snake_case English.",
    ),
    (
        "Versions use the canonical scheme",
        "FlightStream versions are canonical YY.XXX identifiers with "
        "exactly three fractional digits (26.120), the vendor display "
        "name is recorded as an alias (26.12), and ordering comes only "
        "from the registered list position, never from parsing the "
        "identifier. An alias resolves only where it names exactly one "
        "build: the vendor reuses a release name across builds, so both "
        "26.12 and 26.1 name more than one, each refused with every "
        "candidate and its vendor build number named rather than "
        "resolving to one. The members are not written out here, and that "
        "is deliberate: a hand-written list of them has gone stale on "
        "every registration since, so the refusal itself is the list. "
        "Reuse is not descent either: one of those two families is a "
        "release with its hotfixes and the other is separate releases "
        "that happened to share a name, which the registry states per "
        "build rather than leaving to be read off the identifier.",
    ),
    (
        "Indices state their base",
        "Boundary, frame, and other solver entity indices are 1-based, "
        "following the FlightStream convention, and every entity-citing "
        "argument also accepts a declared label; Python-side sequences "
        "stay 0-based. Docstrings state the base wherever an index "
        "crosses the boundary between the two worlds.",
    ),
    (
        "Ids are stems, not paths",
        "Workspace input artifacts are selected by id, and an id is the "
        "file name stem inside the library (letters, digits, dot, "
        "underscore, hyphen); it is never a path, and naming templates "
        "are output-only (the manifest stays the identity authority).",
    ),
    (
        "Refusals teach",
        "Error messages name the physical or version cause and the "
        "remedy, main refusal wordings are pinned by test, and every "
        "exception class is importable from pyflightstream.exceptions; "
        "structured refusals carry their facts as attributes. Every "
        "CATALOGUED exception descends from PyflightstreamError, so one "
        "except clause catches the catalog, and each also keeps the "
        "standard-library base it would have had, so catching "
        "ValueError or RuntimeError still works. Read that word: a "
        "residual of bare standard-library raises survives outside the "
        "catalog. Every site the guard's walk REACHES is named in the "
        "ratchet in tests/test_exceptions_catalog.py, which is the "
        "single home of that list; the walk's own reach is stated in "
        "SRS FR-39, and at least one site sits outside it. Until the "
        "residual is empty the standard-library bases are what covers "
        "it, and the plural matters: it is mostly ValueError and also "
        "holds TypeError and RuntimeError sites, so being exhaustive "
        "today means catching PyflightstreamError together with "
        "ValueError, TypeError and RuntimeError.",
    ),
    (
        "Options are declared knobs",
        "Machine and QA tuning goes through the exact-key options "
        "registry (pyflightstream.options); anything that changes a "
        "physical result belongs in the case definition or workspace, "
        "recorded by the manifest, never in an option.",
    ),
    (
        "Behavior selectors are keyword-only",
        "Arguments that select behavior (active_only, resume, "
        "open_browser) are keyword-only, so call sites read as prose "
        "and new parameters never break positional calls.",
    ),
    (
        "Toggles read both vocabularies",
        "A solver flag is a Python bool, and the solver's own ENABLE and "
        "DISABLE are read as True and False by every helper argument and "
        "every settings field that switches one, because a setup carried "
        "over from the solver speaks that vocabulary. Each helper reads "
        "its toggles before it emits anything, and refuses a value in "
        "neither vocabulary naming the helper and the argument. "
        "Truthiness is never consulted, since a non-empty string is "
        "truthy and 'DISABLE' would otherwise silently emit ENABLE.",
    ),
    (
        "Diagnostics are nouns, validators say check_",
        "A function that MEASURES a property of a result is named for the "
        "quantity it returns, as a noun: sample_coverage beside "
        "ring_sample_weights, symmetry_floor, spurious_diagnostic, "
        "mass_closure. A function that REFUSES an invalid combination "
        "carries the check_ prefix and returns nothing: check_recipe, "
        "check_state_matches_config. The two are different jobs and the "
        "name says which, so a reader knows before opening it whether a "
        "call can raise.",
    ),
    (
        "A validator takes the values it compares where the object would "
        "reverse the dependency direction",
        "Where taking a configuration object would make a lower module "
        "import a higher one, a check_ function takes the individual "
        "values instead: check_state_matches_config takes two integer "
        "counts, so fsi.state keeps its import surface to pydantic and "
        "the module owning the persisted state needs nothing else. Such "
        "decomposed values are KEYWORD-ONLY, because same-typed scalars "
        "transpose silently in a positional call, which is the shape of "
        "the defect the check exists to catch. Convenience at one call "
        "site is not worth an upward import, and neither rule generalises "
        "to a validator whose object is already below it.",
    ),
)


def conventions_markdown() -> str:
    """Render the house conventions as a markdown section.

    Returns
    -------
    str
        One heading plus one titled paragraph per convention, rendered
        from the same ``CONVENTIONS`` home as the ``help()`` section,
        so any consumer of this function can never disagree with the
        offline page (single home, NFR-11).
    """
    blocks = [f"### {title}\n\n{text}" for title, text in CONVENTIONS]
    return "## Naming conventions\n\n" + "\n\n".join(blocks) + "\n"


def _conventions_html() -> str:
    """Render the conventions section of the HTML reference."""
    blocks = "\n".join(
        f"<h3>{html.escape(title)}</h3>\n<p>{html.escape(text)}</p>" for title, text in CONVENTIONS
    )
    return "<h2>Naming conventions</h2>\n" + blocks


# ---------------------------------------------------------------------------
# Shared extraction helpers (both rendering layers sit on these).
# ---------------------------------------------------------------------------


def _arg_text(arg: ArgSpec) -> str:
    """Return the one-line plain-text description of one argument."""
    text = f"{arg.name}: {arg.type}"
    if arg.values:
        text += " in {" + ", ".join(arg.values) + "}"
    if arg.unit:
        text += f" [{arg.unit}]"
    if not arg.required:
        text += " (optional)"
    return text


def _version_records(entry: CommandEntry) -> list[tuple[str, VersionStatus]]:
    """Return the entry's evidence records in registry release order."""
    return [
        (version.canonical, entry.versions[version.canonical])
        for version in known_versions()
        if version.canonical in entry.versions
    ]


def _citation_label(entry: CommandEntry) -> str:
    """Name the KIND of evidence an entry rests on, for a rendered page.

    An entry cites a manual page or a committed probe report, never both,
    and the page used to label every citation "Manual" and then print an
    empty string for the one entry resting on a report. Naming the kind
    is what makes the two distinguishable to a reader.
    """
    return "Manual" if entry.manual_ref else "Probe report"


def _evidence_text(record: VersionStatus) -> str:
    """Return the evidence citation of one per-version record.

    Both citation fields are printed, and the reason both are read here
    rather than one is the defect this function has already had once. A
    citation added to the model and consumed at a single call site
    leaves every other consumer rendering the CLAIM without the evidence
    for it, which reads as an unsupported assertion on the page a person
    actually looks at. ``probe_ref`` on a version row arrived at v0.5.0
    and this was the surface it did not reach: the one row using it
    rendered "the 26.121 solver answers the name with an unrecognised
    command error" beside the manual page of an edition that DOCUMENTS
    the command, with the run that measured it named nowhere.
    """
    parts = []
    if record.report:
        parts.append(record.report)
    if record.probe_ref:
        parts.append(record.probe_ref)
    if record.note:
        parts.append(record.note)
    if record.successor:
        parts.append(f"Successor: {record.successor}")
    return "; ".join(parts)


def _grouped_by_chapter(version: FsVersion | None) -> dict[str, list[CommandEntry]]:
    """Group database entries by chapter, optionally scoped to one version.

    Parameters
    ----------
    version : FsVersion or None
        When given, only commands with an evidence record for this
        version (hotfix inheritance included) are kept; removed
        commands stay visible with their removal note. None keeps the
        whole database.

    Returns
    -------
    dict of str to list of CommandEntry
        Entries per chapter file stem, names sorted inside each
        chapter.
    """
    registry = CommandRegistry.load()
    chapters: dict[str, list[CommandEntry]] = {}
    for entry in registry.commands.values():
        if version is not None and entry.status_in(version) is None:
            continue
        chapters.setdefault(entry.chapter, []).append(entry)
    for members in chapters.values():
        members.sort(key=lambda entry: entry.name)
    return dict(sorted(chapters.items()))


def _chapter_title(chapter: str) -> str:
    """Return the display title of a chapter file stem."""
    return chapter.replace("_", " ").capitalize()


# Manual citations as the database writes them: "SRC-003 p.341",
# "SRC-003 pp.344-346". Page numbers only, never manual text.
_CITATION_PATTERN = re.compile(r"SRC-(\d{3})\s+pp?\.\s?(\d+)(?:\s*-\s*(\d+))?")
_EDITION_SOURCE_PATTERN = re.compile(r"SRC-\d{3}")
_EDITION_RANGE_PATTERN = re.compile(r"pp\.?\s*(\d+)\s*-\s*(\d+)")


def _chapter_headers() -> dict[str, str]:
    """Return the leading comment block of each chapter YAML file.

    The headers name the manual chapter each file drafts and cite its
    page range; they are the only place this information lives, so the
    coverage report reads them from the installed package. Lines are
    joined with spaces, so a citation wrapped across comment lines
    reassembles.

    Returns
    -------
    dict of str to str
        Header text keyed by chapter file stem.
    """
    headers: dict[str, str] = {}
    package = resources.files("pyflightstream.commands")
    for resource in sorted(package.iterdir(), key=lambda item: item.name):
        if not resource.name.endswith(".yaml") or resource.name == "_meta.yaml":
            continue
        lines = []
        for line in resource.read_text(encoding="utf-8").splitlines():
            if not line.startswith("#"):
                break
            lines.append(line.lstrip("#").strip())
        headers[resource.name.removesuffix(".yaml")] = " ".join(filter(None, lines))
    return headers


def _citation_pages(text: str) -> dict[str, set[int]]:
    """Return the manual pages cited in ``text``, keyed by source id."""
    pages: dict[str, set[int]] = {}
    for match in _CITATION_PATTERN.finditer(text):
        source = f"SRC-{match.group(1)}"
        start = int(match.group(2))
        end = int(match.group(3) or start)
        pages.setdefault(source, set()).update(range(start, end + 1))
    return pages


def _database_cited_pages() -> dict[str, set[int]]:
    """Return every manual page cited anywhere in the database.

    Scans the chapter headers, every ``manual_ref``, the entry notes,
    and the per-version notes, so the gap analysis credits every
    recorded citation.

    A ``removed`` row's note is NOT credited, and the exclusion is what
    keeps this report meaning anything. That note cites the edition the
    absence was read from, and an absence is read across a whole
    chapter: the rows entered on 2026-08-10 cite ranges like
    ``pp.275-369``. Credited, one such note marks every page of an
    edition as cited, and the section it feeds went from a page-by-page
    gap listing to "every page is cited" for that edition in a single
    change. The question this report answers is which pages somebody has
    drafted a command FROM, and a note saying a command is not on any of
    them is not an answer to it.

    Returns
    -------
    dict of str to set of int
        Cited page numbers keyed by source id (for example
        ``"SRC-003"``).
    """
    pages: dict[str, set[int]] = {}

    def absorb(text: str | None) -> None:
        if not text:
            return
        for source, found in _citation_pages(text).items():
            pages.setdefault(source, set()).update(found)

    for header in _chapter_headers().values():
        absorb(header)
    for entry in CommandRegistry.load().commands.values():
        absorb(entry.citation)
        absorb(entry.notes)
        for record in entry.versions.values():
            if record.status is not Status.REMOVED:
                absorb(record.note)
    return pages


def _page_spans(pages: set[int]) -> str:
    """Collapse a page-number set into a span list, ``"300-306, 310"``."""
    ordered = sorted(pages)
    spans: list[str] = []
    start = prev = ordered[0]
    for page in ordered[1:]:
        if page == prev + 1:
            prev = page
            continue
        spans.append(f"{start}-{prev}" if prev > start else f"{start}")
        start = prev = page
    spans.append(f"{start}-{prev}" if prev > start else f"{start}")
    return ", ".join(spans)


def _coverage_rows() -> list[tuple[str, str, str, int]]:
    """Return one coverage row per chapter: stem, title, pages, count.

    The page text re-emits the citations found in the chapter YAML
    header; a header without a citation is reported as such rather
    than guessed at.
    """
    chapters = _grouped_by_chapter(None)
    headers = _chapter_headers()
    rows = []
    for chapter, members in chapters.items():
        header = headers.get(chapter, "")
        citations = [match.group(0) for match in _CITATION_PATTERN.finditer(header)]
        pages = "; ".join(dict.fromkeys(citations)) or "no page citation in the chapter header"
        rows.append((chapter, _chapter_title(chapter), pages, len(members)))
    return rows


def _coverage_notes() -> list[str]:
    """Return the honest coverage caveats as plain-text paragraphs.

    Gaps are derived where the database can know them: the registered
    manual edition page range in ``commands/_meta.yaml`` against every
    page cited in the database. Where the database cannot know what is
    missing, the note says so explicitly instead of guessing.
    """
    cited = _database_cited_pages()
    notes = []
    for canonical, edition in manual_editions().items():
        source_match = _EDITION_SOURCE_PATTERN.search(edition)
        if source_match is None:
            continue
        source = source_match.group(0)
        range_match = _EDITION_RANGE_PATTERN.search(edition)
        if range_match is None:
            notes.append(
                f"{source} (the edition registered for {canonical}) records no "
                "closed page range for its scripting reference in "
                "commands/_meta.yaml, so no gap listing can be computed for it."
            )
            continue
        start, end = int(range_match.group(1)), int(range_match.group(2))
        uncited = set(range(start, end + 1)) - cited.get(source, set())
        if uncited:
            notes.append(
                f"{source} scripting reference pages not yet cited by any "
                f"database entry or chapter header (registered range "
                f"pp.{start}-{end}, edition for {canonical}): "
                f"pp.{_page_spans(uncited)}. The database cannot know which "
                "commands live on an uncited page; absence here means not yet "
                "drafted, not absent from the manual."
            )
        else:
            notes.append(
                f"Every page of the registered {source} scripting reference "
                f"range (pp.{start}-{end}, edition for {canonical}) is cited by "
                "at least one database entry or chapter header. A cited page "
                "can still hold undrafted commands; citation is not exhaustion."
            )
        outside = {page for page in cited.get(source, set()) if page < start or page > end}
        if outside:
            notes.append(
                f"Database citations of {source} outside that registered range "
                f"(pp.{_page_spans(outside)}) point at scripting material beyond "
                "the core reference span: scripting basics, toolbox chapters, "
                "worked examples, and usage guidance. No page range is "
                "registered for those areas, so the database cannot compute "
                "their gaps."
            )
    notes.append(
        "Each chapter header states whether the chapter is complete for its "
        "page range, and each says how many editions it was stamped "
        "against. A header naming fewer than the registered count predates "
        "a build that has since joined; no number is interpolated here, "
        "because the count that belongs in that sentence is the one the "
        "header was written with and not today's. Read a cited page as "
        "cited rather than as exhausted: the claim is that the commands the "
        "editions document are recorded, not that nothing else could be on "
        "the page. Manual areas outside the scripting chapters (GUI "
        "reference, theory) are out of scope of the command database and are "
        "not tracked here."
    )
    return notes


def _package_version() -> str:
    """Return the installed package version, or ``"unknown"``."""
    try:
        return metadata.version("pyflightstream")
    except metadata.PackageNotFoundError:
        return "unknown"


#: What each evidence state rests on and what the emitter does with it,
#: as data, because there are TWO rendering layers and this repository
#: has already shipped a correction to one of them and not the other.
#: Both consume this tuple, so neither can carry a different legend.
#:
#: The right-hand column is the half a reader cannot get from the status
#: name. These are EVIDENCE states rather than quality judgements, so
#: `documented` says a manual page describes the command and nobody has
#: run it, not that it works; and two of the five make the script
#: builder refuse, which is what a person reading the matrix to plan a
#: run actually needs to know.
_STATUS_LEGEND: tuple[tuple[str, str, str], ...] = (
    (
        "documented",
        "A manual page of that edition describes the command and its grammar "
        "(manual_ref), or a committed report measured the solver ACCEPTING a "
        "command no edition documents (the ENTRY's probe_ref; on a version row "
        "that field is for `removed` alone). Nobody has run it on this build, so "
        "it is a claim about a document rather than about the solver.",
        "Emitted, subject to the argument and phase checks every emission gets.",
    ),
    (
        "verified",
        "A Tier 2 probe ran the command on a licensed machine and observed its "
        "effect. The strongest POSITIVE state: a run watched the command do what "
        "the manual says. `broken` and a measured `removed` also rest on a run, "
        "and what they record is a failure.",
        "Emitted, subject to the argument and phase checks every emission gets.",
    ),
    (
        "broken",
        "A probe recorded a discrepancy between the manual and the solver: the "
        "script aborted at the command, the log carried an error inside the "
        "probe's own region, or the command ran and changed nothing. A command "
        "that runs but does nothing is broken, not verified. A build that does "
        "not carry the command lands in `removed` when the probe reads the "
        "solver's refusal of the name; it still lands here when the build "
        "refuses without writing that record, as an access violation does.",
        "REFUSED, with BrokenCommandError. Waivable per command with "
        "Script.allow_broken(name, reason=...), which needs a reason because "
        "the waiver, the report it overrides and the first line it covers are "
        "all recorded in the run manifest.",
    ),
    (
        "removed",
        "The build does not carry the command, and the row says which of three "
        "things happened: an edition STATES the withdrawal, an edition simply "
        "STOPS PRINTING the command, or a probe MEASURED the solver refusing "
        "the name. Only the third observes the solver, and it cites its run.",
        "REFUSED, with CommandNotInVersionError naming the build whose record it is, "
        "the reason and the citation, and saying so explicitly when that record was "
        "inherited from a base release rather than recorded for the build asked for.",
    ),
    (
        "empty cell",
        "No recorded evidence for that build. Not a claim that the command is "
        "absent: it awaits a manual reading of that edition or a probe. This is "
        "the honest absence, and no status is ever guessed to fill it.",
        "REFUSED, with CommandNotInVersionError listing the evidence that does "
        "exist on other builds.",
    ),
)


def _spelled(count: int) -> str:
    """Spell a small count, because these read as prose and not as data.

    The counts are derived from :data:`_STATUS_LEGEND` rather than
    written, so the sentence cannot disagree with the table under it;
    that is the whole reason they are computed. Rendering them as
    numerals was the cost, and this pays it back.
    """
    words = {
        0: "none",
        1: "one",
        2: "two",
        3: "three",
        4: "four",
        5: "five",
        6: "six",
        7: "seven",
        8: "eight",
    }
    return words.get(count, str(count))


def _status_legend_markdown() -> str:
    """Render the evidence legend as a markdown section."""
    rows = "\n".join(
        f"| {state} | {rests_on} | {emitter} |" for state, rests_on, emitter in _STATUS_LEGEND
    )
    refusing = sum(1 for _s, _r, emitter in _STATUS_LEGEND if emitter.startswith("REFUSED"))
    return (
        "## Reading a cell\n\n"
        f"The {_spelled(len(_STATUS_LEGEND))} states are EVIDENCE states, not "
        f"quality judgements, and {_spelled(refusing)} of them make the script "
        "builder REFUSE the "
        "command, each with a different error. That second column is the one a "
        "reader planning a run needs, and it is the one no status name carries."
        "\n\n"
        "| Cell | What it rests on | What `Script.emit` does |\n"
        "|---|---|---|\n"
        f"{rows}\n"
    )


def _status_legend_html() -> str:
    """Render the evidence legend as an HTML section."""
    rows = "\n".join(
        f"<tr><td>{html.escape(state)}</td><td>{html.escape(rests_on)}</td>"
        f"<td>{html.escape(emitter)}</td></tr>"
        for state, rests_on, emitter in _STATUS_LEGEND
    )
    refusing = sum(1 for _s, _r, emitter in _STATUS_LEGEND if emitter.startswith("REFUSED"))
    return (
        "<h2>Reading a cell</h2>\n"
        f"<p>The {_spelled(len(_STATUS_LEGEND))} states are evidence states, not "
        f"quality judgements, and {_spelled(refusing)} of them make the script "
        "builder refuse the "
        "command, each with a different error.</p>\n"
        "<table>\n<tr><th>Cell</th><th>What it rests on</th>"
        "<th>What Script.emit does</th></tr>\n"
        f"{rows}\n</table>"
    )


def _database_meta_sentence(entry_count: int, scope: str) -> str:
    """Return the provenance sentence shared by both rendering layers."""
    registered = ", ".join(f"{v.canonical} ({v.alias})" for v in known_versions())
    return (
        f"Generated from the command database of pyflightstream "
        f"{_package_version()}. Scope: {scope}. "
        f"Registered versions, release order: {registered}. "
        f"{entry_count} commands. Every entry cites exactly one piece of evidence: "
        "the FlightStream manual page that documents it (manual_ref), paraphrased "
        "and never quoted, or a committed probe report measuring that the solver "
        "accepts a command no edition documents (probe_ref). Statuses follow the "
        "evidence rules of CLAUDE.md invariant 3."
    )


# ---------------------------------------------------------------------------
# Layer 1: self-contained HTML page (offline fallback).
# ---------------------------------------------------------------------------


def _row_citation_html(record: VersionStatus) -> str:
    """Name the ROW's own evidence, where it has evidence of its own.

    Most rows have none and rest on the entry's citation, which the
    rightmost column already prints. A measured removal is the case that
    must not: it asserts the solver refused the name, and the entry cites
    an edition that documents the command, so printing the status alone
    beside that page sends a reader to a page contradicting the status.

    Both run-citation fields are read. ``probe_ref`` was the only one a
    measured removal could carry while the harness had no ``removed``
    outcome; a promoted one now cites the compat yaml through ``report``,
    and reading only the older field would have quietly reintroduced the
    contradiction this function exists to prevent.
    """
    citation = record.probe_ref or (record.report if record.status is Status.REMOVED else "")
    if not citation:
        return ""
    return f' <span class="notes">({html.escape(citation)})</span>'


def _format_versions_html(entry: CommandEntry) -> str:
    lines = [
        f'<span class="status-{record.status}">{html.escape(canonical)}: {record.status}</span>'
        + _row_citation_html(record)
        for canonical, record in _version_records(entry)
    ]
    return "<br>".join(lines)


def _entry_row_html(entry: CommandEntry) -> str:
    args = "<br>".join(html.escape(_arg_text(arg)) for arg in entry.args) or "none"
    notes = f'<div class="notes">{html.escape(entry.notes)}</div>' if entry.notes else ""
    return (
        f"<tr><td><code>{html.escape(entry.name)}</code>{notes}</td>"
        f"<td>{entry.phase}</td><td>{entry.layout}</td><td>{args}</td>"
        f"<td>{_format_versions_html(entry)}</td>"
        f"<td>{html.escape(_citation_label(entry))}: "
        f"{html.escape(entry.citation)}</td></tr>"
    )


def _coverage_html() -> str:
    """Render the manual-coverage section of the HTML reference."""
    rows = "\n".join(
        f"<tr><td>{html.escape(title)}</td><td>{html.escape(pages)}</td><td>{count}</td></tr>"
        for _, title, pages, count in _coverage_rows()
    )
    notes = "\n".join(f'<p class="notes">{html.escape(note)}</p>' for note in _coverage_notes())
    return (
        "<h2>Manual coverage</h2>\n"
        "<p>Chapters drafted from the manual, whole database, independent of "
        "any version scope. Pages are citations, never quotations.</p>\n"
        "<table>\n<tr><th>Chapter</th><th>Manual pages</th>"
        "<th>Commands drafted</th></tr>\n"
        f"{rows}\n</table>\n{notes}"
    )


def render_html(version: str | FsVersion | None = None) -> str:
    """Render the command database as one self-contained HTML page.

    Parameters
    ----------
    version : str, FsVersion, or None
        When given, only commands with an evidence record for this
        version (hotfix inheritance included) are rendered; removed
        commands stay visible with their removal note. None renders
        the whole database.

    Returns
    -------
    str
        Complete HTML document.
    """
    resolved = resolve(version) if version is not None else None
    chapters = _grouped_by_chapter(resolved)
    entry_count = sum(len(members) for members in chapters.values())

    scope = f"FlightStream {resolved.canonical}" if resolved else "all registered versions"
    sections = []
    for chapter, members in chapters.items():
        rows = "\n".join(_entry_row_html(entry) for entry in members)
        title = html.escape(chapter.replace("_", " "))
        sections.append(
            f"<h2>{title}</h2>\n<table>\n"
            "<tr><th>Command</th><th>Phase</th><th>Layout</th>"
            "<th>Arguments</th><th>Versions</th><th>Evidence</th></tr>\n"
            f"{rows}\n</table>"
        )

    body = "\n".join(sections)
    return (
        "<!DOCTYPE html>\n<html><head><meta charset='utf-8'>"
        f"<title>pyflightstream command reference</title><style>{_STYLE}</style></head>"
        "<body>\n<h1>pyflightstream command reference</h1>\n"
        f'<p class="meta">{html.escape(_database_meta_sentence(entry_count, scope))}</p>\n'
        f"{_status_legend_html()}\n"
        f"{_conventions_html()}\n"
        f"{_coverage_html()}\n"
        f"{body}\n</body></html>\n"
    )


def help(  # noqa: A001
    version: str | FsVersion | None = None,
    *,
    path: str | Path | None = None,
    open_browser: bool = True,
) -> Path:
    """Write the HTML command reference and open it in the browser.

    This is the offline fallback of the published docs reference;
    both are rendered from the same database by this module.

    Parameters
    ----------
    version : str, FsVersion, or None
        Optional version filter, canonical identifier (26.120); a vendor
        release name works only where it names exactly one registered
        build. See
        :func:`render_html`.
    path : str or Path, optional
        Where to write the page. Defaults to a stable file name in the
        system temporary directory, overwritten on each call.
    open_browser : bool
        Whether to open the page with the default browser. Set False
        in headless environments and tests.

    Returns
    -------
    Path
        Location of the written HTML file.
    """
    if path is None:
        suffix = resolve(version).canonical if version is not None else "all"
        path = Path(tempfile.gettempdir()) / f"pyflightstream_reference_{suffix}.html"
    target = Path(path)
    target.write_text(render_html(version), encoding="utf-8")
    if open_browser:
        webbrowser.open(target.as_uri())
    return target


# ---------------------------------------------------------------------------
# Layer 2: markdown pages for the docs site (generated at build time).
# ---------------------------------------------------------------------------


#: Marks a matrix cell whose evidence was inherited from the base
#: release rather than recorded for that build. A superscript rather
#: than a word, so the status stays the thing the eye lands on, and
#: with a title so hovering explains it without a legend lookup
#: (PLN-20260802-2016).
_INHERITED_MARK = (
    '<sup title="inherited from the base release, not probed on this build">base</sup>'
)


def _md_cell(text: str) -> str:
    """Escape one markdown table cell (pipes and line breaks)."""
    return text.replace("|", "\\|").replace("\n", " ").strip()


def _status_span(status: Status) -> str:
    """Return the status word wrapped in its CSS class span."""
    return f'<span class="status-{status}">{status}</span>'


def _entry_markdown(entry: CommandEntry) -> str:
    """Render one command as a markdown section with anchor heading."""
    lines = [f"## {entry.name}", ""]
    lines.append(
        f"Phase `{entry.phase}`, layout `{entry.layout}`. "
        f"{_citation_label(entry)}: {entry.citation}."
    )
    lines.append("")
    if entry.notes:
        lines.append(f"> {_md_cell(entry.notes)}")
        lines.append("")
    if entry.args:
        lines.append("| Argument | Specification |")
        lines.append("|---|---|")
        for arg in entry.args:
            spec = _arg_text(arg).removeprefix(f"{arg.name}: ")
            lines.append(f"| `{arg.name}` | {_md_cell(spec)} |")
        lines.append("")
    lines.append("| Version | Status | Evidence |")
    lines.append("|---|---|---|")
    for canonical, record in _version_records(entry):
        evidence = _evidence_text(record) or entry.citation
        lines.append(f"| {canonical} | {_status_span(record.status)} | {_md_cell(evidence)} |")
    lines.append("")
    return "\n".join(lines)


def markdown_reference_pages() -> dict[str, str]:
    """Render the command reference as markdown pages for the docs site.

    One page per manual chapter plus an index and a ``SUMMARY.md``
    navigation file (literate-nav format). Paths are relative to
    the ``reference/`` section of the docs; the docs build generates
    them through ``scripts/gen_docs_pages.py`` so the site can never
    drift from the database.

    Returns
    -------
    dict of str to str
        Page content keyed by path relative to ``reference/``.
    """
    chapters = _grouped_by_chapter(None)
    entry_count = sum(len(members) for members in chapters.values())

    pages: dict[str, str] = {}
    index_lines = [
        "# Command reference",
        "",
        _database_meta_sentence(entry_count, "all registered versions"),
        "",
        "Offline fallback: `pyflightstream.help()` renders this same database "
        "into a self-contained HTML page from the installed package, no docs "
        "site needed.",
        "",
        "See also the [version compatibility matrix](../compatibility.md).",
        "",
        "| Chapter | Manual pages | Commands drafted |",
        "|---|---|---|",
    ]
    nav_lines = ["* [Overview](index.md)"]
    coverage_pages = {chapter: pages for chapter, _, pages, _ in _coverage_rows()}
    for chapter, members in chapters.items():
        title = _chapter_title(chapter)
        index_lines.append(
            f"| [{title}]({chapter}.md) | {_md_cell(coverage_pages[chapter])} | {len(members)} |"
        )
        nav_lines.append(f"* [{title}]({chapter}.md)")

        page_lines = [
            f"# {title}",
            "",
            f"Commands of the `{chapter}` chapter of the database, "
            f"{len(members)} entries. The status words are defined once, on "
            "the [compatibility matrix](../compatibility.md#reading-a-cell), "
            "which says what each rests on and what the script builder does "
            "with it. Read it before this page: `broken` and `removed` are "
            "refusals, so a row here can be telling you the emitter will not "
            "write that command for that version.",
            "",
        ]
        page_lines.extend(_entry_markdown(entry) for entry in members)
        pages[f"{chapter}.md"] = "\n".join(page_lines)

    index_lines.append("")
    index_lines.append("## Manual coverage")
    index_lines.append("")
    index_lines.append(
        "The table above lists, per chapter drafted from the manual, the "
        "pages its header cites and the number of commands drafted. Pages "
        "are citations, never quotations. What the database knows about "
        "what it does not yet cover:"
    )
    index_lines.append("")
    for note in _coverage_notes():
        index_lines.append(f"* {_md_cell(note)}")
    index_lines.append("")
    pages["index.md"] = "\n".join(index_lines)
    pages["SUMMARY.md"] = "\n".join(nav_lines) + "\n"
    return pages


def markdown_compatibility_matrix() -> str:
    """Render the version compatibility matrix as one markdown page.

    Rows are commands grouped by chapter; columns are the registered
    FlightStream versions in release order. Cells carry the evidence
    status; an empty cell is the honest absence of recorded evidence
    for that version (no status is ever guessed).

    Returns
    -------
    str
        Complete markdown page.
    """
    chapters = _grouped_by_chapter(None)
    entry_count = sum(len(members) for members in chapters.values())
    versions = known_versions()
    editions = manual_editions()

    counts: dict[str, dict[Status, int]] = {
        version.canonical: dict.fromkeys(Status, 0) for version in versions
    }
    none_counts: dict[str, int] = dict.fromkeys(counts, 0)
    inherited_counts: dict[str, int] = dict.fromkeys(counts, 0)
    for members in chapters.values():
        for entry in members:
            for version in versions:
                evidence = entry.evidence_in(version)
                if evidence is None:
                    none_counts[version.canonical] += 1
                else:
                    counts[version.canonical][evidence.record.status] += 1
                    if evidence.inherited:
                        inherited_counts[version.canonical] += 1

    lines = [
        "# Version compatibility matrix",
        "",
        _database_meta_sentence(entry_count, "all registered versions"),
        "",
        _status_legend_markdown(),
        "A cell marked " + _INHERITED_MARK + " carries the base release's "
        "evidence rather than evidence recorded for that build. A build "
        "inherits its base release's record until a probe overrides it, "
        "WHERE the registry says it does: inheritance is stated per build "
        "rather than read off the identifier, because 26.101 sits at a "
        "hotfix index behind 26.100 and is an independent release. Where "
        "it applies it is the honest default, but an inherited cell is an "
        "assumption and a direct one is a measurement. Read the two "
        "differently: this repository has "
        "measured a hotfix changing a command's behaviour, so the "
        "assumption is known to be falsifiable.",
        "",
        "## Evidence per version",
        "",
        "| Version | Vendor name | Documented | Verified | Broken | Removed | No evidence "
        "| Of which inherited | Manual edition |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for version in versions:
        row = counts[version.canonical]
        edition = editions.get(version.canonical, "none registered")
        lines.append(
            f"| {version.canonical} | {version.alias} "
            f"| {row[Status.DOCUMENTED]} | {row[Status.VERIFIED]} | {row[Status.BROKEN]} "
            f"| {row[Status.REMOVED]} | {none_counts[version.canonical]} "
            f"| {inherited_counts[version.canonical]} "
            f"| {_md_cell(edition)} |"
        )
    lines.append("")

    header = " | ".join(version.canonical for version in versions)
    divider = "|---" * (len(versions) + 1) + "|"
    for chapter, members in chapters.items():
        lines.append(f"## {_chapter_title(chapter)}")
        lines.append("")
        lines.append(f"| Command | {header} |")
        lines.append(divider)
        for entry in members:
            cells = []
            for version in versions:
                evidence = entry.evidence_in(version)
                if evidence is None:
                    cells.append("")
                elif evidence.inherited:
                    cells.append(_status_span(evidence.record.status) + " " + _INHERITED_MARK)
                else:
                    cells.append(_status_span(evidence.record.status))
            link = f"[{entry.name}](reference/{entry.chapter}.md#{entry.name.lower()})"
            lines.append(f"| {link} | " + " | ".join(cells) + " |")
        lines.append("")
    return "\n".join(lines)


def _sharing_a_printed_name(versions: tuple[FsVersion, ...]) -> int:
    """Count the builds whose printed release name another build shares.

    Derived rather than written down: the figure moved from four to five
    the day 26.122 was registered, and the sentence carrying it as a
    literal sat seven lines from the code that computes the same set.

    Parameters
    ----------
    versions : tuple of FsVersion
        The registered builds, in release order.

    Returns
    -------
    int
        How many of them print a release name at least one other build
        also prints. Zero when every build prints a distinct name.
    """
    return sum(
        1
        for version in versions
        if version.prints is not None
        and sum(1 for other in versions if other.prints == version.prints) > 1
    )


def markdown_build_table() -> str:
    """Render the build correspondence table as one markdown page.

    Answers one question and is shaped around it: the reader has an
    install, wants to know which canonical identifier names it, and the
    only thing their install tells them is the line it prints when it
    starts. So the first two columns are the two values off that line,
    not the identifier.

    The printed release name alone cannot do this job, which is the
    whole reason the page exists, and the name to print is
    :attr:`FsVersion.prints` rather than :attr:`FsVersion.alias`. Those
    two differ wherever the vendor has shipped more than one build under
    one release name, which is most of the 26 series: those builds ship
    under one alias and their binaries print one release name, so
    neither string separates them. The members are not written out
    here, and the sentence saying so used to be followed by a list of
    them; the rendered page computes the tally, which is the only copy
    that cannot go stale. A table
    keyed on the alias would offer a 26.12 owner a name their solver
    never prints, they would match one of the rows that does print
    "26.1", and they would leave with the identifier of a different
    solver. The build number is what separates them, and it has been
    unique across every install registered here.

    Returns
    -------
    str
        Complete markdown page, generated from the version registry at
        docs build time and never committed.
    """
    versions = known_versions()
    shared = {
        version.prints
        for version in versions
        if version.prints is not None
        and sum(1 for other in versions if other.prints == version.prints) > 1
    }

    lines = [
        "# Which build do I have",
        "",
        "Every FlightStream install prints its release name and its build "
        "number when it starts. That PAIR is what identifies a build. "
        f"Neither half does it alone: {_sharing_a_printed_name(versions)} "
        "registered builds print the same release name as at least one "
        "other, and the name the vendor sells a build under is not always "
        "the name the binary prints.",
        "",
        "Read the two values off that line, find the row carrying both, "
        "and pass the identifier beside them wherever this package asks "
        "for a version. The columns are the two values rather than the "
        "whole line, because the line is not byte-identical across "
        "builds: the 25.0 solver writes a NUL byte into it where the "
        "newer builds write a space, which a terminal draws as a space "
        "and a comparison does not (RPT-023).",
        "",
        "| Release name it prints | Build number it prints | Pass this | Vendor ships it as |",
        "|---|---|---|---|",
    ]
    for version in versions:
        printed = "not recorded here yet" if version.prints is None else version.prints
        build = "not recorded here yet" if version.build is None else f"#{version.build}"
        note = " (shared)" if version.prints in shared else ""
        sold = version.alias
        if version.prints is not None and version.alias != version.prints:
            sold = f"{version.alias} (not what it prints)"
        lines.append(f"| {printed}{note} | {build} | `{version.canonical}` | {sold} |")

    lines.extend(
        [
            "",
            "## Reading the table",
            "",
            "The identifiers in the *Pass this* column are this package's "
            "own, in the `YY.XXX` scheme: the vendor major, the minor "
            "release, and a last digit that indexes builds within that "
            "release. That last digit is an ORDERING position and not a "
            "claim of descent, so a build at a hotfix index is not "
            "necessarily a hotfix of the one before it.",
            "",
        ]
    )
    if shared:
        names = ", ".join(sorted(shared))
        lines.extend(
            [
                f"A printed name marked (shared) is printed by more than one "
                f"registered build: {names}. Match on the build number, "
                "which is unique. Passing a shared release name to this "
                "package is refused rather than resolved to one of the "
                "builds, and the refusal lists the candidates by build "
                "number.",
                "",
            ]
        )
    if any(v.prints is not None and v.alias != v.prints for v in versions):
        lines.extend(
            [
                "The last column is the name the vendor sells the build "
                "under, which is the name that appears in release notes "
                "and download pages. Where it says *not what it prints*, "
                "the binary states a different release name about itself, "
                "so a reader matching on the sold name would land on the "
                "wrong row. Match on what your install prints.",
                "",
            ]
        )
    lines.extend(
        [
            "A build number recorded here comes from the solver's own "
            "banner captured in a committed report, never from a note or "
            "a recollection. That is why a newly registered build can "
            "appear with no number: it is registered before it is run.",
            "",
            "Registered is not the same as supported. What each build can "
            "actually do is on the [compatibility matrix](compatibility.md), "
            "and the level each one has reached is in "
            "`pyflightstream.support_table()`.",
        ]
    )
    return "\n".join(lines)


def percent_script_markdown(source: str) -> str:
    """Render a percent-format example script as one markdown page.

    Markdown cells (``# %% [markdown]``) become prose; code cells
    (``# %%``) become fenced Python blocks; a leading module docstring
    is dropped because it repeats the page introduction. This is the
    committed rendering of the no-notebooks policy (CLAUDE.md
    invariant 7): the ``.py`` file is the single source and the docs
    page is generated from it at build time.

    Parameters
    ----------
    source : str
        Content of a percent-format ``.py`` example.

    Returns
    -------
    str
        Complete markdown page.
    """
    blocks: list[str] = []
    cell_lines: list[str] = []
    is_markdown = False

    def flush() -> None:
        lines = list(cell_lines)
        while lines and not lines[0].strip():
            lines.pop(0)
        if not is_markdown and lines and lines[0].startswith('"""'):
            first = lines.pop(0).strip()
            if not (first.endswith('"""') and len(first) > 3):
                while lines and '"""' not in lines[0]:
                    lines.pop(0)
                if lines:
                    lines.pop(0)
        body = "\n".join(lines).strip("\n")
        if not body:
            return
        blocks.append(body if is_markdown else f"```python\n{body}\n```")

    for line in source.splitlines():
        marker = line.strip()
        if marker.startswith("# %%"):
            flush()
            cell_lines = []
            is_markdown = marker == "# %% [markdown]"
        elif is_markdown:
            cell_lines.append(line.removeprefix("#").removeprefix(" "))
        else:
            cell_lines.append(line)
    flush()
    return "\n\n".join(blocks) + "\n"
