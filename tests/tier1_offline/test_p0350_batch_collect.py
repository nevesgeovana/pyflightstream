"""FR-367 to FR-370: collect over the points of a grouped job (0.35.0).

Hand-built workspaces in the layout of IMPL-0350 sections 4.2, 4.3 and 4.6:
SUBMITTED records carrying ``submission["job"]``, a batch folder
``sims/batch/mtx_b1/`` or a polar sweep folder ``sims/sim_<id>/``, each
point's outputs and its cumulative log (the compacted A2 transcript, two points
of one polar). The clock, the observation and the judgement are injected; no
solver runs.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

from pyflightstream._errors import PyflightstreamWarning
from pyflightstream.results.log import point_log_text, split_job_log
from pyflightstream.run._batch_collect import job_ended
from pyflightstream.run.collect import Stamp, collect_once, observe, settled
from pyflightstream.workspace import CampaignWorkspace, RunRecord, RunStatus
from pyflightstream.workspace.inputs import read_hpc_profile
from tests.tier1_offline.test_goal024_profile_log import LOG_TABLE, _write_profile

LOGS = Path(__file__).parent / "fixtures" / "batch0350" / "logs"
A2 = (LOGS / "A2.cumulative.txt").read_text(encoding="utf-8")
TAGS = ("AL+000", "AL+020")
STATE = {"fired": True, "steps": 30, "stopped_at": {"step": 30, "elapsed_s": 41.5}}


def _no_sleep(_seconds: float) -> None:
    """The clock, injected."""


def _converged(_record, _sim_dir):
    """The judgement, injected: what is tested here is where the files are, not the physics."""
    return RunStatus.CONVERGED, None


def _make_link(target: Path, link: Path) -> None:
    if sys.platform == "win32":
        import _winapi

        _winapi.CreateJunction(str(target), str(link))
    else:
        os.symlink(target, link, target_is_directory=True)


def _listing(root: Path) -> dict[str, tuple[int, int]]:
    """Every entry under ``root`` with size and mtime, never through a link."""
    seen: dict[str, tuple[int, int]] = {}
    for path in sorted(root.iterdir()):
        info = os.lstat(path)
        linked = path.is_symlink() or bool(getattr(info, "st_file_attributes", 0) & 0x400)
        if linked or not path.is_dir():
            seen[path.relative_to(root).as_posix()] = (info.st_size, info.st_mtime_ns)
        else:
            seen.update({f"{path.name}/{k}": v for k, v in _listing(path).items()})
    return seen


def _job(kind: str, order: int) -> dict[str, object]:
    batch = kind == "batch"
    return {
        "kind": kind,
        "name": "BATCH-2006-2006" if batch else "FULL-POLAR",
        "batch_id": 1 if batch else None,
        "label": "mtx_b1" if batch else "2006",
        "dir": "sims/batch/mtx_b1" if batch else "sims/sim_2006",
        "script": "BATCH-2006-2006.txt" if batch else "FULL-POLAR.txt",
        "root": "<machine path>",
        "executor": "local",
        "values": {"sim": "mtx_b1" if batch else "2006", "point": "BATCH-2006-2006"},
        "order": order,
        "points": len(TAGS),
        "receipt_sha256": "d" * 64,
    }


def _record(tag: str, *, job: dict[str, object] | None) -> RunRecord:
    submission: dict[str, object] = {
        "descriptor": None,
        "profile": None,
        "submitted": False,
        "declared_outputs": [f"P2006-{tag}.txt", f"P2006-{tag}_log.txt"],
        "working_dir": f"datapoints/DP-{tag}",
    }
    if job is not None:
        submission["job"] = job
    return RunRecord(
        run_id=f"camp/sim_2006/{tag}",
        point_name=tag,
        sweep_name=tag,
        point={"alpha": 0.0},
        status=RunStatus.SUBMITTED,
        outputs=[],
        wall_time_s=None,
        submission=submission,
        sim_id="2006",
        matrix_stem="mtx",
        fs_version_requested="26.124",
        fs_build="8172026",
        fs_exe="<machine path>/FlightStream.exe",
        fs_exe_sha256="e" * 64,
        package_version="0.35.0.dev0",
        package_commit="69c8416",
        package_dirty=False,
        script_path=f"scripts/P2006-{tag}.txt",
        script_sha256="c" * 64,
        inputs_sha256={"30_BLADE.fsm": "a" * 64},
        raw_flag=False,
        pproc="p001",
        description="GROUPED_POINT",
        mach=0.15,
        reference={"SREF": 1.0, "CREF": 1.0, "BREF": 1.0, "XMOM": 0.0},
        executor={"class_name": "LocalExecutor", "argv": ["FlightStream.exe"]},
    )


def _cumulative(order: int) -> str:
    """The point's own EXPORT_LOG inside the job: the log up to its own end."""
    segments = split_job_log(A2)
    lines = A2.splitlines()
    return "".join(f"{line}\n" for line in lines[: segments[order - 1].last_line + 1])


