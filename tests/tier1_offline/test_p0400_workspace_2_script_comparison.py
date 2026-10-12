"""P0400-SCRIPTDRIFT: a command rendered after the last executed one is reported where it lands."""

from __future__ import annotations

from pyflightstream.workspace._script_comparison import _changed_commands, _Comparison, drift

EXECUTED = ["SET_SOLVER_STEADY", "ITERATIONS", "500", "START_SOLVER"]


def test_p0400_scriptdrift_an_appended_command_is_not_reported_at_line_one(tmp_path):
    """P0400-SCRIPTDRIFT (PFS-2103.040): an insertion after the last executed command is at
    line 5 of a four-line script, not line 1."""
    comparison = _Comparison(
        same=False,
        run_root=None,
        rendered=[*EXECUTED, "EXPORT_SOLVER_ANALYSIS_VTK"],
        executed=list(EXECUTED),
    )
    assert _changed_commands(comparison) == [(4, "", "EXPORT_SOLVER_ANALYSIS_VTK")]
    assert drift(comparison, tmp_path, []).startswith("line 5: ran '(nothing)'")
