"""Readability guards for the documentation and their falsifying controls."""

from __future__ import annotations

import html
import json
import os
import re
import shutil
from pathlib import Path

import markdown
import yaml

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"
FIXTURE = json.loads((Path(__file__).parent / "data/p0360_doc_slugs.json").read_text("utf-8"))
NARRATIVE = re.compile(
    r"\b(since|until|before|from|as of)\s+v?0\.\d+(\.\d+)?\b"
    r"|\b(added|new|introduced|changed|removed|renamed)\s+in\s+v?0\.\d+",
    re.IGNORECASE,
)
FROZEN = "> Frozen record: not edited after its release."
APPENDED = (
    "> Frozen record of its release; the historical-context section at the end was appended "
    "at 0.36.0, when the reference pages stopped narrating versions, and is frozen too."
)
ASSEMBLED = "> Historical record assembled at 0.36.0 from the reference pages; frozen from now on."
# Classified from the DOC-C diff b656abbf..8a670a31, not from the banner under test.
RECORD_BANNERS = {
    "migrating-to-0.5.0.md": ASSEMBLED,
    "migrating-to-0.8.1.md": ASSEMBLED,
    "migrating-to-0.10.0.md": ASSEMBLED,
    "migrating-to-0.10.1.md": ASSEMBLED,
    "migrating-to-0.11.0.md": ASSEMBLED,
    "migrating-to-0.13.0.md": ASSEMBLED,
    "migrating-to-0.14.0.md": ASSEMBLED,
    "migrating-to-0.15.0.md": ASSEMBLED,
    "migrating-to-0.16.0.md": ASSEMBLED,
    "migrating-to-0.17.0.md": ASSEMBLED,
    "migrating-to-0.18.0.md": ASSEMBLED,
    "migrating-to-0.19.0.md": ASSEMBLED,
    "migrating-to-0.21.0.md": FROZEN,
    "migrating-to-0.22.0.md": APPENDED,
    "migrating-to-0.23.0.md": APPENDED,
    "migrating-to-0.24.0.md": FROZEN,
    "migrating-to-0.25.0.md": FROZEN,
    "migrating-to-0.26.0.md": FROZEN,
    "migrating-to-0.27.0.md": APPENDED,
    "migrating-to-0.28.0.md": FROZEN,
    "migrating-to-0.29.0.md": APPENDED,
    "migrating-to-0.30.0.md": FROZEN,
    "migrating-to-0.31.0.md": FROZEN,
    "migrating-to-0.32.0.md": FROZEN,
    "migrating-to-0.33.0.md": FROZEN,
    "migrating-to-0.33.1.md": FROZEN,
    "migrating-to-0.34.0.md": FROZEN,
    "migrating-to-0.35.0.md": FROZEN,
    "migrating-to-0.35.1.md": FROZEN,
    "migrating-to-0.36.0.md": FROZEN,
    "migrating-to-0.37.0.md": FROZEN,
    "release-notes.md": FROZEN,
}

# NFR-33 homes and heading anchors fixed by the session decisions.
TOPIC_HOMES = {
    "sync": ("storage-and-sync.md", "sync", ("sync-folders-and-matrix-homes.md",)),
    "archive and restore": (
        "restore-and-rebuild.md",
        "archive-and-restore",
        ("continuation-recovery.md", "pproc-artifact.md"),
    ),
    "saved simulation": (
        "continuation-recovery.md",
        "saved-simulation",
        ("mesh/how-to.md", "gui-to-pyfs.md"),
    ),
    "evidence discipline": ("srs/philosophy.md", "evidence-discipline", ("index.md",)),
    "rotor facts": (
        "mesh/reference.md",
        "the-four-rotor-facts-a-reference-artifact-once-carried",
        ("workflow-reference-artifact.md",),
    ),
    "entry pages": ("index.md", "where-to-start", ()),
}
DEFINING_SENTENCES = {
    "sync": (
        "Brings runs and results from the other workspaces named in "
        "inputs/sync-workspaces.toml into the main workspace."
    ),
    "archive and restore": (
        "A campaign workspace keeps its run records in runs.json, and a few files of "
        "the same nature beside it: the storage record storage_management.json, the "
        "additional-post record additional.json, and per matrix the products record "
        "post/<matrix>/products.json and the plan receipt post/<matrix>/plan.json."
    ),
    "saved simulation": (
        "The FlightStream scripting interface covers a subset of what the GUI can do."
    ),
    "evidence discipline": (
        "Nothing about the solver is asserted without a citation or a measurement."
    ),
    "rotor facts": (
        "The reference artifact refuses the retired fields rotation, blade_travel, "
        "rpm_sign_installed and rpm_sign_isolated."
    ),
    "entry pages": "Half an hour, and no solver until the last step.",
}


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


