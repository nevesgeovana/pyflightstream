"""The plan says READY for exactly the points ``run --resume`` would run.

A steady row of a matrix is ONE job recorded under the row's id and not under
its points' (FR-95). ``run_campaign`` knew that and skipped the points a
recorded job ran; ``plan_campaign`` looked for the points' own ids, found none,
and reported every point of a recorded sweep READY, which its own docstring
defines as what resume runs, while resume ran none of them.

And where resume itself was wrong, the licence was spent: a recorded sweep
extended by two angles was resumed as a second job of the row, the solver ran,
and the record was refused afterwards because the job's id was taken. Its new
points now run one each, as one new point always has, and a redo that names
the job still runs the whole row as one job. A row cut back to one angle the
job already ran was run again as a point, which its own outputs stopped before
the solver and recorded as a failure; it is recorded, and nothing runs.

Each case below is planned and then resumed with a counting stub solver, and
the plan's READY points are compared with the points the resume actually ran.
"""

from __future__ import annotations

import warnings

import pytest

from pyflightstream.cases.workflows import workflow_registry
from pyflightstream.exceptions import PyflightstreamWarning
from pyflightstream.run import PlanStatus
from pyflightstream.run.matrix import plan_matrix, run_matrix
from tests.tier1_offline.test_matrix_run import (
    RECIPES,
    WRITES_EVERY_EXPORT,
    CountingStub,
    _steady_sweep_matrix,
    converged,
)

RECORDED = ("M100RE230AL-020BE+000", "M100RE230AL+000BE+000", "M100RE230AL+020BE+000")
SWEPT = "-2.0,0.0,2.0"


def _run(workspace, matrix, stub, **extra):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", PyflightstreamWarning)
        return run_matrix(
            matrix,
            workspace,
            name="warm",
            default_fs_version="26.120",
            recipes=RECIPES,
            recipe_registry=workflow_registry(),
            assess=converged,
            executor=stub,
            **extra,
        )


def _plan(workspace, matrix):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", PyflightstreamWarning)
        plan = plan_matrix(
            matrix,
            workspace,
            name="warm",
            default_fs_version="26.120",
            recipes=RECIPES,
            recipe_registry=workflow_registry(),
        )
    return {entry.run_id.rsplit("/", 1)[1]: entry for entry in plan.points}


def _recorded_sweep(tmp_path, sweep=SWEPT):
    """Record the three-point job, then set the row's angles to ``sweep``."""
    workspace, matrix = _steady_sweep_matrix(tmp_path)
    _run(workspace, matrix, CountingStub(WRITES_EVERY_EXPORT))
    (job,) = workspace.read_manifest()
    assert [entry["tag"] for entry in job.points_ran] == list(RECORDED), job.points_ran
    text = matrix.read_text(encoding="utf-8")
    assert SWEPT in text, text
    matrix.write_text(text.replace(SWEPT, sweep), encoding="utf-8")
    return workspace, matrix


def test_the_plan_reports_a_recorded_jobs_points_as_recorded(tmp_path):
    """Nothing added to the row, and the plan said READY for every point."""
    workspace, matrix = _recorded_sweep(tmp_path)
    statuses = {name: entry.status for name, entry in _plan(workspace, matrix).items()}
    assert statuses == dict.fromkeys(RECORDED, PlanStatus.ALREADY_RECORDED), (
        f"the plan of a sweep its recorded job already ran says {statuses}; "
        "READY is what resume runs, and resume runs none of them"
    )
    stub = CountingStub(WRITES_EVERY_EXPORT)
    assert _run(workspace, matrix, stub, resume=True) == []
    assert stub.invocations == [], stub.invocations


@pytest.mark.parametrize(
    ("sweep", "ready"),
    [
        (SWEPT, set()),
        # ONE NEW ANGLE runs as its own point, which is not a job.
        (SWEPT + ",4.0", {"M100RE230AL+040BE+000"}),
        # TWO NEW ANGLES run one each too: the row's job id is the recorded job's.
        (SWEPT + ",4.0,6.0", {"M100RE230AL+040BE+000", "M100RE230AL+060BE+000"}),
        # CUT BACK TO AN ANGLE THE JOB RAN: nothing is left to run.
        ("0.0", set()),
    ],
    ids=["unchanged", "one-new-angle", "two-new-angles", "cut-to-a-ran-angle"],
)
def test_the_plan_is_ready_for_exactly_what_resume_runs(tmp_path, sweep, ready):
    workspace, matrix = _recorded_sweep(tmp_path, sweep)
    planned = _plan(workspace, matrix)
    said_ready = {name for name, entry in planned.items() if entry.status is PlanStatus.READY}
    assert said_ready == ready, {name: str(entry.status) for name, entry in planned.items()}
    assert {
        name for name, entry in planned.items() if entry.status is PlanStatus.ALREADY_RECORDED
    } == set(planned) - ready
    stub = CountingStub(WRITES_EVERY_EXPORT)
    records = _run(workspace, matrix, stub, resume=True)
    ran = {record.run_id.rsplit("/", 1)[1] for record in records}
    assert ran == ready, (
        f"the plan said READY for {sorted(said_ready)} and resume ran {sorted(ran)}"
    )
    assert len(stub.invocations) == len(ready), stub.invocations


def test_two_new_angles_of_a_recorded_job_are_recorded_one_each(tmp_path):
    """No second job under the recorded job's id: the seat is not spent on a refusal."""
    workspace, matrix = _recorded_sweep(tmp_path, SWEPT + ",4.0,6.0")
    stub = CountingStub(WRITES_EVERY_EXPORT)
    records = _run(workspace, matrix, stub, resume=True)
    assert [record.run_id for record in records] == [
        "warm/sim_5001/M100RE230AL+040BE+000",
        "warm/sim_5001/M100RE230AL+060BE+000",
    ], [record.run_id for record in records]
    assert all(not record.points_ran for record in records), "a new point ran as a job"
    job, *points = workspace.read_manifest()
    assert job.run_id == "warm/sim_5001/sweep" and len(job.points_ran) == 3, job.run_id
    assert [record.run_id for record in points] == [record.run_id for record in records]
    # AND THE NEXT PLAN AND RESUME AGREE THERE IS NOTHING LEFT.
    planned = _plan(workspace, matrix)
    assert {entry.status for entry in planned.values()} == {PlanStatus.ALREADY_RECORDED}
    again = CountingStub(WRITES_EVERY_EXPORT)
    assert _run(workspace, matrix, again, resume=True) == []
    assert again.invocations == [], again.invocations


def test_redoing_the_job_still_runs_the_whole_row_as_one_job(tmp_path):
    """--force-rerun naming the job supersedes it and runs every angle as one job."""
    workspace, matrix = _recorded_sweep(tmp_path, SWEPT + ",4.0,6.0")
    stub = CountingStub(WRITES_EVERY_EXPORT)
    records = _run(workspace, matrix, stub, force_rerun=["warm/sim_5001/sweep"])
    assert [record.run_id for record in records] == ["warm/sim_5001/sweep"], records
    assert len(records[0].points_ran) == 5, records[0].points_ran
    assert len(stub.invocations) == 1, stub.invocations
