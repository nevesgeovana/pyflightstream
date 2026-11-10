"""PFS-2218 (0.57.0): ``pyfs-matrix search-log-batch`` writes a batch point's log from the master.

A SUBMITTED point of a grouped job that has every other output but neither its
log nor its cumulative log gets the segment of its order from the job's master
log, and collect then judges it from that log. The verb previews unless
``--apply`` is given; several candidate master logs, none, or too few points are
named and nothing is written.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pyflightstream.results.log import split_job_log
from pyflightstream.run._mark_converged import mark_converged
from pyflightstream.run._search_log_batch import search_log_batch
from pyflightstream.run.collect import Stamp, collect_once, observe
from pyflightstream.workspace import RunStatus
from tests.support_helpers import no_sleep
from tests.tier1_offline import test_p0370_s1_matrix_home as home

SENTINEL = "SENTINEL-LAST-POINT"
NATIVE = '\n[log]\nexport_log = false\nnative_log = "FTS{sim}.l*"\n'


def _rows(workspace):
    return {record.run_id: record for record in workspace.read_manifest()}


def _scheduler_name(job):
    return f"FTS{job['values'].get('sim', 'x')}.l6902784"


def _job_log_name(job):
    return Path(job["script"]).stem + ".job-log.txt"


def _master_text(job):
    """The job's master log: the fixture's points, repeated to the job's count, then a sentinel."""
    segments = split_job_log(home.A2)
    lines = home.A2.splitlines()
    tail = lines[segments[-1].first_line : segments[-1].last_line + 1]
    text = list(lines)
    for _ in range(job["points"] - len(segments)):
        text += ["Solution cleared. Initialization removed.", *tail]
    text.append(SENTINEL)
    return "\n".join(text) + "\n"


def _lose_last_logs(workspace, name=None):
    """Delete each job's last point's cumulative log and write the job's master log."""
    lasts = {}
    for record in workspace.read_manifest():
        job = record.submission["job"]
        if job["order"] != job["points"]:
            continue
        lasts[record.run_id] = job
        folder = (
            workspace.root / job["dir"] / workspace.sim_dir(record.sim_id).name
        ) / record.submission["working_dir"]
        found = list(folder.glob("*.cumulative-log.txt"))
        assert found
        master = workspace.root / job["dir"] / (name or _job_log_name)(job)
        master.write_text(_master_text(job), encoding="utf-8")
        for path in found:
            path.unlink()
    assert lasts
    return lasts


def _workspace(tmp_path, **kwargs):
    return home.grouped_workspace(
        tmp_path / "w", mode="batch", collect=False, logs=True, ended=True, **kwargs
    )


def _point_log(workspace, record):
    folder = workspace.sim_dir(record.sim_id) / record.submission["working_dir"]
    return sorted(folder.glob("*_log.txt"))


def test_p0570_fix5_the_preview_writes_nothing_and_apply_writes_the_scheduler_log(tmp_path):
    """PFS-2218: a point with no log gets its segment of the job log; the preview writes nothing."""
    workspace = _workspace(tmp_path)
    lasts = _lose_last_logs(workspace)
    assert set(search_log_batch(workspace.root)["would write"]) == set(lasts)
    for run_id in lasts:
        assert not _point_log(workspace, _rows(workspace)[run_id])
    assert set(search_log_batch(workspace.root, apply=True)["written"]) == set(lasts)
    for run_id in lasts:
        logs = _point_log(workspace, _rows(workspace)[run_id])
        assert logs and SENTINEL in logs[0].read_text(encoding="utf-8")


def test_p0570_fix5_the_scheduler_log_is_found_by_its_name(tmp_path):
    """PFS-2218: the scheduler's FTS<first sim>.l* is the master log when no job log exists."""
    workspace = _workspace(tmp_path)
    lasts = _lose_last_logs(workspace, _scheduler_name)
    assert set(search_log_batch(workspace.root, apply=True)["written"]) == set(lasts)
    for run_id in lasts:
        logs = _point_log(workspace, _rows(workspace)[run_id])
        assert logs and SENTINEL in logs[0].read_text(encoding="utf-8")


