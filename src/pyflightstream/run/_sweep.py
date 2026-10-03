"""One steady row of several points run as one solver job.

Private to :mod:`pyflightstream.run`. :func:`_execute_sweep` renders the
row's single script, runs or submits it once in the simulation folder and
lands one record per point of the row, each judged by the assessor on the
loads of its own step. It shares the pending files and the declared logs
with the point path and sits above it in the package order.
"""

from __future__ import annotations

import warnings
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pyflightstream

# The writer is looked up on its module, not bound here, so the point path
# and the sweep path reach one function through one name (and a test that
# replaces it replaces it for both).
import pyflightstream.run._pending as _pending
from pyflightstream._errors import (
    PyflightstreamError,
    PyflightstreamWarning,
)
from pyflightstream.cases import (
    Campaign,
    CampaignConfigError,
    SimCase,
    case_at_point,
    point_name,
    sweep_name,
)
from pyflightstream.cases.workflows import (
    build_steady_sweep,
    rotor_machs,
)
from pyflightstream.results import (
    translate_surface_exports,
)
from pyflightstream.run._assessment import (
    OutcomeAssessor,
    worse_of,
)
from pyflightstream.run._continuation import (
    _refuse_an_import_count_nothing_logs,
)
from pyflightstream.run._executors import (
    _LOG_OUTPUT_SUFFIX,
    ExecutionResult,
    Executor,
    LocalExecutor,
    _submission_record,
    _with_the_profile_s_log,
    bind_submission_values,
    invocation_record,
)
from pyflightstream.run._identity import (
    _file_digest,
    package_vcs_state,
)
from pyflightstream.run._ids import (
    _job_run_id,
    _point_names,
)
from pyflightstream.run._pending import (
    _declared_logs,
    _descriptor_of,
    _run_log_text,
    _write_probe_points,
)
from pyflightstream.run._points import (
    _NO_JOB_LOG_NOTE,
    _no_local_log_verdict,
    _PointProgress,
    _reference_block,
    _sections_layout,
    _translation_problems,
)
from pyflightstream.run._step_exports import untranslated_surfaces
from pyflightstream.run._wake_edge_verdict import (
    actuator_profile_verdict,
    collected_log_texts,
    wake_edge_import_verdict,
    with_wake_edge_verdict,
)
from pyflightstream.script import Script
from pyflightstream.workspace import (
    MANIFEST_SCHEMA,
    CampaignWorkspace,
    MissingOutputsError,
    NamingTemplateError,
    RunRecord,
    RunStatus,
    WorkspaceError,
)
from pyflightstream.workspace.naming import (
    PointName,
    submitted_by,
    sweep_file_stem,
)


def _job_rotor_mach(
    case: SimCase, points: Sequence[Mapping[str, float]]
) -> dict[str, dict[str, object]] | None:
    """Return a steady job's rotor and disc Mach numbers, keyed by point name (0.30.0, M1)."""
    by_point: dict[str, dict[str, object]] = {}
    for point in points:
        machs = rotor_machs(case_at_point(case, point))
        if machs:
            by_point[point_name(case, point)] = {mach.alias: mach.record() for mach in machs}
    return by_point or None


@dataclass(kw_only=True)
class _SweepJob:
    """Inputs and phase results of one ordered execution."""

    campaign: Campaign
    canonical: str
    fs_exe: str | Path
    fs_version: str
    fs_version_source: str
    case: SimCase
    pending: list[tuple[dict[str, float], str]]
    preparation_error: str | None
    inputs_sha256: dict[str, str]
    staged_geometry: str | None
    name_from: str | None
    executor: Executor
    workspace: CampaignWorkspace
    sim_dir: Path
    assess: OutcomeAssessor
    cold: bool
    progress: _PointProgress | None
    base: dict[str, Any] = field(init=False)
    points: list[dict[str, float]] = field(init=False)
    point_cases: list[tuple[dict[str, float], str, SimCase]] = field(init=False)
    script: Script = field(init=False)
    rendered: str = field(init=False)
    script_path: Path = field(init=False)
    probe_points_file: str | None = field(init=False)
    result: ExecutionResult = field(init=False)
    ran: list[dict] = field(init=False)
    worst: RunStatus = field(init=False)
    collected_all: list[str] = field(init=False)
    error_lines: list[str] = field(init=False)
    collected_by_tag: dict[str, list[str]] = field(init=False)
    failed_tags: dict[str, str] = field(init=False)
    job_warnings: list[str] = field(init=False)
    reported: list[tuple[str, str | None, str | None]] = field(init=False)
    cannot_log: bool = field(init=False)
    printed: str = field(init=False)
    excused: set[str] = field(init=False)


