"""J_CLOCK and RPM_CLOCK: what the clock rotor RAN at, beside what the row requested.

MEASURED ON A REAL POLAR, 2026-09-22. An alpha sweep at a fixed RPM wrote `J` as NA in every
row -- correctly, since `J` is the ratio the ROW REQUESTED and that row requested a speed -- while
the same row carried `VINF` 61.4 and `RPM` 7585, and the reference carried the diameter. The
ratio the rotor ran at was arithmetic on values already in the row, and no column held it.

The pair is the CLOCK rotor's because a row may turn several rotors, each with its own ratio:
the one `CLOCK_MOTION` names, or the only one the row turns. The rotor table keeps `J_<alias>`
per rotor.
"""

from __future__ import annotations

import pytest

from pyflightstream._tokens import FLIGHT_CONDITION_COLUMNS
from pyflightstream.post.products import clock_rotor_facts


class _Rotor:
    def __init__(self, diameter_m: float) -> None:
        self.diameter_m = diameter_m


class _Artifact:
    def __init__(self, rotors: dict[str, _Rotor]) -> None:
        self.rotors = rotors


class _Record:
    def __init__(self, reductions: dict[str, object]) -> None:
        self.reductions = reductions


class _Row:
    def __init__(self, variables: dict[str, str]) -> None:
        self.variables = variables


def test_the_columns_sit_beside_the_ratio_the_row_requested():
    """The order is the contract: a reader finds them next to `J`, not two thousand columns away."""
    assert FLIGHT_CONDITION_COLUMNS[-3:] == ("J", "J_CLOCK", "RPM_CLOCK")


def test_the_clock_rotor_is_the_one_the_row_names():
    """With several rotors, CLOCK_MOTION decides; one rotor needs no naming."""
    record = _Record({"rotors": {"PUSHER": {"rpm": -7585.0}, "LIFT": {"rpm": 1200.0}}})
    artifact = _Artifact({"PUSHER": _Rotor(1.2), "LIFT": _Rotor(2.0)})
    facts = clock_rotor_facts(record, _Row({"CLOCK_MOTION": "PUSHER"}), artifact)
    assert facts == {"alias": "PUSHER", "rpm": -7585.0, "diameter_m": 1.2}

    one = _Record({"rotors": {"PUSHER": {"rpm": -7585.0}}})
    alone = clock_rotor_facts(one, _Row({}), _Artifact({"PUSHER": _Rotor(1.2)}))
    assert alone == {"alias": "PUSHER", "rpm": -7585.0, "diameter_m": 1.2}


def test_several_rotors_and_no_clock_name_nothing():
    """A row turning several and naming none has no clock, and no column takes one for another."""
    record = _Record({"rotors": {"PUSHER": {"rpm": -7585.0}, "LIFT": {"rpm": 1200.0}}})
    facts = clock_rotor_facts(record, _Row({}), _Artifact({"PUSHER": _Rotor(1.2)}))
    assert facts["alias"] is None
    assert facts["rpm"] is None


@pytest.mark.parametrize(
    ("rpm", "diameter", "speed", "expected"),
    [
        # her own row: 61.4 m/s at 7585 rev/min on a 1.2 m rotor
        (-7585.0, 1.2, 61.4, 61.4 / (7585.0 / 60.0 * 1.2)),
        # the hand of the rotation belongs to RPM_CLOCK, not to the ratio
        (7585.0, 1.2, 61.4, 61.4 / (7585.0 / 60.0 * 1.2)),
    ],
)
def test_the_ratio_is_the_speed_the_run_turned(rpm, diameter, speed, expected):
    """J = V / (n D), with n in rev/s and the magnitude of the speed."""
    from pyflightstream.post.products import point_condition

    class _Report:
        angle_of_attack_deg = 0.0
        sideslip_deg = 0.0
        freestream_velocity_m_s = speed
        reynolds = None
        reference_velocity_m_s = None

    class _Point:
        name = "AL-000"
        loads = _Report()
        point: dict[str, object] = {}
        state = None

    condition = point_condition(
        _Point(), mach=0.18, clock={"alias": "PUSHER", "rpm": rpm, "diameter_m": diameter}
    )
    assert condition["RPM_CLOCK"] == rpm, condition
    assert condition["J_CLOCK"] == pytest.approx(expected), condition


