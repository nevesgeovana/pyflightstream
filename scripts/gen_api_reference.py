"""Generate the Python API reference and the exceptions catalog (NFR-29 R2, R6).

Pipeline role: a docs-build helper, imported by ``scripts/gen_docs_pages.py``
(which writes the pages at build time, so nothing generated is committed)
and by the tier-1 tests that prove the reference complete.

The reference has one page per public subpackage: the root package and every
module one level below it whose name has no leading underscore. A page holds
one mkdocstrings entry (``::: dotted.name``) per name of the subpackage's
public surface, which is its ``__all__``; a module that declares no
``__all__`` exposes the public names it defines itself, read from its source.
Every name is on the page. The tier of a name only orders it: the names a
guide or an example uses come first, the rest follow under "Advanced". A name
nobody should use leaves ``__all__`` rather than being hidden here (NFR-29 R8).

The exceptions catalog is generated from :mod:`pyflightstream.exceptions`:
the hierarchy under its two roots, then one row per class with its base and
the first line of its docstring, each linked to its entry in the reference.
"""

from __future__ import annotations

import ast
import importlib
import importlib.util
import inspect
import pkgutil
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = "pyflightstream"

#: The two tiers, in page order.
TIER_USED = "Used in the guides"
TIER_ADVANCED = "Advanced"

_DIRECTIVE = re.compile(r"^::: ([\w.]+)\s*$", re.MULTILINE)
_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_FENCE = re.compile(r"^```python[^\n]*\n(.*?)^```", re.MULTILINE | re.DOTALL)


def public_subpackages() -> list[str]:
    """Return the root package and every public module one level below it.

    Returns
    -------
    list of str
        ``pyflightstream`` first, then ``pyflightstream.<name>`` for every
        module or subpackage whose name has no leading underscore, sorted.
    """
    package = importlib.import_module(PACKAGE)
    below = sorted(
        f"{PACKAGE}.{info.name}"
        for info in pkgutil.iter_modules(package.__path__)
        if not info.name.startswith("_")
    )
    return [PACKAGE, *below]


def _source_path(module_name: str) -> Path:
    module = importlib.import_module(module_name)
    return Path(inspect.getfile(module))


def _defined_public_names(module_name: str) -> list[str]:
    tree = ast.parse(_source_path(module_name).read_text(encoding="utf-8"))
    names: list[str] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.append(node.name)
        elif isinstance(node, ast.Assign):
            names += [t.id for t in node.targets if isinstance(t, ast.Name)]
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.append(node.target.id)
    return sorted({name for name in names if not name.startswith("_")})


def public_surface(module_name: str) -> list[str]:
    """Return the public names of one subpackage.

    Parameters
    ----------
    module_name : str
        A dotted module name.

    Returns
    -------
    list of str
        The module's ``__all__``, sorted; for a module that declares none,
        the public functions, classes and module-level assignments its own
        source defines (imported names are not its surface).
    """
    module = importlib.import_module(module_name)
    declared = getattr(module, "__all__", None)
    if declared is not None:
        return sorted(str(name) for name in declared)
    return _defined_public_names(module_name)


def guide_words(repo: Path = REPO) -> set[str]:
    """Return every identifier the runnable examples and the guides' code use.

    Parameters
    ----------
    repo : Path, optional
        The repository root.

    Returns
    -------
    set of str
        The identifiers in ``examples/*.py`` and in the ``python`` blocks of
        the hand-written guide pages (the SRS and the migration pages are
        records, not guides, and are left out).
    """
    words: set[str] = set()
    for path in sorted((repo / "examples").glob("*.py")):
        words.update(_WORD.findall(path.read_text(encoding="utf-8")))
    for path in sorted((repo / "docs").glob("*.md")):
        if path.name.startswith(("migrating-to-", "release-notes")):
            continue
        for block in _FENCE.findall(path.read_text(encoding="utf-8")):
            words.update(_WORD.findall(block))
    return words


def page_slug(module_name: str) -> str:
    """Return the page name under ``api/`` for a subpackage, without suffix.

    Parameters
    ----------
    module_name : str
        A name :func:`public_subpackages` returns.

    Returns
    -------
    str
        ``pyflightstream`` for the root, the last dotted part otherwise.
    """
    return module_name.rpartition(".")[2]


def _summary(module_name: str) -> str:
    doc = inspect.getdoc(importlib.import_module(module_name)) or ""
    first = doc.strip().split("\n\n")[0]
    return " ".join(first.split()).replace("|", "\\|")


def subpackage_page(module_name: str, words: set[str]) -> str:
    """Render the reference page of one subpackage.

    Parameters
    ----------
    module_name : str
        A name :func:`public_subpackages` returns.
    words : set of str
        The identifiers the guides use, from :func:`guide_words`.

    Returns
    -------
    str
        Markdown: the module docstring, then one ``::: <module>.<name>``
        entry per public name, the names the guides use first.
    """
    names = public_surface(module_name)
    used = [name for name in names if name in words]
    advanced = [name for name in names if name not in words]
    source = (
        "`__all__`"
        if hasattr(importlib.import_module(module_name), "__all__")
        else ("public definitions (the module declares no `__all__`)")
    )
    lines = [
        f"# `{module_name}`",
        "",
        f"Generated from the docstrings at build time: every one of the {len(names)} "
        f"names in the {source} of `{module_name}` has an entry below. The names a "
        "guide or an example uses come first; the others follow under Advanced.",
        "",
        f"::: {module_name}",
        "    options:",
        "      show_root_heading: false",
        "      show_root_toc_entry: false",
        "      members: false",
        "",
    ]
    for tier, group in ((TIER_USED, used), (TIER_ADVANCED, advanced)):
        if not group:
            continue
        lines += [f"## {tier}", ""]
        for name in group:
            lines += _entry(module_name, name)
    return "\n".join(lines).rstrip() + "\n"


