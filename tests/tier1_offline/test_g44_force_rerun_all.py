"""G44 of 0.28.0: `pyfs-matrix run --force-rerun-all [--sims SIM ...]`.

Her words: "para 28, eu quero um --force-rerun-all". Every recorded point of the
matrix, or of the simulations --sims names, is archived and runs again (a steady row
recorded as one job runs again as one job); the count is said before anything runs;
--sims narrows the run to those simulations; the mode is refused beside --resume and
--force-rerun, for an id the matrix does not carry, and when nothing is recorded.
"""

from __future__ import annotations

import warnings

import pytest

from pyflightstream.cases.workflows import workflow_registry
from pyflightstream.exceptions import PyflightstreamWarning
from pyflightstream.run.matrix import MatrixError, run_matrix
from tests.tier1_offline.test_goal031_recorded_job_plan import _recorded_sweep
from tests.tier1_offline.test_matrix_run import (
    RECIPES,
    WRITES_EVERY_EXPORT,
    CountingStub,
    _steady_sweep_matrix,
    converged,
)


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


def _two_simulations(tmp_path):
    """The one-row steady matrix with a second row, simulation 5002, both recorded."""
    workspace, matrix = _steady_sweep_matrix(tmp_path)
    lines = matrix.read_text(encoding="utf-8").splitlines()
    row = next(line for line in lines if line.startswith("5001"))
    matrix.write_text("\n".join([*lines, "5002" + row[len("5001") :]]) + "\n", encoding="utf-8")
    _run(workspace, matrix, CountingStub(WRITES_EVERY_EXPORT))
    assert [r.run_id for r in workspace.read_manifest()] == [
        "warm/sim_5001/sweep",
        "warm/sim_5002/sweep",
    ]
    return workspace, matrix


def test_g44_every_recorded_point_runs_again_and_the_count_is_said_first(tmp_path, capsys):
    workspace, matrix = _recorded_sweep(tmp_path)
    capsys.readouterr()
    stub = CountingStub(WRITES_EVERY_EXPORT)
    records = _run(workspace, matrix, stub, force_rerun_all=True)
    assert [r.run_id for r in records] == ["warm/sim_5001/sweep"]
    assert len(records[0].points_ran) == 3 and len(stub.invocations) == 1
    said = capsys.readouterr().err
    assert "force-rerun-all: selected 3 point(s) in 1 job(s)" in said, said
    assert (
        said.index("force-rerun-all") < said.index("warm/sim_5001")
        if "warm/sim_5001" in said
        else True
    )


def test_g44_sims_narrows_the_run_to_those_simulations(tmp_path):
    workspace, matrix = _two_simulations(tmp_path)
    kept = workspace.read_manifest()[0]
    stub = CountingStub(WRITES_EVERY_EXPORT)
    records = _run(workspace, matrix, stub, force_rerun_all=True, sims=["5002"])
    assert [r.run_id for r in records] == ["warm/sim_5002/sweep"]
    assert len(stub.invocations) == 1
    after = {r.run_id: r for r in workspace.read_manifest()}
    assert after["warm/sim_5001/sweep"] == kept, "a simulation --sims did not name was touched"


@pytest.mark.parametrize(
    "extra, said",
    [
        ({"resume": True}, r"refused together with resume"),
        ({"force_rerun": ["warm/sim_5001/sweep"]}, r"refused together with force_rerun"),
        ({"sims": ["9999"]}, r"sims names 9999, which this matrix does not carry"),
    ],
    ids=["with-resume", "with-force-rerun", "unknown-sim"],
)
def test_g44_refusals_come_before_anything_runs(tmp_path, extra, said):
    workspace, matrix = _recorded_sweep(tmp_path)
    before = [r.model_dump() for r in workspace.read_manifest()]
    stub = CountingStub(WRITES_EVERY_EXPORT)
    with pytest.raises(MatrixError, match=said):
        _run(workspace, matrix, stub, force_rerun_all=True, **extra)
    assert stub.invocations == []
    assert [r.model_dump() for r in workspace.read_manifest()] == before
    assert not list((workspace.root / "archive").glob("runs-*.json"))


def test_g44_sims_alone_and_an_empty_manifest_are_refused(tmp_path):
    workspace, matrix = _steady_sweep_matrix(tmp_path)
    stub = CountingStub(WRITES_EVERY_EXPORT)
    with pytest.raises(MatrixError, match=r"chooses the simulations of force_rerun_all"):
        _run(workspace, matrix, stub, sims=["5001"])
    with pytest.raises(MatrixError, match=r"found no recorded point"):
        _run(workspace, matrix, stub, force_rerun_all=True)
    assert stub.invocations == []
