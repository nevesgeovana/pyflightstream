"""The grouped run: ``run --batch N`` and ``run --polar-sweep`` (0.35.0).

Pipeline role: the grouped modes reuse the per-point run path unchanged and add
only what is new around it (IMPL-0350 section 1). :func:`run_grouped_matrix`
gates the run on its grouping receipt, hands the campaign loop a
:class:`~pyflightstream.run._batch_exec.GroupingExecutor` and a
:class:`~pyflightstream.run._batch_exec.BatchStagingWorkspace`, so every point
is recorded ``SUBMITTED`` exactly as a submitted point is and every file lands
in its job's folder, then assembles ONE job script per job from the per-point
scripts just written, writes the job's action programs, checks every save and
export target, and launches the job once through the real executor
(:func:`launch_job`). It never posts: every record is ``SUBMITTED`` and
``pyfs-matrix collect`` completes them.
"""

from __future__ import annotations

import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path, PurePath
from typing import Any, Literal

import pyflightstream._textio as _textio
from pyflightstream.cases import CampaignConfigError, SimCase, case_at_point
from pyflightstream.cases._unsteady_actions import (
    UNSTEADY_ACTION_PROGRAM,
    UNSTEADY_ACTION_SCRIPT,
    WALLTIME_CLOCK_PROGRAM,
    WALLTIME_STOP_SCRIPT,
)
from pyflightstream.cases.matrix import MatrixError, read_matrix, refuse_silent_rows_without_default
from pyflightstream.cases.workflows import (
    EXPORT_LOG_VARIABLE,
    JOB_END_SUFFIX,
    JOB_LOG_SUFFIX,
)
from pyflightstream.cases.workflows._batch_actions import (
    JOB_SCHEDULE,
    job_schedule,
    render_job_clock_program,
    render_job_counter_program,
)
from pyflightstream.cases.workflows._batch_script import (
    JobPoint,
    JobPolar,
    JobScript,
    assemble_job,
    job_point,
)
from pyflightstream.run._batch_exec import (
    BatchStagingWorkspace,
    GroupingExecutor,
    JobCollector,
)
from pyflightstream.run._campaign import run_campaign
from pyflightstream.run._executors import (
    PROGRESS_EVERY_DEFAULT,
    ExecutionResult,
    ExecutorConfigurationError,
    Submitting,
)
from pyflightstream.run._grouped import (
    batch_receipt_error,
    grouped_case,
    read_receipt,
    refuse_grouped_options,
)
from pyflightstream.run._ids import CampaignErrors, narrow_to_selection
from pyflightstream.run._plan import plan_campaign
from pyflightstream.run._rebuild import bind_row_builds, campaign_executor, row_versions
from pyflightstream.workspace import CampaignWorkspace, RunRecord, RunStatus
from pyflightstream.workspace._batches import GroupedJob, GroupingReceipt, job_of
from pyflightstream.workspace.hpc import HpcProfile
from pyflightstream.workspace.inputs import hpc_profiles, read_hpc_profile
from pyflightstream.workspace.matrix import ResolvedMatrix, resolve_matrix
from pyflightstream.workspace.naming import PointName

#: The job root a profile that states none takes: the job folder as the workspace sees it.
DEFAULT_JOB_ROOT = "{work_dir}"


@dataclass(frozen=True)
class JobLaunch:
    """What launching one job did.

    Attributes
    ----------
    job : str
        The job's label (``<matrix>_b<ID>``, or the simulation id of a polar sweep).
    result : ExecutionResult or None
        The executor's result; None when the job was refused before the launch.
    refusal : str or None
        Why the job did not launch, or None when it did.
    """

    job: str
    result: ExecutionResult | None
    refusal: str | None


@dataclass(frozen=True)
class _Context:
    """What every job of one grouped run shares."""

    staging: CampaignWorkspace
    receipt: GroupingReceipt
    collector: JobCollector
    cases: Mapping[str, SimCase]
    exports_log: bool
    local: bool


def _target_folder(target: str, *, job_root: PurePath, job_dir: Path) -> Path:
    """Return the workspace-side folder a job's save or export target writes into."""
    path = PurePath(target)
    try:
        return job_dir / path.relative_to(job_root).parent
    except ValueError:
        return Path(path.parent)


