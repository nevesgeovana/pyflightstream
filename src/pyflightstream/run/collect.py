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
from ..workspace.naming import datapoint_name_of

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


def _datapoint_of(record: RunRecord) -> str | None:
    """Return the datapoint folder's NAME for this record's outputs, or None.

    The name the run RECORDED when it has one. When it does not -- every record
    written before 0.21.0 -- the folder the record's own submission block says
    the job ran in, which is read rather than recomputed: a name recomputed now
    would file the outputs where no record of them points, and that is the thing
    to avoid. None when the record names neither, which is a point submitted
    before 0.18.1, whose job ran in the simulation folder.

    ONE HOME, because the two callers must not disagree. `_recorded_name`
    refuses when this is None and the assessor's shim carries the None through,
    and when they disagreed the shim fell into the branch written for a real
    case and asked it for a field only a case has.
    """
    if record.point_name:
        return record.point_name
    # THE FOLDER NAME IS READ BY THE MODULE THAT WRITES IT, which answers None
    # for anything that is not a point's folder rather than raising an error
    # this sweep's handler does not catch (the architect lens, FIX-0211).
    #
    # WHAT THIS DOES NOT CHECK, stated because the same field is read twice in
    # this module with two different trust models: `_working_dir` resolves
    # `working_dir` and REFUSES one that is not a direct child of this record's
    # own `datapoints/`, and it runs before this on the collecting path. This
    # reads the name only and is not itself that check.
    ran_in = datapoint_name_of(Path(str((record.submission or {}).get("working_dir") or "")).name)
    if ran_in is None:
        return None
    # AND IT IS THIS RECORD'S FOLDER, not merely a datapoint folder of this
    # simulation. `_working_dir` checks the second and not the first, so an
    # edited `working_dir` naming ANOTHER point's folder was refused for a
    # record that carries a point name and accepted for one that does not --
    # this release's own records (the qa lens, FIX-0211). A 0.20.x record ends
    # its `run_id` in the tag, which is what `pyfs-matrix rename` reads it by,
    # so the record carries its own cross-check and only had to be asked.
    tail = str(record.run_id).rsplit("/", 1)[-1]
    return str(ran_in) if tail in ("", str(ran_in)) else None


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

    def __init__(self, record: RunRecord, *, velocity_is_the_point_s: bool = True) -> None:
        self.point = dict(record.point or {})
        # 0.21.0: the folder the assessor judges is named by the name the run
        # RECORDED, never recomputed from a record that is not a case. 0.21.1:
        # a record written before 0.21.0 recorded no name and names its folder
        # in its submission block instead, and reading it here is what keeps
        # the assessor out of the branch that would ask this shim for a field
        # only a real case has.
        self.datapoint_name = _datapoint_of(record)
        self.outputs = list(record.outputs or _declared_outputs(record))
        # THE VELOCITY THE RUN REQUESTED, which the record has carried since
        # OPS-2009.01.13 and which this read as None until 0.24.0, calling None
        # the honest answer. It was not: a local point whose export printed
        # 30 m/s against a requested 80 is FAILED_INCOMPLETE_OUTPUT, and the
        # same files collected from a cluster were CONVERGED, because nothing
        # here asked. The two paths claim one judgement and now make it.
        #
        # None still, in the one place the record cannot answer: a POINT OF A
        # JOB that sweeps a flow variable. The job's record carries the row's
        # velocity and not that point's, and holding a point to another
        # point's speed would refuse a correct export. Unasked is recorded as
        # unasked there, which rule 3 of `_bind_case_conditions` exists for.
        self.velocity = record.velocity_requested_m_s if velocity_is_the_point_s else None


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


@dataclass(frozen=True)
class _NativeLog:
    """What the HPC profile's ``native_log`` resolved to for one record."""

    #: The sentence of a refusal, or None.
    refusal: str | None = None
    #: The file the scheduler is writing, or None when there is none to read.
    source: Path | None = None
    #: The declared name the row's log is read under.
    target: Path | None = None


