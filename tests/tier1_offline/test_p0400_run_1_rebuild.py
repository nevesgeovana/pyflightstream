"""Tier 1, 0.40.0 lane run-1: ``rebuild`` reconstructs a local record's command line.

The local campaign of the 0.32.0 records tests: one steady point run here by a stand-in
solver whose executable is on this machine, then its runs.json lost. No solver runs.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pyflightstream.run import records
from tests.tier1_offline.test_p0320_records import _local_campaign, _lose_the_manifest


def _set_hidden(matrix: Path, value: str) -> None:
    """Write ``value`` in the HIDDEN cell of every row of a pipe-table matrix."""
    lines = matrix.read_text(encoding="utf-8").splitlines()
    header = [cell.strip() for cell in lines[0].split("|")]
    column = header.index("HIDDEN")
    out = lines[:2]
    for line in lines[2:]:
        cells = line.split("|")
        if len(cells) == len(header) and line.strip() and not line.lstrip().startswith("#"):
            width = len(cells[column])
            cells[column] = f" {value}".ljust(width)
        out.append("|".join(cells))
    matrix.write_text("\n".join(out) + "\n", encoding="utf-8")


@pytest.mark.parametrize(("hidden", "flag"), [("0", False), ("1", True)])
def test_p0400_a_rebuilt_command_line_follows_the_rows_hidden_column(
    tmp_path, monkeypatch, hidden, flag
):
    """P0400-REBUILD-ARGV (PFS-2103.004): one reconstruction, from SCRIPT_ARGUMENT and HIDDEN.

    With the executable on this machine the argv was always ``-hidden``, the row's HIDDEN 0
    notwithstanding, and without it never: the record depended on the rebuilding machine.
    """
    workspace, matrix, original = _local_campaign(tmp_path, monkeypatch)
    _set_hidden(matrix, hidden)
    _lose_the_manifest(workspace)
    (rebuilt,) = records.rebuild(workspace.root)["records"]
    argv = rebuilt["argv"]
    assert argv[0] == original["fs_exe"] and argv[-2] == "-script", argv
    assert ("-hidden" in argv) is flag, argv
    assert rebuilt["executor"]["argv"] == argv
