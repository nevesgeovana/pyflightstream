"""Collect a submitted job's outputs when they land, then post (FR-99).

THIS IS COLLECT-AND-POST, not submit-and-collect. A watcher stands by, sees
that the file is not there yet, waits until it is, and only then generates the
post-processing.

WHY IT WATCHES FILES AND NOT THE SCHEDULER: it DECOUPLES THE STAGE FROM THE
QUEUE. A watcher that watches FILES needs no status command in the submission
profile, no job-script template and no second scheduler vocabulary, and the
same stage then serves a cluster job, a local run somebody interrupted, and
outputs a colleague dropped in by hand. The collector is a client of the
WORKSPACE, which is the thing this package actually owns, rather than of a
queue, which it does not.

THE HAZARD THAT DESIGN INHERITS, and it is not hypothetical: A FILE EXISTS
BEFORE IT IS FINISHED. The solver opens each export and writes into it, so
"the file appeared" is not "the file is complete", and a watcher that fired on
appearance alone would post-process a half-written loads table and report
numbers for it. That is the same class as every other silent wrong number this
package has paid for.

SO THE CONDITION IS PRESENCE **AND** SETTLED, and settled is asserted by two
signals that fail differently:

1. SIZE AND MODIFICATION TIME STABLE across two observations separated by the
   poll interval. This costs nothing and catches a file still being written.
   It is a heuristic with a timer on it: a solver that pauses for longer than
   the interval between two writes to one file looks finished for one poll.
2b. OR THE SCHEDULER'S OWN LOG HAS BEEN COPIED TO THE DECLARED NAME, which
    is what happens on a machine whose HPC profile states ``export_log =
    false`` and names a ``native_log`` (0.21.0). There `EXPORT_LOG` is not
    emitted at all, so the argument below does not hold: the copy is made
    BEFORE the settle condition is evaluated, and what settles is the copy.

2. THE LAST DECLARED OUTPUT IS PRESENT. This is the stronger statement,
   because the emitted script's own order ends with the log: `EXPORT_LOG` and
   `CLOSE_FLIGHTSTREAM` are the last two commands every workflow emits, so a
   log that exists and has settled means the solver closed the file and left.

Neither is a scheduler query, so neither costs a profile key, which is the
whole advantage of this architecture. Both are required, because a run that
never wrote its log and a run still writing its loads table are different
failures and one signal cannot tell them apart.

ONE-SHOT IS THE PRIMITIVE AND THE WATCH IS A LOOP AROUND IT. Building the
watch first would make the feature untestable without a scheduler and unusable
from anything that schedules its own polling, such as a cron or a login-node
session someone detaches.

NO NINTH STATUS. A job the scheduler killed, or one whose outputs never
arrive, takes a FAILED value with the scheduler and the descriptor named.
0.17.0 already spent a status value on ``SUBMITTED`` and the board carries a
node asking whether a seventh terminal status was worth amending a published
vocabulary for; the answer to that question must not be that so was a ninth.
"""

from __future__ import annotations

import shutil
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

# THE EXCEPTIONS COME FROM THE MODULES THAT DEFINE THEM, not from the
# package's exception CATALOG. The catalog re-exports every public error of
# the package, which means it imports `pyflightstream.post.products` and
# `pyflightstream.post.writers`; `post` sits ABOVE `run` in the layer order,
# so importing the catalog from here made this module depend upward at import
# time. The layering guard did not see it, and the reason is worth recording:
# the guard assigns rows from the core layer list, `exceptions` has no row, and
# an unrowed module is not examined. So the guard's no-allowlist property is
# weaker than it reads, because an unrowed module can be a conduit. Found by
# the architect lens of the 0.18.0 release round, 2026-09-14.
from typing import TYPE_CHECKING

from ..cases import CampaignConfigError
from ..workspace import (
    SIM_DATAPOINTS_DIR,
    CampaignWorkspace,
    PointName,
    RunRecord,
    RunStatus,
    WorkspaceError,
)
from ..workspace.inputs import resolve_hpc_profile

if TYPE_CHECKING:  # the return type of the whole judgement, without a runtime cycle
    from pyflightstream.run import Assessment

