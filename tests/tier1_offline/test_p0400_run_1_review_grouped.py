"""Grouped retries must retain evidence when a campaign scheduling guard refuses."""

from __future__ import annotations

import pytest

from pyflightstream.workspace import RunStatus, WorkspaceError
from tests.tier1_offline.test_p0400_run_1_batch_run import _failed_once, p0350


def test_p0400_review_grouped_queue_refusal_preserves_failed_records(tmp_path):
    """P0400-REVIEW-GROUPED: a foreign queued point refuses before supersession."""
    workspace, matrix, profile = _failed_once(tmp_path)
    original = workspace.read_manifest()[0]
    workspace.append_record(
        original.model_copy(
            update={"run_id": "foreign/sim_7001/queued", "status": RunStatus.SUBMITTED}
        )
    )
    before = workspace.manifest_path.read_bytes()
    with pytest.raises(WorkspaceError, match="queue"):
        p0350._run(workspace, matrix, executor=p0350._submitting(profile))
    assert workspace.manifest_path.read_bytes() == before


@pytest.mark.parametrize("resume", [False, True])
def test_p0400_review_grouped_retry_still_runs_after_the_guards_pass(tmp_path, resume):
    """P0400-REVIEW-GROUPED: deferring supersession must not skip the failed points."""
    workspace, matrix, profile = _failed_once(tmp_path)
    ids = [record.run_id for record in workspace.read_manifest()]
    records = p0350.run_grouped_matrix(
        matrix,
        workspace,
        mode="batch",
        batch=1,
        name=p0350.MATRIX,
        recipes={},
        recipe_registry=p0350.workflow_registry(),
        executor=p0350._submitting(profile, submit=False),
        assess=p0350.converged,
        resume=resume,
    )
    assert [record.run_id for record in records] == ids
    assert all(record.status is RunStatus.SUBMITTED for record in records)
    assert [record.run_id for record in workspace.read_manifest()] == ids


@pytest.mark.parametrize("resume", [False, True])
def test_p0400_review_grouped_partial_retry_preserves_unfailed_points(tmp_path, resume):
    """P0400-REVIEW-GROUPED: retry neither removes nor reruns a completed sibling."""
    workspace, matrix, profile = _failed_once(tmp_path)
    rows = workspace.read_raw_manifest()
    rows[0]["status"] = RunStatus.CONVERGED.value
    workspace._replace_manifest(rows)
    before = workspace.manifest_path.read_bytes()
    keywords = dict(
        mode="batch",
        batch=1,
        name=p0350.MATRIX,
        recipes={},
        recipe_registry=p0350.workflow_registry(),
        executor=p0350._submitting(profile, submit=False),
        assess=p0350.converged,
        resume=resume,
    )
    if not resume:
        with pytest.raises(WorkspaceError):
            p0350.run_grouped_matrix(matrix, workspace, **keywords)
        assert workspace.manifest_path.read_bytes() == before
    else:
        records = p0350.run_grouped_matrix(matrix, workspace, **keywords)
        assert {record.run_id for record in records} == {row["run_id"] for row in rows[1:]}
        assert workspace.read_raw_manifest()[0] == rows[0]
