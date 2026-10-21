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
    false`` and names a ``native_log``. There `EXPORT_LOG` is not
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
the package already spent a status value on ``SUBMITTED`` and the board carries a
node asking whether a seventh terminal status was worth amending a published
vocabulary for; the answer to that question must not be that so was a ninth.
A non-failure outcome is RAN_MISSING_LOG (FR-413): every output of
the point is present and its declared solver log is not, a run that ENDED with
its outputs and whose log was deleted or never copied back. It is decided by
:func:`pyflightstream.workspace._missing_log.point_absent_logs` before any rule
that waits for the log or reads the job's end files, so such a point is neither
waited for forever nor failed as a job that ended without its log.
"""

from __future__ import annotations

import json
import math
import shutil
import time
import warnings
from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

# Import exceptions from their defining modules. The public exception
# catalog also imports post-processing modules above run in the layer order;
# using it here would introduce an upward dependency.
from typing import TYPE_CHECKING, Protocol, TypeGuard

from pyflightstream._errors import PyflightstreamError, PyflightstreamWarning
from pyflightstream._progress import tracked, workspace_activity
from pyflightstream.run._additional import (
    extraction_context,
    extraction_job_end,
    finish_extraction,
)
from pyflightstream.run._assessment import job_solver_identity
from pyflightstream.run._batch_collect import clock_stop_update, prepare_grouped_points
from pyflightstream.run._collect_logs import JOB_END_TAIL_LINES as JOB_END_TAIL_LINES
from pyflightstream.run._collect_logs import LOG_SUFFIX as LOG_SUFFIX
from pyflightstream.run._collect_logs import (
    NativeLog,
    job_ended_without_log,
    native_log,
    observed_paths,
)
from pyflightstream.run._collect_notes import (
    _datapoint_of,
    _declared_outputs,
    _RecordAsCase,
    is_a_sweep_job,
    job_log_note,
    limit_for_its_word,
    no_time_without_the_log,
    note_untranslated,
    refused_entry,
)
from pyflightstream.run._step_exports import missing_step_warning, untranslated_surfaces
from pyflightstream.workspace._batches import job_of
from pyflightstream.workspace._missing_log import (
    declared_log_names,
    missing_log_fields,
    missing_log_note,
    point_absent_logs,
)
from pyflightstream.workspace.storage import ensure_sim_expanded

from ..cases import CampaignConfigError
from ..cases.acoustics import acoustic_section_outputs
from ..cases.workflows import WALLTIME_CLOCK_STATE
from ..results import translate_surface_exports
from ..workspace import (
    SIM_DATAPOINTS_DIR,
    AdditionalRecord,
    CampaignWorkspace,
    MissingOutputsError,
    PointName,
    RunRecord,
    RunStatus,
    WorkspaceError,
    selected_sims,
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


# THE CALLBACKS' REAL CONTRACT (PFS-2095.027). They were annotated without
# ``sims`` and called with it under `type: ignore` when the collect is
# scoped, so a callback written to the annotation crashed after the records
# were written. The keyword is passed only when the collect is scoped.
class _Post(Protocol):
    """The ``post`` of :func:`collect_and_post`."""

    def __call__(
        self, workspace: CampaignWorkspace, /, *, sims: list[str] | None = None
    ) -> None: ...


class _PostMatrix(Protocol):
    """The ``post_matrix`` of :func:`collect_and_post`."""

    def __call__(
        self,
        workspace: CampaignWorkspace,
        matrix_stem: str | None,
        /,
        *,
        sims: list[str] | None = None,
    ) -> None: ...


@dataclass(frozen=True)
class Stamp:
    """What one file looked like at one moment: its size and its mtime."""

    size: int
    mtime_ns: int


def observe(paths: Iterable[Path]) -> dict[str, Stamp | None]:
    """Return one stamp per path, or None where the path does not exist yet.

    NONE IS A REAL ANSWER HERE and not an error: the whole point of this
    stage is that it runs while the files are still missing.

    Parameters
    ----------
    paths : iterable of Path
        The files to stamp.

    Returns
    -------
    dict of str to Stamp or None
        Path to its size and modification time, or None where it does not exist.
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

    Parameters
    ----------
    before : mapping of str to Stamp or None
        The first observation, from :func:`observe`.
    after : mapping of str to Stamp or None
        The second observation.

    Returns
    -------
    bool
        True when every path is present in both and unchanged.
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
    record: RunRecord | AdditionalRecord | None = None


@dataclass
class CollectReport:
    """What one sweep did, per point and in total."""

    collected: list[CollectOutcome] = field(default_factory=list)
    waiting: list[CollectOutcome] = field(default_factory=list)
    failed: list[CollectOutcome] = field(default_factory=list)
    #: Points whose records declare no output set cannot be awaited by this stage. They are
    #: reported separately from ``waiting``, so a caller can distinguish missing declarations
    #: from outputs still in progress.
    unknown: list[CollectOutcome] = field(default_factory=list)
    discarded: list[RunRecord] = field(default_factory=list)

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
            out.append(_outcome_line(outcome))
        for record in self.discarded:
            out.append(
                f"discarded WALLTIME_REACHED: sim {record.sim_id} {record.run_id} "
                f"(stopped at {record.stopped_at or '?'}); a grouped plan runs it again"
            )
        return out

    def failed_lines(self) -> list[str]:
        """Return the line :meth:`lines` prints for each point the sweep failed, and no other."""
        return [_outcome_line(outcome) for outcome in self.failed]


def _outcome_line(outcome: CollectOutcome) -> str:
    """Return the human line of one point's outcome: its state, its run, what happened."""
    return f"  {outcome.state:9} {outcome.run_id}: {outcome.detail}"


def assess_collected(record: RunRecord, sim_dir: Path) -> tuple[RunStatus, str | None]:
    """Judge a collected point from the files on disk, as a local run is judged.

    The default assessor judges settled points from their evidence; a settled process alone does
    not establish convergence.

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

    Parameters
    ----------
    record : RunRecord
        The SUBMITTED record of the point.
    sim_dir : Path
        The point's simulation folder, where the collected files are.

    Returns
    -------
    tuple of (RunStatus, str or None)
        The point's status and the error that explains it, None when there is none.
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
    record was the only place those numbers could land, and in legacy releases they
    landed nowhere.

    Parameters
    ----------
    record : RunRecord
        The SUBMITTED record of the point.
    sim_dir : Path
        The point's simulation folder, where the collected files are.

    Returns
    -------
    Assessment
        The status, the error and the evidence read from the log.
    """
    from pyflightstream.run import LoadsAssessor

    return LoadsAssessor()(_RecordAsCase(record), None, sim_dir)  # type: ignore[arg-type]


