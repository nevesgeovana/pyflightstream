"""P0400-RESULTS (PFS-2105.044): the condition binding at the exact half count of the print."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from pyflightstream.results.conditions import bind_conditions

pytestmark = pytest.mark.requirement("P0400-RESULTS-CONDITIONS")


@dataclass
class _Printed:
    """The three fields the binding reads, and nothing else."""

    angle_of_attack_deg: float = 2.0
    sideslip_deg: float = 0.0
    freestream_velocity_m_s: float = 30.0


def test_p0400_results_half_count_is_within_the_print_tolerance():
    """P0400-RESULTS (PFS-2105.044): requested 0.0625 printed 0.063 is rounding, not a mismatch."""
    binding = bind_conditions(
        {"alpha": 0.0625, "velocity": 30.0625},
        reported=_Printed(angle_of_attack_deg=0.063, freestream_velocity_m_s=30.063),
    )
    alpha = next(check for check in binding.checks if check.axis == "alpha")
    assert alpha.deviation > alpha.tolerance, (
        "the control: binary floating point puts the difference just past 5e-4"
    )
    assert binding.mismatch_free, binding.describe()


def test_p0400_results_one_count_past_the_half_is_still_a_mismatch():
    """P0400-RESULTS (PFS-2105.044): the slack absorbs representation, not a real offset."""
    binding = bind_conditions({"alpha": 0.0624}, reported=_Printed(angle_of_attack_deg=0.063))
    assert not binding.mismatch_free
