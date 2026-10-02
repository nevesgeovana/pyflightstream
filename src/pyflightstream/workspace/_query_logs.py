"""Read activity, post, storage and additional registers for query verbs.

Pipeline role: plain-dictionary readers below run and post. No writer, lock,
scheduler or optional table dependency participates in these queries.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from pyflightstream.workspace._query_files import _files, _groups, _json, _text
from pyflightstream.workspace.ledger import Ledger, matrix_stem
from pyflightstream.workspace.storage import read_storage_calls


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
    for path in sorted(paths):
        for number, line in enumerate(_text(ledger, path).splitlines(), 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
                if not isinstance(row, dict):
                    raise ValueError("event must be an object")
            except ValueError as error:
                raise ValueError(
                    f"workspace (CLI: --workspace): {path} line {number}: {error}"
                ) from error
            rows.append({**row, "source": path})
    return sorted(rows, key=_chronology)


def _stamp(row: dict[str, Any]) -> str:
    return str(row.get("timestamp") or row.get("at") or "")


def _chronology(row: dict[str, Any]) -> datetime:
    return _time(_stamp(row)) if _stamp(row) else datetime.min.replace(tzinfo=UTC)


def _time(text: str) -> datetime:
    value = datetime.fromisoformat(text.replace("Z", "+00:00"))
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _since(text: str | None) -> datetime | None:
    if text is None:
        return None
    duration = re.fullmatch(r"(\d+(?:\.\d+)?)([smhdw])", text)
    if duration:
        units = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}
        return datetime.now(UTC) - timedelta(seconds=float(duration[1]) * units[duration[2]])
    try:
        return _time(text)
    except ValueError as error:
        raise ValueError("since (CLI: --since) needs an ISO time or duration such as 2h") from error


def _mentions(row: dict[str, Any], token: str) -> bool:
    """Match an id on token boundaries, including recorded paths and nested details."""
    text = json.dumps(row, ensure_ascii=False).replace("\\\\", "/")
    return re.search(r"(?<![\w])" + re.escape(token) + r"(?![\w])", text) is not None


def _sim_matches(row: dict[str, Any], sim: str) -> bool:
    if str(row.get("sim_id", "")) == sim:
        return True
    sims = row.get("sims", [])
    if isinstance(sims, list) and sim in [str(s) for s in sims]:
        return True
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
    words.extend(str(key) for key, count in (row.get("outcomes") or {}).items() if count)
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
    cutoff = _since(since)
    candidates = _open_stages(rows) if open_only else rows
    return [
        row
        for row in candidates
        if (not sims or any(_sim_matches(row, sim) for sim in sims))
        and (run is None or _mentions(row, run))
        and (stage is None or row.get("stage", row.get("action", row.get("command"))) == stage)
        and (not problems or _problem(row))
        and (cutoff is None or bool(_stamp(row)) and _time(_stamp(row)) >= cutoff)
    ]


def _post_rows(ledger: Ledger, matrix: str) -> list[dict[str, Any]]:
    path = ledger.root / "post" / matrix_stem(matrix) / "post.log.json"
    document = _json(path, {"records": []})
    if not isinstance(document, dict) or not isinstance(document.get("records"), list):
        raise ValueError(f"post (CLI: --post): {path} needs an object with records")
    if any(not isinstance(row, dict) for row in document["records"]):
        raise ValueError(f"post (CLI: --post): {path} has a non-object record")
    return document["records"]


def _post_groups(ledger: Ledger, matrix: str, sims: Sequence[str] = ()) -> list[dict[str, Any]]:
    records = _post_rows(ledger, matrix)
    return _groups([row for row in records if not sims or any(_sim_matches(row, s) for s in sims)])


def _storage(ledger: Ledger) -> list[dict[str, Any]]:
    return sorted(read_storage_calls(ledger.root), key=_chronology)


def _additional(ledger: Ledger) -> list[dict[str, Any]]:
    rows = _json(ledger.root / "additional.json", [])
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError("additional (CLI: --additional): additional.json needs a list of objects")
    return rows