def _missing_target_folders(
    targets: Sequence[str], *, job_root: PurePath, job_dir: Path
) -> list[str]:
    """Return every target folder that does not exist, workspace side, as posix text."""
    folders = {_target_folder(target, job_root=job_root, job_dir=job_dir) for target in targets}
    return sorted(folder.as_posix() for folder in folders if not folder.is_dir())


def _end_file(job_dir: Path, script_name: str) -> Path:
    """Return the ``<job stem>.end.json`` of a job run locally."""
    return job_dir / f"{PurePath(script_name).stem}{JOB_END_SUFFIX}"


def launch_job(
    job: GroupedJob,
    script: JobScript,
    *,
    inner: Any,
    root: Path,
    values: Mapping[str, object],
    timeout_s: float | None,
    job_root: PurePath | None = None,
) -> JobLaunch:
    """Launch one assembled job once, through the real executor (FR-361, FR-372, FR-375).

    Every folder a save or export of the job writes into is checked first, on
    the workspace side; a missing one refuses the job and nothing is called. A
    submitting executor is given the job's values and writes the job's
    descriptor in the job folder; a local executor runs ONE solver process for
    the whole job and ``<job stem>.end.json`` is written when it returns.

    Parameters
    ----------
    job : GroupedJob
        The job, from the receipt.
    script : JobScript
        The assembled job script; its file is already written in the job folder.
    inner : Executor
        The executor the job runs through.
    root : Path
        The workspace root.
    values : mapping of str to object
        The job's placeholder values (IMPL-0350 section 8, reading 9).
    timeout_s : float, optional
        The limit of a local job (the receipt's walltime); passed through.
    job_root : PurePath, optional
        The root the job script's paths start with; the job folder by default.

    Returns
    -------
    JobLaunch
        The result, or the refusal.
    """
    job_dir = Path(root) / job.dir
    missing = _missing_target_folders(
        script.targets, job_root=job_root or PurePath(job_dir), job_dir=job_dir
    )
    if missing:
        return JobLaunch(
            job.label, None, f"the folder(s) {', '.join(missing)} the job writes into do not exist"
        )
    script_path = job_dir / PurePath(job.script).name
    if isinstance(inner, Submitting):
        inner.bind_point(values, replace=True)
    try:
        result = inner.run_script(script_path, job_dir, timeout_s)
    except (CampaignConfigError, ExecutorConfigurationError, OSError) as error:
        return JobLaunch(job.label, None, f"{type(error).__name__}: {error}")
    if not isinstance(inner, Submitting):
        _textio.write_json(
            _end_file(job_dir, job.script),
            {
                "job": job.name,
                "return_code": result.return_code,
                "timed_out": result.timed_out,
                "finished_at": result.finished_at or datetime.now(UTC).isoformat(),
            },
        )
        return JobLaunch(job.label, result, None)
    return JobLaunch(job.label, result, result.diagnosis() if result.failed else None)


def _default_version(keywords: Mapping[str, Any]) -> str | None:
    """Return the campaign default version from either keyword ``run_matrix`` takes."""
    stated = keywords.get("default_fs_version")
    return stated if stated is not None else keywords.get("fs_version")


def _bound_matrix(
    path: str | Path, workspace: CampaignWorkspace, receipt: GroupingReceipt, kw: Mapping[str, Any]
) -> ResolvedMatrix:
    """Resolve the matrix, narrowed to the receipt's simulations and the user's points."""
    default = _default_version(kw)
    refuse_silent_rows_without_default(read_matrix(path), default, path)
    resolved = resolve_matrix(
        path,
        workspace,
        name=kw["name"],
        fs_version=default,
        recipes=kw.get("recipes", {}),
        fs_exe=kw.get("fs_exe"),
        ignore_missing_families=kw.get("ignore_missing_families", True),
    )
    sims = [sim for job in receipt.jobs for sim in job.sims]
    resolved = narrow_to_selection(resolved, sims, kw.get("points"), workspace)
    campaign = resolved.campaign
    grouped = campaign.model_copy(update={"sims": [grouped_case(c) for c in campaign.sims]})
    return replace(resolved, campaign=grouped)


