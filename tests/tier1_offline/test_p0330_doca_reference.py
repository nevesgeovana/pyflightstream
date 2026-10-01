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
import functools
import importlib.util
import re
import sys
import tomllib
import zlib
from pathlib import Path

import griffe
import pytest
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
    """The root and every public module at every depth, from the affirmed list."""
    return ["pyflightstream", *PUBLIC_MODULES]


#: The public modules that declare no ``__all__``: 51 of 122 when DOC-A
#: measured it, 7 once DOC-B part 1 gave the others one and WP3 (AD-11) gave
#: ``workspace.inputs`` one, its ten new public modules each declaring their
#: own. Their surface is the public names they define (R2 as amended in SRS
#: 1.53.0). The list only shrinks: a new public module declares ``__all__``
#: (R8), and a module listed here that gains one leaves the list in the same
#: change. Six of the seven are the modules DOC-B part 2 completes;
#: ``script.helpers`` stays because it sits at its module-size baseline
#: entry, which an ``__all__`` would exceed.
MODULES_WITHOUT_ALL = {
    "pyflightstream.post.field_frames",
    "pyflightstream.post.probe_fields",
    "pyflightstream.results.native_surface",
    "pyflightstream.results.tables",
    "pyflightstream.run.cli",
    "pyflightstream.run.records",
    "pyflightstream.script.helpers",
}


@functools.cache
def _static_package():
    """The package as the renderer reads it: griffe, from the sources, no import."""
    return griffe.load("pyflightstream", search_paths=[str(REPO / "src")], resolve_aliases=False)


def _static_module(module_name: str):
    package = _static_package()
    return package if module_name == "pyflightstream" else package[module_name.split(".", 1)[1]]


def _expected_surface(module_name: str) -> set[str]:
    """The public names of a module by the renderer's own rule, read statically.

    Deliberately not the generator's rule: the generator imports the module
    and reads ``__all__`` at run time, or walks its source; this asks griffe,
    the library mkdocstrings renders with, which names it holds public. A
    submodule is a page of its own, not a name of its parent's surface.
    """
    module = _static_module(module_name)
    if module.exports is not None:
        return {str(name) for name in module.exports}
    return {
        name for name, member in module.members.items() if member.is_public and not member.is_module
    }


_ENTRY = re.compile(r"^::: ([\w.]+)[ \t]*$", re.MULTILINE)
_ENTRY_WITH_OPTIONS = re.compile(r"^::: ([\w.]+)[ \t]*\n((?:    .*\n)*)", re.MULTILINE)


def _entries(page: str, module_name: str) -> set[str]:
    """The names a page carries an mkdocstrings entry for; a foreign path stays whole."""
    found = set()
    for target in _ENTRY.findall(page):
        if target == module_name:
            continue  # the module's own docstring, not a name of its surface
        prefix = f"{module_name}."
        found.add(target[len(prefix) :] if target.startswith(prefix) else target)
    return found


