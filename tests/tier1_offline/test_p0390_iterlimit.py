"""P0390-ITERLIMIT (FR-434): a steady run at its iteration limit, unsettled, is MAX_ITER_REACHED.

Expected values are worked from the requirement and the fixtures: the steady
loads export prints 312 of a requested 500 and the unsteady one 1575; a log
ending at the requested iteration with a velocity residual of 9.6e-2 is
unsettled against the export's convergence limit of 1e-5.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pyflightstream.run import LoadsAssessor
from pyflightstream.workspace import CampaignWorkspace, RunStatus
from tests.tier1_offline import test_goal031_local_run_log as local_run
from tests.tier1_offline.test_goal028_hpc_log_completeness import _log
from tests.tier1_offline.test_p0370_s1_matrix_home import MATRIX, grouped_workspace, pyfs
from tests.tier1_offline.test_run_campaign import FIXTURES, make_collected

UNSETTLED = "+9.6000000E-2"
STEADY = (FIXTURES / "loads_steady_26.120.txt").read_text(encoding="utf-8")
UNSTEADY = (FIXTURES / "loads_unsteady_26.120.txt").read_text(encoding="utf-8")
COUNTER = "Current solver iteration number:            "


def _at(text: str, counter: int, *, was: str = "312") -> str:
    """The export with its iteration counter replaced."""
    return text.replace(f"{COUNTER}{was}", f"{COUNTER}{counter}")


def _assess(tmp_path: Path, loads: str, log: str | None = None):
    sim_dir = make_collected(tmp_path, "", text=loads)
    if log is not None:
        make_collected(tmp_path, "", name="log.txt", text=log)
    return LoadsAssessor("loads.txt")(None, None, sim_dir)


def test_p0390_iterlimit_a_steady_point_at_the_limit_with_a_log_is_max_iter_reached(tmp_path):
    """P0390-ITERLIMIT (FR-434 R1): log counter at the limit 500, residual above the limit.

    The record states the requested limit and the iterations reached. A mutant
    that keeps the 0.38.0 status fails this test.
    """
    assessment = _assess(tmp_path, _at(STEADY, 500), _log(ends_at=500, final_velocity=UNSETTLED))
    assert assessment.status is RunStatus.MAX_ITER_REACHED, assessment.error
    assert assessment.iterations == 500
    assert assessment.iterations_requested == 500
    note = assessment.residual_note or ""
    assert "500" in note and "iteration limit" in note, note


def test_p0390_iterlimit_a_steady_point_at_the_limit_without_a_log_stays_completed(tmp_path):
    """P0390-ITERLIMIT (FR-434 R2): the footer supplies the counter only, never the verdict.

    A steady export at 500 of 500 and no solver log has no readable residual,
    so the status stays COMPLETED_MAX_ITER and no limit is written. A mutant
    that infers the verdict from the footer alone fails this test.
    """
    assessment = _assess(tmp_path, _at(STEADY, 500))
    assert assessment.status is RunStatus.COMPLETED_MAX_ITER, assessment.error
    assert assessment.iterations == 500
    assert assessment.iterations_requested is None


def test_p0390_iterlimit_a_log_at_the_limit_that_settled_is_converged(tmp_path):
    """P0390-ITERLIMIT (FR-434 R1): the residual settled at the limit, so the point converged."""
    assessment = _assess(tmp_path, _at(STEADY, 500), _log(ends_at=500))
    assert assessment.status is RunStatus.CONVERGED
    assert assessment.iterations_requested is None


def test_p0390_iterlimit_a_point_short_of_the_limit_keeps_the_0_38_status(tmp_path):
    """P0390-ITERLIMIT (FR-434 R2): unsettled at 400 of 500 stays COMPLETED_MAX_ITER.

    A mutant that maps every unsettled steady point to the new status fails
    this test.
    """
    assessment = _assess(tmp_path, _at(STEADY, 400), _log(ends_at=400, final_velocity=UNSETTLED))
    assert assessment.status is RunStatus.COMPLETED_MAX_ITER, assessment.error
    assert "iteration limit" not in (assessment.residual_note or "")
    assert assessment.iterations_requested is None


def test_p0390_iterlimit_an_unsteady_point_at_its_requested_count_stays_completed(tmp_path):
    """P0390-ITERLIMIT (FR-434 R3): an unsteady point whose counter equals the requested 500.

    The time loop reaches its prescribed end, so the counter says nothing; with
    and without a log it stays COMPLETED_MAX_ITER. A mutant that applies the
    new status to an unsteady point fails this test.
    """
    loads = _at(UNSTEADY, 500, was="1575")
    assert "Requested solver iterations                 500" in loads
    assert _assess(tmp_path / "a", loads).status is RunStatus.COMPLETED_MAX_ITER
    with_log = _assess(tmp_path / "b", loads, _log(ends_at=500, final_velocity=UNSETTLED))
    assert with_log.status is RunStatus.COMPLETED_MAX_ITER, with_log.error


@pytest.mark.parametrize("sweep", ["2.0", "-2.0,0.0,2.0"], ids=["alone", "steady-job"])
def test_p0390_iterlimit_a_steady_run_through_the_run_layer(sweep, tmp_path, monkeypatch):
    """P0390-ITERLIMIT (FR-434 R1, R4): a point alone and a steady job's points, through run_matrix.

    The stand-in solver prints the counter at 500 of 500 and writes a log whose
    residual stays above the convergence limit: every point and the job are
    MAX_ITER_REACHED, and each record or `points_ran` entry carries the
    iterations reached, the requested limit and the note naming it. A mutant
    that drops the note or the limit from the points of a steady job fails.
    """
    from tests.tier1_offline.test_matrix_run import HPC_PROFILE

    fixtures = tmp_path / "fixtures"
    fixtures.mkdir()
    (fixtures / "loads_steady_26.120.txt").write_text(_at(STEADY, 500), encoding="utf-8")
    monkeypatch.setattr(local_run, "FIXTURES", fixtures)
    # The stand-in writes the log at its first EXPORT_LOG only; a steady job exports one per point.
    marker = '            printed = "-"' + chr(10)
    every_log = local_run.STUB.replace(marker, "            pass" + chr(10))
    assert every_log != local_run.STUB
    monkeypatch.setattr(local_run, "STUB", every_log)
    _, records, _ = local_run._run(
        tmp_path / "ws",
        monkeypatch,
        cluster=True,
        profile=HPC_PROFILE,
        prints=_log(ends_at=500, final_velocity=UNSETTLED),
        at_log="write",
        sweep=sweep,
    )
    (job,) = records
    assert job.status is RunStatus.MAX_ITER_REACHED, (job.status, job.error)
    entries = job.points_ran or [{"status": str(job.status), **job.model_dump(mode="json")}]
    assert len(entries) == len(sweep.split(","))
    for entry in entries:
        assert entry["status"] == "MAX_ITER_REACHED", entry
        assert entry["iterations"] == 500, entry
        assert entry["iterations_requested"] == 500, entry
        note = entry.get("residual_note") or ""
        assert "iteration limit (500)" in note, entry


def _rows(root: Path) -> list[dict]:
    return json.loads((root / "runs.json").read_text("utf-8"))


def _limit_workspace(tmp_path: Path) -> CampaignWorkspace:
    """A collected workspace whose steady job and points carry what the real assessor wrote.

    The status, counter, requested limit and note are those of the package's
    LoadsAssessor reading a footer at 500 of 500 and a log whose residual is
    above the convergence limit, not a sentence written by hand.
    """
    read = _assess(tmp_path / "read", _at(STEADY, 500), _log(ends_at=500, final_velocity=UNSETTLED))
    assert read.status is RunStatus.MAX_ITER_REACHED, read.error
    workspace = grouped_workspace(tmp_path, mode="alone", logs=False, sims=("7002",))
    rows = _rows(workspace.root)
    fields = {
        "status": str(read.status),
        "iterations": read.iterations,
        "iterations_requested": read.iterations_requested,
        "residual_note": read.residual_note,
    }
    for row in rows:
        row.update(fields)
        for entry in row.get("points_ran") or []:
            entry.update(fields)
    workspace.manifest_path.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    return workspace


def test_p0390_iterlimit_readers_treat_it_as_an_ended_run(tmp_path, capsys):
    """P0390-ITERLIMIT (FR-434 R4): post, status, show and resume read an ended, non-failed run.

    The post writes the products and one WARNING per point naming the limit,
    `run --resume` plans nothing, `status` counts the word apart, and `show`
    names it.
    """
    from tests.tier1_offline.test_p0370_s1_ran_missing_log import _resume

    workspace = _limit_workspace(tmp_path)
    rows = _rows(workspace.root)
    points = [entry for row in rows for entry in (row.get("points_ran") or [row])]
    code, said = pyfs(["post", MATRIX], workspace.root, capsys)
    assert code == 0, said
    folder = workspace.root / "post" / MATRIX
    products = json.loads((folder / "products.json").read_text("utf-8"))
    assert not [key for key in products["skipped"] if key.startswith("runs/")], products["skipped"]
    assert [name for name in products["products"] if name.startswith("polars/P7002")]
    log = (folder / "post.log").read_text("utf-8")
    lines = [line for line in log.splitlines() if "MAX_ITER_REACHED" in line]
    assert len(lines) == len(points), lines
    assert all("iteration limit (500)" in line for line in lines), lines
    code, said = pyfs(["status"], workspace.root, capsys)
    assert code == 0 and "MAX_ITER_REACHED" in said, said
    assert "FAILED" not in said, said
    code, said = pyfs(["show", "7002_1"], workspace.root, capsys)
    assert code == 0 and "MAX_ITER_REACHED" in said, said
    before = workspace.manifest_path.read_bytes()
    assert _resume(workspace) == []
    assert workspace.manifest_path.read_bytes() == before, "run --resume ran an ended point"


def test_p0390_iterlimit_a_0_38_manifest_reads_unchanged(tmp_path):
    """P0390-ITERLIMIT (FR-434 R5): a record written before 0.39.0 is read as it was."""
    workspace = grouped_workspace(tmp_path, mode="alone", logs=False, sims=("7002",))
    rows = _rows(workspace.root)
    for row in rows:
        row["status"] = "COMPLETED_MAX_ITER"
        for entry in row.get("points_ran") or []:
            entry["status"] = "COMPLETED_MAX_ITER"
    workspace.manifest_path.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    before = workspace.manifest_path.read_bytes()
    read = workspace.read_manifest()
    assert {record.status for record in read} == {RunStatus.COMPLETED_MAX_ITER}
    assert workspace.manifest_path.read_bytes() == before


def test_p0390_iterlimit_a_forced_run_at_its_budget_keeps_the_0_38_status(tmp_path):
    """P0390-ITERLIMIT (FR-434 R2): forced iterations run the whole budget by design.

    The threshold is off, so reaching 500 of 500 is not a stop that failed to
    settle; the evidence shows no such stop and the 0.38.0 status is kept.
    """
    forced = STEADY.replace(
        "Force solver to run all iterations           F",
        "Force solver to run all iterations           T",
    )
    assert forced != STEADY
    assessment = _assess(tmp_path, _at(forced, 500))
    assert assessment.status is RunStatus.COMPLETED_MAX_ITER
