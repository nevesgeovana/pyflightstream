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
    package_commit, package_dirty = package_vcs_state()
    run_id = _job_run_id(campaign, case)
    points = [point for point, _ in pending]
    base: dict[str, Any] = {
        "run_id": run_id,
        "sim_id": case.sim_id,
        "point": dict(points[0]),
        # A JOB'S NAME IS ITS SWEEP'S, and it is written to `point_name` as
        # well: the field is what every reader of a record takes the name
        # from, collect included, so a job record that left it empty would
        # be refused as written before 0.21.0 while being one of this
        # version's own. The points it ran carry their own names.
        "point_name": sweep_name(case),
        "sweep_name": sweep_name(case),
        "job_id": run_id,
        "matrix_stem": campaign.matrix_stem,
        "fs_version_requested": canonical,
        "package_version": pyflightstream.__version__,
        "package_commit": package_commit,
        "package_dirty": package_dirty,
        # v0.23.0 item 12. CAPTURED HERE because this is the only moment it
        # is knowable: who submitted a run cannot be recovered afterwards.
        "submitted_by": submitted_by(),
        "recipe": case.recipe,
        # A JOB'S RECIPE IS THE RUN TYPE, which has no user function behind
        # it and therefore no source to digest. The field is carried empty
        # rather than left out, so a reader of the manifest sees the same
        # shape on every record.
        "recipe_sha256": None,
        "fs_exe": str(fs_exe),
        "fs_exe_sha256": _file_digest(fs_exe),
        "fs_version_source": fs_version_source,
        "manifest_schema": MANIFEST_SCHEMA,
        "inputs_sha256": dict(inputs_sha256),
        "campaign_name_from": name_from,
        "pproc": case.pproc_id,
        "velocity_requested_m_s": case.velocity,
        "inventory_source": case.inventory_source,
        "mesh_import": None
        if case.mesh_import is None
        else case.mesh_import.model_dump(mode="json", exclude_none=True),
        "motions": [dict(record) for record in case.motions],
        "point_name_template": workspace.naming.point_name,
        "description": case.description or None,
        "mach": case.mach,
        "reference": _reference_block(case),
        # THE SAME PROVENANCE A POINT RECORD CARRIES. A job is one process
        # over several points of ONE row, so every one of these is a
        # property of the row and is the same for all of them; leaving
        # them out made a job record unable to say whether its state was a
        # wind tunnel's or an altitude's, which its own guard reported.
        "flight_condition": dict(case.flight_condition),
        "flight_condition_defaults": dict(case.flight_condition_defaults),
        "flight_condition_defaults_from": case.flight_condition_defaults_from,
        "density_kg_m3": None if case.fluid is None else case.fluid.density_kg_m3,
        "temperature_k": None if case.fluid is None else case.fluid.temperature_k,
        "viscosity_pa_s": None if case.fluid is None else case.fluid.viscosity_pa_s,
        "density_source": None if case.fluid is None else case.fluid.source,
        "reference_length_m": None if case.fluid is None else case.fluid.reference_length_m,
        "waived_commands": [],
        "raw_commands": [entry.model_dump(mode="json") for entry in case.raw_commands],
        "aliases": {name: list(members) for name, members in case.aliases.items()},
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
        "rotor_mach": _job_rotor_mach(case, points),
    }
    if progress is not None:
        progress.base = base
    if preparation_error is not None:
        return RunRecord(**base, status=RunStatus.FAILED_SCRIPT, error=preparation_error)

    # One case per point, differing only in the point and the names it
    # exports; everything the shared preamble reads is the same on all of
    # them, which is what makes them one script.
    point_cases = []
    for point in points:
        try:
            stem, outputs = _point_names(campaign, case, point, workspace)
        except NamingTemplateError as exc:
            return RunRecord(**base, status=RunStatus.FAILED_SCRIPT, error=str(exc))
        update: dict[str, object] = {"outputs": outputs}
        if staged_geometry is not None:
            update["geometry"] = staged_geometry
        point_cases.append(
            (point, stem, _with_the_profile_s_log(case_at_point(case, point, **update), executor))
        )

    script = Script(version=fs_version)
    # G02: the job runs in the simulation folder, which no other simulation
    # shares, so the node file its one script imports is named there.
    script.working_dir = str(sim_dir)
    try:
        build_steady_sweep([pc for _, _, pc in point_cases], script, cold=cold)
        # G02: the switch is the row's, so the first point's case states it.
        _refuse_an_import_count_nothing_logs(point_cases[0][2], script, executor)
    except Exception as exc:  # a build failure is the job's failure
        return RunRecord(
            **base,
            status=RunStatus.FAILED_SCRIPT,
            error=f"{type(exc).__name__}: {exc}",
        )
    base["probe_field_layout"] = list(script.probe_field_layout) or None
    base["surface_probe_layout"] = list(script.surface_probe_layout) or None
    base["frame_motions"] = script.frame_motions or None
    base["custom_field_coverage"] = script.custom_field_coverage
    base["freestream_units"] = case.variables.get("FREESTREAM_UNITS") or case.freestream_units
    setup = script.solver_setup
    if setup is not None:
        base["solver_setup"] = setup.model_dump(mode="json")
    # R03 of 0.27.0: the names the script was built over, as the point path
    # records them; the post reads a section selection over them.
    if script.boundary_inventory is not None:
        base["inventory"] = list(script.boundary_inventory)
    # WHICH ROWS OF THE SECTIONS EXPORT ARE WHICH SURFACE, recorded as the
    # point path records them (0.27.0). The one-job path recorded no layout
    # since 0.24.0, so the post refused the per-distribution split of every
    # steady row of several points. The builder creates the distributions
    # once, for every point of the job, so one layout is every point's; the
    # empty one where the job creates none (`_sections_layout`).
    layout = _sections_layout(script)
    if layout is not None:
        base["sections_layout"] = layout
    # G45: every point's Tecplot surface, written from its VTK after the job.
    base["surface_translations"] = [
        dict(translation) for translation in script.surface_translations
    ] or None
    # THE HOUSE CONVENTION FOR A SWEEP, not a name of this function's own.
    # A per-polar product table is named by the point name with the swept
    # variable written literally as `sweep`, and a job's script is about
    # exactly the same thing, so it is named the same way:
    # P5001-M090AL+sweepBE+000 (0.21.0).
    job_stem = sweep_file_stem(case.sim_id, sweep_name(case))
    rendered = script.render()
    script_path, script_sha = workspace.write_script(case.sim_id, f"{job_stem}.txt", rendered)
    base["script_path"] = str(Path(script_path).relative_to(sim_dir).as_posix())
    base["script_sha256"] = script_sha
    base["raw_flag"] = script.raw_flag
    base["march_strategy"] = script.march_strategy
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
        probe_points_file = _write_probe_points(sim_dir, case.sim_id, script.probe_points)
    except PyflightstreamError as exc:
        return RunRecord(
            **base,
            status=RunStatus.FAILED_SCRIPT,
            error=f"{type(exc).__name__}: {exc}",
        )
    if probe_points_file is not None:
        base["probe_points_file"] = probe_points_file

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
    stale = sorted(
        {
            name
            for _, _, point_case in point_cases
            for name in point_case.outputs
            if (sim_dir / name).exists()
        }
    )
    if stale:
        return RunRecord(
            **base,
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
            script,
            sim_dir,
            case=case,
            recorded=inputs_sha256,
            run_writes=(
                Path(script_path),
                *([sim_dir / probe_points_file] if probe_points_file is not None else []),
                *_descriptor_of(executor, sim_dir),
            ),
        )
    except CampaignConfigError as exc:
        return RunRecord(
            **base,
            status=RunStatus.FAILED_SCRIPT,
            error=f"{type(exc).__name__}: {exc}",
        )
    if written:
        base["inputs_sha256"] = {**base["inputs_sha256"], **written}
    bind_submission_values(executor, case, point_cases[0][2])
    if progress is not None:
        progress.solver_started = True
    result = executor.run_script(script_path, working_dir=sim_dir, timeout_s=case.solver.timeout_s)
    base["argv"] = list(result.argv)
    base["cwd"] = result.cwd
    base["timeout_s"] = result.timeout_s
    base["executor"] = invocation_record(executor, result)
    base["started_at"] = result.started_at
    base["finished_at"] = result.finished_at
    # FR-99, and the same reason as the point path: the descriptor exists
    # before the scheduler is called, so a rejected submission must keep it.
    submitted = _submission_record(executor)
    if result.failed:
        return RunRecord(
            **base,
            status=RunStatus.FAILED_EXECUTION,
            wall_time_s=result.wall_time_s,
            error=result.diagnosis(),
            submission=submitted,
        )
    # FR-99. A SUBMITTED JOB HAS NO OUTPUTS YET. The scheduler has taken
    # the whole sweep and no point of it has run, so every point is
    # pending: the record says SUBMITTED, names where the job went, and
    # carries the points it will run rather than points it ran.
    if submitted is not None:
        return RunRecord(
            **base,
            status=RunStatus.SUBMITTED,
            wall_time_s=None,
            outputs=[],
            # The whole sweep is ONE job and one script, so the declared
            # set is every point's outputs together: the collector waits
            # for the job, not for a point of it.
            submission={
                **submitted,
                "declared_outputs": [name for _, _, pc in point_cases for name in pc.outputs],
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
                    point_name(case, point): [str(name) for name in pc.outputs]
                    for point, _, pc in point_cases
                },
                "points_by_tag": {
                    point_name(case, point): dict(point) for point, _, _ in point_cases
                },
                # G02: the points the job's one script imports. The job writes
                # one log with one import line, so every point is held to this
                # number and it is never multiplied by the points.
                **(
                    {"wake_edge_points": script.wake_edge_points}
                    if script.wake_edge_points is not None
                    else {}
                ),
                # G06: every file the job was told to write a point's log to,
                # whatever its name; the collector reads the four lines in each.
                "declared_logs": list(
                    dict.fromkeys(
                        name for _, _, pc in point_cases for name in _declared_logs(pc, rendered)
                    )
                ),
            },
            points_ran=[
                {
                    "tag": point_name(case, point),
                    "point": dict(point),
                    "status": str(RunStatus.SUBMITTED),
                }
                for point, _, _ in point_cases
            ],
        )
    base["wall_time_s"] = result.wall_time_s

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
    ran: list[dict] = []
    worst = RunStatus.CONVERGED
    collected_all: list[str] = []
    error_lines: list[str] = []
    collected_by_tag: dict[str, list[str]] = {}
    failed_tags: dict[str, str] = {}
    # 0.30.0: a point whose only missing outputs are surfaces the package failed
    # to translate keeps its assessment; the job's record says so, per point.
    job_warnings: list[str] = []
    #: What each assessed point read as the solver's build and version.
    reported: list[tuple[str, str | None, str | None]] = []
    # 0.27.0: ON A MACHINE THAT CANNOT EXPORT THE LOG, run locally, no point's
    # declared log is written and none is missing. What the solver printed is
    # the whole job's and no single point's, and a job log judged as a point's
    # would end at the last point's iteration; so each point is judged from its
    # loads export, the job's record says why, and the printed output is read
    # for the trailing-edge count the one script imported, as a job's is.
    cannot_log = isinstance(executor, LocalExecutor) and not executor.export_log
    printed = result.captured_output() if cannot_log else ""
    # G45: EVERY POINT'S TECPLOT FROM ITS VTK, where the job wrote them, before
    # collection files each point's outputs in its own folder.
    if base.get("surface_translations"):
        base["surface_translations"] = translate_surface_exports(
            sim_dir,
            base["surface_translations"],  # type: ignore[arg-type]
        )
    excused = {
        name
        for _, _, point_case in point_cases
        for name in point_case.outputs
        if cannot_log and name.endswith(_LOG_OUTPUT_SUFFIX) and not (sim_dir / name).is_file()
    }
    for point, _stem, point_case in point_cases:
        tag = point_name(case, point)
        try:
            collected_by_tag[tag] = workspace.collect_outputs(
                case.sim_id,
                # ABSOLUTE, as the point path passes them: the names on the
                # case are relative to the execution directory and the
                # collector is handed paths, not names.
                [sim_dir / name for name in point_case.outputs if name not in excused],
                datapoint=PointName(tag),
            )
        except MissingOutputsError as exc:
            # FILED, LISTED AND HASHED, and the point still fails (0.27.0),
            # unless all it misses is the package's own translation (0.30.0).
            collected_by_tag[tag] = exc.collected
            owned = [
                entry
                for entry in base.get("surface_translations") or []  # type: ignore[attr-defined]
                if isinstance(entry, Mapping) and entry.get("dat") in point_case.outputs
            ]
            untranslated = untranslated_surfaces(owned, exc.missing, exc.collected)
            if untranslated is None:
                failed_tags[tag] = str(exc) + _translation_problems(owned)
            else:
                for line in untranslated:
                    job_warnings.append(f"{tag}: {line}")
                    warnings.warn(f"{tag}: {line}", PyflightstreamWarning, stacklevel=2)
        except (WorkspaceError, CampaignConfigError) as exc:
            failed_tags[tag] = str(exc)
    for point, _stem, point_case in point_cases:
        tag = point_name(case, point)
        if tag in failed_tags:
            entry: dict[str, object] = {
                "tag": tag,
                "point": dict(point),
                "status": str(RunStatus.FAILED_INCOMPLETE_OUTPUT),
            }
            if collected_by_tag.get(tag):
                entry["outputs"] = list(collected_by_tag[tag])
                collected_all.extend(collected_by_tag[tag])
            ran.append(entry)
            worst = RunStatus.FAILED_INCOMPLETE_OUTPUT
            error_lines.append(f"{tag}: {failed_tags[tag]}")
            continue
        collected = collected_by_tag[tag]
        assessment = assess(point_case, result, sim_dir)
        reported.append((tag, assessment.fs_build, assessment.fs_version_reported))
        # G02. The job's one script imported the trailing edges once, and each
        # point is held to that count through the log it collected, else the
        # job's own.
        log_text = _run_log_text(sim_dir, collected, assessment.log_file_used, result) or (
            printed or None
        )
        status, error = with_wake_edge_verdict(
            assessment.status,
            assessment.error,
            _no_local_log_verdict(script.wake_edge_points, log_text, _NO_JOB_LOG_NOTE)
            if cannot_log
            else wake_edge_import_verdict(script.wake_edge_points, log_text),
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
                result.log_text,
                printed,
                *collected_log_texts(sim_dir, collected, _declared_logs(point_case, rendered)),
            ),
        )
        collected_all.extend(collected)
        ran.append(
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
            error_lines.append(f"{tag}: {error or status}")
        # THE WORST, BY A STATED ORDER, and it was the LAST failing point
        # until 2026-09-13: each failure simply overwrote the variable, so
        # a sweep whose first point DIVERGED and whose third left an
        # incomplete output recorded the third, and a reader triaging by
        # status was pointed at the wrong point (the QA lens). `points_ran`
        # carried each point's own status either way, so nothing was lost;
        # what was wrong was the job's headline.
        worst = worse_of(worst, status)
    base["points_ran"] = ran
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
        readings = {entry[0]: entry[index] for entry in reported if entry[index] is not None}
        if len(set(readings.values())) == 1:
            base[key] = next(iter(readings.values()))
        elif readings:
            worst = worse_of(worst, RunStatus.FAILED_EXECUTION)
            error_lines.append(
                f"one process ran every point of this job, and its points read different "
                f"{key} values ("
                + ", ".join(f"{name}: {value!r}" for name, value in readings.items())
                + "), so the record cannot say which solver build produced its evidence; "
                "check that every point's log is this job's and not a leftover of another "
                "run, then re-run the row"
            )
    return RunRecord(
        **base,
        status=worst,
        warnings=job_warnings,
        outputs=collected_all,
        outputs_sha256=workspace.output_digests(case.sim_id, collected_all),
        residual_note=_NO_JOB_LOG_NOTE if excused else None,
        error="; ".join(error_lines) or None,
    )
