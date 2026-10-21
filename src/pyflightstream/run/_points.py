"""One campaign point: render, run or submit, assess, record.

Private to :mod:`pyflightstream.run`. :func:`_execute_point` is the path of
every point that is not part of a steady row run as one job; the helpers
beside it build the records of a point that could not be written, and the
verdicts on the solver log a local run leaves or does not leave. The sweep
path above reuses those helpers.
"""

from __future__ import annotations

import hashlib
import time
import warnings
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

import pyflightstream
import pyflightstream._textio as _textio

# The writer is looked up on its module, not bound here, so the point path
# and the sweep path reach one function through one name (and a test that
# replaces it replaces it for both).
import pyflightstream.run._pending as _pending
from pyflightstream._digest import (
    file_sha256,
)
from pyflightstream._errors import (
    PyflightstreamError,
    PyflightstreamWarning,
)
from pyflightstream.cases import (
    Campaign,
    CampaignConfigError,
    ScriptRecipe,
    SimCase,
    case_at_point,
    point_name,
    sweep_name,
)
from pyflightstream.cases._skipped_families import collecting_the_study_skips
from pyflightstream.cases.acoustics import (
    acoustic_section_leftovers,
    acoustic_section_outputs,
)
from pyflightstream.cases.workflows import (
    UNSTEADY_ACTION_COUNT,
    WALLTIME_CLOCK_ACTION,
    WALLTIME_CLOCK_PROGRAM,
    WALLTIME_CLOCK_STATE,
    WALLTIME_STOP_SCRIPT,
    creates_surface_sections,
    job_start_state,
    reduction_windows,
    rotor_machs,
    row_walltime_s,
    walltime_clock_program,
    walltime_margin_s,
)
from pyflightstream.results import (
    translate_surface_exports,
)
from pyflightstream.run._actions_counter import stage_counter
from pyflightstream.run._assessment import (
    OutcomeAssessor,
)
from pyflightstream.run._continuation import (
    _queued_record_of_point,
    _recorded_loads_frame,
    _refuse_an_import_count_nothing_logs,
    workflow_conventions_for,
)
from pyflightstream.run._executors import (
    ExecutionResult,
    Executor,
    LocalExecutor,
    _submission_record,
    _with_the_profile_s_log,
    action_count,
    bind_submission_values,
    invocation_record,
)
from pyflightstream.run._identity import (
    _file_digest,
    _recipe_digest,
    package_vcs_state,
)
from pyflightstream.run._ids import (
    _point_names,
    _unplaced,
)
from pyflightstream.run._pending import (
    _declared_logs,
    _descriptor_of,
    _local_logs,
    _run_log_text,
    _walltime_stop,
    _write_probe_points,
)
from pyflightstream.run._step_exports import missing_step_warning, untranslated_surfaces
from pyflightstream.run._wake_edge_verdict import (
    actuator_profile_verdict,
    collected_log_texts,
    wake_edge_import_verdict,
    with_wake_edge_verdict,
)
from pyflightstream.script import Script
from pyflightstream.workspace import (
    MANIFEST_SCHEMA,
    SIM_DATAPOINTS_DIR,
    CampaignWorkspace,
    MissingOutputsError,
    NamingTemplateError,
    RunRecord,
    RunStatus,
    WorkspaceError,
    datapoint_dir_name,
)
from pyflightstream.workspace.naming import (
    PointName,
    submitted_by,
)


def _translation_problems(translations: object) -> str:
    """Return the sentences a translation pass recorded, for a record's error (G45)."""
    if not isinstance(translations, list):
        return ""
    said = [
        str(problem)
        for translation in translations
        if isinstance(translation, Mapping)
        for problem in (translation.get("problems") or [])  # type: ignore[attr-defined]
    ]
    return "" if not said else " " + "; ".join(said)


def _reference_block(case: SimCase) -> dict[str, float] | None:
    """Return the reference block a product row carries, from the case's reference data."""
    reference = case.reference
    if reference is None:
        return None
    moment = reference.moment_point_m or (0.0, 0.0, 0.0)
    block = {"SREF": reference.area, "CREF": reference.length}
    if reference.span_m is not None:
        block["BREF"] = reference.span_m
    block.update({"XMOM": moment[0], "YMOM": moment[1], "ZMOM": moment[2]})
    return block


def _sections_layout(script: Script) -> list[dict[str, object]] | None:
    """Return the section layout a run records beside its script, or None.

    The builder's blocks where it created distributions. THE EMPTY LAYOUT where
    the rendered script adds or removes no surface section at all, which is
    every steady point of a pproc declaring no distribution: its sections
    exports state none. An empty layout distinguishes that known absence from
    an unrecorded layout. None where the script changes sections the builder
    did not describe (a LEGACY recipe's or a raw command's), whose split the
    post refuses rather than guesses.
    """
    if script.section_blocks:
        return [dict(block) for block in script.section_blocks]
    if not creates_surface_sections(script.render()):
        return []
    return None


@dataclass
class _PointProgress:
    """How far one point's (or one job's) path got, for a failure it could not record.

    The run path writes a script, its input files and its state before
    the solver starts, and a workspace on a network share can refuse any one of
    those writes with an ``OSError``. The caller catches it and records the
    point from what this holds, allowing later planned points to proceed.
    """

    #: The record fields as the path had built them, None before they exist.
    #: A keyword bag for a record constructor is ``dict[str, Any]``: its values
    #: differ by key, and the record's own model checks each one when it is built.
    base: dict[str, Any] | None = None
    #: Whether the solver had been launched when the error came.
    solver_started: bool = False


def _unwritable(error: OSError, where: str) -> str:
    """Say which write failed and what the run did about it."""
    return (
        f"{type(error).__name__}: {error}, {where}. A file of this point could not be "
        "written (a workspace on a network share that refuses a write is one cause), so "
        "the point is recorded failed and the run went on with the next point. Make the "
        "folder writable and run the point again: pyfs-matrix run --force-rerun <point>"
    )


def _bare_record(
    campaign: Campaign, case: SimCase, point: Mapping[str, float], run_id: str, canonical: str
) -> dict[str, object]:
    """Return the fields a record of a point that never built its own can state."""
    return {
        "run_id": run_id,
        "sim_id": case.sim_id,
        "point": dict(point),
        "matrix_stem": campaign.matrix_stem,
        "fs_version_requested": canonical,
        "package_version": pyflightstream.__version__,
        "manifest_schema": MANIFEST_SCHEMA,
        "script_sha256": "",
        "raw_flag": False,
    }