def _execute_sweep(
    *,
    campaign: Campaign,
    canonical: str,
    fs_exe: str | Path,
    fs_version: str,
    fs_version_source: str,
    case: SimCase,
    pending: list[tuple[dict[str, float], str]],
    preparation_error: str | None,
    inputs_sha256: dict[str, str],
    staged_geometry: str | None,
    name_from: str | None = None,
    executor: Executor,
    workspace: CampaignWorkspace,
    sim_dir: Path,
    assess: OutcomeAssessor,
    cold: bool,
    progress: _PointProgress | None = None,
) -> RunRecord:
    """Take every point of a steady row through ONE process to ONE record.

    FR-95. The shape is the predecessor's own
    steady recipe and the reason it is one record is
    that it is one process: the wall time in this record is a measurement
    rather than a share of one, and a job is what a cluster queues.

    WHAT THE JOB RECORD CARRIES that a point record does not:
    :attr:`RunRecord.job_id` and :attr:`RunRecord.points_ran`, the points in
    the order they ran with the status each ended in. The record's own
    status is the WORST of them, because a job with one diverged point is
    not a converged job.

    WHAT THE PER-POINT FOLDERS DO NOT LOSE: each point still collects into
    its own ``datapoints/DP-<tag>/``. The predecessor already wrote one
    folder per point from inside a single script, so what changed is the
    number of processes and not the number of folders.
    """
    job = _SweepJob(
        campaign=campaign,
        canonical=canonical,
        fs_exe=fs_exe,
        fs_version=fs_version,
        fs_version_source=fs_version_source,
        case=case,
        pending=pending,
        preparation_error=preparation_error,
        inputs_sha256=inputs_sha256,
        staged_geometry=staged_geometry,
        name_from=name_from,
        executor=executor,
        workspace=workspace,
        sim_dir=sim_dir,
        assess=assess,
        cold=cold,
        progress=progress,
    )
    if (record := _prepare_sweep_script(job)) is not None:
        return record
    if (record := _write_sweep_script(job)) is not None:
        return record
    if (record := _run_sweep_solver(job)) is not None:
        return record
    if (record := _collect_sweep_outputs(job)) is not None:
        return record
    if (record := _assess_sweep_points(job)) is not None:
        return record
    return _record_sweep_outcome(job)


