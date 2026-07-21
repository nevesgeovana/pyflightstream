"""Command reference and compatibility matrix rendered from the database.

Pipeline role: presentation layer sitting above ``commands`` and
``versions``; nothing imports it back. This module is the single
rendering source for both delivery layers of the reference:
``pyflightstream.help()`` renders a self-contained HTML page and opens
it in the default browser (layer 1, the offline fallback), and the
markdown generators feed the mkdocs site at build time (layer 2, the
published docs). Both layers read the same database through the same
extraction helpers, so they can never disagree.
"""

from __future__ import annotations

import html
import tempfile
import webbrowser
from importlib import metadata
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
        f"{body}\n</body></html>\n"
    )


def help(  # noqa: A001
    version: str | FsVersion | None = None,
    path: str | Path | None = None,
    open_browser: bool = True,
) -> Path:
    """Write the HTML command reference and open it in the browser.

    This is the offline fallback of the published mkdocs reference;
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
# Layer 2: markdown pages for the mkdocs site (generated at build time).
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
    navigation file (mkdocs-literate-nav format). Paths are relative to
    the ``reference/`` section of the docs; the mkdocs build generates
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
        "| Chapter | Commands |",
        "|---|---|",
    ]
    nav_lines = ["* [Overview](index.md)"]
    for chapter, members in chapters.items():
        title = _chapter_title(chapter)
        index_lines.append(f"| [{title}]({chapter}.md) | {len(members)} |")
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
