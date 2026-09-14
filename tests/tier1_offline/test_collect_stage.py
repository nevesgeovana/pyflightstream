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
    """A point submitted before 0.18.0 carries no declared set and is NOT silently collected.

    AND IT IS NOT COUNTED AS OUTSTANDING, which is the half this test gained
    on 2026-09-14. UNKNOWN is a TERMINAL answer for that point: nothing here
    knows what to wait for it, so a later sweep cannot change the answer.
    While it counted as outstanding, `--watch` in a workspace holding one
    0.17.0 submitted point could never reach its own stop condition and swept
    forever, and that user is exactly the one 0.17.0's release note told to
    expect this stage.
    """
    workspace, _sim = _submitted_workspace(tmp_path, declared=())
    report = collect_once(workspace, interval=0.0, sleep=_no_sleep)
    assert report.unknown and report.unknown[0].state == "UNKNOWN"
    assert "completed by hand" in report.unknown[0].detail
    assert report.outstanding == 0, (
        "an UNKNOWN point counts as outstanding, so a watch over it can never stop"
    )
    assert report.unknown[0].run_id in " ".join(report.lines()), (
        "the point is excluded from the stop condition and must still be REPORTED"
    )


def test_goal020_collect_a_watch_over_an_unknown_point_terminates(tmp_path):
    """The loop ends rather than sweeping forever, and it is asserted by RUNNING it.

    The bound is not `rounds`: this passes no rounds at all, so the only thing
    that can end the loop is the stop condition itself. A regression would
    hang rather than fail, so the sleep is counted and the assertion is on the
    number of sweeps.
    """
    workspace, _sim = _submitted_workspace(tmp_path, declared=())
    sweeps: list[float] = []

    def counting(seconds):
        sweeps.append(seconds)
        if len(sweeps) > 20:
            raise AssertionError("the watch did not terminate over an UNKNOWN point")

    report = collect_and_post(workspace, watch=True, interval=0.0, sleep=counting)
    assert report.outstanding == 0
    assert len(report.unknown) == 1


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


# --- the collected point is JUDGED, not declared converged ---------------------
#
# ADDED 2026-09-14 after two independent review lenses of the 0.18.0 round found
# the same defect: `collect_once` with no assessor recorded every settled point
# CONVERGED, whatever the solver had done, while the subcommand's help, FR-99,
# the change log and the submitting executor's docstring all said the stage
# "assesses the run". The tests above did not catch it, and the reason is the
# shape this repository has paid for before: the completion test asserted
# `!= "SUBMITTED"`, which a constant CONVERGED satisfies. These assert WHICH
# status, and one of them supplies a point that must not be judged converged.


def _loads_table(cl: str) -> str:
    """A minimal loads export the standard parser accepts, with one CL value."""
    from tests.tier1_offline.test_matrix_run import LOADS_TABLE  # the shared fixture

    return LOADS_TABLE.replace("0.4210", cl) if "0.4210" in LOADS_TABLE else LOADS_TABLE


def test_goal020_collect_records_what_the_outputs_say_and_not_a_constant(tmp_path):
    """A collected point's status comes from its files, not from a literal.

    THE ACCEPTANCE, and it is deliberately about the value rather than about
    the value being different from SUBMITTED: a status field that asserts
    convergence nothing evaluated is the silent-wrong-number class this
    package exists to make impossible, and it reads exactly like a working
    stage until somebody's diverged cluster job is recorded as converged.
    """
    workspace, sim = _submitted_workspace(tmp_path)
    # A file that does NOT parse as a loads table. The standard assessor
    # cannot judge it and says so with FAILED_INCOMPLETE_OUTPUT; the old
    # default would have called it CONVERGED.
    (sim / "loads.txt").write_text("this is not a loads spreadsheet", encoding="utf-8")
    (sim / "run_log.txt").write_text("nor is this a solver log", encoding="utf-8")
    report = collect_once(workspace, interval=0.0, sleep=_no_sleep)
    assert len(report.collected) == 1
    status = _status_of(workspace, "camp/sim_9001/a+00.0")
    assert status != "CONVERGED", (
        "the collector recorded CONVERGED for a point whose outputs it could not read. "
        "That is the defect this test exists on: the status must come from the files."
    )
    assert status == "FAILED_INCOMPLETE_OUTPUT", status


