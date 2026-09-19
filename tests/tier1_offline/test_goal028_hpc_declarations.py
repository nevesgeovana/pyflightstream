"""DECLARATION-LAST-WINS: one setting stated twice is refused, never resolved by order.

A row is refused rather than guessed. ``RPM:1000/RPM:2000`` kept 2000 in
silence, and a setup stating ``NITER`` beside ``iterations`` (two spellings of
one solver setting) resolved to whichever the file listed last.
"""

from __future__ import annotations

import pytest

from pyflightstream._errors import InputArtifactError
from pyflightstream.cases.matrix import MatrixError, _parse_variables
from pyflightstream.workspace.inputs import SetupArtifact
from pyflightstream.workspace.matrix import _solver_from_setup


def test_a_variable_stated_twice_in_one_cell_is_refused_naming_the_key() -> None:
    with pytest.raises(MatrixError) as refusal:
        _parse_variables("RPM:1000/DELTA_TIME:0.001/RPM:2000")
    sentence = str(refusal.value)
    assert "RPM" in sentence
    assert "1000" in sentence
    assert "2000" in sentence


def test_the_same_value_stated_twice_is_still_a_duplicate() -> None:
    # The refusal is about the declaration, not about whether the two agree:
    # agreeing today is the state the next edit breaks.
    with pytest.raises(MatrixError):
        _parse_variables("RPM:1000/RPM:1000")


def test_a_cell_stating_each_key_once_reads_as_written() -> None:
    assert _parse_variables("RPM:1000/DELTA_TIME:0.001") == {
        "RPM": "1000",
        "DELTA_TIME": "0.001",
    }


@pytest.mark.parametrize(
    "settings",
    [
        {"NITER": 100, "iterations": 500},
        {"iterations": 500, "NITER": 100},
    ],
)
def test_two_spellings_of_one_solver_setting_are_refused_in_either_order(
    settings: dict[str, object],
) -> None:
    with pytest.raises(InputArtifactError) as refusal:
        _solver_from_setup(SetupArtifact(settings=settings), "s900")
    sentence = str(refusal.value)
    assert "NITER" in sentence
    assert "iterations" in sentence
    assert "s900" in sentence


def test_one_spelling_of_the_setting_still_applies() -> None:
    assert _solver_from_setup(SetupArtifact(settings={"NITER": 100}), "s900").iterations == 100
    assert _solver_from_setup(SetupArtifact(settings={"iterations": 250}), "s900").iterations == 250


# --- THROUGH THE READER A CAMPAIGN ENTERS (release review of 0.24.0, QA-Q2) -------


def test_a_matrix_file_stating_a_key_twice_is_refused_by_the_public_reader(tmp_path) -> None:
    from pathlib import Path

    from pyflightstream.cases.matrix import read_matrix

    fixture = Path(__file__).parent / "fixtures" / "matrix.fs"
    text = fixture.read_text(encoding="utf-8")
    stated = "ADVANCE_RATIO: 1.7 /"
    assert text.count(stated) == 1, "the fixture moved; this test names one row's cell"
    # THE CONTROL: the file as committed reads.
    assert read_matrix(fixture)
    doubled = tmp_path / "matrix.fs"
    doubled.write_text(text.replace(stated, f"{stated} ADVANCE_RATIO: 1.9 /"), encoding="utf-8")
    with pytest.raises(MatrixError) as refusal:
        read_matrix(doubled)
    sentence = str(refusal.value)
    assert "ADVANCE_RATIO" in sentence and "1.7" in sentence and "1.9" in sentence


def test_a_setup_stating_two_spellings_is_refused_when_the_matrix_is_resolved(
    tmp_path,
) -> None:
    """The setup loader a campaign enters, not the private helper."""
    from pyflightstream.workspace.matrix import resolve_matrix
    from tests.tier1_offline.test_goal024_point_name import RECIPES, _matrix

    workspace, matrix = _matrix(
        tmp_path, condition="MACH:0.144, REmi:4.38, ALPHA:sweep", values="0.0"
    )

    def resolved():
        return resolve_matrix(matrix, workspace, name="dup", fs_version="26.120", recipes=RECIPES)

    # THE CONTROL: the library's setup, as committed, resolves.
    assert resolved().campaign.sims
    setup = workspace.inputs_dir / "setups" / "s002.toml"
    assert setup.is_file(), "the row names s002; the library moved"
    text = setup.read_text(encoding="utf-8")
    # The library's setup states the setting ONCE, as `iterations`; the second
    # spelling goes at the top, before any table, where the first one sits.
    assert "iterations = " in text and "NITER" not in text, text
    setup.write_text("NITER = 100\n" + text, encoding="utf-8")
    with pytest.raises(InputArtifactError) as refusal:
        resolved()
    sentence = str(refusal.value)
    assert "NITER" in sentence and "iterations" in sentence and "s002" in sentence
