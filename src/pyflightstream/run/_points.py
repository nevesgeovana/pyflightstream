"""One campaign point: render, run or submit, assess, record.

Private to :mod:`pyflightstream.run`. :func:`_execute_point` is the path of
every point that is not part of a steady row run as one job; the helpers
beside it build the records of a point that could not be written, and the
verdicts on the solver log a local run leaves or does not leave. The sweep
path above reuses those helpers.
"""

from __future__ import annotations

import warnings
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
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
    _LOG_OUTPUT_SUFFIX,
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
    exports state none, and a record saying nothing read as one written
    before 0.24.0, so the post refused the split and advised a new run that
    recorded nothing again. None where the script changes sections the builder
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

    0.30.0. The run path writes a script, its input files and its state before
    the solver starts, and a workspace on a network share can refuse any one of
    those writes with an ``OSError``. That escaped the loop, ended the run and
    left every later planned point with no record. The caller now catches it
    and records the point from what this holds.
    """

    #: The record fields as the path had built them, None before they exist.
    #: A keyword bag for a record constructor is ``dict[str, Any]``: its values
    #: differ by key, and the record's own model checks each one when it is built.
    base: dict[str, Any] | None = None
    #: Whether the solver had been launched when the error came.
    solver_started: bool = False


def _unwritable(error: OSError, where: str) -> str:
    """Say which write failed and what the run did about it (0.30.0)."""
    return (
        f"{type(error).__name__}: {error}, {where}. A file of this point could not be "
        "written (a workspace on a network share that refuses a write is one cause), so "
        "the point is recorded failed and the run went on with the next point. Make the "
        "folder writable and run the point again: pyfs-matrix run --force-rerun <point>"
    )


def _bare_record(
    campaign: Campaign, case: SimCase, point: Mapping[str, float], run_id: str, canonical: str
) -> dict[str, object]:
    """Return the fields a record of a point that never built its own can state (0.30.0)."""
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
    """Record one point whose run raised an ``OSError`` (0.30.0).

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

    0.27.0. Such a machine's scheduler writes the log of a SUBMITTED job, and
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
    executor: object, outputs: Sequence[str], work_dir: Path, result: ExecutionResult
) -> _LocalLog:
    """Write a local point's declared log from the solver's output, or excuse it (0.27.0).

    Only on a local executor whose machine cannot export the log; on any other
    run nothing is written and nothing is excused. The declared log is the
    output named like one (``_log.txt``), the name `collect` copies a
    scheduler's log to, and a log the solver did write is never overwritten.
    """
    if not isinstance(executor, LocalExecutor) or executor.export_log:
        return _LocalLog()
    declared = [str(name) for name in outputs if str(name).endswith(_LOG_OUTPUT_SUFFIX)]
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

    ``progress`` is filled as the point goes (0.30.0): the record fields as
    they stand, and whether the solver was started, so a caller that catches
    an ``OSError`` this raises records the point from them rather than
    leaving it with no record.
    """
    package_commit, package_dirty = package_vcs_state()
    # THE STATE OF THIS POINT, NOT OF THE ROW (0.24.0). Every state field below
    # read `case.*`, the simulation-level case, while the point's own case went
    # to the script alone. On a row sweeping a flow variable each point therefore
    # ran at its own Mach, velocity and density and RECORDED the first point's,
    # and the rotor table then divided one point's force by another's density.
    # `case_at_point` is the one function that resolves a point; asking it here
    # is what makes the record describe what the solver was given.
    at_point = case_at_point(case, point)
    base: dict[str, Any] = {
        "run_id": run_id,
        "sim_id": case.sim_id,
        "point": dict(point),
        "point_name": point_name(case, point),
        "sweep_name": sweep_name(case),
        "matrix_stem": campaign.matrix_stem,
        # The run this one CONTINUES, in the base dict so that a continuation
        # that fails says so as well: the chain is a fact about the attempt,
        # not about its success. None for every point that continues nothing.
        "continues": continues,
        "restart": (recovered_continuation or {}).get("restart") if continues else None,
        "fs_version_requested": canonical,
        "package_version": pyflightstream.__version__,
        "package_commit": package_commit,
        "package_dirty": package_dirty,
        # v0.23.0 item 12. CAPTURED HERE because this is the only moment it
        # is knowable: who submitted a run cannot be recovered afterwards.
        "submitted_by": submitted_by(),
        "recipe": case.recipe,
        "recipe_sha256": _recipe_digest(recipe),
        # The BUILD's executable, which is the campaign's unless the case
        # named another. Recording campaign.fs_exe unconditionally is what
        # made a per-case build unstatable: the record would name an
        # executable the point never ran (PFS-2009.05).
        "fs_exe": str(fs_exe),
        "fs_exe_sha256": _file_digest(fs_exe),
        # WHICH of the two sources chose that build, beside WHICH build it
        # was. The pair above reproduces the run; without this a reader of
        # a finished record cannot tell a build chosen FOR THIS ROW from
        # one inherited from the campaign, and the two are different facts
        # about how the study was configured (PFS-2009.08.02).
        "fs_version_source": fs_version_source,
        # The velocity the case ASKED for, in the base dict rather than in
        # the success path: four early returns below build the record from
        # `base` alone, so a field written later would be absent from
        # exactly the failed points a reader most wants to compare
        # (OPS-2009.01.13).
        "velocity_requested_m_s": at_point.velocity,
        # The post-processing artifact the row named (PFS-2029.16), so a
        # reader of the record knows which sections, plots and products
        # the point was run for without opening the matrix.
        "pproc": case.pproc_id,
        "inventory_source": case.inventory_source,
        "mesh_import": None
        if case.mesh_import is None
        else case.mesh_import.model_dump(mode="json", exclude_none=True),
        "motions": [dict(record) for record in case.motions],
        # The windows of every reduction the products stage will write for
        # this point (PFS-2015.04), resolved off the row HERE, where the
        # clock and the blade count are stated, so the stage reads the
        # record alone as it reads everything else. None for a steady row.
        # THE POINT-BEARING CASE, and this line read `reduction_windows(case)`
        # until 2026-09-11. `case` here is the SIM-level case and its `point` is
        # empty: `point_case` is built two hundred lines below, after the names
        # are rendered. So a row sweeping its advance ratio asked the planner a
        # question about a case that did not know which point it was, and the
        # planner correctly answered that no rotor speed was stated. Every
        # unsteady reduction of every swept-ratio point was skipped, four of
        # four on the licensed runs of 2026-09-11.
        #
        # The unit case for that fix passed while this path still failed,
        # because the case it builds carries its point and this one did not.
        "reductions": reduction_windows(case_at_point(case, point)),
        # 0.30.0 (M1): each rotor's tip and helical Mach numbers at THIS point,
        # from the point's own resolved state; None (and absent from the file)
        # where rotor_machs covers nothing: a row turning no rotor at a stated
        # speed and naming no actuator disc.
        "rotor_mach": {mach.alias: mach.record() for mach in rotor_machs(at_point)} or None,
        # How the geometry was staged (PFS-2029.17), read off the workspace
        # that staged it, so the record says link or copy and why.
        **dict(
            zip(
                ("staged_as", "staged_as_reason"),
                workspace.staged_as(case.sim_id) if staged_geometry is not None else (None, None),
                strict=True,
            )
        ),
        # The template that rendered this point's names (PFS-2029.19.01),
        # so a reader can tell a name from the identity beside it.
        "point_name_template": workspace.naming.point_name,
        "description": case.description or None,
        "mach": at_point.mach,
        "reference": _reference_block(case),
        "campaign_name_from": name_from,
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
        "inputs_sha256": inputs_sha256,
        "script_sha256": "",
        "raw_flag": False,
        "waived_commands": [],
        # PFS-2033.02: the setup's raw commands, as the script carried them.
        "raw_commands": [entry.model_dump(mode="json") for entry in case.raw_commands],
        # The design decision of 2026-09-09: the setup's aliases, for the products stage.
        "aliases": {name: list(members) for name, members in case.aliases.items()},
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
    if progress is not None:
        progress.base = base
    if preparation_error is not None or recipe is None:
        error: str | None = preparation_error or "recipe resolution failed"
        return RunRecord(**base, status=RunStatus.FAILED_SCRIPT, error=error)

    # A POINT ALREADY IN A QUEUE IS NOT SUBMITTED AGAIN, and it is refused
    # BEFORE ANY OF ITS FILES IS WRITTEN (the independent review of the
    # 0.18.1 release). A submitted point runs in its datapoint folder, which
    # carries no campaign name, so the same point submitted under another
    # campaign landed in the queued job's folder and rewrote its script,
    # descriptor, action files and clock while the stale-output check
    # passed, because the queued job had written nothing yet. The guard is
    # per simulation AND point: different points of one row still submit
    # together, which is the refusal that was lifted and stays lifted.
    queued = _queued_record_of_point(workspace, case.sim_id, point_name(case, point))
    if queued is not None:
        return RunRecord(
            **base,
            status=RunStatus.FAILED_SCRIPT,
            error=(
                f"point {point_name(case, point)} of simulation {case.sim_id} is already in a "
                f"scheduler's queue as {queued.run_id!r}, and a submitted point runs in its "
                "own datapoint folder, which that job has not finished writing. Collect it "
                "(pyfs-matrix collect) before submitting this point again; nothing of it was "
                "written."
            ),
        )
    try:
        stem, outputs = _point_names(campaign, case, point, workspace)
    except NamingTemplateError as exc:
        return RunRecord(**base, status=RunStatus.FAILED_SCRIPT, error=str(exc))
    update: dict[str, object] = {"outputs": outputs}
    if staged_geometry is not None:
        update["geometry"] = staged_geometry
    point_case = _with_the_profile_s_log(case_at_point(case, point, **update), executor)
    # The BUILD's version, so a case sent to a second installation emits
    # the commands that installation documents rather than the campaign's.
    script = Script(version=fs_version)
    # G02: the folder this point runs in (see below), given to the script before
    # the build, so a data file it parks is named there and not beside the
    # staged geometry, a link into the library every simulation on the mesh shares.
    work_dir = sim_dir / SIM_DATAPOINTS_DIR / datapoint_dir_name(PointName(point_name(case, point)))
    script.working_dir = str(work_dir)
    try:
        recipe(point_case, script)
        # G02: before the solver starts, and knowing the machine this time.
        _refuse_an_import_count_nothing_logs(point_case, script, executor)
    except Exception as exc:  # recipes are user code; any failure is a build failure
        return RunRecord(
            **base,
            status=RunStatus.FAILED_SCRIPT,
            error=f"{type(exc).__name__}: {exc}",
        )
    # Provenance (decision 4 of 2026-07-22): a script built through the
    # curated solver_settings helper carries the snapshot of every
    # solver flag's effective value; record it with the run.
    base["probe_field_layout"] = list(script.probe_field_layout) or None
    base["surface_probe_layout"] = list(script.surface_probe_layout) or None
    base["frame_motions"] = script.frame_motions or None
    base["custom_field_coverage"] = script.custom_field_coverage
    base["freestream_units"] = case.variables.get("FREESTREAM_UNITS") or case.freestream_units
    setup = script.solver_setup
    if setup is not None:
        base["solver_setup"] = setup.model_dump(mode="json")
    if continues is not None:
        predecessor = next(
            (record for record in workspace.read_manifest() if record.run_id == continues), None
        )
        if predecessor is None:
            return RunRecord(
                **base,
                status=RunStatus.FAILED_SCRIPT,
                error=f"cannot recover surface averaging provenance of predecessor {continues!r}",
            )
        from pyflightstream.run._field_motion import continued_field_inputs, continued_frame_motions

        base["frame_motions"] = continued_frame_motions(predecessor.frame_motions, script)
        if (
            not script.raw_flag
            and not script.surface_operations
            and base["frame_motions"] == predecessor.frame_motions
        ):
            base["custom_field_coverage"] = predecessor.custom_field_coverage
        else:
            base["custom_field_coverage"] = {
                "state": "unknown",
                "reason": "Continuation changed geometry or frame provenance.",
            }
        if not script.surface_probe_layout and predecessor.surface_probe_layout:
            base["surface_probe_layout"] = [
                dict(entry) for entry in predecessor.surface_probe_layout
            ]
        if not script.probe_field_layout:
            try:
                inherited_fields = continued_field_inputs(predecessor, sim_dir)
            except (OSError, ValueError, KeyError) as exc:
                return RunRecord(
                    **base,
                    status=RunStatus.FAILED_SCRIPT,
                    error=f"cannot retain continued field evidence: {exc}",
                )
            for key, value in inherited_fields.items():
                if base.get(key) is None:
                    base[key] = value
            if inherited_fields:
                inherited_path = str(inherited_fields["probe_points_file"])
                inputs_sha256 = {
                    **inputs_sha256,
                    inherited_path: file_sha256(sim_dir / inherited_path),
                }
                base["inputs_sha256"] = inputs_sha256
        # Preserve the original recorded request when reopening the saved state,
        # including its UNVERIFIED qualification; today's pproc cannot replace it.
        script.surface_time_averaging = predecessor.surface_time_averaging
        # G25: the window the stopped run was averaged over, not today's pproc's.
        script.surface_average_window = predecessor.surface_average_window
    base["surface_time_averaging"] = script.surface_time_averaging
    base["surface_average_window"] = script.surface_average_window
    # G45. WHAT THE RUN WRITES FROM THE VTK, and the loads frame the solver
    # writes it in. A continuation's is the saved simulation's, which the run it
    # continues placed and recorded; one that recorded none cannot be undone,
    # and the point is refused before the solver starts rather than after.
    # A CONTINUATION THAT SETS NO LOADS FRAME OF ITS OWN INHERITS IT WHOLE: its
    # script reopens the saved simulation and passes no moment point, so its
    # ledger still reports the reference frame at the origin it starts from,
    # which is placed and is not the frame the solver writes the VTK in
    # (reading C32 of 0.28.0).
    translations = [dict(translation) for translation in script.surface_translations]
    inherits = continues is not None and not script.sets_loads_frame
    if continues is not None and any(inherits or _unplaced(entry) for entry in translations):
        carried = _recorded_loads_frame(predecessor)
        frame_proof: dict[str, object] = {}
        if carried is None and recovered_continuation is not None:
            recovered = recovered_continuation.get("recovered_frame")
            proof = recovered_continuation.get("frame_recovery")
            if isinstance(recovered, Mapping) and not _unplaced({"frame": recovered}):
                carried = dict(recovered)
                if isinstance(proof, Mapping):
                    frame_proof = {"frame_recovery": dict(proof)}
        if carried is None:
            return RunRecord(
                **base,
                status=RunStatus.FAILED_SCRIPT,
                error=(
                    f"the Tecplot surface of this continuation is written by the package from "
                    f"the VTK the solver exports in the analysis loads frame (RPT-074), and "
                    f"the run it continues, {continues!r}, recorded no placement of that "
                    "frame: it was recorded before 0.28.0 or exported no Tecplot. Set "
                    "tecplot = false under the pproc's [exports] to continue it without one."
                ),
            )
        translations = [
            {**entry, "frame": dict(carried), **frame_proof}
            if inherits or _unplaced(entry)
            else entry
            for entry in translations
        ]
    base["surface_translations"] = translations or None
    rendered = script.render()
    script_path, script_sha = workspace.write_script(case.sim_id, f"{stem}.txt", rendered)
    # FR-91. WHERE THIS SCRIPT PUT ITS PROBE POINTS, written next to the
    # script that placed them. An unsteady plots export numbers its columns
    # `MACH7`, `VELOCITY7` and never says where vertex 7 is, so this file is
    # the only thing that can place a point of that table.
    #
    # A COLLISION HERE IS THIS POINT'S FAILURE AND NOT THE CAMPAIGN'S. The
    # refusal was the one statement in this function that escaped the loop,
    # so a single row whose name collides with a points file the user wrote
    # aborted a campaign whose earlier points had already spent the licence
    # (the interface lens at the release boundary, 2026-09-11). Every other
    # build failure around it records the point and carries on, and a seat
    # is the scarce thing here.
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
    if script.plot_groups and isinstance(base.get("reductions"), dict):
        base["reductions"]["plot_groups"] = [dict(group) for group in script.plot_groups]
    # WHICH ROWS OF THE SECTIONS EXPORT ARE WHICH SURFACE (0.24.0), recorded
    # beside the script that created the distributions, and the empty layout
    # where it created none (`_sections_layout`). A CONTINUATION CREATES NONE
    # AND REOPENS THOSE OF THE RUN IT CONTINUES, whose saved simulation carries
    # them, so it records that run's layout, as it keeps its averaging window.
    if continues is not None:
        # A continuation reached here holds the record it continues: a missing
        # one returned a failed record above, so the cast states a fact.
        layout = (
            None
            if creates_surface_sections(script.render())
            else cast(RunRecord, predecessor).sections_layout
        )
    else:
        layout = _sections_layout(script)
    if layout is not None:
        base["sections_layout"] = [dict(block) for block in layout]
    # R03 of 0.27.0: the names the script was built over, beside the layout
    # whose selections the post reads over them.
    if script.boundary_inventory is not None:
        base["inventory"] = list(script.boundary_inventory)
    # PFS-2031.13. The child script of a SCRIPT action is parked on the
    # script by helpers.unsteady_action and written HERE, before the
    # solver starts, where the registration line names it: a relative
    # path lands in the solver's working directory, the point's own
    # datapoint folder since 0.27.0, an absolute one where it says. Until this existed the
    # helper promised a writer that did not exist, and a SCRIPT action
    # registered through it named a file that was never there.
    #
    # GOAL-021 ITEM 3, PFS-2010.01.02: A SUBMITTED POINT RUNS IN ITS OWN
    # DATAPOINT FOLDER, `sims/sim_<id>/datapoints/DP-<tag>/`, the folder its
    # outputs are filed under since 0.16.0 (FR-92). Every file below that
    # was written to the working directory follows it: the action programs,
    # the clock and its state, and the scheduler's descriptor. That removes
    # the reason a second submitted point of a row was refused, which was
    # that all of them rewrote those files under a job still in a queue.
    #
    # A LOCAL POINT RUNS THERE TOO, since 0.27.0, so every output is WRITTEN
    # where it is filed rather than moved there by collection. It ran in the
    # simulation folder until then, and a point whose run or collection failed
    # left its exports there, the per-step ones included, in the folder every
    # point of the row shares (measured on a cluster, 2026-09-24). The script
    # is unchanged: its exports are named relative to the working directory,
    # the form measured on 26.124, and every input it reads is named by
    # absolute path since 0.18.1, which is what makes the working directory
    # free to move at all (GOAL-021 item 2). The files it parks, the action
    # program, the clock and the trailing-edge node file, are written relative
    # to this folder below, as they are for a submitted point. The steady job
    # of several points keeps the simulation folder (`_execute_sweep`).
    # G02: and the data files a command reads, the trailing-edge node file,
    # whose digests join the inputs the record states; one that shares its
    # name with another input is refused here, before the solver starts.
    try:
        written = _pending._write_pending_files(
            script,
            work_dir,
            case=case,
            recorded=inputs_sha256,
            run_writes=(
                Path(script_path),
                *([sim_dir / probe_points_file] if probe_points_file is not None else []),
                *_descriptor_of(executor, work_dir),
            ),
        )
    except CampaignConfigError as exc:
        return RunRecord(
            **base,
            status=RunStatus.FAILED_SCRIPT,
            error=f"{type(exc).__name__}: {exc}",
        )
    if written:
        inputs_sha256 = {**inputs_sha256, **written}
        base["inputs_sha256"] = inputs_sha256
    # PFS-2031.18, FR-314: the counter program the script registers, count-only on a
    # row that asks no per-step export (`run._actions_counter.stage_counter`).
    counter = stage_counter(work_dir, script, point_case, fs_version, inputs_sha256)
    base.update(counter or {})
    # FR-98. THE CLOCK PAIR, written the same way and for
    # the same reason: the program is rendered with this row's deadline so
    # the emitted file states the number the run will use, and the script
    # is parked EMPTY so the solver finds a file with no command in it
    # until the clock fires. The state of an EARLIER point of this case is
    # removed, because a clock carried over would fire the second point
    # before its first step.
    if any(use.name == WALLTIME_CLOCK_ACTION for use in script.unsteady_actions):
        clock = work_dir / WALLTIME_CLOCK_PROGRAM
        clock.parent.mkdir(parents=True, exist_ok=True)
        _textio.write_text(
            clock,
            walltime_clock_program(
                point_case, workflow_conventions_for(point_case), version=fs_version
            ),
        )
        (work_dir / WALLTIME_CLOCK_STATE).unlink(missing_ok=True)
        base["inputs_sha256"] = {
            **base.get("inputs_sha256", inputs_sha256),
            WALLTIME_CLOCK_PROGRAM: file_sha256(clock),
            WALLTIME_STOP_SCRIPT: file_sha256(work_dir / WALLTIME_STOP_SCRIPT),
        }
        base["walltime_s"] = row_walltime_s(point_case)
        base["walltime_margin_s"] = walltime_margin_s(point_case)
    base["script_sha256"] = script_sha
    base["script_path"] = str(Path(script_path).relative_to(sim_dir).as_posix())
    base["raw_flag"] = script.raw_flag
    base["march_strategy"] = script.march_strategy
    # FR-48: a recipe may waive a command the database records broken.
    # The waiver is the recipe's, so the record of it belongs with the
    # run, not with the recipe: this is the only place a reader of the
    # manifest can learn that the numbers below came from a command a
    # probe measured not to work.
    base["waived_commands"] = [use.model_dump(mode="json") for use in script.waived_commands]

    # PYFS-006. Every point of a case ran in the same simulation folder until
    # 0.27.0, and collection asks only whether the declared output EXISTS, never
    # whether this run produced it. A file left there by anything else, a
    # point that failed after the solver wrote, a hand copy, an aborted
    # sweep, was collected as this point's evidence and the point was
    # published CONVERGED from a solver that wrote nothing at all. The
    # measurement is in the commit message; the record was
    # indistinguishable from a real one.
    #
    # Refused before the solver runs rather than reconciled afterwards. A
    # baseline hash comparison would also work and is strictly weaker: it
    # cannot tell a rewritten identical file from an untouched one, and it
    # spends solver time before saying so. The script is already written,
    # so the refused point still records the script it would have run.
    # IN THE WORKING DIRECTORY, which is the point's datapoint folder, for a
    # submitted point and, since 0.27.0, for a local one: a file an earlier run
    # of the point left there is exactly what this refuses to collect as the
    # new run's evidence.
    stale = [name for name in point_case.outputs if (work_dir / name).exists()]
    if stale:
        return RunRecord(
            **base,
            status=RunStatus.FAILED_INCOMPLETE_OUTPUT,
            error=(
                f"declared output(s) {', '.join(stale)} already exist in "
                f"{work_dir.relative_to(sim_dir).as_posix()}/, the folder this point runs "
                "in, before it ran, so collecting them would attribute somebody else's "
                "file to this run: collection cannot tell a file this solver wrote from "
                "one that was already there. Redo the point with pyfs-matrix run "
                "--force-rerun <point>, which archives what is there first, or remove "
                "the leftover, then re-run."
            ),
        )
    # 0.32.0 (E2): a section's files are listed after the run, so one already there is refused.
    leftover = acoustic_section_leftovers(work_dir, sim_dir)
    if leftover is not None:
        return RunRecord(**base, status=RunStatus.FAILED_INCOMPLETE_OUTPUT, error=leftover)
    work_dir.mkdir(parents=True, exist_ok=True)

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
    bind_submission_values(executor, case, point_case)
    if progress is not None:
        progress.solver_started = True
    result = executor.run_script(script_path, working_dir=work_dir, timeout_s=case.solver.timeout_s)
    # PYFS-015. The invocation is the half of a run that lived only in the
    # executor's code: which flags, which directory, which effective
    # timeout. Reproducing a run from its record used to mean re-deriving
    # all three from a class that may have changed since.
    base["argv"] = list(result.argv)
    base["cwd"] = result.cwd
    base["timeout_s"] = result.timeout_s
    base["executor"] = invocation_record(executor, result)
    # PFS-2012.08.01. WHEN the solver ran, for the provenance document's
    # activity; None where the executor reports no clock.
    base["started_at"] = result.started_at
    base["finished_at"] = result.finished_at
    # PFS-2031.18. How far the counter got, read from the file the
    # program left, on every path below: a failed execution's count is
    # evidence about the failure. None when the file was never written,
    # which is a run with no counter or a solver that never reached a
    # time step.
    if counter is not None:
        base["action_count"] = action_count(work_dir / UNSTEADY_ACTION_COUNT)
    # FR-98. WHETHER THE CLOCK FIRED, read from the state the program left.
    # This is the only thing that knows: the solver reports a run that
    # ended, and the difference between ending because it finished and
    # ending because the watchdog stopped it is here or nowhere.
    stopped = _walltime_stop(work_dir / WALLTIME_CLOCK_STATE)
    if stopped is not None:
        base["stopped_at"] = stopped
    # FR-99. READ BEFORE THE FAILURE BRANCH, because the likeliest cluster
    # failure is a REJECTED SUBMISSION and the descriptor is written before
    # the scheduler is called. Read after it, a rejected job produced a
    # FAILED_EXECUTION record with no descriptor, no profile and no
    # submitted flag: the one thing FR-99 says names where the job went,
    # missing from the record of the case that most needs it (the
    # architect lens, round two). `submitted` distinguishes not-sent from
    # sent-and-refused, so the failure record needs no new vocabulary.
    submitted = _submission_record(executor)
    if result.failed:
        # One composer, never a chain here: the timeout branch used to
        # discard every captured channel, and the timeout branch is the
        # one a pre-script failure takes (INC-20260809-2230).
        error = result.diagnosis()
        return RunRecord(
            **base,
            status=RunStatus.FAILED_EXECUTION,
            wall_time_s=result.wall_time_s,
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
            **base,
            status=RunStatus.SUBMITTED,
            wall_time_s=None,
            outputs=[],
            # FR-99, 0.18.0. WHAT THE COLLECTOR WILL WAIT FOR, recorded at
            # the moment of submission. It is on the RECORD and not re-read
            # off the matrix later, because a matrix edited between the
            # submission and the collection is exactly the shape that made
            # a recorded flight condition read back as a different number
            # in a regenerated product (GEO-039-F02). `outputs` stays empty
            # because a submitted point has collected nothing; these are
            # what it was BUILT to write.
            submission={
                **submitted,
                "declared_outputs": list(point_case.outputs),
                # GOAL-021 item 3: WHERE the job runs and writes, relative to
                # the simulation folder so a moved workspace still resolves;
                # the collector waits on the declared outputs here.
                "working_dir": work_dir.relative_to(sim_dir).as_posix(),
                # G02: the points the script imports, which the collector
                # compares with the count the solver logs.
                **(
                    {"wake_edge_points": script.wake_edge_points}
                    if script.wake_edge_points is not None
                    else {}
                ),
                # G06: every file the point was told to write its log to,
                # whatever its name, the output its LOG_OUTPUT names among them;
                # the collector reads the four lines in each.
                "declared_logs": _declared_logs(point_case, rendered),
            },
        )

    # G45: THE TECPLOT IS WRITTEN FROM THE VTK before anything is collected, at
    # the name the solver's own had, and each per-step VTK into its own step's.
    if base.get("surface_translations"):
        base["surface_translations"] = translate_surface_exports(
            work_dir,
            base["surface_translations"],  # type: ignore[arg-type]
        )
    # 0.27.0: ON A MACHINE THAT CANNOT EXPORT THE LOG, the declared log is
    # written from what the solver printed, or, with nothing printed, excused:
    # the machine cannot write one locally, which is not an output the run
    # failed to produce. Nothing happens here on any other run.
    local_log = _the_local_log(executor, point_case.outputs, work_dir, result)
    # 0.30.0: what the package's own post-processing of an output could not
    # write, where the solver wrote its sources (`untranslated_surfaces`).
    post_warnings: list[str] = []
    try:
        collected = workspace.collect_outputs(
            case.sim_id,
            [work_dir / name for name in point_case.outputs if name != local_log.excused],
            # FR-92. THE POINT'S OWN FOLDER, always, steady or unsteady.
            # Every point of one case collected into one `outputs/` until
            # 0.16.0, so from the second point of a swept row onward that
            # folder held two files that both read as loads tables and
            # nothing in the layout said which point either belonged to.
            # The point's checked NAME is passed and the folder is rendered
            # there, so a caller cannot name a folder the assessor will not read.
            datapoint=PointName(point_name(case, point)),
            # 0.27.0: every point runs in that folder, so its outputs are
            # filed where the solver wrote them.
            ran_in_datapoint=True,
        )
        # 0.32.0 (E2): an acoustic section's files, listed where the solver wrote them.
        collected = acoustic_section_outputs(workspace.sim_dir(case.sim_id), collected)
    except MissingOutputsError as exc:
        exc.collected = acoustic_section_outputs(workspace.sim_dir(case.sim_id), exc.collected)
        # A COMPLETED SOLVE IS NOT DEMOTED BY THE PACKAGE'S OWN POST-PROCESSING
        # (0.30.0). A Tecplot the package failed to write from the VTK the
        # solver did write is not a missing solver output: the point is
        # assessed as any other and the failure is a warning on the record.
        untranslated = untranslated_surfaces(
            base.get("surface_translations"), exc.missing, exc.collected
        )
        if untranslated is None:
            # WHAT WAS WRITTEN IS FILED, LISTED AND HASHED, and the error names
            # only what is missing (0.27.0). An empty record here left a point's
            # exports out of every product (measured on a cluster, 2026-09-24).
            return RunRecord(
                **base,
                status=RunStatus.FAILED_INCOMPLETE_OUTPUT,
                wall_time_s=result.wall_time_s,
                outputs=exc.collected,
                outputs_sha256=workspace.output_digests(case.sim_id, exc.collected),
                residual_note=local_log.note,
                error=str(exc) + _translation_problems(base.get("surface_translations")),
            )
        collected = exc.collected
        post_warnings = untranslated
        for line in untranslated:
            warnings.warn(f"{point_name(case, point)}: {line}", PyflightstreamWarning, stacklevel=2)
    except (WorkspaceError, CampaignConfigError) as exc:
        # BOTH, because collection can refuse for two reasons and only one of
        # them used to be caught. `collect_outputs` renders the point's folder
        # name, so a point naming no known axis raises CampaignConfigError from
        # `point_tag`, and that is not a WorkspaceError: uncaught it would abort
        # the campaign HERE, after the solver has run, instead of costing this
        # point (the architecture lens, 2026-09-11). Unreachable through
        # `sweep.points()`, which yields only points keyed by a known axis, and
        # caught anyway: the thing this costs is a licensed seat.
        return RunRecord(
            **base,
            status=RunStatus.FAILED_INCOMPLETE_OUTPUT,
            wall_time_s=result.wall_time_s,
            error=str(exc),
        )

    assessment = assess(point_case, result, sim_dir)
    # FR-98. THE CLOCK'S VERDICT WINS, and only over a converged one.
    # A run the watchdog stopped did not converge and did not fail: it
    # ran out of clock with its outputs written, which is a state of
    # its own and the reason the value exists. A run that DIVERGED and
    # then hit the clock is still diverged, so a failure is left alone.
    status = (
        RunStatus.WALLTIME_REACHED
        if base.get("stopped_at") and not str(assessment.status).startswith("FAILED")
        else assessment.status
    )
    # G02. A run that imported trailing edges is held to the count the solver
    # logged, over any status that is not already a failure.
    # The log is found by the name the assessor read it under, else by the name
    # a local run on a machine that cannot export one wrote it under (0.27.0):
    # the solver's printed output need not read as a residual history to carry
    # the count.
    named_log = assessment.log_file_used or (
        Path(local_log.written).name if local_log.written else None
    )
    # On a machine that cannot export the log, what the solver printed is the
    # point's log when nothing else is, as it is a local steady job's: a row that
    # declares no log output wrote none from it above.
    printed = (
        result.captured_output()
        if isinstance(executor, LocalExecutor) and not executor.export_log
        else ""
    )
    log_text = _run_log_text(sim_dir, collected, named_log, result) or (printed or None)
    status, error = with_wake_edge_verdict(
        status,
        assessment.error,
        _no_local_log_verdict(script.wake_edge_points, log_text, local_log.note)
        if local_log.excused and local_log.note
        else wake_edge_import_verdict(script.wake_edge_points, log_text),
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
            result.log_text,
            printed,
            *collected_log_texts(sim_dir, collected, _declared_logs(point_case, rendered)),
        ),
    )
    step_warning = missing_step_warning(
        base.get("action_program"),
        base.get("action_count"),
        base.get("export_window"),
        assessment.time_steps,
    )
    # 0.31.0: what the judgment did without (an unreadable quasi-steady record).
    for line in assessment.warnings or []:
        warnings.warn(f"{point_name(case, point)}: {line}", PyflightstreamWarning, stacklevel=2)
    return RunRecord(
        **base,
        status=status,
        warnings=[
            *post_warnings,
            *(assessment.warnings or []),
            *([step_warning] if step_warning else []),
        ],
        iterations=assessment.iterations,
        residual=assessment.residual,
        fs_version_reported=assessment.fs_version_reported,
        fs_build=assessment.fs_build,
        wall_time_s=result.wall_time_s,
        outputs=collected,
        # PYFS-006, the other half of "which file is this record about".
        # The refusal above stops a stale file becoming evidence; this
        # states which bytes the evidence WAS, so a file edited or
        # replaced after the run stops matching its own record. inputs
        # have carried this since the first manifest; outputs never did.
        outputs_sha256=workspace.output_digests(case.sim_id, collected),
        # REV010-001. The decision is persisted, not just acted on: a later
        # reader of the manifest can see which axes were compared, by how
        # much the export deviated, and what tolerance let it through. A
        # status alone cannot answer "was this result ever bound to the
        # point it claims", and that question is the whole finding.
        conditions=assessment.conditions,
        log_file_used=assessment.log_file_used,
        residual_note="; ".join(note for note in (assessment.residual_note, local_log.note) if note)
        or None,
        solver_run_time_s=assessment.solver_run_time_s,
        solver_initialization_s=assessment.solver_initialization_s,
        time_steps=assessment.time_steps,
        clocking_verdicts=assessment.clocking_verdicts,
        error=error,
    )
