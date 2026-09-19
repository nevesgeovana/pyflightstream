"""Tier 1: a record is named by the condition IT ran at, never by today's row (0.24.0).

RENAME-CURRENT-CONDITION. The rename built its naming case from the CURRENT
matrix row, and its "the matrix changed since the run" check compared the point
tags alone. A fixed Mach number edited after the run therefore passed the
check, and a record that ran at Mach 0.2 was renamed ``M100...`` because the
row says 0.1 today: historical evidence relabeled with a condition it never
saw, in its folder, its files and its manifest row.

The requirement: the name describes the RECORDED condition, and a row that
disagrees with a record is refused BY NAME (which record, which variable, both
values) with the workspace untouched.

Expected names are written from the approved naming table (Mach x 1000 in three
digits, REmi x 100, alpha x 10 signed), never read off the renamer.
"""

from __future__ import annotations

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


def _edit(matrix, before: str, after: str) -> None:
    text = matrix.read_text(encoding="utf-8")
    assert text.count(before) == 1, (before, text.count(before))
    matrix.write_text(text.replace(before, after), encoding="utf-8")


def test_goal028_rename_recorded_condition_a_0_20_record_is_not_named_by_todays_mach(tmp_path):
    """Ran at Mach 0.2, the row says 0.1 today: refused, and nothing is called M100."""
    workspace, matrix, _ = _ran(tmp_path)
    _as_0_20(workspace, mach=0.2)
    _edit(matrix, "MACH:0.2", "MACH:0.1")
    before = _tree(workspace)

    with pytest.raises(WorkspaceError) as caught:
        rename_workspace(_reopened(workspace))

    assert _tree(workspace) == before, "a refused rename changed the workspace"
    message = str(caught.value)
    # BY NAME: the record, the variable, what it ran at and what the row says.
    assert "named/sim_3207/sweep" in message, message
    assert "MACH" in message and "0.2" in message and "0.1" in message, message
    assert "nothing was changed" in message, message


def test_goal028_rename_recorded_condition_a_named_record_is_not_relabeled(tmp_path):
    """The same edit on a workspace ALREADY at the 0.21 names, which is the costlier case.

    Nothing about this workspace needs renaming. Before 0.24.0 the command
    moved `DP-M200RE230AL+000` to `DP-M100RE230AL+000` and rewrote the record
    to match, so a second look at the tree showed a Mach 0.1 campaign.
    """
    workspace, matrix, _ = _ran(tmp_path)
    _edit(matrix, "MACH:0.2", "MACH:0.1")
    before = _tree(workspace)

    with pytest.raises(WorkspaceError) as caught:
        rename_workspace(_reopened(workspace), apply=False)

    assert _tree(workspace) == before
    assert "MACH" in str(caught.value), str(caught.value)
    datapoints = workspace.sim_dir("3207") / "datapoints"
    assert sorted(p.name for p in datapoints.iterdir()) == [
        "DP-M200RE230AL+000",
        "DP-M200RE230AL-020",
    ]


def test_goal028_rename_recorded_condition_a_variable_the_row_dropped_is_a_disagreement(tmp_path):
    """The row no longer states REmi: the name would silently lose its `RE230` field."""
    workspace, matrix, _ = _ran(tmp_path)
    _as_0_20(workspace, mach=0.2)
    _edit(matrix, "MACH:0.2, REmi:2.3, ALPHA:sweep", "MACH:0.2, ALPHA:sweep")

    with pytest.raises(WorkspaceError) as caught:
        rename_workspace(_reopened(workspace))

    assert "REmi" in str(caught.value), str(caught.value)


def test_goal028_rename_recorded_condition_an_edit_that_states_the_same_condition_renames(
    tmp_path,
):
    """THE CONTROL: the matrix was edited and the CONDITION was not, so the rename goes through.

    `0.2` respelled `0.20` and a new description are one flight condition. A
    check that refused every edited matrix would pass the three tests above.
    """
    workspace, matrix, _ = _ran(tmp_path)
    _as_0_20(workspace, mach=0.2)
    _edit(matrix, "MACH:0.2", "MACH:0.20")
    _edit(matrix, "NAMED_BY_ITS_FLIGHT_CONDITION", "DESCRIBED_AGAIN_SINCE_THE_RUN")

    report = rename_workspace(_reopened(workspace))

    assert report.renamed_records == 1
    datapoints = workspace.sim_dir("3207") / "datapoints"
    assert sorted(p.name for p in datapoints.iterdir()) == [
        "DP-M200RE230AL+000",
        "DP-M200RE230AL-020",
    ]


@pytest.mark.parametrize("workflow", ["steady", "unsteady"])
def test_goal028_rename_recorded_condition_a_swept_flow_variable_is_not_a_disagreement(
    tmp_path, workflow
):
    """THE OTHER CONTROL: on a Mach sweep each record states ITS Mach and the row states none.

    The recorded condition of a swept flow variable is the point's own value,
    `MACH: 0.1` on one record and `MACH: 0.2` on the next, while the row's cell
    says `sweep`. That is the record agreeing with the row, not a changed matrix.
    """
    cell = "DELTA_TIME: 0.01 / TIME_ITERATIONS: 8" if workflow == "unsteady" else ""
    workspace, _, _ = _ran(
        tmp_path,
        condition="MACH:sweep, REmi:2.3, ALPHA:0.0",
        values="0.1,0.2",
        workflow=workflow,
        cell=cell,
    )
    recorded = [row["flight_condition"].get("MACH") for row in workspace.read_raw_manifest()]
    assert recorded == [0.1, 0.2], "the fixture is a row whose records each state their own Mach"

    report = rename_workspace(_reopened(workspace))

    assert report.changes == [], report.lines()
    datapoints = workspace.sim_dir("3207") / "datapoints"
    assert sorted(p.name for p in datapoints.iterdir()) == [
        "DP-M100RE230AL+000",
        "DP-M200RE230AL+000",
    ]
