"""GOAL-020 item 3: collect-and-post waits for a settled file, then completes the record.

THE OWNER'S ARCHITECTURE OF 2026-09-13, and these tests are written against
the part of it a grep cannot see. It is easy to prove that a function named
``collect`` exists; what has to be proved is that it does NOT fire on a file
that merely appeared, because a file exists before it is finished and the
failure that causes is a table of numbers nobody can tell is half written.

Every test here drives the REAL entry point over a REAL workspace on disk.
The clock is injected so the suite does not sleep, and the observations are
real ``stat`` calls on real files.
"""

from __future__ import annotations

import json

import pytest

from pyflightstream.run.collect import (
    Stamp,
    collect_and_post,
    collect_once,
    observe,
    settled,
)
from pyflightstream.workspace import CampaignWorkspace, RunRecord, RunStatus, WorkspaceError

#: The eight statuses after 0.17.0. Item 3 says a job the scheduler killed
#: takes a FAILED value with the scheduler and the descriptor named, and that
#: NO NINTH is minted, so this list is the contract rather than a snapshot.
CLOSED_SET = {
    "CONVERGED",
    "COMPLETED_MAX_ITER",
    "FAILED_EXECUTION",
    "FAILED_SCRIPT",
    "FAILED_INCOMPLETE_OUTPUT",
    "FAILED_DIVERGED",
    "WALLTIME_REACHED",
    "SUBMITTED",
}


def _no_sleep(_seconds: float) -> None:
    """The clock, injected. A suite that waited two seconds per point is a suite nobody runs."""


def _submitted_workspace(tmp_path, *, declared=("loads.txt", "run_log.txt")):
    """A workspace holding one SUBMITTED record that declares two outputs."""
    workspace = CampaignWorkspace(tmp_path / "camp")
    workspace.init(tmp_path / "camp")
    sim = workspace.sim_dir("9001")
    sim.mkdir(parents=True, exist_ok=True)
    common = dict(
        sim_id="9001",
        matrix_stem="matriz",
        fs_version_requested="26.123",
        fs_build="7012026",
        fs_exe="C:/builds/26123/FlightStream.exe",
        fs_exe_sha256="e" * 64,
        package_version="0.18.0.dev0",
        package_commit="4fd9916",
        package_dirty=False,
        script_path="scripts/point.fs",
        script_sha256="c" * 64,
        inputs_sha256={"10_WING.fsm": "a" * 64},
        raw_flag=False,
        pproc="p001",
        description="SUBMITTED_POINT",
        mach=0.15,
        reference={"SREF": 50.0, "CREF": 2.5, "BREF": 20.0, "XMOM": 9.0},
        executor={"class_name": "SubmittingExecutor", "argv": ["sbatch", "job.sh"]},
    )
    workspace.append_record(
        RunRecord(
            run_id="camp/sim_9001/a+00.0",
            point={"alpha": 0.0},
            status=RunStatus.SUBMITTED,
            outputs=[],
            wall_time_s=None,
            submission={
                "descriptor": "sims/sim_9001/job.sh",
                "profile": "h001",
                "submitted": True,
                "declared_outputs": list(declared),
            },
            **common,
        )
    )
    return workspace, sim


def _status_of(workspace, run_id: str) -> str:
    raw = json.loads(workspace.manifest_path.read_text(encoding="utf-8"))
    return next(row["status"] for row in raw if row["run_id"] == run_id)


# ------------------------------------------------------- the settle predicate


def test_goal020_collect_an_absent_file_is_never_settled(tmp_path):
    """PRESENCE is half the condition, and the half a watcher meets first."""
    there = tmp_path / "there.txt"
    there.write_text("x", encoding="utf-8")
    missing = tmp_path / "missing.txt"
    first = observe([there, missing])
    second = observe([there, missing])
    assert first[str(missing)] is None
    assert not settled(first, second)


