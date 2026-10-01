"""What a continuation may continue, and the evidence checks of a stopped run.

Two halves, both read by the run layer before a ``RESTART`` row is built.
:func:`continuation_verdict` says, per point, whether its latest record may be
continued and what the plan and the run say about it (FR-96, amended in
0.33.0: a CONVERGED unsteady march may be continued by ``ADDITIONAL_REVS`` or
``ADDITIONAL_ITERS``, once per request). :func:`recover_frame` proves the
original setup of a stopped run whose manifest predates frame placement.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import NoReturn

from pyflightstream._console import wrap
from pyflightstream._digest import file_sha256
from pyflightstream.cases import (
    CampaignConfigError,
    ScriptRecipe,
    SimCase,
    case_at_point,
    point_name,
)
from pyflightstream.cases.workflows import (
    RESERVED_CONTINUATION_VARIABLES,
    RESTART_ADDITIONAL_ITERS,
    RESTART_ADDITIONAL_REVS,
    RESTART_FINISH_PENDING,
    RESTART_VARIABLE,
    UNSTEADY_COUNTER_ACTION,
    RestartRequest,
    parse_restart,
    restart_iterations,
)
from pyflightstream.script import Script
from pyflightstream.workspace import CampaignWorkspace, RunRecord, RunStatus

#: The statuses a continuation continues FROM whatever the run type: these two
#: stopped with their outputs written and more to march, the wall clock or the
#: iteration cap having ended them. A CONVERGED record of an unsteady march is
#: continued too, but only by ``ADDITIONAL_REVS`` or ``ADDITIONAL_ITERS`` and
#: once per request (:func:`continuation_verdict`); a failed run has no state
#: worth resuming.
CONTINUABLE = (RunStatus.WALLTIME_REACHED, RunStatus.COMPLETED_MAX_ITER)

#: Every status a run ends in when it FAILED, read off the enum by name so a
#: failure status added there is covered here without an edit.
FAILED_STATUSES = tuple(status for status in RunStatus if status.name.startswith("FAILED_"))

#: The run types that march in time, whose CONVERGED is the residual test at the
#: last step and not the end of what an average needs.
MARCHING_RUN_TYPES = ("unsteady", "unsteady_rotor")

#: The statuses of a run that reached every step it was given.
_COMPLETED = (RunStatus.CONVERGED, RunStatus.COMPLETED_MAX_ITER)

#: The step counter's registration, which every unsteady row carries since 0.33.0
#: (FR-314) and which counts and places nothing.
_COUNTER_HEAD = f"SET_NEW_UNSTEADY_SOLVER_ACTION COMMAND_LINE {UNSTEADY_COUNTER_ACTION}"


def _refuse(record: RunRecord, reason: str) -> NoReturn:
    raise CampaignConfigError(
        f"run {record.run_id!r} recorded no placement of its analysis loads frame; "
        f"offline recovery cannot prove the same stopped row: {reason}. "
        "Nothing was archived or launched. Restore the original row and evidence, "
        "or set tecplot = false to continue without a surface Tecplot export."
    )


def _verified_file(record: RunRecord, path: Path, digest: str | None, label: str) -> None:
    if not digest or not path.is_file():
        _refuse(record, f"{label} is missing or has no recorded SHA256")
    if file_sha256(path) != digest:
        _refuse(record, f"{label} changed since the stopped run")


def _native_setup(text: str, script: Script) -> tuple[str, ...]:
    """Compare native setup, excluding output serialization and comments.

    0.27 wrote Tecplot natively; current releases translate VTK. Exports
    select no loads frame, and neither does the step counter 0.33.0 registers
    on every unsteady row (FR-314). Scientific commands and their order stay
    compared.
    """
    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    kept: list[str] = []
    at = 0
    while at < len(lines):
        line = lines[at]
        # FR-314: a row recorded by 0.32.0 without the counter is the same setup.
        if line == _COUNTER_HEAD and at + 1 < len(lines):
            at += 2
            continue
        if line == "SET_VTK_EXPORT_VARIABLES -1 DISABLE":
            at += 1
            continue
        if line in {
            "EXPORT_SOLVER_ANALYSIS_TECPLOT",
            "EXPORT_SOLVER_ANALYSIS_VTK",
        } and at + 1 < len(lines):
            filename = lines[at + 1]
            suffix = ".dat" if line.endswith("TECPLOT") else ".vtk"
            # Only the documented surface serialization difference is ignored.
            # Unknown commands and unproved grammars remain in the comparison.
            if filename.split()[0] not in script.registry.commands and filename.strip(
                '"'
            ).lower().endswith(suffix):
                if line.endswith("TECPLOT"):
                    at += 2
                    continue
                if at + 2 < len(lines) and lines[at + 2] == "SURFACES -1":
                    at += 3
                    continue
        kept.append(line)
        at += 1
    return tuple(kept)


def _input_hashes(record: RunRecord, case: SimCase, script: Script) -> dict[str, str]:
    current: dict[str, str] = {}
    for name in (case.geometry, case.freestream_profile):
        if name is not None:
            path = Path(name)
            _verified_file(
                record, path, record.inputs_sha256.get(path.name), f"input {path.name!r}"
            )
            current[path.name] = file_sha256(path)
    if case.fsi is not None or script.pending_action_scripts:
        _refuse(record, "the historical record cannot verify FSI or child-script dependencies")
    for name, content in script.pending_input_files.items():
        key = Path(name).name
        data = content if isinstance(content, bytes) else content.encode("utf-8")
        candidates = {hashlib.sha256(data).hexdigest()}
        if isinstance(content, str):
            candidates.add(hashlib.sha256(data.replace(b"\n", b"\r\n")).hexdigest())
        expected = record.inputs_sha256.get(key)
        if expected not in candidates:
            _refuse(record, f"generated input {key!r} changed or has no recorded SHA256")
        if key in current and current[key] != expected:
            _refuse(record, f"input identity {key!r} is ambiguous")
        current[key] = str(expected)
    if current != record.inputs_sha256:
        _refuse(record, "the set of native input identities changed or cannot be reconstructed")
    return current


def _rebuild(
    workspace: CampaignWorkspace,
    case: SimCase,
    point: Mapping[str, float],
    record: RunRecord,
    recipe: ScriptRecipe,
    version: str,
) -> Script:
    from pyflightstream.workspace import PointName, datapoint_dir_name

    variables = {
        k: v
        for k, v in case.variables.items()
        if k not in (RESTART_VARIABLE, *RESERVED_CONTINUATION_VARIABLES)
    }
    updates: dict[str, object] = {"variables": variables}
    if case.geometry is not None:
        staged = workspace.sim_dir(case.sim_id) / "inputs" / Path(case.geometry).name
        _verified_file(
            record,
            staged,
            record.inputs_sha256.get(staged.name),
            f"staged geometry {staged.name!r}",
        )
        updates["geometry"] = str(staged)
    shadow_case = case_at_point(case, dict(point), **updates)
    shadow = Script(version)
    work = (
        workspace.sim_dir(case.sim_id)
        / "datapoints"
        / datapoint_dir_name(PointName(point_name(case, point)))
    )
    shadow.working_dir = str(work)
    try:
        recipe(shadow_case, shadow)
        shadow.render()
    except Exception as error:
        _refuse(record, f"the original row cannot be rebuilt: {type(error).__name__}: {error}")
    return shadow


def recover_frame(
    workspace: CampaignWorkspace,
    case: SimCase,
    point: Mapping[str, float],
    record: RunRecord,
    saved: str,
    recipe: ScriptRecipe,
    version: str,
) -> dict[str, object]:
    """Recover a frame only after proving the original native setup and inputs."""
    from itertools import zip_longest

    from pyflightstream.versions import resolve

    if record.continues:
        _refuse(record, "an unplaced restart chain does not retain a proven original setup")
    if record.point != dict(point) or record.recipe != case.recipe:
        _refuse(record, "the point or recipe identity changed or was not recorded")
    if resolve(record.fs_version_requested).canonical != resolve(version).canonical:
        _refuse(record, "the requested FlightStream version changed")
    sim = workspace.sim_dir(case.sim_id)
    if not record.script_path:
        _refuse(record, "original script path is missing; no SHA256 evidence can be checked")
    original = sim / record.script_path
    _verified_file(record, original, record.script_sha256, "original script")
    saved_digest = record.outputs_sha256.get(saved)
    _verified_file(record, sim / saved, saved_digest, "saved simulation")
    shadow = _rebuild(workspace, case, point, record, recipe, version)
    inputs = _input_hashes(record, case, shadow)
    try:
        was = _native_setup(original.read_text(encoding="utf-8"), shadow)
        rebuilt = shadow.render()
        now = _native_setup(rebuilt, shadow)
    except (OSError, UnicodeError, ValueError) as error:
        _refuse(record, f"native setup evidence cannot be read: {error}")
    if was != now:
        before, after = next((a, b) for a, b in zip_longest(was, now) if a != b)
        _refuse(record, f"native setup changed: recorded {before!r}; rebuilt {after!r}")
    frame = shadow.loads_frame_record()
    if not shadow.sets_loads_frame or frame.get("origin") is None or frame.get("axes") is None:
        _refuse(record, "the rebuilt analysis loads-frame placement is ambiguous")
    return {
        "recovered_frame": frame,
        "frame_recovery": {
            "method": "offline_native_setup_and_input_comparison",
            "source_run_id": record.run_id,
            "script_sha256": record.script_sha256,
            "inputs_sha256": inputs,
            "saved_simulation_sha256": saved_digest,
            "reconstructed_text_sha256": hashlib.sha256(rebuilt.encode("utf-8")).hexdigest(),
        },
    }


# --- what a RESTART row continues (FR-96; a CONVERGED march since 0.33.0) -------


@dataclass(frozen=True)
class ContinuationVerdict:
    """Whether one point of a ``RESTART`` row goes on to be continued, and what is said.

    Attributes
    ----------
    pending : bool
        True when the point goes on to the continuation resolver, which either
        continues it or refuses it by name (a point nothing records, or whose
        latest run failed). False when it is not run, and ``said`` says why.
    said : str or None
        The sentence the plan and the run state for the point: what the
        continuation does, or why the request cannot continue it. None where
        the resolver's own refusal is what is said.
    """

    pending: bool
    said: str | None


def restart_request(case: SimCase) -> RestartRequest | None:
    """Return the row's ``RESTART`` request, or None where it states none or a malformed one.

    A malformed cell is the continuation resolver's to refuse, per point and by
    name; scheduling only needs to know whether the row is one.
    """
    try:
        return parse_restart(case)
    except CampaignConfigError:
        return None


def request_record(request: RestartRequest) -> dict[str, object]:
    """Return what a continuation's record states of the request it answered."""
    return {"form": request.form, "value": request.value}


