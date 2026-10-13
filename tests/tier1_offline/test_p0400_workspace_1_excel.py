"""P0400-WSEXCEL: the Excel workbook reader and the Excel to matrix sync (0.40.0 lane workspace-1).

Each test is the regression of one planning node and fails on the code before its fix.
"""

from __future__ import annotations

import zipfile

import pytest

from pyflightstream.workspace.excel_bridge import read_request
from pyflightstream.workspace.excel_file import read_snapshot
from pyflightstream.workspace.excel_sync import Cell, ExcelSyncError, preview_sync
from tests.tier1_offline.test_excel_sync import imported, matrix

pytestmark = pytest.mark.requirement("P0400-WSEXCEL")


def test_p0400_wsexcel_an_encrypted_workbook_is_refused_by_name(tmp_path):
    """P0400-WSEXCEL (PFS-2095.060): an OLE container (a password workbook) is no traceback."""
    book = tmp_path / "locked.xlsx"
    book.write_bytes(bytes.fromhex("d0cf11e0a1b11ae1") + b"\x00" * 504)
    with pytest.raises(ExcelSyncError, match="locked.xlsx"):
        read_snapshot(book)


def test_p0400_wsexcel_a_package_missing_its_parts_is_refused_by_name(tmp_path):
    """P0400-WSEXCEL (PFS-2095.060): a zip with no workbook relationships is no KeyError."""
    book = tmp_path / "damaged.xlsx"
    with zipfile.ZipFile(book, "w") as package:
        package.writestr("[Content_Types].xml", "<Types/>")
    with pytest.raises(ExcelSyncError, match="damaged.xlsx"):
        read_snapshot(book)


def test_p0400_wsexcel_a_noninteger_shared_string_index_is_refused(tmp_path):
    """P0400-WSEXCEL (PFS-2095.060): a malformed cell index raises ExcelSyncError."""
    main = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    rel = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    book = tmp_path / "bad-index.xlsx"
    sheets = ("Runs", "Dictionary", "_Baseline")
    with zipfile.ZipFile(book, "w") as package:
        package.writestr(
            "xl/workbook.xml",
            f'<workbook xmlns="{main}" xmlns:r="{rel}"><sheets>'
            + "".join(f'<sheet name="{name}" r:id="r{i}"/>' for i, name in enumerate(sheets))
            + "</sheets></workbook>",
        )
        package.writestr(
            "xl/_rels/workbook.xml.rels",
            "<Relationships>"
            + "".join(f'<Relationship Id="r{i}" Target="worksheets/s{i}.xml"/>' for i in range(3))
            + "</Relationships>",
        )
        package.writestr(
            "xl/worksheets/s0.xml",
            f'<worksheet xmlns="{main}"><sheetData><row r="1">'
            '<c r="A1" t="s"><v>not-a-number</v></c></row></sheetData></worksheet>',
        )
    with pytest.raises(ExcelSyncError, match="bad-index.xlsx"):
        read_snapshot(book)


@pytest.mark.parametrize("record", ["META", "HEADER", "DICTIONARY", "CELL", "BASELINE"])
def test_p0400_wsexcel_a_short_bridge_record_is_refused(tmp_path, record):
    """P0400-WSEXCEL (PFS-2095.060): malformed bridge records name their line."""
    path = tmp_path / "request.txt"
    path.write_text(record + "\n", encoding="utf-8")
    with pytest.raises(ExcelSyncError, match="request.txt line 1"):
        read_request(path)


@pytest.mark.parametrize("direction", ["write", "read"])
def test_p0400_wsexcel_a_pol_cell_with_a_trailing_space_is_the_same_row(tmp_path, direction):
    """P0400-WSEXCEL (PFS-2096.025): POL '001 ' is the matrix row 001, in both directions."""
    path = matrix(tmp_path)
    snap = imported(tmp_path)
    column = snap.headers.index("POL")
    snap.rows[0][column] = Cell(snap.rows[0][column].value + " ")
    preview = preview_sync(tmp_path, snap, direction=direction)
    assert [c for c in preview.changes if c.action == "ADD"] == [], preview.changes
    rendered = preview.file_outputs.get("batch.fs", path.read_text(encoding="utf-8"))
    rows = [line for line in rendered.splitlines() if line.startswith("001")]
    assert len(rows) == 1, rendered