def _record_of_an_unwritable_point(
    progress: _PointProgress, error: OSError, *, fallback: dict[str, object]
) -> RunRecord:
    """Record one point whose run raised an ``OSError``.

    FAILED_SCRIPT when the solver was not started, the status of a point whose
    script could not be built, and here it could not be written;
    FAILED_INCOMPLETE_OUTPUT when it was, since what could not be written then
    is the filing or the recording of its outputs. The cause is the record's
    ``error``.
    """
    started = progress.solver_started
    return RunRecord(
        **(progress.base if progress.base is not None else fallback),  # type: ignore[arg-type]
        status=RunStatus.FAILED_INCOMPLETE_OUTPUT if started else RunStatus.FAILED_SCRIPT,
        error=_unwritable(
            error,
            "after the solver ran, while its outputs were filed or recorded"
            if started
            else "before the solver started, while its script, input files or state were written",
        ),
    )


@dataclass(frozen=True)
class _LocalLog:
    """What a local run on a machine that cannot export its log did about the log.

    Such a machine's scheduler writes the log of a SUBMITTED job, and
    `collect` copies it to the declared name; a run kept local has no
    scheduler, so the declared log is written from what the executor captured
    of the solver, or, when it captured nothing, excused: the machine cannot
    write one locally, which is not an output the run failed to produce.
    """

    #: The declared log written from the captured output, as declared.
    written: str | None = None
    #: The declared log excused because nothing was captured, as declared.
    excused: str | None = None
    #: The sentence the record carries about it, in ``residual_note``.
    note: str | None = None


#: The sentence a local run's record carries when its log is the captured output.
_CAPTURED_LOG_NOTE = (
    "{name} is the solver's captured standard output and error, written by this package: "
    "this machine's HPC profile states export_log = false and the local switch (--local) "
    "kept the run here, where no scheduler writes a log"
)


#: The sentence a steady job's record carries on such a machine, whatever was printed.
_NO_JOB_LOG_NOTE = (
    "no point of this job has a solver log: this machine's HPC profile states export_log = "
    "false and the local switch (--local) kept the job here, where no scheduler writes one; "
    "what the solver printed is the whole job's and no single point's, so each point is "
    "judged from its loads export alone"
)


#: The sentence it carries when the solver printed nothing to capture.
_NO_LOCAL_LOG_NOTE = (
    "no solver log: this machine's HPC profile states export_log = false, the local switch "
    "(--local) kept the run here, where no scheduler writes one, and the solver printed "
    "nothing to capture, so the point is judged from its loads export alone"
)


def _the_local_log(
    executor: object, logs: Sequence[str], work_dir: Path, result: ExecutionResult
) -> _LocalLog:
    """Write a local point's declared log from the solver's output, or excuse it.

    Only on a local executor whose machine cannot export the log; on any other
    run nothing is written and nothing is excused. ``logs`` are the point's
    declared logs (``_declared_logs``, PFS-2103.030: a case built in Python
    names its log as it likes, so the ``_log.txt`` suffix did not find it),
    and a log the solver did write is never overwritten.
    """
    if not isinstance(executor, LocalExecutor) or executor.export_log:
        return _LocalLog()
    declared = [str(name) for name in logs]
    if not declared or (work_dir / declared[0]).is_file():
        return _LocalLog()
    captured = result.captured_output()
    if captured:
        _textio.write_text(work_dir / declared[0], captured)
        return _LocalLog(
            written=declared[0], note=_CAPTURED_LOG_NOTE.format(name=Path(declared[0]).name)
        )
    return _LocalLog(excused=declared[0], note=_NO_LOCAL_LOG_NOTE)


def _no_local_log_verdict(
    expected: int | None, log_text: str | None, note: str
) -> tuple[RunStatus, str] | None:
    """Judge the trailing-edge count of a local run whose machine could write no log.

    G02 on such a machine: the count is read from the log, and with none the
    point is recorded FAILED_INCOMPLETE_OUTPUT naming the MACHINE as the reason
    rather than telling the row to export a log it did declare.
    """
    if expected is None or log_text is not None:
        return wake_edge_import_verdict(expected, log_text)
    return (
        RunStatus.FAILED_INCOMPLETE_OUTPUT,
        f"the script imported {expected} trailing-edge points and no solver log was read "
        f"({note}), so whether the file marked anything cannot be told: a file whose "
        "points match no edge marks nothing and says nothing. Run this row where its log "
        "is written, submitted from this cluster (without --local), where the scheduler's "
        "log is collected",
    )


@dataclass(kw_only=True)
class _PointJob:
    """Inputs and phase results of one ordered execution."""

    campaign: Campaign
    canonical: str
    fs_exe: str | Path
    fs_version: str
    fs_version_source: str
    case: SimCase
    point: dict[str, float]
    run_id: str
    recipe: ScriptRecipe | None
    preparation_error: str | None
    inputs_sha256: dict[str, str]
    staged_geometry: str | None
    name_from: str | None
    executor: Executor
    workspace: CampaignWorkspace
    sim_dir: Path
    assess: OutcomeAssessor
    continues: str | None
    recovered_continuation: Mapping[str, object] | None
    progress: _PointProgress | None
    base: dict[str, Any] = field(init=False)
    stem: str = field(init=False)
    point_case: SimCase = field(init=False)
    script: Script = field(init=False)
    work_dir: Path = field(init=False)
    predecessor: RunRecord | None = field(init=False)
    rendered: str = field(init=False)
    script_path: Path = field(init=False)
    script_sha: str = field(init=False)
    probe_points_file: str | None = field(init=False)
    counter: dict[str, object] | None = field(init=False)
    result: ExecutionResult = field(init=False)
    local_log: _LocalLog = field(init=False)
    collected: list[str] = field(init=False)
    post_warnings: list[str] = field(init=False)