def _job_field(record: RunRecord, key: str) -> object:
    """Return one field of a record's job entry, or None for a point run alone."""
    entry: Mapping[str, object] | None = job_of(record)
    return None if entry is None else entry.get(key)


def _supersede_not_started(workspace: CampaignWorkspace, receipt: GroupingReceipt) -> None:
    """Take out the failed records of the points this receipt runs, so they run again.

    A point a previous job never started (D5) and a point whose effective
    record is any FAILED_* status are pending again for a grouped plan; before
    the job runs them, their records leave the manifest for its archive and
    their collected outputs move into the datapoint's ``archive/<stamp>/``, as
    ``--force-rerun`` does for a point run alone.
    """
    planned = {run_id for job in receipt.jobs for run_id in job.points}
    stale = [
        record
        for record in workspace.read_manifest()
        if record.run_id in planned and str(record.status).startswith("FAILED")
    ]
    for record in stale:
        workspace.archive_datapoint(record.sim_id, PointName(record.run_id.rsplit("/", 1)[-1]))
    if stale:
        workspace.supersede_records([record.run_id for record in stale])


def _profile_for(workspace: CampaignWorkspace, inner: Any) -> HpcProfile | None:
    """Return the profile a grouped run reads: the inner's, or the workspace's under --local."""
    profile = getattr(inner, "profile", None)
    if isinstance(profile, HpcProfile):
        return profile
    if getattr(inner, "forced_local", False):
        found = hpc_profiles(workspace.inputs_dir)
        return read_hpc_profile(found[0]) if found else None
    return None


def _job_root(job: GroupedJob, root: Path, profile: HpcProfile | None, submits: bool) -> PurePath:
    """Return the root a job's script names its paths from (reading 3)."""
    work_dir = (root / job.dir).as_posix().rstrip("/")
    # FT-PLAN adds `job_root` to HpcProfile in parallel; read with a default so
    # this holds before and after that merge (the session reconciles at INT).
    template = getattr(profile, "job_root", DEFAULT_JOB_ROOT) if submits else DEFAULT_JOB_ROOT
    return PurePath(str(template).format(work_dir=work_dir, batch=job.label, sim=job.label))


def job_values(job: GroupedJob, *, profile: HpcProfile | None) -> dict[str, object]:
    """Return the placeholders a job's descriptor is formatted with (IMPL-0350 reading 9).

    ``sim`` is the job's FIRST simulation id (a batch runs its polars in order,
    so ``job_name = "FTS{sim}"`` names a batch by the polar it starts with; for a
    polar sweep it is that polar) and ``point`` its name (``BATCH-<a>-<b>``,
    ``FULL-POLAR``), so the profile's ``native_log`` finds the job's log in the
    job's own folder. The batch label ``<matrix>_b<ID>`` is ``batch``. A batch adds
    ``batch`` and ``batch_id``; every job adds
    ``sims``, ``first_sim``, ``last_sim``, ``fs_build`` and ``ncpus``, and the
    walltime in the three spellings a point offers, when the job has one.

    Parameters
    ----------
    job : GroupedJob
        The job, from the receipt.
    profile : HpcProfile, optional
        The profile, whose ``walltime_arithmetic`` says what ``walltime`` carries.

    Returns
    -------
    dict of str to object
        The values; a value the job does not have is omitted, never empty.
    """
    values: dict[str, object] = {
        "sim": job.sims[0] if job.sims else job.label,
        "point": job.name,
        "sims": ",".join(job.sims),
        "first_sim": job.sims[0] if job.sims else "",
        "last_sim": job.sims[-1] if job.sims else "",
        "fs_build": job.fs_build,
        "ncpus": job.ncpus,
    }
    if job.batch_id is not None:
        values.update(batch=job.label, batch_id=job.batch_id)
    if job.walltime_s is not None:
        seconds = profile is not None and profile.walltime_arithmetic == "seconds"
        values["walltime"] = int(job.walltime_s) if seconds else job.walltime_written
        values.update(walltime_s=int(job.walltime_s), walltime_written=job.walltime_written)
    return values


def _homes(receipt: GroupingReceipt, root: Path) -> dict[str, Path]:
    """Return each batched simulation's folder inside its batch; none for a polar sweep."""
    if receipt.mode != "batch":
        return {}
    return {sim: root / job.dir / f"sim_{sim}" for job in receipt.jobs for sim in job.sims}