def test_a_row_that_records_no_rotor_states_neither():
    """Absent and not zero: a steady wing has no clock rotor, and the funnel writes NA."""
    from pyflightstream.post.products import point_condition

    class _Point:
        name = "AL-000"
        loads = None
        point: dict[str, object] = {}
        state = None

    condition = point_condition(_Point(), mach=0.18, clock={"alias": None, "rpm": None})
    assert "RPM_CLOCK" not in condition
    assert "J_CLOCK" not in condition


def test_the_clock_name_is_matched_the_way_the_planner_matches_it():
    """Both lenses, 2026-09-22: the planner folds the case and this did not.

    `cases.workflows` resolves CLOCK_MOTION against the rotors it turns with
    `alias.casefold() == clock.casefold()`, so a row writing `lift` plans
    happily and records `LIFT`. Matching exactly here published NA in both
    columns for a campaign that had named its clock perfectly well.
    """
    record = _Record({"rotors": {"LIFT": {"rpm": 1200.0}, "PUSHER": {"rpm": -7585.0}}})
    artifact = _Artifact({"LIFT": _Rotor(2.0), "PUSHER": _Rotor(1.2)})
    facts = clock_rotor_facts(record, _Row({"CLOCK_MOTION": "lift"}), artifact)
    assert facts == {"alias": "LIFT", "rpm": 1200.0, "diameter_m": 2.0}, facts
    # and the diameter is found under the reference's own spelling too
    mixed = _Artifact({"Lift": _Rotor(2.0), "PUSHER": _Rotor(1.2)})
    assert clock_rotor_facts(record, _Row({"CLOCK_MOTION": "LIFT"}), mixed)["diameter_m"] == 2.0


def test_a_record_holding_both_a_flat_speed_and_rotor_blocks_states_no_clock():
    """The architect and V&V lenses, 2026-09-22, on the same defect.

    `reduction_windows` records BOTH a flat `rpm` and per-rotor blocks, so a
    record holding both is ordinary. With two rotors and no CLOCK_MOTION the
    clock is unresolved, and the flat fallback published that speed anyway --
    one rotor's number for a row whose clock nobody could name. The page is
    explicit: both columns are NA there.
    """
    record = _Record(
        {"rpm": 2200.0, "rotors": {"LIFT": {"rpm": -2200.0}, "PUSHER": {"rpm": 900.0}}}
    )
    facts = clock_rotor_facts(record, _Row({}), _Artifact({"LIFT": _Rotor(2.0)}))
    assert facts["alias"] is None, facts
    assert facts["rpm"] is None, "a speed was published for a clock nobody identified"
    assert facts["diameter_m"] is None, facts

    # the flat field still serves a record that carries NO rotor block at all
    flat = _Record({"rpm": 2200.0})
    assert clock_rotor_facts(flat, _Row({}), _Artifact({"LIFT": _Rotor(2.0)}))["rpm"] == 2200.0


def test_a_named_clock_absent_from_the_reference_takes_no_other_rotors_diameter():
    """The architect lens: a ratio measured against another rotor's span is a wrong number.

    The clock is named and recorded, and the reference declares a DIFFERENT
    rotor. Falling back to the only declared diameter would divide this rotor's
    speed by that rotor's span and publish it as this row's ratio.
    """
    record = _Record({"rotors": {"PUSHER": {"rpm": -7585.0}}})
    facts = clock_rotor_facts(
        record, _Row({"CLOCK_MOTION": "PUSHER"}), _Artifact({"LIFT": _Rotor(2.0)})
    )
    assert facts["alias"] == "PUSHER"
    assert facts["rpm"] == -7585.0, "the speed is the record's and is known"
    assert facts["diameter_m"] is None, "another rotor's diameter was taken"
