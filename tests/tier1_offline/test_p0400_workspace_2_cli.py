"""P0400-WSCLI: the workspace command line says what it does, and reads settings where it parses."""

from __future__ import annotations

import pytest

from pyflightstream.run.cli import main as matrix_main
from pyflightstream.workspace.cli import main as workspace_main


def _exit(call) -> int:
    try:
        return call()
    except SystemExit as stopped:
        return int(stopped.code or 0)


def test_p0400_wscli_archive_help_does_not_promise_a_status_check(capsys):
    """P0400-WSCLI (PFS-2081.21): archive reads no run status, so its help names a recorded
    simulation, not a completed one, and says the status is not read."""
    assert _exit(lambda: workspace_main(["archive", "--help"])) == 0
    help_text = " ".join(capsys.readouterr().out.split())
    assert "completed simulation" not in help_text, help_text
    assert "does not read the status" in help_text, help_text


def test_p0400_wscli_an_abbreviated_workspace_is_refused_not_read_elsewhere(tmp_path, capsys):
    """P0400-WSCLI (PFS-2094.021): settings are read from the folder an exact --workspace
    names, so `--works PATH` is refused by the parse instead of parsing to PATH while the
    settings came from the current folder."""
    assert _exit(lambda: matrix_main(["post", "--works", str(tmp_path)])) == 2
    assert "unrecognized arguments: --works" in capsys.readouterr().err


@pytest.mark.parametrize("flag", ["--workspace", "--workspace="])
def test_p0400_wscli_the_exact_workspace_option_still_parses(tmp_path, capsys, flag):
    """P0400-WSCLI (PFS-2094.021): the exact spelling, either form, is not refused."""
    argv = ["post", flag + str(tmp_path)] if flag.endswith("=") else ["post", flag, str(tmp_path)]
    _exit(lambda: matrix_main(argv))
    assert "unrecognized arguments" not in capsys.readouterr().err