def _asked(request: RestartRequest) -> str:
    if request.value is None:
        return request.form
    return f"{request.form}={request.value:g}"


def _by(request: RestartRequest) -> str:
    if request.form == RESTART_FINISH_PENDING:
        return "by the steps the row still owes"
    unit = "revolution(s)" if request.form == RESTART_ADDITIONAL_REVS else "time step(s)"
    return f"by {request.value:g} {unit}"


#: How a continuation recorded before 0.33.0, which states no request, is asked
#: whether it answered one: :func:`recorded_requests` builds it from a workspace.
Unstated = Callable[[RunRecord, RestartRequest], bool]


def _answered(request: RestartRequest, latest: RunRecord, unstated: Unstated | None) -> bool:
    """Whether the latest record is a completed continuation of this same request.

    A continuation recorded before 0.33.0 states no request. It answered this
    one when it marched the steps this request asks of the run it continues
    (``unstated``, :func:`recorded_requests`), and where that cannot be read it
    is taken to answer it, so running an existing matrix again never adds
    revolutions to a point while a changed request continues it.
    """
    if latest.continues is None or latest.status not in _COMPLETED:
        return False
    stated = latest.restart
    if stated is None:
        return unstated(latest, request) if unstated is not None else True
    return stated.get("form") == request.form and stated.get("value") == request.value