def one_home_problems(docs: Path) -> list[str]:
    problems = []
    bodies = {page: rendered(page.read_text("utf-8")) for page in docs.rglob("*.md")}

    def plain(body: str) -> str:
        return " ".join(html.unescape(re.sub(r"<[^>]+>", "", body)).split())

    for topic, (home, anchor, pointers) in TOPIC_HOMES.items():
        sentence = DEFINING_SENTENCES[topic]
        body = bodies[docs / home]
        section = re.search(rf'<h[1-6] id="{anchor}".*?</h[1-6]>(.*?)(?=<h[1-6]|\Z)', body, re.S)
        assert section, (topic, anchor)
        paragraph = re.search(r"<p>(.*?)</p>", section[1], re.S)
        assert paragraph and sentence in plain(paragraph[1]), topic
        for page, other_body in bodies.items():
            if page != docs / home and sentence in plain(other_body):
                problems.append(f"{topic}: duplicate in {page.relative_to(docs)}")
        for pointer in pointers:
            relative = Path(os.path.relpath(docs / home, (docs / pointer).parent)).as_posix()
            if f"{relative}#{anchor}" not in (docs / pointer).read_text("utf-8"):
                problems.append(f"{topic}: missing pointer in {pointer}")
    return problems


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
            family = f"definitions/{heading['slug']}.md"
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


def narrative_matches(docs: Path) -> list[tuple[str, str]]:
    return [
        (page.relative_to(docs).as_posix(), match[0])
        for page in docs.rglob("*.md")
        if not page.name.startswith("migrating-to-")
        and page.name not in {"release-notes.md", "upgrading.md"}
        for match in NARRATIVE.finditer(page.read_text("utf-8"))
    ]


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


def upgrading_problems(docs: Path) -> list[str]:
    records = sorted(docs.glob("migrating-to-*.md"))
    index = docs / "upgrading.md"
    if not index.is_file():
        return ["missing upgrading index"]
    links = re.findall(r"\]\((migrating-to-[^)]+\.md)\)", index.read_text("utf-8"))
    problems = (
        [] if sorted(links) == sorted(p.name for p in records) else ["migration index differs"]
    )
    for record in [*records, docs / "release-notes.md"]:
        banners = [
            line
            for line in record.read_text("utf-8").splitlines()
            if line.startswith(("> Frozen record", "> Historical record"))
        ]
        if banners != [RECORD_BANNERS.get(record.name)]:
            problems.append(f"incorrect frozen line: {record.name}")
    return problems


def test_one_home(tmp_path):
    """P0360-DOC-ONE-HOME (NFR-33): six homes and a planted duplicate of each."""
    assert len(TOPIC_HOMES) == 6
    assert TOPIC_HOMES.keys() == DEFINING_SENTENCES.keys()
    assert not one_home_problems(DOCS)
    sync = rendered((DOCS / "storage-and-sync.md").read_text("utf-8"))
    assert re.search(r'<h2 id="sync_1".*?</h2>\s*<p>See <a href="#sync">', sync)
    copied = tmp_path / "docs"
    shutil.copytree(DOCS, copied)
    for topic, sentence in DEFINING_SENTENCES.items():
        home, _, pointers = TOPIC_HOMES[topic]
        pointer = (
            pointers[0] if pointers else "index.md" if home != "index.md" else "getting-started.md"
        )
        page = copied / pointer
        original = page.read_text("utf-8")
        page.write_text(original + "\n\n" + html.escape(sentence) + "\n", "utf-8")
        assert any(p.startswith(f"{topic}: duplicate in") for p in one_home_problems(copied))
        page.write_text(original, "utf-8")


def test_definitions_split(tmp_path):
    """P0360-DOC-DEFINITIONS-SPLIT (NFR-34): all old slugs, families and unchanged pins."""
    assert len(FIXTURE["definitions"]) == 53
    assert not split_problems(DOCS, "post-processing-definitions.md", "definitions")
    expected = {
        h["slug"] + ".md"
        for h in FIXTURE["definitions"]
        if h["level"] == 2 and h["slug"] != "contents"
    }
    assert {p.name for p in (DOCS / "definitions").glob("*.md")} == expected
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
    assert len(FIXTURE["mesh"]) == 21
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


def test_narrative(tmp_path):
    """P0360-DOC-NARRATIVE (NFR-36): the exact regex, recursively, with both controls."""
    assert not narrative_matches(DOCS)
    (tmp_path / "migrating-to-0.1.0.md").write_text("Since 0.1.0, history lives here.", "utf-8")
    assert narrative_matches(tmp_path) == []
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "reference.md").write_text("Added in v0.1.0, a planted phrase.", "utf-8")
    assert narrative_matches(tmp_path) == [("nested/reference.md", "Added in v0.1")]


def test_upgrading(tmp_path):
    """P0360-DOC-UPGRADING (NFR-37): exact inventory and frozen record lines."""
    assert not upgrading_problems(DOCS)
    assert "upgrading.md" in (ROOT / "properdocs.yml").read_text("utf-8")
    copied = tmp_path / "docs"
    shutil.copytree(DOCS, copied)
    index = copied / "upgrading.md"
    text = index.read_text("utf-8")
    index.write_text(re.sub(r"\]\(migrating-to-[^)]+\.md\)", "]", text, count=1), "utf-8")
    assert "migration index differs" in upgrading_problems(copied)
    index.write_text(text, "utf-8")
    record = copied / "migrating-to-0.21.0.md"
    original = record.read_text("utf-8")
    record.write_text(original.replace(FROZEN, ""), "utf-8")
    assert upgrading_problems(copied) == [f"incorrect frozen line: {record.name}"]
    record.write_text(original, "utf-8")
    created = copied / "migrating-to-0.10.0.md"
    created.write_text(created.read_text("utf-8").replace(ASSEMBLED, FROZEN), "utf-8")
    assert upgrading_problems(copied) == [f"incorrect frozen line: {created.name}"]
