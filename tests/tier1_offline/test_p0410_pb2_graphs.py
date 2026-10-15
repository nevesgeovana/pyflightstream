"""Canonical graphs regenerate from SRS and source, with controlled drift."""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def generator():
    path = ROOT / "scripts/gen_canonical_graphs.py"
    assert path.is_file(), "canonical graph generator must exist"
    spec = importlib.util.spec_from_file_location("canonical_graphs", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("family", ["requirements", "library"])
def test_p0410_canonical_graph_bytes_and_planted_drift(family, tmp_path):
    gen = generator()
    artifacts = gen.generate(ROOT, family)
    assert artifacts, "every graph family has committed artifacts"
    assert gen.drift(ROOT, artifacts) == []
    for name, content in artifacts.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    assert gen.drift(tmp_path, artifacts) == []
    for name in artifacts:
        path = tmp_path / name
        original = path.read_bytes()
        path.write_bytes(original + b"planted drift")
        assert gen.drift(tmp_path, artifacts) == [name]
        path.write_bytes(original)


def test_p0410_requirements_parent_and_status_are_source_driven(tmp_path):
    gen = generator()
    source = tmp_path / "docs/unpublished/requirements"
    source.mkdir(parents=True)
    page = source / "functional-requirements.md"
    page.write_text(
        "| UID | Parent | Area | Status | Statement | Code | Test |\n"
        "| --- | --- | --- | --- | --- | --- | --- |\n"
        "| FR-1 | - | DOCS | implemented | Root | x:y | tests/x.py::test_x |\n"
        "| FR-2 | FR-1 | DOCS | pending | Child | x:y | tests/x.py::test_x |\n",
        encoding="utf-8",
    )
    before = gen.generate(tmp_path, "requirements")
    data = json.loads(before["docs/graphs/requirements.json"])
    assert data["nodes"][1]["parent"] == "FR-1"
    page.write_text(page.read_text().replace("pending", "implemented"), encoding="utf-8")
    assert gen.generate(tmp_path, "requirements") != before


def test_p0410_library_walker_includes_deferred_and_typing_edges():
    gen = generator()
    tree = gen.arch.Tree(
        {
            "__init__.py": "",
            "post/__init__.py": "",
            "versions.py": "",
            "commands/__init__.py": "",
            "post/sample.py": "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n"
            "    import pyflightstream.versions\ndef f():\n    import pyflightstream.commands\n",
        }
    )
    rows = {"post": 0, "commands": 5, "versions": 6}
    data = gen.module_data(tree, rows)
    edges = {(e["source"], e["target"], e["kind"]) for e in data["edges"]}
    assert ("pyflightstream.post.sample", "pyflightstream.versions", "typing") in edges
    assert ("pyflightstream.post.sample", "pyflightstream.commands", "deferred") in edges
    changed = tree.with_changes({"post/sample.py": "import pyflightstream.versions\n"})
    assert gen.module_data(changed, rows) != data