def _prepare_sweep_script(job: _SweepJob) -> RunRecord | None:
    """Prepare sweep script."""
    package_commit, package_dirty = package_vcs_state()
    run_id = _job_run_id(job.campaign, job.case)
    job.points = [point for point, _ in job.pending]
    job.base = {
        "run_id": run_id,
        "sim_id": job.case.sim_id,
        "point": dict(job.points[0]),
        # A JOB'S NAME IS ITS SWEEP'S, and it is written to `point_name` as
        # well: the field is what every reader of a record takes the name
        # from, collect included, so a job record that left it empty would
        # be refused as written before 0.21.0 while being one of this
        # version's own. The points it ran carry their own names.
        "point_name": sweep_name(job.case),
        "sweep_name": sweep_name(job.case),
        "job_id": run_id,
        "matrix_stem": job.campaign.matrix_stem,
        "fs_version_requested": job.canonical,
        "package_version": pyflightstream.__version__,
        "package_commit": package_commit,
        "package_dirty": package_dirty,
        # v0.23.0 item 12. CAPTURED HERE because this is the only moment it
        # is knowable: who submitted a run cannot be recovered afterwards.
        "submitted_by": submitted_by(),
        "recipe": job.case.recipe,
        # A JOB'S RECIPE IS THE RUN TYPE, which has no user function behind
        # it and therefore no source to digest. The field is carried empty
        # rather than left out, so a reader of the manifest sees the same
        # shape on every record.
        "recipe_sha256": None,
        "fs_exe": str(job.fs_exe),
        "fs_exe_sha256": _file_digest(job.fs_exe),
        "fs_version_source": job.fs_version_source,
        "manifest_schema": MANIFEST_SCHEMA,
        "inputs_sha256": dict(job.inputs_sha256),
        "campaign_name_from": job.name_from,
        "pproc": job.case.pproc_id,
        "velocity_requested_m_s": job.case.velocity,
        "inventory_source": job.case.inventory_source,
        "mesh_import": None
        if job.case.mesh_import is None
        else job.case.mesh_import.model_dump(mode="json", exclude_none=True),
        "motions": [dict(record) for record in job.case.motions],
        "point_name_template": job.workspace.naming.point_name,
        "description": job.case.description or None,
        "mach": job.case.mach,
        "reference": _reference_block(job.case),
        # THE SAME PROVENANCE A POINT RECORD CARRIES. A job is one process
        # over several points of ONE row, so every one of these is a
        # property of the row and is the same for all of them; leaving
        # them out made a job record unable to say whether its state was a
        # wind tunnel's or an altitude's, which its own guard reported.
        "flight_condition": dict(job.case.flight_condition),
        "flight_condition_defaults": dict(job.case.flight_condition_defaults),
        "flight_condition_defaults_from": job.case.flight_condition_defaults_from,
        "density_kg_m3": None if job.case.fluid is None else job.case.fluid.density_kg_m3,
        "temperature_k": None if job.case.fluid is None else job.case.fluid.temperature_k,
        "viscosity_pa_s": None if job.case.fluid is None else job.case.fluid.viscosity_pa_s,
        "density_source": None if job.case.fluid is None else job.case.fluid.source,
        "reference_length_m": None if job.case.fluid is None else job.case.fluid.reference_length_m,
        "waived_commands": [],
        "raw_commands": [entry.model_dump(mode="json") for entry in job.case.raw_commands],
        "aliases": {name: list(members) for name, members in job.case.aliases.items()},
        # Both are REQUIRED on a record and both are only known once the
        # script is built, so they carry the empty answer until then: a
        # record that never got as far as a script is a record whose script
        # has no digest and whose raw flag is false, and saying so is not
        # the same as leaving the field out.
        "script_sha256": "",
        "raw_flag": False,
        # 0.30.0 (M1): each point's rotors and discs, keyed by the POINT'S NAME
        # on a job record, because the numbers move with the point;
        # `RunRecord.as_points` hands each point its own. None where no point
        # carries any.
        "rotor_mach": _job_rotor_mach(job.case, job.points),
    }
    if job.progress is not None:
        job.progress.base = job.base
    if job.preparation_error is not None:
        return RunRecord(**job.base, status=RunStatus.FAILED_SCRIPT, error=job.preparation_error)

    # One case per point, differing only in the point and the names it
    # exports; everything the shared preamble reads is the same on all of
    # them, which is what makes them one script.
    job.point_cases = []
    for point in job.points:
        try:
            stem, outputs = _point_names(job.campaign, job.case, point, job.workspace)
        except NamingTemplateError as exc:
            return RunRecord(**job.base, status=RunStatus.FAILED_SCRIPT, error=str(exc))
        update: dict[str, object] = {"outputs": outputs}
        if job.staged_geometry is not None:
            update["geometry"] = job.staged_geometry
        job.point_cases.append(
            (
                point,
                stem,
                _with_the_profile_s_log(case_at_point(job.case, point, **update), job.executor),
            )
        )

    job.script = Script(version=job.fs_version)
    # G02: the job runs in the simulation folder, which no other simulation
    # shares, so the node file its one script imports is named there.
    job.script.working_dir = str(job.sim_dir)
    try:
        build_steady_sweep([pc for _, _, pc in job.point_cases], job.script, cold=job.cold)
        # G02: the switch is the row's, so the first point's case states it.
        _refuse_an_import_count_nothing_logs(job.point_cases[0][2], job.script, job.executor)
    except Exception as exc:  # a build failure is the job's failure
        return RunRecord(
            **job.base,
            status=RunStatus.FAILED_SCRIPT,
            error=f"{type(exc).__name__}: {exc}",
        )
    return None


