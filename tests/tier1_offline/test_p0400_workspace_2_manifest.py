"""P0400-JOBPOINTS: a steady job's per-point records keep the job's verdict and their own limit."""

from __future__ import annotations

from pyflightstream.workspace.manifest import RunRecord, RunStatus

_MARK = {"from": "CONVERGED", "at": "2026-10-12T12:00:00", "reason": "wrong mesh"}


def _job(**fields) -> RunRecord:
    row = {
        "run_id": "campaign/sim_7002/sweep",
        "sim_id": "7002",
        "fs_version_requested": "26.120",
        "package_version": "0.40.0",
        "script_sha256": "0" * 64,
        "raw_flag": False,
        "status": "CONVERGED",
        "points_ran": [
            {"tag": "A0", "status": "CONVERGED", "point": {"ALPHA": 0.0}},
            {"tag": "A4", "status": "CONVERGED", "point": {"ALPHA": 4.0}},
        ],
    }
    row.update(fields)
    return RunRecord.model_validate(row)


def test_p0400_jobpoints_a_job_marked_failed_fails_every_unmarked_point():
    """P0400-JOBPOINTS (PFS-2103.014): mark-failed writes FAILED_MARKED and the mark on the job
    row only; every point of it comes back FAILED_MARKED, not its entry's CONVERGED."""
    job = _job(status="FAILED_MARKED", marked=_MARK)
    points = job.as_points()
    assert [p.status for p in points] == [RunStatus.FAILED_MARKED, RunStatus.FAILED_MARKED]
    assert all(p.marked == _MARK for p in points)


def test_p0400_jobpoints_a_point_verdict_of_its_own_stands_under_a_failed_job():
    """P0400-JOBPOINTS (PFS-2103.014): a point a person marked on its own keeps that verdict."""
    own = {"from": "FAILED_MARKED", "at": "2026-10-12T13:00:00", "reason": "checked"}
    job = _job(status="FAILED_MARKED", marked=_MARK)
    job.points_ran[1].update(status="CONVERGED", marked=own)
    assert [p.status for p in job.as_points()] == [RunStatus.FAILED_MARKED, RunStatus.CONVERGED]


def test_p0400_jobpoints_each_point_keeps_its_own_limit_and_note():
    """P0400-JOBPOINTS (PFS-2103.015): the job row carries what _record_sweep_outcome writes (no
    note, no limit) and the MAX_ITER_REACHED entry carries its own; the per-point record keeps
    the entry's, so the post's warning names the limit."""
    job = _job(status="MAX_ITER_REACHED")
    job.points_ran[0].update(
        status="MAX_ITER_REACHED",
        iterations_requested=500,
        residual_note="unsettled at the iteration limit (500)",
    )
    first, second = job.as_points()
    assert first.iterations_requested == 500
    assert first.residual_note == "unsettled at the iteration limit (500)"
    assert second.iterations_requested is None and second.residual_note is None
