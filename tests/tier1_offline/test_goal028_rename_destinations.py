"""Tier 1: a rename that would collide is refused before the first move (0.24.0).

RENAME-PARTIAL-MUTATION. The reading pass of ``pyfs-matrix rename`` checked no
destination: the apply pass moved paths in order and refused an occupied
destination AFTER moving the ones before it, saying nothing else was changed,
with the manifest still describing the tree as it had been. The rehearsal said
the rename would go through.

What is asserted is the requirement and not the implementation: a workspace
whose rename is refused is BYTE FOR BYTE the workspace it was, every path of
it, and the rehearsal refuses what the run refuses.

The fixture is the real one of ``test_goal024_rename_command``: a matrix run
through the campaign loop and written back into the 0.20.x shape.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pyflightstream.run.rename import rename_workspace
from pyflightstream.workspace import CampaignWorkspace, WorkspaceError
from tests.tier1_offline.test_goal024_rename_command import _as_0_20, _ran, _reopened


def _tree(workspace: CampaignWorkspace) -> dict[str, bytes | None]:
    """Return every path under the workspace root with its bytes (None for a folder)."""
    root = workspace.root
    return {
        path.relative_to(root).as_posix(): (path.read_bytes() if path.is_file() else None)
        for path in sorted(root.rglob("*"))
    }


def _old_workspace(tmp_path) -> tuple[CampaignWorkspace, Path]:
    """A 0.20.x workspace of one steady row with two points, and its simulation folder."""
    workspace, _, _ = _ran(tmp_path)
    _as_0_20(workspace, mach=0.2)
    sim = workspace.sim_dir("3207")
    # The 0.20 shape this fixture promises: the FIRST point the command moves
    # is alpha -2, the second is alpha 0.
    assert sorted(p.name for p in (sim / "datapoints").iterdir()) == ["DP-a+00.0", "DP-a-02.0"]
    return workspace, sim


@pytest.mark.parametrize("apply", [True, False], ids=["apply", "dry-run"])
def test_goal028_rename_destinations_an_occupied_folder_refuses_before_any_move(tmp_path, apply):
    """The SECOND point's new folder is occupied: the first point must not have moved."""
    workspace, sim = _old_workspace(tmp_path)
    occupied = sim / "datapoints" / "DP-M200RE230AL+000"
    occupied.mkdir()
    (occupied / "kept.txt").write_text("evidence of something else", encoding="utf-8")
    before = _tree(workspace)

    with pytest.raises(WorkspaceError) as caught:
        rename_workspace(_reopened(workspace), apply=apply)

    assert _tree(workspace) == before, "a refused rename changed the workspace"
    message = str(caught.value)
    assert "DP-M200RE230AL+000" in message, message
    assert "nothing was changed" in message, message


@pytest.mark.parametrize("apply", [True, False], ids=["apply", "dry-run"])
def test_goal028_rename_destinations_an_occupied_file_refuses_before_any_move(tmp_path, apply):
    """A file of the second point already carries its new name: nothing moves.

    This is the shape the review measured: the folder moved, and THEN the file
    inside it met a name that was taken.
    """
    workspace, sim = _old_workspace(tmp_path)
    taken = sim / "datapoints" / "DP-a+00.0" / "P3207-M200RE230AL+000_cp.txt"
    taken.write_text("a file nothing of this record wrote", encoding="utf-8")
    before = _tree(workspace)

    with pytest.raises(WorkspaceError) as caught:
        rename_workspace(_reopened(workspace), apply=apply)

    assert _tree(workspace) == before, "a refused rename changed the workspace"
    message = str(caught.value)
    assert "P3207-M200RE230AL+000_cp.txt" in message, message
    assert "nothing was changed" in message, message


@pytest.mark.parametrize("apply", [True, False], ids=["apply", "dry-run"])
def test_goal028_rename_destinations_an_occupied_script_refuses_before_any_move(tmp_path, apply):
    """The script is the LAST path of a record to move, so it is the costliest to meet late."""
    workspace, sim = _old_workspace(tmp_path)
    taken = sim / "scripts" / "P3207-M200RE230AL+sweep.txt"
    taken.write_text("a script nothing of this record wrote", encoding="utf-8")
    before = _tree(workspace)

    with pytest.raises(WorkspaceError) as caught:
        rename_workspace(_reopened(workspace), apply=apply)

    assert _tree(workspace) == before, "a refused rename changed the workspace"
    assert "P3207-M200RE230AL+sweep.txt" in str(caught.value), str(caught.value)


def test_goal028_rename_destinations_a_free_workspace_still_renames(tmp_path):
    """THE CONTROL: the same workspace with nothing in the way is renamed whole.

    A pre-check that refuses everything would pass the three tests above.
    """
    workspace, sim = _old_workspace(tmp_path)

    report = rename_workspace(_reopened(workspace))

    assert report.renamed_records == 1
    assert sorted(p.name for p in (sim / "datapoints").iterdir()) == [
        "DP-M200RE230AL+000",
        "DP-M200RE230AL-020",
    ]
    assert (sim / "scripts" / "P3207-M200RE230AL+sweep.txt").is_file()
    # AND A SECOND RUN IS QUIET: the destinations it finds occupied are its own
    # work, already done, and not a collision.
    again = rename_workspace(_reopened(workspace))
    assert again.changes == [], again.lines()