def _entry_defects(page: str, module_name: str) -> list[str]:
    """Why an entry of the page would render less than its object, or nothing.

    Each entry must resolve, in the renderer's own reading of the sources, to
    an object; and only one option block is allowed on a name's entry: the
    one that names the function a package re-exports under its submodule's
    name. The block that silenced the docstring parser for a listed defect
    left with the last defect (DOC-B, NFR-30). Anything else
    (``members: false``, a filter) could hide what the entry is for, so it
    is refused here rather than trusted.
    """
    package = _static_package()
    defects = []
    for target, options in _ENTRY_WITH_OPTIONS.findall(page):
        if target == module_name:
            continue  # the module's own docstring, rendered without members on purpose
        try:
            obj = package[target.split(".", 1)[1]]
            if obj.is_alias:
                obj.final_target  # noqa: B018  (resolving is the check)
        except Exception as error:  # a KeyError or an alias resolution error
            defects.append(f"{target} does not resolve in the sources: {error!r}")
            continue
        name = target.rpartition(".")[2]
        allowed = {"", f"    options:\n      members: [{name}]\n"}
        if options not in allowed:
            defects.append(f"{target} carries options that may hide it: {options!r}")
    return defects


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
        "the reference's list of public modules is not the affirmed one of "
        "test_public_api.PUBLIC_MODULES"
    )
    without_all = {m for m in subpackages if _static_module(m).exports is None}
    assert without_all == MODULES_WITHOUT_ALL, (
        f"public modules newly without __all__ (declare one, R8): "
        f"{sorted(without_all - MODULES_WITHOUT_ALL)}; listed modules that now "
        f"declare one (take them off the list): {sorted(MODULES_WITHOUT_ALL - without_all)}"
    )
    pages = generator.api_reference_pages()
    summary = pages["SUMMARY.md"]
    failures = []
    total = 0
    for module_name in subpackages:
        slug = module_name.split(".", 1)[1].replace(".", "/") if "." in module_name else module_name
        page = pages.get(f"{slug}.md")
        assert page is not None, f"{module_name} has no reference page"
        assert f"({slug}.md)" in summary, f"{module_name}'s page is not in the reference menu"
        expected = _expected_surface(module_name)
        total += len(expected)
        missing, extra = _api_differences(page, module_name, expected)
        if missing or extra:
            failures.append(f"{module_name}: missing {sorted(missing)}, extra {sorted(extra)}")
        failures += _entry_defects(page, module_name)
    assert not failures, "\n".join(failures)
    # Non-vacuity: 123 modules and 1894 names measured at 0.33.0 development;
    # the floor leaves room for the one name decision 9 deletes and little more.
    assert len(subpackages) >= 120, subpackages
    assert total >= 1850, f"only {total} public names were compared"

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
    # And the entry check refuses an entry that resolves to nothing and one
    # whose options would render less than its object.
    assert _entry_defects(page, "pyflightstream.script") == []
    dangling = page + "\n::: pyflightstream.script.NoSuchName\n"
    assert len(_entry_defects(dangling, "pyflightstream.script")) == 1
    hidden = page.replace(
        "::: pyflightstream.script.Script\n",
        "::: pyflightstream.script.Script\n    options:\n      members: false\n",
        1,
    )
    assert len(_entry_defects(hidden, "pyflightstream.script")) == 1