__all__ = [
    "CollectOutcome",
    "CollectReport",
    "Stamp",
    "assess_collected",
    "assessment_of_collected",
    "collect_once",
    "collect_and_post",
    "observe",
    "settled",
]

#: How long one observation waits before taking the second, in seconds. Two
#: seconds is long enough that a solver writing a table continuously changes
#: size between them and short enough that a one-shot sweep over a handful of
#: points is not a wait anybody notices. It is an argument everywhere it is
#: used, because the right value on a shared filesystem is not the right value
#: on a local disk and no default can know which this is.
DEFAULT_SETTLE_INTERVAL_S = 2.0

#: How long a watch waits between sweeps. Minutes rather than seconds: the
#: thing it is waiting for is a solver run, and a sweep that finds nothing
#: costs a directory listing per submitted point.
DEFAULT_WATCH_INTERVAL_S = 60.0


@dataclass(frozen=True)
class Stamp:
    """What one file looked like at one moment: its size and its mtime."""

    size: int
    mtime_ns: int


def observe(paths: Iterable[Path]) -> dict[str, Stamp | None]:
    """Return one stamp per path, or None where the path does not exist yet.

    NONE IS A REAL ANSWER HERE and not an error: the whole point of this
    stage is that it runs while the files are still missing.
    """
    seen: dict[str, Stamp | None] = {}
    for path in paths:
        try:
            info = path.stat()
        except OSError:
            seen[str(path)] = None
            continue
        seen[str(path)] = Stamp(size=info.st_size, mtime_ns=info.st_mtime_ns)
    return seen


def settled(before: Mapping[str, Stamp | None], after: Mapping[str, Stamp | None]) -> bool:
    """Return True when every path is present in both observations and unchanged.

    A path missing from either observation is NOT settled, which is the
    branch that carries the "presence" half of the condition; a path whose
    size or mtime moved between them is still being written.
    """
    if set(before) != set(after):
        return False
    if not before:
        # AN EMPTY DECLARED SET IS NOT SETTLED. A point that declares no
        # output would otherwise be collected the instant it was submitted,
        # which is how a stage that waits for files reports success for a
        # run that produced none.
        return False
    for name, first in before.items():
        second = after[name]
        if first is None or second is None or first != second:
            return False
    return True


@dataclass
class CollectOutcome:
    """What one submitted point did when the collector looked at it."""

    run_id: str
    state: str
    detail: str
    record: RunRecord | None = None


@dataclass
class CollectReport:
    """What one sweep did, per point and in total."""

    collected: list[CollectOutcome] = field(default_factory=list)
    waiting: list[CollectOutcome] = field(default_factory=list)
    failed: list[CollectOutcome] = field(default_factory=list)
    #: Points this stage cannot wait for, because their record names no
    #: declared set. SEPARATE FROM `waiting`, and the separation is the whole
    #: of it: UNKNOWN is a TERMINAL answer for that point, not a state a later
    #: sweep changes. While it counted as outstanding, `--watch` in a workspace
    #: holding one point submitted by 0.17.0 could never reach its own stop
    #: condition and swept forever, which is precisely the user 0.17.0's
    #: release note told to expect this stage. Found by the interface lens of
    #: the 0.18.0 release round, 2026-09-14.
    unknown: list[CollectOutcome] = field(default_factory=list)

    @property
    def outstanding(self) -> int:
        """How many submitted points this sweep left waiting FOR SOMETHING.

        A point whose record declares no outputs is not counted: nothing here
        knows what to wait for it, so waiting longer cannot change the answer,
        and a stop condition that includes it is a stop condition that cannot
        be reached.
        """
        return len(self.waiting)

    def lines(self) -> list[str]:
        """One human line per point, in the order a reader wants them."""
        out: list[str] = []
        for outcome in [*self.collected, *self.failed, *self.waiting, *self.unknown]:
            out.append(f"  {outcome.state:9} {outcome.run_id}: {outcome.detail}")
        return out