def _execute_point(
    *,
    campaign: Campaign,
    canonical: str,
    fs_exe: str | Path,
    fs_version: str,
    fs_version_source: str,
    case: SimCase,
    point: dict[str, float],
    run_id: str,
    recipe: ScriptRecipe | None,
    preparation_error: str | None,
    inputs_sha256: dict[str, str],
    staged_geometry: str | None,
    name_from: str | None = None,
    executor: Executor,
    workspace: CampaignWorkspace,
    sim_dir: Path,
    assess: OutcomeAssessor,
    continues: str | None = None,
    recovered_continuation: Mapping[str, object] | None = None,
    progress: _PointProgress | None = None,
) -> RunRecord:
    """Take one point from sweep coordinates to its manifest record.

    ``progress`` is filled as the point goes: the record fields as
    they stand, and whether the solver was started, so a caller that catches
    an ``OSError`` this raises records the point from them rather than
    leaving it with no record.
    """
    job = _PointJob(
        campaign=campaign,
        canonical=canonical,
        fs_exe=fs_exe,
        fs_version=fs_version,
        fs_version_source=fs_version_source,
        case=case,
        point=point,
        run_id=run_id,
        recipe=recipe,
        preparation_error=preparation_error,
        inputs_sha256=inputs_sha256,
        staged_geometry=staged_geometry,
        name_from=name_from,
        executor=executor,
        workspace=workspace,
        sim_dir=sim_dir,
        assess=assess,
        continues=continues,
        recovered_continuation=recovered_continuation,
        progress=progress,
    )
    if (record := _prepare_point_script(job)) is not None:
        return record
    if (record := _retain_point_provenance(job)) is not None:
        return record
    if (record := _retain_point_translations(job)) is not None:
        return record
    if (record := _write_point_script(job)) is not None:
        return record
    if (record := _write_point_pending_files(job)) is not None:
        return record
    if (record := _run_point_solver(job)) is not None:
        return record
    if (record := _collect_point_outputs(job)) is not None:
        return record
    return _assess_point_record(job)


def staging_provenance(
    workspace: CampaignWorkspace, sim_id: str, staged_geometry: str | None
) -> dict[str, str | None]:
    """Return ``staged_as`` and ``staged_as_reason`` of a record (PFS-2029.17).

    One home for the point path and the steady job path (PFS-2103.026): how the
    geometry was staged, read off the workspace that staged it, so the record
    says link or copy and why; None for both where nothing was staged.
    """
    mode, reason = workspace.staged_as(sim_id) if staged_geometry is not None else (None, None)
    return {"staged_as": mode, "staged_as_reason": reason}


def waived_record(script: Script) -> list[dict[str, Any]]:
    """Return a script's waived broken commands as a record writes them (FR-48).

    One home for the point path and the steady job path (PFS-2103.026).
    """
    return [use.model_dump(mode="json") for use in script.waived_commands]


