"""The ledger: one read-only snapshot of a workspace's records (0.35.0).

Pipeline role: the reader under every query verb of ``pyfs-matrix`` (FR-379 to
FR-385) and their Python mirror (FR-388). :func:`read_ledger` reads the run
records (``runs.json``, or the manifest ``runs`` names), each matrix's plan
(``post/<matrix>/plan.json``) and each post's product index
(``post/<matrix>/products.json``) once, and answers from that snapshot:

- :meth:`Ledger.status`, one row per polar (a simulation and its sweep);
- :meth:`Ledger.points`, one row per datapoint;
- :meth:`Ledger.freshness`, per matrix, whether the plan and the post are current;
- :meth:`Ledger.card`, the effective record of one datapoint by its run id;
- :meth:`Ledger.sim_folders`, where a simulation's folder is, a batch's included.

Every answer is plain dictionaries and strings, so a script reads the same rows
the command prints, with no data frame.

A datapoint is counted once, by its effective record, chosen by the rules of
:mod:`pyflightstream.workspace._effective` (FR-381), the one home the run layer
reads too. A point a plan names and no record carries is counted with the
derived status :data:`PLANNED`, written in lower case so that no recorded word
can be mistaken for it (FR-382, FR-384); recorded words are printed as recorded.

READ ONLY (FR-383). Nothing here writes, creates a folder, takes or waits on the
manifest lock, expands a compacted simulation or asks a scheduler: the files are
read whole, each in one call, so a writer that replaces ``runs.json`` at that
moment is neither slowed nor refused. A row of the manifest that cannot be read
is named by its position and run id and the other rows are read
(:attr:`Ledger.unreadable`); only a manifest that is not JSON at all is refused.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from pyflightstream._digest import optional_file_sha256
from pyflightstream.cases.naming import (
    POINT_AXIS_KEYS,
    POINT_NAME_FIELDS,
    SWEEP_NAME_VALUE,
    name_field,
)
from pyflightstream.workspace import (
    RunRecord,
    RunStatus,
    WorkspaceError,
    find_matrix,
    planned_points_without_record,
)
from pyflightstream.workspace._batches import batch_sim_dirs
from pyflightstream.workspace._effective import effective_points
from pyflightstream.workspace._ledger_api import (
    activity_rows,
    additional_rows,
    diff,
    history,
    point_card,
    point_rows,
    post_log_groups,
    status_rows,
    trace_product,
)
from pyflightstream.workspace.naming import resolve_manifest
from pyflightstream.workspace.storage import COMPACTED_SUFFIX, DELETED_SIM_KEY

__all__ = [
    "PLANNED",
    "POINT_COLUMNS",
    "STATUS_COLUMNS",
    "STATUS_SCHEMA",
    "Ledger",
    "activity_rows",
    "additional_rows",
    "diff",
    "history",
    "point_card",
    "point_rows",
    "post_log_groups",
    "status_rows",
    "trace_product",
    "listed_sims",
    "matrix_stem",
    "read_ledger",
    "status_text",
]

#: The schema identifier of the ``--json`` document of ``pyfs-matrix status``.
STATUS_SCHEMA = "pyfs-status/1"

#: The DERIVED state of a point a plan names and no record carries. Lower case
#: on purpose: every recorded status word is upper case (FR-382 R2, FR-384 R4).
PLANNED = "planned"

#: The keys of one polar row, in the order the table, the CSV and the JSON print them.
STATUS_COLUMNS = ("sim", "polar", "sweep", "points", "matrix", "status")

#: The keys of one datapoint row (``status --points``), in print order.
POINT_COLUMNS = (
    "sim",
    "point",
    "matrix",
    "status",
    "was",
    "iterations",
    "residual",
    "wall_s",
    "build",
    "where",
)

_PLAN_FILE = "plan.json"
_PRODUCTS_FILE = "products.json"

#: The recorded words that ended a run without failing it, in the enum's order.
_CONCLUDED = (RunStatus.CONVERGED, RunStatus.COMPLETED_MAX_ITER, RunStatus.WALLTIME_REACHED)

#: A point-name field code back to the sweep variable it writes (``AL`` to ``alpha``).
_AXIS_OF_CODE = {
    POINT_NAME_FIELDS[key].code: axis
    for axis, key in POINT_AXIS_KEYS.items()
    if key in POINT_NAME_FIELDS
}
_SWEPT_CODE = re.compile(r"([A-Z]+)" + re.escape(SWEEP_NAME_VALUE))


def listed_sims(text: str) -> list[str]:
    """Read simulation ids as ``delete-sims`` spells them: ``4001,2009`` or ``[4001,2009]``.

    Parameters
    ----------
    text : str
        The ids, comma separated, with or without square brackets.

    Returns
    -------
    list of str
        The ids, in the order given, blanks dropped.

    Examples
    --------
    >>> listed_sims("[2006, 2007]")
    ['2006', '2007']
    """
    listed = text.replace(" ", "").strip("[]")
    return [item for item in listed.split(",") if item]


def matrix_stem(value: str) -> str:
    """Return the stem a matrix argument names: ``l1_g6``, ``l1_g6.fs`` or a path to it.

    Parameters
    ----------
    value : str
        A matrix stem, file name or path.

    Returns
    -------
    str
        The file name without its ``.fs`` suffix.

    Examples
    --------
    >>> matrix_stem("inputs/matrices/l1_g6.fs")
    'l1_g6'
    """
    name = Path(value).name
    return name[: -len(".fs")] if name.lower().endswith(".fs") else name


def status_text(counts: Mapping[str, int]) -> str:
    """Return a polar's status: the one word, or the count of each word.

    One word when every datapoint shares it. Otherwise each word with its count,
    in the order of FR-379 R3: the concluded words (CONVERGED,
    COMPLETED_MAX_ITER, WALLTIME_REACHED), then the failed ones (``FAILED_*``),
    then SUBMITTED, then :data:`PLANNED`; a word no group names comes last.

    Parameters
    ----------
    counts : mapping of str to int
        Status word to the number of datapoints in it.

    Returns
    -------
    str
        For example ``CONVERGED`` or ``CONVERGED 6, FAILED_DIVERGED 1, planned 2``.

    Examples
    --------
    >>> status_text({"SUBMITTED": 2, "FAILED_DIVERGED": 1, "CONVERGED": 6})
    'CONVERGED 6, FAILED_DIVERGED 1, SUBMITTED 2'
    """
    present = [word for word, count in counts.items() if count]
    if len(present) == 1:
        return present[0]
    return ", ".join(f"{word} {counts[word]}" for word in sorted(present, key=_word_order))


def _word_order(word: str) -> tuple[int, int, str]:
    """Order a status word by its FR-379 R3 group, then by the enum's order."""
    order = [status.value for status in RunStatus]
    position = order.index(word) if word in order else len(order)
    if word in {status.value for status in _CONCLUDED}:
        group = 0
    elif word.startswith("FAILED"):
        group = 1
    elif word == RunStatus.SUBMITTED.value:
        group = 2
    elif word == PLANNED:
        group = 3
    else:
        group = 4
    return group, position, word