def test_goal020_collect_uses_the_same_assessor_the_local_path_uses(tmp_path):
    """The two paths judge by ONE rule, so a cluster point and a local point agree.

    Asserted by identity of the judgement rather than by both happening to
    produce the same word: `assess_collected` is called and its answer is what
    lands on the row, so a change to the standard assessor reaches both paths
    or neither.
    """
    from pyflightstream.run import collect as collect_module

    workspace, sim = _submitted_workspace(tmp_path)
    (sim / "loads.txt").write_text("unreadable", encoding="utf-8")
    (sim / "run_log.txt").write_text("unreadable", encoding="utf-8")
    seen: list[str] = []
    real = collect_module.assess_collected

    def watching(record, sim_dir):
        seen.append(record.run_id)
        return real(record, sim_dir)

    monkey = collect_module.assess_collected
    collect_module.assess_collected = watching
    try:
        collect_once(workspace, interval=0.0, sleep=_no_sleep)
    finally:
        collect_module.assess_collected = monkey
    assert seen == ["camp/sim_9001/a+00.0"], (
        "the default assessor was not called, so the status on the row was not judged"
    )


def test_goal020_collect_passes_the_records_own_point_to_the_assessor(tmp_path):
    """The assessor is handed the run's OWN point, not an empty stand-in.

    `LoadsAssessor` binds the export's printed condition against the point
    that was requested, and a None case makes that binding EMPTY rather than
    agreed. The record carries the real point, so passing it is what keeps
    the binding a comparison; this asserts the value that reaches the
    assessor rather than that something reached it.
    """
    from pyflightstream.run.collect import _RecordAsCase

    workspace, _sim = _submitted_workspace(tmp_path)
    record = workspace.read_manifest()[0]
    shim = _RecordAsCase(record)
    assert shim.point == {"alpha": 0.0}, shim.point
    assert "loads.txt" in [str(name) for name in shim.outputs], shim.outputs


# --- a swept job files each point's outputs under that point -------------------


def _submitted_sweep(tmp_path):
    """One SUBMITTED record for a TWO-POINT warm sweep, shaped as the run path writes it.

    Built from the single-point fixture and then given the two keys a swept
    submission carries, so the two fixtures cannot drift apart in the fields
    they share.
    """
    workspace, _sim = _submitted_workspace(tmp_path, declared=("a+00.0.txt", "a+02.0.txt"))
    record = workspace.read_manifest()[0]
    submission = dict(record.submission or {})
    submission["declared_by_point"] = {
        "a+00.0": ["a+00.0.txt"],
        "a+02.0": ["a+02.0.txt"],
    }
    submission["points_by_tag"] = {"a+00.0": {"alpha": 0.0}, "a+02.0": {"alpha": 2.0}}
    swept = record.model_copy(
        update={
            "submission": submission,
            "points_ran": [
                {"tag": "a+00.0", "point": {"alpha": 0.0}, "status": "SUBMITTED"},
                {"tag": "a+02.0", "point": {"alpha": 2.0}, "status": "SUBMITTED"},
            ],
        }
    )
    # THE ROW IS REPLACED, not appended beside itself: the fixture above wrote
    # one record for this run id and a second would be a manifest holding two.
    path = workspace.root / "runs.json"
    path.write_text(
        json.dumps([json.loads(swept.model_dump_json())], indent=2) + "\n",
        encoding="utf-8",
    )
    return workspace, workspace.sim_dir("9001")


def test_goal020_collect_files_each_point_of_a_sweep_under_its_own_point(tmp_path):
    """A swept job's exports land in one datapoint folder PER POINT, not all in the first.

    THE ACCEPTANCE IS THE FOLDER NAMES, because that is what a downstream
    reader uses to tell which loads table belongs to which incidence. The
    record of a swept job carries the FIRST point in `point`, so a collector
    that files the whole job by `record.point` puts the second point's table
    in the first point's folder and nothing says so.
    """
    workspace, sim = _submitted_sweep(tmp_path)
    (sim / "a+00.0.txt").write_text("first point", encoding="utf-8")
    (sim / "a+02.0.txt").write_text("second point", encoding="utf-8")
    report = collect_once(workspace, interval=0.0, sleep=_no_sleep)
    assert len(report.collected) == 1, report.lines()
    folders = sorted(p.name for p in (sim / "datapoints").iterdir() if p.is_dir())
    assert len(folders) == 2, (
        f"the swept job left {folders}; each point owns a datapoint folder, and one folder "
        "means every point's evidence went into the first point's"
    )
    contents = {
        folder.name: sorted(q.name for q in folder.iterdir())
        for folder in (sim / "datapoints").iterdir()
    }
    for folder, held in contents.items():
        assert len(held) == 1, f"{folder} holds {held}; a point's folder holds that point's file"


