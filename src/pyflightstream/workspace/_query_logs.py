"""Read activity, post, storage and additional registers for query verbs.

Pipeline role: plain-dictionary readers below run and post. No writer, lock,
scheduler or optional table dependency participates in these queries.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from pyflightstream._errors import PyflightstreamWarning, warn
from pyflightstream.workspace import WorkspaceError
from pyflightstream.workspace._query_files import _files, _groups, _json, _text, matrix_stem
from pyflightstream.workspace.storage import read_storage_calls

if TYPE_CHECKING:
    from pyflightstream.workspace.ledger import Ledger


def _activity(ledger: Ledger) -> list[dict[str, Any]]:
    paths = {
        path.relative_to(ledger.root).as_posix()
        for path in ledger.root.glob("logs/activity.log.jsonl")
    }
    for sim in {str(row["sim"]) for row in ledger.points()}:
        paths.update(
            path
            for name, path in _files(ledger, sim).items()
            if name.endswith("activity.log.jsonl")
        )
    rows = []
    skipped: list[str] = []
    for path in sorted(paths):
        for number, line in enumerate(_text(ledger, path).splitlines(), 1):
            if not line.strip():
                continue
            # A TORN OR MALFORMED LINE IS SET ASIDE AND NAMED (PFS-2081.25): an append-only
            # log a process stopped while writing ends in half a line, and that line used
            # to refuse the whole query. Every other event is still read.
            try:
                row = json.loads(line)
            except ValueError as error:
                skipped.append(f"{path} line {number} ({error})")
                continue
            if not isinstance(row, dict):
                skipped.append(f"{path} line {number} (an event is a JSON object)")
                continue
            if _stamp(row) and _parsed(_stamp(row)) is None:
                skipped.append(
                    f"{path} line {number} (timestamp {_stamp(row)!r} is not an ISO time)"
                )
                continue
            rows.append({**row, "source": path})
    if skipped:
        warn(
            f"{len(skipped)} activity line(s) could not be read and are left out of the "
            f"query: {'; '.join(skipped)}. The other events are shown.",
            PyflightstreamWarning,
            stacklevel=2,
        )
    return sorted(rows, key=_chronology)


def _stamp(row: dict[str, Any]) -> str:
    return str(row.get("timestamp") or row.get("at") or "")


def _chronology(row: dict[str, Any]) -> datetime:
    """Order a row by its stamp; a row with none, or a stamp that is no ISO time, sorts first."""
    parsed = _parsed(_stamp(row)) if _stamp(row) else None
    return parsed if parsed is not None else datetime.min.replace(tzinfo=UTC)


def _time(text: str) -> datetime:
    value = datetime.fromisoformat(text.replace("Z", "+00:00"))
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _parsed(text: str) -> datetime | None:
    """Return the time a stamp states, or None when it is no ISO time."""
    try:
        return _time(text)
    except ValueError:
        return None


def _at_or_after(row: dict[str, Any], cutoff: datetime) -> bool:
    """Whether a row's stamp is a time at or after ``cutoff``; no stamp or a bad one is not."""
    parsed = _parsed(_stamp(row)) if _stamp(row) else None
    return parsed is not None and parsed >= cutoff


def _since(text: str | None) -> datetime | None:
    if text is None:
        return None
    duration = re.fullmatch(r"(\d+(?:\.\d+)?)([smhdw])", text)
    if duration:
        units = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}
        try:
            return datetime.now(UTC) - timedelta(seconds=float(duration[1]) * units[duration[2]])
        except OverflowError as error:
            raise WorkspaceError(
                f"since (CLI: --since) {text!r} is a duration too long to count back from now"
            ) from error
    try:
        return _time(text)
    except ValueError as error:
        raise WorkspaceError(
            "since (CLI: --since) needs an ISO time or duration such as 2h"
        ) from error


def _mentions(row: dict[str, Any], token: str) -> bool:
    """Match an id on token boundaries, including recorded paths and nested details."""
    text = json.dumps(row, ensure_ascii=False).replace("\\\\", "/")
    # A hyphen continues an id (PFS-2094.043): sim ids may hold one, so sim_20 is not
    # read inside sim_20-b.
    return re.search(r"(?<![\w-])" + re.escape(token) + r"(?![\w-])", text) is not None


def _sim_matches(row: dict[str, Any], sim: str) -> bool:
    # A row's own ids decide before its text (PFS-2094.043); a `sims` list of records
    # (a storage call's) is read through its children instead.
    if isinstance(row.get("sim_id"), str | int):
        return str(row["sim_id"]) == sim
    sims = row.get("sims")
    if isinstance(sims, list) and sims and all(isinstance(s, str | int) for s in sims):
        return sim in [str(s) for s in sims]
    if _mentions(row, f"sim_{sim}"):
        return True
    return any(_sim_matches(child, sim) for child in _children(row))