def _sim_order(sim: str) -> tuple[int, int, str]:
    """Order simulation ids as numbers, an id that is not a number after them."""
    return (0, int(sim), sim) if sim.isdigit() else (1, 0, sim)


def _mtime(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat(timespec="seconds")


def _validation_text(error: ValidationError) -> str:
    first = error.errors()[0]
    where = ".".join(str(part) for part in first["loc"]) or "row"
    more = f" (and {error.error_count() - 1} more)" if error.error_count() > 1 else ""
    return f"{where}: {first['msg']}{more}"


@dataclass(frozen=True)
class _Entry:
    """One datapoint of the snapshot: its effective record, or None when only planned."""

    sim: str
    name: str
    matrix: str
    values: Mapping[str, float]
    record: RunRecord | None

    @property
    def word(self) -> str:
        return PLANNED if self.record is None else str(self.record.status.value)


@dataclass(frozen=True)
class _Plan:
    """One matrix's plan receipt as read: its points by simulation, or why it was not read."""

    stem: str
    points: dict[str, dict[str, dict[str, float]]]
    run_ids: tuple[str, ...]
    matrix_sha256: str | None
    error: str | None


@dataclass(frozen=True)
class _Records:
    """What the manifest's rows hold: records, notes and unreadable rows."""

    records: list[RunRecord]
    raw: list[dict[str, Any]]
    notes: list[dict[str, object]]
    unreadable: list[dict[str, object]]


@dataclass(frozen=True)
class Ledger:
    """One read-only snapshot of a workspace's records (FR-388).

    Built by :func:`read_ledger`; every method answers from the snapshot and
    reads no file again, except :meth:`freshness` (the matrices on disk) and
    :meth:`sim_folders` (the folders), which only read.

    Attributes
    ----------
    root : Path
        The workspace root.
    manifest : Path
        The run-record file read.
    read_at : str
        When the snapshot was read, ISO 8601 in UTC.
    sources : dict of str to str
        Each file read, relative to the root, to its modification time.
    unreadable : tuple of dict
        Each manifest row that could not be read: ``position`` (1 for the
        first row), ``run_id`` (None when the row names none) and ``error``.
    notes : tuple of dict
        The rows that are notes rather than records: ``delete-sims`` notes and
        refused continuations that never started.
    """

    root: Path
    manifest: Path
    read_at: str
    sources: dict[str, str]
    unreadable: tuple[dict[str, object], ...]
    notes: tuple[dict[str, object], ...]
    _entries: tuple[_Entry, ...]
    _plans: dict[str, _Plan]
    _records: tuple[RunRecord, ...]
    _products: dict[str, dict[str, Any]]

    def records(self) -> list[dict[str, Any]]:
        """Return every valid present record, before effective-point selection.

        Returns
        -------
        list of dict
            Independent JSON-serializable copies in manifest order.

        Examples
        --------
        >>> read_ledger("campaign").records()  # doctest: +SKIP
        """
        return [record.model_dump(mode="json") for record in self._records]

    def status(
        self,
        *,
        sims: Iterable[str] | None = None,
        matrix: str | None = None,
        statuses: Sequence[str] = (),
        failed: bool = False,
    ) -> list[dict[str, object]]:
        """Return one row per polar, ordered by matrix then simulation id as a number.

        Parameters
        ----------
        sims : iterable of str, optional
            Only these simulations.
        matrix : str, optional
            Only the polars of this matrix stem.
        statuses : sequence of str, optional
            Only the polars with a datapoint in one of these words; a word
            ending in ``*`` matches every word it begins.
        failed : bool, optional
            Only the polars with at least one failed datapoint.

        Returns
        -------
        list of dict
            The keys of :data:`STATUS_COLUMNS`, then ``recorded`` (datapoints
            with a record), ``planned`` (datapoints the plan names, None when
            no plan names the simulation) and ``counts`` (word to count).
        """
        rows = []
        for (stem, sim), entries in self._polars(sims=sims, matrix=matrix).items():
            words = [entry.word for entry in entries]
            if not _wanted(words, statuses=statuses, failed=failed):
                continue
            rows.append(self._polar_row(stem, sim, entries))
        return rows

    def points(
        self,
        *,
        sims: Iterable[str] | None = None,
        matrix: str | None = None,
        statuses: Sequence[str] = (),
        failed: bool = False,
    ) -> list[dict[str, object]]:
        """Return one row per datapoint, by its effective record (``status --points``).

        Parameters
        ----------
        sims : iterable of str, optional
            Only these simulations.
        matrix : str, optional
            Only this matrix stem.
        statuses : sequence of str, optional
            Only the datapoints in one of these words (``*`` as in :meth:`status`).
        failed : bool, optional
            Only the failed datapoints.

        Returns
        -------
        list of dict
            The keys of :data:`POINT_COLUMNS`, then ``run_id`` (None for a
            planned point). ``was`` is the status a FAILED_MARKED record
            replaced; ``where`` is ``local``, the job label of a grouped run,
            or ``cluster``.
        """
        rows = []
        for (stem, sim), entries in self._polars(sims=sims, matrix=matrix).items():
            for entry in entries:
                if _wanted([entry.word], statuses=statuses, failed=failed):
                    rows.append(_point_row(stem, sim, entry))
        return rows

    def card(self, run_id: str) -> dict[str, object] | None:
        """Return the effective record of the datapoint whose run id is ``run_id``.

        Parameters
        ----------
        run_id : str
            The run id of an effective point record (a job's point carries its
            job's prefix and its own point name).

        Returns
        -------
        dict or None
            The record as the manifest writes it, or None when no effective
            record has that run id.
        """
        for entry in self._entries:
            if entry.record is not None and entry.record.run_id == run_id:
                return entry.record.model_dump(mode="json")
        return None

    def unmatched(self, sims: Iterable[str]) -> list[str]:
        """Return the ids of ``sims`` that name no record and no planned point (FR-380 R4).

        Parameters
        ----------
        sims : iterable of str
            Simulation ids.

        Returns
        -------
        list of str
            The ids no datapoint of the snapshot carries, in the order given.
        """
        known = {entry.sim for entry in self._entries}
        return [sim for sim in dict.fromkeys(sims) if sim not in known]

    def sim_folders(self, sim_id: str) -> list[str]:
        """Return where a simulation's files are, relative to the root, without opening any.

        Parameters
        ----------
        sim_id : str
            The simulation id.

        Returns
        -------
        list of str
            ``sims/sim_<id>`` when it is a folder, ``sims/sim_<id>.zip`` when it
            is compacted (read as it is, never expanded), and each
            ``sims/batch/<label>/sim_<id>`` a batch holds while it runs.
        """
        sims = self.root / "sims"
        found = [
            path
            for path in (sims / f"sim_{sim_id}", sims / f"sim_{sim_id}{COMPACTED_SUFFIX}")
            if path.exists()
        ]
        found += batch_sim_dirs(self.root).get(sim_id, [])
        return [path.relative_to(self.root).as_posix() for path in found]

    def freshness(self, *, matrix: str | None = None) -> list[dict[str, object]]:
        """Return, per matrix, whether its plan and its post are current (FR-382 R4).

        Parameters
        ----------
        matrix : str, optional
            Only this matrix stem.

        Returns
        -------
        list of dict
            ``matrix``; ``plan``: ``current`` (made from the matrix on disk),
            ``stale`` (made from another revision), ``unpinned`` (it does not
            say which matrix it measured), ``no matrix`` (the matrix is in
            neither home), ``unreadable`` or ``absent``; ``post``: ``complete``,
            ``incomplete`` or ``absent``; ``posted_at``, the index's
            modification time; ``not_posted``, the recorded runs of the matrix
            the index does not name.
        """
        stems = sorted({stem for stem, _ in self._polars(sims=None, matrix=matrix)} - {""})
        return [self._freshness_of(stem) for stem in stems]

    def document(self, rows: Sequence[Mapping[str, object]]) -> dict[str, object]:
        """Return the ``--json`` document of these rows (FR-385 R2).

        Parameters
        ----------
        rows : sequence of dict
            Rows from :meth:`status` or :meth:`points`.

        Returns
        -------
        dict
            ``schema`` (:data:`STATUS_SCHEMA`), ``workspace``, ``read_at``,
            ``sources`` (file to modification time), ``rows``, and the
            ``unreadable`` rows and ``notes`` of the manifest.
        """
        return {
            "schema": STATUS_SCHEMA,
            "workspace": str(self.root),
            "read_at": self.read_at,
            "sources": dict(self.sources),
            "rows": [dict(row) for row in rows],
            "unreadable": [dict(item) for item in self.unreadable],
            "notes": [dict(item) for item in self.notes],
        }

    def _polars(
        self, *, sims: Iterable[str] | None, matrix: str | None
    ) -> dict[tuple[str, str], list[_Entry]]:
        """Group the datapoints by (matrix, simulation), in the order rows are printed."""
        wanted = None if sims is None else set(sims)
        stem = None if matrix is None else matrix_stem(matrix)
        groups: dict[tuple[str, str], list[_Entry]] = {}
        for entry in self._entries:
            if (wanted is None or entry.sim in wanted) and (stem is None or entry.matrix == stem):
                groups.setdefault((entry.matrix, entry.sim), []).append(entry)
        return dict(sorted(groups.items(), key=lambda item: (item[0][0], _sim_order(item[0][1]))))

    def _polar_row(self, stem: str, sim: str, entries: Sequence[_Entry]) -> dict[str, object]:
        counts = Counter(entry.word for entry in entries)
        recorded = sum(1 for entry in entries if entry.record is not None)
        plan = self._plans.get(stem)
        planned = len(plan.points[sim]) if plan is not None and sim in plan.points else None
        values = [entry.values for entry in entries]
        polar = _polar_name(entries)
        return {
            "sim": sim,
            "polar": polar,
            "sweep": _swept(values, polar),
            "points": str(recorded) if planned is None else f"{recorded}/{planned}",
            "matrix": stem,
            "status": status_text(counts),
            "recorded": recorded,
            "planned": planned,
            "counts": dict(sorted(counts.items(), key=lambda item: _word_order(item[0]))),
        }

    def _freshness_of(self, stem: str) -> dict[str, object]:
        products = self._products.get(stem)
        recorded = [record.run_id for record in self._records if record.matrix_stem == stem]
        if products is None:
            post, posted_at, missing = "absent", None, recorded
        else:
            provenance = products.get("provenance") or {}
            post = "complete" if products.get("complete") is True else "incomplete"
            posted_at = products.get("_mtime")
            missing = [run_id for run_id in recorded if run_id not in provenance]
        return {
            "matrix": stem,
            "plan": self._plan_state(stem),
            "post": post,
            "posted_at": posted_at,
            "not_posted": missing,
        }

    def _plan_state(self, stem: str) -> str:
        plan = self._plans.get(stem)
        if plan is None:
            return "absent"
        if plan.error is not None:
            return "unreadable"
        if plan.matrix_sha256 is None:
            return "unpinned"
        try:
            path = find_matrix(self.root, stem)
        except WorkspaceError:
            path = None
        if path is None:
            return "no matrix"
        return "current" if optional_file_sha256(path) == plan.matrix_sha256 else "stale"


def _wanted(words: Sequence[str], *, statuses: Sequence[str], failed: bool) -> bool:
    """Whether a polar (or a point) with these words passes ``--status`` and ``--failed``."""
    if failed and not any(word.startswith("FAILED") for word in words):
        return False
    if not statuses:
        return True
    return any(_matches(word, wanted) for word in words for wanted in statuses)


def _matches(word: str, wanted: str) -> bool:
    return word.startswith(wanted[:-1]) if wanted.endswith("*") else word == wanted


def _polar_name(entries: Sequence[_Entry]) -> str:
    """Return the polar's recorded sweep name, or for a polar only planned the one implied."""
    for entry in entries:
        if entry.record is not None and entry.record.sweep_name:
            return entry.record.sweep_name
    first = entries[0]
    polar = first.name
    for axis in _varying([entry.values for entry in entries]):
        key = POINT_AXIS_KEYS.get(axis)
        if key in POINT_NAME_FIELDS and axis in first.values:
            token = name_field(key, float(first.values[axis]))
            polar = polar.replace(token, POINT_NAME_FIELDS[key].code + SWEEP_NAME_VALUE, 1)
    return polar


def _varying(values: Sequence[Mapping[str, float]]) -> list[str]:
    seen: dict[str, set[float]] = {}
    for point in values:
        for key, value in point.items():
            seen.setdefault(key, set()).add(value)
    return [key for key, found in seen.items() if len(found) > 1]


def _swept(values: Sequence[Mapping[str, float]], polar: str) -> str:
    """Return the variables the polar sweeps: those that vary, else those its name marks swept."""
    names = _varying(values)
    if not names:
        names = [_AXIS_OF_CODE.get(code, code) for code in _SWEPT_CODE.findall(polar)]
    return ", ".join(names) if names else "single point"


def _where(record: RunRecord) -> str:
    submission = record.submission
    if not submission:
        return "local"
    job = submission.get("job")
    if isinstance(job, Mapping) and job.get("label"):
        return str(job["label"])
    return "cluster"


def _point_row(stem: str, sim: str, entry: _Entry) -> dict[str, object]:
    record = entry.record
    if record is None:
        row: dict[str, object] = dict.fromkeys((*POINT_COLUMNS, "run_id"))
        row.update(sim=sim, point=entry.name, matrix=stem, status=PLANNED)
        return row
    marked = record.marked or {}
    return {
        "sim": sim,
        "point": entry.name,
        "matrix": stem,
        "status": entry.word,
        "was": marked.get("from"),
        "iterations": record.iterations,
        "residual": record.residual,
        "wall_s": record.wall_time_s,
        "build": record.fs_build or record.fs_version_requested,
        "where": _where(record),
        "run_id": record.run_id,
    }


def _read_records(path: Path) -> _Records:
    """Read the manifest's rows one by one, naming each row that cannot be read."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else []
    except (OSError, ValueError) as error:
        raise WorkspaceError(
            f"runs (CLI: --runs): the manifest {path} cannot be read as JSON: {error}. "
            "No row of it can be shown; restore it with `pyfs-matrix restore runs`."
        ) from error
    if not isinstance(raw, list):
        raise WorkspaceError(f"runs (CLI: --runs): the manifest {path} is not a list of rows")
    out = _Records(records=[], raw=[], notes=[], unreadable=[])
    for position, row in enumerate(raw, start=1):
        if not isinstance(row, dict):
            out.unreadable.append({"position": position, "run_id": None, "error": "not a row"})
            continue
        if row.get(DELETED_SIM_KEY) is not None:
            out.notes.append({"position": position, "deleted_sim": row[DELETED_SIM_KEY]})
            continue
        # A row read or not still says which point it recorded: an unreadable
        # row is named, never counted as a point the plan has not reached.
        out.raw.append(row)
        try:
            out.records.append(RunRecord.model_validate(row))
        except ValidationError as error:
            run_id = row.get("run_id")
            out.unreadable.append(
                {
                    "position": position,
                    "run_id": run_id if isinstance(run_id, str) else None,
                    "error": _validation_text(error),
                }
            )
    return out


def _read_plan(path: Path) -> _Plan:
    stem = path.parent.name
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        points: dict[str, dict[str, dict[str, float]]] = {}
        run_ids = []
        for point in payload["points"]:
            run_id = str(point["run_id"])
            run_ids.append(run_id)
            values = point.get("point") or {}
            points.setdefault(str(point["sim_id"]), {})[run_id.rsplit("/", 1)[-1]] = dict(values)
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        return _Plan(stem, {}, (), None, f"{type(error).__name__}: {error}")
    sha = payload.get("matrix_sha256")
    return _Plan(stem, points, tuple(run_ids), sha if isinstance(sha, str) else None, None)


def _read_products(path: Path) -> dict[str, Any]:
    """Read a post's product index; one that cannot be read reads as incomplete."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        payload = None
    if not isinstance(payload, dict):
        payload = {"complete": None, "provenance": {}}
    return {**payload, "_mtime": _mtime(path)}


def _sim_and_name(run_id: str) -> tuple[str, str]:
    """Return the simulation and point name of a planned run id ``<campaign>/sim_<id>/<name>``."""
    parts = run_id.split("/")
    sim = parts[1].removeprefix("sim_") if len(parts) > 2 else ""
    return sim, parts[-1]


def _entries(
    found: _Records, plans: Mapping[str, _Plan]
) -> tuple[tuple[_Entry, ...], list[dict[str, object]]]:
    """Every datapoint: the effective records, then the planned points no record carries."""
    plan_of_sim: dict[str, _Plan] = {}
    for plan in plans.values():
        for sim in plan.points:
            plan_of_sim.setdefault(sim, plan)
    planned = {sim: plan.points[sim] for sim, plan in plan_of_sim.items()}
    chosen = effective_points(found.records, planned=planned)
    entries = []
    for (sim, name), record in chosen.records.items():
        owner = plan_of_sim.get(sim)
        stem = record.matrix_stem or (owner.stem if owner is not None else "")
        entries.append(_Entry(sim, name, stem, dict(record.point), record))
    for plan in plans.values():
        # THE PLANNED POINTS NO RECORD CARRIES, by the rule's one home. A point
        # carried by an effective record of another campaign is that record's.
        for run_id in planned_points_without_record(plan.run_ids, found.raw):
            sim, name = _sim_and_name(run_id)
            if (sim, name) not in chosen.records:
                values = plan.points.get(sim, {}).get(name, {})
                entries.append(_Entry(sim, name, plan.stem, values, None))
    notes: list[dict[str, object]] = [
        {"run_id": note.run_id, "kind": "refused continuation", "error": note.error}
        for note in chosen.notes
    ]
    return tuple(entries), notes


def read_ledger(root: str | Path, *, runs: str | None = None) -> Ledger:
    """Read one snapshot of a workspace's records, writing nothing (FR-383, FR-388).

    Parameters
    ----------
    root : str or Path
        The workspace root.
    runs : str, optional
        Another manifest in the root to read in place of ``runs.json``.

    Returns
    -------
    Ledger
        The snapshot; its methods return plain dictionaries.

    Raises
    ------
    WorkspaceError
        When the manifest is not JSON at all, or ``runs`` does not name a file
        of the root (:class:`~pyflightstream.workspace.naming.RunsManifestError`).

    Examples
    --------
    >>> ledger = read_ledger("campaign")  # doctest: +SKIP
    >>> ledger.status(sims=["2006"])  # doctest: +SKIP
    """
    base = Path(root).resolve()
    read_at = datetime.now(UTC).isoformat(timespec="seconds")
    manifest = resolve_manifest(base, runs)
    found = _read_records(manifest)
    sources: dict[str, str] = {}
    if manifest.is_file():
        sources[manifest.relative_to(base).as_posix()] = _mtime(manifest)
    plans: dict[str, _Plan] = {}
    products: dict[str, dict[str, Any]] = {}
    post = base / "post"
    for folder in sorted(post.iterdir()) if post.is_dir() else []:
        plan_file, products_file = folder / _PLAN_FILE, folder / _PRODUCTS_FILE
        if plan_file.is_file():
            plans[folder.name] = _read_plan(plan_file)
            sources[plan_file.relative_to(base).as_posix()] = _mtime(plan_file)
        if products_file.is_file():
            products[folder.name] = _read_products(products_file)
            sources[products_file.relative_to(base).as_posix()] = _mtime(products_file)
    entries, refused = _entries(found, plans)
    return Ledger(
        root=base,
        manifest=manifest,
        read_at=read_at,
        sources=sources,
        unreadable=tuple(found.unreadable),
        notes=tuple(found.notes + refused),
        _entries=entries,
        _plans=plans,
        _records=tuple(found.records),
        _products=products,
    )
