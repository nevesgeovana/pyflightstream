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


def _workflow(name: str) -> dict:
    return yaml.safe_load((ROOT / ".github/workflows" / name).read_text("utf-8"))


@pytest.mark.requirement("FR-2307")
def test_p0430_each_release_carries_its_own_documentation_edition():
    """The release workflow builds the tag's documentation as one zip, granting nothing new."""
    release = _workflow("release.yml")
    job = release["jobs"]["docs-edition"]
    assert "permissions" not in job and release["permissions"] == {"contents": "read"}
    steps = "\n".join(step.get("run", "") for step in job["steps"])
    assert 'EDITION="pyflightstream-docs-$VERSION"' in steps
    assert 'zip -qr "$EDITION.zip" "$EDITION"' in steps
    uploads = [step for step in job["steps"] if step.get("uses", "").startswith("actions/upload")]
    assert [step["with"]["path"] for step in uploads] == ["build/${{ env.EDITION }}.zip"]
    # Publishing does not wait on the documentation.
    assert "docs-edition" not in release["jobs"]["publish"]["needs"]
    # No workflow job may write the repository: the editions live in release assets.
    for name in ("docs.yml", "release.yml", "ci.yml"):
        workflow = _workflow(name)
        assert workflow.get("permissions", {}).get("contents") in (None, "read"), name
        for job_name, body in workflow["jobs"].items():
            granted = body.get("permissions", {})
            assert granted.get("contents") in (None, "read"), (name, job_name)
    assert _workflow("docs.yml")["jobs"]["deploy"]["needs"] == "build"


@pytest.mark.requirement("FR-2331")
def test_p0430_the_offline_edition_reads_its_views_without_a_server(monkeypatch):
    """Built with page.html links, its views load data and code as classic scripts."""
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    job = _workflow("release.yml")["jobs"]["docs-edition"]
    build = "\n".join(step.get("run", "") for step in job["steps"])
    assert 'properdocs build --strict --no-directory-urls --site-dir "build/$EDITION"' in build
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