def _native_log(
    workspace: CampaignWorkspace,
    record: RunRecord,
    names: list[str],
    work_dir: Path,
) -> _NativeLog:
    """Find the log the SCHEDULER wrote, and the declared name it is read under (0.21.0).

    Some machines abort at
    ``EXPORT_LOG``: the job runs, every other export lands, and the log the
    package judges the run by never arrives, so `collect` waits for a file
    nothing will ever write. Such a machine writes its own log beside the run,
    and its HPC profile names it (``native_log = "FTS{sim}.l*"``); this copies
    that file to the declared name, so everything downstream reads one log
    whatever the scheduler called it.

    NOTHING IS COPIED HERE, since 0.24.0. This used to copy the scheduler's
    file to the declared name BEFORE the two settling observations, which then
    watched the COPY: a file nothing writes is settled by construction, so a
    job still running was collected and judged by the log as it stood at the
    first sweep, and the copy was never refreshed once it existed. The source
    is what is OBSERVED (:func:`collect_once`), and it is copied once it has
    settled (:func:`_copy_native_log`), over whatever an earlier sweep left.

    The answer carries a refusal; or the scheduler's file and the declared
    name; or neither, when there is nothing to say: no profile, no
    ``native_log``, or the scheduler's file not written yet, which is a WAIT
    and not a failure.
    """
    profile = resolve_hpc_profile(workspace.inputs_dir)
    pattern = getattr(profile, "native_log", None)
    if not pattern:
        return _NativeLog()
    declared = [name for name in names if str(name).endswith(LOG_SUFFIX)]
    if not declared:
        return _NativeLog(
            f"the HPC profile names a native log ({pattern!r}) and this point declares no "
            f"output ending in {LOG_SUFFIX!r}, so there is no name to copy it to. The row "
            "declares its log among its outputs, which is how it is collected and how the "
            f"run is judged; its outputs are {', '.join(Path(n).name for n in names)}."
        )
    target = work_dir / declared[0]
    # `{point}` IS THE FOLDER THIS RECORD'S OUTPUTS ARE IN, by the one rule,
    # not `point_name` alone: that is empty for exactly the records 0.21.1
    # supports, so a profile naming the point in its pattern would glob nothing,
    # copy no log, and wait for a file nothing writes (the qa lens, FIX-0211).
    glob = pattern.format(sim=record.sim_id, point=_datapoint_of(record) or "", **{})
    found = sorted(path for path in work_dir.glob(glob) if path.is_file())
    if len(found) > 1:
        return _NativeLog(
            f"the HPC profile's native_log ({pattern!r}) matches {len(found)} files in "
            f"{work_dir}: {', '.join(path.name for path in found)}. Which of them is this "
            "run's log is not a guess this package makes, because the log is what the run "
            "is judged by. Narrow the pattern, or clear the ones that are not this run's."
        )
    return _NativeLog(source=found[0] if found else None, target=target)


