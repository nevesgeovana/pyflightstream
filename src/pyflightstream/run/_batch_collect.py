"""The prepare step of ``collect`` for the points of a grouped job (0.35.0).

Pipeline role: called by :func:`pyflightstream.run.collect.collect_once`
before its per-record loop, and nowhere else. For every SUBMITTED record
that carries a job entry (``submission["job"]``, :func:`job_of`), it decides
whether the job ended (:func:`job_ended`), cuts the job's cumulative log into
each finished point's own log (:func:`pyflightstream.results.log.split_job_log`),
and, for a batch, copies each finished point from ``sims/batch/<label>/`` into
``sims/sim_<id>/`` while the job runs and moves the rest once it ended. After
it, a grouped point's folder and record look exactly like those of a submitted
point that ran alone, and the existing loop completes it unchanged.

A RECORD WITH NO JOB ENTRY IS NOT LOOKED AT. A workspace holding none returns
from :func:`prepare_grouped_points` with its records as given, no observation
taken and no sleep spent, so the default mode's ``collect`` is the 0.34.0 one;
:func:`clock_stop_update` returns ``{}`` for such a record for the same reason.

Semantics, each a test (IMPL-0350 section 4.9): FR-367 (copy while running,
move once ended, reconcile by sha256), FR-368 (the log of each point, cut at the
measured marker, idempotent), FR-369 (a point the job never started) and FR-370
(a grouped point the clock stopped is WALLTIME_REACHED).
"""

from __future__ import annotations

import shutil
from collections.abc import Callable, Collection, Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

import pyflightstream._textio as _textio
from pyflightstream.cases import EXPORT_KINDS
from pyflightstream.cases.workflows import (
    CUMULATIVE_LOG_SUFFIX,
    JOB_END_SUFFIX,
    JOB_LOG_SUFFIX,
    WALLTIME_CLOCK_STATE,
)
from pyflightstream.results.log import point_log_text, split_job_log
from pyflightstream.run._pending import _walltime_stop
from pyflightstream.workspace import (
    SIM_DATAPOINTS_DIR,
    CampaignWorkspace,
    RunRecord,
    RunStatus,
    WorkspaceError,
)
from pyflightstream.workspace._batch_relocate import copy_point, move_sim, relink_inputs
from pyflightstream.workspace._batches import JobEntry, batch_sim_dirs, job_of
from pyflightstream.workspace.hpc import HpcProfile, resolve_hpc_profile

__all__ = [
    "GroupedSweep",
    "JobEndVerdict",
    "clock_stop_update",
    "job_ended",
    "prepare_grouped_points",
]

#: The suffix of a point's declared solver log, read off the export table.
_LOG_SUFFIX = next(suffix for kind, suffix, *_ in EXPORT_KINDS if kind == "log")

Observer = Callable[[Iterable[Path]], Mapping[str, Any]]
Settled = Callable[[Mapping[str, Any], Mapping[str, Any]], bool]


@dataclass(frozen=True)
class JobEndVerdict:
    """Whether a grouped job ended, and the file that says so.

    Attributes
    ----------
    ended : bool
        True when one kind of end evidence was found.
    evidence : str
        The evidence found, or what was looked for when none was.
    """

    ended: bool
    evidence: str


@dataclass(frozen=True)
class GroupedSweep:
    """What the prepare step did.

    Attributes
    ----------
    records : list of RunRecord
        The manifest after the step: read again when the step looked at a
        grouped job, the records given otherwise.
    notes : list of str
        Sentences for the person: a file of a point already completed that
        the move replaced (reading 2), named with the point.
    failed : list of tuple of str
        ``(run_id, detail)`` of every point the step completed as failed (a
        point the job never started) or could not prepare.
    """

    records: list[RunRecord]
    notes: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)