def _write_sweep_script(job: _SweepJob) -> RunRecord | None:
    """Write sweep script."""
    job.base["probe_field_layout"] = list(job.script.probe_field_layout) or None
    job.base["surface_probe_layout"] = list(job.script.surface_probe_layout) or None
    job.base["frame_motions"] = job.script.frame_motions or None
    job.base["custom_field_coverage"] = job.script.custom_field_coverage
    job.base["freestream_units"] = (
        job.case.variables.get("FREESTREAM_UNITS") or job.case.freestream_units
    )
    setup = job.script.solver_setup
    if setup is not None:
        job.base["solver_setup"] = setup.model_dump(mode="json")
    # R03 of 0.27.0: the names the script was built over, as the point path
    # records them; the post reads a section selection over them.
    if job.script.boundary_inventory is not None:
        job.base["inventory"] = list(job.script.boundary_inventory)
    # WHICH ROWS OF THE SECTIONS EXPORT ARE WHICH SURFACE, recorded as the
    # point path records them (0.27.0). The one-job path recorded no layout
    # since 0.24.0, so the post refused the per-distribution split of every
    # steady row of several points. The builder creates the distributions
    # once, for every point of the job, so one layout is every point's; the
    # empty one where the job creates none (`_sections_layout`).
    layout = _sections_layout(job.script)
    if layout is not None:
        job.base["sections_layout"] = layout
    # G45: every point's Tecplot surface, written from its VTK after the job.
    job.base["surface_translations"] = [
        dict(translation) for translation in job.script.surface_translations
    ] or None
    # THE HOUSE CONVENTION FOR A SWEEP, not a name of this function's own.
    # A per-polar product table is named by the point name with the swept
    # variable written literally as `sweep`, and a job's script is about
    # exactly the same thing, so it is named the same way:
    # P5001-M090AL+sweepBE+000 (0.21.0).
    job_stem = sweep_file_stem(job.case.sim_id, sweep_name(job.case))
    job.rendered = job.script.render()
    job.script_path, script_sha = job.workspace.write_script(
        job.case.sim_id, f"{job_stem}.txt", job.rendered
    )
    job.base["script_path"] = str(Path(job.script_path).relative_to(job.sim_dir).as_posix())
    job.base["script_sha256"] = script_sha
    job.base["raw_flag"] = job.script.raw_flag
    job.base["march_strategy"] = job.script.march_strategy
    # FR-91 ON THE SWEEP PATH, which lost it. The point path writes where the
    # script put its probe points and names the file on the record; the one-job
    # path did neither, so a steady row of several points with a volume section
    # recorded no positions, its probe table read FRAME NA, and the post refused
    # every point's sampled field as differing from its recorded frame (row 5007
    # of the licensed matrix, 0.29.0). The layout is the row's and the builder
    # records it once for the whole job, so one file serves every point, as it
    # does for the points of a row run one by one. A collision with a user's
    # file is this job's failure, recorded as the point path records it.
    try:
        job.probe_points_file = _write_probe_points(
            job.sim_dir, job.case.sim_id, job.script.probe_points
        )
    except PyflightstreamError as exc:
        return RunRecord(
            **job.base,
            status=RunStatus.FAILED_SCRIPT,
            error=f"{type(exc).__name__}: {exc}",
        )
    if job.probe_points_file is not None:
        job.base["probe_points_file"] = job.probe_points_file

    # PYFS-006 ON THE SWEEP PATH, which lost it. `_execute_point` refuses
    # declared outputs that already exist in the simulation folder before
    # the solver runs, because collection asks only whether a declared
    # output EXISTS and cannot tell a file this solver wrote from one that
    # was already there. The sweep path started the solver without it, so
    # after an interrupted run a leftover export was collected and
    # assessed as fresh evidence, and its digest recorded as this run's.
    # Found by the independent Codex review of `main`, 2026-09-13
    # (GEO-047-C03).
    #
    # EVERY POINT'S OUTPUTS, checked before the shared script runs,
    # because one script writes all of them and a refusal after it has
    # started is a refusal that spent the seat.
    return None