def _declared_outputs(record: RunRecord) -> list[str]:
    """Return the output names the submitted point was built to write.

    THEY COME OFF THE RECORD AND NOT OFF THE MATRIX, deliberately. A
    collector that re-read the matrix would read whatever the matrix says
    NOW, and a matrix edited between the submission and the collection is
    exactly the shape that made a recorded REmi of 11.7716754 read back as
    99.0 in a regenerated product (GEO-039-F02). The submission block
    carries what was declared at the moment the job was handed over.
    """
    submission = record.submission or {}
    declared = submission.get("declared_outputs")
    if isinstance(declared, (list, tuple)):
        return [str(name) for name in declared]
    return []


class _RecordAsCase:
    """The two fields the standard assessor reads, taken off the run record.

    NOT A SimCase AND NOT PRETENDING TO BE ONE. :class:`LoadsAssessor` reads
    exactly three things from its first argument: ``point``, ``outputs``, and
    the flight condition it binds the export against, and both of the first
    two are recorded on the row at submission from the case that produced it.
    So the values here are the RUN'S OWN, carried across, and nothing is
    invented.

    The assessor accepts ``None`` in this position and documents what happens
    then: the condition binding is recorded as EMPTY rather than as agreement.
    Passing the record's real point instead is what makes the binding a
    comparison rather than a blank, which is the whole reason this exists
    rather than a bare ``None``.
    """

    __slots__ = ("point", "outputs", "velocity", "datapoint_name")

    def __init__(self, record: RunRecord) -> None:
        self.point = dict(record.point or {})
        # 0.21.0: the folder the assessor judges is named by the name the run
        # RECORDED, never recomputed from a record that is not a case.
        self.datapoint_name = record.point_name
        self.outputs = list(record.outputs or _declared_outputs(record))
        # THE CASE DEFAULT THAT FILLS IN WHERE THE POINT SUPPLIES NO SPEED.
        # A record carries no case-level velocity, so this is None and the
        # binding falls to rule 3 of `_bind_case_conditions`: nothing is
        # requested, recorded as unasked rather than as agreed. That is the
        # honest answer and it is why the attribute is present rather than
        # absent, since `getattr` would otherwise silently produce the same
        # None and hide that the rule was reached deliberately.
        self.velocity = None


def assess_collected(record: RunRecord, sim_dir: Path) -> tuple[RunStatus, str | None]:
    """Judge a collected point from the files on disk, as a local run is judged.

    THIS EXISTS BECAUSE THE DEFAULT WAS A LIE. Until it did, `collect_once`
    with no assessor recorded every settled point ``CONVERGED``, whatever the
    solver had done, while four separate documents said the stage "assesses
    the run": the subcommand's own help, FR-99, the change log, and the
    submitting executor's docstring. A diverged cluster job, a job the
    scheduler killed after it had written its exports, and a clean run were
    recorded identically and their products built from that. Two independent
    review lenses found it in the same round, 2026-09-14.

    IT IS THE SAME JUDGEMENT THE LOCAL PATH MAKES, through the same class, so
    a point that ran here and a point that ran on a cluster are judged by one
    rule rather than by two that can drift. :class:`LoadsAssessor` reads only
    the collected files and the requested point; it never touches the
    execution result, which is why the two paths CAN share it even though only
    one of them has a process to report on.

    IT ANSWERS WITH THE PAIR THE INTERFACE DEFINES. Everything the log said
    -- the iteration, the residual, the times, the file -- is on the
    :class:`~pyflightstream.run.Assessment` that
    :func:`assessment_of_collected` returns, which is what the collect stage
    itself reads and stamps.

    WHAT IT STILL CANNOT SAY, and the caller is not told otherwise: whether
    the job was killed before it finished writing is the settle predicate's
    question, answered before this runs, and a scheduler's own exit status is
    not visible to a stage that deliberately watches the workspace instead of
    the queue.
    """
    assessment = assessment_of_collected(record, sim_dir)
    return assessment.status, assessment.error