@dataclass(frozen=True)
class _Watch:
    """Two observations of a set of files, ``interval`` apart (collect's own rule)."""

    observer: Observer
    settled: Settled
    sleep: Callable[[float], None]
    interval: float

    def steady(self, paths: list[Path]) -> bool:
        first = self.observer(paths)
        self.sleep(self.interval)
        return self.settled(first, self.observer(paths))


def _job_dir(workspace: CampaignWorkspace, job: JobEntry) -> Path:
    return workspace.root / job["dir"]


def _job_stem(job: JobEntry) -> str:
    return PurePosixPath(job["script"]).stem


def _formatted(pattern: str, job: JobEntry) -> str | None:
    """Format a profile glob with the job's values (reading 9); None when it names another key."""
    try:
        return pattern.format(**job["values"])
    except (KeyError, IndexError, ValueError):
        return None


def _matches(folder: Path, pattern: str | None, job: JobEntry) -> list[Path]:
    glob = _formatted(pattern, job) if pattern else None
    return sorted(path for path in folder.glob(glob) if path.is_file()) if glob else []


def _end_files(job_dir: Path, job: JobEntry, profile: HpcProfile | None) -> str | None:
    """Name the files matching EVERY ``job_end_files`` glob of the profile, or None."""
    patterns = tuple(getattr(profile, "job_end_files", ()) or ())
    matched: list[Path] = []
    for pattern in patterns:
        found = _matches(job_dir, pattern, job)
        if not found:
            return None
        matched += found
    return ", ".join(path.name for path in matched) if matched else None


def _point_folders(workspace: CampaignWorkspace, job: JobEntry) -> list[Path]:
    """Every datapoint folder of a job, where the job is writing them."""
    job_dir = _job_dir(workspace, job)
    if job["kind"] == "batch":
        sims = [
            folder
            for folders in batch_sim_dirs(workspace.root).values()
            for folder in folders
            if folder.parent == job_dir
        ]
    else:
        sims = [job_dir]
    return sorted(p for sim in sims for p in (sim / SIM_DATAPOINTS_DIR).glob("*") if p.is_dir())


def _fired_point(workspace: CampaignWorkspace, job: JobEntry, watch: _Watch) -> str | None:
    """Name a point whose own clock state fired and whose files settled, or None."""
    for folder in _point_folders(workspace, job):
        if _walltime_stop(folder / WALLTIME_CLOCK_STATE) is None:
            continue
        files = [path for path in folder.iterdir() if path.is_file()]
        if watch.steady(files):
            return f"the clock of {folder.name} fired and its files settled"
    return None


def job_ended(
    workspace: CampaignWorkspace,
    job: JobEntry,
    *,
    profile: HpcProfile | None,
    observer: Observer,
    settled: Settled,
    sleep: Callable[[float], None],
    interval: float,
) -> JobEndVerdict:
    """Say whether a grouped job ended, from files only (section 8, reading 1).

    The package never asks the scheduler. Evidence, in this order, any one
    enough: the local end record ``<stem>.end.json``; the job's final log
    ``<stem>.job-log.txt``, present and settled; every ``job_end_files`` glob
    of the HPC profile matching in the job folder, formatted with the job's
    ``values``; a point's own clock state saying it fired, with that point's
    files settled.

    Parameters
    ----------
    workspace : CampaignWorkspace
        The workspace the job belongs to.
    job : JobEntry
        The job entry of one of its records.
    profile : HpcProfile or None
        The workspace's HPC profile, or None.
    observer, settled, sleep, interval
        Collect's own observation, injected.

    Returns
    -------
    JobEndVerdict
        Ended or running, with the evidence.
    """
    job_dir = _job_dir(workspace, job)
    watch = _Watch(observer, settled, sleep, interval)
    end = job_dir / f"{_job_stem(job)}{JOB_END_SUFFIX}"
    if end.is_file():
        return JobEndVerdict(True, f"the local end record {end.name}")
    log = job_dir / f"{_job_stem(job)}{JOB_LOG_SUFFIX}"
    if log.is_file() and watch.steady([log]):
        return JobEndVerdict(True, f"the job's log {log.name}, settled")
    matched = _end_files(job_dir, job, profile)
    if matched:
        return JobEndVerdict(True, f"the job_end_files of the HPC profile: {matched}")
    fired = _fired_point(workspace, job, watch)
    if fired:
        return JobEndVerdict(True, fired)
    return JobEndVerdict(
        False,
        "running: no end record, no settled job log, no job_end_files match, no fired clock",
    )