def _marched_steps(sim_dir: Path, record: RunRecord) -> int | None:
    """Return the time steps a run's script marched (``SET_SOLVER_UNSTEADY``), or None."""
    try:
        lines = (sim_dir / str(record.script_path)).read_text(encoding="utf-8").splitlines()
    except (OSError, TypeError):
        return None
    for at, line in enumerate(lines[:-1]):
        words = lines[at + 1].split()
        if line.strip() == "SET_SOLVER_UNSTEADY" and words[:1] == ["TIME_ITERATIONS"]:
            return int(words[1]) if len(words) == 2 and words[1].isdigit() else None
    return None


def recorded_requests(workspace: CampaignWorkspace, records: Iterable[RunRecord]) -> Unstated:
    """Return whether a continuation recorded before 0.33.0 answered a request (FR-96).

    Such a record states no request, so it is read off what it did: it
    answered the request whose steps, asked of the run it continues, are the
    steps its script marched. The same request is then not continued twice and
    a changed one (another number, or a key that marches another count) is. A
    record whose script or predecessor cannot be read is taken to answer it.
    """
    by_id = {record.run_id: record for record in records}

    def answered(latest: RunRecord, request: RestartRequest) -> bool:
        earlier = by_id.get(str(latest.continues))
        marched = _marched_steps(workspace.sim_dir(latest.sim_id), latest)
        if earlier is None or marched is None:
            return True
        try:
            return restart_steps(request, earlier) == marched
        except CampaignConfigError:
            return True

    return answered


