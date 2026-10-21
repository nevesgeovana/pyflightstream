"""A text bridge for the embedded workbook controls; Excel remains the cell writer."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Literal

import pyflightstream._textio as _textio
from pyflightstream._cli import cli_entrypoint
from pyflightstream.workspace.excel_sync import (
    Cell,
    Change,
    DictionaryEntry,
    ExcelSyncError,
    SyncPreview,
    WorkbookSnapshot,
    _check_snapshot,
    apply_preview,
    preview_sync,
)

__all__ = [
    "bridge",
    "escape",
    "main",
    "preview_from_json",
    "read_request",
    "unescape",
]


def escape(value: str) -> str:
    """Encode delimiters without losing literal text or backslashes.

    Parameters
    ----------
    value : str
        Literal text.

    Returns
    -------
    str
        The text with backslashes, tabs, carriage returns and newlines escaped.
    """
    return (
        value.replace("\\", "\\\\").replace("\t", "\\t").replace("\r", "\\r").replace("\n", "\\n")
    )


def unescape(value: str) -> str:
    """Decode the bridge's reversible text encoding.

    Parameters
    ----------
    value : str
        Text :func:`escape` encoded.

    Returns
    -------
    str
        The literal text.
    """
    result = []
    index = 0
    while index < len(value):
        if value[index] == "\\" and index + 1 < len(value):
            index += 1
            result.append(
                {"t": "\t", "r": "\r", "n": "\n", "\\": "\\"}.get(value[index], "\\" + value[index])
            )
        else:
            result.append(value[index])
        index += 1
    return "".join(result)


#: The number of tab-separated fields each request record kind needs, its kind included.
_RECORD_WIDTHS = {"META": 3, "HEADER": 2, "DICTIONARY": 4, "CELL": 5, "BASELINE": 3}


def read_request(path: Path) -> tuple[dict[str, str], WorkbookSnapshot]:
    """Read a UTF-8 snapshot written by VBA, never a workbook file.

    Parameters
    ----------
    path : Path
        The snapshot file the workbook's macro wrote.

    Returns
    -------
    tuple of (dict of str to str, WorkbookSnapshot)
        The request's metadata and the workbook snapshot it carries.

    Raises
    ------
    ExcelSyncError
        If the file holds a record kind this runtime does not know, or a
        record shorter than its kind or with a cell position that is not a
        number; the message names the line.
    """
    metadata: dict[str, str] = {}
    headers: list[str] = []
    dictionary = []
    baseline: dict[str, str] = {}
    cells: dict[tuple[int, int], Cell] = {}
    for number, raw in enumerate(_record_lines(path), start=1):
        row = [unescape(value) for value in raw.split("\t")]
        width = _RECORD_WIDTHS.get(row[0], 0)
        if len(row) < width:
            raise ExcelSyncError(
                f"bridge record {row[0]} on line {number} holds {len(row) - 1} field(s) and "
                f"needs {width - 1}; recreate the request with this runtime."
            )
        if row[0] == "CELL" and not (row[1].isdigit() and row[2].isdigit()):
            raise ExcelSyncError(
                f"bridge record CELL on line {number} names row {row[1]!r} and column "
                f"{row[2]!r}, which are not cell positions; recreate the request with this runtime."
            )
        if row[0] == "META":
            metadata[row[1]] = row[2]
        elif row[0] == "HEADER":
            headers.append(row[1])
        elif row[0] == "DICTIONARY":
            dictionary.append(DictionaryEntry(*row[1:4]))
        elif row[0] == "CELL":
            position = _bridge_cell_position(path, number, row)
            cells[position] = Cell(row[3], row[4] == "1")
        elif row[0] == "BASELINE":
            baseline[row[1]] = row[2]
        elif row[0]:
            raise ExcelSyncError(
                f"unknown bridge record {row[0]!r}; recreate the workbook with this runtime."
            )
    _refuse_cells_beyond_headers(path, cells, len(headers))
    count = 1 + max((position[0] for position in cells), default=-1)
    rows = [
        [cells.get((row, column), Cell()) for column in range(len(headers))] for row in range(count)
    ]
    return metadata, WorkbookSnapshot(headers, rows, dictionary, baseline)


def _record_lines(path: Path) -> list[str]:
    """Split a request on the record terminators only.

    ``str.splitlines`` also breaks on U+2028, U+0085, VT and FF, which ``escape`` does not
    encode, so a cell holding one would split its record.
    """
    text = path.read_text(encoding="utf-8-sig")
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return lines


def _refuse_cells_beyond_headers(
    path: Path, cells: dict[tuple[int, int], Cell], width: int
) -> None:
    """Refuse a filled cell right of the named headers: the snapshot would drop it."""
    for (cell_row, cell_column), cell in sorted(cells.items()):
        if cell_column >= width and (cell.value or cell.formula):
            raise ExcelSyncError(
                f"{path}: the cell at row {cell_row}, column {cell_column} lies beyond the "
                f"{width} named headers and would be dropped from the snapshot; name its "
                "column in Runs."
            )


def _bridge_cell_position(path: Path, number: int, row: list[str]) -> tuple[int, int]:
    """Read a CELL record's indices and flag before using them in the workbook."""
    try:
        position = (int(row[1]), int(row[2]))
    except ValueError as error:
        raise ExcelSyncError(f"{path} line {number}: CELL needs integer indices") from error
    if min(position) < 0 or row[4] not in ("0", "1"):
        raise ExcelSyncError(f"{path} line {number}: CELL indices or formula flag are invalid")
    return position


