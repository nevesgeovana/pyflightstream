"""Explicit file transactions over the existing name-based synchronization engine."""

from __future__ import annotations

import hashlib
import html
import io
import json
import os
import posixpath
import re
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import asdict
from pathlib import Path
from typing import Literal
from zipfile import BadZipFile, ZipFile

import pyflightstream._textio as _textio
from pyflightstream.workspace.excel_bridge import preview_from_json
from pyflightstream.workspace.excel_sync import (
    Cell,
    DictionaryEntry,
    ExcelSyncError,
    SyncPreview,
    WorkbookSnapshot,
    apply_preview,
    check_snapshot,
    preview_sync,
    require_token,
)

__all__ = [
    "apply_batch",
    "cancel_batch",
    "check_file",
    "patch_cells",
    "preview_file",
    "read_snapshot",
]

_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"


def _xml(raw: bytes) -> ET.Element:
    if b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
        raise ExcelSyncError("Workbook XML declarations with external entities are unsupported.")
    return ET.fromstring(raw)


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


#: The document properties a save rewrites without any cell changing: wall-clock creation and
#: modification stamps and the elapsed editing time (NL-WKSP-7).
_VOLATILE_PROPERTIES = re.compile(
    rb"<dcterms:(created|modified)\b[^>]*>[^<]*</dcterms:\1>|<TotalTime>[^<]*</TotalTime>"
)


def _workbook_digest(raw: bytes) -> str:
    """Hash the workbook's content, not its ZIP envelope (NL-WKSP-7).

    The canonical form is every member's name and uncompressed bytes in name order, with the
    created and modified stamps and the elapsed editing time of the document properties
    removed, so two saves of the same cells agree whatever the clock read. A file that is not a
    ZIP archive is hashed as it is.
    """
    digest = hashlib.sha256()
    try:
        with ZipFile(io.BytesIO(raw)) as archive:
            for name in sorted(archive.namelist()):
                data = archive.read(name)
                if name.startswith("docProps/"):
                    data = _VOLATILE_PROPERTIES.sub(b"", data)
                for part in (name.encode("utf-8"), data):
                    digest.update(len(part).to_bytes(8, "big"))
                    digest.update(part)
    except BadZipFile:
        return _digest(raw)
    return digest.hexdigest()


def _parts(archive: ZipFile) -> dict[str, str]:
    relationships = _xml(archive.read("xl/_rels/workbook.xml.rels"))
    targets = {}
    for item in relationships:
        if item.get("TargetMode") == "External":
            continue
        target = item.get("Target", "")
        path = target.lstrip("/") if target.startswith("/") else posixpath.normpath("xl/" + target)
        if not path.startswith("xl/") or ".." in path.split("/"):
            raise ExcelSyncError("Workbook worksheet target escapes the XLSX package.")
        targets[item.get("Id")] = path
    workbook = _xml(archive.read("xl/workbook.xml"))
    sheets = {}
    for sheet in workbook.findall(_NS + "sheets/" + _NS + "sheet"):
        name, relation = sheet.get("name"), sheet.get(_REL + "id")
        if name is None or relation not in targets:
            raise ExcelSyncError(
                f"xl/workbook.xml lists sheet {name!r} with no name or no worksheet part "
                f"({relation!r}); save the workbook again from Excel."
            )
        sheets[name] = targets[relation]
    return sheets


def _column(name: str) -> int:
    result = 0
    for character in name:
        result = result * 26 + ord(character) - 64
    return result


def _address(row: int, column: int) -> str:
    if row < 1 or column < 1:
        raise ExcelSyncError(
            f"Cell (row {row}, column {column}) is not a worksheet position; rows and columns "
            "count from 1."
        )
    name = ""
    while column:
        column, remainder = divmod(column - 1, 26)
        name = chr(65 + remainder) + name
    return name + str(row)


