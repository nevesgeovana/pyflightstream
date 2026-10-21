from pathlib import Path
from zipfile import ZipFile

import pytest

from pyflightstream.workspace.excel import main
from tests.tier1_offline.test_excel_sync import matrix


def test_macro_free_factory_and_bidirectional_cli(tmp_path: Path) -> None:
    # GOAL033:excel:checks:cli_sync_roundtrip
    # GOAL033:capability_ids:items:G60
    from pyflightstream.workspace.excel_file import read_snapshot

    source = matrix(tmp_path)
    book = tmp_path / "runs.xlsx"
    batch = tmp_path / "read.json"
    assert main(["create", str(book), "--workspace", str(tmp_path)]) == 0
    with ZipFile(book) as archive:
        assert not any("vba" in name.lower() or "vmlDrawing" in name for name in archive.namelist())
    original = book.read_bytes()
    assert (
        main(
            [
                "preview",
                str(book),
                "--workspace",
                str(tmp_path),
                "--direction",
                "read",
                "--batch",
                str(batch),
            ]
        )
        == 0
    )
    assert book.read_bytes() == original
    assert batch.with_suffix(".html").is_file()
    assert main(["apply", str(batch)]) == 0
    snapshot = read_snapshot(book)
    assert snapshot.rows[0][snapshot.headers.index("POL")].value == "001"
    assert snapshot.rows[0][snapshot.headers.index("RUN")].value == "1"
    assert snapshot.rows[0][snapshot.headers.index("SWEEP_VALUES")].value == "0,2,4"
    assert main(["check", str(book)]) == 0
    # Change a real saved cell, rather than passing a synthetic in-memory snapshot.
    from pyflightstream.workspace.excel_file import patch_cells

    patch_cells(book, {"Runs": {(2, snapshot.headers.index("DESCRIPTION") + 1): "owner edit"}})
    write = tmp_path / "write.json"
    assert (
        main(
            [
                "preview",
                str(book),
                "--workspace",
                str(tmp_path),
                "--direction",
                "write",
                "--batch",
                str(write),
            ]
        )
        == 0
    )
    assert b"owner edit" not in source.read_bytes()
    assert main(["apply", str(write)]) == 0
    assert b"owner edit" in source.read_bytes()
    assert source.read_bytes().startswith(b"# owner comment\r\n")