def _write_response(path: Path, records: list[list[str]]) -> None:
    _textio.write_text(
        path, "\n".join("\t".join(escape(value) for value in row) for row in records) + "\n"
    )


def preview_from_json(data: dict[str, Any]) -> SyncPreview:
    """Reconstruct the captured synchronization decision without recomputing it.

    Parameters
    ----------
    data : dict of str to object
        A preview as the batch file stores it.

    Returns
    -------
    SyncPreview
        The preview, its changes and mappings rebuilt as objects.

    Raises
    ------
    ExcelSyncError
        If the batch does not hold a preview's fields.
    """
    try:
        return SyncPreview(
            **{
                **data,
                "changes": [Change(**change) for change in data["changes"]],
                "mappings": [DictionaryEntry(**entry) for entry in data["mappings"]],
            }
        )
    except (KeyError, TypeError) as error:
        raise ExcelSyncError(
            f"the preview batch does not hold a preview ({error}); preview again before Apply."
        ) from error


def _check_records(snapshot: WorkbookSnapshot) -> list[list[str]]:
    """Validate the dictionary of the snapshot and say so."""
    _check_snapshot(snapshot)
    return [["OK", "Dictionary is valid; no cells or matrices were changed."]]


def _selected_matrices(metadata: dict[str, str]) -> list[str]:
    """Return the matrices the request names, in the order it names them."""
    return [item.strip() for item in metadata.get("matrices", "").split(";") if item.strip()]


def _clear_the_previous_batch(batch: Path) -> None:
    """Invalidate an earlier preview, but never delete a file that is not one (F-733).

    An earlier preview is single-use and is invalidated here; a file at the batch path that
    is NOT a preview batch is the caller's own, so it is refused rather than deleted
    without a backup.
    """
    if not batch.exists():
        return
    try:
        preview_from_json(json.loads(batch.read_text(encoding="utf-8")))
    except (ExcelSyncError, ValueError, OSError) as error:
        raise ExcelSyncError(
            f"{batch} exists and is not a preview batch, so Preview will not "
            "overwrite it; name another batch path or move the file."
        ) from error
    batch.unlink()


def _preview_records(
    metadata: dict[str, str], snapshot: WorkbookSnapshot, batch: Path
) -> list[list[str]]:
    """Preview the sync, write the single-use batch and return the response records."""
    stated_direction = metadata["direction"]
    if stated_direction not in ("read", "write"):
        raise ExcelSyncError("direction must be read or write")
    _clear_the_previous_batch(batch)
    direction: Literal["read", "write"] = "read" if stated_direction == "read" else "write"
    selected = _selected_matrices(metadata)
    preview = preview_sync(
        metadata["workspace"], snapshot, direction=direction, matrices=selected or None
    )
    _textio.write_text(batch, json.dumps(asdict(preview), ensure_ascii=False, indent=2))
    records = [
        ["META", "workspace", preview.workspace],
        ["META", "direction", preview.direction],
        ["META", "token", preview.token],
        ["META", "applicable", str(int(preview.applicable))],
    ]
    records.extend(["COUNT", key, str(value)] for key, value in preview.counts.items())
    records.extend(
        ["MAPPING", entry.ascii_name, entry.excel_header, entry.status]
        for entry in preview.mappings
    )
    records.extend(
        [
            "CHANGE",
            change.action,
            change.matrix,
            change.pol,
            change.ascii_name,
            change.excel_header,
            change.before,
            change.after,
            str(change.row),
            str(change.column),
            change.detail,
        ]
        for change in preview.changes
    )
    return records


