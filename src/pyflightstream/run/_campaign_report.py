"""The closing report of a campaign run: the per-row line, the status table, the job statuses.

Moved out of ``_campaign`` so that module keeps its size; the functions are
unchanged and ``_campaign`` imports them by name.
"""

from __future__ import annotations

import warnings
from collections.abc import Mapping, Sequence

from pyflightstream._errors import PyflightstreamWarning
from pyflightstream._progress import quiet_keeps
from pyflightstream.cases import Campaign
from pyflightstream.run._executors import _clock
from pyflightstream.run._ids import _run_id, _say
from pyflightstream.workspace import (
    CampaignWorkspace,
    RunRecord,
    WorkspaceError,
    planned_points_without_record,
)


def _say_the_rows(
    campaign: Campaign,
    workspace: CampaignWorkspace,
    known: Sequence[RunRecord],
    *,
    quiet: bool,
) -> None:
    """Say, per row, how many planned points have a record, and warn of the rest.

    One line per row of the campaign, on the terminal and in
    ``logs/activity.log``: ``row 4016: all 10 executed``, or ``row 4016: 6 of
    10 point(s) executed, 4 not attempted``. A point is executed when a record
    of this campaign carries it, from this call or an earlier one
    (:func:`~pyflightstream.workspace.planned_points_without_record`); a row
    with points no record carries is also a warning naming them. The manifest
    is read again, because a forced re-run archived records this call started
    from; where it cannot be read, the records this call knows stand in.
    """
    try:
        rows: Sequence[Mapping[str, object]] = workspace.read_raw_manifest()
    except (OSError, ValueError, WorkspaceError):
        rows = [record.model_dump(mode="json") for record in known]
    for case in campaign.sims:
        planned = [_run_id(campaign, case, point) for point in case.sweep.points()]
        missing = planned_points_without_record(planned, rows)
        total = len(planned)
        if not missing:
            _say(f"row {case.sim_id}: all {total} executed", quiet=quiet)
            continue
        _say(
            f"row {case.sim_id}: {total - len(missing)} of {total} point(s) executed, "
            f"{len(missing)} not attempted",
            quiet=quiet,
        )
        warnings.warn(
            f"row {case.sim_id}: {len(missing)} of its {total} planned point(s) were not "
            "attempted and no record carries them: "
            + ", ".join(run_id.rsplit("/", 1)[-1] for run_id in missing)
            + ". Run the row again with --resume, which runs the points no record carries.",
            PyflightstreamWarning,
            stacklevel=3,
        )


def _job_point_statuses(record: RunRecord, points: int) -> list[str]:
    """Return one status per point of a job record, each point's own where it has one.

    A job whose record carries an entry for every point it ran counts each by its
    entry; one that stopped before it could (a preparation refusal, a solver that
    never started) counts every point at the job's status.
    """
    entries = record.points_ran or []
    if len(entries) == points:
        return [str(entry.get("status") or record.status) for entry in entries]
    return [str(record.status)] * points


def _say_the_summary(outcomes: Sequence[str], elapsed_s: float, *, quiet: bool) -> None:
    """Say how the points of this call ended, as a small table, and how long it took (G43)."""
    counts: dict[str, int] = {}
    for status in outcomes:
        counts[status] = counts.get(status, 0) + 1
    width = max(len("status"), *(len(status) for status in counts))
    rule = f"  +-{'-' * width}-+--------+"
    _say(rule, quiet=quiet)
    _say(f"  | {'status':<{width}} | points |", quiet=quiet)
    _say(rule, quiet=quiet)
    for status, count in sorted(counts.items()):
        _say(f"  | {status:<{width}} | {count:>6} |", quiet=quiet)
    _say(rule, quiet=quiet)
    _say(f"  {len(outcomes)} point(s) in {_clock(elapsed_s)}", quiet=quiet)
    # FR-997: the table in one line is what a quiet console says of a run.
    ended = ", ".join(f"{status} {count}" for status, count in sorted(counts.items()))
    quiet_keeps(f"{len(outcomes)} point(s) in {_clock(elapsed_s)}: {ended}")
