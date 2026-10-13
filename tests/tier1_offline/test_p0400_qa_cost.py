"""P0400-COSTJOB: the cost view's rows and means.

PFS-2094.002: a steady sweep JOB record is one row, labelled by its sweep, and
its time is never shown as its first point's.
PFS-2094.003: runs that reached no answer are kept apart from the mean that
compare() pairs on.
"""

from __future__ import annotations

import pytest

from pyflightstream.qa.cost import cost_rows, cost_view
from pyflightstream.workspace import RunRecord, RunStatus

SHA = "a" * 64


def _record(run_id: str, *, wall_time_s: float, status=RunStatus.CONVERGED, **extra) -> RunRecord:
    return RunRecord(
        run_id=run_id,
        sim_id="1",
        point={"alpha_deg": 0.0},
        fs_version_requested="26.120",
        fs_build="2122026",
        fs_exe_sha256=SHA,
        package_version="0.40.0",
        script_sha256="0" * 64,
        raw_flag=False,
        status=status,
        wall_time_s=wall_time_s,
        **extra,
    )


def _job() -> RunRecord:
    ran = [
        # A run status as the manifest writes it (PFS-2093.005 reads it at load).
        {"tag": tag, "point": {"alpha_deg": alpha}, "status": "CONVERGED"}
        for tag, alpha in (("AL+000", 0.0), ("AL+002", 2.0), ("AL+004", 4.0))
    ]
    return _record("c/sim_1/sweep", wall_time_s=90.0, points_ran=ran)


def test_p0400_costjob_a_job_record_is_one_sweep_row_and_never_its_first_point():
    """P0400-COSTJOB (PFS-2094.002) the polar's time is labelled by the sweep."""
    view = cost_view([_job()])
    (row,) = view.rows()
    assert row["point"] == "sweep of 3 points: AL+000, AL+002, AL+004", row
    assert "alpha_deg" not in str(row["point"])
    assert view.wall_time_s(view.points[0], view.builds[0]) == pytest.approx(90.0)
    assert cost_rows([_job()])[0]["point"] == row["point"]


def test_p0400_costjob_a_job_and_a_point_record_of_one_sim_are_two_rows():
    """P0400-COSTJOB (PFS-2094.002) the job does not average into the first point's cell."""
    view = cost_view([_job(), _record("c/sim_1/AL+000", wall_time_s=30.0)])
    times = {row["point"]: row[view.builds[0].label] for row in view.rows()}
    assert times == {"alpha_deg=0.0": 30.0, "sweep of 3 points: AL+000, AL+002, AL+004": 90.0}


def test_p0400_costjob_a_failed_run_is_kept_apart_from_the_mean():
    """P0400-COSTJOB (PFS-2094.003) 10 s converged beside 2 s failed is a 10 s answer."""
    view = cost_view(
        [
            _record("r1", wall_time_s=10.0),
            _record("r2", wall_time_s=2.0, status=RunStatus.FAILED_EXECUTION),
        ]
    )
    cell = view.cell(view.points[0], view.builds[0])
    assert cell.run_count == 2
    assert cell.excluded_count == 1
    assert cell.samples == (10.0,)
    assert cell.excluded_samples == (2.0,)
    assert cell.wall_time_s == pytest.approx(10.0)


def test_p0400_costjob_compare_pairs_on_answers_only():
    """P0400-COSTJOB (PFS-2094.003) a build that only failed has no time to an answer to pair."""
    failed_fast = RunRecord.model_validate(
        {
            **_record("r2", wall_time_s=1.0, status=RunStatus.FAILED_EXECUTION).model_dump(),
            "fs_exe_sha256": "b" * 64,
        }
    )
    view = cost_view([_record("r1", wall_time_s=10.0), failed_fast])
    base, cand = view.builds
    comparison = view.compare(base, cand)
    assert comparison.paired == ()
    assert len(comparison.unpaired) == 1