def _table(archive: ZipFile, path: str, strings: list[str]) -> dict[tuple[int, int], Cell]:
    result = {}
    for node in _xml(archive.read(path)).iter(_NS + "c"):
        # The r attribute is optional in OOXML; a cell without it is refused,
        # named, rather than placed by a guess.
        match = re.fullmatch(r"([A-Z]+)([1-9][0-9]*)", node.get("r", ""))
        if match is None:
            raise ExcelSyncError(
                f"Unsupported worksheet cell address {node.get('r')!r} in {path}; save the "
                "workbook again from Excel."
            )
        formula = node.find(_NS + "f")
        kind = node.get("t", "n")
        value = node.findtext(_NS + "v", "")
        if formula is not None:
            value = "=" + (formula.text or "")
        elif kind == "s":
            index = int(value)
            if index < 0:
                raise ExcelSyncError(
                    f"Shared-string index {index} of cell {node.get('r')} in {path} is negative; "
                    "the workbook is damaged, save it again from Excel."
                )
            value = strings[index]
        elif kind == "inlineStr":
            value = "".join(n.text or "" for n in node.iter(_NS + "t"))
        elif kind == "b":
            value = "TRUE" if value.strip() == "1" else "FALSE"
        elif kind == "e":
            raise ExcelSyncError(
                f"Worksheet cell {node.get('r')} in {path} holds the error value {value}; "
                "correct the cell and save the workbook again."
            )
        result[int(match[2]), _column(match[1])] = Cell(value, formula is not None)
    return result


def read_snapshot(path: str | Path) -> WorkbookSnapshot:
    """Read saved values and formula text without recalculating or opening Excel.

    Parameters
    ----------
    path : str or Path
        The saved ``.xlsx`` workbook.

    Returns
    -------
    WorkbookSnapshot
        The Runs headers and rows, the Dictionary entries and the baseline values.

    Raises
    ------
    ExcelSyncError
        If the workbook lacks its Runs, Dictionary or _Baseline worksheet, or a header or
        Dictionary mapping is not unique literal text.
    """
    # A package that is no workbook is refused by name (PFS-2095.060): an encrypted
    # workbook is an OLE container (BadZipFile), a missing part or relationship id is a
    # KeyError and a bad shared-string index an IndexError, and each escaped as a traceback.
    try:
        with ZipFile(path) as archive:
            return _snapshot(archive)
    except ExcelSyncError:
        raise
    except (BadZipFile, KeyError, IndexError, ET.ParseError, ValueError, RuntimeError) as error:
        raise ExcelSyncError(
            f"{path} is not a readable .xlsx workbook (an encrypted or damaged package): "
            f"{type(error).__name__}: {error}. Save it again from Excel without a password."
        ) from error


def _snapshot(archive: ZipFile) -> WorkbookSnapshot:
    """Read the three worksheets of an opened workbook package."""
    parts = _parts(archive)
    if not {"Runs", "Dictionary", "_Baseline"} <= parts.keys():
        raise ExcelSyncError("Workbook needs Runs, Dictionary and _Baseline worksheets.")
    strings = []
    if "xl/sharedStrings.xml" in archive.namelist():
        strings = [
            "".join(n.text or "" for n in item.iter(_NS + "t"))
            for item in _xml(archive.read("xl/sharedStrings.xml"))
        ]
    runs = _table(archive, parts["Runs"], strings)
    width = max(
        (column for (row, column), cell in runs.items() if row == 1 and cell.value), default=0
    )
    height = max((row for (row, _), cell in runs.items() if cell.value or cell.formula), default=1)
    headers = [runs.get((1, column), Cell()).value for column in range(1, width + 1)]
    if any(column > width and (cell.value or cell.formula) for (_, column), cell in runs.items()):
        raise ExcelSyncError("Runs contains data beyond its named headers.")
    if any(cell.formula for (row, _), cell in runs.items() if row == 1):
        raise ExcelSyncError("Runs headers require literal text.")
    rows = [
        [runs.get((row, column), Cell()) for column in range(1, width + 1)]
        for row in range(2, height + 1)
    ]
    dictionary = _table(archive, parts["Dictionary"], strings)
    header_cells = [cell for (row, _), cell in dictionary.items() if row == 1]
    header_names = [cell.value for cell in header_cells]
    if any(cell.formula for cell in header_cells) or len(header_names) != len(set(header_names)):
        raise ExcelSyncError("Dictionary headers must be unique literal text.")
    labels = {cell.value: column for (row, column), cell in dictionary.items() if row == 1}
    required = ("ASCII_NAME", "EXCEL_HEADER", "STATUS")
    if not set(required) <= labels.keys():
        raise ExcelSyncError("Dictionary needs ASCII_NAME, EXCEL_HEADER and STATUS headers.")
    entries = []
    for row in sorted({row for row, _ in dictionary if row > 1}):
        cells = [dictionary.get((row, labels[name]), Cell()) for name in required]
        if any(cell.formula for cell in cells):
            raise ExcelSyncError("Dictionary mappings require literal text, not formulas.")
        if any(cell.value for cell in cells):
            entries.append(DictionaryEntry(*(cell.value for cell in cells)))
    baseline = _table(archive, parts["_Baseline"], strings)
    values = {
        cell.value: baseline.get((row, 2), Cell()).value
        for (row, column), cell in baseline.items()
        if row > 1 and column == 1 and cell.value
    }
    return WorkbookSnapshot(headers, rows, entries, values)


