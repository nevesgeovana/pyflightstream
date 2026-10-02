"""Tier 1, 0.34.0: a selection is planned and run, and a second run says how to continue.

Pipeline role: quality gate on the two run-usability items of the 0.34.0 scope (GEO-071,
section 4.8), through ``pyflightstream.run.cli.main``.

FR-326 (P0340-RUN-ONE-POINT): ``plan`` and ``run`` take ``--sims SIM [SIM ...]`` and
``--points POINT [POINT ...]``; only that selection is planned or run, the matrix file is not
written, an id or a point the matrix does not carry is refused before anything runs, a
selected point already recorded is refused as 0.33.0 refuses it, and ``run --force-rerun-all
--sims`` keeps its 0.33.0 reading.

FR-327 (P0340-RUN-AGAIN): a second ``run`` without ``--resume`` is refused with the exact
command that continues it, the counts of recorded and new points, and the same exit status.

What it does NOT check: a solver. A stub stands in for the executor, which counts its
invocations.
"""
# The evidence line of these requirements cites this module (docs/srs/functional-requirements.md):
# FR-326, FR-327.

from __future__ import annotations

import json
import shlex
import warnings

import pytest

import pyflightstream.run.cli as cli
import pyflightstream.run.matrix as matrix_module
from pyflightstream.cases import point_name
from pyflightstream.exceptions import PyflightstreamWarning
from pyflightstream.run import LoadsAssessor
from pyflightstream.workspace.matrix import resolve_matrix
from tests.tier1_offline.test_matrix_run import (
    WRITES_EVERY_EXPORT,
    CountingStub,
    _steady_sweep_matrix,
    converged,
)


def _two_simulations(tmp_path, monkeypatch):
    """The steady matrix with a second row, 5002, and a stub standing in for the solver."""
    workspace, matrix = _steady_sweep_matrix(tmp_path)
    lines = matrix.read_text(encoding="utf-8").splitlines()
    row = next(line for line in lines if line.startswith("5001"))
    matrix.write_text("\n".join([*lines, "5002" + row[len("5001") :]]) + "\n", encoding="utf-8")
    stub = CountingStub(WRITES_EVERY_EXPORT)
    monkeypatch.setattr(matrix_module, "LocalExecutor", lambda *args, **kwargs: stub)
    monkeypatch.setattr(LoadsAssessor, "__call__", lambda self, *args: converged(*args))
    return workspace, matrix, stub


def _argv(command, workspace, matrix, *extra):
    return [
        command,
        str(matrix),
        "--workspace",
        str(workspace.root),
        "--name",
        "warm",
        "--fs-version",
        "26.120",
        *extra,
    ]


