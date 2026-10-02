"""Archive-aware ledger queries, isolated from the present-state reader.

Pipeline role: read historical records and compare their recorded identities.
Only history and diff enter this module. Archives are inspected in place,
including compacted simulations; no file is extracted or rewritten (FR-383).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import zipfile
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import ValidationError

from pyflightstream.workspace import RunRecord, WorkspaceError
from pyflightstream.workspace._effective import _points_of
from pyflightstream.workspace._script_comparison import _compare_scripts, _drift

if TYPE_CHECKING:
    from pyflightstream.workspace.ledger import Ledger

_STAMP = re.compile(r"\d{8}-\d{6}(?:\.\d+)?(?:-[A-Za-z0-9_-]+)?")


def _files(folder: Path) -> Iterator[Path]:
    """Walk ordinary directories only; never descend into a reparse point."""
    if not folder.is_dir() or _linked(folder):
        return
    for current, dirs, files in os.walk(folder, followlinks=False):
        here = Path(current)
        dirs[:] = sorted(name for name in dirs if not _linked(here / name))
        yield from (here / name for name in sorted(files) if not _linked(here / name))


def _linked(path: Path) -> bool:
    info = path.lstat()
    return path.is_symlink() or bool(
        getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
    )


def _stamp(name: str) -> str | None:
    match = _STAMP.search(name)
    return match.group() if match else None


def _documents(ledger: Ledger) -> Iterator[tuple[str, str | None, bytes]]:
    """Read archived manifests and JSON records inside datapoint archives."""
    for path in _files(ledger.root / "archive"):
        if path.suffix == ".json" and path.name.startswith(ledger.manifest.stem + "-"):
            yield path.relative_to(ledger.root).as_posix(), _stamp(path.name), path.read_bytes()
    for path in _files(ledger.root / "sims"):
        name = path.relative_to(ledger.root).as_posix()
        if path.suffix == ".json" and "/archive/" in name:
            yield name, _stamp(name.split("/archive/", 1)[1]), path.read_bytes()
        elif path.suffix == ".zip":
            yield from _zip_documents(path, name)


def _zip_documents(path: Path, name: str) -> Iterator[tuple[str, str | None, bytes]]:
    try:
        with zipfile.ZipFile(path) as archive:
            for member in sorted(archive.namelist()):
                if "/archive/" in member and member.endswith(".json"):
                    yield f"{name}!{member}", _stamp(member), archive.read(member)
    except (OSError, zipfile.BadZipFile) as error:
        raise WorkspaceError(
            f"target (CLI: history): cannot read archive {name}: {error}"
        ) from error


def _rows(payload: bytes, source: str) -> list[dict[str, Any]]:
    try:
        document = json.loads(payload)
    except (ValueError, UnicodeDecodeError) as error:
        return [{"source": source, "position": None, "run_id": None, "error": str(error)}]
    if isinstance(document, dict):
        document = document.get("runs", [document] if "run_id" in document else [])
    if not isinstance(document, list):
        return [{"source": source, "position": None, "run_id": None, "error": "not a list"}]
    rows = []
    for position, row in enumerate(document, 1):
        if isinstance(row, dict) and "deleted_sim" in row:
            continue
        try:
            record = RunRecord.model_validate(row)
        except ValidationError as error:
            rows.append(
                {
                    "source": source,
                    "position": position,
                    "run_id": row.get("run_id") if isinstance(row, dict) else None,
                    "error": str(error),
                }
            )
        else:
            rows.append({"record": record.model_dump(mode="json"), "position": position})
    return rows


def _matches(record: Mapping[str, Any], target: str) -> bool:
    run_id = str(record.get("run_id", ""))
    sim = str(record.get("sim_id", ""))
    name = str(record.get("point_name") or run_id.rsplit("/", 1)[-1])
    return target in (sim, f"sim_{sim}", name, f"sim_{sim}/{name}", run_id)


def _point_records(record: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Use the manifest model's expansion, preserving every historical attempt."""
    parsed = RunRecord.model_validate(record)
    return [point.model_dump(mode="json") for point in _points_of(parsed, {})]


def _select(record: dict[str, Any], target: str) -> list[dict[str, Any]]:
    if _matches(record, target):
        return [record]
    return [point for point in _point_records(record) if _matches(point, target)]


def _current(ledger: Ledger) -> list[dict[str, Any]]:
    # The ledger owns validation and present-manifest selection. Do not read it again.
    return ledger.records()


def history_rows(ledger: Ledger, target: str) -> list[dict[str, Any]]:
    """Build history rows from a ledger and archived copies, with explicit diagnostics."""
    rows: list[dict[str, Any]] = []
    for source, stamp, payload in _documents(ledger):
        for item in _rows(payload, source):
            if "record" not in item:
                rows.append(item)
                continue
            for record in _select(item["record"], target):
                rows.append(_history_row(ledger, record, source, stamp))
    source = ledger.manifest.relative_to(ledger.root).as_posix()
    for record in _current(ledger):
        rows.extend(_history_row(ledger, item, source, None) for item in _select(record, target))
    return rows