def check_file(path: Path) -> None:
    """Validate saved workbook identity and Dictionary mappings.

    Parameters
    ----------
    path : Path
        The saved macro-free ``.xlsx`` workbook.
    """
    check_snapshot(read_snapshot(path))


def _patch_sheet(raw: bytes, changes: dict[tuple[int, int], str]) -> bytes:
    """Replace only selected cell markup; retain all other worksheet bytes."""
    text = _utf8_text(raw)
    _xml(raw)
    data = re.search(r"<sheetData\b[^>]*(?:/>|>.*?</sheetData>)", text, re.S)
    if data is None:
        raise ExcelSyncError("Unsupported prefixed worksheet XML; originals are unchanged.")
    body = data.group()
    if body.endswith("/>"):
        body = "<sheetData></sheetData>"
    grouped: dict[int, dict[int, str]] = {}
    for (row_index, column), value in changes.items():
        grouped.setdefault(row_index, {})[column] = value
    for row_number, columns in sorted(grouped.items()):
        # The attribute run is LAZY: a greedy one eats the "/" of a
        # self-closing tag, and the body alternative then runs on through the
        # NEXT element's close, so the patch would delete or misplace it.
        row_pattern = rf'<row\b(?=[^>]*\br="{row_number}")[^>]*?(?:/>|>.*?</row>)'
        found = re.search(row_pattern, body, re.S)
        row = found.group() if found else f'<row r="{row_number}"></row>'
        if row.endswith("/>"):
            row = row[:-2] + "></row>"
        for column, value in sorted(columns.items()):
            address = _address(row_number, column)
            cell_pattern = rf'<c\b(?=[^>]*\br="{address}")[^>]*?(?:/>|>.*?</c>)'
            old = re.search(cell_pattern, row, re.S)
            style = ""
            if old:
                style_match = re.search(r'\bs="([0-9]+)"', old.group().split(">", 1)[0])
                if style_match:
                    style = f' s="{style_match[1]}"'
            cell = (
                f'<c r="{address}"{style} t="inlineStr"><is>'
                f'<t xml:space="preserve">{html.escape(value)}</t></is></c>'
            )
            if old:
                row = row[: old.start()] + cell + row[old.end() :]
            else:
                position = row.index("</row>")
                for candidate in re.finditer(r'<c\b[^>]*\br="([A-Z]+)[0-9]+"', row):
                    if _column(candidate[1]) > column:
                        position = candidate.start()
                        break
                row = row[:position] + cell + row[position:]
        if found:
            body = body[: found.start()] + row + body[found.end() :]
        else:
            position = body.index("</sheetData>")
            for candidate in re.finditer(r'<row\b[^>]*\br="([0-9]+)"', body):
                if int(candidate[1]) > row_number:
                    position = candidate.start()
                    break
            body = body[:position] + row + body[position:]
    text = text[: data.start()] + body + text[data.end() :]
    return _with_dimension(text).encode("utf-8")


def _utf8_text(raw: bytes) -> str:
    """Decode a worksheet part, refusing one that is not UTF-8 with the originals untouched."""
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ExcelSyncError(
            f"Unsupported worksheet encoding ({error.reason}); the workbook parts must be UTF-8. "
            "Originals are unchanged."
        ) from error


def _with_dimension(text: str) -> str:
    """Update the dimension cache of a worksheet to include the added cells."""
    cells = list(_xml(text.encode()).iter(_NS + "c"))
    coordinates = [re.fullmatch(r"([A-Z]+)([0-9]+)", node.attrib["r"]) for node in cells]
    if not coordinates:
        return text
    maximum_row = max(int(match[2]) for match in coordinates if match is not None)
    maximum_col = max(_column(match[1]) for match in coordinates if match is not None)
    return re.sub(
        r"<dimension\b[^>]*/>",
        f'<dimension ref="A1:{_address(maximum_row, maximum_col)}"/>',
        text,
        count=1,
    )