def test_the_built_reference_holds_every_public_name():
    """NFR-29 R2: the rendered site's inventory, when a build is at hand.

    P0330-DOC-API-COMPLETE
    """
    # P0330-DOC-API-COMPLETE: the check the docs job runs after the strict
    # build, proved here on inventories written for the purpose, then run on
    # the site in this checkout if one was built after the last source change.
    generator = _script("gen_api_reference")
    expected = set()
    for module_name in _expected_subpackages():
        expected.update(f"{module_name}.{name}" for name in _expected_surface(module_name))
    assert len(expected) >= 1850

    def inventory(names: set[str]) -> bytes:
        body = "".join(f"{name} py:function 1 api/x/#$ -\n" for name in sorted(names))
        header = b"# Sphinx inventory version 2\n# Project: x\n# Version: 0\n# zlib\n"
        return header + zlib.compress(body.encode("utf-8"))

    assert generator.inventory_names(inventory(expected)) == expected
    assert generator.missing_from_inventory(expected) == []
    dropped = sorted(expected)[len(expected) // 2]
    assert generator.missing_from_inventory(expected - {dropped}) == [dropped]

    built = REPO / "site" / "objects.inv"
    sources = [*(REPO / "src").rglob("*.py"), SCRIPTS / "gen_api_reference.py"]
    if not built.is_file() or built.stat().st_mtime < max(p.stat().st_mtime for p in sources):
        pytest.skip("no site built after the last source change; the docs job checks it")
    assert generator.missing_from_inventory(generator.inventory_names(built.read_bytes())) == []


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


#: The ``python -m`` tools the guides name, beside the console scripts.
MODULE_TOOLS = (
    "python -m pyflightstream.workspace.excel",
    "python -m pyflightstream.workspace.excel_bridge",
)
CLI_ARGUMENTS_MEASURED = 355
CLI_SUBCOMMANDS_MEASURED = 45

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
    # The tool list is named here, not taken from the generator: the console
    # scripts pyproject.toml declares, and the two module entries the guides
    # name. A tool the generator dropped would otherwise leave both sides.
    assert sorted(names) == sorted([*declared, *MODULE_TOOLS]), names
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
        subcommands += sum(
            1 for command, argument in expected if command != tool.name and not argument
        )
        if expected != found:
            failures.append(
                f"{tool.name}: missing {sorted(expected - found)[:10]}, "
                f"extra {sorted(found - expected)[:10]}"
            )
    assert not failures, "\n".join(failures)
    # Non-vacuity, at the counts measured at 0.33.0 development (help flags
    # and positionals included). The parity arm of GOAL-038 keeps every
    # option and subcommand of 0.32.0, so these only grow.
    assert len(tools) == 7, names
    assert options >= CLI_ARGUMENTS_MEASURED, f"only {options} arguments were compared"
    assert subcommands >= CLI_SUBCOMMANDS_MEASURED, f"only {subcommands} subcommands"

    # The control: a page with one row cut, and one with an invented option.
    tool = next(t for t in tools if t.name == "pyfs-matrix")
    page = pages[f"{tool.slug}.md"]
    expected = set()
    _walk(tool.parser, tool.name, expected)
    # A long option spelled on exactly one row of the page, taken from the
    # parser, so the control needs no option name of its own.
    lines = page.splitlines()
    unique = sorted(
        (command, argument)
        for command, argument in expected
        if argument.startswith("--")
        and sum(1 for line in lines if _ROW.match(line) and f"`{argument}`" in line) == 1
    )
    assert unique, f"no option of {tool.name} sits on one row alone"
    command, option = unique[0]
    row = next(line for line in lines if _ROW.match(line) and f"`{option}`" in line)
    cut = page.replace(row + "\n", "", 1)
    assert (command, option) in expected - _page_pairs(cut), "cutting a row went unseen"
    invented = page.replace(row, row + "\n| `--no-such-flag` |  |  | invented |", 1)
    assert _page_pairs(invented) - expected == {(command, "--no-such-flag")}


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
    # The skip marker is honoured by the same reading: a block marked skip
    # (one that needs the solver) is never among the executed ones, every
    # other block is, and the executed blocks are most of the page.
    fences = _FENCE.findall(text)
    skipped = [block for block in fences if block not in blocks]
    assert len(blocks) + len(skipped) == len(fences)
    assert len(skipped) < len(blocks), f"{len(skipped)} of {len(fences)} blocks are skipped"
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
    # R9: the LaTeX guides are linked from the navigation, not absorbed
    # (decision 14): one page in the menu links every PDF in guide/, and the
    # home page links the folder.
    assert "guides.md" in _group("Tutorials")
    guides = (DOCS / "guides.md").read_text(encoding="utf-8")
    pdfs = sorted(p.name for p in (REPO / "guide").glob("pyfts-guide-*.pdf"))
    assert len(pdfs) >= 8, pdfs
    # The repository URL is read from pyproject's [project.urls], its one
    # home, rather than written here: the shipped-surface guard keeps
    # identifiers out of the versioned tree outside the exempted files.
    config = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    repository = config["project"]["urls"]["Repository"].rstrip("/")
    for pdf in pdfs:
        assert f"]({repository}/blob/main/guide/{pdf})" in guides
    home = (DOCS / "index.md").read_text(encoding="utf-8")
    assert f"]({repository}/tree/main/guide)" in home


def test_the_renderer_is_a_docs_dependency_with_its_licence_card():
    """NFR-29 R7: mkdocstrings[python] in the docs dependencies, its card committed."""
    # NFR-29 R7 (decision 11 of GOAL-038)
    project = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    dev = project["optional-dependencies"]["dev"]
    assert any(req.replace(" ", "").startswith("mkdocstrings[python]") for req in dev), dev
    plugins = yaml.safe_load((REPO / "properdocs.yml").read_text(encoding="utf-8"))["plugins"]
    assert any(isinstance(p, dict) and "mkdocstrings" in p for p in plugins), plugins
    cards = [
        path
        for path in (REPO / "reports").glob("RPT-*.md")
        if "mkdocstrings" in (text := path.read_text(encoding="utf-8"))
        and "RPT-009" in text
        and "| mkdocstrings | " in text
        and "ISC" in text
    ]
    assert cards, "no licence card for mkdocstrings in the form of RPT-009"