def _sim_dir(workspace: CampaignWorkspace, record: RunRecord) -> Path:
    return workspace.sim_dir(record.sim_id)


def _working_dir(workspace: CampaignWorkspace, record: RunRecord) -> Path:
    """Return where the submitted job runs and writes its declared outputs.

    A submitted point runs in its own datapoint folder and its
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


def _native_log_or_job_end(
    workspace: CampaignWorkspace, record: RunRecord, names: list[str], work_dir: Path
) -> tuple[NativeLog, CollectOutcome | None, tuple[str, ...]]:
    """Resolve the scheduler's log, and the outcome of a point that stops the sweep here.

    The outcome is the refusal ``native_log`` states, or the FAILED_EXECUTION
    record of a job that ended without its log (``job_ended_without_log``);
    None when the point is observed as before. The third answer names the
    declared solver logs that are absent while every other output is present
    (FR-413): asked BEFORE the end-of-job files are read, so such a point is
    RAN_MISSING_LOG and not FAILED_EXECUTION, and never when the scheduler has
    written a log of its own that collect copies to the declared name.
    """
    point = _datapoint_of(record) or ""
    native = native_log(workspace, record, names, work_dir, point=point)
    if native.refusal is not None:
        return (
            native,
            CollectOutcome(run_id=record.run_id, state="FAILED", detail=native.refusal),
            (),
        )
    absent = (
        point_absent_logs(record, work_dir, _sim_dir(workspace, record))
        if native.source is None
        else ()
    )
    if absent:
        return native, None, absent
    failed = job_ended_without_log(workspace, record, names, work_dir, native=native, point=point)
    if failed is None:
        return native, None, ()
    detail = str(failed.error).split("\n", 1)[0]
    return native, CollectOutcome(record.run_id, "FAILED", detail, record=failed), ()


def _copy_native_log(native: NativeLog) -> None:
    """Copy the SETTLED scheduler log to the declared name, over any earlier copy."""
    if native.source is not None and native.target is not None:
        shutil.copy2(native.source, native.target)


def _collect_additional(workspace, report, *, interval, sleep, observer, sims=None) -> None:
    """Complete stable submitted extractions; retain pending jobs and native logs."""
    from pyflightstream.workspace import ExtractionStatus

    latest = {record.extraction_id: record for record in workspace.read_additional()}
    for record in latest.values():
        if record.status is not ExtractionStatus.SUBMITTED:
            continue
        if sims is not None and record.sim_id not in sims:
            continue  # FR-307: another simulation's extraction is left as it is.
        try:
            # A COMPACTED SIMULATION IS EXPANDED FIRST, as the point path does
            # (PFS-2103.006): read zipped, its original and private copy were
            # "changed or missing" and the extraction failed for good.
            ensure_sim_expanded(workspace, record.sim_id, reason="collect")
            context = extraction_context(workspace, record)
            folder = context[1]
            generated = {str(item.get("dat")) for item in record.surface_translations or []}
            waited = [folder / name for name in record.declared_outputs if name not in generated]
            first = observer(waited)
            sleep(interval)
            second = observer(waited)
            if not settled(first, second):
                missing = [Path(name).name for name, stamp in second.items() if stamp is None]
                # A JOB THAT ENDED WITHOUT ITS OUTPUTS NEVER SETTLES
                # (PFS-2085.008): counted outstanding, it kept a watch sweeping
                # forever. The point path's job-end rule (FR-311) fails it.
                ended = extraction_job_end(workspace, record, folder) if missing else None
                if ended is not None:
                    raise WorkspaceError(f"{ended}; absent: {', '.join(missing)}")
                report.waiting.append(
                    CollectOutcome(
                        run_id=record.extraction_id,
                        state="WAITING",
                        record=record,
                        detail=(
                            "extraction outputs not present: " + ", ".join(missing)
                            if missing
                            else "extraction outputs are still changing"
                        ),
                    )
                )
                continue
            completed = finish_extraction(workspace, record, context)
        except (OSError, ValueError, WorkspaceError, CampaignConfigError) as error:
            completed = record.model_copy(
                update={
                    "status": ExtractionStatus.FAILED_EXECUTION,
                    "error": f"extraction collection refused: {error}",
                }
            )
            workspace.append_additional(completed)
        success = completed.status is ExtractionStatus.EXTRACTED
        outcome = CollectOutcome(
            run_id=record.extraction_id,
            state="COLLECTED" if success else "FAILED",
            detail=(
                f"{len(completed.outputs)} extraction outputs collected"
                if success
                else completed.error or "extraction failed"
            ),
            record=completed,
        )
        (report.collected if success else report.failed).append(outcome)


def _refuse_a_string(sims: object) -> None:
    """Refuse ``sims`` given as one string, which would be read character by character.

    PFS-2089.009: ``"2006,2007"`` was refused as simulations 2, 0, 6, and
    the message told a Python caller to write the ids comma separated.
    """
    if isinstance(sims, str):
        raise WorkspaceError(
            f'sims takes a list of ids, e.g. ["2006", "2007"], not the string {sims!r}: '
            'pass sims=["2006", "2007"], or --sims 2006,2007 on the command line'
        )


def _run_label(record: RunRecord) -> str:
    """Return a record as the collect progress line names it."""
    return record.run_id


def _of_the_simulations(records: list[RunRecord], sims: frozenset[str] | None) -> list[RunRecord]:
    """Return the records of ``sims``, or every record when it is None (FR-307)."""
    return records if sims is None else [record for record in records if record.sim_id in sims]


def _records_after_grouped_jobs(
    workspace: CampaignWorkspace,
    report: CollectReport,
    *,
    sims: Collection[str] | None,
    interval: float,
    sleep: Callable[[float], None],
    observer: Callable[[Iterable[Path]], dict[str, Stamp | None]],
) -> list[RunRecord]:
    """Read the manifest after the prepare step of the grouped jobs (FR-367 to FR-370).

    Every point of a grouped job (``--batch``, ``--polar-sweep``) is copied or
    moved home and given its own log by
    :func:`pyflightstream.run._batch_collect.prepare_grouped_points`, so the
    loop below completes it as a point that ran alone. A manifest with no
    grouped point comes back as read, untouched. A point the step completed
    as failed is reported here and not swept again; a note (a file the move
    replaced) is a warning.
    """
    sweep = prepare_grouped_points(
        workspace,
        workspace.read_manifest(),
        sims=sims,
        observer=observer,
        settled=settled,
        sleep=sleep,
        interval=interval,
    )
    for run_id, detail in sweep.failed:
        report.failed.append(CollectOutcome(run_id=run_id, state="FAILED", detail=detail))
    for note in sweep.notes:
        warnings.warn(note, PyflightstreamWarning, stacklevel=3)
    failed = {run_id for run_id, _ in sweep.failed}
    return [
        record
        for record in sweep.records
        if not (record.status is RunStatus.SUBMITTED and record.run_id in failed)
    ]


def _refuse_a_bad_interval(value: float, name: str) -> None:
    """Refuse a wait that is negative or not a finite number, before anything is swept (F-1463).

    A negative wait made ``time.sleep`` raise ValueError inside an extraction, which
    was then recorded as a failed execution of a valid extraction.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise WorkspaceError(f"{name} must be a finite number of seconds, not {value!r}")
    if value < 0:
        raise WorkspaceError(f"{name} must be zero or more seconds, not {value!r}")


