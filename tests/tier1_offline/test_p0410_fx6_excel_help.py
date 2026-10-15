"""The saved-workbook commands explain each argument before any file is opened."""

import argparse

import pytest

from pyflightstream.workspace.excel import main


@pytest.mark.parametrize(
    "command", ["create", "preview", "apply", "cancel", "check"], ids=lambda x: f"P0410-{x}"
)
def test_p0410_excel_arguments_explain_their_inputs(command, monkeypatch, capsys):
    parsers = []
    original = argparse.ArgumentParser.parse_args

    def capture(parser, *args, **kwargs):
        parsers.append(parser)
        return original(parser, *args, **kwargs)

    monkeypatch.setattr(argparse.ArgumentParser, "parse_args", capture)
    with pytest.raises(SystemExit) as exit_info:
        main([command, "--help"])
    assert exit_info.value.code == 0
    subcommands = next(
        action for action in parsers[0]._actions if isinstance(action, argparse._SubParsersAction)
    )
    for action in subcommands.choices[command]._actions:
        assert action.help and action.help != argparse.SUPPRESS, action.dest
    assert "usage:" in capsys.readouterr().out