def _prepare_point_script(job: _PointJob) -> RunRecord | None:
    """Prepare point script."""
    package_commit, package_dirty = package_vcs_state()
    # THE STATE OF THIS POINT, NOT OF THE ROW. Every state field below
    # read `case.*`, the simulation-level case, while the point's own case went
    # to the script alone. On a row sweeping a flow variable each point therefore
    # ran at its own Mach, velocity and density and RECORDED the first point's,
    # and the rotor table then divided one point's force by another's density.
    # `case_at_point` is the one function that resolves a point; asking it here
    # is what makes the record describe what the solver was given.
    at_point = case_at_point(job.case, job.point)
    job.base = {
        "run_id": job.run_id,
        "sim_id": job.case.sim_id,
        "point": dict(job.point),
        "point_name": point_name(job.case, job.point),
        "sweep_name": sweep_name(job.case),
        "matrix_stem": job.campaign.matrix_stem,
        # The run this one CONTINUES, in the base dict so that a continuation
        # that fails says so as well: the chain is a fact about the attempt,
        # not about its success. None for every point that continues nothing.
        "continues": job.continues,
        "restart": (job.recovered_continuation or {}).get("restart") if job.continues else None,
        "fs_version_requested": job.canonical,
        "package_version": pyflightstream.__version__,
        "package_commit": package_commit,
        "package_dirty": package_dirty,
        # Capture who submitted the run here; it cannot be recovered afterwards.
        "submitted_by": submitted_by(),
        "recipe": job.case.recipe,
        "recipe_sha256": _recipe_digest(job.recipe),
        # The BUILD's executable, which is the campaign's unless the case
        # named another. Recording campaign.fs_exe unconditionally is what
        # made a per-case build unstatable: the record would name an
        # executable the point never ran (PFS-2009.05).
        "fs_exe": str(job.fs_exe),
        "fs_exe_sha256": _file_digest(job.fs_exe),
        # WHICH of the two sources chose that build, beside WHICH build it
        # was. The pair above reproduces the run; without this a reader of
        # a finished record cannot tell a build chosen FOR THIS ROW from
        # one inherited from the campaign, and the two are different facts
        # about how the study was configured (PFS-2009.08.02).
        "fs_version_source": job.fs_version_source,
        # The velocity the case ASKED for, in the base dict rather than in
        # the success path: four early returns below build the record from
        # `base` alone, so a field written later would be absent from
        # exactly the failed points a reader most wants to compare
        # (OPS-2009.01.13).
        "velocity_requested_m_s": at_point.velocity,
        # The post-processing artifact the row named (PFS-2029.16), so a
        # reader of the record knows which sections, plots and products
        # the point was run for without opening the matrix.
        "pproc": job.case.pproc_id,
        "inventory_source": job.case.inventory_source,
        "mesh_import": None
        if job.case.mesh_import is None
        else job.case.mesh_import.model_dump(mode="json", exclude_none=True),
        "motions": [dict(record) for record in job.case.motions],
        # Record reduction windows (PFS-2015.04) from a point-bearing case, where
        # the clock and blade count are resolved. The SIM-level case has no point
        # and cannot resolve speed for a swept advance ratio. Products read these
        # recorded windows alone. None for a steady row.
        "reductions": reduction_windows(case_at_point(job.case, job.point)),
        # M1: each rotor's tip and helical Mach numbers from this point's resolved
        # state. None, and absent from the file, when rotor_machs covers nothing: a
        # row turning no rotor at a stated speed and naming no actuator disc.
        "rotor_mach": {mach.alias: mach.record() for mach in rotor_machs(at_point)} or None,
        # How the geometry was staged (PFS-2029.17), read off the workspace
        # that staged it, so the record says link or copy and why.
        **staging_provenance(job.workspace, job.case.sim_id, job.staged_geometry),
        # The template that rendered this point's names (PFS-2029.19.01),
        # so a reader can tell a name from the identity beside it.
        "point_name_template": job.workspace.naming.point_name,
        "description": job.case.description or None,
        "mach": at_point.mach,
        "reference": _reference_block(job.case),
        "campaign_name_from": job.name_from,
        # PFS-2027.05: the inputs as written and the resolved state, so
        # the record is recomputable rather than merely trusted.
        "flight_condition": dict(at_point.flight_condition),
        "flight_condition_defaults": dict(at_point.flight_condition_defaults),
        "flight_condition_defaults_from": at_point.flight_condition_defaults_from,
        "density_kg_m3": None if at_point.fluid is None else at_point.fluid.density_kg_m3,
        "temperature_k": None if at_point.fluid is None else at_point.fluid.temperature_k,
        "viscosity_pa_s": None if at_point.fluid is None else at_point.fluid.viscosity_pa_s,
        "density_source": None if at_point.fluid is None else at_point.fluid.source,
        "reference_length_m": None if at_point.fluid is None else at_point.fluid.reference_length_m,
        "inputs_sha256": job.inputs_sha256,
        "script_sha256": "",
        "raw_flag": False,
        "waived_commands": [],
        # PFS-2033.02: the setup's raw commands, as the script carried them.
        "raw_commands": [entry.model_dump(mode="json") for entry in job.case.raw_commands],
        # Record the setup's aliases for the products stage.
        "aliases": {name: list(members) for name, members in job.case.aliases.items()},
        # PFS-2012.04: how the solver was called, read off the executor
        # and its result once the point has run, and None on the four
        # early returns below, where no solver ran. `argv` beside it is
        # the command line alone; this says which executor built it.
        "executor": None,
        # The export window the row states for its unsteady exports, as
        # resolved for this run (PFS-2031.18): filled below beside the two
        # action files when the row states EXPORT_UNSTEADY_AFTER_REV or
        # EXPORT_UNSTEADY_AFTER_ITER; None for a row that states neither.
        "export_window": None,
        # Stated, not defaulted (REV010-014). The field defaults to None so
        # that a row which never carried it stays honest about that; a row
        # this version writes DOES carry it, and says so here.
        "manifest_schema": MANIFEST_SCHEMA,
    }
    if job.progress is not None:
        job.progress.base = job.base
    if job.preparation_error is not None or job.recipe is None:
        error: str | None = job.preparation_error or "recipe resolution failed"
        return RunRecord(**job.base, status=RunStatus.FAILED_SCRIPT, error=error)

    # Refuse a point already in a queue before writing any files. Its datapoint
    # folder carries no campaign name, so another campaign naming this point
    # would rewrite a queued job's script, descriptor, actions and clock. Check
    # per simulation AND point so distinct points of one row can submit together.
    queued = _queued_record_of_point(
        job.workspace, job.case.sim_id, point_name(job.case, job.point)
    )
    if queued is not None:
        return RunRecord(
            **job.base,
            status=RunStatus.FAILED_SCRIPT,
            error=(
                f"point {point_name(job.case, job.point)} of simulation {job.case.sim_id} "
                "is already in a "
                f"scheduler's queue as {queued.run_id!r}, and a submitted point runs in its "
                "own datapoint folder, which that job has not finished writing. Collect it "
                "(pyfs-matrix collect) before submitting this point again; nothing of it was "
                "written."
            ),
        )
    try:
        job.stem, outputs = _point_names(job.campaign, job.case, job.point, job.workspace)
    except NamingTemplateError as exc:
        return RunRecord(**job.base, status=RunStatus.FAILED_SCRIPT, error=str(exc))
    update: dict[str, object] = {"outputs": outputs}
    if job.staged_geometry is not None:
        update["geometry"] = job.staged_geometry
    job.point_case = _with_the_profile_s_log(
        case_at_point(job.case, job.point, **update), job.executor
    )
    # The BUILD's version, so a case sent to a second installation emits
    # the commands that installation documents rather than the campaign's.
    job.script = Script(version=job.fs_version)
    # G02: the folder this point runs in (see below), given to the script before
    # the build, so a data file it parks is named there and not beside the
    # staged geometry, a link into the library every simulation on the mesh shares.
    job.work_dir = (
        job.sim_dir
        / SIM_DATAPOINTS_DIR
        / datapoint_dir_name(PointName(point_name(job.case, job.point)))
    )
    job.script.working_dir = str(job.work_dir)
    try:
        with collecting_the_study_skips() as skipped:
            job.recipe(job.point_case, job.script)
        # FR-989: the names the build skipped, recorded only where it skipped one.
        job.base["skipped_names"] = [skip.record() for skip in skipped] or None
        # G02: before the solver starts, and knowing the machine this time.
        _refuse_an_import_count_nothing_logs(job.point_case, job.script, job.executor)
    except Exception as exc:  # recipes are user code; any failure is a build failure
        return RunRecord(
            **job.base,
            status=RunStatus.FAILED_SCRIPT,
            error=f"{type(exc).__name__}: {exc}",
        )
    # Record the snapshot of effective solver flags carried by a script built
    # through the curated solver_settings helper.
    return None


def _retain_point_provenance(job: _PointJob) -> RunRecord | None:
    """Retain point provenance."""
    job.base["probe_field_layout"] = list(job.script.probe_field_layout) or None
    # FR-1047 (PFS-2081.58): the far-field probes this script laid or
    # reused, so post integrates exactly them; one point, so its last layout.
    if job.script.farfield_layout:
        job.base["farfield_layout"] = {"shapes": job.script.farfield_layout[-1]["shapes"]}
    job.base["surface_probe_layout"] = list(job.script.surface_probe_layout) or None
    job.base["frame_motions"] = job.script.frame_motions or None
    job.base["custom_field_coverage"] = job.script.custom_field_coverage
    job.base["freestream_units"] = (
        job.case.variables.get("FREESTREAM_UNITS") or job.case.freestream_units
    )
    setup = job.script.solver_setup
    if setup is not None:
        job.base["solver_setup"] = setup.model_dump(mode="json")
    if job.continues is not None:
        job.predecessor = next(
            (record for record in job.workspace.read_manifest() if record.run_id == job.continues),
            None,
        )
        if job.predecessor is None:
            return RunRecord(
                **job.base,
                status=RunStatus.FAILED_SCRIPT,
                error=(
                    f"cannot recover surface averaging provenance of predecessor {job.continues!r}"
                ),
            )
        from pyflightstream.run._field_motion import continued_frame_motions

        job.base["frame_motions"] = continued_frame_motions(
            job.predecessor.frame_motions, job.script
        )
        if (
            not job.script.raw_flag
            and not job.script.surface_operations
            and job.base["frame_motions"] == job.predecessor.frame_motions
        ):
            job.base["custom_field_coverage"] = job.predecessor.custom_field_coverage
        else:
            job.base["custom_field_coverage"] = {
                "state": "unknown",
                "reason": "Continuation changed geometry or frame provenance.",
            }
        if not job.script.surface_probe_layout and job.predecessor.surface_probe_layout:
            job.base["surface_probe_layout"] = [
                dict(entry) for entry in job.predecessor.surface_probe_layout
            ]
        if not job.script.probe_field_layout:
            if (record := _retain_continued_field_inputs(job, job.predecessor)) is not None:
                return record
        # Preserve the original recorded request when reopening the saved state,
        # including its UNVERIFIED qualification; today's pproc cannot replace it.
        job.script.surface_time_averaging = job.predecessor.surface_time_averaging
        # G25: the window the stopped run was averaged over, not today's pproc's.
        job.script.surface_average_window = job.predecessor.surface_average_window
    job.base["surface_time_averaging"] = job.script.surface_time_averaging
    job.base["surface_average_window"] = job.script.surface_average_window
    # G45: translate VTK in the analysis loads frame the solver writes. A
    # continuation inherits the saved simulation's recorded frame. Refuse an
    # unprovable placement before launching. If the continuation sets no loads
    # frame, inherit it whole: its ledger's default origin does not describe the
    # frame retained by the reopened simulation.
    return None


