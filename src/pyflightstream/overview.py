"""Architecture overview rendered from the live module docstrings.

Pipeline role: presentation layer sitting above every subpackage;
nothing imports it back. This module is the single rendering source for
both delivery layers of the architecture overview:
``pyflightstream.overview()`` renders a self-contained HTML page and
opens it in the default browser (layer 1, the offline fallback), and
:func:`markdown_overview` feeds the mkdocs site at build time (layer 2,
the published docs). Both layers read the same source: the actual top
docstrings of the package and its subpackages, imported at call time,
so the overview can never drift from the code it describes.

This is the LibraryHelp companion of the CommandHelp in
:mod:`pyflightstream.reference`: ``help()`` answers "which commands
exist and with what evidence", ``overview()`` answers "how the package
is put together and where to start".
"""

from __future__ import annotations

import html
import importlib
import inspect
import re
import tempfile
import webbrowser
from pathlib import Path

_STYLE = """
body { font-family: system-ui, sans-serif; margin: 2rem auto; max-width: 70rem;
       color: #1c2733; background: #ffffff; }
h1 { font-size: 1.5rem; } h2 { font-size: 1.15rem; margin-top: 2rem; }
code { font-family: ui-monospace, monospace; background: #eef2f6;
       padding: 0.05rem 0.25rem; border-radius: 3px; }
pre { background: #eef2f6; padding: 1rem; overflow-x: auto; line-height: 1.4; }
pre code { background: none; padding: 0; }
ul { margin: 0.4rem 0 0.8rem 1.2rem; }
.meta { color: #55636f; font-size: 0.85rem; }
.toc a { margin-right: 0.8rem; }
"""

# The layered pipeline, one tuple per dependency level, bottom layer
# last. Every module imports only modules of the rows below its own;
# the CLAUDE.md layout rule (versions <- commands <- script/results <-
# cases <- run/workspace <- post/qa) is the authority for the core
# stack (the CLAUDE.md text still spells the row "files"; workspace is
# its renamed successor and pyflightstream.files is the deprecation
# shim).
_CORE_LAYERS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("post", "qa"), "engineering data | probe and regression evidence"),
    (("run", "workspace"), "headless execution | input library, run layout, manifest"),
    (("cases",), "simulation and campaign definitions"),
    (("script", "results"), "validating script builder | output parsers"),
    (("commands",), "the evidence-backed per-version command database"),
    (("versions",), "canonical version identifiers and ordering"),
)

_SIDE_BRANCHES: tuple[tuple[str, str], ...] = (
    ("fsi", "structural executable of the aeroelastic coupling loop"),
    ("probes, farfield", "probe lattices and far-field conservation ledgers"),
    ("reference, overview", "presentation: command reference and this page"),
)

# Every subpackage the overview documents, in pipeline order: the core
# stack bottom-up, then the side branches, then the presentation layer.
_SECTIONS: tuple[str, ...] = (
    "versions",
    "commands",
    "script",
    "results",
    "cases",
    "run",
    "workspace",
    "post",
    "qa",
    "fsi",
    "probes",
    "farfield",
    "reference",
)

_ROLE_PATTERN = re.compile(r":(?:mod|class|func|meth|attr|data|obj|exc):`~?([^`]+)`")


def _module_doc(name: str) -> str:
    """Return the cleaned top docstring of one pyflightstream module.

    Parameters
    ----------
    name : str
        Module name relative to the package, for example ``"commands"``,
        or ``""`` for the package itself.

    Returns
    -------
    str
        The docstring with indentation normalized.

    Raises
    ------
    RuntimeError
        If the module has no docstring. The overview renders only live
        docstrings (didactic policy: module top-docstrings state the
        pipeline role), so a missing one is a defect to fix at the
        module, not to paper over here.
    """
    qualified = f"pyflightstream.{name}" if name else "pyflightstream"
    doc = importlib.import_module(qualified).__doc__
    if not doc:
        raise RuntimeError(
            f"{qualified} has no module docstring; the architecture overview "
            "renders only live docstrings so it can never go stale. Write the "
            "pipeline-role docstring in that module (didactic policy of "
            "CLAUDE.md), not prose here."
        )
    return inspect.cleandoc(doc)


def _layer_diagram() -> str:
    """Return the dependency-flow diagram as preformatted plain text.

    The arrow between rows points at the dependency: every module
    imports only modules of the rows below its own, never upward.
    """
    labels = [
        *("  ".join(names) for names, _ in _CORE_LAYERS),
        *(name for name, _ in _SIDE_BRANCHES),
    ]
    width = max(len(label) for label in labels) + 4
    lines = []
    for position, (names, caption) in enumerate(_CORE_LAYERS):
        lines.append(f"{'  '.join(names):<{width}}{caption}")
        if position < len(_CORE_LAYERS) - 1:
            lines.append("   |")
    lines.append("")
    lines.append("side branches, same downward-only import rule:")
    for name, caption in _SIDE_BRANCHES:
        lines.append(f"{name:<{width}}{caption}")
    return "\n".join(lines)