def _run_sweep_solver(job: _SweepJob) -> RunRecord | None:
    """Run sweep solver."""
    stale = sorted(
        {
            name
            for _, _, point_case in job.point_cases
            for name in point_case.outputs
            if (job.sim_dir / name).exists()
        }
    )
    if stale:
        return RunRecord(
            **job.base,
            status=RunStatus.FAILED_INCOMPLETE_OUTPUT,
            error=(
                f"declared output(s) {', '.join(stale)} already exist in the simulation "
                "folder before this job ran, so collecting them would attribute somebody "
                "else's file to this run. Every point of this sweep shares the folder and "
                "one script writes all of them, so this is checked for the whole job "
                "before the solver starts. Archive the simulation (pyfs-workspace archive "
                "<root> <sim_id>) or remove the leftovers, then re-run."
            ),
        )

    # FR-99. THE JOB'S values, not a point's: a steady row is ONE job, so
    # the descriptor names the sweep and carries the row's clock and
    # processor count. `bind_submission_values` reads them off the case
    # and a local executor has no such method and is handed nothing.
    # G02, and PFS-2031.13 on this path too: the files the script parked are
    # written before the solver starts, and the data files' digests join the
    # job's inputs. This path wrote none of them until 0.27.0. One that
    # shares its name with another input is refused here, before the job.
    try:
        written = _pending._write_pending_files(
            job.script,
            job.sim_dir,
            case=job.case,
            recorded=job.inputs_sha256,
            run_writes=(
                Path(job.script_path),
                *(
                    [job.sim_dir / job.probe_points_file]
                    if job.probe_points_file is not None
                    else []
                ),
                *_descriptor_of(job.executor, job.sim_dir),
            ),
        )
    except CampaignConfigError as exc:
        return RunRecord(
            **job.base,
            status=RunStatus.FAILED_SCRIPT,
            error=f"{type(exc).__name__}: {exc}",
        )
    if written:
        job.base["inputs_sha256"] = {**job.base["inputs_sha256"], **written}
    bind_submission_values(job.executor, job.case, job.point_cases[0][2])
    if job.progress is not None:
        job.progress.solver_started = True
    job.result = job.executor.run_script(
        job.script_path, working_dir=job.sim_dir, timeout_s=job.case.solver.timeout_s
    )
    job.base["argv"] = list(job.result.argv)
    job.base["cwd"] = job.result.cwd
    job.base["timeout_s"] = job.result.timeout_s
    job.base["executor"] = invocation_record(job.executor, job.result)
    job.base["started_at"] = job.result.started_at
    job.base["finished_at"] = job.result.finished_at
    # FR-99, and the same reason as the point path: the descriptor exists
    # before the scheduler is called, so a rejected submission must keep it.
    submitted = _submission_record(job.executor)
    if job.result.failed:
        return RunRecord(
            **job.base,
            status=RunStatus.FAILED_EXECUTION,
            wall_time_s=job.result.wall_time_s,
            error=job.result.diagnosis(),
            submission=submitted,
        )
    # FR-99. A SUBMITTED JOB HAS NO OUTPUTS YET. The scheduler has taken
    # the whole sweep and no point of it has run, so every point is
    # pending: the record says SUBMITTED, names where the job went, and
    # carries the points it will run rather than points it ran.
    if submitted is not None:
        return RunRecord(
            **job.base,
            status=RunStatus.SUBMITTED,
            wall_time_s=None,
            outputs=[],
            # The whole sweep is ONE job and one script, so the declared
            # set is every point's outputs together: the collector waits
            # for the job, not for a point of it.
            submission={
                **submitted,
                "declared_outputs": [name for _, _, pc in job.point_cases for name in pc.outputs],
                # AND THE SAME SET SPLIT BY POINT, because the two questions
                # are different. The flat list above is what the COLLECTOR
                # WAITS FOR: the whole sweep is one job and one script, so the
                # job is finished when all of it has landed. This mapping is
                # what the collector FILES BY: each point's evidence belongs
                # alone in its own datapoint folder, which is the rule
                # `collect_outputs` states and the rule the local sweep pays
                # two passes to honour. Without it the collector had only the
                # first point's tag to hand and filed every point's exports
                # under it, reintroducing on the cluster path the defect the
                # local path carries a comment about: an assessor reading a
                # sibling point's file and reporting the run against the wrong
                # incidence. Found by the interface lens of the 0.18.0 release
                # round, 2026-09-14.
                "declared_by_point": {
                    point_name(job.case, point): [str(name) for name in pc.outputs]
                    for point, _, pc in job.point_cases
                },
                "points_by_tag": {
                    point_name(job.case, point): dict(point) for point, _, _ in job.point_cases
                },
                # G02: the points the job's one script imports. The job writes
                # one log with one import line, so every point is held to this
                # number and it is never multiplied by the points.
                **(
                    {"wake_edge_points": job.script.wake_edge_points}
                    if job.script.wake_edge_points is not None
                    else {}
                ),
                # G06: every file the job was told to write a point's log to,
                # whatever its name; the collector reads the four lines in each.
                "declared_logs": list(
                    dict.fromkeys(
                        name
                        for _, _, pc in job.point_cases
                        for name in _declared_logs(pc, job.rendered)
                    )
                ),
            },
            points_ran=[
                {
                    "tag": point_name(job.case, point),
                    "point": dict(point),
                    "status": str(RunStatus.SUBMITTED),
                }
                for point, _, _ in job.point_cases
            ],
        )
    job.base["wall_time_s"] = job.result.wall_time_s

    # EVERY POINT IS COLLECTED AND ASSESSED, and a point that fails does not
    # stop the ones after it: they have already run, their files are on
    # disk, and throwing them away because a sibling failed would spend the
    # seat twice.
    # TWO PASSES, AND THE ORDER IS THE WHOLE OF IT. Every point of a case
    # writes into the SAME simulation folder, and collection is what moves
    # each point's files into its own datapoint folder. Assessing point one
    # while points two and three are still lying in that folder made the
    # assessor read a file from another operating point and report the run
    # against the wrong incidence: "alpha requested +2.0000, exported ...".
    #
    # So EVERY point is collected first, which empties the shared folder,
    # and only then is any point assessed. The point path never met this
    # because one process wrote one point.
    return None