def test_goal020_collect_a_growing_file_is_never_settled(tmp_path):
    """THE HAZARD THE OWNER'S DESIGN INHERITS: a file EXISTS before it is finished.

    Both observations see the file. It is still not settled, because its size
    moved between them, and a watcher that fired here would post-process a
    half-written table.
    """
    growing = tmp_path / "loads.txt"
    growing.write_text("partial", encoding="utf-8")
    first = observe([growing])
    growing.write_text("partial and then some more", encoding="utf-8")
    second = observe([growing])
    assert first[str(growing)] is not None
    assert second[str(growing)] is not None
    assert not settled(first, second)


def test_goal020_collect_an_unchanged_file_is_settled(tmp_path):
    quiet = tmp_path / "loads.txt"
    quiet.write_text("done", encoding="utf-8")
    first = observe([quiet])
    second = observe([quiet])
    assert settled(first, second)


def test_goal020_collect_an_empty_declared_set_is_not_settled():
    """A point that declares nothing must not read as collected the instant it is submitted."""
    assert not settled({}, {})


def test_goal020_collect_a_stamp_compares_on_size_and_mtime():
    assert Stamp(size=1, mtime_ns=2) == Stamp(size=1, mtime_ns=2)
    assert Stamp(size=1, mtime_ns=2) != Stamp(size=1, mtime_ns=3)


# ----------------------------------------------------------------- the sweep


def test_goal020_collect_waits_while_an_output_has_not_arrived(tmp_path):
    """The record is NOT touched while a declared output is missing."""
    workspace, sim = _submitted_workspace(tmp_path)
    (sim / "loads.txt").write_text("numbers", encoding="utf-8")
    report = collect_once(workspace, interval=0.0, sleep=_no_sleep)
    assert not report.collected
    assert report.outstanding == 1
    assert "not there yet" in report.waiting[0].detail
    assert _status_of(workspace, "camp/sim_9001/a+00.0") == "SUBMITTED"


def test_goal020_collect_waits_while_an_output_is_still_being_written(tmp_path):
    """Every file is PRESENT and the sweep still waits, which is the whole design."""
    workspace, sim = _submitted_workspace(tmp_path)
    loads = sim / "loads.txt"
    loads.write_text("first", encoding="utf-8")
    (sim / "run_log.txt").write_text("log", encoding="utf-8")

    def _grow(_seconds: float) -> None:
        loads.write_text("first and more", encoding="utf-8")

    report = collect_once(workspace, interval=0.0, sleep=_grow)
    assert not report.collected
    assert report.outstanding == 1
    assert "still changing" in report.waiting[0].detail
    assert _status_of(workspace, "camp/sim_9001/a+00.0") == "SUBMITTED"


def test_goal020_collect_completes_a_settled_point(tmp_path):
    """Present AND settled: the outputs are collected and the record stops saying SUBMITTED."""
    workspace, sim = _submitted_workspace(tmp_path)
    (sim / "loads.txt").write_text("numbers", encoding="utf-8")
    (sim / "run_log.txt").write_text("log", encoding="utf-8")
    report = collect_once(workspace, interval=0.0, sleep=_no_sleep)
    assert len(report.collected) == 1
    assert report.outstanding == 0
    assert _status_of(workspace, "camp/sim_9001/a+00.0") != "SUBMITTED"
    assert report.collected[0].record is not None
    assert report.collected[0].record.outputs


def test_goal020_collect_reads_the_declared_set_off_the_record(tmp_path):
    """The collector waits for what the SUBMISSION declared, not for what a matrix says now.

    A matrix edited between the submission and the collection is the shape
    that made a recorded flight condition read back as a different number in
    a regenerated product. Here the record names one output and the folder
    holds another; the sweep waits, because the record is the authority.
    """
    workspace, sim = _submitted_workspace(tmp_path, declared=("expected.txt",))
    (sim / "something_else.txt").write_text("not what was declared", encoding="utf-8")
    report = collect_once(workspace, interval=0.0, sleep=_no_sleep)
    assert report.outstanding == 1
    assert _status_of(workspace, "camp/sim_9001/a+00.0") == "SUBMITTED"


