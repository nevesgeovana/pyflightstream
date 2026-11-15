"""The command word and flags of the console scripts (API-058-01b, 02, 03, 06)."""

from __future__ import annotations

import pytest

from pyflightstream.run.cli import main as matrix_main


@pytest.mark.parametrize(
    "argv", [["convert"], ["--warning-refusals", "convert"], ["--warning-off", "convert", "x"]]
)
def test_the_retired_convert_is_refused_by_name_past_the_global_flags(argv, capsys):
    assert matrix_main(argv) == 2
    assert "Campaign-file conversion is not supported" in capsys.readouterr().err