def _collect_sweep_outputs(job: _SweepJob) -> RunRecord | None:
    """Collect sweep outputs."""
    job.ran = []
    job.worst = RunStatus.CONVERGED
    job.collected_all = []
    job.error_lines = []
    job.collected_by_tag = {}
    job.failed_tags = {}
    # 0.30.0: a point whose only missing outputs are surfaces the package failed
    # to translate keeps its assessment; the job's record says so, per point.
    job.job_warnings = []
    #: What each assessed point read as the solver's build and version.
    job.reported = []
    # 0.27.0: ON A MACHINE THAT CANNOT EXPORT THE LOG, run locally, no point's
    # declared log is written and none is missing. What the solver printed is
    # the whole job's and no single point's, and a job log judged as a point's
    # would end at the last point's iteration; so each point is judged from its
    # loads export, the job's record says why, and the printed output is read
    # for the trailing-edge count the one script imported, as a job's is.
    job.cannot_log = isinstance(job.executor, LocalExecutor) and not job.executor.export_log
    job.printed = job.result.captured_output() if job.cannot_log else ""
    # G45: EVERY POINT'S TECPLOT FROM ITS VTK, where the job wrote them, before
    # collection files each point's outputs in its own folder.
    if job.base.get("surface_translations"):
        job.base["surface_translations"] = translate_surface_exports(
            job.sim_dir,
            job.base["surface_translations"],  # type: ignore[arg-type]
        )
    job.excused = {
        name
        for _, _, point_case in job.point_cases
        for name in point_case.outputs
        if job.cannot_log
        and name.endswith(_LOG_OUTPUT_SUFFIX)
        and not (job.sim_dir / name).is_file()
    }
    for point, _stem, point_case in job.point_cases:
        tag = point_name(job.case, point)
        try:
            job.collected_by_tag[tag] = job.workspace.collect_outputs(
                job.case.sim_id,
                # ABSOLUTE, as the point path passes them: the names on the
                # case are relative to the execution directory and the
                # collector is handed paths, not names.
                [job.sim_dir / name for name in point_case.outputs if name not in job.excused],
                datapoint=PointName(tag),
            )
        except MissingOutputsError as exc:
            # FILED, LISTED AND HASHED, and the point still fails (0.27.0),
            # unless all it misses is the package's own translation (0.30.0).
            job.collected_by_tag[tag] = exc.collected
            owned = [
                entry
                for entry in job.base.get("surface_translations") or []  # type: ignore[attr-defined]
                if isinstance(entry, Mapping) and entry.get("dat") in point_case.outputs
            ]
            untranslated = untranslated_surfaces(owned, exc.missing, exc.collected)
            if untranslated is None:
                job.failed_tags[tag] = str(exc) + _translation_problems(owned)
            else:
                for line in untranslated:
                    job.job_warnings.append(f"{tag}: {line}")
                    warnings.warn(f"{tag}: {line}", PyflightstreamWarning, stacklevel=2)
        except (WorkspaceError, CampaignConfigError) as exc:
            job.failed_tags[tag] = str(exc)
    return None


