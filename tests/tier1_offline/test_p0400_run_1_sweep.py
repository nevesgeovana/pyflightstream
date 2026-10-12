"""Tier 1, 0.40.0 lane run-1: a steady row's one-job record carries what a point's does.

The warm steady row of the 0.19.0 tests, run with the counting stub; no solver runs.
"""

from __future__ import annotations

from pyflightstream.cases.workflows import workflow_registry
from pyflightstream.run.matrix import run_matrix
from pyflightstream.script import BrokenCommandUse, Script
from tests.tier1_offline.test_matrix_run import (
    RECIPES,
    WRITES_EVERY_EXPORT,
    CountingStub,
    _steady_sweep_matrix,
    converged,
)

USE = BrokenCommandUse(
    command="AIR_ALTITUDE",
    version="26.120",
    source_version="26.120",
    report="RPT-000",
    reason="reproducing a run made before the defect",
)
WAIVED = USE.model_dump(mode="json")


def test_p0400_a_steady_job_record_carries_its_waivers_and_its_staging(tmp_path, monkeypatch):
    """P0400-JOB-RECORD-PROVENANCE (PFS-2103.026): waived_commands and staged_as on a job.

    The job path wrote ``waived_commands: []`` whatever its script waived and never wrote
    ``staged_as``; the point path filled both. Both paths now take them from one helper.
    """
    monkeypatch.setattr(Script, "waived_commands", property(lambda self: (USE,)))
    workspace, matrix = _steady_sweep_matrix(tmp_path)
    (record,) = run_matrix(
        matrix,
        workspace,
        name="warm",
        default_fs_version="26.120",
        recipes=RECIPES,
        recipe_registry=workflow_registry(),
        assess=converged,
        executor=CountingStub(WRITES_EVERY_EXPORT),
    )
    assert len(record.points_ran or []) == 3, "the row ran as one job"
    assert [dict(use) for use in record.waived_commands] == [WAIVED]
    mode, reason = workspace.staged_as("5001")
    assert mode is not None
    assert (record.staged_as, record.staged_as_reason) == (mode, reason)