def test_p0570_fix5_two_candidate_master_logs_are_named_and_master_chooses(tmp_path):
    """PFS-2218: two scheduler logs are named and nothing is written; --master chooses one."""
    workspace = _workspace(tmp_path)
    lasts = _lose_last_logs(workspace, _scheduler_name)
    job = next(iter(lasts.values()))
    (workspace.root / job["dir"] / (_scheduler_name(job) + "9")).write_text("x", encoding="utf-8")
    out = search_log_batch(workspace.root, apply=True)
    assert any(label.startswith("several master logs") for label in out), out
    assert "written" not in out
    for run_id in lasts:
        assert not _point_log(workspace, _rows(workspace)[run_id])
    chosen = search_log_batch(workspace.root, apply=True, master=_scheduler_name(job))
    assert set(chosen["written"]) == set(lasts), chosen


def test_p0570_fix5_no_master_log_is_named_and_nothing_is_written(tmp_path):
    """PFS-2218: a job with no master log is named, and no point of it is written."""
    workspace = _workspace(tmp_path)
    lasts = _lose_last_logs(workspace, _scheduler_name)
    for job in lasts.values():
        (workspace.root / job["dir"] / _scheduler_name(job)).unlink()
    out = search_log_batch(workspace.root, apply=True)
    assert any(label.startswith("no master log") for label in out), out
    assert "written" not in out and "would write" not in out


def test_p0570_fix5_a_master_log_with_too_few_points_is_named(tmp_path):
    """PFS-2218: a master log that holds fewer points than the job is named; nothing is written."""
    workspace = _workspace(tmp_path)
    lasts = _lose_last_logs(workspace)
    for job in lasts.values():
        master = workspace.root / job["dir"] / _job_log_name(job)
        master.write_text(home.A2.split("Solution cleared")[0] + "\n", encoding="utf-8")
    out = search_log_batch(workspace.root, apply=True)
    assert any("has only" in label for label in out), out
    assert "written" not in out


def test_p0570_fix5_a_profile_native_log_is_read_first(tmp_path):
    """PFS-2218: the profile's native_log picks the master log among other FTS logs."""
    workspace = _workspace(tmp_path, profile_tail=NATIVE)
    lasts = _lose_last_logs(workspace, _scheduler_name)
    job = next(iter(lasts.values()))
    (workspace.root / job["dir"] / "FTS9999.l1").write_text("another", encoding="utf-8")
    out = search_log_batch(workspace.root, apply=True)
    assert set(out["written"]) == set(lasts), out


def test_p0570_fix5_the_verb_previews_and_applies_then_collect_judges_the_point(tmp_path, capsys):
    """PFS-2218: the command line; after --apply, collect judges the last point from its log."""
    workspace = _workspace(tmp_path)
    lasts = _lose_last_logs(workspace, _scheduler_name)
    code, said = home.pyfs(["search-log-batch"], workspace.root, capsys)
    assert code == 0, said
    assert f"would write: {len(lasts)}" in said and "preview only" in said, said
    code, said = home.pyfs(["search-log-batch", "--apply"], workspace.root, capsys)
    assert code == 0 and f"written: {len(lasts)}" in said, said
    collect_once(workspace, interval=0.0, sleep=no_sleep)
    for run_id in lasts:
        record = _rows(workspace)[run_id]
        assert record.status is not RunStatus.SUBMITTED, record.status
        assert record.status is not RunStatus.RAN_MISSING_LOG, record.status
        logs = [name for name in record.outputs if name.endswith("_log.txt")]
        assert logs
        body = (workspace.sim_dir(record.sim_id) / logs[0]).read_text(encoding="utf-8")
        assert SENTINEL in body


def test_p0570_fix5_the_first_sims_scheduler_log_beats_another_one(tmp_path):
    """PFS-2218: FTS<first sim>.l* is taken before the only-one search, which would name two."""
    workspace = _workspace(tmp_path)
    lasts = _lose_last_logs(workspace, _scheduler_name)
    for job in lasts.values():
        (workspace.root / job["dir"] / "FTS9999.l1").write_text("another\n", encoding="utf-8")
    out = search_log_batch(workspace.root, apply=True)
    assert set(out["written"]) == set(lasts), out


def test_p0570_fix5_the_job_log_beats_a_scheduler_log(tmp_path):
    """PFS-2218: the job's own log is read before any scheduler log."""
    workspace = _workspace(tmp_path)
    lasts = _lose_last_logs(workspace)
    for job in lasts.values():
        (workspace.root / job["dir"] / _scheduler_name(job)).write_text("x\n", encoding="utf-8")
    out = search_log_batch(workspace.root, apply=True)
    assert set(out["written"]) == set(lasts), out
    for run_id in lasts:
        body = _point_log(workspace, _rows(workspace)[run_id])[0].read_text(encoding="utf-8")
        assert SENTINEL in body