@workspace_activity("collection")
def collect_once(
    workspace: CampaignWorkspace,
    *,
    interval: float = DEFAULT_SETTLE_INTERVAL_S,
    sleep: Callable[[float], None] = time.sleep,
    observer: Callable[[Iterable[Path]], dict[str, Stamp | None]] = observe,
    assessor: Callable[[RunRecord, Path], tuple[RunStatus, str | None]] | None = None,
    sims: Collection[str] | None = None,
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
        (``assessor`` as in :func:`collect_and_post`.) Injected so a test can run this with
        no clock, no filesystem delay
        and no solver. A stage whose only entry point needs a scheduler is a
        stage nothing tests, which is the reason the injection exists rather
        than a preference for injection.
    sims
        FR-307, ``collect --sims``: sweep only the SUBMITTED records
        of these simulations; every other record is left untouched and is not
        counted as outstanding. A simulation no record holds is refused by
        name before anything is swept. None sweeps every record.

    Returns
    -------
    CollectReport
        The points the sweep collected, failed, left waiting, and could not wait for because their
        record declares no outputs.

    Raises
    ------
    WorkspaceError
        If the manifest cannot be read, or ``sims`` names a simulation no record holds.
    """
    _refuse_a_string(sims)
    _refuse_a_bad_interval(interval, "interval")
    if assessor is assess_collected:
        # PFS-2110.038: the package's own assessor passed by name is the default, with
        # everything it read from the log stamped, not a caller's (status, error) assessor.
        assessor = None
    report = CollectReport()
    try:
        recorded = workspace.read_manifest()
    except (WorkspaceError, CampaignConfigError) as error:
        raise WorkspaceError(f"the manifest could not be read: {error}") from error
    # THE SELECTION IS VALIDATED BEFORE THE GROUPED STEP (PFS-2096.005), as
    # the docstring says: that step moves files home and writes failed
    # records, and ran first on the unstripped ids, before an unknown one
    # was refused. Its own refusals keep their own words.
    selected = None if sims is None else selected_sims(recorded, sims, scope="in the manifest")
    records = _records_after_grouped_jobs(
        workspace, report, sims=selected, interval=interval, sleep=sleep, observer=observer
    )
    submitted = [
        r for r in _of_the_simulations(records, selected) if r.status is RunStatus.SUBMITTED
    ]
    _collect_additional(
        workspace, report, interval=interval, sleep=sleep, observer=observer, sims=selected
    )

    for record in tracked("collect: points", submitted, label=_run_label):
        names = _declared_outputs(record)
        if not names:
            report.unknown.append(
                CollectOutcome(
                    run_id=record.run_id,
                    state="UNKNOWN",
                    detail=(
                        "the record names no declared outputs, so nothing here knows what to "
                        "wait for. A point without that list must be completed by hand."
                    ),
                )
            )
            continue
        ensure_sim_expanded(workspace, record.sim_id, reason="collect")
        sim_dir = _sim_dir(workspace, record)
        try:
            work_dir = _working_dir(workspace, record)
        except WorkspaceError as error:
            report.failed.append(
                CollectOutcome(run_id=record.run_id, state="FAILED", detail=str(error))
            )
            continue
        # A STEADY JOB OF SEVERAL POINTS ON A MACHINE THAT EXPORTS NO LOG
        #: its scheduler writes ONE log, the job's, and no point's log
        # ever arrives. The job is waited for by its points' other outputs and
        # by that one log, filed once under the job's name where the job ran;
        # waiting for a log per point was waiting forever.
        job_log = _job_log_name(workspace, record, names)
        if job_log is not None:
            names = [name for name in names if not name.endswith(LOG_SUFFIX)] + [job_log]
        # THE SCHEDULER'S OWN LOG IS PUT WHERE THE ROW SAID, before anything
        # waits on it: on a machine that aborts at EXPORT_LOG the declared log
        # is the one file that never arrives, and the sweep would wait forever.
        # FR-311: and A JOB THAT ENDED WITHOUT ITS LOG is failed, not waited for forever.
        # FR-413: AN ABSENT LOG BESIDE PRESENT OUTPUTS is not waited for: the
        # settled outputs decide, and the point is completed RAN_MISSING_LOG.
        native, stopped, absent = _native_log_or_job_end(workspace, record, names, work_dir)
        if stopped is not None:
            report.failed.append(stopped)
            continue
        names = [name for name in names if name not in absent]
        waited, paths = observed_paths(record, names, work_dir, native)
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
                # Name missing files so the user need not infer them from counts.
                detail = (
                    f"{len(missing)} of {len(waited)} declared output(s) not there yet: "
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
        # G45: each Tecplot from its VTK, where the job wrote them, before the
        # outputs are collected; the record keeps what was written and why not.
        if record.surface_translations:
            record = record.model_copy(
                update={
                    "surface_translations": translate_surface_exports(
                        work_dir, record.surface_translations
                    )
                }
            )
        outcome = _complete(
            workspace,
            record,
            names,
            sim_dir,
            assessor,
            job_log=None if job_log is None else work_dir / job_log,
            missing_logs=absent,
        )
        if outcome.state == "COLLECTED":
            report.collected.append(outcome)
        else:
            report.failed.append(outcome)
    return report


def _refused(workspace: CampaignWorkspace, record: RunRecord, error: Exception) -> CollectOutcome:
    """Record one point whose collection was refused, FAILED_INCOMPLETE_OUTPUT.

    THE SAME TWO EXCEPTIONS THE LOCAL PATH CATCHES, for the same reason:
    collection refuses for two kinds of reason and only one of them is a
    WorkspaceError, and an uncaught one here would abort a sweep over every
    other submitted point in the workspace.
    """
    refused: dict[str, object] = {
        "status": RunStatus.FAILED_INCOMPLETE_OUTPUT,
        "error": str(error),
    }
    # WHAT WAS FILED IS LISTED: a missing output no longer strands
    # the others, and a record naming none of them would strand them anyway.
    if isinstance(error, MissingOutputsError):
        refused["outputs"] = list(error.collected)
    failed = record.model_copy(update=refused)
    _write(workspace, failed)
    return CollectOutcome(
        run_id=record.run_id,
        state="FAILED",
        detail=f"collection refused: {error}",
        record=failed,
    )


def _job_log_name(
    workspace: CampaignWorkspace, record: RunRecord, names: Sequence[str]
) -> str | None:
    """Name the one log a steady job's scheduler writes, where no point exports its own.

    A steady row of several points is ONE job over one script, and on a
    machine whose HPC profile states ``export_log = false`` the script exports
    no log for any point: the scheduler writes one log of the whole job. So the
    job's log is filed once, under the job's script stem, and no point's
    declared log is waited for. None for anything else: a job on a machine that
    exports its logs, a job whose points declare none, and a record that is one
    point, whose scheduler log is its own and is copied to its declared name.
    """
    if not is_a_sweep_job(record) or not record.script_path:
        return None
    if not any(name.endswith(LOG_SUFFIX) for name in names):
        return None
    profile = resolve_hpc_profile(workspace.inputs_dir)
    if profile is None or profile.export_log:
        return None
    return f"{Path(record.script_path).stem}{LOG_SUFFIX}"


#: What the package's own assessor read, stamped on the collected record.
_STAMPED_FIELDS: tuple[str, ...] = (
    "fs_version_reported",
    "fs_build",
    "iterations",
    "residual",
    "residual_note",
    "log_file_used",
    "solver_run_time_s",
    "solver_initialization_s",
    "time_steps",
    # FR-434: the requested limit, set by the assessor only for MAX_ITER_REACHED.
    "iterations_requested",
    # Record the quasi-steady wheel's verdict per clocking.
    "clocking_verdicts",
    # Record the comparison supporting the verdict, matching the local path.
    # Solver identity comes from this point's loads export through the same
    # assessor used locally (FR-366).
    "conditions",
)


def _judged(
    record: RunRecord,
    sim_dir: Path,
    assessor: Callable[[RunRecord, Path], tuple[RunStatus, str | None]] | None,
    missing_logs: Sequence[str],
) -> tuple[RunStatus, str | None, dict[str, object]]:
    """Return one collected point's status, its error and the fields its assessment read.

    The default is the same assessor the local path uses. Record its log
    evidence with the verdict. A replaced
    assessor answers with the pair its interface defines,
    the package's own reads the log and everything it read is stamped.

    A POINT WHOSE LOG IS ABSENT (FR-413) is judged by its outputs alone: a
    failure they prove (another operating point, a refused reference) stands,
    and anything else is RAN_MISSING_LOG, never a verdict the absent log would
    have had to give, with every field only a log fills set to null.
    """
    stamped: dict[str, object] = {}
    if assessor is None:
        assessment = assessment_of_collected(record, sim_dir)
        status, verdict = assessment.status, assessment.error
        for field_name in _STAMPED_FIELDS:
            value = getattr(assessment, field_name, None)
            if value is not None:
                stamped[field_name] = value
    else:
        status, verdict = assessor(record, sim_dir)
    if missing_logs and not str(status).startswith("FAILED"):
        fields = missing_log_fields(missing_logs)
        status, verdict = RunStatus.RAN_MISSING_LOG, None
        stamped.pop("iterations_requested", None)
        stamped.update({key: value for key, value in fields.items() if key != "status"})
    return status, verdict, stamped


def _complete(
    workspace: CampaignWorkspace,
    record: RunRecord,
    names: Sequence[str],
    sim_dir: Path,
    assessor: Callable[[RunRecord, Path], tuple[RunStatus, str | None]] | None,
    *,
    job_log: Path | None = None,
    missing_logs: Sequence[str] = (),
) -> CollectOutcome:
    """Collect one settled job's outputs and write its completed record.

    ``missing_logs`` names the declared solver logs the sweep found absent
    beside every other output (FR-413): the point is collected without them
    and recorded RAN_MISSING_LOG unless its outputs prove a failure.

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
    if is_a_sweep_job(record):
        return _complete_sweep(
            workspace, record, sim_dir, assessor, job_log=job_log, missing_logs=missing_logs
        )
    # A surface the package cannot translate from the job's exported sources
    # is a package failure, not the solver's (untranslated_surfaces).
    untranslated: list[str] | None = None
    try:
        collected = _collect_by_point(workspace, record, names, _working_dir(workspace, record))
    except MissingOutputsError as error:
        untranslated = untranslated_surfaces(
            record.surface_translations, error.missing, error.collected
        )
        if untranslated is None:
            return _refused(workspace, record, error)
        collected = list(error.collected)
        for line in untranslated:
            warnings.warn(f"{record.run_id}: {line}", PyflightstreamWarning, stacklevel=2)
    except (WorkspaceError, CampaignConfigError) as error:
        return _refused(workspace, record, error)

    # NAMED APART FROM THE EXCEPTION ABOVE. `error` is bound by the `except`
    # clause a few lines up, and rebinding it here is a name that means two
    # things in one function; the type checker refused it and was right.
    status, verdict, stamped = _judged(record, sim_dir, assessor, missing_logs)
    # G02: a job that imported trailing edges is held to the solver's count;
    # G06: one whose solver could not use its disc's profile file, to that line.
    log_file_used = stamped.get("log_file_used")
    status, verdict = _log_verdicts(
        record,
        sim_dir,
        collected,
        log_file_used if isinstance(log_file_used, str) else None,
        status,
        verdict,
    )
    try:
        digests = workspace.output_digests(record.sim_id, collected)
    except WorkspaceError as error:
        return _refused(workspace, record, error)
    update: dict[str, object] = {
        **stamped,
        "status": status,
        "outputs": list(collected),
        "outputs_sha256": digests,
        "error": verdict,
        **clock_stop_update(record, _working_dir(workspace, record), status),
        **_wall_time_update(record, _working_dir(workspace, record), stamped),
    }
    if missing_logs:
        no_time_without_the_log(update)
    limit_for_its_word(update)
    counter = _action_counter(workspace, record)
    update["action_count"] = counter
    raw_steps = stamped.get("time_steps", record.time_steps)
    steps = raw_steps if isinstance(raw_steps, int) and not isinstance(raw_steps, bool) else None
    warning = missing_step_warning(
        record.action_program,
        counter,
        record.export_window,
        steps,
    )
    status_warnings = list(record.warnings)
    for line in [*(untranslated or []), *([warning] if warning else [])]:
        if line not in status_warnings:
            status_warnings.append(line)
    update["warnings"] = status_warnings
    after = _points_ran_after(record, status)
    if after is not None:
        update["points_ran"] = after
    completed = record.model_copy(update=update)
    _write(workspace, completed)
    return CollectOutcome(
        run_id=record.run_id,
        state="COLLECTED",
        detail=f"{len(collected)} output(s) collected, recorded {completed.status}"
        + ("; WARNING: " + "; ".join(status_warnings) if status_warnings else ""),
        record=completed,
    )


#: The axes a point of a job can carry that say nothing about its speed. A
#: point carrying any other axis sweeps a flow variable, and the job's one
#: recorded velocity is then not that point's.
_ATTITUDE_AXES = frozenset({"alpha", "beta", "advance_ratio"})


def _action_counter(workspace: CampaignWorkspace, record: RunRecord) -> int | None:
    """Return the point's step counter as its action program wrote it, else what the record has."""
    from pyflightstream.cases.workflows import UNSTEADY_ACTION_COUNT
    from pyflightstream.run import action_count

    try:
        counter = action_count(_working_dir(workspace, record) / UNSTEADY_ACTION_COUNT)
    except (OSError, ValueError, KeyError, TypeError):
        counter = None
    return record.action_count if counter is None else counter


def _wall_time_update(
    record: RunRecord, work_dir: Path, stamped: Mapping[str, object]
) -> dict[str, object]:
    """Return the wall time a collected point is recorded with, and how it was measured (FR-366).

    A point run alone records its wall time from the process clock. A point
    collected from a job has no process of its own, so the time is read from
    what the job measured for it: the point's own clock file (the elapsed
    seconds from the point's start to its last step callback), else the
    solver run time its sliced log prints. A point with neither records no
    time AND says why, in ``submission.job.wall_time_basis`` for a grouped
    point, so a null is never silent. A point submitted alone has no job
    entry; it records the clock file's time when one was written and is
    otherwise left as it was.
    """
    elapsed: float | None = None
    basis: str | None = None
    state_path = work_dir / WALLTIME_CLOCK_STATE
    try:
        state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.is_file() else {}
    except (OSError, ValueError):
        state = {}
    raw = state.get("elapsed_s") if isinstance(state, dict) else None
    if _is_a_wall_time(raw):
        elapsed = float(raw)
        basis = (
            f"the point's own clock file ({WALLTIME_CLOCK_STATE}): elapsed_s from the point's "
            "start to its last step callback, measured inside the solver run"
        )
    else:
        solver = stamped.get("solver_run_time_s")
        if _is_a_wall_time(solver):
            elapsed = float(solver)
            basis = "the solver run time printed in the point's sliced log (solver_run_time_s)"
    entry = job_of(record)
    update: dict[str, object] = {}
    if elapsed is not None:
        update["wall_time_s"] = elapsed
    if entry is not None:
        submission = dict(record.submission or {})
        submission["job"] = {
            **entry,
            "wall_time_basis": basis
            or (
                "not measured: the point wrote no clock file and its log prints no solver run "
                "time, so the job has no time of its own for it"
            ),
        }
        update["submission"] = submission
    return update


#: The longest wall time a point can honestly record: ten years, in seconds (F-266).
_MAX_WALL_TIME_S = 3.2e8


def _is_a_wall_time(value: object) -> TypeGuard[float]:
    """Whether ``value`` is a finite number of seconds, zero to ten years (F-266)."""
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and 0 <= value <= _MAX_WALL_TIME_S
    )


