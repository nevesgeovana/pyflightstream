"""G37 of 0.28.0: naming one point of a recorded steady JOB redoes the whole job.

A steady row runs as ONE warm job recorded under the row's id (FR-95). --force-rerun
naming the JOB already redid every angle; naming one of its POINTS, by its point name or
its full run_id, archived the job's record and ran the named point alone and cold, so the
other angles were left in no record (reproduced by the opening round of 0.28.0, all three
lenses). Now every naming of a job's point resolves to the whole job before anything is
archived, and a warning says which points run again.
"""

from __future__ import annotations

import warnings

import pytest

from pyflightstream.exceptions import PyflightstreamWarning
from tests.tier1_offline.test_goal031_recorded_job_plan import SWEPT, _recorded_sweep, _run
from tests.tier1_offline.test_matrix_run import WRITES_EVERY_EXPORT, CountingStub

POINTS = ("M100RE230AL-020BE+000", "M100RE230AL+000BE+000", "M100RE230AL+020BE+000")


@pytest.mark.parametrize(
    "named",
    ["M100RE230AL+000BE+000", "warm/sim_5001/M100RE230AL+000BE+000"],
    ids=["point-name", "point-run-id"],
)
def test_g37_a_point_of_a_recorded_job_redoes_the_whole_job(tmp_path, named):
    workspace, matrix = _recorded_sweep(tmp_path, SWEPT)
    stub = CountingStub(WRITES_EVERY_EXPORT)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        from pyflightstream.cases.workflows import workflow_registry
        from pyflightstream.run.matrix import run_matrix
        from tests.tier1_offline.test_matrix_run import RECIPES, converged

        records = run_matrix(
            matrix,
            workspace,
            name="warm",
            default_fs_version="26.120",
            recipes=RECIPES,
            recipe_registry=workflow_registry(),
            assess=converged,
            executor=stub,
            force_rerun=[named],
        )
    assert [record.run_id for record in records] == ["warm/sim_5001/sweep"], [
        record.run_id for record in records
    ]
    assert len(records[0].points_ran) == 3, records[0].points_ran
    assert len(stub.invocations) == 1, stub.invocations
    said = [str(w.message) for w in caught if issubclass(w.category, PyflightstreamWarning)]
    assert any("a job is indivisible" in s and all(p in s for p in POINTS) for s in said), said
    job, *rest = workspace.read_manifest()
    assert job.run_id == "warm/sim_5001/sweep" and len(job.points_ran) == 3
    assert not rest, [record.run_id for record in rest]


def test_g37_naming_the_job_is_unchanged_and_not_warned_as_a_point(tmp_path):
    workspace, matrix = _recorded_sweep(tmp_path, SWEPT)
    stub = CountingStub(WRITES_EVERY_EXPORT)
    records = _run(workspace, matrix, stub, force_rerun=["warm/sim_5001/sweep"])
    assert [record.run_id for record in records] == ["warm/sim_5001/sweep"]
    assert len(records[0].points_ran) == 3


@pytest.mark.parametrize(
    "extra",
    [{"force_rerun": ["M100RE230AL+000BE+000"]}, {"force_rerun_all": True}],
    ids=["a-point-of-the-job", "force-rerun-all"],
)
def test_g37_the_job_s_rerun_retires_a_point_recorded_on_its_own(tmp_path, capsys, extra):
    """A row extended after its job ran records the new angle by itself (--resume). Redoing
    the job runs that angle too, so its own record is archived with the job's: one active
    record remains, the new job's, and not the old point beside it (reading A28)."""
    workspace, matrix = _recorded_sweep(tmp_path, SWEPT + ",4.0")
    _run(workspace, matrix, CountingStub(WRITES_EVERY_EXPORT), resume=True)
    assert sorted(record.run_id for record in workspace.read_manifest()) == [
        "warm/sim_5001/M100RE230AL+040BE+000",
        "warm/sim_5001/sweep",
    ]
    capsys.readouterr()
    records = _run(workspace, matrix, CountingStub(WRITES_EVERY_EXPORT), **extra)
    assert [record.run_id for record in records] == ["warm/sim_5001/sweep"]
    assert len(records[0].points_ran) == 4, records[0].points_ran
    active = workspace.read_manifest()
    assert [record.run_id for record in active] == ["warm/sim_5001/sweep"], [
        record.run_id for record in active
    ]
    if "force_rerun_all" in extra:
        said = capsys.readouterr().err
        assert "selected 4 point(s) in 1 job(s); 2 recorded record(s)" in said, said
