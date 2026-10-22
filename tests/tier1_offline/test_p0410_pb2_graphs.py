"""Canonical graphs regenerate from SRS and source, with controlled drift."""

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_p0420_doc_charts_ship_pinned_local_libraries():
    """PFS-2143: charts load licensed, hash-pinned libraries without a CDN."""
    import yaml

    vendor = ROOT / "docs/understanding/assets/vendor"
    manifest = vendor / "VERSIONS.json"
    assert manifest.is_file(), "Chart libraries need a version and hash manifest"
    records = json.loads(manifest.read_text(encoding="utf-8"))["files"]
    expected = {"cytoscape.min.js": "MIT", "d3.min.js": "ISC", "d3-sankey.min.js": "BSD-3-Clause"}
    assert set(records) == set(expected)
    licenses = (vendor / "LICENSES.txt").read_bytes()
    config = yaml.safe_load((ROOT / "properdocs.yml").read_text(encoding="utf-8"))
    scripts = config["extra_javascript"]
    controller = scripts.index("understanding/assets/understanding.js")
    for name, license_id in expected.items():
        record = records[name]
        assert record["license"] == license_id
        assert record["version"] and "latest" not in record["source_url"]
        assert record["source_url"].startswith("https://registry.npmjs.org/")
        assert hashlib.sha256((vendor / name).read_bytes()).hexdigest() == record["sha256"]
        payload = (vendor / name).read_bytes()
        if name == "cytoscape.min.js":
            assert chr(0x200B).encode() not in payload
            assert payload.count(b'.join("\\u200b")') == 1
            upstream = payload.replace(
                b'.join("\\u200b")', b'.join("' + chr(0x200B).encode() + b'")'
            )
            assert hashlib.sha256(upstream).hexdigest() == record["upstream_sha256"]
            assert record["transformation"]
        else:
            assert record["upstream_sha256"] == record["sha256"]
            assert record["transformation"] is None
        assert record["license_text"].encode("utf-8") in licenses
        assert scripts.index("understanding/assets/vendor/" + name) < controller
    assert scripts.index("understanding/assets/vendor/d3.min.js") < scripts.index(
        "understanding/assets/vendor/d3-sankey.min.js"
    )
    assert all("://" not in script for script in scripts)
    assert not (ROOT / "properdocs.D.yml").exists()


def test_p0430_the_data_flow_digest_is_the_source_text_not_an_interpreter_rendering():
    """RB8-08: a stage's source_sha256 is the digest of its source text.

    It was the digest of ast.unparse, whose rendering of an f-string with a quoted
    replacement field differs between 3.12 patch releases, so a graph generated on 3.12.0
    drifted on CI's 3.12.15 with no source change.
    """
    import ast

    data = json.loads((ROOT / "docs/graphs/data-flow.json").read_text(encoding="utf-8"))
    for stage in data["stages"]:
        text = (ROOT / "src/pyflightstream" / stage["source"]).read_text(encoding="utf-8")
        function = next(
            node
            for node in ast.parse(text).body
            if isinstance(node, ast.FunctionDef) and node.name == stage["symbol"]
        )
        source = ast.get_source_segment(text, function) or ""
        assert stage["source_sha256"] == hashlib.sha256(source.encode()).hexdigest(), stage["id"]


def test_p0420_doc_understanding_reads_approved_stages():
    """PFS-2143: the view consumes phase-S areas, parents and trace anchors."""
    import yaml

    sys.path.insert(0, str(ROOT / "scripts"))
    failure = None
    try:
        import gen_understanding_data as understanding

        data = understanding.generate()
    except (ValueError, KeyError) as error:
        failure = str(error)
    assert failure is None, failure
    areas = yaml.safe_load((ROOT / "docs/srs/areas.yaml").read_text())
    assert {s["id"] for s in data["mission.json"]["stages"]} == set(areas["stages"])
    rows = data["requirements.json"]["nodes"]
    assert {r["level"] for r in rows if r["status"] != "retired"} >= {"L1", "L2", "L3"}
    assert all(r["source"]["line"] > 0 for r in rows)
    assert all(r["stage"] in {*areas["stages"], "nfr"} for r in rows)