def _sweep_point_entry(
    record: RunRecord,
    as_point: RunRecord,
    sim_dir: Path,
    assessor: Callable[[RunRecord, Path], tuple[RunStatus, str | None]] | None,
    *,
    job_log_text: str | None,
    missing: Sequence[str],
) -> tuple[dict[str, object], RunStatus, str | None, tuple[str | None, str | None]]:
    """Assess one point of a submitted sweep: its ``points_ran`` entry, status and error.

    ``as_point`` is the point as a record of its own (its tag as its name, its
    own point and outputs), which is what both assessors are written against.
    A point whose own declared log is in ``missing`` (FR-413) is RAN_MISSING_LOG
    unless its outputs prove a failure, with no iteration count or residual.
    The fourth answer is the solver build and version the point read (None
    under an injected assessor), which the job folds (PFS-2103.033).
    """
    identity: tuple[str | None, str | None] = (None, None)
    tag = str(as_point.point_name)
    point = dict(as_point.point)
    collected = list(as_point.outputs)
    entry: dict[str, object] = {"tag": tag, "point": point}
    if assessor is None:
        from pyflightstream.run import LoadsAssessor

        shim = _RecordAsCase(as_point, velocity_is_the_point_s=set(point) <= _ATTITUDE_AXES)
        assessment = LoadsAssessor()(shim, None, sim_dir)  # type: ignore[arg-type]
        identity = (assessment.fs_build, assessment.fs_version_reported)
        status, verdict = _log_verdicts(
            record,
            sim_dir,
            collected,
            assessment.log_file_used,
            assessment.status,
            assessment.error,
            job_log=job_log_text,
        )
        read: dict[str, object] = {
            "iterations": assessment.iterations,
            "residual": assessment.residual,
        }
        if status == RunStatus.MAX_ITER_REACHED:
            # FR-974/FR-977: the limit the point stopped at, for the entry and its WARNING.
            read["iterations_requested"] = assessment.iterations_requested
            read["residual_note"] = assessment.residual_note
    else:
        status, verdict = assessor(as_point, sim_dir)
        status, verdict = _log_verdicts(
            record, sim_dir, collected, None, status, verdict, job_log=job_log_text
        )
        read = {}
    note = None
    if missing and not str(status).startswith("FAILED"):
        status, verdict, note = RunStatus.RAN_MISSING_LOG, None, missing_log_note(missing)
        read = dict.fromkeys(k for k in read if k not in ("iterations_requested", "residual_note"))
    entry.update(status=str(status), outputs=collected, **read)
    if note is not None:
        entry["residual_note"] = note
    return entry, status, verdict, identity


