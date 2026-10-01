"""Continuing a stopped run: the run id, the frame, and the refusals.

Private to :mod:`pyflightstream.run`. :func:`resolve_continuation` turns a
continuation request of a row into the case that resumes the recorded run,
refusing what cannot continue; the helpers beside it read the queued and
the recorded loads frames and refuse an import count no log can confirm.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from datetime import datetime
from pathlib import Path
from typing import cast

from pyflightstream._digest import (
    file_sha256,
)
from pyflightstream._progress import (
    workspace_activity,
)
from pyflightstream.cases import (
    CampaignConfigError,
    ScriptRecipe,
    SimCase,
    classify_outputs,
    point_name,
    resolve_recipe,
)
from pyflightstream.cases.workflows import (
    EXPORT_LOG_VARIABLE,
    FREESTREAM_VARIABLE,
    RESTART_VARIABLE,
    SIMULATION_SUFFIX,
    WorkflowConventions,
    parse_restart,
    read_a_choice,
)
from pyflightstream.run._continuation_frame import (
    recover_frame as _recover_continuation_frame,
)
from pyflightstream.run._continuation_frame import (
    refuse_what_cannot_continue,
    request_record,
    restart_steps,
)
from pyflightstream.run._executors import (
    _machine_exports_log,
)
from pyflightstream.run._ids import (
    _unplaced,
)
from pyflightstream.script import Script
from pyflightstream.workspace import (
    CampaignWorkspace,
    RunRecord,
    RunStatus,
)
from pyflightstream.workspace.naming import (
    ARCHIVE_STAMP,
)
from pyflightstream.workspace.storage import ensure_sim_expanded


def _recorded_loads_frame(record: RunRecord | None) -> dict[str, object] | None:
    """Return the placed loads frame a run recorded for its Tecplot surfaces, or None (G45)."""
    for translation in (record.surface_translations if record is not None else None) or []:
        frame = translation.get("frame")
        if isinstance(frame, Mapping) and not _unplaced(translation):
            return dict(frame)
    return None


def workflow_conventions_for(case: SimCase) -> WorkflowConventions:
    """Return the conventions a builder would have been given for this case.

    The run layer owns these and the clock program needs the same ones the
    export block used, so it asks the same constructor rather than
    rebuilding the names.
    """
    return WorkflowConventions.for_case(case)


def continuation_run_id(run_id: str, stamp: datetime) -> str:
    """Return the run id of a continuation of ``run_id``.

    THE STAMP GOES BEFORE THE POINT TAG AND NOT AFTER IT, and that is the
    continuation policy. FR-95 states that
    the point tag is run IDENTITY and ENDS every ``run_id`` in every
    manifest; a stamp appended after it would break that for every reader
    and every resume that walks a manifest by its tags.

    So a continuation is ``<campaign>/sim_<id>/r<stamp>/<tag>``: a row of
    its own in the manifest, discriminated by the SAME stamp that names the
    folder its predecessor's outputs were archived into, and the tag still
    ends it.

    ONE RECORD PER CONTINUATION: the evidence of each continuation lives
    in its own stamped folder. The stamp is already the thing that tells one
    from the next, and a record per continuation costs no new vocabulary.
    The alternative, one record growing segments, would have meant rewriting
    a finished row, which is the thing `append_record` exists to prevent.
    """
    head, _, tag = run_id.rpartition("/")
    return f"{head}/r{stamp.strftime(ARCHIVE_STAMP)}/{tag}"


def _unused_continuation_run_id(run_id: str, stamp: datetime, recorded: Collection[str]) -> str:
    """Return :func:`continuation_run_id`, numbered when the manifest holds that id.

    The stamp resolves one second, and two rows of one point can fall inside it:
    a refusal recorded and the attempt after its cause was fixed, or two
    continuations that each stopped at once. The manifest refuses a second row
    under one id, after the predecessor's outputs have already been archived, so
    the id is numbered the way the archive numbers a folder that exists. The
    point tag still ends it.
    """
    candidate = continuation_run_id(run_id, stamp)
    if candidate not in recorded:
        return candidate
    head, _, tag = candidate.rpartition("/")
    index = 2
    while f"{head}.{index}/{tag}" in recorded:
        index += 1
    return f"{head}.{index}/{tag}"


@workspace_activity("continuation", verbose_only=True)
def resolve_continuation(
    workspace: CampaignWorkspace,
    case: SimCase,
    point: Mapping[str, float],
    *,
    run_id: str,
    recipe: ScriptRecipe | None = None,
    fs_version: str | None = None,
) -> dict[str, object] | None:
    """Resolve the two facts a continuation needs, from the record it continues.

    None where the row states no ``RESTART``, which is every ordinary row.

    THE ROW SAYS HOW MUCH MORE AND THE MANIFEST SAYS FROM WHAT. Which run
    stopped, where it stopped, and which saved simulation it left are all
    answers the record holds; the builder is a pure function of its case and
    must not go looking for them, so they are resolved here and set on the
    point case as two reserved variables.
    """
    request = parse_restart(case)
    if request is None:
        return None
    tag = point_name(case, point)
    # FR-96, 0.33.0: a CONVERGED unsteady march is continued by ADDITIONAL_REVS
    # or ADDITIONAL_ITERS, once per request; everything else as before.
    previous = refuse_what_cannot_continue(workspace, case.sim_id, tag, request)
    iterations = restart_steps(request, previous)
    saved = next(
        (name for name in previous.outputs if str(name).lower().endswith(SIMULATION_SUFFIX)),
        None,
    )
    if saved is None:
        raise CampaignConfigError(
            f"run {previous.run_id!r} stopped at {previous.status} and collected no saved "
            f"simulation ({SIMULATION_SUFFIX}), so there is no state to reopen. A run recorded "
            "before 0.27.0 under a post-processing artifact that turned the simulation export "
            "off cannot be continued: since 0.27.0 every point of a row naming a run type saves "
            "it and no artifact can turn it off, so run the row again."
        )
    ensure_sim_expanded(workspace, case.sim_id, reason="continuation")
    if not (workspace.sim_dir(case.sim_id) / str(saved)).is_file():
        raise CampaignConfigError(
            f"run {previous.run_id!r} stopped at {previous.status} and recorded its saved "
            f"simulation as {saved}, which is not in {workspace.sim_dir(case.sim_id)}. A "
            "continuation reopens that file, so it cannot start without it; restore it, or "
            f"remove the {RESTART_VARIABLE} key to march the point from the start."
        )
    _refuse_a_field_the_stopped_run_did_not_read(case, tag, previous)
    recovery: dict[str, object] = {}
    if (
        "tecplot" in classify_outputs([str(name) for name in case.outputs])
        and _recorded_loads_frame(previous) is None
    ):
        try:
            # `resolve_recipe` returns the imported function as a plain Callable; it is a
            # ScriptRecipe, whose named parameters a Callable type cannot state.
            original_recipe = recipe or cast(ScriptRecipe, resolve_recipe(case.recipe))
        except ValueError as error:
            raise CampaignConfigError(f"cannot rebuild the original row: {error}") from error
        recovery = _recover_continuation_frame(
            workspace,
            case,
            point,
            previous,
            str(saved),
            original_recipe,
            fs_version or case.fs_build or previous.fs_version_requested,
        )
    return {
        "continues": previous.run_id,
        "iterations": iterations,
        "saved": str(saved),
        "form": request.form,
        "restart": request_record(request),
        **recovery,
    }


def _refuse_a_field_the_stopped_run_did_not_read(
    case: SimCase, tag: str, previous: RunRecord
) -> None:
    """Refuse a custom free stream the run being continued did not solve in (G15).

    A CONTINUATION WRITES NO FREE STREAM: it reopens the saved simulation,
    which carries the one the stopped run solved in, and marches on in it. So
    the field a continuing row names must be the one that run read, the file
    its record hashes under the same name to the same digest. Any other field,
    a key added to a row that stopped under the CONSTANT free stream or a file
    edited since the stop, would be hashed into the new record and never
    solved. A file no longer there is the builder's to refuse, by name.
    """
    if case.freestream_profile is None:
        return
    field = Path(case.freestream_profile)
    if not field.is_file():
        return
    recorded = previous.inputs_sha256.get(field.name)
    current = file_sha256(field)
    declaration = case.variables.get("FREESTREAM_UNITS") or case.freestream_units
    if declaration != previous.freestream_units:
        raise CampaignConfigError(
            "The continued custom field changed its FREESTREAM_UNITS declaration; "
            "start a new run rather than reinterpret the saved field."
        )
    if recorded == current:
        return
    stated = case.variables.get(FREESTREAM_VARIABLE)
    named = (
        f"{FREESTREAM_VARIABLE}: {stated}"
        if stated is not None
        else f"the custom free stream {field}"
    )
    if recorded is None:
        what = f"its record hashes no {field.name}, so it solved in another free stream"
        remedy = f"without {FREESTREAM_VARIABLE}"
    else:
        what = (
            f"it read {field.name} with other bytes than the file holds now (sha256 "
            f"{recorded[:12]}... then, {current[:12]}... now)"
        )
        remedy = "with the file restored to the bytes it read"
    raise CampaignConfigError(
        f"case {case.sim_id!r} point {tag} states {named} and {RESTART_VARIABLE}, and the run "
        f"it continues, {previous.run_id!r}, did not solve in that field: {what}. A "
        "continuation reopens the saved simulation and writes no free stream, so it would "
        "march on in the stopped run's and record this field as read. Remove the "
        f"{RESTART_VARIABLE} key to march the point from the start in the field, or continue "
        f"it {remedy}."
    )


def _queued_record_of_point(
    workspace: CampaignWorkspace, sim_id: str, name: str
) -> RunRecord | None:
    """Return a SUBMITTED record of this simulation and point, or None.

    Asked for EVERY executor: since 0.27.0 a local point runs in the same
    datapoint folder a submitted one does, so a local run meets a queued job
    of another campaign that names the same simulation and point.
    """
    for record in workspace.read_manifest():
        if (
            record.sim_id == sim_id
            and record.run_id.endswith(f"/{name}")
            and record.status is RunStatus.SUBMITTED
        ):
            return record
    return None


def _refuse_an_import_count_nothing_logs(
    case: SimCase, script: Script, executor: object | None
) -> None:
    """Refuse a script that imports trailing edges after its log export was turned off.

    G02. The run holds a trailing-edge import to the count the solver logs as
    imported, because a point that matches no edge marks nothing and the
    solver says nothing about it; the solver writes a log of its own only when
    it ends abnormally, so the count is read from the log the script exports.
    The builder refuses a file-route row whose outputs name no log, but it
    reads the NAMES, and ``EXPORT_LOG: false`` then leaves the named log with
    nothing to write it: the point built, ran, and was recorded
    FAILED_INCOMPLETE_OUTPUT after the seat (the qa lens, 2026-09-24).

    So this reads the script as built, after every switch: a case that states
    the switch false and a script that carries no ``EXPORT_LOG`` is refused,
    at plan (``executor`` None) and before the solver starts. The one
    exception is a machine whose HPC profile turns the export off itself
    (``export_log = false``, which a profile states only beside a
    ``native_log``): its scheduler writes the log, `collect` copies it to the
    declared name and the count is read from it there. The plan does not know
    the machine, so it refuses the switch in the row, where it is never needed:
    a machine that writes its own log says so in its profile.

    RUN LOCALLY ON SUCH A MACHINE (``--local``, 0.27.0) the point runs too: the
    declared log is written from what the solver printed and the count read
    from it, and a solver that printed nothing leaves the point recorded
    FAILED_INCOMPLETE_OUTPUT naming the machine, never accepted in silence.
    """
    if script.wake_edge_points is None:
        return
    stated = case.variables.get(EXPORT_LOG_VARIABLE)
    try:
        if stated is None or read_a_choice(stated, context=EXPORT_LOG_VARIABLE):
            return
    except ValueError:
        return  # a word the builder reads, and refuses there by name
    if "EXPORT_LOG" in script.render().splitlines():
        return
    if not _machine_exports_log(executor):
        return
    raise CampaignConfigError(
        f"case {case.sim_id!r} imports {script.wake_edge_points} trailing-edge points from "
        f"a file and states {EXPORT_LOG_VARIABLE}: {stated}, so its script exports no "
        "solver log and the log it declares has nothing to write it. The run compares the "
        "count of trailing edges the solver logs as imported with the points it wrote, "
        "because a point that matches no edge marks nothing and the solver says nothing "
        "about it; without the log the count cannot be read and the point would be "
        f"recorded FAILED_INCOMPLETE_OUTPUT after the solve. Take {EXPORT_LOG_VARIABLE} "
        "out of the row. A machine that aborts at EXPORT_LOG says so in its HPC profile "
        "([log] export_log = false, with native_log naming the log its scheduler writes), "
        "and the count is then read from that log."
    )
