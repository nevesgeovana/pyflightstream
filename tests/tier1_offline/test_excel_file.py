# GEOVERSE_HEADER
# file_version: "1.0.1"
# file_role: macro-free-workbook-roundtrip-tests
# last_modified_at: 2026-09-28T00:24:36.721Z
# last_modified_by: OpenAI / Codex / unknown / primary-agent
# dependencies: [pyflightstream.workspace.excel, pyflightstream.workspace.excel_file]
# authority: geoverse-goddess-control-plane
# status: active
# confidentiality: public
# change_summary: Check CLI refusal status and stderr while retaining unchanged-file guarantees.
# revision_source: git
from pathlib import Path
from zipfile import ZipFile

import pytest

from pyflightstream.workspace.excel import main

from .test_excel_sync import matrix


def test_macro_free_factory_and_bidirectional_cli(tmp_path: Path) -> None:
    # GOAL033:excel:checks:cli_sync_roundtrip
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
    import xlsxwriter

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
    main(["create", str(book), "--workspace", str(tmp_path)])
    assert read_snapshot(book).rows == []
    original_workbook = book.read_bytes()
    batch = tmp_path / "inspect.json"
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
    assert book.read_bytes() == original_workbook
    assert source.read_bytes() == original_matrix


def test_public_saved_workbook_example(tmp_path: Path) -> None:
    import runpy

    example = Path(__file__).parents[2] / "examples" / "excel_matrix_sync.py"
    outputs = runpy.run_path(str(example))["demonstrate"](tmp_path)
    assert outputs["workbook"].is_file()
    assert "Saved Excel edit" in outputs["matrix"].read_text()
    assert outputs["preview"].is_file()


@pytest.mark.parametrize("kind", ["duplicate", "formula"])
def test_dictionary_header_ambiguity_is_refused_before_preview(
    tmp_path: Path, kind: str, capsys: pytest.CaptureFixture[str]
) -> None:
    import xlsxwriter

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
