"""Tier 1: the matrix upgrade edits only what its stage names and counts data rows (0.40.0)."""

from pathlib import Path

import pytest

from pyflightstream.cases import _matrix_upgrade
from pyflightstream.cases._matrix_layouts import _LAYOUT_0_15_0
from pyflightstream.cases.matrix import MATRIX_COLUMNS, MatrixError, upgrade_matrix

FIXTURES = Path(__file__).parent / "fixtures"


def test_p0400_upgrade_leaves_a_current_layout_file_unchanged(tmp_path):
    """P0400-GEOMETRY-ANCHOR (PFS-2096.001): free text naming GEOMETRY is not a file name."""
    row = dict.fromkeys(MATRIX_COLUMNS, "NA")
    row.update(
        POL="9001", DESCRIPTION="see GEOMETRY: baseline", VAR_NAMES_VALUES="NOTE_GEOMETRY: blade"
    )
    path = tmp_path / "current.fs"
    path.write_bytes((" | ".join(row) + "\n" + " | ".join(row.values()) + "\n").encode("utf-8"))
    assert upgrade_matrix(path) == path.read_bytes()


def test_p0400_geometry_stage_renames_only_the_geometry_pair_of_the_free_cell():
    """P0400-GEOMETRY-ANCHOR (PFS-2096.001): on an older layout only the GEOMETRY key is renamed."""
    cells = dict.fromkeys(_LAYOUT_0_15_0, "NA")
    cells.update(
        DESCRIPTION="see GEOMETRY: baseline",
        VAR_NAMES_VALUES="NOTE_GEOMETRY: blade / GEOMETRY: wing / VELOCITY: 30.0",
    )
    data = (" | ".join(cells) + "\n" + " | ".join(cells.values()) + "\n").encode("utf-8")
    renamed = _matrix_upgrade._name_geometry_files(data)
    assert b"see GEOMETRY: baseline |" in renamed
    assert b"NOTE_GEOMETRY: blade /" in renamed
    assert b"GEOMETRY: wing.fsm / VELOCITY" in renamed


def test_p0400_layout_0_9_0_upgrade_counts_data_rows_from_one(tmp_path):
    """P0400-UPGRADE-ROW (PFS-2100.009): the first data row is data row 1, not row 2."""
    lines = (FIXTURES / "pfs202609_matrix15.fs").read_text(encoding="utf-8").splitlines()
    first = next(index for index, line in enumerate(lines) if line.startswith("9001"))
    lines[first] = lines[first].rsplit("|", 1)[0]
    path = tmp_path / "short.fs"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(MatrixError, match=r"data row 1 of .* holds 14 cells against the 15"):
        upgrade_matrix(path)
