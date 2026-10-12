"""Tier 1, 0.40.0 lane run-2: ``pyfs-matrix rename``, the move to the 0.21.0 names.

The workspaces are the real ones of the GOAL-024 rename tests: a matrix run
through the campaign loop and written back into the 0.20.x shape.
"""

from __future__ import annotations

from pyflightstream.run import records
from pyflightstream.run import rename as rename_module
from pyflightstream.run.rename import rename_workspace
from tests.tier1_offline.test_goal024_rename_command import _as_0_20, _ran, _reopened


def test_p0400_rename_archives_in_local_time_so_restore_takes_the_newest(tmp_path, monkeypatch):
    """P0400-RENAME-ARCHIVE (PFS-2096.008, PFS-2096.006): rename stamps as every archiver does.

    A UTC stamp sorted against the local stamps of the other archivers, so a
    later mark-failed copy lost to the rename's as the newest. The stamps are
    pinned to one moment in 2000; a UTC stamp of the real clock sorts after
    both of them.
    """
    workspace, _, _ = _ran(tmp_path)
    _as_0_20(workspace, mach=0.2)
    monkeypatch.setattr(rename_module, "_now_stamp", lambda: "20000101-000000", raising=False)
    monkeypatch.setattr(records, "_now_stamp", lambda: "20000101-000001")
    rename_workspace(_reopened(workspace))
    renamed = workspace.manifest_path.read_bytes()
    records.mark_failed(workspace.root, ["3207"], reason="wrong mesh", apply=True)
    archive = workspace.root / "archive"
    assert (archive / "runs-20000101-000000.json").is_file()
    entry = records.restore(workspace.root, "runs")
    assert entry["source"] == "archive/runs-20000101-000001.json", entry["source"]
    assert (workspace.root / entry["source"]).read_bytes() == renamed
