# The evidence line of these requirements cites this module (docs/srs/functional-requirements.md):
# FR-156.
from pathlib import Path

import pytest

from pyflightstream.cases.matrix import _COLUMNS
from pyflightstream.workspace.excel_sync import (
    Cell,
    DictionaryEntry,
    ExcelSyncError,
    WorkbookSnapshot,
    apply_preview,
    dictionary_mapping,
    preview_sync,
    three_way_action,
)


def test_both_sides_changed_has_no_silent_winner() -> None:
    assert three_way_action("original", "file edit", "unsaved Excel edit") == "CONFLICT"


def matrix(tmp_path: Path, name: str = "batch.fs", description: str = "original") -> Path:
    folder = tmp_path / "inputs" / "matrices"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    values = {key: "-" for key in _COLUMNS}
    values.update(
        POL="001", DESCRIPTION=description, RUN="1", FS_BUILD="2026.1", SWEEP_VALUES="0,2,4"
    )
    path.write_bytes(
        (
            "# owner comment\r\n"
            + " | ".join(_COLUMNS)
            + "\r\n"
            + " | ".join(values[name] for name in _COLUMNS)
            + "\r\n"
        ).encode()
    )
    return path


def blank() -> WorkbookSnapshot:
    return WorkbookSnapshot(
        ["MATRIX", "POL"], [], [DictionaryEntry("MATRIX", "MATRIX"), DictionaryEntry("POL", "POL")]
    )


def consume(snapshot: WorkbookSnapshot, result: object) -> WorkbookSnapshot:
    headers = result.headers
    rows = [row + [Cell()] * (len(headers) - len(row)) for row in snapshot.rows]
    for change in result.changes:
        while len(rows) <= change.row:
            rows.append([Cell()] * len(headers))
        rows[change.row][change.column] = Cell(change.after)
    return WorkbookSnapshot(headers, rows, snapshot.dictionary + result.mappings, result.baseline)


def imported(tmp_path: Path) -> WorkbookSnapshot:
    snap = blank()
    return consume(snap, apply_preview(preview_sync(tmp_path, snap, direction="read"), snap))


def test_read_and_write_preserve_text_identity_sweeps_comments_and_custom_cells(
    tmp_path: Path,
) -> None:
    # GOAL033:excel:checks:both_directions
    path = matrix(tmp_path)
    snap = imported(tmp_path)
    assert snap.rows[0][snap.headers.index("POL")].value == "001"
    assert snap.rows[0][snap.headers.index("SWEEP_VALUES")].value == "0,2,4"
    snap.headers.append("My calculation")
    snap.rows[0].append(Cell("=1+1", formula=True))
    snap.rows[0][snap.headers.index("DESCRIPTION")] = Cell("unsaved edit")
    preview = preview_sync(tmp_path, snap, direction="write")
    assert preview.counts["EXCEL ONLY"] == 1
    result = apply_preview(preview, snap)
    assert not result.error
    assert path.read_bytes().startswith(b"# owner comment\r\n")
    assert b"unsaved edit" in path.read_bytes()
    assert Path(result.backups["batch.fs"]).read_bytes().find(b"original") > 0
    assert snap.rows[0][-1] == Cell("=1+1", True)


def test_column_reordering_and_exact_renaming(tmp_path: Path) -> None:
    # GOAL033:excel:checks:dictionary_by_name
    path = matrix(tmp_path)
    snap = imported(tmp_path)
    index = snap.headers.index("DESCRIPTION")
    snap.headers[index] = "Owner title"
    snap.dictionary = [
        DictionaryEntry(
            entry.ascii_name,
            "Owner title" if entry.ascii_name == "DESCRIPTION" else entry.excel_header,
        )
        for entry in snap.dictionary
    ]
    snap.headers.reverse()
    snap.rows[0].reverse()
    assert dictionary_mapping(snap)["DESCRIPTION"] == "Owner title"
    snap.rows[0][snap.headers.index("Owner title")] = Cell("renamed column edit")
    result = apply_preview(preview_sync(tmp_path, snap, direction="write"), snap)
    assert result.written == ["batch.fs"]
    # The edit landed in DESCRIPTION by name, not by position (Q0-tests-1-5).
    row = [cell.strip() for cell in path.read_text().splitlines()[-1].split("|")]
    assert row[_COLUMNS.index("DESCRIPTION")] == "renamed column edit"


