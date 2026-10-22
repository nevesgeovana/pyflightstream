"""P0420: failed build(output) exposes the TeX cause before temporary cleanup."""

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("failure", ["compiler", "layout", "missing-log"])
def test_p0420_docs_diag_failure_context(tmp_path, monkeypatch, capsys, failure):
    spec = importlib.util.spec_from_file_location("build_guides", ROOT / "scripts/build_guides.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    source = tmp_path / "repo"
    guide = source / "guide/latex-sources/01-example/main.tex"
    guide.parent.mkdir(parents=True)
    guide.write_text("source", encoding="utf-8")
    monkeypatch.setattr(module, "ROOT", source)
    monkeypatch.setattr(module.shutil, "which", lambda _: "pdflatex")
    monkeypatch.setattr(
        module.subprocess,
        "check_output",
        lambda command, **kwargs: (
            "TeX Live" if "--version" in command else "guide/latex-sources/01-example/main.tex"
        ),
    )
    output = tmp_path / "build/guides"
    lines = ["preamble", "! first error", *[f"context {i}" for i in range(10)]]
    lines += ["outside excerpt", *[f"tail {i}" for i in range(80)]]
    if failure == "layout":
        lines[1] = "Overfull box"

    def run(command, **kwargs):
        if command[0] != "pdflatex":
            return subprocess.CompletedProcess(command, 0)
        if failure != "missing-log":
            (output / "pyfts-guide-01-example.log").write_text("\n".join(lines), encoding="utf-8")
        return subprocess.CompletedProcess(command, 0 if failure == "layout" else 1)

    monkeypatch.setattr(module.subprocess, "run", run)
    with pytest.raises(RuntimeError, match="Guide"):
        module.build(output)
    stderr = capsys.readouterr().err
    if failure == "missing-log":
        assert "log unavailable" in stderr
    else:
        assert "\n".join(lines[-80:]) in stderr
        assert "outside excerpt" not in stderr
        if failure == "compiler":
            assert "\n".join(lines[1:12]) in stderr


def test_p0420_docs_diag_manual_build_and_failure_artifact():
    workflow = yaml.safe_load((ROOT / ".github/workflows/docs.yml").read_text("utf-8"))
    triggers = workflow.get("on", workflow.get(True))
    assert "workflow_dispatch" in triggers
    deploy = triggers["workflow_dispatch"]["inputs"]["deploy"]
    assert deploy["type"] == "boolean" and deploy["default"] is False
    assert triggers["push"] == {"tags": ["v*"]}
    steps = workflow["jobs"]["build"]["steps"]
    uploads = [
        step for step in steps if step.get("uses", "").startswith("actions/upload-artifact@")
    ]
    failed = [step for step in uploads if step.get("if") == "failure()"]
    assert len(failed) == 1
    assert failed[0]["with"]["path"] == "build/guides/*.log"
    assert failed[0]["uses"] == uploads[0]["uses"]
    assert workflow["jobs"]["deploy"]["if"] == DEPLOY_IF


# A version tag deploys. A manual dispatch is the pre-tag Linux build and deploys only
# from main with deploy=true (owner decision of 2026-10-15: the 0.41.0 site is published
# from main). A branch push never deploys.
# F-702 (0.43.0): the tag arm requires a push event, so a dispatch started on a v* tag
# deploys only through the dispatch arm, with inputs.deploy.
DEPLOY_IF = (
    "(github.event_name == 'push' && startsWith(github.ref, 'refs/tags/v')) || "
    "(github.event_name == 'workflow_dispatch' && github.ref == 'refs/heads/main' && inputs.deploy)"
)


def test_p0410_docs_deploy_only_on_version_tags():
    root = Path(__file__).resolve().parents[2] / ".github/workflows"
    docs = yaml.safe_load((root / "docs.yml").read_text("utf-8"))
    triggers = docs.get("on", docs.get(True))
    assert set(triggers) == {"workflow_dispatch", "push"}
    assert triggers["push"] == {"tags": ["v*"]}
    assert docs["jobs"]["deploy"]["if"] == DEPLOY_IF
    ci = yaml.safe_load((root / "ci.yml").read_text("utf-8"))
    assert any(
        step.get("run") == "properdocs build --strict" for step in ci["jobs"]["docs"]["steps"]
    )


def _load_script(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _built_site(folder: Path, label: str) -> Path:
    """A built site as the docs build leaves it: pages with a body, at two depths."""
    (folder / "guide").mkdir(parents=True)
    for page in (folder / "index.html", folder / "guide" / "index.html"):
        page.write_text(
            f'<!doctype html><html><body dir="ltr"><p>{label}</p></body></html>\n',
            encoding="utf-8",
        )
    return folder


@pytest.mark.requirement("FR-2307")
def test_p0430_two_editions_stay_published_with_a_selector_and_a_warning(tmp_path):
    """Two releases and main published in turn: each is addressable, listed and labelled."""
    module = _load_script("publish_doc_editions")
    editions = tmp_path / "editions"
    base = "/pyflightstream/"
    for version, aliases in (("0.42.0", ["latest"]), ("0.43.0", ["latest"]), ("main", [])):
        site = _built_site(tmp_path / f"site-{version}", f"edition {version}")
        module.assemble_edition(site, editions, version, aliases=aliases, base=base)
    listed = json.loads((editions / "versions.json").read_text(encoding="utf-8"))
    assert [entry["version"] for entry in listed] == ["main", "0.43.0", "0.42.0"]
    assert [entry["aliases"] for entry in listed] == [[], ["latest"], []]

    def page(*parts: str) -> str:
        return (editions.joinpath(*parts)).read_text(encoding="utf-8")

    # Every edition answers at its own address, and latest is the newest release.
    assert "edition 0.42.0" in page("0.42.0", "guide", "index.html")
    assert "edition 0.43.0" in page("latest", "guide", "index.html")
    # The default edition carries no banner; every other one does, on every page, once.
    for folder in ("0.43.0", "latest"):
        assert module.BANNER_ID not in page(folder, "guide", "index.html")
    for folder, words in (("0.42.0", "pyflightstream 0.42.0"), ("main", "unreleased main")):
        text = page(folder, "guide", "index.html")
        assert text.count(module.BANNER_ID) == 1 and words in text
        assert f'href="{base}latest/"' in text
    # A reader without an edition goes to latest, and an unversioned path to its page there.
    assert f"url={base}latest/" in page("index.html")
    missing = page("404.html")
    assert '["0.42.0", "0.43.0", "latest", "main"]' in missing and '"latest"' in missing
    # Publishing an edition again replaces it and never stacks a second banner.
    site = _built_site(tmp_path / "again", "edition 0.42.0 rebuilt")
    module.assemble_edition(site, editions, "0.42.0", base=base)
    assert page("0.42.0", "index.html").count(module.BANNER_ID) == 1
    assert "rebuilt" in page("0.42.0", "index.html")


@pytest.mark.requirement("FR-2307")
@pytest.mark.parametrize(
    ("version", "aliases", "base"),
    [("v0.43.0", [], "/"), ("0.43.0", ["0.42.0"], "/"), ("0.43.0", [], "pyflightstream")],
)
def test_p0430_an_edition_it_cannot_publish_is_refused_before_anything_is_written(
    tmp_path, version, aliases, base
):
    module = _load_script("publish_doc_editions")
    site = _built_site(tmp_path / "site", "edition")
    with pytest.raises(ValueError):
        module.assemble_edition(site, tmp_path / "editions", version, aliases=aliases, base=base)
    assert not (tmp_path / "editions").exists()


@pytest.mark.requirement("FR-2307")
def test_p0430_a_tag_publishes_its_edition_through_the_editions_branch():
    workflow = yaml.safe_load((ROOT / ".github/workflows/docs.yml").read_text("utf-8"))
    jobs = workflow["jobs"]
    editions = jobs["editions"]
    assert editions["if"] == DEPLOY_IF and editions["needs"] == "build"
    assert editions["permissions"] == {"contents": "write"}
    assert jobs["deploy"]["needs"] == "editions"
    for name, job in jobs.items():
        if name != "editions":
            assert job.get("permissions", {}).get("contents") in (None, "read"), name
    script = "\n".join(step.get("run", "") for step in editions["steps"])
    assert "publish_doc_editions.py" in script and "--alias latest" in script
    assert "HEAD:docs-editions" in script
    assert any(
        step.get("uses", "").startswith("actions/upload-pages-artifact@")
        and step["with"]["path"] == "editions"
        for step in editions["steps"]
    )
    config = _properdocs_config()
    assert config["extra"]["version"] == {"provider": "mike", "default": "latest"}


def _properdocs_config() -> dict:
    class _Loader(yaml.SafeLoader):
        pass

    _Loader.add_multi_constructor("", lambda loader, suffix, node: None)
    return yaml.load((ROOT / "properdocs.yml").read_text(encoding="utf-8"), Loader=_Loader)


@pytest.mark.requirement("FR-2331")
def test_p0430_the_offline_edition_reads_its_views_without_a_server(monkeypatch):
    """Built with page.html links, its views load data and code as classic scripts."""
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    workflow = yaml.safe_load((ROOT / ".github/workflows/docs.yml").read_text("utf-8"))
    build = "\n".join(step.get("run", "") for step in workflow["jobs"]["build"]["steps"])
    assert "properdocs build --strict --no-directory-urls" in build
    assert "site/downloads/pyflightstream-docs-offline.zip" in build
    assert 'gen_understanding_data.py --data-only --revision "$GITHUB_SHA"' in build
    assets = ROOT / "docs/understanding/assets"
    for name in ("understanding.js", "requirements-tree.js", "code-view.js"):
        text = (assets / name).read_text(encoding="utf-8")
        # A page opened from a folder may not fetch() or import a module.
        assert "fetch(" not in text and "import(" not in text and "export " not in text, name
    controller = (assets / "understanding.js").read_text(encoding="utf-8")
    assert '".html"' in controller and 'data/" + name + ".js"' in controller
    module = _load_script("gen_understanding_data")
    text = json.dumps({"schema_version": 1, "nodes": ["FR-1"]}, indent=2) + "\n"
    name, body = module.script_twin("requirements.json", text)
    assert name == "requirements.js"
    registry = f"window.{module.SCRIPT_GLOBAL}"
    prefix = f'({registry} = {registry} || {{}})["requirements"] = '
    assert body.startswith(prefix) and body.endswith(";\n")
    assert json.loads(body[len(prefix) : -2]) == json.loads(text)