def _retain_point_translations(job: _PointJob) -> RunRecord | None:
    """Retain point translations."""
    translations = [dict(translation) for translation in job.script.surface_translations]
    inherits = job.continues is not None and not job.script.sets_loads_frame
    if job.continues is not None and any(inherits or _unplaced(entry) for entry in translations):
        carried = _recorded_loads_frame(job.predecessor)
        frame_proof: dict[str, object] = {}
        if carried is None and job.recovered_continuation is not None:
            recovered = job.recovered_continuation.get("recovered_frame")
            proof = job.recovered_continuation.get("frame_recovery")
            if isinstance(recovered, Mapping) and not _unplaced({"frame": recovered}):
                carried = dict(recovered)
                if isinstance(proof, Mapping):
                    frame_proof = {"frame_recovery": dict(proof)}
        if carried is None:
            return RunRecord(
                **job.base,
                status=RunStatus.FAILED_SCRIPT,
                error=(
                    f"the Tecplot surface of this continuation is written by the package from "
                    f"the VTK the solver exports in the analysis loads frame (RPT-074), and "
                    f"the run it continues, {job.continues!r}, recorded no placement of that "
                    "frame. Set "
                    "tecplot = false under the pproc's [exports] to continue it without one."
                ),
            )
        translations = [
            {**entry, "frame": dict(carried), **frame_proof}
            if inherits or _unplaced(entry)
            else entry
            for entry in translations
        ]
    job.base["surface_translations"] = translations or None
    return None


def _write_script_keeping_replaced(
    workspace: Any, sim_id: str, name: str, text: str
) -> tuple[Path, str]:
    """Write a script, first keeping the bytes of a different script it replaces.

    A re-run of a point rewrites the script under the same name; a manifest row
    that recorded the old script's digest would then name bytes that no longer
    exist. The replaced script is copied to ``scripts/archive/`` under its
    digest before the new one is written (FR-3060).
    """
    target = workspace.sim_dir(sim_id) / "scripts" / name
    previous = target.read_bytes() if target.is_file() else None
    written = workspace.write_script(sim_id, name, text)
    if previous is not None and previous != written[0].read_bytes():
        digest = hashlib.sha256(previous).hexdigest()
        kept = target.parent / "archive" / f"{target.stem}.{digest[:16]}{target.suffix}"
        if not kept.exists():
            kept.parent.mkdir(parents=True, exist_ok=True)
            kept.write_bytes(previous)
    return written


def _write_point_script(job: _PointJob) -> RunRecord | None:
    """Write point script."""
    job.rendered = job.script.render()
    job.script_path, job.script_sha = _write_script_keeping_replaced(
        job.workspace, job.case.sim_id, f"{job.stem}.txt", job.rendered
    )
    # FR-91: write probe-point positions beside the script that places them.
    # An unsteady plots table names columns such as MACH7 and VELOCITY7 but does
    # not locate vertex 7. Refuse a filename collision as this point's failure
    # and continue the campaign, as with other build failures.
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
    if job.script.plot_groups and isinstance(job.base.get("reductions"), dict):
        job.base["reductions"]["plot_groups"] = [dict(group) for group in job.script.plot_groups]
    # WHICH ROWS OF THE SECTIONS EXPORT ARE WHICH SURFACE, recorded
    # beside the script that created the distributions, and the empty layout
    # where it created none (`_sections_layout`). A CONTINUATION CREATES NONE
    # AND REOPENS THOSE OF THE RUN IT CONTINUES, whose saved simulation carries
    # them, so it records that run's layout, as it keeps its averaging window.
    if job.continues is not None:
        # A continuation reached here holds the record it continues: a missing
        # one returned a failed record above, so the cast states a fact.
        layout = (
            None
            if creates_surface_sections(job.script.render())
            else cast(RunRecord, job.predecessor).sections_layout
        )
    else:
        layout = _sections_layout(job.script)
    if layout is not None:
        job.base["sections_layout"] = [dict(block) for block in layout]
    # R03: record the script's names beside the layout whose selections use them.
    if job.script.boundary_inventory is not None:
        job.base["inventory"] = list(job.script.boundary_inventory)
    # PFS-2031.13: write SCRIPT-action child scripts and command input files
    # before launch, where the rendered script names them. Relative paths use
    # the solver's working directory; absolute paths remain absolute. Refuse
    # input filename collisions and record the input digests (G02).
    #
    # Local and submitted points use sims/sim_<id>/datapoints/DP-<tag>/ for their
    # outputs, action programs, clock, state and scheduler descriptor (FR-92).
    # This keeps queued points from rewriting each other's files. Exports are
    # relative, as measured on 26.124; inputs use absolute paths (GOAL-021).
    # A steady job containing several points uses the simulation folder instead
    # (_execute_sweep).
    return None


