"""Regression coverage grouped by subject."""

from __future__ import annotations

import os
import stat
import sys
import warnings
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from zipfile import ZipFile

import pytest

from pyflightstream.cases.matrix import MatrixError
from pyflightstream.workspace import RunRecord, RunStatus
from pyflightstream.workspace.excel_bridge import bridge, escape, preview_from_json, read_request
from pyflightstream.workspace.excel_file import patch_cells, read_snapshot
from pyflightstream.workspace.excel_sync import Cell, ExcelSyncError, WorkbookSnapshot, preview_sync
from pyflightstream.workspace.matrix import PolChange, renumber_repeated_pols, resolve_matrix
from tests.tier1_offline.test_excel_sync import imported as _workspace_1_excel__imported
from tests.tier1_offline.test_excel_sync import imported as _workspace_2_excel_bridge__imported
from tests.tier1_offline.test_excel_sync import matrix as _workspace_1_excel__matrix
from tests.tier1_offline.test_excel_sync import matrix as _workspace_2_excel_bridge__matrix
from tests.tier1_offline.test_goal021_matrix_ids import _matrix as _workspace_1_matrix___matrix
from tests.tier1_offline.test_goal021_matrix_ids import _matrix as _workspace_2_matrix___matrix
from tests.tier1_offline.test_goal021_matrix_ids import (
    _workspace as _workspace_1_matrix___workspace,
)
from tests.tier1_offline.test_goal021_matrix_ids import (
    _workspace as _workspace_2_matrix___workspace,
)
from tests.tier1_offline.test_goal021_matrix_ids import row as _workspace_1_matrix__row
from tests.tier1_offline.test_goal021_matrix_ids import row as _workspace_2_matrix__row
from tests.tier1_offline.test_matrix_run import (
    _flat_rotor_matrix as _workspace_1_matrix_phases___flat_rotor_matrix,
)
from tests.tier1_offline.test_matrix_run import (
    make_library as _workspace_1_matrix_phases__make_library,
)
from tests.tier1_offline.test_matrix_run import (
    stage_geometry as _workspace_1_matrix_phases__stage_geometry,
)


class TestWorkspace1Excel:
    """P0400-WSEXCEL: the Excel workbook reader and the Excel to matrix sync (0.40.0 lane workspace-1).

    Each test is the regression of one planning node and fails on the code before its fix.
    """  # noqa: E501

    pytestmark = pytest.mark.requirement("P0400-WSEXCEL")

    @staticmethod
    def test_p0400_wsexcel_an_encrypted_workbook_is_refused_by_name(tmp_path):
        """P0400-WSEXCEL (PFS-2095.060): an OLE container (a password workbook) is no traceback."""
        book = tmp_path / "locked.xlsx"
        book.write_bytes(bytes.fromhex("d0cf11e0a1b11ae1") + b"\x00" * 504)
        with pytest.raises(ExcelSyncError, match="locked.xlsx"):
            read_snapshot(book)

    @staticmethod
    def test_p0400_wsexcel_a_package_missing_its_parts_is_refused_by_name(tmp_path):
        """P0400-WSEXCEL (PFS-2095.060): a zip with no workbook relationships is no KeyError."""
        book = tmp_path / "damaged.xlsx"
        with zipfile.ZipFile(book, "w") as package:
            package.writestr("[Content_Types].xml", "<Types/>")
        with pytest.raises(ExcelSyncError, match="damaged.xlsx"):
            read_snapshot(book)

    @staticmethod
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
                + "".join(
                    f'<Relationship Id="r{i}" Target="worksheets/s{i}.xml"/>' for i in range(3)
                )
                + "</Relationships>",
            )
            package.writestr(
                "xl/worksheets/s0.xml",
                f'<worksheet xmlns="{main}"><sheetData><row r="1">'
                '<c r="A1" t="s"><v>not-a-number</v></c></row></sheetData></worksheet>',
            )
        with pytest.raises(ExcelSyncError, match="bad-index.xlsx"):
            read_snapshot(book)

    @staticmethod
    @pytest.mark.parametrize("record", ["META", "HEADER", "DICTIONARY", "CELL", "BASELINE"])
    def test_p0400_wsexcel_a_short_bridge_record_is_refused(tmp_path, record):
        """P0400-WSEXCEL (PFS-2095.060): malformed bridge records name their line."""
        path = tmp_path / "request.txt"
        path.write_text(record + "\n", encoding="utf-8")
        with pytest.raises(ExcelSyncError, match="line 1"):
            read_request(path)

    @staticmethod
    @pytest.mark.parametrize("direction", ["write", "read"])
    def test_p0400_wsexcel_a_pol_cell_with_a_trailing_space_is_the_same_row(tmp_path, direction):
        """P0400-WSEXCEL (PFS-2096.025): POL '001 ' is the matrix row 001, in both directions."""
        path = _workspace_1_excel__matrix(tmp_path)
        snap = _workspace_1_excel__imported(tmp_path)
        column = snap.headers.index("POL")
        snap.rows[0][column] = Cell(snap.rows[0][column].value + " ")
        preview = preview_sync(tmp_path, snap, direction=direction)
        assert [c for c in preview.changes if c.action == "ADD"] == [], preview.changes
        rendered = preview.file_outputs.get("batch.fs", path.read_text(encoding="utf-8"))
        rows = [line for line in rendered.splitlines() if line.startswith("001")]
        assert len(rows) == 1, rendered


