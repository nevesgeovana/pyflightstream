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
