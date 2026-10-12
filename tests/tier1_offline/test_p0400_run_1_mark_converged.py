"""Tier 1, 0.40.0 lane run-1: mark-converged (FR-414) over the package's own grouped run.

The workspace of the 0.37.0 tests: three rows collected without their logs, row 7002 a
two-point steady job. No solver runs.
"""

from __future__ import annotations

import json

import pytest

from pyflightstream.run.records import mark_converged, mark_failed
from pyflightstream.workspace.naming import RunsManifestError
from tests.tier1_offline.test_p0370_s1_mark_converged import REASON, _rows
from tests.tier1_offline.test_p0370_s1_mark_converged import workspace as workspace  # noqa: F401
from tests.tier1_offline.test_p0370_s1_matrix_home import pyfs


def _job(workspace) -> dict:
    (row,) = [row for row in _rows(workspace).values() if row["sim_id"] == "7002"]
    return row


def test_p0400_a_point_of_a_job_marked_failed_is_refused(workspace, capsys):  # noqa: F811
    """P0400-MARK-CONVERGED-JOB-MARKED (PFS-2103.031): mark-failed 7002, then one of its points.

    mark-failed marks the job's row and leaves its points' statuses, and mark-converged read
    the points only, so it replaced the person's FAILED_MARKED by a computed status.
    """
    mark_failed(workspace.root, ["7002"], reason="wrong mesh", apply=True)
    tag = _job(workspace)["points_ran"][0]["tag"]
    before = workspace.manifest_path.read_bytes()
    with pytest.raises(RunsManifestError, match="marked failed by a person"):
        mark_converged(workspace.root, ["7002"], points=[tag], reason=REASON, apply=True)
    assert workspace.manifest_path.read_bytes() == before


def test_p0400_a_jobs_own_failure_outlives_a_points_verdict(workspace):  # noqa: F811
    """P0400-MARK-CONVERGED-JOB-FAILURE (PFS-2103.031): the job failed, no point did.

    The row's status was recomputed from its points alone, so a job-level FAILED_EXECUTION
    no point carries became CONVERGED once the points were.
    """
    rows = json.loads(workspace.manifest_path.read_text("utf-8"))
    for row in rows:
        if row["sim_id"] == "7002":
            row["status"] = "FAILED_EXECUTION"
    workspace.manifest_path.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    mark_converged(workspace.root, ["7002"], reason=REASON, apply=True)
    job = _job(workspace)
    assert [point["status"] for point in job["points_ran"]] == ["CONVERGED", "CONVERGED"]
    assert job["status"] == "FAILED_EXECUTION"


def test_p0400_an_unreadable_manifest_is_a_refusal_not_a_traceback(workspace, capsys):  # noqa: F811
    """P0400-MARK-CONVERGED-UNREADABLE (PFS-2095.050): corrupt JSON, then an unknown status."""
    good = workspace.manifest_path.read_text("utf-8")
    workspace.manifest_path.write_text(good[:-20], encoding="utf-8")
    code, said = pyfs(
        ["mark-converged", "--sims", "7002", "--reason", REASON], workspace.root, capsys
    )
    assert code == 2 and "not readable JSON" in said, said
    rows = json.loads(good)
    for row in rows:
        if row["sim_id"] == "7002":
            row["points_ran"][0]["status"] = "HALF_DONE"
            run_id, other = row["run_id"], row["points_ran"][1]["tag"]
    workspace.manifest_path.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    argv = ["mark-converged", "--sims", "7002", "--points", other, "--reason", REASON, "--apply"]
    code, said = pyfs(argv, workspace.root, capsys)
    assert code == 2 and "HALF_DONE" in said and run_id in said, said


def test_p0400_the_preview_of_a_refused_point_does_not_suggest_apply(workspace, capsys):  # noqa: F811
    """P0400-MARK-CONVERGED-PREVIEW-HINT (PFS-2100.016): every named point is refused.

    The preview said 'run again with --apply', which then refuses. It now says that each
    refusal must be resolved first.
    """
    mark_failed(workspace.root, ["7003"], reason="wrong mesh", apply=True)
    code, said = pyfs(
        ["mark-converged", "--sims", "7003", "--reason", REASON], workspace.root, capsys
    )
    assert code == 0, said
    assert "run again with --apply" not in said, said
    assert "resolve each refusal" in said, said