class TestWorkspace1Matrix:
    """P0400-WSMATRIX: the POLs a workspace already claims (0.40.0 lane workspace-1).

    Each test is the regression of one planning node and fails on the code before its fix.
    """

    pytestmark = pytest.mark.requirement("P0400-WSMATRIX")

    @staticmethod
    def test_p0400_wsmatrix_a_compacted_simulation_claims_its_pol(tmp_path):
        """P0400-WSMATRIX (PFS-2085.020): sims/sim_<id>.zip is evidence, and a new POL passes it."""
        workspace = _workspace_1_matrix___workspace(tmp_path)
        matrix = _workspace_1_matrix___matrix(
            workspace.root,
            "planned.fs",
            [_workspace_1_matrix__row(8001), _workspace_1_matrix__row(8001, run=0)],
        )
        (workspace.root / "sims").mkdir(parents=True, exist_ok=True)
        (workspace.root / "sims" / "sim_9800.zip").write_bytes(b"PK")
        changes = renumber_repeated_pols(matrix, workspace)
        assert changes == [PolChange(row_number=2, old="8001", new="9801")], changes

    @staticmethod
    def test_p0400_wsmatrix_a_batch_simulation_claims_its_pol(tmp_path):
        """P0400-WSMATRIX (PFS-2085.020): sims/batch/<label>/sim_<id> claims its id too."""
        workspace = _workspace_1_matrix___workspace(tmp_path)
        matrix = _workspace_1_matrix___matrix(
            workspace.root,
            "planned.fs",
            [_workspace_1_matrix__row(8001), _workspace_1_matrix__row(8001, run=0)],
        )
        (workspace.root / "sims" / "batch" / "planned_b1" / "sim_9900").mkdir(parents=True)
        changes = renumber_repeated_pols(matrix, workspace)
        assert changes == [PolChange(row_number=2, old="8001", new="9901")], changes


class TestWorkspace1MatrixPhases:
    """P0400-WSPHASES: a flat rotor row's named origin and its row setup keys (0.40.0 lane workspace-1).

    Each test is the regression of one planning node and fails on the code before its fix.
    """  # noqa: E501

    pytestmark = pytest.mark.requirement("P0400-WSPHASES")

    @staticmethod
    def test_p0400_wsphases_a_named_origin_keeps_the_row_setup_keys_out_of_the_variables(tmp_path):
        """P0400-WSPHASES (PFS-2095.029): the bound origin does not put FR-316 keys back."""
        workspace = _workspace_1_matrix_phases__make_library(
            tmp_path, register_build=("26.120", "C:/fs/FS.exe")
        )
        (workspace.inputs_dir / "reference_points.toml").write_text(
            "[ARP]\nx_m = 2.0\n\n[ERP1]\nx_m = 4.5\ny_m = 0.0\nz_m = 0.0\n", encoding="utf-8"
        )
        _workspace_1_matrix_phases__stage_geometry(workspace, "rotor.fsm")
        matrix = _workspace_1_matrix_phases___flat_rotor_matrix(tmp_path, "ERP1")
        text = matrix.read_text(encoding="utf-8")
        matrix.write_text(
            text.replace("/ REVOLUTIONS: 0.5", "/ REVOLUTIONS: 0.5 / viscous_coupling: ENABLE"),
            encoding="utf-8",
        )
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            resolved = resolve_matrix(
                matrix, workspace, name="flat", fs_version="26.120", recipes={}
            )
        case = resolved.campaign.sims[0]
        assert case.variables["ROTOR_ORIGIN"] == "4.5,0.0,0.0"
        assert case.variables["ROTOR_ORIGIN_POINT"] == "ERP1"
        assert "viscous_coupling" not in case.variables, sorted(case.variables)
        assert case.solver.viscous_coupling is True


def _workspace_2_excel_bridge___request(
    path: Path, workspace: Path, direction: str, snap: WorkbookSnapshot
) -> Path:
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


