"""Retained runtime, privacy and link checks, with shared test support."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

import markdown
import yaml
from markdown.extensions.toc import slugify

from tests.tier1_offline._docs_site import definition_page, site_pages
from tests.tier1_offline._workflow_docs import WORKFLOW_PAGE_NAMES

REPO = Path(__file__).resolve().parents[2]


DOCS = REPO / "docs"


def _nav() -> list:
    text = (REPO / "properdocs.yml").read_text(encoding="utf-8")
    return yaml.safe_load(text)["nav"]


def _pages(node) -> list[str]:
    """Every page file a nav node lists, in order."""
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


def test_upgrade_guidance_is_consolidated_under_help():
    assert "upgrading.md" in _group("Help")
    assert not [p for p in _pages(_nav()) if p.startswith("migrating-to-")]
    assert (DOCS / "upgrading.md").is_file()


def test_the_definition_of_record_is_an_index_under_reference():
    assert "post-processing-definitions.md" in _group("Reference")
    text = (DOCS / "post-processing-definitions.md").read_text(encoding="utf-8")
    families = sorted(
        path
        for rel, path in site_pages(DOCS, in_nav=True).items()
        if rel.startswith("definitions/")
    )
    fixture = json.loads(
        (Path(__file__).parent / "data/p0360_doc_slugs.json").read_text(encoding="utf-8")
    )
    # A retained legacy page is published and kept out of the nav (properdocs.yml not_in_nav).
    retained = set(site_pages(DOCS)) - set(site_pages(DOCS, in_nav=True))
    expected = {
        Path(definition_page(heading["slug"])).name
        for heading in fixture["definitions"]
        if heading["level"] == 2
        and heading["slug"] != "contents"
        and definition_page(heading["slug"]) not in retained
    }
    assert {family.name for family in families} == expected
    for family in families:
        relative = family.relative_to(DOCS).as_posix()
        assert relative in _group("Reference")
        assert f"]({relative}#" in text
    assert not list(DOCS.glob("post-processing-definitions-*.md"))


def test_the_workspace_guide_is_an_index_and_each_run_type_has_a_page():
    index = (DOCS / "workspace-and-workflows.md").read_text(encoding="utf-8")
    workflows = _group("Workspace CLI")
    for run_type, page in (
        ("steady", "workflow-steady.md"),
        ("unsteady", "workflow-unsteady.md"),
        ("unsteady_rotor", "workflow-unsteady-rotor.md"),
        ("qsteady_rotor", "workflow-qsteady-rotor.md"),
    ):
        assert page in workflows, page
        assert f"]({page})" in index, f"the index does not link the {run_type} page"
    for page in WORKFLOW_PAGE_NAMES:
        assert (DOCS / page).is_file(), page
        assert page in _pages(_nav()), f"{page} is on disk and not in the nav"


def test_every_hand_written_page_is_in_the_nav():
    """A page nobody can navigate to is not published."""
    listed = set(_pages(_nav()))
    missing = sorted(rel for rel in site_pages(DOCS, in_nav=True) if rel not in listed)
    assert not missing, missing


#: Pages the docs build writes (scripts/gen_docs_pages.py, gen_api_reference.py): a link to
#: them cannot resolve against the hand-written set, so they are named, not skipped.
BUILD_GENERATED_PREFIXES = ("examples/", "reference/", "api/", "cli/")
BUILD_GENERATED_PAGES = frozenset(
    {
        "builds.md",
        "compatibility.md",
        "contributing.md",
        "exceptions.md",
        "inputs.md",
        "fsi-tutorial.md",
        "architecture.md",
        "workspace-route-map.md",
    }
)


def test_every_link_between_pages_resolves_to_a_page_and_an_anchor():
    """The split moved sections; a link that still names the old page is broken."""
    pages = site_pages(DOCS)
    anchors: dict[str, set[str]] = {}
    for rel, path in pages.items():
        found: set[str] = set()
        fence = False
        for line in path.read_text(encoding="utf-8").splitlines():
            if re.match(r"^\s*(```|~~~)", line):
                fence = not fence
            heading = re.match(r"^#{1,6} (.*?)\s*$", line)
            if heading and not fence:
                found.add(slugify(heading.group(1), "-"))
        found.update(
            re.findall(
                r'\bid="([^"]+)"',
                markdown.markdown(
                    path.read_text(encoding="utf-8"), extensions=["toc", "pymdownx.superfences"]
                ),
            )
        )
        anchors[rel] = found
    broken = []
    for rel, path in pages.items():
        for match in re.finditer(
            r"\]\(([^)\s#]*)(?:#([^)\s]+))?\)", path.read_text(encoding="utf-8")
        ):
            target, anchor = match.groups()
            if target.startswith(("http", "mailto")):
                continue
            key = (
                rel
                if not target
                else os.path.normpath(os.path.join(os.path.dirname(rel), target)).replace("\\", "/")
            )
            if key in pages and anchor and anchor not in anchors[key]:
                broken.append(f"{rel} -> {key}#{anchor}")
            if (
                key not in pages
                and key.endswith(".md")
                and not key.startswith(BUILD_GENERATED_PREFIXES)
                and key not in BUILD_GENERATED_PAGES
            ):
                # A page link to a file that is neither hand-written nor generated at
                # build time used to be skipped silently (F-867).
                broken.append(f"{rel} -> {key} (no such page)")
    assert not broken, broken[:20]


def test_a_link_to_the_index_page_names_an_anchor_the_index_holds():
    """A section that moved off the index is linked at its new page, not at the index."""
    index = (DOCS / "workspace-and-workflows.md").read_text(encoding="utf-8")
    held = {slugify(h, "-") for h in re.findall(r"^#{1,4} (.+?)\s*$", index, re.M)}
    stale = []
    for path in DOCS.rglob("*.md"):
        for anchor in re.findall(
            r"workspace-and-workflows\.md#([^)\s]+)", path.read_text(encoding="utf-8")
        ):
            if anchor not in held:
                stale.append(f"{path.name}#{anchor}")
    assert not stale, stale[:20]


def test_a_link_to_a_page_of_the_split_names_a_page_that_exists():
    """A retargeted link to a page that was never written must fail here, not only in the build.

    Other targets (examples, reference, builds) are generated at build time, so
    only the pages this package owns are held to exist.
    """
    owned = set(WORKFLOW_PAGE_NAMES)
    missing = []
    for path in DOCS.rglob("*.md"):
        rel = path.relative_to(DOCS).as_posix()
        for target in re.findall(r"\]\(([^)\s#]+\.md)(?:#[^)\s]*)?\)", path.read_text("utf-8")):
            name = os.path.basename(target)
            if (name.startswith("workflow-") or name == "pproc-artifact.md") and (
                name not in owned or not (DOCS / name).is_file()
            ):
                missing.append(f"{rel} -> {target}")
    assert not missing, missing[:20]


def test_the_qsteady_refusal_names_the_page_that_explains_the_passage_positions():
    from pyflightstream.cases import workflows
    from pyflightstream.cases.workflows import _qsteady_rotor

    # The refusal is the quasi-steady builder's, in its module of the package
    # cases/workflows/ since 0.33.0 (AD-12).
    source = Path(_qsteady_rotor.__file__).read_text(encoding="utf-8")
    match = re.search(r"the in-plane loads \((docs/[\w-]+\.md), RPT-089\)", source)
    assert match, "the refusal no longer cites a page"
    page = REPO / match.group(1)
    assert page.is_file()
    assert workflows.PASSAGE_POSITIONS_VARIABLE in page.read_text(encoding="utf-8"), match.group(1)