def _copy_native_log(native: _NativeLog) -> None:
    """Copy the SETTLED scheduler log to the declared name, over any earlier copy."""
    if native.source is not None and native.target is not None:
        shutil.copy2(native.source, native.target)


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
        native = _native_log(workspace, record, names, work_dir)
        if native.refusal is not None:
            report.failed.append(
                CollectOutcome(run_id=record.run_id, state="FAILED", detail=native.refusal)
            )
            continue
        # THE SCHEDULER'S FILE STANDS IN FOR THE DECLARED LOG while the two
        # observations are taken, because it is the one the job is writing.
        # Where the scheduler has written nothing yet the declared name is
        # observed as it always was, and reads as missing.
        paths = [
            native.source
            if native.source is not None and work_dir / name == native.target
            else work_dir / name
            for name in names
        ]
        first = observer(paths)
        sleep(interval)
        second = observer(paths)
        if not settled(first, second):
            missing = [
                str(native.target) if native.source is not None and n == str(native.source) else n
                for n, stamp in second.items()
                if stamp is None
            ]
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
        # SETTLED, so this is the log of a job that has stopped writing it.
        _copy_native_log(native)
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

    A JOB OVER SEVERAL POINTS IS FINALISED POINT BY POINT, in
    :func:`_complete_sweep`, and everything below is the record that is one
    point. Why the split is by point: a swept row is submitted as ONE
    job whose record carries the first point in `point`, so filing the whole
    job under `record.point` put every point's exports in the first point's
    datapoint folder. `collect_outputs` states the rule that breaks: each
    point's evidence alone in its own folder is what makes a swept row
    judgeable, and nothing downstream then has to work out which of several
    files belongs to which point. The local sweep pays two passes to honour
    it and carries a comment about the defect that taught it.
    """
    if _is_a_sweep_job(record):
        return _complete_sweep(workspace, record, sim_dir, assessor)
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
            # 0.24.0: WHAT WAS COMPARED, as the local path records it. The
            # verdict above rests on these checks, and a record that kept the
            # verdict and dropped the comparison could not say what the point
            # was held to. The reported version, build and output hashes stay
            # out: a hash taken at collection cannot say what bytes existed
            # when the job wrote them.
            "conditions",
        ):
            value = getattr(assessment, field_name, None)
            if value is not None:
                stamped[field_name] = value
    else:
        status, verdict = assessor(record, sim_dir)
    # G02: a job that imported trailing edges is held to the solver's count.
    log_file_used = stamped.get("log_file_used")
    status, verdict = _wake_edge_verdict(
        record,
        sim_dir,
        collected,
        log_file_used if isinstance(log_file_used, str) else None,
        status,
        verdict,
    )
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


#: The axes a point of a job can carry that say nothing about its speed. A
#: point carrying any other axis sweeps a flow variable, and the job's one
#: recorded velocity is then not that point's.
_ATTITUDE_AXES = frozenset({"alpha", "beta", "advance_ratio"})


def _is_a_sweep_job(record: RunRecord) -> bool:
    """Whether the record carries a job's per-point mapping, even for one point."""
    by_point = (record.submission or {}).get("declared_by_point")
    return isinstance(by_point, Mapping) and bool(by_point)


