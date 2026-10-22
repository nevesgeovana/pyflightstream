"""One steady row of several points run as one solver job.

Private to :mod:`pyflightstream.run`. :func:`_execute_sweep` renders the
row's single script, runs or submits it once in the simulation folder and
lands ONE record for the whole job, whose ``points_ran`` states each point
with the status the assessor judged it in, on the loads of its own step. It
shares the pending files and the declared logs with the point path and sits
above it in the package order.
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
from pyflightstream.cases._skipped_families import collecting_the_study_skips
from pyflightstream.cases.workflows import (
    angles_not_stated,
    build_steady_sweep,
    rotor_machs,
)
from pyflightstream.results import (
    translate_surface_exports,
)
from pyflightstream.run._assessment import (
    OutcomeAssessor,
    job_solver_identity,
    worse_of,
)
from pyflightstream.run._continuation import (
    _refuse_an_import_count_nothing_logs,
)
from pyflightstream.run._executors import (
    ExecutionResult,
    Executor,
    LocalExecutor,
    Submitting,
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
    _local_logs,
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
    _write_script_keeping_replaced,
    staging_provenance,
    waived_record,
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
    """Return a steady job's rotor and disc Mach numbers, keyed by point name (M1)."""
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
        # Store the sweep name in point_name, the field read by collectors and
        # other record readers. Each point retains its own name.
        "point_name": sweep_name(job.case),
        "sweep_name": sweep_name(job.case),
        "job_id": run_id,
        "matrix_stem": job.campaign.matrix_stem,
        "fs_version_requested": job.canonical,
        "package_version": pyflightstream.__version__,
        "package_commit": package_commit,
        "package_dirty": package_dirty,
        # Capture the submitting user now; that identity cannot be recovered later.
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
        "angles_not_stated": list(angles_not_stated(job.case)),
        "density_kg_m3": None if job.case.fluid is None else job.case.fluid.density_kg_m3,
        "temperature_k": None if job.case.fluid is None else job.case.fluid.temperature_k,
        "viscosity_pa_s": None if job.case.fluid is None else job.case.fluid.viscosity_pa_s,
        "density_source": None if job.case.fluid is None else job.case.fluid.source,
        "reference_length_m": None if job.case.fluid is None else job.case.fluid.reference_length_m,
        # Filled from the built script below, as the point path fills it (PFS-2103.026).
        "waived_commands": [],
        # How the geometry was staged, as on a point's record (PFS-2103.026).
        **staging_provenance(job.workspace, job.case.sim_id, job.staged_geometry),
        "raw_commands": [entry.model_dump(mode="json") for entry in job.case.raw_commands],
        "aliases": {name: list(members) for name, members in job.case.aliases.items()},
        # Both are REQUIRED on a record and both are only known once the
        # script is built, so they carry the empty answer until then: a
        # record that never got as far as a script is a record whose script
        # has no digest and whose raw flag is false, and saying so is not
        # the same as leaving the field out.
        "script_sha256": "",
        "raw_flag": False,
        # M1: key each point's rotor and disc values by its name on the job record.
        # RunRecord.as_points gives each point its own values; None if none exist.
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
        with collecting_the_study_skips() as skipped:
            build_steady_sweep([pc for _, _, pc in job.point_cases], job.script, cold=job.cold)
        # FR-48: the waivers the job's script carries, recorded as a point's are.
        job.base["waived_commands"] = waived_record(job.script)
        # FR-989: the names the row skipped, once each; recorded only where there is one.
        job.base["skipped_names"] = [skip.record() for skip in skipped] or None
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
    # FR-1047 (PFS-2081.58): each point's far-field plane turns with its
    # attitude, so the layouts are keyed by point name, as the rotor Mach numbers are.
    by_point = {
        point_name(job.case, point): {"shapes": laid["shapes"]}
        for point, _stem, point_case in job.point_cases
        for laid in job.script.farfield_layout
        if laid.get("point") == dict(point_case.point)
    }
    if by_point:
        job.base["farfield_layout"] = {"by_point": by_point}
    job.base["surface_probe_layout"] = list(job.script.surface_probe_layout) or None
    job.base["frame_motions"] = job.script.frame_motions or None
    job.base["custom_field_coverage"] = job.script.custom_field_coverage
    job.base["freestream_units"] = (
        job.case.variables.get("FREESTREAM_UNITS") or job.case.freestream_units
    )
    setup = job.script.solver_setup
    if setup is not None:
        job.base["solver_setup"] = setup.model_dump(mode="json")
    # R03: record the script's names for post-processing section selections.
    if job.script.boundary_inventory is not None:
        job.base["inventory"] = list(job.script.boundary_inventory)
    # Record the surface layout as on the point path. The builder creates
    # distributions once per job, so all points share this layout, including an
    # empty layout when the job creates none (_sections_layout).
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
    # P5001-M090AL+sweepBE+000.
    job_stem = sweep_file_stem(job.case.sim_id, sweep_name(job.case))
    job.rendered = job.script.render()
    job.script_path, script_sha = _write_script_keeping_replaced(
        job.workspace, job.case.sim_id, f"{job_stem}.txt", job.rendered
    )
    job.base["script_path"] = str(Path(job.script_path).relative_to(job.sim_dir).as_posix())
    job.base["script_sha256"] = script_sha
    job.base["raw_flag"] = job.script.raw_flag
    job.base["march_strategy"] = job.script.march_strategy
    # FR-91: write probe positions and name the file on the record. The row's
    # layout serves every point in this job. A collision with a user's file is
    # a recorded job failure, matching the point path's refusal.
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

    # PYFS-006: refuse every point's existing declared outputs before launching
    # the shared script. Collection checks existence and cannot distinguish
    # stale exports from this solver's evidence (GEO-047-C03).
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

    # FR-99: bind submission values from the job's row: sweep name, walltime
    # and processor count. A local executor has no binding method.
    # Write parked script and data files before launch and include their digests
    # in the job inputs (G02, PFS-2031.13). Refuse input filename collisions.
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
    # THE DESCRIPTOR NAMES THE SWEEP, as the job record does (PFS-2094.039):
    # the first point's case supplies the row's clock and processors, and
    # bound its own name as the job's.
    if isinstance(job.executor, Submitting):
        job.executor.bind_point({"point": sweep_name(job.case)})
    if job.progress is not None:
        job.progress.solver_started = True
    try:
        job.result = job.executor.run_script(
            job.script_path, working_dir=job.sim_dir, timeout_s=job.case.solver.timeout_s
        )
    except CampaignConfigError as exc:
        # The job's refusal, recorded as the point path records its own (PFS-2094.010).
        return RunRecord(
            **job.base, status=RunStatus.FAILED_SCRIPT, error=f"{type(exc).__name__}: {exc}"
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
                # Record both the whole-job expected outputs and the same set by point.
                # The collector waits for the whole sweep, then files each point's evidence
                # in its own datapoint folder, matching local collection.
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
    # A point missing only surfaces the package failed to translate keeps its
    # assessment. Record that distinction per point on the job.
    job.job_warnings = []
    #: What each assessed point read as the solver's build and version.
    job.reported = []
    # On a machine that cannot export logs, a local job's printed output belongs
    # to the whole job, not one point. Assess each point from its loads export
    # and record why it lacks a log. Read the job output for the trailing-edge
    # count imported by the shared script.
    job.cannot_log = isinstance(job.executor, LocalExecutor) and not job.executor.export_log
    job.printed = job.result.captured_output() if job.cannot_log else ""
    # G45: EVERY POINT'S TECPLOT FROM ITS VTK, where the job wrote them, before
    # collection files each point's outputs in its own folder.
    if job.base.get("surface_translations"):
        job.base["surface_translations"] = translate_surface_exports(
            job.sim_dir,
            job.base["surface_translations"],  # type: ignore[arg-type]
        )
    # The declared logs by the finder and the `_log.txt` suffix (PFS-2103.030).
    job.excused = {
        name
        for _, _, point_case in job.point_cases
        for name in (_local_logs(point_case, job.rendered) if job.cannot_log else ())
        if not (job.sim_dir / name).is_file()
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
            # FILED, LISTED AND HASHED, and the point still fails,
            # unless all it misses is the package's own translation.
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
            # F-616: folded, so a worse verdict of an earlier point stays the headline.
            job.worst = worse_of(job.worst, RunStatus.FAILED_INCOMPLETE_OUTPUT)
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
        ran_entry: dict[str, object] = {
            "tag": tag,
            "point": dict(point),
            "status": str(status),
            "outputs": list(collected),
            "iterations": assessment.iterations,
            "residual": assessment.residual,
        }
        if status == RunStatus.MAX_ITER_REACHED:
            # FR-974/FR-977: the limit and the note, so the record and the post WARNING state them.
            ran_entry["iterations_requested"] = assessment.iterations_requested
            ran_entry["residual_note"] = assessment.residual_note
        job.ran.append(ran_entry)
        if str(status).startswith("FAILED"):
            job.error_lines.append(f"{tag}: {error or status}")
        # Use the worst point status according to the stated order as the job's
        # headline. points_ran retains each point's own status.
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
    # out of the comparison rather than counted as a disagreement. The rule is
    # one helper, which the collect of a submitted sweep calls too.
    agreed, disagreements = job_solver_identity(job.reported)
    job.base.update(agreed)
    if disagreements:
        job.worst = worse_of(job.worst, RunStatus.FAILED_EXECUTION)
        job.error_lines.extend(disagreements)
    return RunRecord(
        **job.base,
        status=job.worst,
        warnings=job.job_warnings,
        outputs=job.collected_all,
        outputs_sha256=job.workspace.output_digests(job.case.sim_id, job.collected_all),
        residual_note=_NO_JOB_LOG_NOTE if job.excused else None,
        error="; ".join(job.error_lines) or None,
    )
