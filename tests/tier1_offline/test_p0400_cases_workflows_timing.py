"""P0400-CW-TIMING: the explicit clock of a rotor row, at rest and out of bounds.

PFS-2095.008 and PFS-2097.005 of the 0.40.0 release: a stationary rotor
stated with the explicit clock divided by zero, and a zero or negative
explicit step or count was emitted to the solver.
"""

from __future__ import annotations

import pytest

from pyflightstream.cases import BladeDatum, CampaignConfigError, RotorBlock, SimCase, SweepAxis
from pyflightstream.cases.workflows import (
    build_script,
    reduction_windows,
    rotor_time_stepping,
    unsteady_time_stepping,
)
from pyflightstream.script import Script

ROTOR = RotorBlock(
    alias="ROTOR",
    x_m=0.1,
    y_m=0.2,
    z_m=0.3,
    axis="X",
    rpm_sign=1,
    diameter_m=3.6576,
    families_general=[],
    families_blades=["Blade1"],
    blade1=BladeDatum(azimuth_deg=0.0, zero="Y"),
)


def _case(workflow: str, **overrides: str | None) -> SimCase:
    variables: dict[str, str | float | int | bool] = {
        "WORKFLOW": workflow,
        "VELOCITY": "30.0",
        "DELTA_TIME": "0.0001",
        "TIME_ITERATIONS": "720",
        "LAST_ITERS_AVG": "10",
    }
    if workflow == "unsteady_rotor":
        variables.update({"RPM": "1200", "ROTOR_AXIS": "X", "BLADES": "1"})
    for key, value in overrides.items():
        if value is None:
            variables.pop(key, None)
        else:
            variables[key] = value
    return SimCase(
        sim_id="7001",
        aircraft="RotorRig",
        sweep=SweepAxis(type="alpha", values=[0.0]),
        recipe=workflow,
        outputs=["loads_a+00.0.txt"],
        variables=variables,
        point={"alpha": 0.0},
        rotors={ROTOR.alias: ROTOR} if workflow == "unsteady_rotor" else {},
    )


def test_p0400_cw_timing_a_rotor_at_rest_on_the_explicit_clock_has_no_revolution():
    """P0400-CW-TIMING (PFS-2095.008): RPM 0 with DELTA_TIME and TIME_ITERATIONS builds.

    The stationary-rotor refusal tells the user to write exactly this clock,
    and before the fix it raised a bare ZeroDivisionError from the property.
    """
    requirement = "P0400-CW-TIMING"
    case = _case("unsteady_rotor", RPM="0")
    stepping = rotor_time_stepping(case)
    assert stepping.rpm == 0.0, requirement
    assert stepping.steps_per_revolution is None
    windows = reduction_windows(case)
    assert windows["steps_per_revolution"] is None
    assert windows["time_iterations"] == 720
    script = Script("26.124")
    build_script(case, script)
    assert "SET_SOLVER_UNSTEADY" in script.render()


@pytest.mark.parametrize("workflow", ["unsteady_rotor", "unsteady"])
@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("DELTA_TIME", "0"),
        ("DELTA_TIME", "-0.01"),
        ("TIME_ITERATIONS", "0"),
        ("TIME_ITERATIONS", "-3"),
    ],
)
def test_p0400_cw_timing_a_non_positive_explicit_clock_is_refused_by_name(workflow, key, value):
    """P0400-CW-TIMING (PFS-2097.005): both explicit branches bound the pair, naming the key."""
    requirement = "P0400-CW-TIMING"
    case = _case(workflow, **{key: value})
    stepping = rotor_time_stepping if workflow == "unsteady_rotor" else unsteady_time_stepping
    with pytest.raises(CampaignConfigError, match=f"'7001' declares {key} as") as refusal:
        stepping(case)
    with pytest.raises(CampaignConfigError, match=key):
        build_script(case, Script("26.124"))
    assert str(refusal.value), requirement
