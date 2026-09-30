"""Tier 1, 0.33.0 package DOC-A: the documentation reference (NFR-29).

Each test names its requirement in its own source, because the goal's checker
reads function sources. The references are generated at build time by
``scripts/gen_api_reference.py`` and ``scripts/gen_cli_reference.py`` (called
from ``scripts/gen_docs_pages.py``); these tests call the same functions the
build calls and compare what the pages carry with a surface they compute
themselves, from the modules and the parsers, so a page that drops a name or
invents one fails here and not only in a reader's search. Each comparison
also runs once on a page deliberately cut and once on a page with an entry
added, so a check that accepts everything cannot pass.
"""

from __future__ import annotations

import argparse
import ast
import importlib
import importlib.util
import re
import sys
import tomllib
from pathlib import Path

import yaml

from tests.tier1_offline.test_public_api import PUBLIC_MODULES

REPO = Path(__file__).resolve().parents[2]
DOCS = REPO / "docs"
SCRIPTS = REPO / "scripts"


def _script(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Registered before it runs: a dataclass looks its module up by name.
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _nav() -> list:
    return yaml.safe_load((REPO / "properdocs.yml").read_text(encoding="utf-8"))["nav"]


def _pages(node) -> list[str]:
    if isinstance(node, str):
        return [node]
    if isinstance(node, list):
        return [page for item in node for page in _pages(item)]
    if isinstance(node, dict):
        return [page for value in node.values() for page in _pages(value)]
    return []


def _group(name: str) -> list[str]:
    for item in _nav():
        if isinstance(item, dict) and name in item:
            return _pages(item[name])
    raise AssertionError(f"no {name!r} group in the nav")


# --------------------------------------------------------------------- the API


def _expected_subpackages() -> list[str]:
    """The root and every public module one level below it, from the affirmed list."""
    return ["pyflightstream", *sorted(m for m in PUBLIC_MODULES if m.count(".") == 1)]


def _expected_surface(module_name: str) -> set[str]:
    """``__all__``; with none, the public names the module's own source defines."""
    module = importlib.import_module(module_name)
    if hasattr(module, "__all__"):
        return {str(name) for name in module.__all__}
    source = Path(module.__file__).read_text(encoding="utf-8")
    names: set[str] = set()
    for node in ast.parse(source).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            names.update(t.id for t in node.targets if isinstance(t, ast.Name))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
    return {name for name in names if not name.startswith("_")}


_ENTRY = re.compile(r"^::: ([\w.]+)[ \t]*$", re.MULTILINE)


def _entries(page: str, module_name: str) -> set[str]:
    """The names a page carries an mkdocstrings entry for; a foreign path stays whole."""
    found = set()
    for target in _ENTRY.findall(page):
        if target == module_name:
            continue  # the module's own docstring, not a name of its surface
        prefix = f"{module_name}."
        found.add(target[len(prefix) :] if target.startswith(prefix) else target)
    return found


def _api_differences(page: str, module_name: str, expected: set[str]) -> tuple[set, set]:
    documented = _entries(page, module_name)
    return expected - documented, documented - expected


def test_the_api_reference_carries_every_public_name_and_nothing_else():
    """NFR-29 R2: both set differences are empty for every public subpackage.

    P0330-DOC-API-COMPLETE
    """
    # P0330-DOC-API-COMPLETE
    generator = _script("gen_api_reference")
    subpackages = _expected_subpackages()
    assert generator.public_subpackages() == subpackages, (
        "the reference's list of public subpackages is not the affirmed one of "
        "test_public_api.PUBLIC_MODULES"
    )
    pages = generator.api_reference_pages()
    summary = pages["SUMMARY.md"]
    failures = []
    total = 0
    for module_name in subpackages:
        slug = module_name.rpartition(".")[2]
        page = pages.get(f"{slug}.md")
        assert page is not None, f"{module_name} has no reference page"
        assert f"({slug}.md)" in summary, f"{module_name}'s page is not in the reference menu"
        expected = _expected_surface(module_name)
        total += len(expected)
        missing, extra = _api_differences(page, module_name, expected)
        if missing or extra:
            failures.append(f"{module_name}: missing {sorted(missing)}, extra {sorted(extra)}")
    assert not failures, "\n".join(failures)
    # Non-vacuity: 577 names in 20 subpackages at the v0.32.0 audit.
    assert len(subpackages) >= 15, subpackages
    assert total >= 500, f"only {total} public names were compared"

    # The control: the same comparison refuses a cut page and a padded one.
    page = pages["script.md"]
    expected = _expected_surface("pyflightstream.script")
    cut = page.replace("::: pyflightstream.script.Script\n", "", 1)
    assert cut != page
    assert _api_differences(cut, "pyflightstream.script", expected) == ({"Script"}, set())
    padded = page + "\n::: pyflightstream.script._private_helper\n"
    assert _api_differences(padded, "pyflightstream.script", expected) == (
        set(),
        {"_private_helper"},
    )
    foreign = page + "\n::: pyflightstream.results.parse_loads\n"
    assert _api_differences(foreign, "pyflightstream.script", expected)[1] == {
        "pyflightstream.results.parse_loads"
    }


# --------------------------------------------------------------------- the CLI


def _walk(parser: argparse.ArgumentParser, path: str, out: set[tuple[str, str]]) -> None:
    """Every (command, argument) pair and every subcommand under a parser."""
    out.add((path, ""))
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            for name, sub in action.choices.items():
                _walk(sub, f"{path} {name}", out)
            continue
        if action.option_strings:
            for option in action.option_strings:
                out.add((path, option))
        else:
            name = action.metavar if isinstance(action.metavar, str) else action.dest
            out.add((path, f"<{name}>"))


_HEADING = re.compile(r"^#{2,6} `([^`]+)`\s*$")
_ROW = re.compile(r"^\| ((?:`[^`]+`)(?:, `[^`]+`)*) \|")


def _page_pairs(page: str) -> set[tuple[str, str]]:
    """The (command, argument) pairs a reference page documents, read from its tables."""
    pairs: set[tuple[str, str]] = set()
    command = None
    for line in page.splitlines():
        heading = _HEADING.match(line)
        if heading:
            command = heading.group(1)
            pairs.add((command, ""))
            continue
        row = _ROW.match(line)
        if row and command is not None:
            for spelled in re.findall(r"`([^`]+)`", row.group(1)):
                pairs.add((command, spelled))
    return pairs


def test_the_cli_reference_carries_every_tool_subcommand_and_option():
    """NFR-29 R3: every console tool, subcommand and option is on its page, and no other.

    P0330-DOC-CLI-COMPLETE
    """
    # P0330-DOC-CLI-COMPLETE
    generator = _script("gen_cli_reference")
    declared = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))["project"][
        "scripts"
    ]
    tools = generator.tools()
    names = [tool.name for tool in tools]
    assert set(declared) <= set(names), (
        f"console scripts with no page: {set(declared) - set(names)}"
    )
    assert "python -m pyflightstream.workspace.excel" in names, "the workbook tool has no page"
    pages = generator.cli_reference_pages()
    failures = []
    options = subcommands = 0
    for tool in tools:
        page = pages.get(f"{tool.slug}.md")
        assert page is not None, f"{tool.name} has no page"
        assert f"({tool.slug}.md)" in pages["SUMMARY.md"], f"{tool.name} is not in the menu"
        expected: set[tuple[str, str]] = set()
        _walk(tool.parser, tool.name, expected)
        found = _page_pairs(page)
        options += sum(1 for _, argument in expected if argument)
        subcommands += sum(1 for command, argument in expected if not argument) - 1
        if expected != found:
            failures.append(
                f"{tool.name}: missing {sorted(expected - found)[:10]}, "
                f"extra {sorted(found - expected)[:10]}"
            )
    assert not failures, "\n".join(failures)
    # Non-vacuity: 112 options and 30 subcommands at the v0.32.0 audit.
    assert len(tools) >= 7, names
    assert options >= 100, f"only {options} arguments were compared"
    assert subcommands >= 20, f"only {subcommands} subcommands were compared"

    # The control: a page with one row cut, and one with an invented option.
    page = pages["pyfs-matrix.md"]
    expected = set()
    _walk(next(t for t in tools if t.name == "pyfs-matrix").parser, "pyfs-matrix", expected)
    row = next(line for line in page.splitlines() if line.startswith("| `--apply`"))
    cut = page.replace(row + "\n", "", 1)
    assert expected - _page_pairs(cut), "cutting a row went unseen"
    invented = page.replace(row, row + "\n| `--no-such-flag` |  |  | invented |", 1)
    assert _page_pairs(invented) - expected, "an invented option went unseen"