def assessment_of_collected(record: RunRecord, sim_dir: Path) -> Assessment:
    """Return the WHOLE judgement of a collected point, not only its verdict.

    :func:`assess_collected` is the assessor INTERFACE a caller may replace,
    and it answers with the `(status, error)` pair that interface defines. This
    one answers with the :class:`~pyflightstream.run.Assessment` behind it: the
    iteration it reached, the residual it reached it at, the times the solver
    printed, and which file they were read from. On a cluster that is the whole
    of the evidence, because there is no process here to report on -- the
    record was the only place those numbers could land, and until 0.21.0 they
    landed nowhere.
    """
    from pyflightstream.run import LoadsAssessor

    return LoadsAssessor()(_RecordAsCase(record), None, sim_dir)  # type: ignore[arg-type]


def _sim_dir(workspace: CampaignWorkspace, record: RunRecord) -> Path:
    return workspace.sim_dir(record.sim_id)


def _working_dir(workspace: CampaignWorkspace, record: RunRecord) -> Path:
    """Return where the submitted job runs and writes its declared outputs.

    Since 0.18.1 a submitted point runs in its own datapoint folder and its
    submission block says so, relative to the simulation folder (GOAL-021
    item 3). A record written before that names none, and its job ran in the
    simulation folder, which is where the collector waits for it.
    """
    relative = str((record.submission or {}).get("working_dir") or "")
    base = _sim_dir(workspace, record)
    if not relative:
        return base
    # CONTAINED, OR REFUSED BY NAME (the architecture and interface lenses,
    # closing round). The field is read off an untyped block of a JSON file
    # someone can edit, and the collector would otherwise wait on whatever
    # folder it names; a working directory is a datapoint folder of this
    # record's own simulation, and nothing else.
    candidate = (base / relative).resolve()
    datapoints = (base / SIM_DATAPOINTS_DIR).resolve()
    if candidate.parent != datapoints:
        raise WorkspaceError(
            f"record {record.run_id!r} names its working_dir as {relative!r}, which does "
            f"not resolve to a datapoint folder of {base}. A submitted point runs in "
            f"{SIM_DATAPOINTS_DIR}/DP-<tag>/ of its own simulation; restore the field, "
            "or complete the record by hand."
        )
    return candidate


#: The suffix every solver log this package names carries, from EXPORT_KINDS.
LOG_SUFFIX = "_log.txt"


def _native_log_copy(
    workspace: CampaignWorkspace,
    record: RunRecord,
    names: list[str],
    work_dir: Path,
) -> str | None:
    """Copy the log the SCHEDULER wrote to the name the row declared (0.21.0).

    THE OWNING SEAT'S DECISION OF 2026-09-15, from the cluster. Some machines abort at
    ``EXPORT_LOG``: the job runs, every other export lands, and the log the
    package judges the run by never arrives, so `collect` waits for a file
    nothing will ever write. Such a machine writes its own log beside the run,
    and its HPC profile names it (``native_log = "FTS{sim}.l*"``); this copies
    that file to the declared name, so everything downstream reads one log
    whatever the scheduler called it.

    Returns the detail of a refusal, or None when there is nothing to say: no
    profile, no ``native_log``, the declared log already there, or the
    scheduler's file not written yet, which is a WAIT and not a failure.
    """
    profile = resolve_hpc_profile(workspace.inputs_dir)
    pattern = getattr(profile, "native_log", None)
    if not pattern:
        return None
    declared = [name for name in names if str(name).endswith(LOG_SUFFIX)]
    if not declared:
        return (
            f"the HPC profile names a native log ({pattern!r}) and this point declares no "
            f"output ending in {LOG_SUFFIX!r}, so there is no name to copy it to. The row "
            "declares its log among its outputs, which is how it is collected and how the "
            f"run is judged; its outputs are {', '.join(Path(n).name for n in names)}."
        )
    target = work_dir / declared[0]
    if target.exists():
        return None
    glob = pattern.format(sim=record.sim_id, point=record.point_name or "", **{})
    found = sorted(path for path in work_dir.glob(glob) if path.is_file())
    if len(found) > 1:
        return (
            f"the HPC profile's native_log ({pattern!r}) matches {len(found)} files in "
            f"{work_dir}: {', '.join(path.name for path in found)}. Which of them is this "
            "run's log is not a guess this package makes, because the log is what the run "
            "is judged by. Narrow the pattern, or clear the ones that are not this run's."
        )
    if found:
        shutil.copy2(found[0], target)
    return None