def _assess_sweep_points(job: _SweepJob) -> RunRecord | None:
    """Assess sweep points."""
    for point, _stem, point_case in job.point_cases:
        tag = point_name(job.case, point)
        if tag in job.failed_tags:
            entry: dict[str, object] = {
                "tag": tag,
                "point": dict(point),
                "status": str(RunStatus.FAILED_INCOMPLETE_OUTPUT),
            }
            if job.collected_by_tag.get(tag):
                entry["outputs"] = list(job.collected_by_tag[tag])
                job.collected_all.extend(job.collected_by_tag[tag])
            job.ran.append(entry)
            job.worst = RunStatus.FAILED_INCOMPLETE_OUTPUT
            job.error_lines.append(f"{tag}: {job.failed_tags[tag]}")
            continue
        collected = job.collected_by_tag[tag]
        assessment = job.assess(point_case, job.result, job.sim_dir)
        job.reported.append((tag, assessment.fs_build, assessment.fs_version_reported))
        # G02. The job's one script imported the trailing edges once, and each
        # point is held to that count through the log it collected, else the
        # job's own.
        log_text = _run_log_text(job.sim_dir, collected, assessment.log_file_used, job.result) or (
            job.printed or None
        )
        status, error = with_wake_edge_verdict(
            assessment.status,
            assessment.error,
            _no_local_log_verdict(job.script.wake_edge_points, log_text, _NO_JOB_LOG_NOTE)
            if job.cannot_log
            else wake_edge_import_verdict(job.script.wake_edge_points, log_text),
        )
        # G06. A point whose log says the solver could not use its actuator
        # disc's profile file ran on with a loading that is not the file's. Every
        # collected log is read for it, a log that is no residual history too,
        # and a log is every file the script or LOG_OUTPUT names as one.
        status, error = with_wake_edge_verdict(
            status,
            error,
            actuator_profile_verdict(
                log_text,
                job.result.log_text,
                job.printed,
                *collected_log_texts(
                    job.sim_dir, collected, _declared_logs(point_case, job.rendered)
                ),
            ),
        )
        job.collected_all.extend(collected)
        job.ran.append(
            {
                "tag": tag,
                "point": dict(point),
                "status": str(status),
                "outputs": list(collected),
                "iterations": assessment.iterations,
                "residual": assessment.residual,
            }
        )
        if str(status).startswith("FAILED"):
            job.error_lines.append(f"{tag}: {error or status}")
        # THE WORST, BY A STATED ORDER, and it was the LAST failing point
        # until 2026-09-13: each failure simply overwrote the variable, so
        # a sweep whose first point DIVERGED and whose third left an
        # incomplete output recorded the third, and a reader triaging by
        # status was pointed at the wrong point (the QA lens). `points_ran`
        # carried each point's own status either way, so nothing was lost;
        # what was wrong was the job's headline.
        job.worst = worse_of(job.worst, status)
    return None


def _record_sweep_outcome(job: _SweepJob) -> RunRecord:
    """Record sweep outcome."""
    job.base["points_ran"] = job.ran
    # THE BUILD THAT RAN, stamped on the job as the point path stamps it on a
    # point. The one-job record left both fields empty, so the post refused the
    # velocity convention of every sampled field of a steady job for want of a
    # build (post/field_frames.py), while the same row run point by point
    # passed. One process ran every point, so every point read the same build;
    # points that read different ones mean the record cannot say which
    # executable produced its evidence, and that is recorded as the job's
    # failure with the readings named rather than settled by picking one.
    # A point whose log stated no build is not a different build, and is left
    # out of the comparison rather than counted as a disagreement.
    for key, index in (("fs_build", 1), ("fs_version_reported", 2)):
        readings = {entry[0]: entry[index] for entry in job.reported if entry[index] is not None}
        if len(set(readings.values())) == 1:
            job.base[key] = next(iter(readings.values()))
        elif readings:
            job.worst = worse_of(job.worst, RunStatus.FAILED_EXECUTION)
            job.error_lines.append(
                f"one process ran every point of this job, and its points read different "
                f"{key} values ("
                + ", ".join(f"{name}: {value!r}" for name, value in readings.items())
                + "), so the record cannot say which solver build produced its evidence; "
                "check that every point's log is this job's and not a leftover of another "
                "run, then re-run the row"
            )
    return RunRecord(
        **job.base,
        status=job.worst,
        warnings=job.job_warnings,
        outputs=job.collected_all,
        outputs_sha256=job.workspace.output_digests(job.case.sim_id, job.collected_all),
        residual_note=_NO_JOB_LOG_NOTE if job.excused else None,
        error="; ".join(job.error_lines) or None,
    )