def clock_stop_update(record: RunRecord, work_dir: Path, status: RunStatus) -> dict[str, object]:
    """Return the fields a grouped point the clock stopped is completed with (FR-370).

    Parameters
    ----------
    record : RunRecord
        The SUBMITTED record being completed.
    work_dir : Path
        Where its files are, the point's datapoint folder.
    status : RunStatus
        The status the collected outputs earned.

    Returns
    -------
    dict of str to object
        ``{}`` for a point run alone (no job entry), so the default mode's
        collect is unchanged; ``{}`` for a failure or a clock that did not
        fire; otherwise ``{"stopped_at": ..., "status": WALLTIME_REACHED}``,
        read as the local path reads a stopped point.
    """
    if job_of(record) is None or str(status).startswith("FAILED"):
        return {}
    stopped = _walltime_stop(work_dir / WALLTIME_CLOCK_STATE)
    if stopped is None:
        return {}
    return {"stopped_at": stopped, "status": RunStatus.WALLTIME_REACHED}


@dataclass(frozen=True)
class _Point:
    """One SUBMITTED point of a job, where its files are and where its log goes."""

    record: RunRecord
    job: JobEntry
    sim: Path
    work: Path
    target: Path
    log_name: str | None
    batch_sim: Path | None


def _declared(record: RunRecord) -> list[str]:
    names = (record.submission or {}).get("declared_outputs")
    return [str(name) for name in names] if isinstance(names, (list, tuple)) else []


def _point(
    workspace: CampaignWorkspace, record: RunRecord, job: JobEntry, *, in_batch: bool
) -> _Point:
    working = str((record.submission or {}).get("working_dir") or "")
    sim = workspace.sim_dir(record.sim_id)
    batch_sim = _job_dir(workspace, job) / sim.name if in_batch else None
    logs = [name for name in _declared(record) if name.endswith(_LOG_SUFFIX)]
    return _Point(
        record=record,
        job=job,
        sim=sim,
        work=(batch_sim or sim) / working,
        target=sim / working,
        log_name=logs[0] if logs else None,
        batch_sim=batch_sim,
    )


def _log_source(point: _Point, job_dir: Path, profile: HpcProfile | None) -> Path | None:
    """Return the cumulative log the point's segment is cut from, or None when there is none yet.

    On a machine whose profile states ``export_log = false``, the job's native
    log (the profile's ``native_log``, formatted with the job's values); else
    the point's own ``<stem>.cumulative-log.txt`` beside its outputs.
    """
    if profile is not None and not profile.export_log:
        found = _matches(job_dir, profile.native_log, point.job)
        return found[0] if len(found) == 1 else None
    if point.log_name is None:
        return None
    return point.work / f"{point.log_name[: -len(_LOG_SUFFIX)]}{CUMULATIVE_LOG_SUFFIX}"


def _waited(point: _Point, source: Path | None) -> list[Path]:
    """Return the files a copy waits for: the outputs but the log, and the log's source."""
    translated = {
        str(item.get("dat"))
        for item in point.record.surface_translations or []
        if isinstance(item, Mapping)
    }
    names = [
        name
        for name in _declared(point.record)
        if not name.endswith(_LOG_SUFFIX) and name not in translated
    ]
    return [point.work / name for name in names] + ([source] if source is not None else [])