def test_conflict_and_mapped_formula_block_apply(tmp_path: Path) -> None:
    # GOAL033:excel:checks:mapped_formula_refusal
    path = matrix(tmp_path)
    snap = imported(tmp_path)
    path.write_bytes(path.read_bytes().replace(b"original", b"ASCII edit"))
    snap.rows[0][snap.headers.index("DESCRIPTION")] = Cell("Excel edit")
    preview = preview_sync(tmp_path, snap, direction="read")
    assert preview.counts["CONFLICT"] == 1
    with pytest.raises(ExcelSyncError, match="CONFLICT"):
        apply_preview(preview, snap)
    snap.rows[0][snap.headers.index("DESCRIPTION")] = Cell("=1+1", True)
    assert not preview_sync(tmp_path, snap, direction="write").applicable


def test_stale_ascii_and_unsaved_cells_reject_apply(tmp_path: Path) -> None:
    # GOAL033:excel:checks:stale_preview_refusal
    path = matrix(tmp_path)
    snap = blank()
    preview = preview_sync(tmp_path, snap, direction="read")
    path.write_bytes(path.read_bytes() + b"# later change\r\n")
    with pytest.raises(ExcelSyncError, match="changed after Preview"):
        apply_preview(preview, snap)
    preview = preview_sync(tmp_path, snap, direction="read")
    snap.headers.append("new custom column")
    with pytest.raises(ExcelSyncError, match="Dictionary or baseline changed"):
        apply_preview(preview, snap)


def test_subset_reads_do_not_delete_other_matrix_rows(tmp_path: Path) -> None:
    # GOAL033:excel:checks:no_deletion
    matrix(tmp_path)
    matrix(tmp_path, "second.fs")
    snap = imported(tmp_path)
    assert len(snap.rows) == 2
    result = apply_preview(
        preview_sync(tmp_path, snap, direction="read", matrices=["batch.fs"]), snap
    )
    assert len(consume(snap, result).rows) == 2


def test_new_identity_adds_instead_of_deleting_old_ascii_row(tmp_path: Path) -> None:
    # GOAL033:excel:checks:matrix_pol_identity
    path = matrix(tmp_path)
    snap = imported(tmp_path)
    snap.rows[0][snap.headers.index("POL")] = Cell("002")
    result = apply_preview(preview_sync(tmp_path, snap, direction="write"), snap)
    assert result.written == ["batch.fs"]
    assert "001" in path.read_text() and "002" in path.read_text()


@pytest.mark.parametrize("headers", [["MATRIX", "MATRIX"], ["MATRIX", ""]])
def test_bad_headers_rejected(headers: list[str]) -> None:
    snap = blank()
    snap.headers = headers
    with pytest.raises(ExcelSyncError):
        dictionary_mapping(snap)


def test_dictionary_collision_and_path_escape_rejected(tmp_path: Path) -> None:
    # GOAL033:excel:checks:ambiguity_refusal
    matrix(tmp_path)
    snap = blank()
    snap.headers.append("DESCRIPTION")
    with pytest.raises(ExcelSyncError, match="collides"):
        preview_sync(tmp_path, snap, direction="read")
    with pytest.raises(ExcelSyncError, match="without directories"):
        preview_sync(tmp_path, blank(), direction="read", matrices=["../escape.fs"])


def test_legacy_union_and_schema_preserved_without_upgrade(tmp_path: Path) -> None:
    from pyflightstream.cases.matrix import _LEGACY_COLUMNS_15

    matrix(tmp_path)
    legacy = tmp_path / "legacy.fs"
    values = dict.fromkeys(_LEGACY_COLUMNS_15, "-")
    values.update(POL="007", RE="2.0", MACH="0.1", DESCRIPTION="old")
    original_header = " | ".join(_LEGACY_COLUMNS_15)
    legacy.write_text(
        original_header + "\n" + " | ".join(values[name] for name in _LEGACY_COLUMNS_15) + "\n"
    )
    snap = imported(tmp_path)
    assert {"RE", "MACH", "FLIGHT_CONDITION"} <= set(snap.headers)
    row = next(row for row in snap.rows if row[snap.headers.index("MATRIX")].value == "legacy.fs")
    row[snap.headers.index("DESCRIPTION")] = Cell("new")
    result = apply_preview(preview_sync(tmp_path, snap, direction="write"), snap)
    assert result.written == ["legacy.fs"]
    assert legacy.read_text().splitlines()[0] == original_header
    assert "new" in legacy.read_text()


