"""Tier 1, 0.32.0 package I1: the documentation site is organized by task.

GEO-066 2.1: the workspace and workflow guide is one page per run type or
topic with each fact in one home, and the definition of record is one page.
The top of the nav was the five task groups of 0.32.0 (Getting started,
Workflows, Post-processing, Reference, Migration) until 0.33.0, when the
a decision of the 0.33 scope (NFR-29 R1) grouped it by Diataxis quadrant
with the SRS under a Project group; the expectations below moved with it:
the five groups are the quadrants and Project, every migration page is under
Project, the definition of record is under Reference and every run-type page
under How-to guides. Nothing else these tests hold changed.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import yaml
from markdown.extensions.toc import slugify

from tests.tier1_offline._workflow_docs import WORKFLOW_PAGE_NAMES

REPO = Path(__file__).resolve().parents[2]
DOCS = REPO / "docs"
GROUPS = ["Tutorials", "How-to guides", "Reference", "Explanation", "Project"]


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


def test_the_nav_has_exactly_the_five_groups_in_order():
    names = [next(iter(item)) for item in _nav()]
    assert names == GROUPS, names


def test_every_migration_page_is_listed_under_project():
    listed = _group("Project")
    on_disk = sorted(path.name for path in DOCS.glob("migrating-to-*.md"))
    assert on_disk, "no migration page on disk: the check would prove nothing"
    assert set(on_disk) <= set(listed), sorted(set(on_disk) - set(listed))
    assert not [p for p in _pages(_nav()) if p.startswith("migrating-to-") and p not in listed]


def test_the_definition_of_record_is_one_page_under_reference():
    assert "post-processing-definitions.md" in _group("Reference")
    text = (DOCS / "post-processing-definitions.md").read_text(encoding="utf-8")
    assert len(text.splitlines()) > 1000, "the definition of record was split or cut down"
    assert not list(DOCS.glob("post-processing-definitions-*.md"))


def test_the_workspace_guide_is_an_index_and_each_run_type_has_a_page():
    index = (DOCS / "workspace-and-workflows.md").read_text(encoding="utf-8")
    assert len(index.splitlines()) < 1000
    workflows = _group("How-to guides")
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
    missing = sorted(
        path.relative_to(DOCS).as_posix()
        for path in DOCS.rglob("*.md")
        if path.relative_to(DOCS).as_posix() not in listed
        and not path.relative_to(DOCS).as_posix().startswith("srs/")
    )
    assert not missing, missing


def test_no_second_home_for_a_fact_no_heading_repeats_across_the_workflow_pages():
    seen: dict[str, str] = {}
    for page in WORKFLOW_PAGE_NAMES:
        fence = False
        for line in (DOCS / page).read_text(encoding="utf-8").splitlines():
            if re.match(r"^\s*(```|~~~)", line):
                fence = not fence
            heading = re.match(r"^#{1,4} (.+?)\s*$", line)
            if heading and not fence:
                slug = slugify(heading.group(1), "-")
                assert slug not in seen or seen[slug] == page, (
                    f"heading {slug!r} is on {seen[slug]} and on {page}"
                )
                seen[slug] = page


def test_every_link_between_pages_resolves_to_a_page_and_an_anchor():
    """The split moved sections; a link that still names the old page is broken."""
    pages = {p.relative_to(DOCS).as_posix(): p for p in DOCS.rglob("*.md")}
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


def test_the_recorded_only_list_keeps_the_merge_h_correction():
    """The split must carry the page as feat/0-32 has it, not as it stood at the branch point.

    slipstream_wake_stabilization left the recorded-only list at 0.32.0; the page
    that holds the list is the input library page.
    """
    text = (DOCS / "workflow-input-library.md").read_text(encoding="utf-8")
    assert "The seven this" in text
    assert "`set_base_region_trailing_edges`, `slipstream_wake_stabilization` and" not in text
    assert "removing-surfaces.md#the-slipstream-wake-stabilization" in text


def test_the_qsteady_refusal_names_the_page_that_explains_the_passage_positions():
    from pyflightstream.cases import workflows

    source = Path(workflows.__file__).read_text(encoding="utf-8")
    match = re.search(r"the in-plane loads \((docs/[\w-]+\.md), RPT-089\)", source)
    assert match, "the refusal no longer cites a page"
    page = REPO / match.group(1)
    assert page.is_file()
    assert workflows.PASSAGE_POSITIONS_VARIABLE in page.read_text(encoding="utf-8"), match.group(1)
