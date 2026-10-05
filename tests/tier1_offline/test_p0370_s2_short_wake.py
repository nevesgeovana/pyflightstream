"""A positive target wake length must advance the solver at least once."""

import pytest

from pyflightstream.cases import ReferenceData, SimCase, SweepAxis
from pyflightstream.cases.workflows import rotor_time_stepping


@pytest.mark.parametrize("length", ["1e-12", "1e-320"])
def test_a_positive_sub_step_wake_resolves_one_step(length):
    """P0370-S2-RUN-WAKE (FR-422): ceil of a positive sub-step duration is one."""
    case = SimCase(
        sim_id="1",
        aircraft="rotor",
        recipe="unsteady_rotor",
        sweep=SweepAxis(type="alpha", values=[0.0]),
        reference=ReferenceData(area=1.0, length=1.0, rotor_diameter=2.0),
        variables={
            "VELOCITY": "30",
            "RPM": "1200",
            "DELTA_THETA": "10",
            "RUN_WAKE_LENGTH_R": length,
        },
    )
    stepping = rotor_time_stepping(case)
    assert stepping.time_iterations == 1
    assert stepping.run_wake.time_iterations == 1
    assert stepping.run_wake.revolutions == pytest.approx(1 / 36)