def _complete_sweep(
    workspace: CampaignWorkspace,
    record: RunRecord,
    sim_dir: Path,
    assessor: Callable[[RunRecord, Path], tuple[RunStatus, str | None]] | None,
) -> CollectOutcome:
    """Collect, assess and finalise EACH point of a submitted sweep (0.24.0).

    THE SHAPE IS THE LOCAL SWEEP'S, entry for entry: ``points_ran`` carries each
    point's tag, point, status, OUTPUTS, iterations and residual, the job's
    status is its worst point's by the one stated order, and its error names
    the points that failed. Until this existed the job was assessed once, as
    though it were its first point, one status was stamped on every entry and
    no entry was given its outputs, so :meth:`RunRecord.as_points` expanded a
    collected sweep into points with nothing in them and the products stage,
    which skips a record with no outputs, left the whole sweep out of every
    product without a word.

    TWO PASSES, for the reason the local sweep states: every point of the job
    wrote into one folder, and a point is judged only once its siblings' files
    have left it. A point whose collection is refused fails ALONE; the others
    ran, their files are on disk, and they are collected and judged.
    """
    from pyflightstream.run import worse_of

    submission = record.submission or {}
    by_point = submission["declared_by_point"]
    points = submission.get("points_by_tag") or {}
    work_dir = _working_dir(workspace, record)
    ran_here = bool(submission.get("working_dir"))
    collected_by_tag: dict[str, list[str]] = {}
    refused: dict[str, str] = {}
    for tag, owned in by_point.items():
        try:
            if tag not in points:
                raise WorkspaceError(
                    f"record {record.run_id!r} declares outputs for point {tag!r} and names "
                    "no such point in its submission; restore the record, or complete it by "
                    "hand."
                )
            collected_by_tag[tag] = list(
                workspace.collect_outputs(
                    record.sim_id,
                    [work_dir / str(output) for output in owned],
                    datapoint=PointName(tag),
                    ran_in_datapoint=ran_here,
                )
            )
        except (WorkspaceError, CampaignConfigError) as error:
            refused[tag] = str(error)

    ran: list[dict] = []
    worst = RunStatus.CONVERGED
    collected_all: list[str] = []
    error_lines: list[str] = []
    for tag in by_point:
        point = dict(points.get(tag) or {})
        if tag in refused:
            ran.append(
                {
                    "tag": tag,
                    "point": point,
                    "status": str(RunStatus.FAILED_INCOMPLETE_OUTPUT),
                }
            )
            worst = worse_of(worst, RunStatus.FAILED_INCOMPLETE_OUTPUT)
            error_lines.append(f"{tag}: {refused[tag]}")
            continue
        # THE POINT AS A RECORD OF ITS OWN, which is what both assessors are
        # written against: its tag as its name, its own point, its own outputs.
        as_point = record.model_copy(
            update={
                "run_id": f"{record.run_id.rsplit('/', 1)[0]}/{tag}",
                "point_name": tag,
                "point": point,
                "outputs": list(collected_by_tag[tag]),
                "points_ran": [],
            }
        )
        entry: dict[str, object] = {"tag": tag, "point": point}
        if assessor is None:
            from pyflightstream.run import LoadsAssessor

            shim = _RecordAsCase(as_point, velocity_is_the_point_s=set(point) <= _ATTITUDE_AXES)
            assessment = LoadsAssessor()(shim, None, sim_dir)  # type: ignore[arg-type]
            status, verdict = _wake_edge_verdict(
                record,
                sim_dir,
                collected_by_tag[tag],
                assessment.log_file_used,
                assessment.status,
                assessment.error,
            )
            entry.update(
                status=str(status),
                outputs=list(collected_by_tag[tag]),
                iterations=assessment.iterations,
                residual=assessment.residual,
            )
        else:
            status, verdict = assessor(as_point, sim_dir)
            status, verdict = _wake_edge_verdict(
                record, sim_dir, collected_by_tag[tag], None, status, verdict
            )
            entry.update(status=str(status), outputs=list(collected_by_tag[tag]))
        ran.append(entry)
        collected_all.extend(collected_by_tag[tag])
        if str(status).startswith("FAILED"):
            error_lines.append(f"{tag}: {verdict or status}")
        worst = worse_of(worst, status)

    completed = record.model_copy(
        update={
            "status": worst,
            "outputs": collected_all,
            "error": "; ".join(error_lines) or None,
            "points_ran": ran,
        }
    )
    _write(workspace, completed)
    return CollectOutcome(
        run_id=record.run_id,
        state="COLLECTED",
        detail=(
            f"{len(collected_all)} output(s) of {len(by_point)} point(s) collected, "
            f"recorded {worst}"
        ),
        record=completed,
    )


def _wake_edge_verdict(
    record: RunRecord,
    sim_dir: Path,
    collected: Sequence[str],
    log_file_used: str | None,
    status: RunStatus,
    verdict: str | None,
) -> tuple[RunStatus, str | None]:
    """Hold a collected job that imported trailing edges to the count its log states.

    G02. The local path judges a point the same way the moment its solver
    returns; a submitted job is judged here instead, from the number its
    submission recorded and the log the assessor read among the collected
    outputs. A job whose submission records no count imported nothing and is
    returned unchanged; one that did, with no log read, cannot be told to have
    marked anything.
    """
    from pyflightstream.run import _wake_edge_import_verdict, _with_wake_edge_verdict

    expected = (record.submission or {}).get("wake_edge_points")
    if not isinstance(expected, int):
        return status, verdict
    log_text: str | None = None
    for entry in collected if log_file_used else ():
        path = sim_dir / entry
        if Path(entry).name == log_file_used and path.is_file():
            log_text = path.read_text(encoding="utf-8", errors="replace")
            break
    return _with_wake_edge_verdict(status, verdict, _wake_edge_import_verdict(expected, log_text))


