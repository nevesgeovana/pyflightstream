"""The effective record of a datapoint: the rules every reader of the records shares (0.35.0).

Pipeline role: the workspace-layer home of the rules that choose, for each
datapoint, the ONE record that states its present outcome (FR-381). The run
layer reads them to decide what a continuation continues, and
:mod:`pyflightstream.workspace.ledger` reads them to answer ``pyfs-matrix
status``; both sit above this module, so neither keeps a copy.

The rules, each from its one home:

1. **A steady row is one job over several points.** :meth:`RunRecord.as_points`
   expands ``points_ran``; a job that ran no point (refused before it ran, or
   SUBMITTED and not yet collected) stands for every point of its row, the
   rule :func:`pyflightstream.workspace.planned_points_without_record` states,
   so it is expanded here over the points its submission names, else over the
   points its plan names.
2. **A continuation replaces the run it continues.**
   :func:`pyflightstream.results.tables.superseded_by_a_continuation` names the
   continued runs; they are not effective.
3. **The latest record of a point is found by its name, not its id**
   (:func:`latest_record_of_point`): a continuation's run id is
   ``<campaign>/sim_<id>/r<stamp>/<name>``, so the name still ends it.
4. **A refused continuation that never started is a note, not a state**
   (:func:`is_a_continuation_that_never_started`).
5. **A ``delete-sims`` row is a note**: it is not a record, and the reader of
   the raw rows passes it over before anything here sees it.

Rules 3 and 4 lived in ``run/_continuation_frame.py`` until 0.35.0, where the
workspace layer could not reach them; they moved down unchanged and the run
layer imports them back.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from pyflightstream.results.tables import superseded_by_a_continuation
from pyflightstream.workspace import JOB_TAG, RunRecord, RunStatus

__all__ = [
    "EffectivePoints",
    "effective_points",
    "is_a_continuation_that_never_started",
    "latest_record_of_point",
    "record_point_name",
]

#: Planned points of one simulation: each point's name mapped to its sweep values.
PlannedPoints = Mapping[str, Mapping[str, float]]


def record_point_name(record: RunRecord) -> str:
    """Return the point name that ends a record's run id (``sweep`` for a job).

    Parameters
    ----------
    record : RunRecord
        A point record, or a job record (whose run id ends with ``sweep``).

    Returns
    -------
    str
        The last segment of ``record.run_id``.
    """
    return record.run_id.rsplit("/", 1)[-1]


def is_a_continuation_that_never_started(record: RunRecord) -> bool:
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

    Parameters
    ----------
    record : RunRecord
        Any run record.

    Returns
    -------
    bool
        True for the note of a refused continuation.
    """
    return (
        record.status is RunStatus.FAILED_SCRIPT
        and not record.script_sha256
        and record.recipe is None
    )


def latest_record_of_point(
    records: Iterable[RunRecord], sim_id: str, name: str
) -> RunRecord | None:
    """Return the most recent record of one point, in file order, whatever its status.

    A continuation's run id is ``<campaign>/sim_<id>/r<stamp>/<name>``, so the
    point name still ENDS every run id of the point, which is what this reads.

    Parameters
    ----------
    records : iterable of RunRecord
        The records, in file order.
    sim_id : str
        The simulation of the point.
    name : str
        The point name.

    Returns
    -------
    RunRecord or None
        The last record of that point that is not a refused continuation.
    """
    latest = None
    for record in records:
        if is_a_continuation_that_never_started(record):
            continue
        if record.sim_id == sim_id and record.run_id.endswith(f"/{name}"):
            latest = record
    return latest


@dataclass(frozen=True)
class EffectivePoints:
    """The effective record of every datapoint, and the notes passed over.

    Attributes
    ----------
    records : dict of (str, str) to RunRecord
        ``(sim_id, point name)`` to the point's effective record, one record
        per point, in the order the points were first recorded.
    notes : tuple of RunRecord
        The refused continuations that never started, in file order.
    superseded : dict of str to str
        Each continued run id mapped to the run id that continued it.
    """

    records: dict[tuple[str, str], RunRecord]
    notes: tuple[RunRecord, ...]
    superseded: dict[str, str]


def effective_points(
    records: Sequence[RunRecord], *, planned: Mapping[str, PlannedPoints] | None = None
) -> EffectivePoints:
    """Choose the effective record of every datapoint (FR-381, rules 1 to 4 above).

    Parameters
    ----------
    records : sequence of RunRecord
        The records of a workspace in file order, delete-sims notes left out.
    planned : mapping, optional
        Simulation id to its planned points (name to sweep values), over which
        a job that ran no point and names none is expanded.

    Returns
    -------
    EffectivePoints
        One record per datapoint, the notes, and the continued runs.

    Examples
    --------
    >>> effective_points([]).records
    {}
    """
    superseded = superseded_by_a_continuation(records)
    chosen: dict[tuple[str, str], RunRecord] = {}
    notes: list[RunRecord] = []
    for record in records:
        if is_a_continuation_that_never_started(record):
            notes.append(record)
            continue
        for point in _points_of(record, (planned or {}).get(record.sim_id, {})):
            if point.run_id not in superseded:
                chosen[(point.sim_id, record_point_name(point))] = point
    return EffectivePoints(records=chosen, notes=tuple(notes), superseded=superseded)


def _points_of(record: RunRecord, planned: PlannedPoints) -> list[RunRecord]:
    """Return one record per point of ``record``; a job that ran none stands for its row."""
    points = record.as_points()
    if record.points_ran or record_point_name(record) != JOB_TAG:
        return points
    submission = record.submission or {}
    named = submission.get("points_by_tag")
    by_name: Mapping[str, object] = named if isinstance(named, Mapping) and named else planned
    if not by_name:
        return points
    base = record.run_id.rsplit("/", 1)[0]
    out = []
    for name, values in by_name.items():
        point = dict(values) if isinstance(values, Mapping) else {}
        out.append(
            record.model_copy(
                update={"run_id": f"{base}/{name}", "point_name": name, "point": point}
            )
        )
    return out