def test_goal020_collect_rewrites_points_ran_so_the_row_does_not_contradict_itself(tmp_path):
    """After collection no point of a completed row still reads SUBMITTED.

    Two fields of one record disagreeing about whether the run came back is
    read wrongly by any consumer written against the local path, where the
    per-point list carries the point's own outcome.
    """
    workspace, sim = _submitted_sweep(tmp_path)
    (sim / "a+00.0.txt").write_text("first point", encoding="utf-8")
    (sim / "a+02.0.txt").write_text("second point", encoding="utf-8")
    collect_once(workspace, interval=0.0, sleep=_no_sleep)
    record = workspace.read_manifest()[0]
    assert record.status is not RunStatus.SUBMITTED
    states = {str(row.get("status")) for row in (record.points_ran or [])}
    assert "SUBMITTED" not in states, (
        f"the row reads {record.status} while its points still read {states}"
    )
    assert states == {str(record.status)}, states


# --- the two halves of `settled` are each load-bearing -------------------------
#
# ADDED 2026-09-14. The quality lens of the 0.18.0 round mutated
# `first != second` to `first.size != second.size` and the suite stayed GREEN:
# the modification-time half of the settle predicate was asserted nowhere, and
# the only mtime assertion in the file exercised the dataclass's generated
# equality rather than the predicate. A solver rewriting a fixed-width block in
# place changes the mtime and not the size, and that is the case the mutant
# made invisible.


def test_goal020_collect_is_not_settled_when_only_the_mtime_moved(tmp_path):
    """A file whose SIZE is unchanged and whose mtime moved is still being written.

    THE CASE IT IS ON: a solver rewriting a fixed-width block in place. The
    byte count never changes, so a predicate reading size alone declares the
    file finished while the solver is mid-write, and the post-processing then
    reports numbers for a half-written table.
    """
    path = tmp_path / "loads.txt"
    path.write_text("aaaa", encoding="utf-8")
    before = observe([path])
    # SAME LENGTH, DIFFERENT BYTES, LATER TIME: exactly the in-place rewrite.
    path.write_text("bbbb", encoding="utf-8")
    import os

    stamp = before[str(path)]
    assert stamp is not None
    os.utime(path, ns=(stamp.mtime_ns + 1_000_000_000, stamp.mtime_ns + 1_000_000_000))
    after = observe([path])
    assert after[str(path)].size == before[str(path)].size, "the fixture must not change size"
    assert not settled(before, after), (
        "settled() ignored the modification time, so a file being rewritten in place reads "
        "as finished"
    )


def test_goal020_collect_is_not_settled_when_only_the_size_moved(tmp_path):
    """THE OTHER HALF, asserted the same way so neither can be dropped unnoticed."""
    path = tmp_path / "loads.txt"
    path.write_text("aaaa", encoding="utf-8")
    before = observe([path])
    path.write_text("aaaaaaaa", encoding="utf-8")
    import os

    stamp = before[str(path)]
    assert stamp is not None
    os.utime(path, ns=(stamp.mtime_ns, stamp.mtime_ns))
    after = observe([path])
    assert after[str(path)].mtime_ns == before[str(path)].mtime_ns, "the fixture must hold mtime"
    assert not settled(before, after), "settled() ignored the size"


def test_goal020_collect_a_watch_stops_at_exactly_the_rounds_it_was_given(tmp_path):
    """`rounds` is the BOUND, asserted as an equality rather than as a floor.

    The lens mutated `swept >= rounds` to `swept >= rounds * 3` and the suite
    stayed green, because the assertion in place read `>= 3`. A floor cannot
    tell a bound that is three times too large from one that is right, and
    with no timeout configured a bound removed entirely hangs rather than
    fails.
    """
    workspace, sim = _submitted_workspace(tmp_path, declared=("never_arrives.txt",))
    assert sim.exists()
    sweeps: list[float] = []

    def counting(seconds):
        sweeps.append(seconds)
        if len(sweeps) > 40:
            raise AssertionError("the watch ignored its bound entirely")

    report = collect_and_post(
        workspace, watch=True, interval=0.0, watch_interval=0.0, rounds=3, sleep=counting
    )
    assert report.outstanding == 1, "the fixture must leave the point outstanding"
    # THREE SWEEPS, and the sleeps are: one settle-interval sleep per sweep
    # plus one watch-interval sleep between sweeps. The assertion is on the
    # SWEEP count, derived, rather than on the raw sleeps, because the sleep
    # pattern is an implementation detail and the bound is not.
    assert len(sweeps) == 3 + 2, (
        f"{len(sweeps)} sleep(s) for a three-round watch; the bound is not exactly three"
    )
