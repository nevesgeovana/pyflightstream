"""Tier 1: the phase-locked gate meets its minimum on a floating-point clock (0.40.0)."""

from pyflightstream.cases.pproc import PhaseLockedSpec
from pyflightstream.cases.windows import phase_locked_entry


def test_p0400_a_run_of_exactly_min_revolutions_is_not_skipped():
    """P0400-PHASE-GATE (PFS-2105.026): 1920 steps at 240.00000000000003 per turn are 8 turns."""
    gate = PhaseLockedSpec(min_revolutions=8, last_revolutions_avg=2)
    entry = phase_locked_entry(gate, last_step=1920, per_revolution=240.00000000000003, who="ROTOR")
    assert "skipped" not in entry, entry.get("skipped")
    assert entry["windows"] == [[1441, 1920]]
    short = phase_locked_entry(gate, last_step=1919, per_revolution=240.0, who="ROTOR")
    assert "skipped" in short
