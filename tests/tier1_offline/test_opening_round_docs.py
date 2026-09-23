"""The opening-round corrections keep current examples and historical reports distinct."""

import inspect
import os
import re
import subprocess
import tomllib
from pathlib import Path

import pytest

from pyflightstream.workspace import RunRecord
from pyflightstream.workspace.inputs import PprocArtifact

ROOT = Path(__file__).resolve().parents[2]


def test_concurrent_log_limit_is_registered_and_linked():
    report = "RPT-058_post-log-captures-warnings-process-wide_2026-09-23.md"
    path = ROOT / "reports" / report
    assert path.is_file(), "process-wide capture has no registered report"
    text = path.read_text(encoding="utf-8")
    assert "**Status:** REGISTERED for 0.27.0" in text
    assert "## What was measured" in text and "## Why it is not fixed here" in text
    # THE PAGE NAMES THE REPORT BY ID, `reports/RPT-058`, as it names every
    # report: a link to the reports tree is refused by the strict docs build
    # (the docs workflow on the v0.26.0 release commit). The CHANGELOG, which
    # is not built, may carry the file link.
    assert "reports/RPT-058" in (ROOT / "docs/post-processing-definitions.md").read_text(
        encoding="utf-8"
    )
    assert report in (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "report",
    [
        "RPT-055_partial-residual-anchor_2026-09-22.md",
        "RPT-057_freeze-check-architecture_2026-09-22.md",
    ],
)
def test_report_keeps_original_body_and_appends_closure(report):
    old = subprocess.run(
        [
            "git",
            "-c",
            f"safe.directory={ROOT.as_posix()}",
            "show",
            f"v0.25.1:reports/{report}",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        # AN EXPLICIT ENVIRONMENT, as every spawn under tests passes one: the
        # repository guard pins the count of spawns that inherit the whole one.
        env={
            "PATH": os.environ.get("PATH", ""),
            "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
            "HOME": os.environ.get("HOME", os.environ.get("USERPROFILE", "")),
        },
        encoding="utf-8",
        check=True,
    ).stdout
    text = (ROOT / "reports" / report).read_text(encoding="utf-8")
    assert text.startswith(old), "the original report was changed in place"
    closure = text[len(old) :]
    assert "## CLOSED in 0.26.0, 2026-09-23" in closure
    assert "**Status:** CLOSED in 0.26.0" in closure
    assert re.findall(r"^\*\*Status:\*\* (.*)$", text, re.M)[-1] == "CLOSED in 0.26.0"


def test_reference_mismatch_points_to_the_default_policy():
    text = (ROOT / "docs/post-processing-definitions.md").read_text(encoding="utf-8")
    paragraph = text.split("**`SREF` and `CREF` are checked against the export.**")[1].split(
        "\n\n"
    )[0]
    assert "check_frozen=True" in paragraph and "warn" in paragraph
    assert "#the-post-log-and-the-default-warning-rule-since-0260" in paragraph


def test_empty_group_migration_checks_alias_collision():
    text = (ROOT / "docs/migrating-to-0.26.0.md").read_text(encoding="utf-8")
    section = text.split("## 6. A pproc group names one alias")[1].split("\n## ")[0]
    assert "rg -n" in section and "all" in section and "[aliases]" in section
    assert "unique alias" in section and "precedence" in section


def test_current_group_examples_and_docstring_use_one_alias():
    text = (ROOT / "docs/workspace-and-workflows.md").read_text(encoding="utf-8")
    for block in re.findall(r"```toml\n(.*?)```", text, re.S):
        if "[groups]" in block:
            groups = tomllib.loads(block)["groups"]
            assert all(isinstance(value, str) for value in groups.values()), groups
            PprocArtifact.model_validate({"groups": groups})
    assert 'wing = ["wing_left", "wing_right"]' not in text
    assert "the empty list still binds" not in text
    doc = inspect.getdoc(PprocArtifact)
    assert "1-based indices" not in doc
    assert '>>> PprocArtifact(groups={"TOTAL": "all"}).groups' in doc


def test_manifest_census_has_one_home():
    doc = inspect.getdoc(RunRecord._take_the_earlier_name_of_the_waived_commands)
    assert "CHANGELOG" in doc and "0.26.0" in doc
    assert "46" not in doc and "74" not in doc