def test_p0430_understanding_check_can_fail_after_the_ci_write(tmp_path, monkeypatch):
    """X-F-0468: CI writes the Understanding data, then checks; the check must be able to fail.

    The workflows ran the generator, which rewrote the committed generated regions, and then
    --check, which therefore could not fail. They now write with --data-only, which leaves
    the committed regions as they are, so a stale region is caught by the check after it.
    """
    for workflow in (".github/workflows/docs.yml", ".github/workflows/ci.yml"):
        calls = [
            line
            for line in (ROOT / workflow).read_text(encoding="utf-8").splitlines()
            if "gen_understanding_data.py" in line
        ]
        assert calls, workflow
        assert all("--check" in line or "--data-only" in line for line in calls), workflow
        assert any("--check" in line for line in calls), workflow
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    import gen_understanding_data as understanding

    payloads = understanding.generate("0" * 40)
    for relative in ("docs/workspace-files.md", "docs/understanding/execution.md"):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        text = (ROOT / relative).read_text(encoding="utf-8")
        target.write_text(text.replace("<!-- END ", "stale row\n<!-- END ", 1), encoding="utf-8")
    stale = (tmp_path / "docs/workspace-files.md").read_text(encoding="utf-8")
    monkeypatch.setattr(understanding, "ROOT", tmp_path)
    monkeypatch.setattr(understanding, "OUT", tmp_path / "docs/understanding/data")
    monkeypatch.setattr(understanding, "generate", lambda revision: payloads)
    monkeypatch.setattr(sys, "argv", ["gen_understanding_data.py", "--data-only"])
    understanding.main()
    assert (tmp_path / "docs/workspace-files.md").read_text(encoding="utf-8") == stale
    monkeypatch.setattr(sys, "argv", ["gen_understanding_data.py", "--check"])
    with pytest.raises(SystemExit, match="Stale Understanding data: docs/workspace-files.md"):
        understanding.main()


def generator():
    path = ROOT / "scripts/gen_canonical_graphs.py"
    assert path.is_file(), "canonical graph generator must exist"
    spec = importlib.util.spec_from_file_location("canonical_graphs", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("family", ["requirements", "library", "data-flow"])
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


def test_p0410_flow_edges_follow_declared_inputs_outputs(tmp_path):
    import shutil

    gen = generator()
    declaration = json.loads((ROOT / "scripts/pipeline_graph.json").read_text())
    (tmp_path / "scripts").mkdir()
    for stage in declaration["stages"]:
        relative = "src/pyflightstream/" + stage["source"]
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
    for case in declaration["cases"]:
        for route in ("workspace", "api"):
            target = tmp_path / case[route]
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / case[route], target)
    path = tmp_path / "scripts/pipeline_graph.json"
    path.write_text(json.dumps(declaration))
    before = gen.flow_data(tmp_path)
    assert {"source": "matrix", "target": "resolve", "artifact": "matrix rows"} in before["edges"]
    declaration["stages"][1]["inputs"].remove("matrix rows")
    path.write_text(json.dumps(declaration))
    after = gen.flow_data(tmp_path)
    assert before != after
    assert not any(e["source"] == "matrix" for e in after["edges"])
    source = tmp_path / "src/pyflightstream/cases/matrix.py"
    source.write_text(
        source.read_text().replace("active_only: bool = True", "active_only: bool = False")
    )
    assert gen.flow_data(tmp_path) != after


def test_p0430_a_repeated_data_flow_case_id_is_refused(tmp_path):
    """F-848: two data-flow cases with one id would write one SVG over the other."""
    import shutil

    gen = generator()
    declaration = json.loads((ROOT / "scripts/pipeline_graph.json").read_text())
    (tmp_path / "scripts").mkdir()
    for stage in declaration["stages"]:
        relative = "src/pyflightstream/" + stage["source"]
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
    for case in declaration["cases"]:
        for route in ("workspace", "api"):
            target = tmp_path / case[route]
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / case[route], target)
    declaration["cases"].append(dict(declaration["cases"][0]))
    (tmp_path / "scripts/pipeline_graph.json").write_text(json.dumps(declaration))
    with pytest.raises(ValueError, match="duplicate data-flow case id"):
        gen.flow_data(tmp_path)