def _collect_by_point(
    workspace: CampaignWorkspace,
    record: RunRecord,
    names: Sequence[str],
    work_dir: Path,
) -> list[str]:
    """File the declared outputs of a record that is ONE point under that point.

    ``work_dir`` is where the job wrote: the point's own datapoint folder for a
    submitted point since 0.18.1, whose outputs are then collected in place,
    and the simulation folder before that.

    A record written before the per-point mapping existed, and a record for a
    single point, both come here, which is correct for them: one point's job
    has one owner. A job over several points never does: it is collected,
    assessed and finalised point by point in :func:`_complete_sweep`.
    """
    submission = record.submission or {}
    # IN PLACE ONLY WHERE THE RECORD SAYS THE JOB RAN IN ITS DATAPOINT FOLDER
    # (the V&V lens, closing round): a record written before 0.18.1 names no
    # working_dir, ran in the simulation folder, and asserts nothing.
    ran_here = bool(submission.get("working_dir"))
    return list(
        workspace.collect_outputs(
            record.sim_id,
            [work_dir / name for name in names],
            datapoint=_recorded_name(record),
            ran_in_datapoint=ran_here,
        )
    )


def _recorded_name(record: RunRecord) -> PointName:
    """Return the point name the run recorded, where its outputs are filed (0.21.0).

    A record written before 0.21.0 carries none. Its folder is then read off the
    record's OWN submission block, which names the datapoint the job ran in, and
    never recomputed: a name recomputed now would file the outputs where no
    record of it points, and that is what this refuses. The folder the record
    itself names is the opposite of a guess, and it is the same folder
    :func:`_working_dir` already resolves to read the outputs from.

    WHY THIS IS NOT A REFUSAL ANY MORE (0.21.1). Refusing here deadlocked a
    0.20.x workspace with submitted points, measured on a cluster 2026-09-16:
    `rename` refuses a SUBMITTED record whose folder would move and says to
    collect it first, and this said to rename first. Worse than the deadlock,
    the refusal is caught by the sweep and written as FAILED_INCOMPLETE_OUTPUT,
    so runs that had finished with every export on disk were stamped failed.

    Raises
    ------
    WorkspaceError
        If the record carries neither a point name nor a working directory,
        which is a record written before 0.18.1: its job ran in the simulation
        folder and no datapoint folder is named for it anywhere.
    """
    name = _datapoint_of(record)
    if name:
        return PointName(name)
    # WHICH OF THE TWO ACTUALLY HELD, because this sentence is written into
    # `record.error` on disk and a message that asserts an unchecked fact is
    # worse than a vague one (the V&V lens, FIX-0211). `_datapoint_of` answers
    # None for a record with no working directory AND for one whose working
    # directory is not a datapoint folder, which is what a pre-0.18.1 job that
    # ran in the simulation folder records.
    stated = str((record.submission or {}).get("working_dir") or "")
    where = (
        f"names its working directory as {stated!r}, which is not a datapoint folder"
        if stated
        else "names no working directory"
    )
    raise WorkspaceError(
        f"record {record.run_id!r} carries no point name and {where}, so nothing says "
        "which folder its outputs belong in. That is a point submitted before 0.18.1: "
        "its job ran in the simulation folder rather than in a datapoint folder of its "
        "own. Set `submission.working_dir` on this record in runs.json to the "
        "`datapoints/DP-<folder>` its outputs are in, or re-run the point."
    )


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
    post_matrix: Callable[[CampaignWorkspace, str | None], None] | None = None,
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

    ``post`` is called once per sweep that collected something, with the
    workspace alone. ``post_matrix`` is called once per MATRIX that sweep
    collected a record of, with the matrix stem the record names (None for a
    record that names none), in the order first collected. The products of a
    workspace are rebuilt per matrix, so a caller that rebuilds them needs the
    second: the command line's own post called the stage with no matrix, and
    the stage then selected the records naming none, which left every
    named-matrix record out and wrote nothing (0.24.0).
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
        if report.collected and post_matrix is not None:
            stems = [
                outcome.record.matrix_stem
                for outcome in report.collected
                if outcome.record is not None
            ]
            for stem in dict.fromkeys(stems):
                post_matrix(workspace, stem)
        if not watch:
            break
        if report.outstanding == 0:
            break
        if rounds is not None and swept >= rounds:
            break
        sleep(watch_interval)
    return total