def _write_log(point: _Point, source: Path, *, complete: bool, start: int) -> None:
    """Write the point's own log under its declared name, only when the bytes differ."""
    text = source.read_bytes().decode("utf-8", errors="replace")
    segments = split_job_log(text)
    index = point.job["order"] - 1
    if point.log_name is None or index >= len(segments):
        return
    segment = segments[index]
    if not (segment.complete or complete):
        return
    polar = segments[start - 1] if 0 < start <= len(segments) else segment
    body = point_log_text(text, segment, polar_start=polar)
    target = point.target / point.log_name
    if not target.is_file() or target.read_bytes() != body.encode("utf-8"):
        _textio.write_text(target, body)


@dataclass
class _Job:
    """One grouped job of the sweep: its entry, its records, and the step's context."""

    job: JobEntry
    members: list[RunRecord]
    profile: HpcProfile | None
    watch: _Watch
    notes: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)

    def polar_start(self, record: RunRecord) -> int:
        """Return the order of the first point of the record's polar (its simulation)."""
        orders = [
            entry["order"]
            for member in self.members
            if member.sim_id == record.sim_id and (entry := job_of(member)) is not None
        ]
        return min(orders) if orders else 1


def _not_started(
    workspace: CampaignWorkspace, point: _Point, source: Path | None, job: _Job
) -> None:
    """Complete a point of an ended job that left no file and no stop (FR-369, D5)."""
    files = [*_waited(point, source)]
    if any(path.exists() for path in files):
        return
    if _walltime_stop(point.work / WALLTIME_CLOCK_STATE) is not None:
        return
    record = point.record
    error = f"the job {point.job['name']} ended before this point started"
    submission = dict(record.submission or {})
    submission["job"] = {**point.job, "not_started": True}
    failed = record.model_copy(
        update={"status": RunStatus.FAILED_EXECUTION, "error": error, "submission": submission}
    )
    workspace.complete_submitted_record(failed)
    job.failed.append((record.run_id, error))


def _adopt_stop_exports(point: _Point, source: Path | None) -> None:
    """Give a clock-stopped point its outputs under their declared names (FR-370).

    The job's clock writes the CURRENT point's exports from a solver action, and
    an export run from an action is stamped ``<stem>_iteration=<step><suffix>``
    (measured on 26.124 in the dev-wheel rehearsal: every output of the stopped
    point, its ``.fsm`` and its cumulative log carried the stamp of the step the
    clock fired at). Each declared output missing under its plain name is copied
    from that stamped file, so the point is collected as the stop left it; the
    stamped file stays, and nothing is done for a point whose own clock did not
    fire or whose stamped file is absent.
    """
    stopped = _walltime_stop(point.work / WALLTIME_CLOCK_STATE)
    step = (stopped or {}).get("step")
    if step is None:
        return
    for path in _waited(point, source):
        stamped = path.with_name(f"{path.stem}_iteration={step}{path.suffix}")
        if not path.exists() and stamped.is_file():
            shutil.copy2(stamped, path)


def _sweep_point(workspace: CampaignWorkspace, point: _Point, job: _Job, *, ended: bool) -> None:
    """Copy (a running batch) and slice the log of one point once its files settled."""
    job_dir = _job_dir(workspace, point.job)
    source = _log_source(point, job_dir, job.profile)
    if ended:
        _adopt_stop_exports(point, source)
    if (point.log_name is not None and source is None) or not job.watch.steady(
        _waited(point, source)
    ):
        if ended:
            _not_started(workspace, point, source, job)
        return
    if point.batch_sim is not None:
        copy_point(point.batch_sim, point.sim, point.target.name)
        relink_inputs(point.batch_sim, point.sim)
    if source is not None:
        # A point's own cumulative copy is exported at its end, so its segment
        # is complete; the job's native log only once a later marker follows.
        own = source.name.endswith(CUMULATIVE_LOG_SUFFIX)
        start = job.polar_start(point.record)
        _write_log(point, source, complete=ended or own, start=start)


