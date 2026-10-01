"""A text bridge for the embedded workbook controls; Excel remains the cell writer."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Literal

from pyflightstream._cli import cli_entrypoint
from pyflightstream.workspace.excel_sync import (
    Cell,
    Change,
    DictionaryEntry,
    ExcelSyncError,
    SyncPreview,
    WorkbookSnapshot,
    apply_preview,
    dictionary_mapping,
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
        If the file holds a record kind this runtime does not know.
    """
    metadata: dict[str, str] = {}
    headers: list[str] = []
    dictionary = []
    baseline: dict[str, str] = {}
    cells: dict[tuple[int, int], Cell] = {}
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        row = [unescape(value) for value in raw.split("\t")]
        if row[0] == "META":
            metadata[row[1]] = row[2]
        elif row[0] == "HEADER":
            headers.append(row[1])
        elif row[0] == "DICTIONARY":
            dictionary.append(DictionaryEntry(*row[1:4]))
        elif row[0] == "CELL":
            cells[int(row[1]), int(row[2])] = Cell(row[3], row[4] == "1")
        elif row[0] == "BASELINE":
            baseline[row[1]] = row[2]
        elif row[0]:
            raise ExcelSyncError(
                f"unknown bridge record {row[0]!r}; recreate the workbook with this runtime."
            )
    count = 1 + max((position[0] for position in cells), default=-1)
    rows = [
        [cells.get((row, column), Cell()) for column in range(len(headers))] for row in range(count)
    ]
    return metadata, WorkbookSnapshot(headers, rows, dictionary, baseline)


def _write_response(path: Path, records: list[list[str]]) -> None:
    path.write_text(
        "\n".join("\t".join(escape(value) for value in row) for row in records) + "\n",
        encoding="utf-8",
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
    """
    return SyncPreview(
        **{
            **data,
            "changes": [Change(**change) for change in data["changes"]],
            "mappings": [DictionaryEntry(**entry) for entry in data["mappings"]],
        }
    )


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
        nothing changed by the refused step.
    """
    try:
        metadata, snapshot = read_request(request)
        records = []
        if action == "check":
            dictionary_mapping(snapshot)
            records.append(["OK", "Dictionary is valid; no cells or matrices were changed."])
        elif action == "preview":
            batch.unlink(missing_ok=True)
            stated_direction = metadata["direction"]
            if stated_direction not in ("read", "write"):
                raise ExcelSyncError("direction must be read or write")
            direction: Literal["read", "write"] = "read" if stated_direction == "read" else "write"
            selected = [
                item.strip() for item in metadata.get("matrices", "").split(";") if item.strip()
            ]
            preview = preview_sync(
                metadata["workspace"], snapshot, direction=direction, matrices=selected or None
            )
            batch.write_text(
                json.dumps(asdict(preview), ensure_ascii=False, indent=2), encoding="utf-8"
            )
            records += [
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
        elif action == "apply":
            preview = preview_from_json(json.loads(batch.read_text(encoding="utf-8")))
            if (
                str(Path(metadata["workspace"]).resolve()) != preview.workspace
                or metadata["direction"] != preview.direction
            ):
                raise ExcelSyncError(
                    "Workspace or direction changed after Preview; preview again before Apply."
                )
            selected = [
                item.strip() for item in metadata.get("matrices", "").split(";") if item.strip()
            ]
            if (selected or None) != preview.selection:
                raise ExcelSyncError(
                    "matrix selection changed after Preview; preview again before Apply."
                )
            result = apply_preview(preview, snapshot)
            records.extend(["HEADER", header] for header in result.headers)
            records.extend(
                ["MAPPING", entry.ascii_name, entry.excel_header, entry.status]
                for entry in result.mappings
            )
            records.extend(
                ["CELL", str(change.row), str(change.column), change.after]
                for change in result.changes
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
        else:
            raise ExcelSyncError(f"unknown action {action!r}; accepted: preview, apply, check.")
        _write_response(response, records)
        return 0
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