def continuation_verdict(
    request: RestartRequest, latest: RunRecord | None, unstated: Unstated | None = None
) -> ContinuationVerdict:
    """Judge one point of a ``RESTART`` row by its latest record (FR-96).

    A run the wall clock stopped, and one recorded at its iteration cap, are
    continued as they always were. A CONVERGED run of an unsteady run type is
    continued by ``ADDITIONAL_REVS`` or ``ADDITIONAL_ITERS``, because for a
    march CONVERGED is the residual test at its last step and an average may
    need more revolutions; ``FINISH_PENDING`` has nothing to finish there. A
    completed continuation of the same request is not continued again, so
    running the matrix again never re-marches what a continuation added; a
    different request continues it. A point nothing records, or whose latest
    run failed, goes on to the resolver, which refuses it by name. Every point
    that is not run is said, never passed over.
    """
    if latest is None or latest.status in FAILED_STATUSES:
        return ContinuationVerdict(True, None)
    run, status = latest.run_id, latest.status.value
    if latest.status is RunStatus.SUBMITTED:
        return ContinuationVerdict(
            False,
            f"not continued yet: its latest run, {run!r}, is SUBMITTED and still in a "
            "scheduler's queue; collect it (pyfs-matrix collect) and plan again",
        )
    if latest.status is RunStatus.WALLTIME_REACHED:
        return ContinuationVerdict(
            True, f"continuing {run!r}, stopped by its wall clock, {_by(request)}"
        )
    if request.form == RESTART_FINISH_PENDING:
        if latest.status is RunStatus.CONVERGED:
            return ContinuationVerdict(
                False,
                f"nothing is pending: its latest run, {run!r}, CONVERGED, and "
                f"{RESTART_FINISH_PENDING} finishes only a run its wall clock stopped. To march "
                f"a converged unsteady run further, write {RESTART_VARIABLE}: "
                f"{{{RESTART_ADDITIONAL_REVS}=n}} or {{{RESTART_ADDITIONAL_ITERS}=n}}",
            )
        return ContinuationVerdict(True, None)
    if _answered(request, latest, unstated):
        before = (
            ""
            if latest.restart
            else " (recorded before 0.33.0, it states no request and marched what this one asks)"
        )
        return ContinuationVerdict(
            False,
            f"already continued by {_asked(request)}: its latest run, {run!r}, continues "
            f"{latest.continues!r} and ended {status}{before}; change the request to march "
            "further",
        )
    if latest.status is RunStatus.COMPLETED_MAX_ITER:
        return ContinuationVerdict(True, f"continuing {run!r}, recorded {status}, {_by(request)}")
    if latest.recipe in MARCHING_RUN_TYPES:
        return ContinuationVerdict(
            True, f"continuing a CONVERGED unsteady run, {run!r}, {_by(request)}"
        )
    return ContinuationVerdict(
        False,
        f"nothing to march: its latest run, {run!r}, is a {latest.recipe or 'steady'} run "
        f"recorded {status}, and {RESTART_VARIABLE} continues an unsteady march",
    )


def refuse_what_cannot_continue(
    workspace: CampaignWorkspace, sim_id: str, tag: str, request: RestartRequest
) -> RunRecord:
    """Return the record a point's ``RESTART`` request continues, or raise why it cannot.

    The point's MOST RECENT record, whatever it says, is the one asked: this read
    the latest STOPPED record until 0.18.1, so a point whose continuation had
    since finished was continued again from the run before it (GOAL-021).
    """
    records = workspace.read_manifest()
    previous = latest_record_of_point(records, sim_id, tag)
    verdict = continuation_verdict(request, previous, recorded_requests(workspace, records))
    if previous is not None and previous.status not in FAILED_STATUSES:
        if verdict.pending:
            return previous
        raise CampaignConfigError(
            f"case {sim_id!r} point {tag} states {RESTART_VARIABLE}: {verdict.said}."
        )
    latest = (
        "records no run of it"
        if previous is None
        else f"records its latest run, {previous.run_id!r}, as {previous.status}"
    )
    remedy = (
        " A failed continuation is not retried: the saved simulation of the stop it "
        "continued is kept under this point's archive/ folder. Find why it failed, "
        "then restore that file and its record by hand, or remove the "
        f"{RESTART_VARIABLE} key to march the point from the start."
        if previous is not None
        else ""
    )
    raise CampaignConfigError(
        f"case {sim_id!r} point {tag} states {RESTART_VARIABLE} and this workspace "
        f"{latest}, which is not a run that STOPPED with more to do.{remedy} A continuation "
        "continues a recorded run whose latest status is one of "
        f"{', '.join(str(s) for s in CONTINUABLE)}, or a CONVERGED unsteady run asked for "
        f"{RESTART_ADDITIONAL_REVS} or {RESTART_ADDITIONAL_ITERS}; run the row once, or "
        f"remove the {RESTART_VARIABLE} key to march it from the start."
    )