def _prepare_job_folders(receipt: GroupingReceipt, root: Path) -> None:
    """Create every job folder and its ``actions/`` before anything runs (FR-361)."""
    for job in receipt.jobs:
        (root / job.dir / "actions").mkdir(parents=True, exist_ok=True)


def _exports_log(grouping: GroupingExecutor) -> bool:
    """Whether the machine the jobs run on lets a script export the solver log."""
    if grouping.profile is not None:
        return grouping.profile.export_log
    return bool(getattr(grouping.inner, "export_log", True))


def _point_case(context: _Context, record: RunRecord) -> SimCase:
    """Return the case of one recorded point, as its script was built for it."""
    case = case_at_point(context.cases[record.sim_id], record.point)
    declared = list((record.submission or {}).get("declared_outputs", case.outputs))
    update: dict[str, object] = {"outputs": declared}
    if not context.exports_log:
        update["variables"] = {**case.variables, EXPORT_LOG_VARIABLE: "false"}
    return case.model_copy(update=update)


def _job_points(
    context: _Context, records: Sequence[RunRecord], job_root: PurePath, job_dir: Path
) -> list[JobPoint]:
    """Return the job's points, in run order, from the records just written."""
    points = []
    for record in records:
        sim_dir = context.staging.sim_dir(record.sim_id)
        working = sim_dir / str((record.submission or {})["working_dir"])
        points.append(
            job_point(
                _point_case(context, record),
                run_id=record.run_id,
                text=(sim_dir / str(record.script_path)).read_text(encoding="utf-8"),
                datapoint_dir=job_root / working.relative_to(job_dir),
                version=record.fs_version_requested,
            )
        )
    return points


def _polars(points: Sequence[JobPoint]) -> list[JobPolar]:
    """Group a job's points into its polars, in run order."""
    by_sim: dict[str, list[JobPoint]] = {}
    for point in points:
        by_sim.setdefault(point.sim_id, []).append(point)
    return [JobPolar(sim_id=sim, points=tuple(items)) for sim, items in by_sim.items()]


def _write_job_files(
    job: GroupedJob, job_dir: Path, script: JobScript, points: Sequence[JobPoint]
) -> None:
    """Write the job script, its schedule, its programs and its empty action scripts.

    A steady job (FR-403) registers no action, so it writes its script alone.
    """
    if all(point.steady for point in points):
        _textio.write_text(job_dir / PurePath(job.script).name, script.text)
        return
    deadline = None if job.walltime_s is None else max(job.walltime_s - job.margin_s, 0.0)
    schedule = job_schedule(points, deadline_s=deadline)
    _textio.write_json(job_dir / JOB_SCHEDULE, schedule)
    total = int(str(schedule["total_steps"]))
    _textio.write_text(
        job_dir / UNSTEADY_ACTION_PROGRAM,
        render_job_counter_program(total_steps=total, interpreter=sys.executable),
    )
    _textio.write_text(job_dir / UNSTEADY_ACTION_SCRIPT, "")
    if job.walltime_s is not None:
        _textio.write_text(
            job_dir / WALLTIME_CLOCK_PROGRAM, render_job_clock_program(interpreter=sys.executable)
        )
        _textio.write_text(job_dir / WALLTIME_STOP_SCRIPT, "")
    _textio.write_text(job_dir / PurePath(job.script).name, script.text)


def _assemble(
    context: _Context, job: GroupedJob, records: Sequence[RunRecord], job_root: PurePath
) -> JobScript:
    """Assemble and write one job from the per-point scripts of its records."""
    job_dir = context.staging.root / job.dir
    points = _job_points(context, records, job_root, job_dir)
    stem = PurePath(job.script).stem
    kind: Literal["batch", "polar_sweep"] = (
        "batch" if context.receipt.mode == "batch" else ("polar_sweep")
    )
    script = assemble_job(
        _polars(points),
        kind=kind,
        version=records[0].fs_version_requested,
        job_dir=job_root,
        job_log=job_root / f"{stem}{JOB_LOG_SUFFIX}" if context.exports_log else None,
        walltime=job.walltime_s is not None,
    )
    _write_job_files(job, job_dir, script, points)
    return script