def _complete_sweep(
    workspace: CampaignWorkspace,
    record: RunRecord,
    sim_dir: Path,
    assessor: Callable[[RunRecord, Path], tuple[RunStatus, str | None]] | None,
    *,
    job_log: Path | None = None,
    missing_logs: Sequence[str] = (),
) -> CollectOutcome:
    """Collect, assess and finalise EACH point of a submitted sweep.

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
    # A point missing only surfaces the package failed to translate keeps its
    # assessment. Record that distinction per point on the job.
    job_warnings = list(record.warnings)
    # Where the machine exports no per-point logs, use the shared job log
    # (_job_log_name). Assess each point from its loads export; read the job log
    # for the shared script's import count. Each point and the job name this log.
    job_note, job_log_text = job_log_note(job_log, sim_dir)
    for tag, owned in by_point.items():
        if job_log is not None:
            owned = [name for name in owned if not str(name).endswith(LOG_SUFFIX)]
        owned = [name for name in owned if str(name) not in missing_logs]  # FR-413
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
        except MissingOutputsError as error:
            # Filed and listed, and the point still fails, unless all
            # it misses is the package's own translation.
            collected_by_tag[tag] = list(error.collected)
            note_untranslated(tag, error, owned, record, job_warnings=job_warnings, refused=refused)
        except (WorkspaceError, CampaignConfigError) as error:
            refused[tag] = str(error)

    ran: list[dict] = []
    worst = RunStatus.CONVERGED
    collected_all: list[str] = []
    error_lines: list[str] = []
    reported: list[tuple[str, str | None, str | None]] = []
    for tag in by_point:
        point = dict(points.get(tag) or {})
        if tag in refused:
            ran.append(refused_entry(tag, point, collected_by_tag.get(tag)))
            collected_all.extend(collected_by_tag.get(tag) or [])
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
        entry, status, verdict, (build, version) = _sweep_point_entry(
            record,
            as_point,
            sim_dir,
            assessor,
            job_log_text=job_log_text,
            missing=[name for name in missing_logs if name in by_point[tag]],
        )
        reported.append((tag, build, version))
        if job_note is not None:
            entry["residual_note"] = job_note
        ran.append(entry)
        collected_all.extend(collected_by_tag[tag])
        if str(status).startswith("FAILED"):
            error_lines.append(f"{tag}: {verdict or status}")
        worst = worse_of(worst, status)
    # THE JOB'S SOLVER IDENTITY, by the local sweep's one rule (PFS-2103.033):
    # this path stamped neither field, so the post could not state the
    # velocity convention of the job's sampled fields.
    identity, disagreements = job_solver_identity(reported)
    if disagreements:
        worst = worse_of(worst, RunStatus.FAILED_EXECUTION)
        error_lines.extend(disagreements)

    try:
        sweep_digests = workspace.output_digests(record.sim_id, collected_all)
    except WorkspaceError as error:
        return _refused(workspace, record, error)
    completed = record.model_copy(
        update={
            "status": worst,
            "outputs": collected_all,
            "outputs_sha256": sweep_digests,
            "error": "; ".join(error_lines) or None,
            "warnings": job_warnings,
            "points_ran": ran,
            **identity,
            **({"residual_note": job_note} if job_note is not None else {}),
        }
    )
    _write(workspace, completed)
    return CollectOutcome(
        run_id=record.run_id,
        # A refused point or a disagreeing solver identity is a failed collection, not a
        # collected one: the sweep must not let collect exit successfully over it.
        state="FAILED" if refused or disagreements else "COLLECTED",
        detail=(
            f"{len(collected_all)} output(s) of {len(by_point)} point(s) collected, "
            f"recorded {worst}"
        ),
        record=completed,
    )


def _log_verdicts(
    record: RunRecord,
    sim_dir: Path,
    collected: Sequence[str],
    log_file_used: str | None,
    status: RunStatus,
    verdict: str | None,
    *,
    job_log: str | None = None,
) -> tuple[RunStatus, str | None]:
    """Hold a collected job to what its solver log states, whatever the assessor said.

    Two verdicts, each over a status that is not already a failure. G02: a job
    that imported trailing edges is held to the count the solver logged, from
    the number its submission recorded; a job whose submission records no count
    imported nothing and is not held to one, and one that did, with no log
    collected, cannot be told to have marked anything. G06: a job whose log says
    the solver could not use its actuator disc's profile file is FAILED_SCRIPT,
    whatever its submission recorded, so a job submitted before this was read is
    judged by it too.

    The local path judges a point the same way the moment its solver returns;
    a submitted job is judged here instead, from the solver log among the
    collected outputs. The log is found whichever assessor judged the job: the
    file the package's own assessor names, or, for an assessor a caller passed,
    which answers with a status and names nothing, the one collected output
    that reads as a residual history, as the package's own assessor finds it.
    The four G06 lines are read in every collected log besides, found by its
    name: a log carrying no residual table, a scheduler's, is found by neither
    rule, and its refusal line was left unread under a CONVERGED point. A log
    is every output named ``_log.txt`` and every file the job was told to write
    its log to, whatever its name: the record's ``declared_logs`` when it carries
    the field, else its script's (FR-867, the workspace layer's one reading).
    """
    from pyflightstream.run._wake_edge_verdict import (
        SOLVER_OWN_LOG,
        actuator_profile_verdict,
        collected_log_texts,
        collected_solver_log,
        wake_edge_import_verdict,
        with_wake_edge_verdict,
    )

    log_text = collected_solver_log(sim_dir, collected, log_file_used)
    # Hold a point with no own log to the job log, supplied by the scheduler on
    # a machine that exports none (_job_log_name).
    if log_text is None:
        log_text = job_log
    expected = (record.submission or {}).get("wake_edge_points")
    if isinstance(expected, int):
        status, verdict = with_wake_edge_verdict(
            status, verdict, wake_edge_import_verdict(expected, log_text)
        )
    declared = declared_log_names(record, sim_dir)
    # The solver's own log, where the job ran, whether or not a row declared it:
    # it carries the four lines on a job that collected nothing else as a log.
    # Where the job ran: the datapoint folder its submission names relative to
    # the simulation, which holds when the workspace was moved after the
    # submission, and the absolute cwd the record kept, which holds when not.
    relative = str((record.submission or {}).get("working_dir") or "")
    cwd = getattr(record, "cwd", None)
    ran_in = [
        *([sim_dir / relative] if relative else []),
        *([Path(cwd)] if isinstance(cwd, str) and cwd else []),
    ]
    own = [
        (folder / SOLVER_OWN_LOG).read_text(encoding="utf-8", errors="replace")
        # F-608: the simulation folder holds other points' logs; read only if no folder recorded
        for folder in dict.fromkeys(ran_in or [sim_dir])
        if (folder / SOLVER_OWN_LOG).is_file()
    ]
    return with_wake_edge_verdict(
        status,
        verdict,
        actuator_profile_verdict(
            log_text, job_log, *own, *collected_log_texts(sim_dir, collected, declared)
        ),
    )


def _collect_by_point(
    workspace: CampaignWorkspace,
    record: RunRecord,
    names: Sequence[str],
    work_dir: Path,
) -> list[str]:
    """File the declared outputs of a record that is ONE point under that point.

    ``work_dir`` is where the job wrote: the point's own datapoint folder for a
    submitted point whose outputs are then collected in place,
    and the simulation folder before that.

    A record written before the per-point mapping existed, and a record for a
    single point, both come here, which is correct for them: one point's job
    has one owner. A job over several points never does: it is collected,
    assessed and finalised point by point in :func:`_complete_sweep`.
    """
    submission = record.submission or {}
    # Collect in place only when the record says the job ran in its datapoint
    # folder. A record without working_dir cannot establish that location.
    ran_here = bool(submission.get("working_dir"))
    collected = workspace.collect_outputs(
        record.sim_id,
        [work_dir / name for name in names],
        datapoint=_recorded_name(record),
        ran_in_datapoint=ran_here,
    )
    # E2: list acoustic section files where the job ran.
    return acoustic_section_outputs(workspace.sim_dir(record.sim_id), collected)


def _recorded_name(record: RunRecord) -> PointName:
    """Return the point name the run recorded, where its outputs are filed.

    A record written in legacy releases carries none. Its folder is then read off the
    record's OWN submission block, which names the datapoint the job ran in, and
    never recomputed: a name recomputed now would file the outputs where no
    record of it points, and that is what this refuses. The folder the record
    itself names is the opposite of a guess, and it is the same folder
    :func:`_working_dir` already resolves to read the outputs from.

    Collection remains available when workspace names differ from the current naming policy.
    Submitted points must be collected before their folders can be renamed.

    Raises
    ------
    WorkspaceError
        If the record carries neither a point name nor a working directory,
        which is a record written in legacy releases: its job ran in the simulation
        folder and no datapoint folder is named for it anywhere.
    """
    name = _datapoint_of(record)
    if name:
        return PointName(name)
    # Distinguish a missing working directory from one outside a datapoint
    # folder. _datapoint_of returns None for both; the persisted error must
    # state only the condition actually established (FIX-0211).
    stated = str((record.submission or {}).get("working_dir") or "")
    where = (
        f"names its working directory as {stated!r}, which is not a datapoint folder"
        if stated
        else "names no working directory"
    )
    raise WorkspaceError(
        f"record {record.run_id!r} carries no point name and {where}, so nothing says "
        "which folder its outputs belong in. Set `submission.working_dir` on this "
        "record in runs.json to the "
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
    discard_walltime: bool = False,
    interval: float = DEFAULT_SETTLE_INTERVAL_S,
    watch_interval: float = DEFAULT_WATCH_INTERVAL_S,
    rounds: int | None = None,
    sleep: Callable[[float], None] = time.sleep,
    post: _Post | None = None,
    post_matrix: _PostMatrix | None = None,
    # Name and type the primitive's two injection points explicitly so callers
    # of this public scheduled-collection interface can discover its assessor.
    observer: Callable[[Iterable[Path]], dict[str, Stamp | None]] = observe,
    assessor: Callable[[RunRecord, Path], tuple[RunStatus, str | None]] | None = None,
    sims: Collection[str] | None = None,
) -> CollectReport:
    """Collect, then post-process after collection or an explicit walltime discard.

    THE LOOP AROUND THE PRIMITIVE. With ``watch`` false this is one sweep,
    which is what a cron wants. With ``watch`` true it sweeps until nothing
    is outstanding, or until ``rounds`` sweeps have run, which is the bound
    that stops a test or a mistake becoming an endless loop.

    THE POST RUNS ONLY WHERE SOMETHING CHANGED. A sweep that found
    nothing new must not rewrite the products: rebuilding can archive the
    previous ones, so a watch that posted every minute would fill
    the archive with copies of an unchanged answer.

    ``post`` is called once per sweep that collected or discarded something, with the
    workspace alone. ``post_matrix`` is called once per MATRIX that sweep
    collected or discarded a record of, with the matrix stem the record names (None for a
    record that names none), in the order first collected. The products of a
    workspace are rebuilt per matrix, so a caller that rebuilds them needs the
    second: the command line's own post called the stage with no matrix, and
    the stage then selected the records naming none, which left every
    named-matrix record out and wrote nothing.

    ``sims`` (FR-307) limits every sweep to the SUBMITTED records of
    those simulations (:func:`collect_once`) and the post to the same
    simulations: ``post`` is then called with the keyword ``sims`` too, and
    ``post_matrix`` with ``sims`` naming the ones of that matrix.

    Parameters
    ----------
    workspace : CampaignWorkspace
        The campaign workspace whose manifest is swept.
    watch : bool, optional
        Sweep until nothing is outstanding or ``rounds`` sweeps have run; one sweep when false.
    discard_walltime : bool, optional
        Mark the latest WALLTIME_REACHED records in scope FAILED_MARKED after
        each sweep, before post. Keep their outputs for the next run to archive.
    interval : float, optional
        Seconds between the two observations that decide settled.
    watch_interval : float, optional
        Seconds between two sweeps of a watch.
    rounds : int, optional
        The most sweeps a watch runs; None for no bound.
    sleep : callable, optional
        The clock, injected so a test runs with none.
    post : callable, optional
        Called with the workspace once per sweep that collected or discarded something,
        and with the keyword ``sims`` too when ``sims`` scopes the collect; it must take it.
    post_matrix : callable, optional
        Called once per matrix a sweep changed a record of, with the workspace and the matrix
        stem, and with the keyword ``sims`` too when ``sims`` scopes the collect; it must
        take it.
    observer : callable, optional
        Stamps the paths, :func:`observe` by default.
    assessor : callable, optional
        Judges a collected point. None, the default, and :func:`assess_collected` passed
        explicitly are the package's own assessor, and everything it read from the log is
        stamped on the record. Any other callable answers ``(status, error)`` only, and
        no log field is stamped.
    sims : collection of str, optional
        Limit every sweep and the post to the SUBMITTED records of these simulations.

    Returns
    -------
    CollectReport
        The points every sweep collected, failed and discarded, and the points the last sweep
        left waiting or could not wait for.
    """
    _refuse_a_string(sims)
    _refuse_a_bad_interval(interval, "interval")
    _refuse_a_bad_interval(watch_interval, "watch_interval")
    selected = None
    if sims is not None:
        # REFUSED BEFORE THE FIRST SWEEP, so a watch over a typo stops at once.
        selected = selected_sims(workspace.read_manifest(), sims, scope="in the manifest")
    total = CollectReport()
    # ONE FAILED OUTCOME PER POINT, the latest (PFS-2103.032): a refusal that
    # writes no record leaves the point SUBMITTED, so a watch kept going by
    # other points refused it again each sweep and piled up its outcome.
    failed: dict[str, CollectOutcome] = {}
    swept = 0
    while True:
        report = collect_once(
            workspace,
            interval=interval,
            sleep=sleep,
            observer=observer,
            assessor=assessor,
            sims=selected,
        )
        if discard_walltime:
            report.discarded = _discard_walltime(workspace, selected)
        total.discarded.extend(report.discarded)
        total.collected.extend(report.collected)
        failed.update((outcome.run_id, outcome) for outcome in report.failed)
        # F-1464: a run that collects in a later sweep is no longer a failure of the watch.
        for outcome in report.collected:
            failed.pop(outcome.run_id, None)
        total.failed = list(failed.values())
        total.waiting = list(report.waiting)
        total.unknown = list(report.unknown)
        swept += 1
        _post_sweep(workspace, report, selected=selected, post=post, post_matrix=post_matrix)
        if not watch:
            break
        if report.outstanding == 0:
            break
        if rounds is not None and swept >= rounds:
            break
        sleep(watch_interval)
    return total


def _discard_walltime(
    workspace: CampaignWorkspace, selected: frozenset[str] | None
) -> list[RunRecord]:
    """Discard clock-stopped current records within this collect's scope."""
    from pyflightstream.run._record_files import mark_runs_failed

    latest = {record.run_id: record for record in workspace.read_manifest()}
    # F-609: a record a later run continues is superseded; only the end of a chain is current.
    superseded = {record.continues for record in latest.values() if record.continues}
    run_ids = [
        record.run_id
        for record in _of_the_simulations(list(latest.values()), selected)
        if record.status is RunStatus.WALLTIME_REACHED and record.run_id not in superseded
    ]
    return mark_runs_failed(
        workspace,
        run_ids,
        reason="collect --discard-walltime",
        discarded_by="collect --discard-walltime",
    )