def _write_point_pending_files(job: _PointJob) -> RunRecord | None:
    """Write point pending files."""
    try:
        written = _pending._write_pending_files(
            job.script,
            job.work_dir,
            case=job.case,
            recorded=job.inputs_sha256,
            run_writes=(
                Path(job.script_path),
                *(
                    [job.sim_dir / job.probe_points_file]
                    if job.probe_points_file is not None
                    else []
                ),
                *_descriptor_of(job.executor, job.work_dir),
            ),
        )
    except CampaignConfigError as exc:
        return RunRecord(
            **job.base,
            status=RunStatus.FAILED_SCRIPT,
            error=f"{type(exc).__name__}: {exc}",
        )
    if written:
        job.inputs_sha256 = {**job.inputs_sha256, **written}
        job.base["inputs_sha256"] = job.inputs_sha256
    # PFS-2031.18, FR-314: the counter program the script registers, count-only on a
    # row that asks no per-step export (`run._actions_counter.stage_counter`).
    job.counter = stage_counter(
        job.work_dir, job.script, job.point_case, job.fs_version, job.inputs_sha256
    )
    job.base.update(job.counter or {})
    # FR-98. THE CLOCK PAIR, written the same way and for
    # the same reason: the program is rendered with this row's deadline so
    # the emitted file states the number the run will use, and the script
    # is parked EMPTY so the solver finds a file with no command in it
    # until the clock fires. The state of an EARLIER point of this case is
    # removed, because a clock carried over would fire the second point
    # before its first step.
    if any(use.name == WALLTIME_CLOCK_ACTION for use in job.script.unsteady_actions):
        clock = job.work_dir / WALLTIME_CLOCK_PROGRAM
        clock.parent.mkdir(parents=True, exist_ok=True)
        _textio.write_text(
            clock,
            walltime_clock_program(
                job.point_case, workflow_conventions_for(job.point_case), version=job.fs_version
            ),
        )
        job.base["inputs_sha256"] = {
            **job.base.get("inputs_sha256", job.inputs_sha256),
            WALLTIME_CLOCK_PROGRAM: file_sha256(clock),
            WALLTIME_STOP_SCRIPT: file_sha256(job.work_dir / WALLTIME_STOP_SCRIPT),
        }
        job.base["walltime_s"] = row_walltime_s(job.point_case)
        job.base["walltime_margin_s"] = walltime_margin_s(job.point_case)
    job.base["script_sha256"] = job.script_sha
    job.base["script_path"] = str(Path(job.script_path).relative_to(job.sim_dir).as_posix())
    job.base["raw_flag"] = job.script.raw_flag
    job.base["march_strategy"] = job.script.march_strategy
    # FR-48: a recipe may waive a command the database records broken.
    # The waiver is the recipe's, so the record of it belongs with the
    # run, not with the recipe: this is the only place a reader of the
    # manifest can learn that the numbers below came from a command a
    # probe measured not to work.
    job.base["waived_commands"] = waived_record(job.script)

    # PYFS-006: refuse existing declared outputs before launch. Collection
    # checks existence, which alone cannot prove this run wrote a file. A hash
    # comparison cannot distinguish identical rewrites from untouched files and
    # would spend solver time before refusal. The script is already written, so
    # the refused point records what it would have run. Check the datapoint
    # working directory for both local and submitted points.
    return None


def start_the_wall_clock(job: _PointJob) -> None:
    """Write the job start into the wall clock's state, just before the solver is launched.

    FR-98, PFS-2119.023. THE CLOCK STARTS WHEN THE SOLVER IS LAUNCHED, not at its
    first action call, which is after the first step: a run that launches the
    solver itself hands the clock program its origin through the state file
    (:func:`~pyflightstream.cases.workflows.job_start_state`). A job handed to a
    scheduler waits in a queue this run cannot see, so it keeps the
    first-invocation origin, and its margin must also cover the time before
    the first step.
    """
    if any(use.name == WALLTIME_CLOCK_ACTION for use in job.script.unsteady_actions):
        # F-604: the state of an EARLIER point is removed only here, once the point
        # is certain to launch, so a refusal that launches nothing leaves it as evidence.
        (job.work_dir / WALLTIME_CLOCK_STATE).unlink(missing_ok=True)
    if isinstance(job.executor, LocalExecutor) and any(
        use.name == WALLTIME_CLOCK_ACTION for use in job.script.unsteady_actions
    ):
        _textio.write_text(job.work_dir / WALLTIME_CLOCK_STATE, job_start_state(time.time()))