def collect_once(
    workspace: CampaignWorkspace,
    *,
    interval: float = DEFAULT_SETTLE_INTERVAL_S,
    sleep: Callable[[float], None] = time.sleep,
    observer: Callable[[Iterable[Path]], dict[str, Stamp | None]] = observe,
    assessor: Callable[[RunRecord, Path], tuple[RunStatus, str | None]] | None = None,
) -> CollectReport:
    """Sweep every SUBMITTED record once and collect the ones that settled.

    THE PRIMITIVE. It returns rather than waits, so a caller can run it from
    a cron, from a login-node session, or in the loop :func:`collect_and_post`
    puts around it.

    Parameters
    ----------
    workspace
        The campaign workspace whose manifest is swept.
    interval
        Seconds between the two observations that decide "settled".
    sleep, observer, assessor
        Injected so a test can run this with no clock, no filesystem delay
        and no solver. A stage whose only entry point needs a scheduler is a
        stage nothing tests, which is the reason the injection exists rather
        than a preference for injection.
    """
    report = CollectReport()
    try:
        records = workspace.read_manifest()
    except (WorkspaceError, CampaignConfigError) as error:
        raise WorkspaceError(f"the manifest could not be read: {error}") from error

    submitted = [r for r in records if r.status is RunStatus.SUBMITTED]
    if not submitted:
        return report

    for record in submitted:
        names = _declared_outputs(record)
        if not names:
            report.unknown.append(
                CollectOutcome(
                    run_id=record.run_id,
                    state="UNKNOWN",
                    detail=(
                        "the record names no declared outputs, so nothing here knows what to "
                        "wait for. A point submitted before 0.18.0 carries no such list and is "
                        "completed by hand, which is what its release said it would be."
                    ),
                )
            )
            continue
        sim_dir = _sim_dir(workspace, record)
        try:
            work_dir = _working_dir(workspace, record)
        except WorkspaceError as error:
            report.failed.append(
                CollectOutcome(run_id=record.run_id, state="FAILED", detail=str(error))
            )
            continue
        # THE SCHEDULER'S OWN LOG IS PUT WHERE THE ROW SAID, before anything
        # waits on it: on a machine that aborts at EXPORT_LOG the declared log
        # is the one file that never arrives, and the sweep would wait forever.
        refusal = _native_log_copy(workspace, record, names, work_dir)
        if refusal is not None:
            report.failed.append(
                CollectOutcome(run_id=record.run_id, state="FAILED", detail=refusal)
            )
            continue
        paths = [work_dir / name for name in names]
        first = observer(paths)
        sleep(interval)
        second = observer(paths)
        if not settled(first, second):
            missing = [n for n, stamp in second.items() if stamp is None]
            if missing:
                # 0.21.0: THE FILES ARE NAMED, not only counted. "1 of 8 not there
                # yet" sent a user looking through eight names to find the one
                # that never comes, which on a cluster was the solver log.
                detail = (
                    f"{len(missing)} of {len(names)} declared output(s) not there yet: "
                    + ", ".join(Path(n).name for n in missing)
                )
            else:
                detail = "every declared output is present and at least one is still changing"
            report.waiting.append(
                CollectOutcome(run_id=record.run_id, state="WAITING", detail=detail)
            )
            continue
        outcome = _complete(workspace, record, names, sim_dir, assessor)
        if outcome.state == "COLLECTED":
            report.collected.append(outcome)
        else:
            report.failed.append(outcome)
    return report


