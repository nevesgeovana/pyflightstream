"""P0400-WSCLI: the workspace command line says what it does, and reads settings where it parses."""

from __future__ import annotations

import pytest

from pyflightstream.run._cli_parsers import _build_parser, parsed
from pyflightstream.workspace import cli as workspace_cli


def test_p0400_wscli_archive_help_does_not_promise_a_status_check():
    """P0400-WSCLI (PFS-2081.21): archive reads no run status, so its help names a recorded
    simulation, not a completed one, and says the status is not read."""
    archive = workspace_cli._subparsers(workspace_cli._build_parser())["archive"]
    description = " ".join(archive.description.split())
    assert "completed simulation" not in description, description
    assert "does not read the status" in description, description


def test_p0400_wscli_an_abbreviated_workspace_is_refused_not_read_elsewhere(tmp_path, capsys):
    """P0400-WSCLI (PFS-2094.021): settings are read from the folder an exact --workspace
    names, so `--works PATH` is refused by the parse instead of parsing to PATH while the
    settings came from the current folder; the parser abbreviates again afterwards."""
    parser = _build_parser()
    with pytest.raises(SystemExit) as caught:
        parsed(parser, ["post", "--works", str(tmp_path)])
    assert caught.value.code == 2
    assert "--works" in capsys.readouterr().err
    assert parser.allow_abbrev and workspace_cli._subparsers(parser)["post"].allow_abbrev
    assert parsed(parser, ["post", "--workspace", str(tmp_path)]).workspace == str(tmp_path)
