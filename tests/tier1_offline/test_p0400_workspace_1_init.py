"""P0400-WSINIT: staging, collection and archiving of `CampaignWorkspace` (0.40.0 lane workspace-1).

Each test is the regression of one planning node and fails on the code before its fix.
"""

from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

import pytest

import pyflightstream.workspace as workspace_module
from pyflightstream.workspace import CampaignWorkspace, PointName, WorkspaceError, _is_link
from tests.tier1_offline.test_workspace import make_record


def _geometry(workspace: CampaignWorkspace, folder: str, name: str) -> Path:
    path = workspace.inputs_dir / "geometries" / folder / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"fake simulation " + name.encode())
    return path


def test_p0400_wsinit_a_dangling_inputs_link_is_replaced_by_the_next_staging(tmp_path):
    """P0400-WSINIT (PFS-2095.056): the staged link's target is gone; staging again relinks."""
    workspace = CampaignWorkspace.init(tmp_path / "camp")
    wing = _geometry(workspace, "wing", "wing.fsm")
    workspace.stage_inputs("9001", [wing])
    inputs = workspace.sim_dir("9001") / "inputs"
    assert _is_link(inputs)
    shutil.rmtree(wing.parent)
    tail = _geometry(workspace, "tail", "tail.fsm")
    workspace.stage_inputs("9001", [tail])
    assert _is_link(inputs) and (inputs / "tail.fsm").is_file()
    assert workspace.staged_as("9001") == ("link", None)


def test_p0400_wsinit_create_sim_keeps_a_dangling_inputs_link(tmp_path):
    """P0400-WSINIT (PFS-2095.056): a script is written into a simulation with a dangling link."""
    workspace = CampaignWorkspace.init(tmp_path / "camp")
    wing = _geometry(workspace, "wing", "wing.fsm")
    workspace.stage_inputs("9001", [wing])
    shutil.rmtree(wing.parent)
    workspace.write_script("9001", "point.txt", "START_SOLVER\n")
    assert (workspace.sim_dir("9001") / "scripts" / "point.txt").is_file()


def _refuse_removal(monkeypatch) -> None:
    def held(link: Path) -> None:
        raise PermissionError(5, "Access is denied", str(link))

    monkeypatch.setattr(workspace_module, "_remove_link", held)


def test_p0400_wsinit_a_link_that_cannot_be_retargeted_is_a_reason_and_copies_nothing(
    tmp_path, monkeypatch
):
    """P0400-WSINIT (PFS-2095.062): a refused removal of a link to another geometry is named."""
    workspace = CampaignWorkspace.init(tmp_path / "camp")
    wing = _geometry(workspace, "wing", "wing.fsm")
    workspace.stage_inputs("9001", [wing])
    tail = _geometry(workspace, "tail", "tail.fsm")
    _refuse_removal(monkeypatch)
    inputs = workspace.sim_dir("9001") / "inputs"
    mode, reason = workspace._link_inputs(inputs, [tail])
    assert mode == "copy" and "Access is denied" in str(reason), (mode, reason)
    with pytest.raises(WorkspaceError, match="no input was copied"):
        workspace.stage_inputs("9001", [tail])
    assert not (wing.parent / "tail.fsm").exists()


def test_p0400_wsinit_a_link_that_cannot_be_removed_for_copies_is_a_reason(tmp_path, monkeypatch):
    """P0400-WSINIT (PFS-2095.062): sources outside the library and a refused removal are named."""
    workspace = CampaignWorkspace.init(tmp_path / "camp")
    wing = _geometry(workspace, "wing", "wing.fsm")
    workspace.stage_inputs("9001", [wing])
    outside = tmp_path / "outside.fsm"
    outside.write_bytes(b"outside")
    _refuse_removal(monkeypatch)
    inputs = workspace.sim_dir("9001") / "inputs"
    mode, reason = workspace._link_inputs(inputs, [outside])
    assert mode == "copy" and "Access is denied" in str(reason), (mode, reason)
    with pytest.raises(WorkspaceError, match="no input was copied"):
        workspace.stage_inputs("9001", [outside])
    assert not (wing.parent / "outside.fsm").exists()


def test_p0400_wsinit_collect_names_moves_and_records_by_collection_name(tmp_path, monkeypatch):
    """P0400-WSINIT (PFS-2094.042): the held check, the move and the record take one rule."""
    workspace = CampaignWorkspace(tmp_path / "camp")
    produced = tmp_path / "loads.txt"
    produced.write_text("x", encoding="utf-8")
    rule = workspace_module.collection_name
    monkeypatch.setattr(workspace_module, "collection_name", lambda path: "ruled_" + rule(path))
    collected = workspace.collect_outputs("9001", [produced], datapoint=PointName("AL+000"))
    assert collected == ["datapoints/DP-AL+000/ruled_loads.txt"]
    folder = workspace.sim_dir("9001") / "datapoints" / "DP-AL+000"
    assert (folder / "ruled_loads.txt").is_file()
    produced.write_text("y", encoding="utf-8")
    with pytest.raises(WorkspaceError, match="cannot collect ruled_loads.txt"):
        workspace.collect_outputs("9001", [produced], datapoint=PointName("AL+000"))


def test_p0400_wsinit_a_failed_archive_leaves_no_fragment_and_a_retry_succeeds(
    tmp_path, monkeypatch
):
    """P0400-WSINIT (PFS-2096.010): a write that fails leaves no zip, and the retry archives."""
    workspace = CampaignWorkspace(tmp_path)
    workspace.write_script("9001", "point.txt", "START_SOLVER\n")
    workspace.write_script("9001", "other.txt", "START_SOLVER\n")
    workspace.append_record(make_record())
    real_write = zipfile.ZipFile.write
    calls = {"n": 0}

    def failing(self, filename, *args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 2:
            raise PermissionError(13, "held by another process", str(filename))
        return real_write(self, filename, *args, **kwargs)

    monkeypatch.setattr(zipfile.ZipFile, "write", failing)
    with pytest.raises(WorkspaceError, match="No archive was written"):
        workspace.archive_sim("9001")
    assert list((tmp_path / "archive").iterdir()) == []
    assert (tmp_path / "sims" / "sim_9001" / "scripts" / "point.txt").is_file()
    monkeypatch.setattr(zipfile.ZipFile, "write", real_write)
    bundle = workspace.archive_sim("9001")
    with zipfile.ZipFile(bundle) as archive:
        assert "scripts/point.txt" in archive.namelist()