def _complete(
    workspace: CampaignWorkspace,
    record: RunRecord,
    names: Sequence[str],
    sim_dir: Path,
    assessor: Callable[[RunRecord, Path], tuple[RunStatus, str | None]] | None,
) -> CollectOutcome:
    """Collect one settled job's outputs and write its completed record.

    ONE CALL PER POINT WHERE THE RECORD SAYS WHICH POINT OWNS WHAT, and one
    call for the whole set where it does not. A swept row is submitted as ONE
    job whose record carries the first point in `point`, so filing the whole
    job under `record.point` put every point's exports in the first point's
    datapoint folder. `collect_outputs` states the rule that breaks: each
    point's evidence alone in its own folder is what makes a swept row
    judgeable, and nothing downstream then has to work out which of several
    files belongs to which point. The local sweep pays two passes to honour
    it and carries a comment about the defect that taught it.
    """
    try:
        collected = _collect_by_point(workspace, record, names, _working_dir(workspace, record))
    except (WorkspaceError, CampaignConfigError) as error:
        # THE SAME TWO EXCEPTIONS THE LOCAL PATH CATCHES, for the same
        # reason: collection refuses for two kinds of reason and only one of
        # them is a WorkspaceError, and an uncaught one here would abort a
        # sweep over every other submitted point in the workspace.
        failed = record.model_copy(
            update={
                "status": RunStatus.FAILED_INCOMPLETE_OUTPUT,
                "error": str(error),
            }
        )
        _write(workspace, failed)
        return CollectOutcome(
            run_id=record.run_id,
            state="FAILED",
            detail=f"collection refused: {error}",
            record=failed,
        )

    # NAMED APART FROM THE EXCEPTION ABOVE. `error` is bound by the `except`
    # clause a few lines up, and rebinding it here is a name that means two
    # things in one function; the type checker refused it and was right.
    # THE DEFAULT JUDGES. It used to be the literal CONVERGED with the
    # assessor an option no caller passed, which meant the shipped command
    # recorded every settled point as converged whatever the solver did. A
    # status field asserting a property nothing evaluated is the defect this
    # package exists to make structurally impossible, so the fallback is now
    # the same assessor the local path uses and `None` is not a way to reach
    # the old behaviour.
    # WHAT THE LOG SAID RIDES WITH THE VERDICT (0.21.0). A replaced assessor
    # answers with the pair its interface defines and nothing more; the
    # package's own reads the log, and everything it read is stamped.
    stamped: dict[str, object] = {}
    if assessor is None:
        assessment = assessment_of_collected(record, sim_dir)
        status, verdict = assessment.status, assessment.error
        for field_name in (
            "iterations",
            "residual",
            "residual_note",
            "log_file_used",
            "solver_run_time_s",
            "solver_initialization_s",
            "time_steps",
        ):
            value = getattr(assessment, field_name, None)
            if value is not None:
                stamped[field_name] = value
    else:
        status, verdict = assessor(record, sim_dir)
    update: dict[str, object] = {
        **stamped,
        "status": status,
        "outputs": list(collected),
        "error": verdict,
    }
    after = _points_ran_after(record, status)
    if after is not None:
        update["points_ran"] = after
    completed = record.model_copy(update=update)
    _write(workspace, completed)
    return CollectOutcome(
        run_id=record.run_id,
        state="COLLECTED",
        detail=f"{len(collected)} output(s) collected, recorded {status}",
        record=completed,
    )


def _collect_by_point(
    workspace: CampaignWorkspace,
    record: RunRecord,
    names: Sequence[str],
    work_dir: Path,
) -> list[str]:
    """File each declared output under the point that declared it.

    ``work_dir`` is where the job wrote: the simulation folder for a job over
    a whole row, and the point's own datapoint folder for a submitted point
    since 0.18.1, whose outputs are then collected in place.

    A record written before the per-point mapping existed, and a record for a
    single point, both fall to the whole-set call under `record.point`, which
    is correct for them: one point's job has one owner.
    """
    submission = record.submission or {}
    # IN PLACE ONLY WHERE THE RECORD SAYS THE JOB RAN IN ITS DATAPOINT FOLDER
    # (the V&V lens, closing round): a record written before 0.18.1 names no
    # working_dir, ran in the simulation folder, and asserts nothing.
    ran_here = bool(submission.get("working_dir"))
    by_point = submission.get("declared_by_point")
    points = submission.get("points_by_tag") or {}
    if not isinstance(by_point, Mapping) or len(by_point) <= 1:
        return list(
            workspace.collect_outputs(
                record.sim_id,
                [work_dir / name for name in names],
                datapoint=_recorded_name(record),
                ran_in_datapoint=ran_here,
            )
        )
    collected: list[str] = []
    for name, owned in by_point.items():
        if name not in points:
            raise WorkspaceError(
                f"record {record.run_id!r} declares outputs for point {name!r} and names no "
                "such point in its submission; restore the record, or complete it by hand."
            )
        collected.extend(
            workspace.collect_outputs(
                record.sim_id,
                [work_dir / str(output) for output in owned],
                datapoint=PointName(name),
                ran_in_datapoint=ran_here,
            )
        )
    return collected


