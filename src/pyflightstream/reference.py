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
        "FlightStream versions are canonical 26.XXX identifiers with "
        "exactly three fractional digits (26.120), the vendor display "
        "name is an alias (26.12), and ordering comes only from the "
        "registered list position, never from parsing the identifier.",
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
        "structured refusals carry their facts as attributes.",
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


def _evidence_text(record: VersionStatus) -> str:
    """Return the evidence citation of one per-version record."""
    parts = []
    if record.report:
        parts.append(record.report)
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
        absorb(entry.manual_ref)
        absorb(entry.notes)
        for record in entry.versions.values():
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
        "Several chapter headers state they draft only the subset needed so "
        "far; a chapter appearing in this table is not a claim of completeness "
        "for its page range. Manual areas outside the scripting chapters (GUI "
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


def _database_meta_sentence(entry_count: int, scope: str) -> str:
    """Return the provenance sentence shared by both rendering layers."""
    registered = ", ".join(f"{v.canonical} ({v.alias})" for v in known_versions())
    return (
        f"Generated from the command database of pyflightstream "
        f"{_package_version()}. Scope: {scope}. "
        f"Registered versions, release order: {registered}. "
        f"{entry_count} commands. Every entry paraphrases the FlightStream manual "
        "and cites its page (manual_ref); statuses follow the evidence rules of "
        "CLAUDE.md invariant 3."
    )


# ---------------------------------------------------------------------------
# Layer 1: self-contained HTML page (offline fallback).
# ---------------------------------------------------------------------------


def _format_versions_html(entry: CommandEntry) -> str:
    lines = [
        f'<span class="status-{record.status}">{html.escape(canonical)}: {record.status}</span>'
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
        f"<td>{html.escape(entry.manual_ref)}</td></tr>"
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
            "<th>Arguments</th><th>Versions</th><th>Manual ref</th></tr>\n"
            f"{rows}\n</table>"
        )

    body = "\n".join(sections)
    return (
        "<!DOCTYPE html>\n<html><head><meta charset='utf-8'>"
        f"<title>pyflightstream command reference</title><style>{_STYLE}</style></head>"
        "<body>\n<h1>pyflightstream command reference</h1>\n"
        f'<p class="meta">{html.escape(_database_meta_sentence(entry_count, scope))}</p>\n'
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
        Optional version filter, canonical or alias; see
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


def _md_cell(text: str) -> str:
    """Escape one markdown table cell (pipes and line breaks)."""
    return text.replace("|", "\\|").replace("\n", " ").strip()


def _status_span(status: Status) -> str:
    """Return the status word wrapped in its CSS class span."""
    return f'<span class="status-{status}">{status}</span>'


def _entry_markdown(entry: CommandEntry) -> str:
    """Render one command as a markdown section with anchor heading."""
    lines = [f"## {entry.name}", ""]
    lines.append(f"Phase `{entry.phase}`, layout `{entry.layout}`. Manual: {entry.manual_ref}.")
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
        evidence = _evidence_text(record) or entry.manual_ref
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
            f"{len(members)} entries. Statuses follow the evidence rules of "
            "CLAUDE.md invariant 3: `documented` cites the manual, `verified` "
            "and `broken` cite a committed probe report, `removed` records "
            "the manual page stating the removal.",
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
    for members in chapters.values():
        for entry in members:
            for version in versions:
                record = entry.status_in(version)
                if record is None:
                    none_counts[version.canonical] += 1
                else:
                    counts[version.canonical][record.status] += 1

    lines = [
        "# Version compatibility matrix",
        "",
        _database_meta_sentence(entry_count, "all registered versions"),
        "",
        "An empty cell means no recorded evidence for that version: the "
        "command awaits release-notes review or backfill probing, and the "
        "script builder refuses it for that version until evidence lands.",
        "",
        "## Evidence per version",
        "",
        "| Version | Vendor name | Documented | Verified | Broken | Removed | No evidence "
        "| Manual edition |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for version in versions:
        row = counts[version.canonical]
        edition = editions.get(version.canonical, "none registered")
        lines.append(
            f"| {version.canonical} | {version.alias} "
            f"| {row[Status.DOCUMENTED]} | {row[Status.VERIFIED]} | {row[Status.BROKEN]} "
            f"| {row[Status.REMOVED]} | {none_counts[version.canonical]} "
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
                record = entry.status_in(version)
                cells.append(_status_span(record.status) if record else "")
            link = f"[{entry.name}](reference/{entry.chapter}.md#{entry.name.lower()})"
            lines.append(f"| {link} | " + " | ".join(cells) + " |")
        lines.append("")
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