def _refuse_job(
    workspace: CampaignWorkspace, job: GroupedJob, records: Sequence[RunRecord], reason: str
) -> list[RunRecord]:
    """Complete every SUBMITTED record of a job that did not launch as FAILED_EXECUTION."""
    failed = []
    for record in records:
        completed = record.model_copy(
            update={
                "status": RunStatus.FAILED_EXECUTION,
                "error": f"the job {job.name} ({job.label}) was not launched: {reason}",
            }
        )
        workspace.complete_submitted_record(completed)
        failed.append(completed)
    return failed


def _run_job(
    context: _Context, job: GroupedJob, records: Sequence[RunRecord], inner: Any
) -> tuple[JobLaunch, list[RunRecord]]:
    """Assemble, check and launch one job; complete its records FAILED when it did not launch."""
    root = context.staging.root
    job_root = PurePath(context.collector.job_roots[job.label])
    try:
        script = _assemble(context, job, records, job_root)
    except (CampaignConfigError, OSError) as error:
        launch = JobLaunch(job.label, None, f"{type(error).__name__}: {error}")
    else:
        launch = launch_job(
            job,
            script,
            inner=inner,
            root=root,
            values=context.collector.values.get(job.label, {}),
            timeout_s=float(job.walltime_s) if context.local and job.walltime_s else None,
            job_root=job_root,
        )
    if launch.refusal is None:
        return launch, list(records)
    return launch, _refuse_job(context.staging, job, records, launch.refusal)


def _say_job(job: GroupedJob, launch: JobLaunch, count: int, *, local: bool) -> None:
    """Print one line for a job."""
    if launch.refusal is not None:
        print(f"job {job.name} ({job.label}, {count} point(s)) NOT launched: {launch.refusal}")
        return
    verb = "ran on this machine" if local else "submitted"
    print(f"job {job.name} ({job.label}, {count} point(s)) {verb}")


def _records_of(job: GroupedJob, records: Sequence[RunRecord]) -> list[RunRecord]:
    """Return the SUBMITTED records of a job, in run order."""
    return [
        record
        for record in records
        if record.status == RunStatus.SUBMITTED and _job_field(record, "label") == job.label
    ]


def _launch_all(
    context: _Context, records: list[RunRecord], inners: Mapping[str, Any]
) -> list[RunRecord]:
    """Launch every job that holds a point this call recorded; return the records as they end."""
    done: dict[str, RunRecord] = {}
    for job in context.receipt.jobs:
        mine = _records_of(job, records)
        if not mine:
            continue
        launch, ended = _run_job(context, job, mine, inners[job.label])
        done.update({record.run_id: record for record in ended})
        _say_job(job, launch, len(mine), local=context.local)
    print("next: pyfs-matrix collect, then pyfs-matrix post")
    return [done.get(record.run_id, record) for record in records]


def _inner_of(job: GroupedJob, cases: Mapping[str, SimCase], builds: Any, grouping: Any) -> Any:
    """Return the real executor a job launches through: its build's, else the campaign's."""
    build = cases[job.sims[0]].fs_build if job.sims and job.sims[0] in cases else None
    chosen = builds.get(build) if builds and build else None
    return chosen.executor.inner if chosen is not None else grouping.inner