def _shadows_a_submodule(module_name: str, name: str) -> bool:
    module = importlib.import_module(module_name)
    if not hasattr(module, "__path__") or inspect.ismodule(getattr(module, name, None)):
        return False
    return importlib.util.find_spec(f"{module_name}.{name}") is not None


def _entry(module_name: str, name: str) -> list[str]:
    if not _shadows_a_submodule(module_name, name):
        return [f"::: {module_name}.{name}", ""]
    # The package re-exports a function under the name of its own submodule
    # (``pyflightstream.overview``). The static reader resolves the dotted path
    # to the submodule, so the entry renders that module with only the
    # function of the same name, and says so, rather than the module alone.
    return [
        f"`{module_name}.{name}` is the function `{name}` of the submodule of the "
        "same name, re-exported here; the entry shows that submodule with it.",
        "",
        f"::: {module_name}.{name}",
        "    options:",
        f"      members: [{name}]",
        "",
    ]


def documented_names(page: str, module_name: str) -> set[str]:
    """Return the names a reference page carries an entry for.

    Parameters
    ----------
    page : str
        The markdown of one reference page.
    module_name : str
        The subpackage the page documents.

    Returns
    -------
    set of str
        Each ``::: <module>.<name>`` entry as ``name``; an entry for any
        other path is returned whole, so it can never pass for a name of
        this subpackage. The module's own docstring entry is left out.
    """
    found: set[str] = set()
    for target in _DIRECTIVE.findall(page):
        if target == module_name:
            continue
        prefix = f"{module_name}."
        found.add(target[len(prefix) :] if target.startswith(prefix) else target)
    return found


def api_reference_pages(repo: Path = REPO) -> dict[str, str]:
    """Render the Python API reference, one page per public subpackage.

    Parameters
    ----------
    repo : Path, optional
        The repository root.

    Returns
    -------
    dict of str to str
        Page path under ``api/`` to its markdown, with ``index.md`` and the
        ``SUMMARY.md`` the literate-nav plugin reads.
    """
    words = guide_words(repo)
    index = [
        "# Python API",
        "",
        "Every public name of the package, generated from the docstrings at build "
        "time, one page per public subpackage. A page lists every name of the "
        "subpackage's `__all__`; the names a guide or an example uses come first. "
        "The [Python API tutorial](../tutorial-python-api.md) is the place to start, "
        "and the [exceptions catalog](../exceptions.md) lists every refusal.",
        "",
        "| Subpackage | Names | What it holds |",
        "|---|---:|---|",
    ]
    pages: dict[str, str] = {}
    summary = ["- [Overview](index.md)"]
    for module_name in public_subpackages():
        slug = page_slug(module_name)
        pages[f"{slug}.md"] = subpackage_page(module_name, words)
        count = len(public_surface(module_name))
        index.append(f"| [`{module_name}`]({slug}.md) | {count} | {_summary(module_name)} |")
        summary.append(f"- [{module_name}]({slug}.md)")
    pages["index.md"] = "\n".join(index) + "\n"
    pages["SUMMARY.md"] = "\n".join(summary) + "\n"
    return pages


def _first_line(cls: type) -> str:
    doc = inspect.getdoc(cls) or ""
    first = doc.strip().split("\n\n")[0]
    return " ".join(first.split()).replace("|", "\\|")


def exceptions_catalog_markdown() -> str:
    """Render the exceptions catalog page from :mod:`pyflightstream.exceptions`.

    Returns
    -------
    str
        Markdown: the hierarchy under the catalog's roots, then one row per
        catalogued class with its bases and the first line of its docstring,
        each name linked to its entry in the Python API reference.
    """
    module = importlib.import_module(f"{PACKAGE}.exceptions")
    classes = {name: getattr(module, name) for name in sorted(module.__all__)}
    by_class = {cls: name for name, cls in classes.items()}

    def parents(cls: type) -> list[str]:
        return [by_class[base] for base in cls.__bases__ if base in by_class]

    def link(name: str) -> str:
        return f"[`{name}`](api/exceptions.md#{PACKAGE}.exceptions.{name})"

    children: dict[str, list[str]] = {name: [] for name in classes}
    roots = []
    for name, cls in classes.items():
        found = parents(cls)
        if not found:
            roots.append(name)
        for parent in found:
            children[parent].append(name)

    tree: list[str] = []

    def walk(name: str, depth: int) -> None:
        tree.append(f"{'    ' * depth}- {link(name)}")
        for child in sorted(children[name]):
            walk(child, depth + 1)

    for root in roots:
        walk(root, 0)
    lines = [
        "# Exceptions catalog",
        "",
        f"Generated from `{PACKAGE}.exceptions` at build time. Every one of the "
        f"{len(classes)} exception and warning classes the package raises is importable "
        f"from `{PACKAGE}.exceptions`, so a caller catches without knowing which layer "
        "raised. A class with two parents in the tree is listed under both.",
        "",
        "## Hierarchy",
        "",
        *tree,
        "",
        "## Every class",
        "",
        "| Class | Derives from | What it means |",
        "|---|---|---|",
    ]
    for name, cls in classes.items():
        bases = ", ".join(f"`{base.__name__}`" for base in cls.__bases__)
        lines.append(f"| {link(name)} | {bases} | {_first_line(cls)} |")
    return "\n".join(lines) + "\n"
