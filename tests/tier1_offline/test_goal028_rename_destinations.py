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

from pyflightstream.workspace import CampaignWorkspace
from tests.tier1_offline.test_goal024_rename_command import _as_0_20, _ran


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
