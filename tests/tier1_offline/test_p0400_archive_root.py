"""P0400-ARCHROOT (PFS-2089.004): archive selects the campaign like its siblings.

Usage: pyfs-workspace archive 9001 --workspace campaign
Compatibility: pyfs-workspace archive campaign 9001
"""

from pathlib import Path
from zipfile import ZipFile

import pytest

import pyflightstream
from pyflightstream._errors import PyflightstreamWarning
from pyflightstream.workspace import CampaignWorkspace, RunRecord, RunStatus
from pyflightstream.workspace.cli import main

pytestmark = pytest.mark.requirement("P0400-ARCHROOT")


def recorded_campaign(root: Path, content: str) -> Path:
    workspace = CampaignWorkspace.init(root)
    script, _ = workspace.write_script("9001", "point.txt", content)
    workspace.append_record(
        RunRecord(
            run_id="campaign/sim_9001/a",
            sim_id="9001",
            point={"alpha": 0.0},
            fs_version_requested="26.120",
            package_version=pyflightstream.__version__,
            script_sha256="0" * 64,
            raw_flag=False,
            status=RunStatus.CONVERGED,
        )
    )
    return script


def assert_archived(root: Path, content: str) -> None:
    with ZipFile(root / "archive" / "sim_9001.zip") as bundle:
        assert bundle.read("scripts/point.txt").decode() == content
    assert not (root / "sims" / "sim_9001").exists()


@pytest.mark.parametrize("option_first", [False, True])
def test_named_workspace_archives_only_the_selected_campaign(tmp_path, monkeypatch, option_first):
    """The same simulation in the current directory stays untouched."""
    selected, current = tmp_path / "selected", tmp_path / "current"
    recorded_campaign(selected, "selected\n")
    untouched = recorded_campaign(current, "current\n")
    monkeypatch.chdir(current)
    option = ["--workspace", str(selected)]
    argv = ["archive", *(option + ["9001"] if option_first else ["9001"] + option)]
    try:
        result = main(argv)
    except SystemExit as error:
        result = error.code
    assert result == 0
    assert_archived(selected, "selected\n")
    assert untouched.read_text(encoding="utf-8") == "current\n"
    assert not (current / "archive" / "sim_9001.zip").exists()


@pytest.mark.parametrize("relative", [False, True])
def test_legacy_positional_archives_and_warns(tmp_path, monkeypatch, relative):
    recorded_campaign(tmp_path, "legacy\n")
    monkeypatch.chdir(tmp_path)
    root = "." if relative else str(tmp_path)
    with pytest.warns(
        PyflightstreamWarning, match="positional root.*deprecated.*--workspace"
    ) as caught:
        assert main(["archive", root, "9001"]) == 0
    assert len(caught) == 1
    assert_archived(tmp_path, "legacy\n")


def test_archive_defaults_to_the_current_campaign(tmp_path, monkeypatch):
    recorded_campaign(tmp_path, "current\n")
    monkeypatch.chdir(tmp_path)
    assert main(["archive", "9001"]) == 0
    assert_archived(tmp_path, "current\n")


def test_different_campaign_names_are_refused_without_archiving(tmp_path, capsys):
    first, second = tmp_path / "first", tmp_path / "second"
    scripts = [recorded_campaign(first, "first\n"), recorded_campaign(second, "second\n")]
    assert main(["archive", str(first), "9001", "--workspace", str(second)]) == 2
    assert "named twice" in capsys.readouterr().err
    assert all(script.is_file() for script in scripts)
    assert not list(tmp_path.glob("*/archive/*.zip"))


def test_identical_campaign_names_keep_the_legacy_call_working(tmp_path):
    recorded_campaign(tmp_path, "same\n")
    with pytest.warns(PyflightstreamWarning, match="positional root.*deprecated"):
        assert main(["archive", str(tmp_path), "9001", "--workspace", str(tmp_path)]) == 0
    assert_archived(tmp_path, "same\n")