def _post_sweep(
    workspace: CampaignWorkspace,
    report: CollectReport,
    *,
    selected: frozenset[str] | None,
    post: _Post | None,
    post_matrix: _PostMatrix | None,
) -> None:
    """Post the changed matrices; a refused post is said as the post's own (PFS-2095.052).

    The records are written before the post runs, so a product stage's
    refusal or an OSError is no collection failure: it reaches the caller as
    one WorkspaceError saying so, where it escaped as a traceback.
    """
    try:
        _post_each(workspace, report, selected=selected, post=post, post_matrix=post_matrix)
    except (OSError, PyflightstreamError) as error:
        said = "the points were collected and their records written; the post was refused"
        raise WorkspaceError(f"{said}: {error}") from error


def _post_each(
    workspace: CampaignWorkspace,
    report: CollectReport,
    *,
    selected: frozenset[str] | None,
    post: _Post | None,
    post_matrix: _PostMatrix | None,
) -> None:
    """Post matrices changed by collection or discard after their records are written."""
    if not report.collected and not report.discarded:
        return
    if post is not None:
        if selected is None:
            post(workspace)
        else:
            post(workspace, sims=sorted(selected))
    if post_matrix is None:
        return
    records = [outcome.record for outcome in report.collected if outcome.record is not None]
    stems = [record.matrix_stem for record in [*records, *report.discarded]]
    recorded = workspace.read_manifest() if selected is not None else []
    for stem in dict.fromkeys(stems):
        if selected is None:
            post_matrix(workspace, stem)
            continue
        of_matrix = {record.sim_id for record in recorded if record.matrix_stem == stem}
        post_matrix(workspace, stem, sims=sorted(selected & of_matrix))
