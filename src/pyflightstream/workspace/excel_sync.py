"""Name-based optional Excel synchronization; no solver or live Excel dependency."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import uuid
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal

from pyflightstream._errors import PyflightstreamError
from pyflightstream.cases.matrix import (
    MATRIX_COLUMNS,
)
from pyflightstream.cases.matrix import (
    RECOGNIZED_MATRIX_LAYOUTS as SUPPORTED_LAYOUTS,
)

__all__ = [
    "ApplyResult",
    "Cell",
    "Change",
    "DictionaryEntry",
    "ExcelSyncError",
    "SUPPORTED_COLUMNS",
    "SyncPreview",
    "WorkbookSnapshot",
    "apply_preview",
    "dictionary_mapping",
    "preview_sync",
    "three_way_action",
]

SUPPORTED_COLUMNS = tuple(dict.fromkeys(name for layout in SUPPORTED_LAYOUTS for name in layout))


class ExcelSyncError(PyflightstreamError, ValueError):
    """A preview or apply cannot preserve an unambiguous matrix meaning."""


@dataclass(frozen=True)
class Cell:
    """One literal or formula captured from the current workbook."""

    value: str = ""
    formula: bool = False


@dataclass(frozen=True)
class DictionaryEntry:
    """An exact ASCII-to-Excel name mapping or an Excel-only column declaration."""

    ascii_name: str
    excel_header: str
    status: str = "MAPPED"


@dataclass
class WorkbookSnapshot:
    """Values captured from the live workbook, including unsaved edits.

    Rows follow headers in their current order. Custom cells and formulas stay
    opaque. Baseline keys are JSON [MATRIX, POL, ASCII_NAME] arrays.
    """

    headers: list[str]
    rows: list[list[Cell]]
    dictionary: list[DictionaryEntry]
    baseline: dict[str, str] = field(default_factory=dict)

    def digest(self) -> str:
        """Hash every captured cell, mapping and baseline value for freshness."""
        return _digest(json.dumps(asdict(self), sort_keys=True, ensure_ascii=False).encode())


@dataclass(frozen=True)
class Change:
    """One visible preview decision with its identity and before/after values."""

    action: str
    matrix: str
    pol: str
    ascii_name: str
    excel_header: str
    before: str
    after: str
    row: int = -1
    column: int = -1
    detail: str = ""


@dataclass
class SyncPreview:
    """A captured synchronization batch that must be reviewed before applying."""

    direction: Literal["read", "write"]
    workspace: str
    workbook_digest: str
    file_digests: dict[str, str | None]
    changes: list[Change]
    mappings: list[DictionaryEntry]
    headers: list[str]
    baseline: dict[str, str]
    file_outputs: dict[str, str] = field(default_factory=dict)
    token: str = field(default_factory=lambda: uuid.uuid4().hex)
    selection: list[str] | None = None

    @property
    def counts(self) -> dict[str, int]:
        """Count actual preview actions, including conflicts and Excel-only columns."""
        return dict(Counter(change.action for change in self.changes))

    @property
    def applicable(self) -> bool:
        """Return whether the batch contains no invalid or conflicting changes."""
        return not any(change.action in ("INVALID", "CONFLICT") for change in self.changes)


@dataclass
class ApplyResult:
    """Only cell deltas go back to VBA; the open workbook is never replaced."""

    changes: list[Change]
    mappings: list[DictionaryEntry]
    headers: list[str]
    baseline: dict[str, str]
    written: list[str] = field(default_factory=list)
    backups: dict[str, str] = field(default_factory=dict)
    error: str = ""


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _key(matrix: str, pol: str, name: str) -> str:
    return json.dumps([matrix, pol, name], ensure_ascii=False, separators=(",", ":"))


def _matrix_path(workspace: Path, name: str, direction: str) -> Path:
    """Return the file of the matrix ``name``, by the workspace's one lookup (FR-310).

    Read, it is the home that holds the name, the root's when both hold the
    same bytes, and ``inputs/matrices/<name>`` when neither does; written, it
    is the home that holds it, or ``inputs/matrices/`` for a new file, and a
    name held in both homes is refused, since writing one would leave the
    other stale. Different bytes in both homes are refused either way.
    """
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_. -]*\.fs", name) or ".." in name:
        raise ExcelSyncError(f"MATRIX {name!r}: use an .fs filename, without directories or '..'.")
    from pyflightstream.workspace import WorkspaceError
    from pyflightstream.workspace._matrix_homes import matrix_path, matrix_to_write

    try:
        if direction == "write":
            return matrix_to_write(workspace, name)
        found = matrix_path(workspace, name)
    except WorkspaceError as error:
        raise ExcelSyncError(f"MATRIX {name!r}: {error}") from error
    return matrix_to_write(workspace, name) if found == Path(name) else found


def _every_matrix_name(root: Path) -> list[str]:
    """Every matrix name of the workspace, one per stem over both homes (FR-310)."""
    from pyflightstream.workspace import WorkspaceError
    from pyflightstream.workspace._matrix_homes import every_matrix

    try:
        return sorted(path.name for path in every_matrix(root))
    except WorkspaceError as error:
        raise ExcelSyncError(str(error)) from error


def dictionary_mapping(snapshot: WorkbookSnapshot) -> dict[str, str]:
    """Return the validated ASCII-to-Excel mapping, without guessing names or positions.

    Parameters
    ----------
    snapshot : WorkbookSnapshot
        The workbook snapshot.

    Returns
    -------
    dict of str to str
        ASCII name to Excel header.

    Raises
    ------
    ExcelSyncError
        If the Runs headers are blank, repeated or narrower than a row, or the Dictionary is
        ambiguous, misses MATRIX or POL, or names a field the matrix reader does not support.
    """
    if any(not header.strip() for header in snapshot.headers):
        raise ExcelSyncError("Runs contains a blank header; name every column before Preview.")
    if len(set(snapshot.headers)) != len(snapshot.headers):
        raise ExcelSyncError("Runs has duplicate headers; each column must have one unique name.")
    mappings: dict[str, str] = {}
    mapped_headers: set[str] = set()
    for entry in snapshot.dictionary:
        if entry.status == "EXCEL ONLY":
            if entry.ascii_name:
                raise ExcelSyncError(
                    f"Dictionary {entry.excel_header!r}: EXCEL ONLY must have an empty ASCII_NAME."
                )
            if entry.excel_header not in snapshot.headers or entry.excel_header in mapped_headers:
                raise ExcelSyncError(
                    f"Dictionary EXCEL ONLY header {entry.excel_header!r} is absent or repeated."
                )
            mapped_headers.add(entry.excel_header)
            continue
        if entry.status != "MAPPED":
            raise ExcelSyncError(
                f"Dictionary status {entry.status!r}; accepted: MAPPED or EXCEL ONLY."
            )
        if entry.ascii_name not in (*SUPPORTED_COLUMNS, "MATRIX"):
            raise ExcelSyncError(
                f"Dictionary ASCII_NAME {entry.ascii_name!r} is unsupported by this matrix reader."
            )
        if not entry.excel_header or entry.excel_header not in snapshot.headers:
            raise ExcelSyncError(
                f"Dictionary header {entry.excel_header!r} is absent from Runs; "
                "use an exact header."
            )
        if entry.ascii_name in mappings or entry.excel_header in mapped_headers:
            raise ExcelSyncError(
                "Dictionary mapping is ambiguous; ASCII_NAME and EXCEL_HEADER must be one-to-one."
            )
        mappings[entry.ascii_name] = entry.excel_header
        mapped_headers.add(entry.excel_header)
    if not {"MATRIX", "POL"} <= mappings.keys():
        raise ExcelSyncError(
            "Dictionary must map both MATRIX and POL; their pair identifies each row."
        )
    if any(len(row) != len(snapshot.headers) for row in snapshot.rows):
        raise ExcelSyncError(
            "Runs row width differs from its header; capture every column before Preview."
        )
    return mappings


def _rows(
    snapshot: WorkbookSnapshot, mapping: dict[str, str]
) -> dict[tuple[str, str], tuple[int, dict[str, Cell]]]:
    indices = {name: snapshot.headers.index(header) for name, header in mapping.items()}
    rows = {}
    for index, cells in enumerate(snapshot.rows):
        if all(not cell.value and not cell.formula for cell in cells):
            continue
        record = {name: cells[column] for name, column in indices.items()}
        identity = (record["MATRIX"].value.casefold(), record["POL"].value)
        if not all(identity) or any(record[name].formula for name in ("MATRIX", "POL")):
            raise ExcelSyncError(
                f"Runs row {index + 2}: MATRIX and POL need nonempty text values, not formulas."
            )
        if identity in rows:
            raise ExcelSyncError(
                f"Runs repeats MATRIX/POL {identity!r}; fix duplicate row identities."
            )
        rows[identity] = (index, record)
    return rows


@dataclass
class _Matrix:
    lines: list[str]
    records: dict[str, dict[str, str]]
    locations: dict[str, int]
    newline: str
    bom: str = ""
    columns: tuple[str, ...] = MATRIX_COLUMNS

    def render(self, updates: dict[str, dict[str, str]]) -> str:
        lines = list(self.lines)
        for pol, values in updates.items():
            if pol in self.locations:
                position = self.locations[pol]
                old = lines[position]
                ending = "\r\n" if old.endswith("\r\n") else "\n" if old.endswith("\n") else ""
                parts = old.rstrip("\r\n").split("|")
                for name, value in values.items():
                    index = self.columns.index(name)
                    if parts[index].strip() == value:
                        continue
                    leading = parts[index][: len(parts[index]) - len(parts[index].lstrip())]
                    trailing = parts[index][len(parts[index].rstrip()) :]
                    parts[index] = leading + value + trailing
                lines[position] = "|".join(parts) + ending
            else:
                if lines and not lines[-1].endswith(("\r", "\n")):
                    lines[-1] += self.newline
                lines.append(
                    " | ".join(values.get(name, "") for name in self.columns) + self.newline
                )
        return self.bom + "".join(lines)


def _parse_matrix(raw: bytes, name: str) -> _Matrix:
    text = raw.decode("utf-8-sig")
    lines = text.splitlines(keepends=True)
    header_seen = False
    records: dict[str, dict[str, str]] = {}
    locations = {}
    columns: tuple[str, ...] = MATRIX_COLUMNS
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "|" not in line:
            continue
        fields = [value.strip() for value in line.rstrip("\r\n").split("|")]
        if not header_seen:
            if tuple(fields) not in SUPPORTED_LAYOUTS:
                raise ExcelSyncError(
                    f"{name}: unsupported matrix schema; "
                    "use a recognized current or legacy ASCII header."
                )
            columns = tuple(fields)
            header_seen = True
            continue
        if all(not value or set(value) <= {"-", ":", "+"} for value in fields):
            continue
        if len(fields) != len(columns):
            raise ExcelSyncError(
                f"{name} line {index + 1}: {len(fields)} cells, expected {len(columns)}."
            )
        record = dict(zip(columns, fields, strict=True))
        pol = record["POL"]
        if not pol or pol in records:
            raise ExcelSyncError(
                f"{name}: empty or duplicated POL {pol!r}; repair identity before Preview."
            )
        records[pol] = record
        locations[pol] = index
    if not header_seen:
        raise ExcelSyncError(f"{name}: no supported matrix header.")
    return _Matrix(
        lines,
        records,
        locations,
        "\r\n" if "\r\n" in text else "\n",
        "\ufeff" if raw.startswith(b"\xef\xbb\xbf") else "",
        columns,
    )


def _empty_matrix() -> _Matrix:
    return _Matrix([" | ".join(MATRIX_COLUMNS) + "\n"], {}, {}, "\n")


def three_way_action(base: str | None, source: str, target: str) -> str:
    """Keep target-only changes; refuse different changes on both sides.

    Parameters
    ----------
    base : str or None
        The value at the last synchronization; None when there was none.
    source : str
        The value on the side being read.
    target : str
        The value on the side being written.

    Returns
    -------
    str
        ``UNCHANGED``, ``UPDATE`` or ``CONFLICT``.
    """
    if source == target or (base is not None and source == base):
        return "UNCHANGED"
    if base is None:
        return "UPDATE" if target == "" else "CONFLICT"
    return "UPDATE" if target == base else "CONFLICT"


def preview_sync(
    workspace: str | Path,
    snapshot: WorkbookSnapshot,
    *,
    direction: Literal["read", "write"],
    matrices: list[str] | None = None,
) -> SyncPreview:
    """Capture an immutable review batch. This function writes nothing.

    Parameters
    ----------
    workspace : str or Path
        The workspace whose matrices are compared.
    snapshot : WorkbookSnapshot
        The workbook snapshot.
    direction : str
        ``read`` (matrices to workbook) or ``write`` (workbook to matrices).
    matrices : list of str, optional
        The matrix files to compare. None compares every matrix of the workspace when reading, and
        the matrices the Runs rows name when writing.

    Returns
    -------
    SyncPreview
        The batch: every change with its action, the mappings, the counts and a token.

    Raises
    ------
    ExcelSyncError
        If the direction is unknown, a selected matrix does not exist or is ambiguous, or a new
        field collides with an unmapped Runs column.
    """
    if direction not in ("read", "write"):
        raise ExcelSyncError(f"direction {direction!r}; accepted: read or write.")
    root = Path(workspace).resolve()
    mappings = dictionary_mapping(snapshot)
    sheet_rows = _rows(snapshot, mappings)
    selected = (
        matrices
        if matrices is not None
        else (
            _every_matrix_name(root)
            if direction == "read"
            else sorted({row[1]["MATRIX"].value for row in sheet_rows.values()})
        )
    )
    if len(selected) != len({name.casefold() for name in selected}):
        raise ExcelSyncError(
            "matrix selection repeats or ambiguously locates a filename; "
            "use unique MATRIX filenames."
        )
    loaded: dict[str, tuple[bytes | None, _Matrix]] = {}
    for filename in selected:
        path = _matrix_path(root, filename, direction)
        raw = path.read_bytes() if path.exists() else None
        if raw is None and direction == "read":
            raise ExcelSyncError(f"matrix {path} does not exist; choose an existing source.")
        loaded[filename] = (
            raw,
            _parse_matrix(raw, filename) if raw is not None else _empty_matrix(),
        )
    headers = list(snapshot.headers)
    additions = []
    if direction == "read":
        for name in dict.fromkeys(name for _, matrix in loaded.values() for name in matrix.columns):
            if name not in mappings:
                if name in headers:
                    raise ExcelSyncError(
                        f"new ASCII field {name} collides with an existing unmapped Runs column."
                    )
                mappings[name] = name
                headers.append(name)
                additions.append(DictionaryEntry(name, name))
    result = SyncPreview(
        direction,
        str(root),
        snapshot.digest(),
        {},
        [],
        additions,
        headers,
        dict(snapshot.baseline),
        selection=list(matrices) if matrices is not None else None,
    )
    for header in snapshot.headers:
        if header not in mappings.values():
            result.changes.append(
                Change(
                    "EXCEL ONLY",
                    "",
                    "",
                    "",
                    header,
                    "",
                    "",
                    detail="Preserved; excluded from ASCII.",
                )
            )
    next_row = len(snapshot.rows)
    for filename in selected:
        raw, matrix = loaded[filename]
        result.file_digests[filename] = _digest(raw) if raw is not None else None
        identities = (
            [(filename.casefold(), pol) for pol in matrix.records]
            if direction == "read"
            else [identity for identity in sheet_rows if identity[0] == filename.casefold()]
        )
        updates: dict[str, dict[str, str]] = {}
        for identity in identities:
            _, pol = identity
            sheet_index, sheet = sheet_rows.get(identity, (next_row, {}))
            if direction == "read" and not sheet:
                next_row += 1
            ascii_record = matrix.records.get(pol, {})
            new_target = not sheet if direction == "read" else not ascii_record
            if direction == "write" and new_target:
                missing = set(matrix.columns) - mappings.keys()
                if missing:
                    result.changes.append(
                        Change(
                            "INVALID",
                            filename,
                            pol,
                            "",
                            "",
                            "",
                            "",
                            detail=f"new row needs mappings for {sorted(missing)}",
                        )
                    )
                    continue
            for name, header in mappings.items():
                if name == "MATRIX":
                    if direction == "read" and not sheet:
                        result.changes.append(
                            Change(
                                "ADD",
                                filename,
                                pol,
                                name,
                                header,
                                "",
                                filename,
                                sheet_index,
                                headers.index(header),
                            )
                        )
                    continue
                if name not in ascii_record and direction == "read":
                    continue
                if name not in matrix.columns:
                    # A legacy-layout file has no such column. An Excel value
                    # for it is refused visibly rather than skipped: the
                    # preview shows every decision.
                    cell = sheet.get(name, Cell())
                    if direction == "write" and (cell.value or cell.formula):
                        result.changes.append(
                            Change(
                                "INVALID",
                                filename,
                                pol,
                                name,
                                header,
                                "",
                                cell.value,
                                sheet_index,
                                headers.index(header),
                                "Column is absent from this file's legacy layout; "
                                "migrate the matrix before writing it.",
                            )
                        )
                    continue
                cell = sheet.get(name, Cell())
                file_value = ascii_record.get(name, "")
                source, target = (
                    (file_value, cell.value) if direction == "read" else (cell.value, file_value)
                )
                action = (
                    "ADD"
                    if new_target
                    else three_way_action(
                        snapshot.baseline.get(_key(filename, pol, name)), source, target
                    )
                )
                if cell.formula:
                    action = "INVALID"
                if direction == "write" and any(
                    character in source for character in ("|", "\r", "\n")
                ):
                    action = "INVALID"
                change = Change(
                    action,
                    filename,
                    pol,
                    name,
                    header,
                    target,
                    source,
                    sheet_index,
                    headers.index(header),
                    "Mapped cells require literal text without formulas or pipe/newline separators."
                    if action == "INVALID"
                    else "",
                )
                result.changes.append(change)
                if action in ("ADD", "UPDATE"):
                    if direction == "write":
                        updates.setdefault(pol, {})[name] = source
                    result.baseline[_key(filename, pol, name)] = source
                elif action == "UNCHANGED" and source == target:
                    result.baseline[_key(filename, pol, name)] = source
            if direction == "write" and new_target:
                updates.setdefault(pol, {})["POL"] = pol
        if updates:
            result.file_outputs[filename] = matrix.render(updates)
    return result


def apply_preview(preview: SyncPreview, snapshot: WorkbookSnapshot) -> ApplyResult:
    """Apply a reviewed batch after freshness checks; keep originals per file.

    A write failure returns completed files and their recovery paths. There is
    deliberately no claim of a filesystem-wide atomic transaction.

    Parameters
    ----------
    preview : SyncPreview
        The reviewed preview.
    snapshot : WorkbookSnapshot
        The workbook as it is now, checked against the preview.

    Returns
    -------
    ApplyResult
        The files written and their backups, the headers and mappings returned to the workbook, and
        the error of a partial write.

    Raises
    ------
    ExcelSyncError
        If the preview holds INVALID or CONFLICT rows, or the workbook or a matrix changed after
        the preview. A matrix that changes during the apply is not raised: the result's
        ``error`` names it, with the files already written and their backups.
    """
    if not preview.applicable:
        raise ExcelSyncError(
            "Preview contains INVALID or CONFLICT rows; correct them and Preview again."
        )
    if snapshot.digest() != preview.workbook_digest:
        raise ExcelSyncError(
            "Runs, Dictionary or baseline changed after Preview; preview again before Apply."
        )
    root = Path(preview.workspace)
    for filename, expected in preview.file_digests.items():
        path = _matrix_path(root, filename, preview.direction)
        actual = _digest(path.read_bytes()) if path.exists() else None
        if expected != actual:
            raise ExcelSyncError(f"{filename} changed after Preview; preview again before Apply.")
    result = ApplyResult(
        [change for change in preview.changes if change.action in ("ADD", "UPDATE")]
        if preview.direction == "read"
        else [],
        preview.mappings,
        preview.headers,
        dict(preview.baseline),
    )
    if preview.direction == "read":
        return result
    for filename, content in preview.file_outputs.items():
        path = _matrix_path(root, filename, preview.direction)
        temporary: str | None = None
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            # Recheck immediately before replacing this file, not just at batch start.
            original = path.read_bytes() if path.exists() else None
            expected = preview.file_digests[filename]
            if (_digest(original) if original is not None else None) != expected:
                raise ExcelSyncError(f"{filename} changed during Apply; preview again.")
            if original is not None:
                backup = root / ".excel-sync-recovery" / preview.token / filename
                backup.parent.mkdir(parents=True, exist_ok=True)
                with backup.open("xb") as stream:
                    stream.write(original)
                result.backups[filename] = str(backup)
            descriptor, temporary = tempfile.mkstemp(
                prefix=".excel-sync-", suffix=".tmp", dir=path.parent
            )
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(content.encode("utf-8"))
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
            temporary = None
            result.written.append(filename)
        except (OSError, ExcelSyncError) as exc:
            result.error = (
                f"Apply stopped at {filename}: {exc}. "
                "Completed files and recovery copies are listed."
            )
            result.baseline = dict(snapshot.baseline)
            break
        finally:
            if temporary is not None:
                Path(temporary).unlink(missing_ok=True)
    return result