def test_goal020_collect_says_so_when_a_record_declares_nothing(tmp_path):
    """A point submitted before 0.18.0 carries no declared set and is NOT silently collected."""
    workspace, _sim = _submitted_workspace(tmp_path, declared=())
    report = collect_once(workspace, interval=0.0, sleep=_no_sleep)
    assert report.outstanding == 1
    assert report.waiting[0].state == "UNKNOWN"
    assert "completed by hand" in report.waiting[0].detail


def test_goal020_collect_sweeps_a_workspace_with_nothing_submitted(tmp_path):
    workspace = CampaignWorkspace(tmp_path / "camp")
    workspace.init(tmp_path / "camp")
    report = collect_once(workspace, interval=0.0, sleep=_no_sleep)
    assert report.collected == [] and report.failed == [] and report.outstanding == 0


# ------------------------------------------------------- the manifest contract


def test_goal020_collect_mints_no_ninth_status():
    """0.17.0 spent a value on SUBMITTED; the answer to that question is not a ninth."""
    assert {member.name for member in RunStatus} == CLOSED_SET


def test_goal020_collect_refuses_to_rewrite_a_run_that_finished(tmp_path):
    """The ONE method that rewrites a row refuses every row but a submitted one."""
    workspace, sim = _submitted_workspace(tmp_path)
    (sim / "loads.txt").write_text("numbers", encoding="utf-8")
    (sim / "run_log.txt").write_text("log", encoding="utf-8")
    collect_once(workspace, interval=0.0, sleep=_no_sleep)
    done = workspace.read_manifest()[0]
    with pytest.raises(WorkspaceError) as refusal:
        workspace.complete_submitted_record(done)
    assert "not SUBMITTED" in str(refusal.value)


def test_goal020_collect_refuses_a_run_the_manifest_does_not_hold(tmp_path):
    workspace, _sim = _submitted_workspace(tmp_path)
    stranger = workspace.read_manifest()[0].model_copy(update={"run_id": "camp/sim_9001/nobody"})
    with pytest.raises(WorkspaceError) as refusal:
        workspace.complete_submitted_record(stranger)
    assert "no row with that run_id" in str(refusal.value)


# ------------------------------------------------------------------ the post


def test_goal020_collect_posts_only_where_something_was_collected(tmp_path):
    """A rebuild ARCHIVES what it replaces, so a watch must not post on an empty sweep."""
    workspace, sim = _submitted_workspace(tmp_path)
    posted: list[str] = []
    report = collect_and_post(
        workspace,
        interval=0.0,
        sleep=_no_sleep,
        post=lambda _ws: posted.append("posted"),
    )
    assert report.outstanding == 1
    assert posted == []

    (sim / "loads.txt").write_text("numbers", encoding="utf-8")
    (sim / "run_log.txt").write_text("log", encoding="utf-8")
    report = collect_and_post(
        workspace,
        interval=0.0,
        sleep=_no_sleep,
        post=lambda _ws: posted.append("posted"),
    )
    assert len(report.collected) == 1
    assert posted == ["posted"]


def test_goal020_collect_a_watch_is_bounded_by_its_rounds(tmp_path):
    """The loop around the primitive stops, which is what stops a mistake being endless."""
    workspace, _sim = _submitted_workspace(tmp_path)
    sweeps: list[float] = []
    report = collect_and_post(
        workspace,
        watch=True,
        rounds=3,
        interval=0.0,
        watch_interval=0.0,
        sleep=sweeps.append,
    )
    assert report.outstanding == 1
    # Two observations per sweep plus one wait between sweeps, and it STOPPED.
    assert len(sweeps) >= 3