class TestWorkspace2ExcelBridge:
    """P0400-XLSXBRIDGE: the workbook bridge answers every malformed input with a response, and a
    partial apply with exit 1."""

    @staticmethod
    @pytest.mark.parametrize("record", ["CELL\t1\t2", "META\tworkspace", "CELL\tone\t2\tx\t0"])
    def test_p0400_xlsxbridge_a_truncated_record_writes_an_error_response(tmp_path, record):
        """P0400-XLSXBRIDGE (PFS-2095.030): a short or non-numeric record is refused naming its line,
        and the bridge writes the ERROR response and returns 1 instead of raising."""  # noqa: E501
        request, response, batch = (tmp_path / n for n in ("request.tsv", "response.tsv", "b.json"))
        request.write_text("HEADER\tPOL\n" + record + "\n", encoding="utf-8")
        assert bridge("check", request, response, batch) == 1
        text = response.read_text(encoding="utf-8")
        assert text.startswith("ERROR") and "line 2" in text, text

    @staticmethod
    def test_p0400_xlsxbridge_a_malformed_batch_is_a_sync_error():
        """P0400-XLSXBRIDGE (PFS-2095.030): a batch that is not a preview is an ExcelSyncError,
        which the bridge answers, never a bare KeyError or TypeError."""
        with pytest.raises(ExcelSyncError, match="preview again"):
            preview_from_json({"changes": [], "mappings": [], "unexpected": 1})

    @staticmethod
    @pytest.mark.skipif(
        sys.platform != "win32", reason="a read-only file refuses os.replace on Windows"
    )
    def test_p0400_xlsxbridge_a_partial_apply_returns_one(tmp_path: Path):
        """P0400-XLSXBRIDGE (PFS-2095.030): an apply that writes batch.fs and is refused second.fs
        answers PARTIAL and returns 1, as pyfs-excel apply does for the same batch."""
        _workspace_2_excel_bridge__matrix(tmp_path)
        second = _workspace_2_excel_bridge__matrix(tmp_path, "second.fs")
        snap = _workspace_2_excel_bridge__imported(tmp_path)
        for row in snap.rows:
            row[snap.headers.index("DESCRIPTION")] = Cell("changed")
        request = _workspace_2_excel_bridge___request(
            tmp_path / "request.tsv", tmp_path, "write", snap
        )
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


_WORKSPACE_2_EXCEL_FILE___MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"


_WORKSPACE_2_EXCEL_FILE___NS = "{" + _WORKSPACE_2_EXCEL_FILE___MAIN + "}"


_WORKSPACE_2_EXCEL_FILE___SHEET = (
    f'<worksheet xmlns="{_WORKSPACE_2_EXCEL_FILE___MAIN}"><sheetData>'
    '<row r="2"><c r="B2" s="1"/><c r="C2" t="s"><v>3</v></c></row>'
    '<row r="3" spans="1:3"/>'
    '<row r="4"><c r="A4"><v>7</v></c><c r="C4"><v>8</v></c></row>'
    "</sheetData></worksheet>"
)


_WORKSPACE_2_EXCEL_FILE___EMPTY = (
    f'<worksheet xmlns="{_WORKSPACE_2_EXCEL_FILE___MAIN}"><sheetData/></worksheet>'
)


def _workspace_2_excel_file___workbook(
    path: Path, sheets: dict[str, str], *, relation: bool = True
) -> Path:
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
            f'<workbook xmlns="{_WORKSPACE_2_EXCEL_FILE___MAIN}" xmlns:r="http://schemas.openxmlformats.org/'
            f'officeDocument/2006/relationships"><sheets>{listed}</sheets></workbook>',
        )
        for i, text in enumerate(sheets.values(), start=1):
            archive.writestr(f"xl/worksheets/sheet{i}.xml", text)
    return path


def _workspace_2_excel_file___cells(raw: bytes) -> dict[str, tuple[str, str]]:
    """Each cell's address -> (its row's r, its text)."""
    found = {}
    for row in ET.fromstring(raw).iter(_WORKSPACE_2_EXCEL_FILE___NS + "row"):
        for cell in row.iter(_WORKSPACE_2_EXCEL_FILE___NS + "c"):
            found[cell.attrib["r"]] = (row.attrib["r"], "".join(cell.itertext()))
    return found


