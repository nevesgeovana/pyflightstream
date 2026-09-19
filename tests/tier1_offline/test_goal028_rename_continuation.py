"""Tier 1: a continuation chain is renamed, and two points are still refused (0.24.0).

RENAME-CONTINUATION-REFUSAL. A continuation is a record of its own,
``<campaign>/sim_<id>/r<stamp>/<tag>``, OF THE SAME POINT as the run it
continues: one datapoint folder, the predecessor's files moved under
``archive/<stamp>/`` inside it. The rename keyed its collision check on
``(sim_id, new name)``, which the two records share by definition, so every
workspace that held a continuation was refused as two points colliding.

The fixture is a real workspace (the one of ``test_goal024_rename_command``)
with a continuation added the way ``continuation_run_id`` and
``archive_datapoint`` document the shape, in BOTH recordings: with the
``continues`` field of 0.24.0 and without it, as every chain recorded before
that field was.

The control is the refusal itself: two records of DIFFERENT folders that would
take one name are still refused.
"""

from __future__ import annotations

import json
import shutil

import pytest

from pyflightstream.run.rename import rename_workspace
from pyflightstream.workspace import CampaignWorkspace, WorkspaceError
from tests.tier1_offline.test_goal024_rename_command import _as_0_20, _ran, _reopened

STAMP = "20260901-101112"
POINT = "M200RE230AL+000"
STOPPED = f"named/sim_3207/{POINT}"
CONTINUATION = f"named/sim_3207/r{STAMP}/{POINT}"


def _unsteady(tmp_path) -> CampaignWorkspace:
    """A workspace of one unsteady row: one record per point, so a run id ends in its point."""
    workspace, _, _ = _ran(
        tmp_path,
        workflow="unsteady",
        cell="DELTA_TIME: 0.01 / TIME_ITERATIONS: 8",
    )
    assert [row["run_id"] for row in workspace.read_raw_manifest()] == [
        "named/sim_3207/M200RE230AL-020",
        STOPPED,
    ]
    return workspace


def _with_a_continuation(workspace: CampaignWorkspace, *, continues_field: bool) -> None:
    """Add the continuation of the alpha 0 point, as the run loop leaves one.

    The predecessor's files go under ``archive/<stamp>/`` inside the point's
    folder and the continuation's own files take their place; its record is a
    row of its own whose id carries the stamp BEFORE the point, and the
    predecessor's row is left as written.
    """
    rows = workspace.read_raw_manifest()
    stopped = next(row for row in rows if row["run_id"] == STOPPED)
    folder = workspace.sim_dir("3207") / "datapoints" / f"DP-{POINT}"
    archive = folder / "archive" / STAMP
    archive.mkdir(parents=True)
    for path in sorted(p for p in folder.iterdir() if p.is_file()):
        shutil.copy2(path, archive / path.name)
    continuation = json.loads(json.dumps(stopped))
    continuation["run_id"] = CONTINUATION
    if continues_field:
        continuation["continues"] = STOPPED
    else:
        continuation.pop("continues", None)
        stopped.pop("continues", None)
    rows.append(continuation)
    workspace.manifest_path.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")


@pytest.mark.parametrize(
    "continues_field", [True, False], ids=["recorded-by-0.24", "recorded-before-0.24"]
)
def test_goal028_rename_continuation_a_chain_is_renamed_as_one_point(tmp_path, continues_field):
    """Two records of ONE point and ONE folder are a chain, and the rename takes both."""
    workspace = _unsteady(tmp_path)
    _with_a_continuation(workspace, continues_field=continues_field)
    old_rows = _as_0_20(workspace, mach=0.2)
    # THE 0.20 SHAPE OF THE CHAIN: both rows end in the one tag, and the one
    # folder of that tag is on disk.
    assert [row["run_id"] for row in old_rows] == [
        "named/sim_3207/a-02.0",
        "named/sim_3207/a+00.0",
        f"named/sim_3207/r{STAMP}/a+00.0",
    ]
    sim = workspace.sim_dir("3207")
    assert sorted(p.name for p in (sim / "datapoints").iterdir()) == ["DP-a+00.0", "DP-a-02.0"]

    report = rename_workspace(_reopened(workspace))

    assert report.renamed_records == 3, report.summary()
    rows = workspace.read_raw_manifest()
    assert [row["run_id"] for row in rows] == [
        "named/sim_3207/M200RE230AL-020",
        STOPPED,
        CONTINUATION,
    ]
    assert [row["point_name"] for row in rows] == ["M200RE230AL-020", POINT, POINT]
    # ONE FOLDER, MOVED ONCE, with the archive of the predecessor still inside.
    assert sorted(p.name for p in (sim / "datapoints").iterdir()) == [
        f"DP-{POINT}",
        "DP-M200RE230AL-020",
    ]
    folder = sim / "datapoints" / f"DP-{POINT}"
    assert (folder / "archive" / STAMP).is_dir()
    for output in rows[2]["outputs"]:
        assert (sim / output).is_file(), output
    # A MOVE IS REPORTED ONCE: two records of one folder are one move of it.
    lines = report.lines()
    assert len(lines) == len(set(lines)), sorted(line for line in lines if lines.count(line) > 1)
    # THE CHAIN STILL READS AS A CHAIN: the continuation names its predecessor
    # under the predecessor's NEW id, which is an identity and not a path.
    if continues_field:
        assert rows[2]["continues"] == STOPPED, rows[2]["continues"]
    else:
        assert "continues" not in rows[2]
    assert "a+00.0" not in json.dumps(rows)

    again = rename_workspace(_reopened(workspace))
    assert again.changes == [], again.lines()


def test_goal028_rename_continuation_two_folders_taking_one_name_are_still_refused(tmp_path):
    """THE CONTROL: two records of two folders that would share one name are two points.

    A second record of the alpha 0 point is written under a respelled tag:
    `a+00.00` is ANOTHER folder on disk whose point is still alpha 0, so both
    folders would move to `DP-M200RE230AL+000` and one would destroy the other.
    """
    workspace = _unsteady(tmp_path)
    old_rows = _as_0_20(workspace, mach=0.2)
    sim = workspace.sim_dir("3207")
    twin = json.loads(json.dumps(old_rows[1]).replace("a+00.0", "a+00.00"))
    shutil.copytree(sim / "datapoints" / "DP-a+00.0", sim / "datapoints" / "DP-a+00.00")
    old_rows.append(twin)
    workspace.manifest_path.write_text(json.dumps(old_rows, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(WorkspaceError) as caught:
        rename_workspace(_reopened(workspace))

    message = str(caught.value)
    assert "cannot share one folder" in message, message
    assert "a+00.0" in message and "a+00.00" in message, message
    assert sorted(p.name for p in (sim / "datapoints").iterdir()) == [
        "DP-a+00.0",
        "DP-a+00.00",
        "DP-a-02.0",
    ]
    assert workspace.read_raw_manifest() == old_rows
