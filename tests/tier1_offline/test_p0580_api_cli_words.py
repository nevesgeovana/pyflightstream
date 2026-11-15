"""The command word and flags of the console scripts (API-058-01b, 02, 03, 06)."""

from __future__ import annotations

import importlib

import pytest

from pyflightstream.run.cli import main as matrix_main


@pytest.mark.parametrize(
    "argv", [["convert"], ["--warning-refusals", "convert"], ["--warning-off", "convert", "x"]]
)
def test_the_retired_convert_is_refused_by_name_past_the_global_flags(argv, capsys):
    assert matrix_main(argv) == 2
    assert "Campaign-file conversion is not supported" in capsys.readouterr().err


@pytest.mark.parametrize("module", ["pyflightstream.workspace.cli", "pyflightstream.run.cli"])
def test_no_top_level_option_takes_a_value(module):
    """The command word is the first token without a dash (_cli.delegated_entry, refused_command).

    That is only right while no global option takes a value: a value would be read as the word.
    A global option that takes one must make those two skip it, and this test then says so.
    """
    parser = importlib.import_module(module)._build_parser()
    valued = [
        action.option_strings
        for action in parser._actions
        if action.option_strings and action.nargs != 0
    ]
    assert valued == []