def _expected_log(order: int) -> str:
    segments = split_job_log(A2)
    return point_log_text(A2, segments[order - 1], polar_start=segments[0])


def _write_point(folder: Path, tag: str, order: int) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"P2006-{tag}.txt").write_bytes(f"loads of {tag}\n".encode())
    (folder / f"P2006-{tag}.cumulative-log.txt").write_bytes(_cumulative(order).encode())


def _workspace(tmp_path: Path, kind: str, *, written=TAGS):
    workspace = CampaignWorkspace(tmp_path / "camp")
    workspace.init(tmp_path / "camp")
    staged = tmp_path / "staged"
    staged.mkdir()
    (staged / "SENTINEL.fsm").write_bytes(b"geometry")
    job_dir = workspace.root / str(_job(kind, 1)["dir"])
    sim = job_dir / "sim_2006" if kind == "batch" else job_dir
    (sim / "scripts").mkdir(parents=True)
    for order, tag in enumerate(TAGS, start=1):
        (sim / "scripts" / f"P2006-{tag}.txt").write_bytes(b"script\n")
        if tag in written:
            _write_point(sim / "datapoints" / f"DP-{tag}", tag, order)
        workspace.append_record(_record(tag, job=_job(kind, order)))
    _make_link(staged, sim / "inputs")
    (job_dir / str(_job(kind, 1)["script"])).write_bytes(b"job script\n")
    return workspace, job_dir, staged


def _growing(tag: str):
    """An observer under which one point's files are still being written."""
    ticks = iter(range(1, 1_000_000))

    def observer(paths):
        seen = observe(paths)
        return {
            name: (Stamp(size=next(ticks), mtime_ns=0) if f"DP-{tag}" in name else stamp)
            for name, stamp in seen.items()
        }

    return observer


def _status(workspace, tag):
    return {r.run_id: r for r in workspace.read_manifest()}[f"camp/sim_2006/{tag}"]


def test_p0350_collect_fr367_copy_while_running_never_touches_the_batch(tmp_path):
    """P0350-COLLECT-COPY-MOVE (FR-367): a settled point is copied home; the batch is only read."""
    requirement = "FR-367"
    workspace, job_dir, staged = _workspace(tmp_path, "batch")
    before = _listing(job_dir)
    report = collect_once(
        workspace, interval=0.0, sleep=_no_sleep, observer=_growing("AL+020"), assessor=_converged
    )
    assert [o.run_id for o in report.collected] == ["camp/sim_2006/AL+000"], report.lines()
    first = _status(workspace, "AL+000")
    assert first.status is RunStatus.CONVERGED, requirement
    assert first.outputs and all("DP-AL+000" in name for name in first.outputs), first.outputs
    home = workspace.sim_dir("2006") / "datapoints" / "DP-AL+000"
    assert (home / "P2006-AL+000_log.txt").read_text(encoding="utf-8") == _expected_log(1)
    assert _status(workspace, "AL+020").status is RunStatus.SUBMITTED, requirement
    assert _listing(job_dir) == before, "the running batch folder was written"
    assert (workspace.sim_dir("2006") / "inputs").resolve() == staged.resolve()
    # The control: the same listing sees a write into the batch folder.
    (job_dir / "sim_2006" / "scripts" / "planted.txt").write_bytes(b"x")
    assert _listing(job_dir) != before