def _recorded_name(record: RunRecord) -> PointName:
    """Return the point name the run recorded, where its outputs are filed (0.21.0).

    A record written before 0.21.0 carries none, and its folder is named by the
    earlier scheme; collecting it under a name recomputed now would file its
    outputs where no record of it points. It is refused by name instead.
    """
    if not record.point_name:
        raise WorkspaceError(
            f"record {record.run_id!r} was written before 0.21.0 and carries no point name, "
            "so this release cannot tell which folder its outputs belong in. Run "
            "`pyfs-matrix rename` once, naming the workspace root as workspace (CLI: --workspace), "
            "to move the workspace to the 0.21.0 names, then collect."
        )
    return PointName(record.point_name)


def _points_ran_after(record: RunRecord, status: RunStatus) -> list[dict] | None:
    """Rewrite the per-point list with what the collection found.

    A completed sweep whose `points_ran` still read SUBMITTED under a
    top-level CONVERGED was two fields of one row disagreeing about whether
    the run came back, and a consumer written against the local path's shape
    read the collected shape wrongly.
    """
    rows = record.points_ran
    if not rows:
        return None
    return [{**dict(row), "status": str(status)} for row in rows]


def _write(workspace: CampaignWorkspace, record: RunRecord) -> None:
    workspace.complete_submitted_record(record)


def collect_and_post(
    workspace: CampaignWorkspace,
    *,
    watch: bool = False,
    interval: float = DEFAULT_SETTLE_INTERVAL_S,
    watch_interval: float = DEFAULT_WATCH_INTERVAL_S,
    rounds: int | None = None,
    sleep: Callable[[float], None] = time.sleep,
    post: Callable[[CampaignWorkspace], None] | None = None,
    # NAMED, NOT PASSED THROUGH `**kwargs`. These are the two injection points
    # of the primitive and they used to reach it as `object`, with a
    # `type: ignore` recording that the checker had refused: on a module this
    # package declares public BECAUSE A CRON IMPORTS IT, a caller had to read
    # the source to learn that `assessor` was even a name. That is the case
    # the interface charter names outright, and `assessor` is the parameter a
    # serious caller most needs.
    observer: Callable[[Iterable[Path]], dict[str, Stamp | None]] = observe,
    assessor: Callable[[RunRecord, Path], tuple[RunStatus, str | None]] | None = None,
) -> CollectReport:
    """Collect, and post-process once something was collected.

    THE LOOP AROUND THE PRIMITIVE. With ``watch`` false this is one sweep,
    which is what a cron wants. With ``watch`` true it sweeps until nothing
    is outstanding, or until ``rounds`` sweeps have run, which is the bound
    that stops a test or a mistake becoming an endless loop.

    THE POST RUNS ONLY WHERE SOMETHING WAS COLLECTED. A sweep that found
    nothing new must not rewrite the products: rebuilding archives the
    previous ones by design, so a watch that posted every minute would fill
    the archive with copies of an unchanged answer.
    """
    total = CollectReport()
    swept = 0
    while True:
        report = collect_once(
            workspace,
            interval=interval,
            sleep=sleep,
            observer=observer,
            assessor=assessor,
        )
        total.collected.extend(report.collected)
        total.failed.extend(report.failed)
        total.waiting = list(report.waiting)
        total.unknown = list(report.unknown)
        swept += 1
        if report.collected and post is not None:
            post(workspace)
        if not watch:
            break
        if report.outstanding == 0:
            break
        if rounds is not None and swept >= rounds:
            break
        sleep(watch_interval)
    return total