def test_an_edit_to_a_column_the_legacy_layout_lacks_is_refused_not_skipped(
    tmp_path: Path,
) -> None:
    # Q0-src-workspace-3: the preview shows every decision; a silent skip is a defect.
    from pyflightstream.cases.matrix import _LEGACY_COLUMNS_15

    assert "FLIGHT_CONDITION" not in _LEGACY_COLUMNS_15
    legacy = tmp_path / "legacy.fs"
    values = dict.fromkeys(_LEGACY_COLUMNS_15, "-")
    values.update(POL="007", RE="2.0", MACH="0.1", DESCRIPTION="old")
    legacy.write_text(
        " | ".join(_LEGACY_COLUMNS_15)
        + "\n"
        + " | ".join(values[name] for name in _LEGACY_COLUMNS_15)
        + "\n"
    )
    matrix(tmp_path)
    snap = imported(tmp_path)
    row = next(row for row in snap.rows if row[snap.headers.index("MATRIX")].value == "legacy.fs")
    assert row[snap.headers.index("FLIGHT_CONDITION")].value == ""
    row[snap.headers.index("FLIGHT_CONDITION")] = Cell("MACH:0.2")
    preview = preview_sync(tmp_path, snap, direction="write")
    refused = [
        change
        for change in preview.changes
        if change.matrix == "legacy.fs" and change.ascii_name == "FLIGHT_CONDITION"
    ]
    assert [change.action for change in refused] == ["INVALID"]
    assert "legacy layout" in refused[0].detail
    assert not preview.applicable
    # An untouched current-only cell of a legacy row is not a decision to show.
    row[snap.headers.index("FLIGHT_CONDITION")] = Cell("")
    assert preview_sync(tmp_path, snap, direction="write").applicable


def test_duplicate_filename_across_locations_is_ambiguous(tmp_path: Path) -> None:
    nested = matrix(tmp_path)
    (tmp_path / "batch.fs").write_bytes(nested.read_bytes())
    with pytest.raises(ExcelSyncError, match="ambigu"):
        preview_sync(tmp_path, blank(), direction="read")


def test_macro_free_workbook_has_no_macro_controls(tmp_path: Path) -> None:
    from zipfile import ZipFile

    from pyflightstream.workspace import excel

    path = excel.create_workbook(tmp_path / "controls.xlsx", workspace=tmp_path)
    with ZipFile(path) as package:
        assert not any("vba" in name.lower() for name in package.namelist())
        assert not any("vmlDrawing" in name for name in package.namelist())
    with pytest.raises(ExcelSyncError, match="never overwritten"):
        excel.create_workbook(path, workspace=tmp_path)


def test_partial_write_reports_completed_files_and_exact_recovery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # GOAL033:excel:checks:recoverable_originals
    import os

    first = matrix(tmp_path)
    second = matrix(tmp_path, "second.fs")
    first_original, second_original = first.read_bytes(), second.read_bytes()
    snap = imported(tmp_path)
    for row in snap.rows:
        row[snap.headers.index("DESCRIPTION")] = Cell("changed")
    original_replace = os.replace

    def replace(source: str, target: Path) -> None:
        if target.name == "second.fs":
            raise PermissionError("synthetic second-file refusal")
        original_replace(source, target)

    monkeypatch.setattr(os, "replace", replace)
    result = apply_preview(preview_sync(tmp_path, snap, direction="write"), snap)
    assert result.written == ["batch.fs"]
    assert "second.fs" in result.error
    assert Path(result.backups["batch.fs"]).read_bytes() == first_original
    assert second.read_bytes() == second_original
    assert result.baseline == snap.baseline


def test_bridge_checks_unsaved_snapshot_and_invalidates_failed_preview(tmp_path: Path) -> None:
    # GOAL033:excel:checks:python_engine
    from pyflightstream.workspace.excel_bridge import bridge, escape, unescape

    path = matrix(tmp_path)
    request, response, batch = [
        tmp_path / name for name in ("request.tsv", "response.tsv", "preview.json")
    ]
    text = (
        "META\tworkspace\t"
        + escape(str(tmp_path))
        + "\nMETA\tdirection\tread\nHEADER\tMATRIX\nHEADER\tPOL\n"
        "DICTIONARY\tMATRIX\tMATRIX\tMAPPED\nDICTIONARY\tPOL\tPOL\tMAPPED\n"
    )
    request.write_text(text)
    assert bridge("preview", request, response, batch) == 0
    assert "CHANGE\tADD\tbatch.fs\t001" in response.read_text()
    request.write_text(text + "HEADER\tPOL\n")
    assert bridge("apply", request, response, batch) == 1
    assert "changed after Preview" in response.read_text()
    assert bridge("preview", request, response, batch) == 1
    assert not batch.exists()
    assert b"original" in path.read_bytes()
    literal = "a\\b\tline\nnext\rreturn"
    assert unescape(escape(literal)) == literal