def _history_row(
    ledger: Ledger, record: dict[str, Any], source: str, stamp: str | None
) -> dict[str, Any]:
    return {
        "run_id": record["run_id"],
        "archive_stamp": stamp,
        "source": source,
        "continues": record.get("continues"),
        "status": record.get("status"),
        "sim_folders": ledger.sim_folders(str(record["sim_id"])),
        "datapoint_archives": _archive_locations(ledger, record),
        "record": record,
    }


def _archive_locations(ledger: Ledger, record: dict[str, Any]) -> list[dict[str, str]]:
    """List output archives even when they contain no JSON record document."""
    point = str(record.get("point_name") or record["run_id"].rsplit("/", 1)[-1])
    marker = f"datapoints/DP-{point}/archive/"
    found = set()
    for folder in ledger.sim_folders(str(record["sim_id"])):
        for name in _member_names(ledger.root, folder):
            if marker in name:
                prefix, rest = name.split(marker, 1)
                stamp = rest.split("/", 1)[0]
                found.add((stamp, prefix + marker + stamp))
    return [{"stamp": stamp, "path": path} for stamp, path in sorted(found)]


def _member_names(root: Path, folder: str) -> Iterator[str]:
    path = root / folder
    if path.suffix == ".zip":
        with zipfile.ZipFile(path) as archive:
            yield from (f"{folder}!{member}" for member in sorted(archive.namelist()))
    else:
        yield from (file.relative_to(root).as_posix() for file in _files(path))


def _resolve(ledger: Ledger, selector: str) -> dict[str, Any]:
    target, sep, stamp = selector.rpartition("@")
    target = target if sep else selector
    rows = [
        row
        for row in history_rows(ledger, target)
        if "record" in row
        and row["run_id"] == target
        and row["archive_stamp"] == (stamp if sep else None)
    ]
    unique = {json.dumps(row["record"], sort_keys=True): row for row in rows}
    if len(unique) != 1:
        reason = "no recorded run" if not unique else "several archived copies; use the full stamp"
        raise WorkspaceError(f"run (CLI: diff): {selector!r} names {reason}")
    return next(iter(unique.values()))


def _flatten(value: Mapping[str, Any], prefix: str = "") -> dict[str, Any]:
    flat = {}
    for key, item in value.items():
        name = f"{prefix}.{key}" if prefix else key
        if isinstance(item, dict) and item:
            flat.update(_flatten(item, name))
        else:
            flat[name] = item
    return flat


def diff_rows(ledger: Ledger, run_a: str, run_b: str) -> list[dict[str, Any]]:
    """Compare every recorded field and the scripts whose digests establish identity."""
    left, right = _resolve(ledger, run_a), _resolve(ledger, run_b)
    a, b = _flatten(left["record"]), _flatten(right["record"])
    rows = [
        {
            "field": key,
            "a": a.get(key),
            "b": b.get(key),
            "a_present": key in a,
            "b_present": key in b,
        }
        for key in sorted(a.keys() | b.keys())
        if a.get(key) != b.get(key) or (key in a) != (key in b)
    ]
    rows.extend(_script_diff(ledger, left, right))
    return rows


def _script_candidates(ledger: Ledger, row: Mapping[str, Any]) -> Iterator[tuple[str, bytes]]:
    record = row["record"]
    name = str(record.get("script_path") or "").replace("\\", "/").rsplit("/", 1)[-1]
    if not name:
        return
    for folder in ledger.sim_folders(str(record["sim_id"])):
        path = ledger.root / folder
        if path.suffix == ".zip":
            with zipfile.ZipFile(path) as archive:
                for member in sorted(archive.namelist()):
                    if member.rsplit("/", 1)[-1] == name:
                        yield f"{folder}!{member}", archive.read(member)
        else:
            for candidate in _files(path):
                if candidate.name == name:
                    yield candidate.relative_to(ledger.root).as_posix(), candidate.read_bytes()
    recorded = ledger.root / str(record.get("script_path") or "")
    if recorded.is_file() and recorded.resolve().is_relative_to(ledger.root):
        yield recorded.relative_to(ledger.root).as_posix(), recorded.read_bytes()


def _script(ledger: Ledger, row: Mapping[str, Any]) -> tuple[str | None, str | None]:
    digest = row["record"].get("script_sha256")
    for source, payload in _script_candidates(ledger, row):
        if digest and hashlib.sha256(payload).hexdigest() == digest:
            return source, payload.decode("utf-8")
    return None, None


def _script_diff(
    ledger: Ledger, left: Mapping[str, Any], right: Mapping[str, Any]
) -> list[dict[str, Any]]:
    path_a, a = _script(ledger, left)
    path_b, b = _script(ledger, right)
    if a is None or b is None:
        return [
            {
                "field": "script_comparison",
                "a": path_a,
                "b": path_b,
                "detail": "unavailable: no script matching the recorded digest",
            }
        ]
    compared = _compare_scripts(b, a, ledger.root)
    if compared.same:
        return []
    inputs = sorted(
        set(left["record"].get("inputs_sha256", {})) | set(right["record"].get("inputs_sha256", {}))
    )
    inputs = [name.removeprefix("inputs/") for name in inputs]
    return [
        {
            "field": "script_comparison",
            "a": path_a,
            "b": path_b,
            "detail": _drift(compared, ledger.root / "inputs", inputs, limit=None),
        }
    ]