def _meta_sentence() -> str:
    """Return the provenance sentence shared by both rendering layers."""
    version = importlib.import_module("pyflightstream").__version__
    return (
        f"Generated at render time from the live module docstrings of "
        f"pyflightstream {version}; this page has no text of its own beyond "
        "the layer diagram, so it can never drift from the code."
    )


def _inline_code_html(text: str) -> str:
    """Escape one docstring text and mark inline code up as HTML."""
    escaped = html.escape(_ROLE_PATTERN.sub(r"``\1``", text))
    return re.sub(r"``([^`]+)``", r"<code>\1</code>", escaped)


def _doc_to_html(doc: str) -> str:
    """Render one cleaned docstring as HTML paragraphs and lists."""
    blocks = []
    for paragraph in re.split(r"\n\s*\n", doc.strip()):
        lines = paragraph.splitlines()
        if all(line.lstrip().startswith("- ") or line.startswith("  ") for line in lines):
            items = re.split(r"\n(?=\s*- )", paragraph)
            rendered = "\n".join(
                f"<li>{_inline_code_html(' '.join(item.split()).removeprefix('- '))}</li>"
                for item in items
            )
            blocks.append(f"<ul>\n{rendered}\n</ul>")
        else:
            blocks.append(f"<p>{_inline_code_html(' '.join(paragraph.split()))}</p>")
    return "\n".join(blocks)


def _doc_to_markdown(doc: str) -> str:
    """Render one cleaned docstring as markdown (roles and code spans)."""
    text = _ROLE_PATTERN.sub(r"`\1`", doc.strip())
    return text.replace("``", "`")


def render_overview_html() -> str:
    """Render the architecture overview as one self-contained HTML page.

    The entry view is the layer diagram (dependency flow); it is
    followed by the package docstring and one section per subpackage,
    each rendered from the module's live top docstring.

    Returns
    -------
    str
        Complete HTML document.
    """
    toc = " ".join(f'<a href="#{name}"><code>{name}</code></a>' for name in _SECTIONS)
    sections = [
        "<h2>Layer diagram</h2>",
        "<p>Dependencies flow strictly downward: every module imports only "
        "modules of the rows below its own, never upward.</p>",
        f"<pre><code>{html.escape(_layer_diagram())}</code></pre>",
        "<h2>The package in its own words</h2>",
        _doc_to_html(_module_doc("")),
        f'<p class="toc">Sections: {toc}</p>',
    ]
    for name in _SECTIONS:
        sections.append(f'<h2 id="{name}"><code>pyflightstream.{name}</code></h2>')
        sections.append(_doc_to_html(_module_doc(name)))
    body = "\n".join(sections)
    return (
        "<!DOCTYPE html>\n<html><head><meta charset='utf-8'>"
        f"<title>pyflightstream architecture overview</title><style>{_STYLE}</style></head>"
        "<body>\n<h1>pyflightstream architecture overview</h1>\n"
        f'<p class="meta">{html.escape(_meta_sentence())}</p>\n'
        f"{body}\n</body></html>\n"
    )


def overview(path: str | Path | None = None, open_browser: bool = True) -> Path:
    """Write the HTML architecture overview and open it in the browser.

    This is the offline fallback of the published architecture page;
    both are rendered from the same live docstrings by this module. It
    is the LibraryHelp companion of :func:`pyflightstream.help`, the
    command reference.

    Parameters
    ----------
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
        path = Path(tempfile.gettempdir()) / "pyflightstream_overview.html"
    target = Path(path)
    target.write_text(render_overview_html(), encoding="utf-8")
    if open_browser:
        webbrowser.open(target.as_uri())
    return target


def markdown_overview() -> str:
    """Render the architecture overview as one markdown page.

    Same content as :func:`render_overview_html`, for the mkdocs site;
    the build generates it through ``scripts/gen_docs_pages.py`` so the
    published page can never drift from the code.

    Returns
    -------
    str
        Complete markdown page.
    """
    lines = [
        "# Architecture overview",
        "",
        _meta_sentence(),
        "",
        "Offline fallback: `pyflightstream.overview()` renders this same page "
        "from the installed package, no docs site needed.",
        "",
        "## Layer diagram",
        "",
        "Dependencies flow strictly downward: every module imports only "
        "modules of the rows below its own, never upward.",
        "",
        "```text",
        _layer_diagram(),
        "```",
        "",
        "## The package in its own words",
        "",
        _doc_to_markdown(_module_doc("")),
        "",
    ]
    for name in _SECTIONS:
        lines.append(f"## `pyflightstream.{name}`")
        lines.append("")
        lines.append(_doc_to_markdown(_module_doc(name)))
        lines.append("")
    return "\n".join(lines)