class TestWorkspace2ExcelFile:
    """P0400-XLSXPATCH: the workbook patcher and reader keep to the cells and sheets the XML names."""  # noqa: E501

    @staticmethod
    def test_p0400_xlsxpatch_self_closing_cell_and_row_keep_their_neighbours(tmp_path):
        """P0400-XLSXPATCH (PFS-2096.011): patching a self-closing cell (B2) and a self-closing
        row (A3, B4 beside it) keeps C2, A4 and C4, and puts every new cell in its own row."""
        book = _workspace_2_excel_file___workbook(
            tmp_path / "book.xlsx", {"Runs": _WORKSPACE_2_EXCEL_FILE___SHEET}
        )
        patch_cells(book, {"Runs": {(2, 2): "x", (3, 1): "y", (4, 2): "z"}})
        with ZipFile(book) as archive:
            patched = archive.read("xl/worksheets/sheet1.xml")
        assert _workspace_2_excel_file___cells(patched) == {
            "B2": ("2", "x"),
            "C2": ("2", "3"),
            "A3": ("3", "y"),
            "A4": ("4", "7"),
            "B4": ("4", "z"),
            "C4": ("4", "8"),
        }

    @staticmethod
    def test_p0400_xlsxpatch_a_cell_without_an_address_is_a_named_refusal(tmp_path):
        """P0400-XLSXPATCH (PFS-2095.030): a cell with no r attribute (optional in OOXML) is an
        ExcelSyncError naming the sheet part, never a bare KeyError."""
        runs = _WORKSPACE_2_EXCEL_FILE___SHEET.replace(' t="s"', "").replace(
            '<c r="A4"><v>7</v></c>', "<c><v>7</v></c>"
        )
        book = _workspace_2_excel_file___workbook(
            tmp_path / "book.xlsx",
            {
                "Runs": runs,
                "Dictionary": _WORKSPACE_2_EXCEL_FILE___EMPTY,
                "_Baseline": _WORKSPACE_2_EXCEL_FILE___EMPTY,
            },
        )
        with pytest.raises(ExcelSyncError, match="sheet1.xml"):
            read_snapshot(book)

    @staticmethod
    def test_p0400_xlsxpatch_a_sheet_without_its_relationship_is_a_named_refusal(tmp_path):
        """P0400-XLSXPATCH (PFS-2095.030): a workbook sheet entry with no r:id is an
        ExcelSyncError naming the sheet, never a bare KeyError."""
        book = _workspace_2_excel_file___workbook(
            tmp_path / "book.xlsx", {"Runs": _WORKSPACE_2_EXCEL_FILE___SHEET}, relation=False
        )
        with pytest.raises(ExcelSyncError, match="Runs"):
            patch_cells(book, {"Runs": {(2, 2): "x"}})


class TestWorkspace2Matrix:
    """P0400-RENUMBER: the refusal to move a row with runs names a remedy that clears it."""

    @staticmethod
    def test_p0400_renumber_the_printed_remedy_clears_the_refusal(tmp_path):
        """P0400-RENUMBER (PFS-2100.017): planned.fs has runs of POL 8001, which other.fs also
        states. The refusal names other.fs and its --update-ids, not archiving (which leaves the
        records); doing what it prints lets planned.fs keep 8001 with nothing to move."""
        workspace = _workspace_2_matrix___workspace(tmp_path)
        planned = _workspace_2_matrix___matrix(
            workspace.root, "planned.fs", [_workspace_2_matrix__row(8001)]
        )
        other = _workspace_2_matrix___matrix(
            workspace.root, "other.fs", [_workspace_2_matrix__row(8001)]
        )
        workspace.append_record(
            RunRecord(
                run_id="p/sim_8001/a-02.0",
                sim_id="8001",
                point={"alpha": -2.0},
                matrix_stem="planned",
                fs_version_requested="26.120",
                package_version="0.40.0",
                script_sha256="0" * 64,
                raw_flag=False,
                status=RunStatus.CONVERGED,
            )
        )
        with pytest.raises(MatrixError) as raised:
            renumber_repeated_pols(planned, workspace, in_place=True)
        message = str(raised.value)
        assert "pyfs-matrix plan other.fs --update-ids" in message, message
        assert "archive the simulation" not in message, message
        moved = renumber_repeated_pols(other, workspace, in_place=True)
        assert [change.old for change in moved] == ["8001"]
        assert renumber_repeated_pols(planned, workspace, in_place=True) == []


def test_p0430_f1491_recognized_setting_named_recorded_only_is_not_applied():
    from pyflightstream.workspace._matrix_binding import _match_settings

    matched, refused, recorded = _match_settings(
        {"iterations": 400, "NITER": 7}, "s1", {"iterations"}
    )
    assert "iterations" not in matched
    assert recorded == ["iterations", "NITER"]
    assert refused == []
    # an alias resolving to the declared field is recorded too, never applied
    assert "iterations" not in matched and "NITER" in recorded


def test_p0430_f1580_explicit_dot_slash_matrix_is_not_redirected(tmp_path):
    from pyflightstream.workspace._matrix_homes import matrix_path, names_its_folder

    root = tmp_path / "ws"
    (root / "inputs" / "matrices").mkdir(parents=True)
    (root / "inputs" / "matrices" / "m.fs").write_text("a", encoding="utf-8")
    assert names_its_folder("./m.fs")
    assert matrix_path(root, "./m.fs") == Path("./m.fs")
    assert matrix_path(root, "m.fs") == root / "inputs" / "matrices" / "m.fs"