# ---------------------------------------------------------------- the tutorial

_FENCE = re.compile(r"^```python[^\n]*\n(.*?)^```", re.MULTILINE | re.DOTALL)


def _executed_blocks(text: str) -> list[str]:
    """The python blocks the documentation tests execute: every one not marked skip."""
    blocks = []
    for match in _FENCE.finditer(text):
        before = text[: match.start()].rstrip().splitlines()
        if before and before[-1].strip() == "<!-- skip: next -->":
            continue
        blocks.append(match.group(1))
    return blocks


def test_the_python_api_tutorial_is_on_the_site_and_its_blocks_run():
    """NFR-29 R5: the Python API tutorial exists, is a tutorial, and its blocks run.

    P0330-DOC-TUTORIAL
    """
    # P0330-DOC-TUTORIAL
    page = DOCS / "tutorial-python-api.md"
    assert page.is_file(), "the Python API tutorial page is absent"
    assert "tutorial-python-api.md" in _group("Tutorials")
    text = page.read_text(encoding="utf-8")
    blocks = _executed_blocks(text)
    assert len(blocks) >= 5, f"only {len(blocks)} executed blocks on the tutorial"
    # The skip marker is honoured by the same reading: this page holds one
    # block that needs the solver, and it is not among the executed ones.
    assert len(_FENCE.findall(text)) == len(blocks) + 1
    assert _executed_blocks("<!-- skip: next -->\n```python\nx = 1\n```\n") == []
    namespace: dict[str, object] = {"__name__": "tutorial_python_api"}
    for index, block in enumerate(blocks):
        try:
            exec(compile(block, f"tutorial-python-api.md block {index + 1}", "exec"), namespace)
        except Exception as error:  # the block number is what a reader needs
            raise AssertionError(f"block {index + 1} of the tutorial failed: {error!r}") from error
    # What the tutorial teaches actually happened, not merely ran.
    assert str(namespace["version"]) == "26.124"
    assert len(namespace["plan"].points) == 3


