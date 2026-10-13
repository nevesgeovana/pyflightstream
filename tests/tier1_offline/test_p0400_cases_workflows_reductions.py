"""P0400-CW-REDUCTIONS: the windows a point record carries for its reductions.

0.40.0 items PFS-2104.011 (the block is the blade count, never the periodic
copies), PFS-2095.007 and PFS-2081.33 (an averaging window the clock cannot
resolve is a recorded skip, as the docstring says, not an exception),
PFS-2100.022 (a window cut to the run says so), PFS-2095.006 (a left-handed
rotor spins) and PFS-2081.20 (a rotor's revolution comes from the azimuthal
step where the clock states one).
"""

from __future__ import annotations

import pytest

from pyflightstream.cases import (
    BladeDatum,
    CampaignConfigError,
    ReferenceData,
    RotorBlock,
    SimCase,
    SweepAxis,
)
from pyflightstream.cases.workflows import export_window, reduction_windows
from pyflightstream.cases.workflows._reductions import _blade_count

FOUR = RotorBlock(
    alias="ROTOR",
    x_m=0.0,
    y_m=0.0,
    z_m=0.0,
    axis="X",
    diameter_m=1.0,
    families_general=[],
    families_blades=["Blade1", "Blade2", "Blade3", "Blade4"],
    blade1=BladeDatum(azimuth_deg=0.0, zero="Y"),
)


def _row(workflow: str = "unsteady_rotor", **variables: str) -> SimCase:
    stated: dict[str, str | float | int | bool] = {
        "WORKFLOW": workflow,
        "VELOCITY": "30.0",
        "DELTA_THETA": "5",
        "REVOLUTIONS": "4",
        "LAST_REVS_AVG": "1",
        "RPM": "1200",
        "ROTOR_AXIS": "X",
    }
    if workflow == "unsteady":
        stated = {
            "WORKFLOW": workflow,
            "VELOCITY": "30.0",
            "DELTA_TIME": "0.001",
            "TIME_ITERATIONS": "720",
        }
    stated.update(variables)
    return SimCase(
        sim_id="7101",
        aircraft="RotorRig",
        sweep=SweepAxis(type="alpha", values=[0.0]),
        recipe=workflow,
        variables=stated,
        point={"alpha": 0.0},
        rotors={"ROTOR": FOUR} if workflow == "unsteady_rotor" else {},
    )


def test_p0400_cw_reductions_a_two_of_four_sector_has_four_blades():
    """P0400-CW-REDUCTIONS (PFS-2104.011): PERIODIC_COPIES 2 is what the file is, not the rotor."""
    requirement = "P0400-CW-REDUCTIONS"
    case = _row(SYMMETRY="PERIODIC", PERIODIC_COPIES="2")
    assert _blade_count(case) == 4, requirement
    plan = reduction_windows(case)
    assert plan is not None
    assert plan["blades"] == 4
    assert plan["per_blade"]["period_steps"] == 72 // 4


def test_p0400_cw_reductions_a_row_blade_count_against_the_block_is_refused():
    """P0400-CW-REDUCTIONS (PFS-2104.011): BLADES 3 beside a block of four names both."""
    requirement = "P0400-CW-REDUCTIONS"
    with pytest.raises(CampaignConfigError, match="BLADES: 3 .* 4 blade"):
        _blade_count(_row(BLADES="3"))
    assert _blade_count(_row(BLADES="4")) == 4, requirement


def test_p0400_cw_reductions_revolutions_without_a_clock_are_a_recorded_skip():
    """P0400-CW-REDUCTIONS (PFS-2095.007, PFS-2081.33): the refusal is recorded, not raised.

    The averaging window was read outside the try, so the run's point record
    raised where the docstring promised a skipped reduction with its reason.
    """
    requirement = "P0400-CW-REDUCTIONS"
    plan = reduction_windows(_row("unsteady", LAST_REVS_AVG="1"))
    assert plan is not None, requirement
    assert "no rotor speed" in plan["time_average"]["skipped"]


def test_p0400_cw_reductions_a_window_longer_than_the_run_says_it_was_cut():
    """P0400-CW-REDUCTIONS (PFS-2100.022): the record no longer calls a cut window the row's."""
    requirement = "P0400-CW-REDUCTIONS"
    plan = reduction_windows(_row("unsteady", LAST_ITERS_AVG="1000"))
    assert plan is not None, requirement
    average = plan["time_average"]
    assert average["windows"] == [[1, 720]]
    assert "cut to the whole run" in average["window_from"], average
    stated = reduction_windows(_row("unsteady", LAST_ITERS_AVG="100"))
    assert stated is not None
    assert "cut" not in stated["time_average"]["window_from"]


def test_p0400_cw_reductions_a_left_handed_rotor_spins():
    """P0400-CW-REDUCTIONS (PFS-2095.006): a signed speed is a speed of that magnitude."""
    requirement = "P0400-CW-REDUCTIONS"
    window = export_window(revolutions=1.0, rpm=-1200.0, delta_time_s=0.0001, time_iterations=720)
    assert window.steps == 500, requirement
    assert window.steps_per_revolution == pytest.approx(500.0)


def test_p0400_cw_reductions_a_stationary_public_window_has_no_revolution():
    """P0400-CW-REDUCTIONS (PFS-2095.006): a step window at rest has no angular clock."""
    requirement = "P0400-CW-REDUCTIONS"
    window = export_window(steps=10, rpm=0.0, delta_time_s=0.001, time_iterations=20)
    assert window.steps_per_revolution is None, requirement


LIFTER = FOUR.model_copy(update={"alias": "LIFTER", "axis": "Z"})
PUSHER = FOUR.model_copy(
    update={"alias": "PUSHER", "families_blades": ["P1", "P2", "P3"], "diameter_m": 1.8}
)


def test_p0400_cw_reductions_a_rotors_revolution_is_counted_from_the_azimuthal_step():
    """P0400-CW-REDUCTIONS (PFS-2081.20): 1.5 degrees a step is 240 steps a turn, exactly.

    From the seconds derived from that step, 60 / (rpm dt) read
    240.00000000000003 for the clock rotor.
    """
    requirement = "P0400-CW-REDUCTIONS"
    case = SimCase(
        sim_id="9201",
        aircraft="WORK",
        recipe="unsteady_rotor",
        sweep=SweepAxis(type="alpha", values=[0.0]),
        rotors={"LIFTER": LIFTER, "PUSHER": PUSHER},
        variables={
            "WORKFLOW": "unsteady_rotor",
            "VELOCITY": "30.0",
            "DELTA_THETA": "1.5",
            "REVOLUTIONS": "8",
            "LAST_REVS_AVG": "1",
            "CLOCK_MOTION": "LIFTER",
        },
        motions=[
            {"MOVING_BC_ALIAS": "LIFTER", "RPM": "473.1723"},
            {"MOVING_BC_ALIAS": "PUSHER", "RPM": "900"},
        ],
        reference=ReferenceData(area=16.0, length=1.6, span_m=10.0),
        point={"alpha": 0.0},
    )
    plan = reduction_windows(case)
    assert plan is not None, requirement
    rotors = plan["rotors"]
    assert rotors["LIFTER"]["steps_per_revolution"] == 240.0
    assert rotors["PUSHER"]["steps_per_revolution"] == pytest.approx(240.0 * 473.1723 / 900.0)