def _patched(raw: bytes, changes: dict[str, dict[tuple[int, int], str]]) -> bytes:
    buffer = io.BytesIO()
    with ZipFile(io.BytesIO(raw)) as source, ZipFile(buffer, "w") as target:
        parts = _parts(source)
        by_path = {parts[name]: cells for name, cells in changes.items() if cells}
        target.comment = source.comment
        for member in source.infolist():
            data = source.read(member)
            target.writestr(
                member,
                _patch_sheet(data, by_path[member.filename])
                if member.filename in by_path
                else data,
            )
    return buffer.getvalue()


def _replace(path: Path, raw: bytes) -> None:
    descriptor, temporary = tempfile.mkstemp(prefix=".excel-sync-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def patch_cells(path: Path, changes: dict[str, dict[tuple[int, int], str]]) -> None:
    """Apply explicit literal cell edits, preserving all unrelated package members.

    Parameters
    ----------
    path : Path
        The saved macro-free ``.xlsx`` workbook.
    changes : dict of str to dict of (int, int) to str
        Worksheet name to the cells to set, (row, column) to literal text.
    """
    _replace(path, _patched(path.read_bytes(), changes))


def preview_file(
    path: Path,
    *,
    workspace: Path,
    direction: Literal["read", "write"],
    batch: Path,
    matrices: list[str] | None = None,
) -> Path:
    """Save a reviewable transaction and HTML preview without changing either input.

    Parameters
    ----------
    path : Path
        The saved macro-free ``.xlsx`` workbook.
    workspace : Path
        The workspace whose matrices are compared.
    direction : str
        ``read`` (matrices to workbook) or ``write`` (workbook to matrices).
    batch : Path
        A new preview batch file; an existing one is refused.
    matrices : list of str, optional
        The matrix files to compare. None compares every matrix of the workspace when reading, and
        the matrices the Runs rows name when writing.

    Returns
    -------
    Path
        The HTML preview written beside the batch.

    Raises
    ------
    ExcelSyncError
        If the workbook is not a ``.xlsx`` file, or the batch or its HTML preview already exists.
    """
    path, batch = path.resolve(), batch.resolve()
    if path.suffix.lower() != ".xlsx":
        raise ExcelSyncError("Use a macro-free .xlsx workbook.")
    if batch.suffix.lower() == ".html":
        raise ExcelSyncError(
            f"Preview batch {batch.name!r} ends in .html, the name of its preview page; "
            "name the batch with .json."
        )
    if batch.exists() or batch.with_suffix(".html").exists():
        raise ExcelSyncError("Choose a new preview batch path; existing previews are preserved.")
    original = path.read_bytes()
    preview = preview_sync(workspace, read_snapshot(path), direction=direction, matrices=matrices)
    payload = {
        "schema": 1,
        "status": "pending",
        "workbook": str(path),
        "workbook_sha256": _workbook_digest(original),
        "preview": asdict(preview),
    }
    batch.parent.mkdir(parents=True, exist_ok=True)
    with _textio.open_text(batch, "x") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2)
    rows = "".join(
        "<tr>"
        + "".join(
            "<td>" + html.escape(str(value)) + "</td>"
            for value in (
                change.action,
                change.matrix,
                change.pol,
                change.excel_header,
                change.before,
                change.after,
                change.detail,
            )
        )
        + "</tr>"
        for change in preview.changes
    )
    page = (
        '<!doctype html><meta charset="utf-8"><title>Matrix synchronization preview</title>'
        "<style>body{font:15px system-ui;margin:2rem}table{border-collapse:collapse}"
        "td,th{border:1px solid #bbb;padding:.5rem;text-align:left;white-space:pre-wrap}</style>"
        "<h1>Matrix synchronization preview</h1><p>Direction: "
        + direction
        + ". This preview applies no changes. See the batch JSON for its current status.</p>"
        "<table><tr><th>Action<th>Matrix<th>POL<th>Column<th>Before<th>After<th>Detail</tr>"
        + rows
        + "</table>"
    )
    _textio.write_text(batch.with_suffix(".html"), page)
    return batch.with_suffix(".html")