def restart_steps(request: RestartRequest, previous: RunRecord) -> int:
    """Return the time steps a continuation marches, from the record it continues.

    :func:`~pyflightstream.cases.workflows.restart_iterations` is the arithmetic.
    ``ADDITIONAL_REVS`` reads the azimuthal step of the record's export window;
    a rotor run that exported nothing per step records none, and its own clock,
    the steps per revolution of its reductions plan, gives the same number.
    """
    record = previous.model_dump(mode="json")
    window = record.get("export_window") or {}
    plan = record.get("reductions") or {}
    per_revolution = plan.get("steps_per_revolution")
    if not window.get("step_deg") and isinstance(per_revolution, int | float) and per_revolution:
        record["export_window"] = {**window, "step_deg": 360.0 / float(per_revolution)}
    return restart_iterations(request, record)


def latest_record_of_point(
    records: Iterable[RunRecord], sim_id: str, name: str
) -> RunRecord | None:
    """Return the most recent record of one point, in file order, whatever its status.

    A continuation's run id is ``<campaign>/sim_<id>/r<stamp>/<name>``, so the
    point name still ENDS every run id of the point, which is what this reads.
    """
    latest = None
    for record in records:
        if _is_a_continuation_that_never_started(record):
            continue
        if record.sim_id == sim_id and record.run_id.endswith(f"/{name}"):
            latest = record
    return latest


def _is_a_continuation_that_never_started(record: RunRecord) -> bool:
    """Whether a record is `run_campaign`'s note that a continuation was refused.

    Such a row says an attempt was made and why it could not start; it built no
    script, archived nothing and touched no folder, so it is NOT the state of the
    point and the run before it still is. Read as the latest run it would turn a
    refusal whose remedy is "restore the saved simulation" into one that can
    never be lifted, because the next attempt would find a FAILED run and be
    told that a failed continuation is not retried.

    It is told apart by what it lacks: every record `_execute_point` builds
    names its recipe, including the four that fail before a script exists, and
    this one reached no recipe.
    """
    return (
        record.status is RunStatus.FAILED_SCRIPT
        and not record.script_sha256
        and record.recipe is None
    )


def point_verdict(
    workspace: CampaignWorkspace, case: SimCase, point: Mapping[str, float]
) -> ContinuationVerdict | None:
    """Judge one point of a row by its latest record, or None where the row states no RESTART."""
    request = restart_request(case)
    if request is None:
        return None
    records = workspace.read_manifest()
    latest = latest_record_of_point(records, case.sim_id, point_name(case, point))
    return continuation_verdict(request, latest, recorded_requests(workspace, records))


def pending_restart_points(
    case: SimCase,
    points: Sequence[tuple[dict[str, float], str]],
    workspace: CampaignWorkspace,
    say: Callable[[str], None],
) -> list[tuple[dict[str, float], str]]:
    """Return the points of a ``RESTART`` row the run goes on with, saying every other one.

    A point is run when :func:`continuation_verdict` finds it pending; a point
    that is not is named with the reason, so a run never passes one over in
    silence (FR-96).
    """
    pending = []
    for point, run_id in points:
        verdict = point_verdict(workspace, case, point) or ContinuationVerdict(True, None)
        if verdict.pending:
            pending.append((point, run_id))
        else:
            say(f"  -> {run_id}  not run: {RESTART_VARIABLE}: {verdict.said}")
    return pending


def continuation_block(points: Iterable[object]) -> list[str]:
    """Return the plan's block of what ``RESTART`` does on each point that states it."""
    lines = []
    for entry in points:
        said = getattr(entry, "continuation", None)
        if said:
            lines += [f"  {getattr(entry, 'run_id', '')}", *wrap(str(said), first="    ")]
    return lines
