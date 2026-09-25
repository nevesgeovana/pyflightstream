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
