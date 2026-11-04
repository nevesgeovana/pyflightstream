"""G44 of 0.28.0: `pyfs-matrix run --force-rerun-all [--sims SIM ...]`.

Every recorded point of the
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


@pytest.mark.requirement("FR-131")
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


@pytest.mark.requirement("FR-131")
def test_p0430_every_selected_recorded_point_is_archived_and_no_other_fr_131(tmp_path):
    """FR-131: the evidence of each selected recorded point is archived before it reruns."""
    workspace, matrix = _two_simulations(tmp_path)
    selected = sorted((workspace.sim_dir("5002") / "datapoints").glob("DP-*"))
    other = sorted((workspace.sim_dir("5001") / "datapoints").glob("DP-*"))
    assert selected and other
    before = {
        folder.name: {p.name: p.read_bytes() for p in folder.iterdir() if p.is_file()}
        for folder in selected
    }
    _run(workspace, matrix, CountingStub(WRITES_EVERY_EXPORT), force_rerun_all=True, sims=["5002"])
    for folder in selected:
        stamps = sorted((folder / "archive").iterdir())
        assert len(stamps) == 1, f"{folder.name} was not archived exactly once"
        kept = {p.name: p.read_bytes() for p in stamps[0].iterdir() if p.is_file()}
        assert kept and kept.items() <= before[folder.name].items(), (
            f"{folder.name}: the archive does not hold the evidence that was replaced"
        )
    assert not [folder for folder in other if (folder / "archive").exists()], (
        "a point of a simulation --sims did not name was archived"
    )


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


def test_g44_points_recorded_one_by_one_are_counted_as_the_one_job_that_reruns_them(
    tmp_path, capsys
):
    """A steady row whose angles were recorded one at a time (one run, then a --resume)
    runs again as ONE warm job, and the count said first says one job (reading A29)."""
    workspace, matrix = _steady_sweep_matrix(tmp_path)
    text = matrix.read_text(encoding="utf-8")
    swept = "-2.0,0.0,2.0"
    assert swept in text, text
    matrix.write_text(text.replace(swept, "0.0"), encoding="utf-8")
    _run(workspace, matrix, CountingStub(WRITES_EVERY_EXPORT))
    matrix.write_text(text.replace(swept, "0.0,2.0"), encoding="utf-8")
    _run(workspace, matrix, CountingStub(WRITES_EVERY_EXPORT), resume=True)
    assert len(workspace.read_manifest()) == 2, [r.run_id for r in workspace.read_manifest()]
    assert all(not r.run_id.endswith("/sweep") for r in workspace.read_manifest())
    capsys.readouterr()
    stub = CountingStub(WRITES_EVERY_EXPORT)
    _run(workspace, matrix, stub, force_rerun_all=True)
    said = capsys.readouterr().err
    assert "selected 2 point(s) in 1 job(s); 2 recorded record(s)" in said, said
    assert len(stub.invocations) == 1, stub.invocations


def test_g44_points_beside_the_redo_and_an_empty_manifest_are_refused(tmp_path):
    """FR-326 retargets the refusal of `--sims` alone, which is a selection since 0.34.0.

    What stays refused is the redo of a selection of points, which `--force-rerun` names, and the
    redo of an empty manifest; both before anything runs.
    """
    workspace, matrix = _steady_sweep_matrix(tmp_path)
    stub = CountingStub(WRITES_EVERY_EXPORT)
    with pytest.raises(MatrixError, match=r"cannot be combined with force_rerun_all"):
        _run(workspace, matrix, stub, force_rerun_all=True, sims=["5001"], points=["X"])
    with pytest.raises(MatrixError, match=r"found no recorded point"):
        _run(workspace, matrix, stub, force_rerun_all=True)
    assert stub.invocations == []


# --- a point recorded as SUBMITTED is redone by --force-rerun-all ---------------------


def _submitted_rotor(tmp_path):
    from tests.tier1_offline.test_goal021_swept_row import _rotor_row, _submitted_row

    workspace, records = _submitted_row(tmp_path)
    assert {r.status.name for r in records} == {"SUBMITTED"}, records
    return workspace, _rotor_row(tmp_path, extra=" / EXPORT_UNSTEADY_AFTER_REV: 1"), records


@pytest.mark.parametrize("sims", [None, ["7001"]], ids=["whole-matrix", "with-sims"])
def test_force_rerun_all_redoes_a_point_recorded_as_submitted(tmp_path, sims, capsys):
    from tests.tier1_offline.test_matrix_run import StubSolver

    workspace, row, submitted = _submitted_rotor(tmp_path)
    ids = sorted(r.run_id for r in submitted)
    extra = {} if sims is None else {"sims": sims}
    with pytest.warns(PyflightstreamWarning) as caught:
        records = run_matrix(
            row,
            workspace,
            name="rotor",
            recipes={},
            recipe_registry=workflow_registry(),
            assess=converged,
            executor=StubSolver(WRITES_EVERY_EXPORT),
            force_rerun_all=True,
            **extra,
        )
    assert sorted(r.run_id for r in records) == ids
    assert all(r.status.name != "SUBMITTED" for r in records), [r.status for r in records]
    said = " ".join(str(w.message) for w in caught)
    assert "may still be in the scheduler's queue" in said and "not cancelled" in said, said
    assert all(run_id in said for run_id in ids), said
    archives = list((workspace.root / "archive").glob("runs-*.json"))
    assert len(archives) == 1, "the old records were not archived"
    assert all(r.status.name != "SUBMITTED" for r in workspace.read_manifest())


def test_force_rerun_all_leaves_a_plain_run_of_a_submitted_point_as_it_was(tmp_path):
    from pyflightstream.exceptions import WorkspaceError
    from tests.tier1_offline.test_goal021_swept_row import _run as run_rotor
    from tests.tier1_offline.test_matrix_run import StubSolver

    workspace, row, submitted = _submitted_rotor(tmp_path)
    with pytest.raises(WorkspaceError, match=r"still in a scheduler's queue"):
        run_rotor(
            workspace,
            row,
            StubSolver(WRITES_EVERY_EXPORT),
            force_rerun=[submitted[0].run_id],
        )


def _submitted_batch(tmp_path):
    from tests.tier1_offline import test_p0350_batch_run as grouped

    workspace, profile, _ = grouped._workspace(tmp_path)
    matrix = grouped._matrix(tmp_path)
    grouped._plan(workspace, matrix, mode="batch", batch=1)
    records = grouped._run(workspace, matrix, executor=grouped._submitting(profile))
    assert {r.status.name for r in records} == {"SUBMITTED"}, records
    return grouped, workspace, profile, matrix, records


def _rerun(grouped, workspace, profile, matrix, **extra):
    return run_matrix(
        matrix,
        workspace,
        name=grouped.MATRIX,
        recipes={},
        recipe_registry=workflow_registry(),
        assess=converged,
        executor=grouped._submitting(profile, submit=False),
        **extra,
    )


def test_force_rerun_all_redoes_a_point_of_a_batch_still_in_the_queue(tmp_path):
    grouped, workspace, profile, matrix, records = _submitted_batch(tmp_path)
    ids = sorted(r.run_id for r in records)
    label = f"{grouped.MATRIX}_b1"
    with pytest.warns(PyflightstreamWarning) as caught:
        redone = _rerun(grouped, workspace, profile, matrix, force_rerun_all=True)
    said = " ".join(str(w.message) for w in caught)
    assert "not cancelled" in said and "writes the batch folder" in said, said
    assert label in said and all(run_id in said for run_id in ids), said
    assert sorted(r.run_id for r in redone) == ids
    # THE REDONE POINTS WRITE THE MANAGED SIMULATION FOLDER, not the batch folder the old
    # job still writes, so the old job cannot write over the folder the new run collects.
    assert (workspace.root / "sims" / "sim_7001").is_dir()
    batch_folder = workspace.root / "sims" / "batch" / label
    assert batch_folder not in workspace.sim_dir("7001").parents


def test_a_plain_force_rerun_of_a_point_of_a_batch_still_in_the_queue_is_refused(tmp_path):
    from pyflightstream.exceptions import WorkspaceError

    grouped, workspace, profile, matrix, records = _submitted_batch(tmp_path)
    with pytest.raises(WorkspaceError, match=r"whose job has not ended"):
        _rerun(grouped, workspace, profile, matrix, force_rerun=[records[0].run_id])


def _redo_said(call):
    """Run ``call`` and return its result and the force_rerun_all warnings it raised."""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = call()
    said = " ".join(
        str(w.message) for w in caught if str(w.message).startswith("force_rerun_all redoes")
    )
    return result, said


def test_the_warning_says_the_old_jobs_outputs_are_recorded_as_the_new_runs(tmp_path):
    from tests.tier1_offline.test_matrix_run import StubSolver

    workspace, row, _ = _submitted_rotor(tmp_path)
    _, said = _redo_said(
        lambda: run_matrix(
            row,
            workspace,
            name="rotor",
            recipes={},
            recipe_registry=workflow_registry(),
            assess=converged,
            executor=StubSolver(WRITES_EVERY_EXPORT),
            force_rerun_all=True,
        )
    )
    assert "recorded as the new run's" in said and "job id" in said, said