def _refuse_a_changed_preview(
    metadata: dict[str, str], snapshot: WorkbookSnapshot, preview: SyncPreview
) -> None:
    """Refuse an apply whose workspace, selection, workbook or matrices moved since Preview."""
    if (
        str(Path(metadata["workspace"]).resolve()) != preview.workspace
        or metadata["direction"] != preview.direction
    ):
        raise ExcelSyncError(
            "Workspace or direction changed after Preview; preview again before Apply."
        )
    if (_selected_matrices(metadata) or None) != preview.selection:
        raise ExcelSyncError("matrix selection changed after Preview; preview again before Apply.")
    # The batch is a file the user can edit: what Apply writes (file_outputs) is
    # recomputed from the matrices and the snapshot, never trusted from it.
    if snapshot.digest() != preview.workbook_digest:
        raise ExcelSyncError(
            "Runs, Dictionary or baseline changed after Preview; preview again before Apply."
        )
    fresh = preview_sync(
        preview.workspace, snapshot, direction=preview.direction, matrices=preview.selection
    )
    fresh.token = preview.token
    if asdict(fresh) != asdict(preview):
        raise ExcelSyncError("Matrices or preview changed after Preview; preview again.")


def _apply_records(
    metadata: dict[str, str], snapshot: WorkbookSnapshot, batch: Path
) -> list[list[str]]:
    """Apply the previewed batch and return the response records."""
    preview = preview_from_json(json.loads(batch.read_text(encoding="utf-8")))
    _refuse_a_changed_preview(metadata, snapshot, preview)
    result = apply_preview(preview, snapshot)
    records: list[list[str]] = [["HEADER", header] for header in result.headers]
    records.extend(
        ["MAPPING", entry.ascii_name, entry.excel_header, entry.status] for entry in result.mappings
    )
    records.extend(
        ["CELL", str(change.row), str(change.column), change.after] for change in result.changes
    )
    records.extend(["BASELINE", key, value] for key, value in result.baseline.items())
    records.extend(
        ["WRITTEN", filename, result.backups.get(filename, "new file, no previous version")]
        for filename in result.written
    )
    if result.error:
        records.append(["PARTIAL", result.error])
    else:
        records.append(
            [
                "OK",
                "Apply complete. Workbook cells were returned to Excel; files written: "
                + str(len(result.written)),
            ]
        )
    # A preview is single-use even when a batch stops partway through.
    batch.unlink()
    return records


def bridge(action: str, request: Path, response: Path, batch: Path) -> int:
    """Execute only the explicitly selected action and write a reviewable response.

    Parameters
    ----------
    action : str
        ``check``, ``preview`` or ``apply``.
    request : Path
        The UTF-8 snapshot the workbook's macro wrote.
    response : Path
        Where the reviewable response is written.
    batch : Path
        The preview batch: written by ``preview``, read back by ``apply``.

    Returns
    -------
    int
        0 when the action ran; 1 when it was refused, the reason written to the response and
        nothing changed by the refused step, or when an apply stopped partway (its PARTIAL
        record, and the cells and files it did write, are in the response). A refusal
        is 1 here; ``python -m pyflightstream.workspace.excel`` returns 2 for a
        refusal and 1 only for a partial apply.
    """
    try:
        metadata, snapshot = read_request(request)
        if action == "check":
            records = _check_records(snapshot)
        elif action == "preview":
            records = _preview_records(metadata, snapshot, batch)
        elif action == "apply":
            records = _apply_records(metadata, snapshot, batch)
        else:
            raise ExcelSyncError(f"unknown action {action!r}; accepted: preview, apply, check.")
        _write_response(response, records)
        return 1 if records and records[-1][0] == "PARTIAL" else 0
    except (ExcelSyncError, OSError, ValueError, KeyError) as exc:
        _write_response(response, [["ERROR", str(exc)]])
        return 1


@cli_entrypoint
def main(argv: list[str] | None = None) -> int:
    """Handle one explicitly selected workbook bridge operation.

    Parameters
    ----------
    argv : list of str, optional
        The command-line arguments, ``sys.argv[1:]`` by default.

    Returns
    -------
    int
        The exit code :func:`bridge` returns.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("preview", "apply", "check"))
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--response", type=Path, required=True)
    parser.add_argument("--batch", type=Path, required=True)
    args = parser.parse_args(argv)
    return bridge(args.action, args.request, args.response, args.batch)


if __name__ == "__main__":
    raise SystemExit(main())
