"""Retained runtime, privacy and link checks, with shared test support."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import markdown
import yaml

from tests.tier1_offline._docs_site import definition_page, site_pages

ROOT = Path(__file__).resolve().parents[2]


DOCS = ROOT / "docs"


FIXTURE = json.loads((Path(__file__).parent / "data/p0360_doc_slugs.json").read_text("utf-8"))


def rendered(text: str) -> str:
    config = yaml.safe_load((ROOT / "properdocs.yml").read_text("utf-8"))
    names = ["tables", "fenced_code"]
    options = {}
    for entry in config["markdown_extensions"]:
        if isinstance(entry, dict):
            name, settings = next(iter(entry.items()))
            names.append(name)
            options[name] = settings or {}
        else:
            names.append(entry)
    return markdown.Markdown(extensions=names, extension_configs=options).convert(text)


def ids(page: Path) -> set[str]:
    return set(re.findall(r'\bid="([^"]+)"', rendered(page.read_text("utf-8"))))


def split_problems(docs: Path, index: str, family: str) -> list[str]:
    text = (docs / index).read_text("utf-8")
    problems = []
    resolved = ids(docs / index)
    for heading in FIXTURE[family]:
        slug = heading["slug"]
        if f'<a id="{slug}"></a>' not in text or slug not in resolved:
            problems.append(f"missing anchor: {slug}")
        if (
            family == "definitions"
            and heading["level"] <= 2
            and slug in {"contents", "post-processing-definitions"}
        ):
            continue
        after = text.split(f'<a id="{slug}"></a>', 1)[-1].split('<a id="', 1)[0]
        links = re.findall(r"\]\(([^)]+\.md)\#([^)]+)\)", after)
        if not links:
            problems.append(f"missing destination: {slug}")
        for page, anchor in links:
            target = docs / page
            if not target.is_file() or anchor not in ids(target):
                problems.append(f"broken destination: {page}#{anchor}")
    return problems


def definition_pins_problems(root: Path, docs: Path) -> list[str]:
    old = "post-processing-definitions.md"
    mapping = {}
    for heading in FIXTURE["definitions"]:
        if heading["level"] == 2 and heading["slug"] != "contents":
            family = definition_page(heading["slug"])
        if heading["level"] >= 2 and heading["slug"] != "contents":
            mapping[heading["slug"]] = family
    problems = []
    for folder in (root / "src", root / "tests"):
        for source in folder.rglob("*.py"):
            for page, anchor in re.findall(
                r"(post-processing-definitions\.md|definitions/[\w-]+\.md)#([\w-]+)",
                source.read_text("utf-8"),
            ):
                expected = mapping.get(anchor)
                if page == old or expected != page:
                    problems.append(f"stale pin: {source.name}: {page}#{anchor}")
                elif anchor not in ids(docs / page):
                    problems.append(f"missing pin anchor: {page}#{anchor}")
    return problems


def mesh_pins_problems(root: Path, docs: Path) -> list[str]:
    problems = []
    for folder in (root / "src", root / "tests"):
        for source in folder.rglob("*.py"):
            for page, anchor in re.findall(
                r"(mesh-inputs\.md|mesh/(?:how-to|reference|example)\.md)#([\w-]+)",
                source.read_text("utf-8"),
            ):
                if anchor not in ids(docs / page):
                    problems.append(f"missing pin anchor: {page}#{anchor}")
    return problems


def test_definitions_split(tmp_path):
    """P0360-DOC-DEFINITIONS-SPLIT (NFR-34): all old slugs, families and unchanged pins."""
    # 61 on 0.40.0: the far-field family page and its seven anchors (FR-450 to FR-459).
    assert not split_problems(DOCS, "post-processing-definitions.md", "definitions")
    expected = {
        Path(definition_page(h["slug"])).name
        for h in FIXTURE["definitions"]
        if h["level"] == 2 and h["slug"] != "contents"
    }
    retained = set(site_pages(DOCS)) - set(site_pages(DOCS, in_nav=True))
    expected = {name for name in expected if f"definitions/{name}" not in retained}
    assert {
        p.name for rel, p in site_pages(DOCS, in_nav=True).items() if rel.startswith("definitions/")
    } == expected
    assert not definition_pins_problems(ROOT, DOCS)
    for pin in FIXTURE["definition_pins"]:
        text = (ROOT / pin["source"]).read_text("utf-8")
        assert re.search(r"definitions/[\w-]+\.md#" + re.escape(pin["anchor"]) + r"\b", text)
    copied = tmp_path / "docs"
    shutil.copytree(DOCS, copied)
    index = copied / "post-processing-definitions.md"
    index.write_text(index.read_text("utf-8").replace('<a id="etaw"></a>', ""), "utf-8")
    assert "missing anchor: etaw" in split_problems(copied, index.name, "definitions")
    source = tmp_path / "src"
    source.mkdir()
    (source / "pin.py").write_text('"""post-processing-definitions' + '.md#etaw"""', "utf-8")
    assert any("stale pin" in p for p in definition_pins_problems(tmp_path, DOCS))


def test_mesh_split(tmp_path):
    """P0360-DOC-MESH-SPLIT (NFR-35): rendered headings exclude comments in fences."""
    assert not split_problems(DOCS, "mesh-inputs.md", "mesh")
    assert not mesh_pins_problems(ROOT, DOCS)
    assert {p.name for p in (DOCS / "mesh").glob("*.md")} == {
        "how-to.md",
        "reference.md",
        "example.md",
    }
    roles = {
        "how-to.md": "starting-from-an-obj-or-stl",
        "reference.md": "the-unit",
        "example.md": "a-complete-example-a-wing-obj-with-its-trailing-edge-by-file",
    }
    for page, anchor in roles.items():
        assert anchor in ids(DOCS / "mesh" / page), (page, anchor)
    copied = tmp_path / "docs"
    shutil.copytree(DOCS, copied)
    index = copied / "mesh-inputs.md"
    index.write_text(index.read_text("utf-8").replace('<a id="the-unit"></a>', ""), "utf-8")
    assert "missing anchor: the-unit" in split_problems(copied, index.name, "mesh")
    source = tmp_path / "src"
    source.mkdir()
    (source / "pin.py").write_text('"""mesh-inputs' + '.md#missing-anchor"""', "utf-8")
    assert mesh_pins_problems(tmp_path, DOCS) == [
        "missing pin anchor: mesh-inputs" + ".md#missing-anchor"
    ]
