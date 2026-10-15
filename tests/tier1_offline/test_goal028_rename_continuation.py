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

from pyflightstream.workspace import CampaignWorkspace
from tests.tier1_offline.test_goal024_rename_command import _ran

STAMP = "20260901-101112"
POINT = "M200RE230AL+000"
STOPPED = f"named/sim_3207/{POINT}"
CONTINUATION = f"named/sim_3207/r{STAMP}/{POINT}"


def _unsteady(tmp_path) -> CampaignWorkspace:
    """A workspace of one unsteady row: one record per point, so a run id ends in its point."""
    workspace, _, _ = _ran(
        tmp_path,
        workflow="unsteady",
        cell="DELTA_TIME: 0.01 / TIME_ITERATIONS: 8 / LAST_ITERS_AVG: 8",
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
    workspace._replace_manifest(rows)
