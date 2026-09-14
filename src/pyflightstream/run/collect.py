"""Collect a submitted job's outputs when they land, then post (FR-99).

THE OWNER'S ARCHITECTURE, in her own words on 2026-09-13: not
submit-and-collect but COLLECT-AND-POST. A watcher stands by, sees that the
file is not there yet, waits until it is, and only then generates the
post-processing.

WHY THAT IS BETTER THAN WATCHING THE SCHEDULER, which is what an earlier
design proposed and she replaced: it DECOUPLES THE STAGE FROM THE QUEUE. A
watcher that watches FILES needs no status command in the submission profile,
no job-script template and no second scheduler vocabulary, and the same stage
then serves a cluster job, a local run somebody interrupted, and outputs a
colleague dropped in by hand. The proposed design made the collector a client
of the queue; hers makes it a client of the WORKSPACE, which is the thing this
package actually owns.

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
2. THE LAST DECLARED OUTPUT IS PRESENT. This is the stronger statement,
   because the emitted script's own order ends with the log: `EXPORT_LOG` and
   `CLOSE_FLIGHTSTREAM` are the last two commands every workflow emits, so a
   log that exists and has settled means the solver closed the file and left.

Neither is a scheduler query, so neither costs a profile key, which is the
whole advantage of her architecture. Both are required, because a run that
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

import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from ..exceptions import CampaignConfigError, WorkspaceError
from ..workspace import CampaignWorkspace, RunRecord, RunStatus

__all__ = [
    "CollectOutcome",
    "CollectReport",
    "Stamp",
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

    @property
    def outstanding(self) -> int:
        """How many submitted points this sweep left waiting."""
        return len(self.waiting)

    def lines(self) -> list[str]:
        """One human line per point, in the order a reader wants them."""
        out: list[str] = []
        for outcome in [*self.collected, *self.failed, *self.waiting]:
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


def _sim_dir(workspace: CampaignWorkspace, record: RunRecord) -> Path:
    return workspace.sim_dir(record.sim_id)


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
            report.waiting.append(
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
        paths = [sim_dir / name for name in names]
        first = observer(paths)
        sleep(interval)
        second = observer(paths)
        if not settled(first, second):
            missing = [n for n, stamp in second.items() if stamp is None]
            if missing:
                detail = f"{len(missing)} of {len(names)} declared output(s) not there yet"
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
    """Collect one settled point's outputs and write its completed record."""
    try:
        collected = workspace.collect_outputs(
            record.sim_id,
            [sim_dir / name for name in names],
            datapoint=record.point,
        )
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
    status, verdict = (RunStatus.CONVERGED, None)
    if assessor is not None:
        status, verdict = assessor(record, sim_dir)
    completed = record.model_copy(
        update={
            "status": status,
            "outputs": list(collected),
            "error": verdict,
        }
    )
    _write(workspace, completed)
    return CollectOutcome(
        run_id=record.run_id,
        state="COLLECTED",
        detail=f"{len(collected)} output(s) collected, recorded {status}",
        record=completed,
    )


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
    **kwargs: object,
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
        report = collect_once(workspace, interval=interval, sleep=sleep, **kwargs)  # type: ignore[arg-type]
        total.collected.extend(report.collected)
        total.failed.extend(report.failed)
        total.waiting = list(report.waiting)
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