# ------------------------------------------------------------------ the home


def test_the_home_page_offers_the_two_routes_near_its_top():
    """NFR-29 R4: the workspace route and the Python API route, before anything else.

    P0330-DOC-HOME
    """
    # P0330-DOC-HOME
    text = (DOCS / "index.md").read_text(encoding="utf-8")
    headings = re.findall(r"^## (.+?)\s*$", text, re.MULTILINE)
    assert headings and headings[0] == "Two ways in", headings[:3]
    section = text.split("## Two ways in", 1)[1].split("\n## ", 1)[0]
    assert text.index("## Two ways in") < 1000, "the routes are not near the top"
    for target in ("getting-started.md", "cli/index.md", "tutorial-python-api.md", "api/index.md"):
        assert f"]({target})" in section, f"the routes do not link {target}"
    assert "`pyfs-matrix`" in section and "Python API" in section


# ------------------------------------------------------------ the exceptions

_CATALOG_ROW = re.compile(
    r"^\| \[`(\w+)`\]\(api/exceptions\.md#pyflightstream\.exceptions\.\1\)", re.MULTILINE
)


def test_the_exceptions_catalog_lists_every_catalogued_exception():
    """NFR-29 R6: the catalog page is generated from the catalog and carries all of it.

    P0330-DOC-EXCEPTIONS
    """
    # P0330-DOC-EXCEPTIONS
    from pyflightstream import exceptions

    page = _script("gen_api_reference").exceptions_catalog_markdown()
    rows = set(_CATALOG_ROW.findall(page))
    catalogued = set(exceptions.__all__)
    assert catalogued - rows == set(), f"missing from the page: {sorted(catalogued - rows)}"
    assert rows - catalogued == set(), (
        f"on the page and not catalogued: {sorted(rows - catalogued)}"
    )
    assert len(rows) >= 60, f"only {len(rows)} classes compared"
    hierarchy = page.split("## Hierarchy", 1)[1].split("## Every class", 1)[0]
    for name in catalogued:
        assert f"[`{name}`]" in hierarchy, f"{name} is not in the hierarchy"
    generator = (SCRIPTS / "gen_docs_pages.py").read_text(encoding="utf-8")
    assert 'mkdocs_gen_files.open("exceptions.md"' in generator
    assert "exceptions.md" in _group("Reference")
    # The control: a row cut from the page is seen.
    first = sorted(catalogued)[0]
    cut = re.sub(rf"^\| \[`{first}`\].*\n", "", page, count=1, flags=re.MULTILINE)
    assert cut != page
    assert first not in set(_CATALOG_ROW.findall(cut))


# -------------------------------------------------------------------- the nav


def test_the_nav_is_the_four_quadrants_and_project_with_the_srs_under_project():
    """NFR-29 R1: Tutorials, How-to guides, Reference, Explanation, then Project."""
    # NFR-29 R1 (decision 13 of GOAL-038)
    names = [next(iter(item)) for item in _nav()]
    assert names == ["Tutorials", "How-to guides", "Reference", "Explanation", "Project"]
    srs = sorted(p.relative_to(DOCS).as_posix() for p in (DOCS / "srs").glob("*.md"))
    assert len(srs) >= 10, srs
    assert set(srs) <= set(_group("Project")), sorted(set(srs) - set(_group("Project")))
    elsewhere = [p for p in _pages(_nav()) if p.startswith("srs/") and p not in _group("Project")]
    assert not elsewhere, elsewhere
    for folder in ("api/", "cli/", "reference/"):
        assert folder in _group("Reference"), f"{folder} is not under Reference"
    # The LaTeX guides are linked from the home page, not absorbed (decision 14).
    home = (DOCS / "index.md").read_text(encoding="utf-8")
    assert "](https://github.com/nevesgeovana/pyflightstream/tree/main/guide)" in home
