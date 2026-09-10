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
    # PINNED AS LITERALS, not by restating the implementation's formula.
    # Written as `round(60.0 / (2200 * 0.0001) / 4)` this could not tell
    # rounding from truncation, because that expression is the code's own
    # (the QA lens, 2026-09-10). 272.727 / 4 = 68.18 truncates to the same
    # 68, so the lifter cannot discriminate either; the SEVEN-bladed rotor
    # in `test_a_period_whose_fraction_decides_is_rounded_not_truncated`
    # is the case that can.
    assert lifter["period_steps"] == 68
    assert pusher["period_steps"] == 222


def test_a_period_whose_fraction_decides_is_rounded_not_truncated():
    """A blade passage is the nearest whole number of steps, not the floor.

    272.727 steps per revolution over SEVEN blades is 38.96, which rounds
    to 39 and truncates to 38. The four-bladed fixture cannot tell the two
    apart, so the mutant that truncates survived it (the QA lens,
    2026-09-10).
    """
    seven = rotor("LIFT_L1", ["LH_L1"], 7, 1.2)
    plan = reduction_windows(transition_case(engines={"LIFT_L1": seven, "PUSHER": PUSHER}))
    assert plan is not None
    assert plan["rotors"]["LIFT_L1"]["period_steps"] == 39


@pytest.mark.parametrize("rpm", ["2200", "-2200"])
def test_a_rotor_turning_the_other_way_reduces_over_the_same_passage(rpm):
    """A blade passage is a DURATION, so the sign of the speed does not shorten it.

    Without the absolute value a negative rpm gives a negative revolution,
    the period rounds below one, and BOTH passage reductions of that rotor
    are skipped under a sentence saying the passage is under one time
    step, which is false about the case. `RPM_SIGN` is part of the
    vocabulary and a counter-rotating pair is an ordinary row (the QA
    lens, 2026-09-10).
    """
    case = transition_case(
        motions=[
            {"MOVING_BC_ALIAS": "LIFT_L1", "RPM": rpm},
            {"MOVING_BC_ALIAS": "PUSHER", "RPM": "900"},
        ]
    )
    plan = reduction_windows(case)
    assert plan is not None
    entry = plan["rotors"]["LIFT_L1"]
    assert entry["period_steps"] == 68, entry
    assert "skipped" not in entry["per_blade"], entry["per_blade"]


def test_a_rotor_that_does_not_turn_is_skipped_naming_it():
    """QA F3's reachable arm: a rotor at rest has no blade passage.

    Measured by the lens on the clean code: `PUSHER` at `RPM: 0` produces
    "turns 'PUSHER' at 0.0 rev/min with a solver step of 0.0001, so one
    blade passage of it has no length in steps", and no case reached it.
    """
    case = transition_case(
        motions=[
            {"MOVING_BC_ALIAS": "LIFT_L1", "RPM": "2200"},
            {"MOVING_BC_ALIAS": "PUSHER", "RPM": "0"},
        ]
    )
    plan = reduction_windows(case)
    assert plan is not None
    said = plan["rotors"]["PUSHER"]["per_blade"]["skipped"]
    assert "PUSHER" in said and "no length" in said, said
    assert "skipped" not in plan["rotors"]["LIFT_L1"]["per_blade"], "the lifter went with it"


def test_a_run_holding_no_whole_revolution_of_a_rotor_is_skipped_naming_it():
    """QA F3's second reachable arm: the run is shorter than that rotor's wheel."""
    case = transition_case(
        variables={
            "WORKFLOW": "unsteady_rotor",
            "VELOCITY": "30.0",
            "DELTA_TIME": "0.0001",
            "TIME_ITERATIONS": "300",
            "CLOCK_MOTION": "LIFT_L1",
        }
    )
    plan = reduction_windows(case)
    assert plan is not None
    said = plan["rotors"]["PUSHER"]["per_blade"]["skipped"]
    assert "PUSHER" in said and "complete revolution" in said, said
    assert "skipped" not in plan["rotors"]["LIFT_L1"]["per_blade"], "the lifter went with it"


def test_a_window_shorter_than_one_passage_of_a_rotor_is_skipped_naming_it():
    """QA F3's third arm: the row's window holds no whole passage of that rotor."""
    case = transition_case(
        variables={
            "WORKFLOW": "unsteady_rotor",
            "VELOCITY": "30.0",
            "DELTA_TIME": "0.0001",
            "TIME_ITERATIONS": "720",
            "WINDOW_STEPS": "100",
            "CLOCK_MOTION": "LIFT_L1",
        }
    )
    plan = reduction_windows(case)
    assert plan is not None
    said = plan["rotors"]["PUSHER"]["phase_locked"]["skipped"]
    assert "PUSHER" in said, said
    assert "skipped" not in plan["rotors"]["LIFT_L1"]["phase_locked"], "the lifter went with it"


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