def _run_point_solver(job: _PointJob) -> RunRecord | None:
    """Run point solver."""
    stale = [name for name in job.point_case.outputs if (job.work_dir / name).exists()]
    if stale:
        return RunRecord(
            **job.base,
            status=RunStatus.FAILED_INCOMPLETE_OUTPUT,
            error=(
                f"declared output(s) {', '.join(stale)} already exist in "
                f"{job.work_dir.relative_to(job.sim_dir).as_posix()}/, the folder this point runs "
                "in, before it ran, so collecting them would attribute somebody else's "
                "file to this run: collection cannot tell a file this solver wrote from "
                "one that was already there. Redo the point with pyfs-matrix run "
                "--force-rerun <point>, which archives what is there first, or remove "
                "the leftover, then re-run."
            ),
        )
    # E2: section files are listed after the run, so refuse any already present.
    leftover = acoustic_section_leftovers(job.work_dir, job.sim_dir)
    if leftover is not None:
        return RunRecord(**job.base, status=RunStatus.FAILED_INCOMPLETE_OUTPUT, error=leftover)
    job.work_dir.mkdir(parents=True, exist_ok=True)

    # FR-99, GEO-047-C04. THE REFUSAL OF A SECOND SUBMITTED POINT OF A ROW IS
    # GONE FROM THIS PATH, and deliberately from this path only (the
    # lifting of GOAL-020's hold, GOAL-021 item 3). It refused because every
    # point shared the simulation folder's action program, script and clock
    # state; each submitted point now runs in its own datapoint folder, so the
    # reason is removed rather than overruled. The swept-steady path is ONE job
    # over every point of its row and never had the refusal to lift.
    # FR-99. WHAT THIS POINT IS, for the scheduler's descriptor, and it is
    # bound per point because a descriptor names the simulation, its wall
    # clock and its processor count, and those are the row's. A local
    # executor has no such method and is handed nothing.
    bind_submission_values(job.executor, job.case, job.point_case)
    # F-612: a write that fails here fails BEFORE the solver is launched.
    start_the_wall_clock(job)
    if job.progress is not None:
        job.progress.solver_started = True
    try:
        job.result = job.executor.run_script(
            job.script_path, working_dir=job.work_dir, timeout_s=job.case.solver.timeout_s
        )
    except CampaignConfigError as exc:
        # THIS POINT'S REFUSAL, recorded, and the campaign goes on (PFS-2094.010): a
        # submitting executor refuses a steady coupled script, or a descriptor or
        # submit placeholder this row does not supply, before anything is sent.
        return RunRecord(
            **job.base, status=RunStatus.FAILED_SCRIPT, error=f"{type(exc).__name__}: {exc}"
        )
    # PYFS-015: record invocation flags, working directory and effective timeout
    # so reproducing a run does not require re-deriving them from executor code.
    job.base["argv"] = list(job.result.argv)
    job.base["cwd"] = job.result.cwd
    job.base["timeout_s"] = job.result.timeout_s
    job.base["executor"] = invocation_record(job.executor, job.result)
    # PFS-2012.08.01. WHEN the solver ran, for the provenance document's
    # activity; None where the executor reports no clock.
    job.base["started_at"] = job.result.started_at
    job.base["finished_at"] = job.result.finished_at
    # PFS-2031.18. How far the counter got, read from the file the
    # program left, on every path below: a failed execution's count is
    # evidence about the failure. None when the file was never written,
    # which is a run with no counter or a solver that never reached a
    # time step.
    if job.counter is not None:
        job.base["action_count"] = action_count(job.work_dir / UNSTEADY_ACTION_COUNT)
    # FR-98. WHETHER THE CLOCK FIRED, read from the state the program left.
    # This is the only thing that knows: the solver reports a run that
    # ended, and the difference between ending because it finished and
    # ending because the watchdog stopped it is here or nowhere.
    stopped = _walltime_stop(job.work_dir / WALLTIME_CLOCK_STATE)
    if stopped is not None:
        job.base["stopped_at"] = stopped
    # FR-99. READ BEFORE THE FAILURE BRANCH, because the likeliest cluster
    # failure is a REJECTED SUBMISSION and the descriptor is written before
    # the scheduler is called. Read after it, a rejected job produced a
    # FAILED_EXECUTION record with no descriptor, no profile and no
    # submitted flag: the one thing FR-99 says names where the job went,
    # missing from the record of the case that most needs it (the
    # architect lens, round two). `submitted` distinguishes not-sent from
    # sent-and-refused, so the failure record needs no new vocabulary.
    submitted = _submission_record(job.executor)
    if job.result.failed:
        # Use the shared diagnostic composer, including all captured channels on
        # timeout: standard output may hold pre-script evidence (INC-20260809-2230).
        error = job.result.diagnosis()
        return RunRecord(
            **job.base,
            status=RunStatus.FAILED_EXECUTION,
            wall_time_s=job.result.wall_time_s,
            error=error,
            submission=submitted,
        )

    # FR-99. A SUBMITTED POINT HAS NO OUTPUTS YET, so nothing below runs.
    # The scheduler has taken the job and the solver has not started; a
    # collection here would find nothing and call it an incomplete output,
    # and an assessment would read a log that does not exist. The record
    # says SUBMITTED, which is the eighth status and is not a failure, and
    # it carries the descriptor the scheduler was handed so the job can be
    # found again.
    if submitted is not None:
        return RunRecord(
            **job.base,
            status=RunStatus.SUBMITTED,
            wall_time_s=None,
            outputs=[],
            # FR-99: record the collector's expected outputs at submission. Reading an
            # edited matrix later could substitute different conditions (GEO-039-F02).
            # outputs remains empty because the submitted point has collected nothing;
            # these names describe what it was built to write.
            submission={
                **submitted,
                "declared_outputs": list(job.point_case.outputs),
                # GOAL-021 item 3: WHERE the job runs and writes, relative to
                # the simulation folder so a moved workspace still resolves;
                # the collector waits on the declared outputs here.
                "working_dir": job.work_dir.relative_to(job.sim_dir).as_posix(),
                # G02: the points the script imports, which the collector
                # compares with the count the solver logs.
                **(
                    {"wake_edge_points": job.script.wake_edge_points}
                    if job.script.wake_edge_points is not None
                    else {}
                ),
                # G06: every file the point was told to write its log to,
                # whatever its name, the output its LOG_OUTPUT names among them;
                # the collector reads the four lines in each.
                "declared_logs": _declared_logs(job.point_case, job.rendered),
            },
        )

    # G45: THE TECPLOT IS WRITTEN FROM THE VTK before anything is collected, at
    # the name the solver's own had, and each per-step VTK into its own step's.
    return None


def _collect_point_outputs(job: _PointJob) -> RunRecord | None:
    """Collect point outputs."""
    if job.base.get("surface_translations"):
        job.base["surface_translations"] = translate_surface_exports(
            job.work_dir,
            job.base["surface_translations"],  # type: ignore[arg-type]
        )
    # On a machine that cannot export the log, write it from captured solver
    # output, or excuse it when nothing was captured: the machine cannot write
    # one locally. Other runs need no special handling here.
    job.local_log = _the_local_log(
        job.executor, _local_logs(job.point_case, job.rendered), job.work_dir, job.result
    )
    # Record outputs the package's post-processing could not write despite
    # the solver writing their sources (untranslated_surfaces).
    job.post_warnings = []
    try:
        job.collected = job.workspace.collect_outputs(
            job.case.sim_id,
            [
                job.work_dir / name
                for name in job.point_case.outputs
                if name != job.local_log.excused
            ],
            # FR-92: collect in the point's own folder, steady or unsteady. Pass the
            # checked point name so collection and assessment render the same folder.
            datapoint=PointName(point_name(job.case, job.point)),
            # Every point runs in its collection folder; outputs are already filed.
            ran_in_datapoint=True,
        )
        # E2: list acoustic section files where the solver wrote them.
        job.collected = acoustic_section_outputs(
            job.workspace.sim_dir(job.case.sim_id), job.collected
        )
    except MissingOutputsError as exc:
        exc.collected = acoustic_section_outputs(
            job.workspace.sim_dir(job.case.sim_id), exc.collected
        )
        # A COMPLETED SOLVE IS NOT DEMOTED BY THE PACKAGE'S OWN POST-PROCESSING
        # . A Tecplot the package failed to write from the VTK the
        # solver did write is not a missing solver output: the point is
        # assessed as any other and the failure is a warning on the record.
        untranslated = untranslated_surfaces(
            job.base.get("surface_translations"), exc.missing, exc.collected
        )
        if untranslated is None:
            # File, list and hash every written output so products can use it.
            # The error names only missing outputs.
            return RunRecord(
                **job.base,
                status=RunStatus.FAILED_INCOMPLETE_OUTPUT,
                wall_time_s=job.result.wall_time_s,
                outputs=exc.collected,
                outputs_sha256=job.workspace.output_digests(job.case.sim_id, exc.collected),
                residual_note=job.local_log.note,
                error=str(exc) + _translation_problems(job.base.get("surface_translations")),
            )
        job.collected = exc.collected
        job.post_warnings = untranslated
        for line in untranslated:
            warnings.warn(
                f"{point_name(job.case, job.point)}: {line}", PyflightstreamWarning, stacklevel=2
            )
    except (WorkspaceError, CampaignConfigError) as exc:
        # Catch both collection refusals as this point's failure. collect_outputs
        # can raise WorkspaceError or CampaignConfigError when point_tag cannot
        # render an unknown axis. Neither should abort the campaign after launch.
        return RunRecord(
            **job.base,
            status=RunStatus.FAILED_INCOMPLETE_OUTPUT,
            wall_time_s=job.result.wall_time_s,
            error=str(exc),
        )

    return None


