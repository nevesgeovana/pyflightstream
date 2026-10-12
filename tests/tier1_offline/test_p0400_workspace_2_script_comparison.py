"""P0400-SCRIPTDRIFT: a command rendered after the last executed one is reported where it lands."""

from __future__ import annotations

from pyflightstream.workspace._script_comparison import compare_scripts, drift

EXECUTED = "SET_SOLVER_STEADY\nITERATIONS\n500\nSTART_SOLVER\n"


def test_p0400_scriptdrift_an_appended_command_is_not_reported_at_line_one(tmp_path):
    """P0400-SCRIPTDRIFT (PFS-2103.040): an insertion after the last executed command is at
    line 5 of a four-line script, not line 1."""
    comparison = compare_scripts(EXECUTED + "EXPORT_SOLVER_ANALYSIS_VTK\n", EXECUTED, tmp_path)
    described = drift(comparison, tmp_path, [])
    assert described.startswith("line 5: ran '(nothing)', renders 'EXPORT_SOLVER"), described