def _other_outputs(workspace, record, job):
    folder = (
        workspace.root / job["dir"] / workspace.sim_dir(record.sim_id).name
    ) / record.submission["working_dir"]
    return [
        folder / name
        for name in record.submission["declared_outputs"]
        if not name.endswith("_log.txt")
    ]


def test_p0570_fix5_a_point_missing_another_output_is_left_alone(tmp_path):
    """PFS-2218: only a point that has every other file gets a log; a running one does not."""
    workspace = _workspace(tmp_path)
    lasts = _lose_last_logs(workspace, _scheduler_name)
    for run_id, job in lasts.items():
        _other_outputs(workspace, _rows(workspace)[run_id], job)[0].unlink()
    for apply in (False, True):
        out = search_log_batch(workspace.root, apply=apply)
        assert set(out["other outputs missing, left alone"]) == set(lasts), out
        assert "written" not in out and "would write" not in out, out
    for run_id in lasts:
        assert not _point_log(workspace, _rows(workspace)[run_id])


def test_p0570_fix5_a_point_already_moved_home_counts_its_outputs_there(tmp_path):
    """PFS-2218: a relocated batch point's outputs are read at home."""
    workspace = _workspace(tmp_path, profile_tail=NATIVE)
    lasts = _lose_last_logs(workspace, _scheduler_name)
    from pyflightstream.workspace._batch_relocate import move_sim

    for record in workspace.read_manifest():
        source = (
            workspace.root / record.submission["job"]["dir"] / workspace.sim_dir(record.sim_id).name
        )
        if source.is_dir():
            move_sim(source, workspace.sim_dir(record.sim_id))
    assert set(search_log_batch(workspace.root, apply=True)["written"]) == set(lasts)


def test_p0570_lreq_a_job_without_end_files_collects_its_settled_last_point(tmp_path):
    """P0570-LREQ-BATCH-END: the final native segment needs no later initialization marker."""
    workspace = home.grouped_workspace(
        tmp_path / "w", mode="batch", collect=False, logs=False, ended=False, profile_tail=NATIVE
    )
    job = workspace.read_manifest()[0].submission["job"]
    master = workspace.root / job["dir"] / _scheduler_name(job)
    master.write_text(_master_text(job), encoding="utf-8")
    collect_once(workspace, interval=0.0, sleep=no_sleep)
    last = next(r for r in workspace.read_manifest() if r.submission["job"]["order"] == 3)
    assert last.status is not RunStatus.SUBMITTED
    assert SENTINEL in _point_log(workspace, last)[0].read_text(encoding="utf-8")
    assert "written" not in search_log_batch(workspace.root, apply=True)


def test_p0570_fix5_a_simulation_no_batch_holds_is_named(tmp_path, capsys):
    """PFS-2218: --sims with an id no batch holds says so, not that nothing is missing a log."""
    workspace = _workspace(tmp_path)
    code, said = home.pyfs(["search-log-batch", "--sims", "9999"], workspace.root, capsys)
    assert code == 0, said
    assert "not a simulation of a batch, left alone: 1" in said and "9999" in said, said
    assert "no SUBMITTED point" not in said, said


def test_p0570_fix5_a_point_that_has_its_log_is_left_alone(tmp_path, capsys):
    """PFS-2218: nothing is missing a log, so the verb says so and writes nothing."""
    workspace = _workspace(tmp_path)
    code, said = home.pyfs(["search-log-batch", "--apply"], workspace.root, capsys)
    assert code == 0, said
    assert "no SUBMITTED point of a batch is missing its log" in said, said


@pytest.mark.parametrize("flag", ["--sims", "--master", "--apply", "--workspace"])
def test_p0570_fix5_the_verb_reads_its_flags(flag):
    """PFS-2218: the verb accepts the options the guides name."""
    from pyflightstream.run.cli import _build_parser

    parser = _build_parser()
    assert parser.parse_args(["search-log-batch"]).subcommand == "search-log-batch"
    verb = parser._subparsers._group_actions[0].choices["search-log-batch"]
    assert flag in verb.format_help()


