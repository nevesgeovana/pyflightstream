"""Tier 1: the reductions read each rotor's blade count from its own declaration (FR-68).

Her design of 2026-09-10, PFS-2035.11, AMENDING PFS-2015.04.01 which reads
the count from `PERIODIC_COPIES` at 0.14.0.

TWO HALVES, and the first is not in the requirement's text because nothing
had measured it. A 0.15.0 transition row states its speeds in MOTIONS and
carries no `RPM` of its own, so the window reader found no speed and EVERY
reduction of the point was skipped, the time average included. The second
half is the requirement as written: a row turning several rotors reduces
each over its OWN blade passage, and the files name the rotor.

The defect the second half is against does not announce itself. Reducing
the pusher over the lifters' passage writes the file, with the right
columns, averaged over the wrong window.
"""

from __future__ import annotations

import pytest

from pyflightstream.cases import EngineBlock, ReferenceData, SimCase, SweepAxis
from pyflightstream.cases.workflows import reduction_windows


def rotor(alias: str, general: list[str], blades: int, diameter: float) -> EngineBlock:
    """One engine block, its blades named one per entry as the reference declares them."""
    return EngineBlock(
        alias=alias,
        x_m=0.0,
        y_m=0.0,
        z_m=0.0,
        axis="Z",
        diameter_m=diameter,
        families_general=general,
        families_blades=[f"{alias}_B{number}" for number in range(1, blades + 1)],
    )


#: Four blades on the lifter and three on the pusher, deliberately unequal:
#: a count taken from the row rather than from each block gives one of the
#: two the other's passage, and the assertion below could not tell.
LIFTER = rotor("LIFT_L1", ["LH_L1"], 4, 1.2)
PUSHER = rotor("PUSHER", ["PH"], 3, 1.8)


def transition_case(**overrides) -> SimCase:
    """A row that turns the lifter and the pusher at different speeds."""
    variables: dict[str, str | float | int | bool] = {
        "WORKFLOW": "unsteady_rotor",
        "VELOCITY": "30.0",
        "DELTA_TIME": "0.0001",
        "TIME_ITERATIONS": "720",
        "CLOCK_MOTION": "LIFT_L1",
    }
    fields: dict[str, object] = {
        "sim_id": "9201",
        "aircraft": "WORK",
        "recipe": "unsteady_rotor",
        "sweep": SweepAxis(type="alpha", values=[0.0]),
        "engines": {"LIFT_L1": LIFTER, "PUSHER": PUSHER},
        "variables": variables,
        "motions": [
            {"MOVING_BC_ALIAS": "LIFT_L1", "RPM": "2200"},
            {"MOVING_BC_ALIAS": "PUSHER", "RPM": "900"},
        ],
        "reference": ReferenceData(area=16.0, length=1.6, span_m=10.0),
        "point": {"alpha": 0.0},
    }
    fields.update(overrides)
    return SimCase(**fields)


def test_a_row_that_states_its_speeds_in_motions_reduces_at_all():
    """HALF ONE. The window reader asked the ROW for one RPM and got none.

    Measured before the change on this very case: all three reductions
    skipped with "states no rotor speed, and a rotary motion turns at
    one", which is a true sentence about a row that states two.
    """
    plan = reduction_windows(transition_case())
    assert plan is not None
    assert "skipped" not in plan["time_average"], plan["time_average"]
    assert plan["time_iterations"] == 720


def test_each_rotor_reduces_over_its_own_blade_passage():
    """HALF TWO, and the whole of FR-68.

    The lifter turns at 2200 rev/min with four blades and the pusher at
    900 with three, so their passages are different lengths. This asserts
    the two are NOT EQUAL rather than asserting either number, so it
    cannot be satisfied by a constant, and then pins each against the
    arithmetic 60 / (rpm * dt) / blades.
    """
    plan = reduction_windows(transition_case())
    assert plan is not None
    rotors = plan["rotors"]
    assert set(rotors) == {"LIFT_L1", "PUSHER"}, rotors

    lifter, pusher = rotors["LIFT_L1"], rotors["PUSHER"]
    assert lifter["blades"] == 4 and pusher["blades"] == 3, "the count is each block's own"
    assert lifter["period_steps"] != pusher["period_steps"], (
        "both rotors were reduced over one passage, so one of them is averaged over a "
        "window that is not its own"
    )
    assert lifter["period_steps"] == round(60.0 / (2200 * 0.0001) / 4)
    assert pusher["period_steps"] == round(60.0 / (900 * 0.0001) / 3)


