"""Self-contained HTML reference rendered from the command database.

Pipeline role: presentation layer sitting above ``commands`` and
``versions``; nothing imports it back. ``pyflightstream.help()`` renders
the database (or one version's availability) into a single HTML page
and opens it in the default browser. At milestone M5 the same renderer
feeds the mkdocs command reference, so the interactive page and the
published docs share one rendering source.
"""

from __future__ import annotations

import html
import tempfile
import webbrowser
from importlib import metadata
from pathlib import Path

from pyflightstream.commands import ArgSpec, CommandEntry, CommandRegistry
from pyflightstream.versions import FsVersion, known_versions, resolve

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


def _format_arg(arg: ArgSpec) -> str:
    text = f"{arg.name}: {arg.type}"
    if arg.values:
        text += " in {" + ", ".join(arg.values) + "}"
    if arg.unit:
        text += f" [{arg.unit}]"
    if not arg.required:
        text += " (optional)"
    return html.escape(text)


def _format_versions(entry: CommandEntry) -> str:
    lines = []
    for canonical in sorted(entry.versions):
        record = entry.versions[canonical]
        lines.append(
            f'<span class="status-{record.status}">{html.escape(canonical)}: {record.status}</span>'
        )
    return "<br>".join(lines)


def _entry_row(entry: CommandEntry) -> str:
    args = "<br>".join(_format_arg(arg) for arg in entry.args) or "none"
    notes = f'<div class="notes">{html.escape(entry.notes)}</div>' if entry.notes else ""
    return (
        f"<tr><td><code>{html.escape(entry.name)}</code>{notes}</td>"
        f"<td>{entry.phase}</td><td>{entry.layout}</td><td>{args}</td>"
        f"<td>{_format_versions(entry)}</td>"
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
    registry = CommandRegistry.load()
    resolved = resolve(version) if version is not None else None
    entries = [
        entry
        for entry in registry.commands.values()
        if resolved is None or entry.status_in(resolved) is not None
    ]

    chapters: dict[str, list[CommandEntry]] = {}
    for entry in entries:
        chapters.setdefault(entry.chapter, []).append(entry)

    try:
        package_version = metadata.version("pyflightstream")
    except metadata.PackageNotFoundError:
        package_version = "unknown"

    scope = f"FlightStream {resolved.canonical}" if resolved else "all registered versions"
    registered = ", ".join(f"{v.canonical} ({v.alias})" for v in known_versions())
    sections = []
    for chapter in sorted(chapters):
        rows = "\n".join(_entry_row(e) for e in sorted(chapters[chapter], key=lambda e: e.name))
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
        f'<p class="meta">Generated from the command database of pyflightstream '
        f"{html.escape(package_version)}. Scope: {html.escape(scope)}. "
        f"Registered versions, release order: {html.escape(registered)}. "
        f"{len(entries)} commands. Every entry paraphrases the FlightStream manual "
        "and cites its page (manual_ref); statuses follow the evidence rules of "
        "CLAUDE.md invariant 3.</p>\n"
        f"{body}\n</body></html>\n"
    )


def help(  # noqa: A001
    version: str | FsVersion | None = None,
    path: str | Path | None = None,
    open_browser: bool = True,
) -> Path:
    """Write the HTML command reference and open it in the browser.

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