def test_p0350_collect_fr367_move_once_ended_and_reconcile(tmp_path):
    """P0350-COLLECT-COPY-MOVE (FR-367): the end record moves the rest and reconciles by sha256."""
    requirement = "FR-367"
    workspace, job_dir, staged = _workspace(tmp_path, "batch")
    collect_once(
        workspace, interval=0.0, sleep=_no_sleep, observer=_growing("AL+020"), assessor=_converged
    )
    log = workspace.sim_dir("2006") / "datapoints" / "DP-AL+000" / "P2006-AL+000_log.txt"
    stamp = log.stat().st_mtime_ns
    (job_dir / "sim_2006" / "datapoints" / "DP-AL+000" / "P2006-AL+000.txt").write_bytes(b"later")
    (job_dir / "BATCH-2006-2006.end.json").write_bytes(b'{"returncode": 0}\n')
    with pytest.warns(PyflightstreamWarning, match="camp/sim_2006/AL\\+000"):
        report = collect_once(workspace, interval=0.0, sleep=_no_sleep, assessor=_converged)
    assert [o.run_id for o in report.collected] == ["camp/sim_2006/AL+020"], report.lines()
    assert _status(workspace, "AL+020").status is RunStatus.CONVERGED, requirement
    home = workspace.sim_dir("2006") / "datapoints"
    assert (home / "DP-AL+000" / "P2006-AL+000.txt").read_bytes() == b"later", requirement
    assert (home / "DP-AL+020" / "P2006-AL+020_log.txt").read_text(
        encoding="utf-8"
    ) == _expected_log(2)
    assert log.stat().st_mtime_ns == stamp, "an unchanged log is not written again"
    assert not (job_dir / "sim_2006").exists(), requirement
    assert sorted(p.name for p in job_dir.iterdir()) == [
        "BATCH-2006-2006.end.json",
        "BATCH-2006-2006.txt",
    ]
    assert (workspace.sim_dir("2006") / "inputs").resolve() == staged.resolve()
    assert (staged / "SENTINEL.fsm").read_bytes() == b"geometry", requirement


def test_p0350_collect_fr369_not_started_points(tmp_path):
    """P0350-BATCH-RECORDS (FR-369): an ended job's point with no file is FAILED_EXECUTION."""
    requirement = "FR-369"
    workspace, job_dir, _ = _workspace(tmp_path, "batch", written=("AL+000",))
    collect_once(workspace, interval=0.0, sleep=_no_sleep, assessor=_converged)
    assert _status(workspace, "AL+020").status is RunStatus.SUBMITTED, "a running job waits"
    (job_dir / "BATCH-2006-2006.end.json").write_bytes(b'{"returncode": 0}\n')
    report = collect_once(workspace, interval=0.0, sleep=_no_sleep, assessor=_converged)
    second = _status(workspace, "AL+020")
    assert second.status is RunStatus.FAILED_EXECUTION, requirement
    assert second.error == "the job BATCH-2006-2006 ended before this point started"
    assert (second.submission or {})["job"]["not_started"] is True, requirement
    assert [o.run_id for o in report.failed] == ["camp/sim_2006/AL+020"], report.lines()


def test_p0350_collect_fr370_walltime_reached_from_the_points_clock(tmp_path):
    """P0350-BATCH-RECORDS (FR-370): the point's own clock fired, so WALLTIME_REACHED."""
    requirement = "FR-370"
    workspace, job_dir, _ = _workspace(tmp_path, "polar_sweep")
    actions = job_dir / "datapoints" / "DP-AL+000" / "actions"
    actions.mkdir()
    (actions / "pfs_walltime_clock.json").write_text(json.dumps(STATE), encoding="utf-8")
    collect_once(workspace, interval=0.0, sleep=_no_sleep, assessor=_converged)
    first = _status(workspace, "AL+000")
    assert first.status is RunStatus.WALLTIME_REACHED, requirement
    assert first.stopped_at == STATE["stopped_at"], requirement
    assert _status(workspace, "AL+020").status is RunStatus.CONVERGED


def test_p0350_collect_fr370_a_point_run_alone_is_collected_as_in_0_34_0(tmp_path):
    """The control: the same clock state beside a point with no job entry changes nothing."""
    workspace = CampaignWorkspace(tmp_path / "camp")
    workspace.init(tmp_path / "camp")
    folder = workspace.sim_dir("2006") / "datapoints" / "DP-AL+000"
    (folder / "actions").mkdir(parents=True)
    (folder / "actions" / "pfs_walltime_clock.json").write_text(json.dumps(STATE), "utf-8")
    (folder / "P2006-AL+000.txt").write_bytes(b"loads\n")
    (folder / "P2006-AL+000_log.txt").write_bytes(_expected_log(1).encode())
    workspace.append_record(_record("AL+000", job=None))
    sleeps: list[float] = []
    collect_once(workspace, interval=0.0, sleep=sleeps.append, assessor=_converged)
    alone = _status(workspace, "AL+000")
    assert alone.status is RunStatus.CONVERGED and alone.stopped_at is None
    assert sleeps == [0.0], "the default mode takes its one observation pair and no other"