def test_the_phase_locked_passages_of_each_rotor_start_at_the_rows_window():
    """THE HALF NOTHING ASSERTED, and a mutant lived in it.

    A mutant cutting each rotor's phase-locked passages from STEP ONE
    instead of from the row's export window survived the whole suite (the
    QA lens, 2026-09-10). That is the requirement's own defect sentence
    for the phase-locked half: the file is written, the columns are
    right, and the average is over the wrong window.
    """
    plan = reduction_windows(transition_case())
    assert plan is not None
    opens = plan["time_average"]["windows"][0][0]
    for alias in ("LIFT_L1", "PUSHER"):
        entry = plan["rotors"][alias]["phase_locked"]
        windows, period = entry["windows"], entry["period_steps"]
        assert windows[0][0] == opens, (alias, "the passages do not start at the row's window")
        for first, last in windows:
            assert last - first + 1 == period, (alias, "a passage is not one blade passage")
        for earlier, later in zip(windows, windows[1:], strict=False):
            assert later[0] == earlier[1] + 1, (alias, "the passages are not contiguous")


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
    assert "<point>_<reduction>_<alias>.csv" in said, (
        "the skip does not say what the files are called. The PRODUCTS stage "
        "rewrites this sentence with the real names, because it knows the point "
        "stem and this layer does not; that is asserted in test_post_products.py."
    )


def test_a_row_turning_one_rotor_takes_the_count_from_that_rotors_block():
    """FR-68's own sentence: the reference already states it.

    A row naming ONE rotor by alias has said how many blades it has, so
    it needs no `BLADES` of its own. Its reductions are under `rotors`
    like any other row that names its rotors, which is the uniform rule
    the interface lens asked for on 2026-09-10: gating the rotor's name on
    there being SEVERAL made the rotor COUNT a file-naming input, so the
    day a second rotor is added every script pointing at the flat file
    stops finding its input.
    """
    case = transition_case(
        motions=[{"MOVING_BC_ALIAS": "LIFT_L1", "RPM": "2200"}],
        variables={
            "WORKFLOW": "unsteady_rotor",
            "VELOCITY": "30.0",
            "DELTA_TIME": "0.0001",
            "TIME_ITERATIONS": "720",
            # REQUIRED SINCE 0.15.0 on a row naming its rotors by alias.
            "CLOCK_MOTION": "LIFT_L1",
        },
    )
    plan = reduction_windows(case)
    assert plan is not None
    assert plan["blades"] == 4, "the row states no BLADES and its rotor declares four"
    assert plan["rotors"]["LIFT_L1"]["blades"] == 4
    assert "skipped" not in plan["rotors"]["LIFT_L1"]["per_blade"]
    assert "rotors" in plan["per_blade"]["skipped"], plan["per_blade"]


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
            "CLOCK_MOTION": "LIFT_L1",
        },
    )
    plan = reduction_windows(case)
    assert plan is not None
    assert plan["blades"] == 4
    assert plan["rotors"]["LIFT_L1"]["blades"] == 4


@pytest.mark.parametrize("recipe", ["steady", "unsteady"])
def test_a_row_with_no_rotor_carries_no_per_rotor_block(recipe):
    """A row that states no motion reduces as today, which is FR-68's own sentence."""
    case = transition_case(recipe=recipe, motions=[])
    plan = reduction_windows(case)
    if plan is None:
        return  # steady rows carry no history at all
    assert "rotors" not in plan


def test_the_documented_record_reader_example_runs():
    """The example on `docs/workspace-and-workflows.md`, RUN.

    A consumer reading a run record's reductions should not hard-code
    either `rotors` or the pair of per-rotor reduction names, and the page
    shows how; executing it is what keeps the page from rotting into a lie,
    and it is what the docs arm of GOAL-014 asks for.
    """
    from pyflightstream.cases.workflows import PER_ROTOR_REDUCTIONS, ROTORS_KEY

    plan = reduction_windows(transition_case())
    assert plan is not None
    per_rotor = plan.get(ROTORS_KEY, {})
    assert set(per_rotor) == {"LIFT_L1", "PUSHER"}
    for alias, block in per_rotor.items():
        for reduction in PER_ROTOR_REDUCTIONS:
            entry = block[reduction]
            assert "windows" in entry or "skipped" in entry, (alias, reduction, entry)
    assert "time_average" not in PER_ROTOR_REDUCTIONS, (
        "the time average is one window of the whole point, whatever turns in it"
    )