def run_grouped_matrix(
    path: str | Path,
    workspace: CampaignWorkspace,
    *,
    mode: Literal["batch", "polar_sweep"],
    batch: int | None,
    **run_matrix_keywords: Any,
) -> list[RunRecord]:
    """Run a matrix in a grouped mode: one solver job per batch or per polar (FR-351, FR-350).

    In order: the options a grouped run does not take are refused; the
    grouping receipt gates the run; the matrix is resolved and narrowed to the
    receipt; points a previous job never started are superseded (D5); every
    case loses its WALLTIME (the job's clock replaces the point's); the
    campaign pre-flights; every job folder is created; the campaign loop runs
    with the grouping executor and the staging workspace, so every point is
    recorded SUBMITTED; then each job is assembled, checked and launched ONCE.
    Nothing is posted (FR-376).

    Parameters
    ----------
    path : str or Path
        The matrix file.
    workspace : CampaignWorkspace
        The campaign workspace.
    mode : {"batch", "polar_sweep"}
        The grouped mode.
    batch : int or None
        The N of ``--batch N``; None for a polar sweep.
    **run_matrix_keywords
        The keywords :func:`pyflightstream.run.matrix.run_matrix` takes.

    Returns
    -------
    list of RunRecord
        The records of this call: SUBMITTED, or FAILED_EXECUTION for the
        points of a job that did not launch.

    Raises
    ------
    pyflightstream.cases.matrix.MatrixError
        A refused option, a receipt that does not match, or a blocked pre-flight.
    """
    kw = run_matrix_keywords
    refusal = refuse_grouped_options(
        force_rerun=kw.get("force_rerun"),
        force_rerun_all=bool(kw.get("force_rerun_all")),
        sweep_csv=kw.get("sweep_csv"),
    )
    stem = Path(path).stem
    refusal = refusal or batch_receipt_error(
        workspace, path, stem, mode=mode, batch=batch, sims=kw.get("sims"), points=kw.get("points")
    )
    receipt = read_receipt(workspace, stem)
    if refusal is not None or receipt is None:
        raise MatrixError(f"grouped run refused: {refusal}")
    resolved = _bound_matrix(path, workspace, receipt, kw)
    _supersede_not_started(workspace, receipt)
    # THE PRE-FLIGHT ALLOCATES EACH SIMULATION'S FOLDER, so it plans in the
    # staging workspace too: a batched simulation gets no sims/sim_<id>/ here.
    staging = BatchStagingWorkspace(
        workspace.root, workspace.naming, homes=_homes(receipt, workspace.root)
    )
    plan = plan_campaign(
        resolved.campaign,
        staging,
        recipes=kw.get("recipe_registry"),
        versions=row_versions(resolved),
        matrix_path=path,
        write_plan=False,
    )
    if plan.blocked:
        raise MatrixError(
            f"pre-flight blocked {len(plan.blocked)} matrix point(s); nothing was "
            f"executed:\n{plan.summary()}"
        )
    return _run_receipt(path, staging, receipt, resolved, kw)


def _run_receipt(
    path: str | Path,
    workspace: BatchStagingWorkspace,
    receipt: GroupingReceipt,
    resolved: ResolvedMatrix,
    kw: Mapping[str, Any],
) -> list[RunRecord]:
    """Run the campaign loop through the adapters, then launch every job."""
    inner, inner_for = campaign_executor(
        workspace,
        resolved,
        path,
        executor=kw.get("executor"),
        local=bool(kw.get("local")),
        hidden=kw.get("hidden"),
        progress_every=kw.get("progress_every", PROGRESS_EVERY_DEFAULT),
    )
    root = workspace.root
    submits = isinstance(inner, Submitting)
    profile = _profile_for(workspace, inner)
    collector = JobCollector(
        receipt,
        root=root,
        job_roots={job.label: _job_root(job, root, profile, submits) for job in receipt.jobs},
        values={job.label: job_values(job, profile=profile) for job in receipt.jobs},
    )
    grouping = GroupingExecutor(inner, collector, profile=profile)
    campaign, builds = bind_row_builds(
        resolved,
        _default_version(kw),
        grouping,
        lambda exe: GroupingExecutor(inner_for(exe), collector, profile=profile),
    )
    _prepare_job_folders(receipt, root)
    context = _Context(
        staging=workspace,
        receipt=receipt,
        collector=collector,
        cases={case.sim_id: case for case in campaign.sims},
        exports_log=_exports_log(grouping),
        local=not submits,
    )
    inners = {job.label: _inner_of(job, context.cases, builds, grouping) for job in receipt.jobs}
    try:
        records = run_campaign(
            campaign,
            grouping,
            workspace,
            assess=kw["assess"],
            recipes=kw.get("recipe_registry"),
            resume=bool(kw.get("resume")),
            builds=builds,
            name_from=kw.get("name_from"),
            accept_unregistered_build=bool(kw.get("accept_unregistered_build")),
        )
    except CampaignErrors as error:
        error.records = _launch_all(context, list(error.records), inners)
        raise
    return _launch_all(context, records, inners)