def test_the_windows_of_each_rotor_are_that_rotors_last_revolution():
    """A per-blade window per blade, contiguous, ending at the run's last step."""
    plan = reduction_windows(transition_case())
    assert plan is not None
    for alias, blades in (("LIFT_L1", 4), ("PUSHER", 3)):
        windows = plan["rotors"][alias]["per_blade"]["windows"]
        assert len(windows) == blades, (alias, windows)
        assert windows[-1][1] == 720, (alias, "the last window does not end at the run")
        for earlier, later in zip(windows, windows[1:], strict=False):
            assert later[0] == earlier[1] + 1, (alias, "the windows are not contiguous")


def test_the_row_says_where_its_reductions_went_rather_than_naming_a_count():
    """A row turning several rotors has no single blade passage, and says so.

    The older sentence tells the author to state `BLADES`, which on this
    row would be advice to write a number that is now two different
    numbers.
    """
    plan = reduction_windows(transition_case())
    assert plan is not None
    said = plan["per_blade"]["skipped"]
    assert "rotors" in said and "LIFT_L1" in said and "PUSHER" in said, said
    assert "BLADES" not in said, "the row is told to state a count it cannot have"


def test_a_row_turning_one_rotor_takes_the_count_from_that_rotors_block():
    """FR-68's own sentence: the reference already states it.

    A row naming ONE rotor by alias has said how many blades it has, so
    the flat keys resolve exactly as a row stating `BLADES: 4` does, and
    every file keeps the name it has always had.
    """
    case = transition_case(
        motions=[{"MOVING_BC_ALIAS": "LIFT_L1", "RPM": "2200"}],
        variables={
            "WORKFLOW": "unsteady_rotor",
            "VELOCITY": "30.0",
            "DELTA_TIME": "0.0001",
            "TIME_ITERATIONS": "720",
        },
    )
    plan = reduction_windows(case)
    assert plan is not None
    assert plan["blades"] == 4, "the row states no BLADES and its rotor declares four"
    assert "skipped" not in plan["per_blade"], plan["per_blade"]


def test_a_sector_row_reduces_over_the_whole_wheel():
    """FR-68's second paragraph: a mesh carrying one blade of four reduces over four.

    The count is the length of `families_blades` and not a property of the
    file, which is the same sentence FR-61 stands on from the other side:
    there the mesh's own blades are the DIVISOR of the copy count, here
    the reference's are the count itself. The two read the same list and
    cannot give different answers.
    """
    case = transition_case(
        motions=[{"MOVING_BC_ALIAS": "LIFT_L1", "RPM": "2200"}],
        variables={
            "WORKFLOW": "unsteady_rotor",
            "VELOCITY": "30.0",
            "DELTA_TIME": "0.0001",
            "TIME_ITERATIONS": "720",
            "SYMMETRY": "PERIODIC",
        },
    )
    plan = reduction_windows(case)
    assert plan is not None
    assert plan["blades"] == 4
    assert plan["rotors"]["LIFT_L1"]["blades"] == 4


def test_a_motion_naming_no_rotor_of_the_reference_leaves_the_others_reducing():
    """One motion that cannot be resolved is a drop-out, not the loss of the rest.

    WHAT THIS ALSO RECORDS, because it is why a branch is not here: a
    MOTION record whose alias the reference declares as no rotor is
    refused before it reaches the reduction, and the model refuses an
    engine block with no blade families, so a rotor block in this list
    ALWAYS has a count. A ROTATE record may name a non-rotor alias
    (FR-71); a motion may not. Both were measured while trying to build a
    case for the empty branch.
    """
    case = transition_case(
        motions=[
            {"MOVING_BC_ALIAS": "LIFT_L1", "RPM": "2200"},
            {"MOVING_BC_ALIAS": "NOT_A_ROTOR", "RPM": "600"},
        ],
    )
    plan = reduction_windows(case)
    assert plan is not None
    assert set(plan["rotors"]) == {"LIFT_L1"}, plan["rotors"]
    assert "skipped" not in plan["rotors"]["LIFT_L1"]["per_blade"]


@pytest.mark.parametrize("recipe", ["steady", "unsteady"])
def test_a_row_with_no_rotor_carries_no_per_rotor_block(recipe):
    """A row that states no motion reduces as today, which is FR-68's own sentence."""
    case = transition_case(recipe=recipe, motions=[])
    plan = reduction_windows(case)
    if plan is None:
        return  # steady rows carry no history at all
    assert "rotors" not in plan