def test_cancel_and_stale_whole_workbook(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # GOAL033:excel:checks:preview_apply_cancel
    from pyflightstream.workspace.excel_file import patch_cells

    source = matrix(tmp_path)
    original_matrix = source.read_bytes()
    book = tmp_path / "runs.xlsx"
    main(["create", str(book), "--workspace", str(tmp_path)])
    original = book.read_bytes()
    batch = tmp_path / "cancel.json"
    main(
        [
            "preview",
            str(book),
            "--workspace",
            str(tmp_path),
            "--direction",
            "read",
            "--batch",
            str(batch),
        ]
    )
    main(["cancel", str(batch)])
    assert book.read_bytes() == original
    assert main(["apply", str(batch)]) == 2
    assert "cancelled" in capsys.readouterr().err
    assert book.read_bytes() == original
    assert source.read_bytes() == original_matrix
    fresh = tmp_path / "stale.json"
    main(
        [
            "preview",
            str(book),
            "--workspace",
            str(tmp_path),
            "--direction",
            "read",
            "--batch",
            str(fresh),
        ]
    )
    patch_cells(book, {"Controls": {(20, 1): "unrelated owner edit"}})
    changed = book.read_bytes()
    assert main(["apply", str(fresh)]) == 2
    assert "changed after Preview" in capsys.readouterr().err
    assert book.read_bytes() == changed
    assert source.read_bytes() == original_matrix


def test_reordered_columns_formula_and_drawings_survive(tmp_path: Path) -> None:
    # GOAL033:excel:checks:preserve_custom_order_formulas
    xlsxwriter = pytest.importorskip("xlsxwriter")

    from pyflightstream.workspace.excel_file import read_snapshot

    source = matrix(tmp_path)
    book = tmp_path / "custom.xlsx"
    with xlsxwriter.Workbook(book) as workbook:
        runs = workbook.add_worksheet("Runs")
        runs.write_row(0, 0, ["Owner note", "Run ID", "File", "Title"])
        runs.write_formula(1, 0, "=1+1", None, 2)
        runs.write_row(1, 1, ["001", "batch.fs", "original"])
        runs.insert_textbox("F3", "Preserve this shape")
        dictionary = workbook.add_worksheet("Dictionary")
        dictionary.write_row(0, 0, ["ASCII_NAME", "EXCEL_HEADER", "STATUS"])
        for row, values in enumerate(
            [
                ("", "Owner note", "EXCEL ONLY"),
                ("POL", "Run ID", "MAPPED"),
                ("MATRIX", "File", "MAPPED"),
                ("DESCRIPTION", "Title", "MAPPED"),
            ],
            1,
        ):
            dictionary.write_row(row, 0, values)
        workbook.add_worksheet("_Baseline").write_row(0, 0, ["KEY", "VALUE"])
    with ZipFile(book) as archive:
        opaque = {
            name: archive.read(name)
            for name in archive.namelist()
            if not name.startswith("xl/worksheets/sheet")
        }
    initial = tmp_path / "initial.json"
    main(
        [
            "preview",
            str(book),
            "--workspace",
            str(tmp_path),
            "--direction",
            "read",
            "--batch",
            str(initial),
        ]
    )
    main(["apply", str(initial)])
    source.write_bytes(source.read_bytes().replace(b"original", b"ASCII change"))
    batch = tmp_path / "read.json"
    main(
        [
            "preview",
            str(book),
            "--workspace",
            str(tmp_path),
            "--direction",
            "read",
            "--batch",
            str(batch),
        ]
    )
    main(["apply", str(batch)])
    snap = read_snapshot(book)
    assert snap.headers[:4] == ["Owner note", "Run ID", "File", "Title"]
    assert snap.rows[0][0].formula and snap.rows[0][0].value == "=1+1"
    assert snap.rows[0][3].value == "ASCII change"
    with ZipFile(book) as archive:
        assert all(archive.read(name) == data for name, data in opaque.items())


def test_stale_matrix_rejects_before_workbook_mutation(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = matrix(tmp_path)
    book = tmp_path / "runs.xlsx"
    main(["create", str(book), "--workspace", str(tmp_path)])
    batch = tmp_path / "read.json"
    main(
        [
            "preview",
            str(book),
            "--workspace",
            str(tmp_path),
            "--direction",
            "read",
            "--batch",
            str(batch),
        ]
    )
    original = book.read_bytes()
    source.write_bytes(source.read_bytes() + b"# later edit\n")
    changed_matrix = source.read_bytes()
    assert main(["apply", str(batch)]) == 2
    assert "changed after Preview" in capsys.readouterr().err
    assert book.read_bytes() == original
    assert source.read_bytes() == changed_matrix


def test_literal_ids_and_boolean_strings_survive_saved_workbook(tmp_path: Path) -> None:
    # GOAL033:excel:checks:literal_ids
    from pyflightstream.workspace.excel_file import read_snapshot

    source = matrix(tmp_path, description="false")
    book = tmp_path / "literal.xlsx"
    main(["create", str(book), "--workspace", str(tmp_path)])
    batch = tmp_path / "literal.json"
    main(
        [
            "preview",
            str(book),
            "--workspace",
            str(tmp_path),
            "--direction",
            "read",
            "--batch",
            str(batch),
        ]
    )
    main(["apply", str(batch)])
    snapshot = read_snapshot(book)
    assert snapshot.rows[0][snapshot.headers.index("POL")].value == "001"
    assert snapshot.rows[0][snapshot.headers.index("DESCRIPTION")].value == "false"
    assert snapshot.rows[0][snapshot.headers.index("SWEEP_VALUES")].value == "0,2,4"
    assert b"false" in source.read_bytes()


def test_create_and_preview_do_not_automatically_synchronize(tmp_path: Path) -> None:
    # GOAL033:excel:checks:no_auto_sync
    from pyflightstream.workspace.excel_file import read_snapshot

    source = matrix(tmp_path)
    original_matrix = source.read_bytes()
    book = tmp_path / "unsynchronized.xlsx"
    assert main(["create", str(book), "--workspace", str(tmp_path)]) == 0
    assert read_snapshot(book).rows == []
    original_workbook = book.read_bytes()
    batch = tmp_path / "inspect.json"
    # A preview that did nothing would leave both files unchanged too, so the
    # preview must succeed and produce its batch (Q0-tests-1-4).
    assert (
        main(
            [
                "preview",
                str(book),
                "--workspace",
                str(tmp_path),
                "--direction",
                "read",
                "--batch",
                str(batch),
            ]
        )
        == 0
    )
    assert batch.is_file() and batch.with_suffix(".html").is_file()
    assert book.read_bytes() == original_workbook
    assert source.read_bytes() == original_matrix


def test_public_saved_workbook_example(tmp_path: Path) -> None:
    import runpy

    example = Path(__file__).parents[2] / "docs/examples/_sources" / "excel_matrix_sync.py"
    outputs = runpy.run_path(str(example))["demonstrate"](tmp_path)
    assert outputs["workbook"].is_file()
    assert "Saved Excel edit" in outputs["matrix"].read_text()
    assert outputs["preview"].is_file()


@pytest.mark.parametrize("kind", ["duplicate", "formula"])
def test_dictionary_header_ambiguity_is_refused_before_preview(
    tmp_path: Path, kind: str, capsys: pytest.CaptureFixture[str]
) -> None:
    xlsxwriter = pytest.importorskip("xlsxwriter")

    source = matrix(tmp_path)
    original_matrix = source.read_bytes()
    book = tmp_path / "ambiguous.xlsx"
    with xlsxwriter.Workbook(book) as workbook:
        runs = workbook.add_worksheet("Runs")
        runs.write_row(0, 0, ["MATRIX", "POL"])
        dictionary = workbook.add_worksheet("Dictionary")
        dictionary.write_row(0, 0, ["ASCII_NAME", "EXCEL_HEADER", "STATUS"])
        dictionary.write_row(1, 0, ["MATRIX", "MATRIX", "MAPPED"])
        dictionary.write_row(2, 0, ["POL", "POL", "MAPPED"])
        if kind == "duplicate":
            dictionary.write_string(0, 3, "ASCII_NAME")
            dictionary.write_column(1, 3, ["MATRIX", "POL"])
        else:
            dictionary.write_formula(0, 0, '="ASCII_NAME"', None, "ASCII_NAME")
        workbook.add_worksheet("_Baseline").write_row(0, 0, ["KEY", "VALUE"])
    original = book.read_bytes()
    batch = tmp_path / "invalid.json"
    assert (
        main(
            [
                "preview",
                str(book),
                "--workspace",
                str(tmp_path),
                "--direction",
                "read",
                "--batch",
                str(batch),
            ]
        )
        == 2
    )
    error = capsys.readouterr().err
    assert "Dictionary" in error and "headers" in error
    assert book.read_bytes() == original and not batch.exists()
    assert source.read_bytes() == original_matrix


def _book(tmp_path: Path) -> Path:
    matrix(tmp_path)
    book = tmp_path / "runs.xlsx"
    assert main(["create", str(book), "--workspace", str(tmp_path)]) == 0
    return book


def _runs_part(book: Path) -> str:
    import re

    with ZipFile(book) as archive:
        workbook = archive.read("xl/workbook.xml").decode("utf-8")
        rels = archive.read("xl/_rels/workbook.xml.rels").decode("utf-8")
    sheet = re.search(r'<sheet\b[^>]*name="Runs"[^>]*', workbook)[0]
    rid = re.search(r'r:id="([^"]+)"', sheet)[1]
    rel = next(m[0] for m in re.finditer(r"<Relationship\b[^>]*>", rels) if f'"{rid}"' in m[0])
    return "xl/" + re.search(r'Target="([^"]+)"', rel)[1].lstrip("/").removeprefix("xl/")


def _rewrite_member(book: Path, member: str, transform) -> None:
    with ZipFile(book) as source:
        items = [(info, source.read(info)) for info in source.infolist()]
    with ZipFile(book, "w") as target:
        for info, data in items:
            target.writestr(info, transform(data) if info.filename == member else data)


def test_f1523_a_negative_cell_position_is_refused_not_an_endless_loop(tmp_path: Path) -> None:
    from pyflightstream.workspace.excel_file import patch_cells
    from pyflightstream.workspace.excel_sync import ExcelSyncError

    book = _book(tmp_path)
    original = book.read_bytes()
    for position in ((2, -1), (0, 1), (2, 0)):
        with pytest.raises(ExcelSyncError, match="not a worksheet position"):
            patch_cells(book, {"Runs": {position: "x"}})
    assert book.read_bytes() == original


def test_f1222_a_negative_shared_string_index_is_a_damaged_workbook(tmp_path: Path) -> None:
    from pyflightstream.workspace.excel_file import read_snapshot
    from pyflightstream.workspace.excel_sync import ExcelSyncError

    book = _book(tmp_path)
    runs = _runs_part(book)
    cell = b'<c r="A1" t="s"><v>-1</v></c>'
    _rewrite_member(
        book,
        runs,
        lambda data: data.replace(b"<sheetData>", b"<sheetData><row r='9'>" + cell + b"</row>", 1),
    )
    with pytest.raises(ExcelSyncError, match="negative"):
        read_snapshot(book)


def test_f1204_a_utf16_worksheet_is_an_excel_sync_error_not_a_decode_error(
    tmp_path: Path,
) -> None:
    from pyflightstream.workspace.excel_file import patch_cells
    from pyflightstream.workspace.excel_sync import ExcelSyncError

    book = _book(tmp_path)
    runs = _runs_part(book)
    _rewrite_member(book, runs, lambda data: data.decode("utf-8").encode("utf-16"))
    with pytest.raises(ExcelSyncError, match="encoding"):
        patch_cells(book, {"Runs": {(2, 1): "x"}})


def test_f1590_an_html_batch_name_is_refused_before_it_collides_with_its_preview(
    tmp_path: Path,
) -> None:
    book = _book(tmp_path)
    batch = tmp_path / "read.html"
    assert (
        main(
            ["preview", str(book), "--workspace", str(tmp_path), "--direction", "read"]
            + ["--batch", str(batch)]
        )
        == 2
    )
    assert not batch.exists()


def test_f735_an_edited_preview_token_cannot_place_recovery_files_outside(
    tmp_path: Path,
) -> None:
    import json

    book = _book(tmp_path)
    batch = tmp_path / "read.json"
    args = ["--workspace", str(tmp_path), "--direction", "read", "--batch", str(batch)]
    assert main(["preview", str(book), *args]) == 0
    data = json.loads(batch.read_text(encoding="utf-8"))
    data["preview"]["token"] = "../../escaped"
    batch.write_text(json.dumps(data), encoding="utf-8")
    assert main(["apply", str(batch)]) == 2
    assert not (tmp_path / ".excel-sync-recovery").exists()
    assert not (tmp_path.parent / "escaped").exists()


def test_f1589_check_reports_a_runs_row_without_identity(tmp_path: Path) -> None:
    from pyflightstream.workspace.excel_file import patch_cells, read_snapshot

    book = _book(tmp_path)
    assert main(["check", str(book)]) == 0
    headers = read_snapshot(book).headers
    patch_cells(book, {"Runs": {(2, headers.index("DESCRIPTION") + 1): "orphan row"}})
    assert main(["check", str(book)]) == 2


def test_x_f_0572_boolean_cells_read_as_their_words_and_error_cells_are_refused(
    tmp_path: Path,
) -> None:
    from pyflightstream.workspace.excel_file import read_snapshot
    from pyflightstream.workspace.excel_sync import ExcelSyncError

    def inject(cells: bytes):
        return lambda data: data.replace(
            b"<sheetData>", b"<sheetData><row r='9'>" + cells + b"</row>", 1
        )

    book = _book(tmp_path)
    runs = _runs_part(book)
    _rewrite_member(book, runs, inject(b'<c r="A9" t="b"><v>1</v></c><c r="B9" t="b"><v>0</v></c>'))
    row = read_snapshot(book).rows[-1]
    assert [row[0].value, row[1].value] == ["TRUE", "FALSE"]
    (tmp_path / "bad").mkdir()
    bad = _book(tmp_path / "bad")
    _rewrite_member(bad, runs, inject(b'<c r="A9" t="e"><v>#N/A</v></c>'))
    with pytest.raises(ExcelSyncError, match=r"A9.*#N/A"):
        read_snapshot(bad)


def _previewed(tmp_path: Path, name: str) -> tuple[Path, Path]:
    matrix(tmp_path)
    book = tmp_path / f"{name}.xlsx"
    main(["create", str(book), "--workspace", str(tmp_path)])
    batch = tmp_path / f"{name}.json"
    main(
        [
            "preview",
            str(book),
            "--workspace",
            str(tmp_path),
            "--direction",
            "read",
            "--batch",
            str(batch),
        ]
    )
    return book, batch


def test_x_f_1314_a_repeated_cancel_says_so(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, batch = _previewed(tmp_path, "twice")
    assert main(["cancel", str(batch)]) == 0
    capsys.readouterr()
    assert main(["cancel", str(batch)]) == 2
    assert "already cancelled" in capsys.readouterr().err


def test_x_f_1358_a_token_that_is_not_a_package_token_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    import json

    _, batch = _previewed(tmp_path, "token")
    payload = json.loads(batch.read_text(encoding="utf-8"))
    payload["preview"]["token"] = "../../escape"
    batch.write_text(json.dumps(payload), encoding="utf-8")
    assert main(["apply", str(batch)]) == 2
    assert "token" in capsys.readouterr().err
    assert not (tmp_path / "escape").exists()


def test_x_f_0586_a_line_separator_inside_a_cell_does_not_split_its_record(tmp_path: Path) -> None:
    from pyflightstream.workspace.excel_bridge import read_request

    request = tmp_path / "request.tsv"
    value = "a" + chr(0x2028) + "b" + chr(0x0B) + "c" + chr(0x0C) + "d" + chr(0x85) + "e"
    request.write_text("META" + chr(9) + "note" + chr(9) + value + chr(10), encoding="utf-8")
    metadata, _ = read_request(request)
    assert metadata["note"] == value