def _names(workspace, matrix, sim):
    """The point names of a simulation, as the plan prints them."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", PyflightstreamWarning)
        resolved = resolve_matrix(
            matrix,
            workspace,
            name="warm",
            fs_version="26.120",
            recipes={},
            ignore_missing_families=True,
        )
    (case,) = [case for case in resolved.campaign.sims if case.sim_id == sim]
    return [point_name(case, point) for point in case.sweep.points()]


def _plan_file(workspace, matrix):
    return workspace.plan_dir(matrix.stem) / "plan.json"


def test_fr326_a_simulation_and_a_point_are_planned_and_run_alone(tmp_path, monkeypatch, capsys):
    """P0340-RUN-ONE-POINT (FR-326): one point of one simulation is planned and run through main.

    THE ASSERTIONS ARE WHAT RAN: the solver is started once, the manifest holds the one record of
    the selected simulation, named by the one selected point, the other simulation has no record,
    and the matrix file is byte-identical before and after both commands.
    """
    workspace, matrix, stub = _two_simulations(tmp_path, monkeypatch)
    names = _names(workspace, matrix, "5002")
    chosen = names[1]
    before = matrix.read_bytes()
    assert cli.main(_argv("plan", workspace, matrix, "--sims", "5002", "--points", chosen)) == 0
    planned = json.dumps(json.loads(_plan_file(workspace, matrix).read_text(encoding="utf-8")))
    assert chosen in planned and names[0] not in planned and "5001" not in planned, planned
    capsys.readouterr()
    status = cli.main(_argv("run", workspace, matrix, "--sims", "5002", "--points", chosen))
    assert status == 0, capsys.readouterr().err
    assert len(stub.invocations) == 1
    (record,) = workspace.read_manifest()
    assert record.run_id == f"warm/sim_5002/{chosen}"
    assert matrix.read_bytes() == before, "the matrix file was written"


def test_fr326_sims_alone_selects_whole_simulations_and_force_rerun_all_keeps_its_reading(
    tmp_path, monkeypatch, capsys
):
    """P0340-RUN-ONE-POINT (FR-326): `run --sims` alone runs those simulations, no refusal.

    The control is `--force-rerun-all --sims`, which keeps its 0.33.0 reading: it redoes the
    recorded points of the simulations it names, and says the count first.
    """
    workspace, matrix, stub = _two_simulations(tmp_path, monkeypatch)
    assert cli.main(_argv("plan", workspace, matrix)) == 0
    assert cli.main(_argv("run", workspace, matrix, "--sims", "5001")) == 0
    assert [record.sim_id for record in workspace.read_manifest()] == ["5001"]
    assert len(stub.invocations) == 1
    capsys.readouterr()
    status = cli.main(_argv("run", workspace, matrix, "--force-rerun-all", "--sims", "5001"))
    assert status == 0
    assert "force-rerun-all: selected 3 point(s) in 1 job(s)" in capsys.readouterr().err
    assert len(stub.invocations) == 2


@pytest.mark.parametrize(
    "extra, said",
    [
        (["--sims", "9999"], "9999"),
        (["--sims", "5001", "--points", "NOPE"], "NOPE"),
        (["--points", "NOPE"], "--sims"),
    ],
    ids=["unknown-sim", "unknown-point", "points-without-sims"],
)
@pytest.mark.parametrize("command", ["plan", "run"])
def test_fr326_an_id_or_a_point_the_matrix_lacks_is_refused_before_anything_runs(
    tmp_path, monkeypatch, capsys, command, extra, said
):
    """P0340-RUN-ONE-POINT (FR-326): the refusal names it and what exists, and nothing runs."""
    workspace, matrix, stub = _two_simulations(tmp_path, monkeypatch)
    assert cli.main(_argv("plan", workspace, matrix)) == 0
    capsys.readouterr()
    assert cli.main(_argv(command, workspace, matrix, *extra)) == 2
    err = capsys.readouterr().err
    assert said in err, err
    if "9999" in said:
        assert "5001" in err and "5002" in err, err
    if said == "NOPE":
        assert _names(workspace, matrix, "5001")[0] in err, err
    assert stub.invocations == [] and workspace.read_manifest() == []


def test_fr326_a_selected_point_already_recorded_is_refused_as_before(
    tmp_path, monkeypatch, capsys
):
    """P0340-RUN-ONE-POINT (FR-326): a recorded selected point follows the 0.33.0 rules."""
    workspace, matrix, stub = _two_simulations(tmp_path, monkeypatch)
    chosen = _names(workspace, matrix, "5001")[0]
    argv = _argv("run", workspace, matrix, "--sims", "5001", "--points", chosen)
    assert cli.main(_argv("plan", workspace, matrix)) == 0
    assert cli.main(argv) == 0
    capsys.readouterr()
    assert cli.main(argv) == 2
    assert "already in the manifest" in capsys.readouterr().err
    assert len(stub.invocations) == 1
    assert cli.main([*argv, "--resume"]) == 0
    assert len(stub.invocations) == 1, "a resume re-ran a recorded point"


def test_fr326_force_rerun_of_a_selected_point_leaves_an_unselected_record_unchanged(
    tmp_path, monkeypatch, capsys
):
    """P0340-RUN-ONE-POINT (FR-326): --force-rerun with --sims and --points follows 0.33.0.

    Both simulations are run, then 5001 alone is redone through its point name. The record of the
    unselected simulation 5002 is byte for byte what it was, and the redone one ran again.
    """
    workspace, matrix, stub = _two_simulations(tmp_path, monkeypatch)
    assert cli.main(_argv("plan", workspace, matrix)) == 0
    assert cli.main(_argv("run", workspace, matrix)) == 0
    assert len(stub.invocations) == 2
    capsys.readouterr()
    chosen = _names(workspace, matrix, "5001")[0]

    def dump(record):
        return record.model_dump_json()

    other = {r.sim_id: dump(r) for r in workspace.read_manifest() if r.sim_id == "5002"}
    argv = _argv("run", workspace, matrix, "--sims", "5001", "--points", chosen)
    assert cli.main([*argv, "--force-rerun", chosen]) == 0, capsys.readouterr().err
    assert len(stub.invocations) == 3, "the selected point was not redone"
    after = {r.sim_id: dump(r) for r in workspace.read_manifest() if r.sim_id == "5002"}
    assert after == other, "the record of an unselected simulation changed"


def test_fr327_a_second_run_names_the_command_that_continues_it_with_resume(
    tmp_path, monkeypatch, capsys
):
    """P0340-RUN-AGAIN (FR-327): the refusal prints the invoked command plus --resume, and it runs.

    The matrix is run, two points are added, and the run is repeated WITHOUT resume: the status
    stays 2, nothing is staged or run, the message counts the recorded and the new points, and the
    printed command, parsed back as a shell would, is the invoked one with `--resume` added.
    Running it runs exactly the two new points. The control is a run with nothing recorded, which
    says nothing of the kind.
    """
    workspace, matrix = _steady_sweep_matrix(tmp_path)
    stub = CountingStub(WRITES_EVERY_EXPORT)
    monkeypatch.setattr(matrix_module, "LocalExecutor", lambda *args, **kwargs: stub)
    monkeypatch.setattr(LoadsAssessor, "__call__", lambda self, *args: converged(*args))
    text = matrix.read_text(encoding="utf-8")
    matrix.write_text(text.replace("-2.0,0.0,2.0", "0.0"), encoding="utf-8")
    argv = _argv("run", workspace, matrix, "--local")
    assert cli.main(_argv("plan", workspace, matrix)) == 0
    assert cli.main(argv) == 0
    assert len(stub.invocations) == 1
    first = capsys.readouterr()
    assert "To continue" not in first.err, "the control, nothing recorded, printed the hint"
    matrix.write_text(text.replace("-2.0,0.0,2.0", "0.0,2.0,4.0"), encoding="utf-8")
    assert cli.main(_argv("plan", workspace, matrix)) == 0
    capsys.readouterr()
    before = [record.run_id for record in workspace.read_manifest()]
    assert cli.main(argv) == 2
    err = capsys.readouterr().err
    assert "1 point(s) of this run are recorded and 2 would run" in err, err
    (printed,) = [line.strip() for line in err.splitlines() if line.strip().endswith("--resume")]
    words = _words_of(printed)
    assert words == ["pyfs-matrix", *argv, "--resume"], words
    assert len(stub.invocations) == 1 and [r.run_id for r in workspace.read_manifest()] == before
    assert cli.main(words[1:]) == 0
    assert len(stub.invocations) == 2
    ran = [record for record in workspace.read_manifest() if record.run_id not in before]
    assert sum(max(len(record.points_ran or []), 1) for record in ran) == 2, ran


def test_fr327_the_library_refusal_carries_the_counts_a_resume_would_act_on(tmp_path):
    """P0340-RUN-AGAIN (FR-327): the error counts the recorded points and those resume runs.

    Raised in pass one, so nothing is staged: the stub is never started by the refused call.
    """
    from pyflightstream.cases.workflows import workflow_registry
    from pyflightstream.run.matrix import run_matrix
    from pyflightstream.workspace import WorkspaceError

    workspace, matrix = _steady_sweep_matrix(tmp_path)
    text = matrix.read_text(encoding="utf-8")
    keywords = dict(
        name="warm",
        default_fs_version="26.120",
        recipes={},
        recipe_registry=workflow_registry(),
        assess=converged,
    )
    stub = CountingStub(WRITES_EVERY_EXPORT)
    matrix.write_text(text.replace("-2.0,0.0,2.0", "0.0"), encoding="utf-8")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", PyflightstreamWarning)
        run_matrix(matrix, workspace, executor=stub, **keywords)
        matrix.write_text(text.replace("-2.0,0.0,2.0", "0.0,2.0,4.0"), encoding="utf-8")
        with pytest.raises(WorkspaceError) as refused:
            run_matrix(matrix, workspace, executor=stub, **keywords)
    assert (refused.value.recorded, refused.value.would_run) == (1, 2)
    assert len(stub.invocations) == 1


def test_fr327_a_steady_row_recorded_as_one_job_is_counted_by_the_points_it_ran(
    tmp_path, monkeypatch, capsys
):
    """P0340-RUN-AGAIN (FR-327): a recorded job counts as its points, and a grown row adds new.

    A steady row of three points is ONE job, recorded under the job's id with ``points_ran``.
    The row then grows by one point: the refusal must count 3 recorded and 1 that resume would
    run, from the job's points and not from point ids no record carries (which would say 0 and 4).
    The same counts are on the library error, and the printed command carries resume.
    """
    from pyflightstream.cases.workflows import workflow_registry
    from pyflightstream.run.matrix import run_matrix
    from pyflightstream.workspace import WorkspaceError

    workspace, matrix = _steady_sweep_matrix(tmp_path)
    stub = CountingStub(WRITES_EVERY_EXPORT)
    monkeypatch.setattr(matrix_module, "LocalExecutor", lambda *args, **kwargs: stub)
    monkeypatch.setattr(LoadsAssessor, "__call__", lambda self, *args: converged(*args))
    text = matrix.read_text(encoding="utf-8")
    argv = _argv("run", workspace, matrix, "--local")
    assert cli.main(_argv("plan", workspace, matrix)) == 0
    assert cli.main(argv) == 0
    (job,) = workspace.read_manifest()
    assert len(job.points_ran or []) == 3, "the fixture must record one job of three points"
    matrix.write_text(text.replace("-2.0,0.0,2.0", "-2.0,0.0,2.0,4.0"), encoding="utf-8")
    assert cli.main(_argv("plan", workspace, matrix)) == 0
    capsys.readouterr()
    assert cli.main(argv) == 2
    err = capsys.readouterr().err
    assert "3 point(s) of this run are recorded and 1 would run" in err, err
    assert any(line.strip().endswith("--resume") for line in err.splitlines()), err
    keywords = dict(
        name="warm",
        default_fs_version="26.120",
        recipes={},
        recipe_registry=workflow_registry(),
        assess=converged,
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", PyflightstreamWarning)
        with pytest.raises(WorkspaceError) as refused:
            run_matrix(matrix, workspace, executor=stub, **keywords)
    assert (refused.value.recorded, refused.value.would_run) == (3, 1)
    assert len(stub.invocations) == 1


def _words_of(line):
    """Split a printed command the way the shell it was printed for does."""
    import os

    if os.name != "nt":
        return shlex.split(line)
    import ctypes
    from ctypes import wintypes

    count = ctypes.c_int()
    split = ctypes.windll.shell32.CommandLineToArgvW
    split.restype = ctypes.POINTER(wintypes.LPWSTR)
    pieces = split(line, ctypes.byref(count))
    return [pieces[index] for index in range(count.value)]
