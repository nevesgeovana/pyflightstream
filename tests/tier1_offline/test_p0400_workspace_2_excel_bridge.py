"""P0400-XLSXBRIDGE: the workbook bridge answers every malformed input with a response, and a
partial apply with exit 1."""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

import pytest

from pyflightstream.workspace.excel_bridge import bridge, escape, preview_from_json
from pyflightstream.workspace.excel_sync import Cell, ExcelSyncError, WorkbookSnapshot
from tests.tier1_offline.test_excel_sync import imported, matrix


def _request(path: Path, workspace: Path, direction: str, snap: WorkbookSnapshot) -> Path:
    """Write the request the workbook would send for ``snap``."""
    rows = [["META", "workspace", workspace.as_posix()], ["META", "direction", direction]]
    rows += [["HEADER", header] for header in snap.headers]
    rows += [["DICTIONARY", e.ascii_name, e.excel_header, e.status] for e in snap.dictionary]
    rows += [
        ["CELL", str(r), str(c), cell.value, str(int(cell.formula))]
        for r, row in enumerate(snap.rows)
        for c, cell in enumerate(row)
        if cell.value
    ]
    rows += [["BASELINE", key, value] for key, value in snap.baseline.items()]
    path.write_text("\n".join("\t".join(escape(v) for v in row) for row in rows) + "\n", "utf-8")
    return path


@pytest.mark.parametrize("record", ["CELL\t1\t2", "META\tworkspace", "CELL\tone\t2\tx\t0"])
def test_p0400_xlsxbridge_a_truncated_record_writes_an_error_response(tmp_path, record):
    """P0400-XLSXBRIDGE (PFS-2095.030): a short or non-numeric record is refused naming its line,
    and the bridge writes the ERROR response and returns 1 instead of raising."""
    request, response, batch = (tmp_path / n for n in ("request.tsv", "response.tsv", "b.json"))
    request.write_text("HEADER\tPOL\n" + record + "\n", encoding="utf-8")
    assert bridge("check", request, response, batch) == 1
    text = response.read_text(encoding="utf-8")
    assert text.startswith("ERROR") and "line 2" in text, text


def test_p0400_xlsxbridge_a_malformed_batch_is_a_sync_error():
    """P0400-XLSXBRIDGE (PFS-2095.030): a batch that is not a preview is an ExcelSyncError,
    which the bridge answers, never a bare KeyError or TypeError."""
    with pytest.raises(ExcelSyncError, match="preview again"):
        preview_from_json({"changes": [], "mappings": [], "unexpected": 1})


@pytest.mark.skipif(
    sys.platform != "win32", reason="a read-only file refuses os.replace on Windows"
)
def test_p0400_xlsxbridge_a_partial_apply_returns_one(tmp_path: Path):
    """P0400-XLSXBRIDGE (PFS-2095.030): an apply that writes batch.fs and is refused second.fs
    answers PARTIAL and returns 1, as pyfs-excel apply does for the same batch."""
    matrix(tmp_path)
    second = matrix(tmp_path, "second.fs")
    snap = imported(tmp_path)
    for row in snap.rows:
        row[snap.headers.index("DESCRIPTION")] = Cell("changed")
    request = _request(tmp_path / "request.tsv", tmp_path, "write", snap)
    response, batch = tmp_path / "response.tsv", tmp_path / "preview.json"
    assert bridge("preview", request, response, batch) == 0, response.read_text("utf-8")
    second.chmod(stat.S_IREAD)
    try:
        code = bridge("apply", request, response, batch)
    finally:
        os.chmod(second, stat.S_IWRITE | stat.S_IREAD)
    text = response.read_text(encoding="utf-8")
    assert "\nPARTIAL\t" in text and "second.fs" in text, text
    assert code == 1
