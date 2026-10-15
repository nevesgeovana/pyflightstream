"""P0420: failed build(output) exposes the TeX cause before temporary cleanup."""

import importlib.util
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
    assert triggers["workflow_dispatch"] is None
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


# A version tag deploys; a manual dispatch deploys only from main (owner decision of
# 2026-10-15: the 0.41.0 site is published from main). A branch push never deploys.
DEPLOY_IF = (
    "startsWith(github.ref, 'refs/tags/v') || "
    "(github.event_name == 'workflow_dispatch' && github.ref == 'refs/heads/main')"
)


def test_p0410_docs_deploy_only_on_version_tags():
    root = Path(__file__).resolve().parents[2] / ".github/workflows"
    docs = yaml.safe_load((root / "docs.yml").read_text("utf-8"))
    triggers = docs.get("on", docs.get(True))
    assert triggers == {"workflow_dispatch": None, "push": {"tags": ["v*"]}}
    assert docs["jobs"]["deploy"]["if"] == DEPLOY_IF
    ci = yaml.safe_load((root / "ci.yml").read_text("utf-8"))
    assert any(
        step.get("run") == "properdocs build --strict" for step in ci["jobs"]["docs"]["steps"]
    )