def _load_batch(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema") != 1 or payload.get("status") != "pending":
        raise ExcelSyncError(
            f"Preview is {payload.get('status', 'invalid')}; create a new preview."
        )
    return payload


def cancel_batch(path: Path) -> None:
    """Mark a pending preview cancelled; never modify the workbook or matrices.

    Parameters
    ----------
    path : Path
        The preview batch file :func:`preview_file` wrote.

    Raises
    ------
    ExcelSyncError
        If the preview is not pending: already cancelled (said so), applied or invalid.
    """
    try:
        payload = _load_batch(path)
    except ExcelSyncError:
        if json.loads(path.read_text(encoding="utf-8")).get("status") == "cancelled":
            raise ExcelSyncError(
                "Preview is already cancelled; there is nothing to cancel. To synchronize "
                "again, create a new preview."
            ) from None
        raise
    payload["status"] = "cancelled"
    _replace(path, json.dumps(payload, ensure_ascii=False, indent=2).encode())


def _refuse_a_stale_preview(preview: SyncPreview, snapshot: WorkbookSnapshot) -> None:
    """Refuse a preview whose token, matrices or rows no longer allow an apply."""
    require_token(preview.token)
    fresh = preview_sync(
        preview.workspace, snapshot, direction=preview.direction, matrices=preview.selection
    )
    fresh.token = preview.token
    if asdict(fresh) != asdict(preview):
        raise ExcelSyncError("Matrices or preview changed after Preview; preview again.")
    if not preview.applicable:
        raise ExcelSyncError(
            "Preview contains INVALID or CONFLICT rows; correct and preview again."
        )


def apply_batch(path: Path) -> dict:
    """Apply one fresh preview, retaining exact originals and partial-write details.

    Parameters
    ----------
    path : Path
        The preview batch file :func:`preview_file` wrote.

    Returns
    -------
    dict
        The files written, their backups, the workbook's backup and the error of a partial write,
        if any.

    Raises
    ------
    ExcelSyncError
        If the workbook, the matrices or the preview changed after the preview, or the preview
        holds INVALID or CONFLICT rows. A workbook that changes during the apply is not raised:
        the returned ``error`` names it and the original is kept.
    """
    payload = _load_batch(path)
    workbook = Path(payload["workbook"])
    original = workbook.read_bytes()
    if _workbook_digest(original) != payload["workbook_sha256"]:
        raise ExcelSyncError("Workbook changed after Preview; save and preview again.")
    snapshot = read_snapshot(workbook)
    preview = preview_from_json(payload["preview"])
    _refuse_a_stale_preview(preview, snapshot)
    recovery = Path(preview.workspace) / ".excel-sync-recovery" / preview.token
    recovery.mkdir(parents=True, exist_ok=False)
    backup = recovery / "workbook-original.xlsx"
    backup.write_bytes(original)
    result = apply_preview(preview, snapshot)
    changes: dict[str, dict[tuple[int, int], str]] = {"Runs": {}, "Dictionary": {}, "_Baseline": {}}
    for column, name in enumerate(result.headers, 1):
        if column > len(snapshot.headers):
            changes["Runs"][1, column] = name
    for change in result.changes:
        changes["Runs"][change.row + 2, change.column + 1] = change.after
    # Dictionary column order belongs to the owner; locate the three fields by name.
    with ZipFile(workbook) as archive:
        parts = _parts(archive)
        strings = []
        if "xl/sharedStrings.xml" in archive.namelist():
            strings = [
                "".join(n.text or "" for n in item.iter(_NS + "t"))
                for item in _xml(archive.read("xl/sharedStrings.xml"))
            ]
        table = _table(archive, parts["Dictionary"], strings)
        columns = {cell.value: column for (row, column), cell in table.items() if row == 1}
        next_row = max((row for row, _ in table), default=1) + 1
    for row, entry in enumerate(result.mappings, next_row):
        for label, value in zip(
            ("ASCII_NAME", "EXCEL_HEADER", "STATUS"),
            (entry.ascii_name, entry.excel_header, entry.status),
            strict=True,
        ):
            changes["Dictionary"][row, columns[label]] = value
    for row, (key, value) in enumerate(result.baseline.items(), 2):
        changes["_Baseline"][row, 1] = key
        changes["_Baseline"][row, 2] = value
    try:
        if workbook.read_bytes() != original:
            raise ExcelSyncError(
                "Workbook changed during Apply; recover originals and preview again."
            )
        _replace(workbook, _patched(original, changes))
    except (OSError, ExcelSyncError) as exc:
        result.error = f"Workbook update failed: {exc}. Original retained at {backup}."
    payload.update(
        status="partial" if result.error else "applied",
        result=asdict(result),
        workbook_backup=str(backup),
        workbook_after_sha256=_workbook_digest(workbook.read_bytes()),
    )
    _replace(path, json.dumps(payload, ensure_ascii=False, indent=2).encode())
    return {
        "written": result.written,
        "backups": result.backups,
        "workbook_backup": str(backup),
        "error": result.error,
    }