def _children(row: dict[str, Any]) -> list[dict[str, Any]]:
    nested = []
    for value in row.values():
        if isinstance(value, dict):
            nested.append(value)
        elif isinstance(value, list):
            nested.extend(item for item in value if isinstance(item, dict))
    return nested


def _problem(row: dict[str, Any]) -> bool:
    if any(row.get(key) for key in ("problems", "warnings", "error", "exception_type", "refused")):
        return True
    words = [str(row.get(key, "")) for key in ("event", "status", "outcome", "severity")]
    outcomes = row.get("outcomes")
    if isinstance(outcomes, dict):
        words.extend(str(key) for key, count in outcomes.items() if count)
    elif isinstance(outcomes, list):
        words.extend(value for value in outcomes if isinstance(value, str))
    failed = any(
        word.upper().startswith(("FAILED", "ERROR", "WARNING", "CANCELLED")) for word in words
    )
    return failed or any(_problem(child) for child in _children(row))


def _open_stages(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    pending: dict[tuple[str, ...], list[dict[str, Any]]] = {}
    for row in rows:
        key = tuple(
            str(row.get(k, "")) for k in ("source", "stage", "run_id", "sim_id", "datapoint")
        )
        if row.get("event") == "started":
            pending.setdefault(key, []).append(row)
        elif row.get("event") in {"finished", "failed", "cancelled"} and pending.get(key):
            pending[key].pop()
    return sorted((row for group in pending.values() for row in group), key=_chronology)


def _select_logs(
    rows: Sequence[dict[str, Any]],
    *,
    sims: Sequence[str] = (),
    run: str | None = None,
    stage: str | None = None,
    since: str | None = None,
    problems: bool = False,
    open_only: bool = False,
) -> list[dict[str, Any]]:
    """Keep the log rows that match every filter given.

    Parameters
    ----------
    rows : Sequence[dict[str, Any]]
        The log rows, in the order read.
    sims : Sequence[str], optional
        Keep rows of these simulations; empty keeps all.
    run : str or None, optional
        Keep rows that mention this run id.
    stage : str or None, optional
        Keep rows of this stage, action or command.
    since : str or None, optional
        Keep rows stamped at or after this time.
    problems : bool, optional
        Keep only rows that record a problem.
    open_only : bool, optional
        Keep only rows of stages that are still open.

    Returns
    -------
    list[dict[str, Any]]
        The rows kept, in their original order.
    """
    cutoff = _since(since)
    candidates = _open_stages(rows) if open_only else rows
    return [
        row
        for row in candidates
        if (not sims or any(_sim_matches(row, sim) for sim in sims))
        and (run is None or _mentions(row, run))
        and (stage is None or row.get("stage", row.get("action", row.get("command"))) == stage)
        and (not problems or _problem(row))
        and (cutoff is None or _at_or_after(row, cutoff))
    ]


def _post_rows(ledger: Ledger, matrix: str) -> list[dict[str, Any]]:
    path = ledger.root / "post" / matrix_stem(matrix) / "post.log.json"
    document = _json(path, {"records": []})
    if not isinstance(document, dict) or not isinstance(document.get("records"), list):
        raise WorkspaceError(f"post (CLI: --post): {path} needs an object with records")
    if any(not isinstance(row, dict) for row in document["records"]):
        raise WorkspaceError(f"post (CLI: --post): {path} has a non-object record")
    return document["records"]


def _post_groups(ledger: Ledger, matrix: str, sims: Sequence[str] = ()) -> list[dict[str, Any]]:
    records = _post_rows(ledger, matrix)
    return _groups([row for row in records if not sims or any(_sim_matches(row, s) for s in sims)])


def _storage(ledger: Ledger) -> list[dict[str, Any]]:
    """Read the recorded storage calls of a workspace in chronological order.

    Parameters
    ----------
    ledger : Ledger
        The workspace ledger.

    Returns
    -------
    list[dict[str, Any]]
        The storage call rows, oldest first.
    """
    return sorted(read_storage_calls(ledger.root), key=_chronology)


def _additional(ledger: Ledger) -> list[dict[str, Any]]:
    rows = _json(ledger.root / "additional.json", [])
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise WorkspaceError(
            "additional (CLI: --additional): additional.json needs a list of objects"
        )
    return rows