def _settling_workspace(tmp_path, *, end_file=False, master=True):
    profile = NATIVE + ('job_end_files = ["done.flag"]\n' if end_file else "")
    workspace = home.grouped_workspace(
        tmp_path / "w",
        mode="batch",
        collect=False,
        logs=False,
        ended=False,
        profile_tail=profile,
    )
    last = max(workspace.read_manifest(), key=lambda r: r.submission["job"]["order"])
    job = last.submission["job"]
    folder = workspace.root / job["dir"]
    if master:
        (folder / _scheduler_name(job)).write_text(_master_text(job), encoding="utf-8")
    return workspace, last, folder


def _settling_last(workspace, record):
    return _rows(workspace)[record.run_id]


def test_p0570_lreq_settled_final_point_gets_its_scheduler_segment(tmp_path):
    workspace, last, folder = _settling_workspace(tmp_path)
    pauses = []
    collect_once(workspace, interval=2.0, sleep=pauses.append)
    assert _settling_last(workspace, last).status is not RunStatus.SUBMITTED
    assert SENTINEL in _point_log(workspace, last)[0].read_text(encoding="utf-8")
    assert pauses and all(pause == 2.0 for pause in pauses)
    assert not (folder / workspace.sim_dir(last.sim_id).name).exists()


def test_p0570_lreq_declared_end_file_is_required_before_final_slice(tmp_path):
    workspace, last, folder = _settling_workspace(tmp_path, end_file=True)
    collect_once(workspace, interval=2.0, sleep=lambda _: None)
    assert _settling_last(workspace, last).status is RunStatus.SUBMITTED
    assert not _point_log(workspace, last)
    (folder / "done.flag").write_text("ended", encoding="utf-8")
    collect_once(workspace, interval=2.0, sleep=lambda _: None)
    assert _settling_last(workspace, last).status is not RunStatus.SUBMITTED
    assert SENTINEL in _point_log(workspace, last)[0].read_text(encoding="utf-8")


@pytest.mark.parametrize("changing", ["output", "master", "point-log"])
def test_p0570_lreq_changing_final_files_keep_the_batch_submitted(tmp_path, changing):
    workspace, last, folder = _settling_workspace(tmp_path)
    job = last.submission["job"]
    target = (
        folder / _scheduler_name(job)
        if changing == "master"
        else _other_outputs(workspace, last, job)[0]
    )
    if changing == "point-log":
        target = target.parent / next(
            name for name in last.submission["declared_outputs"] if name.endswith("_log.txt")
        )
        target.write_text("still writing", encoding="utf-8")
    serial = 0

    def observer(paths):
        nonlocal serial
        serial += 1
        seen = dict(observe(paths))
        key = str(target)
        if key in seen:
            stamp = seen[key]
            seen[key] = Stamp(size=stamp.size + serial, mtime_ns=stamp.mtime_ns)
        return seen

    collect_once(workspace, interval=2.0, sleep=lambda _: None, observer=observer)
    assert _settling_last(workspace, last).status is RunStatus.SUBMITTED
    assert (folder / workspace.sim_dir(last.sim_id).name).exists()


def test_p0570_lreq_missing_final_output_keeps_the_batch_submitted(tmp_path):
    workspace, last, folder = _settling_workspace(tmp_path)
    _other_outputs(workspace, last, last.submission["job"])[0].unlink()
    collect_once(workspace, interval=2.0, sleep=lambda _: None)
    assert _settling_last(workspace, last).status is RunStatus.SUBMITTED
    assert (folder / workspace.sim_dir(last.sim_id).name).exists()


def test_p0570_lreq_missing_log_is_reported_and_can_be_marked(tmp_path):
    workspace, last, _folder = _settling_workspace(tmp_path, master=False)
    report = collect_once(workspace, interval=2.0, sleep=lambda _: None)
    judged = _settling_last(workspace, last)
    assert judged.status is RunStatus.RAN_MISSING_LOG
    assert "RAN_MISSING_LOG" in "\n".join(report.lines())
    assert judged.wall_time_s is None and judged.iterations is None
    out = mark_converged(workspace.root, [last.sim_id], reason="outputs checked", apply=True)
    assert out["applied"] and out["marked"]
    marked = _settling_last(workspace, last)
    assert marked.status is RunStatus.CONVERGED
    assert marked.marked["from"] == "RAN_MISSING_LOG"
    assert (workspace.root / out["runs_archived_as"]).is_file()