def _move_job(workspace: CampaignWorkspace, job: _Job, sims: set[str]) -> None:
    """Move every simulation of an ended batch home, naming what replaced a copy (reading 2)."""
    job_dir = _job_dir(workspace, job.job)
    for sim_id in sorted(sims):
        sim = workspace.sim_dir(sim_id)
        report = move_sim(job_dir / sim.name, sim)
        for name in report.replaced:
            judged = [
                member.run_id
                for member in job.members
                if member.sim_id == sim_id
                and member.status is not RunStatus.SUBMITTED
                and name.startswith(str((member.submission or {}).get("working_dir") or "-"))
            ]
            job.notes.append(
                f"WARNING: {sim.name}/{name} changed after it was copied and the job's file "
                "replaced the copy"
                + (f"; {', '.join(judged)} was completed from the earlier copy" if judged else "")
            )


def _sweep_job(workspace: CampaignWorkspace, job: _Job, submitted: list[RunRecord]) -> None:
    """Prepare every SUBMITTED point of one job: ended or running, move or copy, then slice."""
    verdict = job_ended(
        workspace,
        job.job,
        profile=job.profile,
        observer=job.watch.observer,
        settled=job.watch.settled,
        sleep=job.watch.sleep,
        interval=job.watch.interval,
    )
    in_batch = job.job["kind"] == "batch"
    if in_batch and verdict.ended:
        _move_job(workspace, job, {record.sim_id for record in submitted})
        in_batch = False
    for record in sorted(submitted, key=lambda r: (job_of(r) or {"order": 0})["order"]):
        entry = job_of(record)
        if entry is not None:
            point = _point(workspace, record, entry, in_batch=in_batch)
            _sweep_point(workspace, point, job, ended=verdict.ended)


def _jobs_of(records: list[RunRecord]) -> dict[tuple[str, str], list[RunRecord]]:
    """Every record that carries a job entry, by its job (folder and name)."""
    jobs: dict[tuple[str, str], list[RunRecord]] = {}
    for record in records:
        entry = job_of(record)
        if entry is not None:
            jobs.setdefault((entry["dir"], entry["name"]), []).append(record)
    return jobs


def prepare_grouped_points(
    workspace: CampaignWorkspace,
    records: list[RunRecord],
    *,
    sims: Collection[str] | None,
    observer: Observer,
    settled: Settled,
    sleep: Callable[[float], None],
    interval: float,
) -> GroupedSweep:
    """Prepare the SUBMITTED points of every grouped job before collect's own loop.

    Parameters
    ----------
    workspace : CampaignWorkspace
        The workspace being collected.
    records : list of RunRecord
        Its manifest, as just read.
    sims : collection of str or None
        ``collect --sims``: only the points of these simulations are
        prepared, and only their folders are moved (FR-307); None for all.
    observer, settled, sleep, interval
        Collect's own observation, injected.

    Returns
    -------
    GroupedSweep
        The manifest after the step, its notes and its failures.
    """
    watch = _Watch(observer, settled, sleep, interval)
    jobs = _jobs_of(records)
    pending = {
        key: [
            r
            for r in members
            if r.status is RunStatus.SUBMITTED and (sims is None or r.sim_id in sims)
        ]
        for key, members in jobs.items()
    }
    if not any(pending.values()):
        return GroupedSweep(records=records)
    profile = resolve_hpc_profile(workspace.inputs_dir)
    notes: list[str] = []
    failed: list[tuple[str, str]] = []
    for key, submitted in sorted(pending.items()):
        entry = job_of(submitted[0]) if submitted else None
        if entry is None:
            continue
        job = _Job(job=entry, members=jobs[key], profile=profile, watch=watch)
        try:
            _sweep_job(workspace, job, submitted)
        except (OSError, WorkspaceError) as error:
            job.failed += [
                (r.run_id, f"the grouped job {entry['name']} could not be prepared: {error}")
                for r in submitted
            ]
        notes += job.notes
        failed += job.failed
    return GroupedSweep(records=workspace.read_manifest(), notes=notes, failed=failed)
