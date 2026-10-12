"""P0400-XLSXPATCH: the workbook patcher and reader keep to the cells and sheets the XML names."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import ZipFile

import pytest

from pyflightstream.workspace.excel_file import patch_cells, read_snapshot
from pyflightstream.workspace.excel_sync import ExcelSyncError

_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_NS = "{" + _MAIN + "}"
_SHEET = (
    f'<worksheet xmlns="{_MAIN}"><sheetData>'
    '<row r="2"><c r="B2" s="1"/><c r="C2" t="s"><v>3</v></c></row>'
    '<row r="3" spans="1:3"/>'
    '<row r="4"><c r="A4"><v>7</v></c><c r="C4"><v>8</v></c></row>'
    "</sheetData></worksheet>"
)
_EMPTY = f'<worksheet xmlns="{_MAIN}"><sheetData/></worksheet>'


def _workbook(path: Path, sheets: dict[str, str], *, relation: bool = True) -> Path:
    """Write a minimal package: one worksheet part per sheet, in order."""
    rels = "".join(
        f'<Relationship Id="rId{i}" Target="worksheets/sheet{i}.xml"/>'
        for i in range(1, len(sheets) + 1)
    )
    listed = "".join(
        f'<sheet name="{name}" sheetId="{i}"' + (f' r:id="rId{i}"' if relation else "") + "/>"
        for i, name in enumerate(sheets, start=1)
    )
    with ZipFile(path, "w") as archive:
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            f"{rels}</Relationships>",
        )
        archive.writestr(
            "xl/workbook.xml",
            f'<workbook xmlns="{_MAIN}" xmlns:r="http://schemas.openxmlformats.org/'
            f'officeDocument/2006/relationships"><sheets>{listed}</sheets></workbook>',
        )
        for i, text in enumerate(sheets.values(), start=1):
            archive.writestr(f"xl/worksheets/sheet{i}.xml", text)
    return path


def _cells(raw: bytes) -> dict[str, tuple[str, str]]:
    """Each cell's address -> (its row's r, its text)."""
    found = {}
    for row in ET.fromstring(raw).iter(_NS + "row"):
        for cell in row.iter(_NS + "c"):
            found[cell.attrib["r"]] = (row.attrib["r"], "".join(cell.itertext()))
    return found


def test_p0400_xlsxpatch_self_closing_cell_and_row_keep_their_neighbours(tmp_path):
    """P0400-XLSXPATCH (PFS-2096.011): patching a self-closing cell (B2) and a self-closing
    row (A3, B4 beside it) keeps C2, A4 and C4, and puts every new cell in its own row."""
    book = _workbook(tmp_path / "book.xlsx", {"Runs": _SHEET})
    patch_cells(book, {"Runs": {(2, 2): "x", (3, 1): "y", (4, 2): "z"}})
    with ZipFile(book) as archive:
        patched = archive.read("xl/worksheets/sheet1.xml")
    assert _cells(patched) == {
        "B2": ("2", "x"),
        "C2": ("2", "3"),
        "A3": ("3", "y"),
        "A4": ("4", "7"),
        "B4": ("4", "z"),
        "C4": ("4", "8"),
    }


def test_p0400_xlsxpatch_a_cell_without_an_address_is_a_named_refusal(tmp_path):
    """P0400-XLSXPATCH (PFS-2095.030): a cell with no r attribute (optional in OOXML) is an
    ExcelSyncError naming the sheet part, never a bare KeyError."""
    runs = _SHEET.replace(' t="s"', "").replace('<c r="A4"><v>7</v></c>', "<c><v>7</v></c>")
    book = _workbook(
        tmp_path / "book.xlsx", {"Runs": runs, "Dictionary": _EMPTY, "_Baseline": _EMPTY}
    )
    with pytest.raises(ExcelSyncError, match="sheet1.xml"):
        read_snapshot(book)


def test_p0400_xlsxpatch_a_sheet_without_its_relationship_is_a_named_refusal(tmp_path):
    """P0400-XLSXPATCH (PFS-2095.030): a workbook sheet entry with no r:id is an
    ExcelSyncError naming the sheet, never a bare KeyError."""
    book = _workbook(tmp_path / "book.xlsx", {"Runs": _SHEET}, relation=False)
    with pytest.raises(ExcelSyncError, match="Runs"):
        patch_cells(book, {"Runs": {(2, 2): "x"}})
