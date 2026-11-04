"""P0550-IDENTIFIERS: what a row states as IDENTIFIERS reaches the tables of the post alone.

A row writes ``IDENTIFIERS: {FLAP:0,TESTE:10}`` in its VAR_NAMES_VALUES cell. This module holds the
reader's half and the post's half, on real posts of the fixture campaigns; the run's half, a real
plan and run through the command line, is in ``test_run_cli.py``, beside its stub solver.
"""

from __future__ import annotations

import csv
import shutil
from pathlib import Path

import pytest

from pyflightstream._errors import PyflightstreamWarning
from pyflightstream.cases.matrix import MATRIX_COLUMNS, MatrixError, read_matrix
from pyflightstream.workspace import CampaignWorkspace, find_matrix

STATED = "IDENTIFIERS: {FLAP:0,TESTE:10}"


def _state(matrix: Path, by_pol: dict[str, str]) -> None:
    """Add to each row of ``by_pol`` the text given, the way a person edits the cell."""
    lines = []
    for line in matrix.read_text(encoding="utf-8").splitlines():
        cells = line.split("|")
        if cells[0].strip() in by_pol:
            last = cells[-1].rstrip()
            line = line.rstrip() + (" / " if last.strip() else " ") + by_pol[cells[0].strip()]
        lines.append(line)
    matrix.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _one_row(tmp_path: Path, variables: str, **stated: str) -> Path:
    cells = dict.fromkeys(MATRIX_COLUMNS, "NA")
    cells.update(
        POL="9001",
        HIDDEN="0",
        RUN="1",
        AIRCRAFT="Wing",
        DESCRIPTION="POLAR",
        FLIGHT_CONDITION="MACH:0.1, ALPHA:sweep",
        SWEEP_VALUES="0.0,2.0",
        FS_BUILD="MANUAL",
        WORKFLOW="LEGACY",
        VAR_NAMES_VALUES=variables,
    )
    cells.update(stated)
    path = tmp_path / "one.fs"
    path.write_text(" | ".join(cells) + "\n" + " | ".join(cells.values()) + "\n", encoding="utf-8")
    return path


def _table(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.reader(handle))
    return rows[0], [dict(zip(rows[0], row, strict=True)) for row in rows[1:]]


def _tables(root: Path) -> list[Path]:
    return sorted(root.rglob("*.csv"))


# ------------------------------------------------------------------ the reader


def test_p0550_identifiers_leave_the_variables_for_a_field_of_their_own(tmp_path):
    (row,) = read_matrix(_one_row(tmp_path, f"RECIPE: 003 / {STATED} / OUTPUTS: l_{{point}}.txt"))
    (plain,) = read_matrix(_one_row(tmp_path, "RECIPE: 003 / OUTPUTS: l_{point}.txt"))
    assert row.identifiers == {"FLAP": "0", "TESTE": "10"}
    assert row.variables == plain.variables
    assert plain.identifiers == {}


def test_p0550_identifier_values_are_text_as_written(tmp_path):
    cell = "IDENTIFIERS: {FLAP:0.10,RUN NAME:a/b,CLOCK:12:30,EMPTY:} / RECIPE: 003"
    (row,) = read_matrix(_one_row(tmp_path, cell))
    assert row.identifiers == {"FLAP": "0.10", "RUN NAME": "a/b", "CLOCK": "12:30", "EMPTY": ""}
    assert row.variables["RECIPE"] == "003"


@pytest.mark.parametrize(
    "value",
    [
        "FLAP",
        "FLAP:0",
        "{FLAP}",
        "{FLAP:0",
        "FLAP:0}",
        "{A:1}{B:2}",
        "{A:1} tail",
        "{:1}",
        "{A:1,A:2}",
        "{\"A\":1,'A':2}",
    ],
)
def test_p0550_a_malformed_identifiers_value_warns_and_states_none(tmp_path, value):
    """Nothing else of the row moves, the keys after a brace left open included."""
    with pytest.warns(PyflightstreamWarning, match="POL 9001: IDENTIFIERS"):
        (row,) = read_matrix(_one_row(tmp_path, f"IDENTIFIERS: {value} / RECIPE: 003"))
    assert row.identifiers == {}
    assert row.variables["RECIPE"] == "003"
    assert "IDENTIFIERS" not in row.variables


def test_p0550_the_key_stated_twice_follows_the_rule_of_every_key(tmp_path):
    path = _one_row(tmp_path, "IDENTIFIERS: {A:1} / RECIPE: 003 / IDENTIFIERS: {A:1}")
    with pytest.raises(MatrixError, match="'IDENTIFIERS' is stated twice"):
        read_matrix(path)


def test_p0550_a_key_that_only_holds_the_word_is_a_variable(tmp_path):
    (row,) = read_matrix(_one_row(tmp_path, "MY_IDENTIFIERS: 1 / IDENTIFIERS_X: 2 / RECIPE: 003"))
    assert row.identifiers == {}
    assert row.variables["MY_IDENTIFIERS"] == "1"
    assert row.variables["IDENTIFIERS_X"] == "2"


def test_p0550_identifiers_differing_between_the_two_homes_refuse_nothing(tmp_path):
    workspace = CampaignWorkspace.init(tmp_path / "camp")
    home = workspace.inputs_dir / "matrices"
    home.mkdir(parents=True, exist_ok=True)
    root = _one_row(workspace.root, "RECIPE: 003")
    other = home / "one.fs"
    shutil.copyfile(root, other)
    _state(other, {"9001": STATED})
    with pytest.warns(PyflightstreamWarning, match="differ in their IDENTIFIERS alone"):
        assert find_matrix(workspace.root, "one") is not None
