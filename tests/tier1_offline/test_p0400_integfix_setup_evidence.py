"""Tier 1, 0.40.0 integration fixes: the setup evidence reads the command database alone."""

from __future__ import annotations

import pytest

from pyflightstream.commands import CommandRegistry, Status
from pyflightstream.workspace.setup_standards import render_guidelines, setup_entry_evidence

REPORT = "reports/compat/CMP-2026-09-27-setup-parser.md"
COMMANDS = {
    "wake_relaxation": "SET_WAKE_RELAXATION",
    "wake_streamwise_agglomeration": "SET_WAKE_STREAMWISE_AGGLOMERATION",
    "adverse_gradient_boundary_layer": "SOLVER_SET_ADVERSE_GRADIENT_BOUNDARY_LAYER",
}


@pytest.mark.parametrize("key", sorted(COMMANDS))
@pytest.mark.parametrize("build", ["26.123", "26.124"])
def test_p0400_a_parser_refusal_is_a_database_row_not_a_literal(key, build):
    """P0400-SETUP-PARSER-ROWS (PFS-2084.002): the 26.123/26.124 refusals are version rows.

    The workspace layer appended the parser probe's evidence from a literal set of
    builds and keys while the command database held no row for either build; the
    database now records each as removed, citing the probe, and the evidence line
    reads it from there.
    """
    row = CommandRegistry.load().commands[COMMANDS[key]].versions[build]
    assert row.status is Status.REMOVED
    assert row.probe_ref == REPORT
    available, said = setup_entry_evidence(key, build)
    assert not available
    assert f"build {build}: removed" in said and REPORT in said, said


def test_p0400_the_guidelines_carry_no_parser_literal():
    """P0400-SETUP-PARSER-ROWS (PFS-2084.002): render_guidelines repeated the literal."""
    assert "Native parser-only observations" not in render_guidelines("26.124")
