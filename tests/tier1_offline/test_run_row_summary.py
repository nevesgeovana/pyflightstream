"""At the end of a run, every row says how many of its planned points ran (0.30.0).

A row of ten planned points once recorded six on an HPC workspace, the run went
on to the next row, and nothing said so until the owner counted the scripts.
Now each row closes with one line, on the terminal and in
``logs/activity.log``, and a row whose planned points have no record is a
warning naming them.
"""

from __future__ import annotations

import pytest

from pyflightstream._errors import PyflightstreamWarning
from pyflightstream.run import run_campaign
from pyflightstream.workspace import CampaignWorkspace
from tests.tier1_offline.test_run_campaign import (
    WRITES_LOADS,
    StubSolver,
    converged,
    make_campaign,
    steady_recipe,
)

ALPHAS = tuple(float(value) for value in range(10))


def _run(tmp_path, workspace):
    return run_campaign(
        make_campaign(tmp_path, alphas=ALPHAS),
        StubSolver(WRITES_LOADS),
        workspace,
        assess=converged,
        recipes={"steady": steady_recipe},
    )


def test_a_complete_row_says_all_executed(tmp_path, capsys):
    workspace = CampaignWorkspace(tmp_path / "camp")
    _run(tmp_path, workspace)
    assert "row 9001: all 10 executed" in capsys.readouterr().err
    log = (workspace.root / "logs" / "activity.log").read_text(encoding="utf-8")
    assert "row 9001: all 10 executed" in log


def test_a_row_with_points_no_record_carries_says_so_and_warns(tmp_path, capsys, monkeypatch):
    """Three points are dropped on the way to the manifest, as the HPC run lost four."""
    workspace = CampaignWorkspace(tmp_path / "camp")
    real = workspace.append_record
    dropped = {"camp/sim_9001/AL+060", "camp/sim_9001/AL+070", "camp/sim_9001/AL+090"}

    def losing(record):
        if record.run_id not in dropped:
            real(record)

    monkeypatch.setattr(workspace, "append_record", losing)
    with pytest.warns(PyflightstreamWarning, match="not attempted") as caught:
        _run(tmp_path, workspace)
    err = capsys.readouterr().err
    assert "row 9001: 7 of 10 point(s) executed, 3 not attempted" in err
    (said,) = [str(w.message) for w in caught if "not attempted" in str(w.message)]
    assert "AL+060, AL+070, AL+090" in said
    log = (workspace.root / "logs" / "activity.log").read_text(encoding="utf-8")
    assert "row 9001: 7 of 10 point(s) executed, 3 not attempted" in log


def test_the_coverage_reads_jobs_and_continuations():
    from pyflightstream.workspace import planned_points_without_record

    planned = ["c/sim_1/A", "c/sim_1/B", "c/sim_2/A", "c/sim_3/A", "c/sim_4/A"]
    rows = [
        {"run_id": "c/sim_1/sweep", "sim_id": "1", "points_ran": [{"tag": "A"}]},
        {"run_id": "c/sim_2/sweep", "sim_id": "2", "points_ran": []},
        {"run_id": "c/sim_3/r20260928T1200/A", "sim_id": "3"},
        {"run_id": "other/sim_4/A", "sim_id": "4"},
        {"deleted_sim": "9", "deleted_run_ids": []},
    ]
    assert planned_points_without_record(planned, rows) == ["c/sim_1/B", "c/sim_4/A"]