def test_p0350_collect_fr368_native_log_on_a_machine_without_export_log(tmp_path):
    """P0350-COLLECT-LOG-SLICE (FR-368): export_log = false, each point cut from the job's log."""
    requirement = "FR-368"
    workspace, job_dir, _ = _workspace(tmp_path, "batch")
    _write_profile(workspace, LOG_TABLE)
    for tag in TAGS:
        (
            job_dir / "sim_2006" / "datapoints" / f"DP-{tag}" / f"P2006-{tag}.cumulative-log.txt"
        ).unlink()
    (job_dir / "FTSmtx_b1.l3714205").write_bytes(A2.encode())
    (job_dir / "BATCH-2006-2006.end.json").write_bytes(b'{"returncode": 0}\n')
    report = collect_once(workspace, interval=0.0, sleep=_no_sleep, assessor=_converged)
    assert len(report.collected) == 2, report.lines()
    home = workspace.sim_dir("2006") / "datapoints"
    for order, tag in enumerate(TAGS, start=1):
        log = home / f"DP-{tag}" / f"P2006-{tag}_log.txt"
        assert log.read_text(encoding="utf-8") == _expected_log(order), requirement


def test_p0350_collect_ended_evidence(tmp_path):
    """P0350-COLLECT-COPY-MOVE (FR-367): each kind of end evidence alone says ended."""
    requirement = "FR-367"
    workspace, job_dir, _ = _workspace(tmp_path, "batch")
    job = _job("batch", 1)
    kwargs = dict(observer=observe, settled=settled, sleep=_no_sleep, interval=0.0)

    def verdict(profile=None):
        return job_ended(workspace, job, profile=profile, **kwargs)  # type: ignore[arg-type]

    assert not verdict().ended, requirement
    end = job_dir / "BATCH-2006-2006.end.json"
    end.write_bytes(b"{}\n")
    assert verdict().ended and "end record" in verdict().evidence
    end.unlink()
    log = job_dir / "BATCH-2006-2006.job-log.txt"
    log.write_bytes(A2.encode())
    assert verdict().ended and "job-log" in verdict().evidence
    log.unlink()
    _write_profile(workspace, LOG_TABLE + 'job_end_files = ["FTS{sim}.o*"]\n')
    profile = read_hpc_profile(workspace.inputs_dir / "hpc" / "h001.toml")
    (job_dir / "FTS2006.o1").write_bytes(b"the record's sim, not the job's\n")
    assert not verdict(profile).ended, "the glob is formatted with the job's values"
    (job_dir / "FTSmtx_b1.o1").write_bytes(b"job summary\n")
    assert verdict(profile).ended and "FTSmtx_b1.o1" in verdict(profile).evidence
    (job_dir / "FTSmtx_b1.o1").unlink()
    actions = job_dir / "sim_2006" / "datapoints" / "DP-AL+020" / "actions"
    actions.mkdir()
    (actions / "pfs_walltime_clock.json").write_text(json.dumps(STATE), encoding="utf-8")
    assert verdict().ended and "DP-AL+020" in verdict().evidence, requirement


def test_p0350_collect_fr370_a_clock_stopped_point_is_collected_from_its_stamped_exports(tmp_path):
    """P0350-BATCH-RECORDS (FR-370): the stop's exports carry the step stamp; collect adopts them.

    Measured in the dev-wheel rehearsal on 26.124: the job clock's stop wrote
    every output of the current point as ``<stem>_iteration=<step><suffix>``.
    Without adopting them the point waited forever under its plain names.
    """
    requirement = "FR-370"
    workspace, job_dir, _ = _workspace(tmp_path, "polar_sweep")
    folder = job_dir / "datapoints" / "DP-AL+000"
    step = STATE["stopped_at"]["step"]
    plain = sorted(p for p in folder.iterdir() if p.is_file())
    for path in plain:
        path.rename(path.with_name(f"{path.stem}_iteration={step}{path.suffix}"))
    (folder / "actions").mkdir()
    (folder / "actions" / "pfs_walltime_clock.json").write_text(json.dumps(STATE), encoding="utf-8")
    collect_once(workspace, interval=0.0, sleep=_no_sleep, assessor=_converged)
    first = _status(workspace, "AL+000")
    assert first.status is RunStatus.WALLTIME_REACHED, requirement
    assert all(path.is_file() for path in plain), "every declared output under its plain name"
    assert _status(workspace, "AL+020").status is RunStatus.CONVERGED