def _assess_point_record(job: _PointJob) -> RunRecord:
    """Assess point record."""
    assessment = job.assess(job.point_case, job.result, job.sim_dir)
    # FR-98. THE CLOCK'S VERDICT WINS, and only over a converged one.
    # A run the watchdog stopped did not converge and did not fail: it
    # ran out of clock with its outputs written, which is a state of
    # its own and the reason the value exists. A run that DIVERGED and
    # then hit the clock is still diverged, so a failure is left alone.
    status = (
        RunStatus.WALLTIME_REACHED
        if job.base.get("stopped_at") and not str(assessment.status).startswith("FAILED")
        else assessment.status
    )
    # G02. A run that imported trailing edges is held to the count the solver
    # logged, over any status that is not already a failure.
    # The log is found by the name the assessor read it under, else by the name
    # a local run on a machine that cannot export one wrote it under:
    # the solver's printed output need not read as a residual history to carry
    # the count.
    named_log = assessment.log_file_used or (
        Path(job.local_log.written).name if job.local_log.written else None
    )
    # On a machine that cannot export the log, what the solver printed is the
    # point's log when nothing else is, as it is a local steady job's: a row that
    # declares no log output wrote none from it above.
    printed = (
        job.result.captured_output()
        if isinstance(job.executor, LocalExecutor) and not job.executor.export_log
        else ""
    )
    log_text = _run_log_text(job.sim_dir, job.collected, named_log, job.result) or (printed or None)
    status, error = with_wake_edge_verdict(
        status,
        assessment.error,
        _no_local_log_verdict(job.script.wake_edge_points, log_text, job.local_log.note)
        if job.local_log.excused and job.local_log.note
        else wake_edge_import_verdict(job.script.wake_edge_points, log_text),
    )
    # G06. A run whose log says the solver could not use its actuator disc's
    # profile file went on to the end with a loading that is not the file's, and
    # its outputs look like any other run's; the line is the one statement of it.
    # The log the solver left is read too, where the collected log is another,
    # and so is every collected log, a log that is no residual history too; a
    # log is every file the script or LOG_OUTPUT names as one, whatever its name.
    status, error = with_wake_edge_verdict(
        status,
        error,
        actuator_profile_verdict(
            log_text,
            job.result.log_text,
            printed,
            *collected_log_texts(
                job.sim_dir, job.collected, _declared_logs(job.point_case, job.rendered)
            ),
        ),
    )
    step_warning = missing_step_warning(
        job.base.get("action_program"),
        job.base.get("action_count"),
        job.base.get("export_window"),
        assessment.time_steps,
    )
    # Record what the judgment lacked: an unreadable quasi-steady record.
    for line in assessment.warnings or []:
        warnings.warn(
            f"{point_name(job.case, job.point)}: {line}", PyflightstreamWarning, stacklevel=2
        )
    return RunRecord(
        **job.base,
        status=status,
        warnings=[
            *job.post_warnings,
            *(assessment.warnings or []),
            *([step_warning] if step_warning else []),
        ],
        iterations=assessment.iterations,
        residual=assessment.residual,
        fs_version_reported=assessment.fs_version_reported,
        fs_build=assessment.fs_build,
        wall_time_s=job.result.wall_time_s,
        outputs=job.collected,
        # PYFS-006, the other half of "which file is this record about".
        # The refusal above stops a stale file becoming evidence; this
        # states which bytes the evidence WAS, so a file edited or
        # replaced after the run stops matching its own record. inputs
        # have carried this since the first manifest; outputs never did.
        outputs_sha256=job.workspace.output_digests(job.case.sim_id, job.collected),
        # REV010-001. The decision is persisted, not just acted on: a later
        # reader of the manifest can see which axes were compared, by how
        # much the export deviated, and what tolerance let it through. A
        # status alone cannot answer "was this result ever bound to the
        # point it claims", and that question is the whole finding.
        conditions=assessment.conditions,
        log_file_used=assessment.log_file_used,
        residual_note="; ".join(
            note for note in (assessment.residual_note, job.local_log.note) if note
        )
        or None,
        solver_run_time_s=assessment.solver_run_time_s,
        solver_initialization_s=assessment.solver_initialization_s,
        time_steps=assessment.time_steps,
        # FR-974: the limit rides only on the FINAL status MAX_ITER_REACHED, so a
        # walltime or log verdict that overrode the assessment does not carry it.
        iterations_requested=(
            assessment.iterations_requested if status is RunStatus.MAX_ITER_REACHED else None
        ),
        clocking_verdicts=assessment.clocking_verdicts,
        error=error,
    )


def _retain_continued_field_inputs(job: _PointJob, predecessor: RunRecord) -> RunRecord | None:
    """Retain a predecessor's field evidence and input digests."""
    from pyflightstream.run._field_motion import continued_field_inputs

    try:
        inherited_fields = continued_field_inputs(predecessor, job.sim_dir)
    except (OSError, ValueError, KeyError) as exc:
        return RunRecord(
            **job.base,
            status=RunStatus.FAILED_SCRIPT,
            error=f"cannot retain continued field evidence: {exc}",
        )
    for key, value in inherited_fields.items():
        if job.base.get(key) is None:
            job.base[key] = value
    if inherited_fields:
        inherited_path = str(inherited_fields["probe_points_file"])
        job.inputs_sha256 = {
            **job.inputs_sha256,
            inherited_path: file_sha256(job.sim_dir / inherited_path),
        }
        job.base["inputs_sha256"] = job.inputs_sha256
    return None
