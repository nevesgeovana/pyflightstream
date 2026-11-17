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


def _jclock582_plan(tmp_path, cell, *, workflow="unsteady", diameter=True, blocks=True):
    """Plan the documented no-turning clock example through a real matrix."""
    import warnings

    from tests.tier1_offline.test_tier3_offline import TOUR, _rendered, _tier3_copy

    root = _tier3_copy(tmp_path)
    reference = root / "inputs/references/r004.toml"
    text = reference.read_text(encoding="utf-8")
    text = text.split("[rotor]")[0] + "[PUSHER]" + text.split("[PUSHER]")[1]
    text = text.replace("rotor_diameter_m = 3.6576", "rotor_diameter_m = 2.0" if diameter else "")
    text = text.replace("diameter_m = 3.6576", "diameter_m = 7.0")
    if not blocks:
        text = text.split("[PUSHER]")[0]
    elif blocks == 2:
        text += (
            '\n[SECOND]\nkind = "rotor"\nid = 1\nx_m = 0\ny_m = 0\nz_m = 0\n'
            'axis = "X"\nrpm_sign = 1\ndiameter_m = 9\nfamilies_blades = ["Blade2"]\n'
            'blade1 = { azimuth_deg = 0.0, zero = "Y" }\n'
        )
    reference.write_text(text, encoding="utf-8")
    header, rule = TOUR.read_text(encoding="utf-8").splitlines()[:2]
    row = (
        "7582 | 0 | 1 | Rig | - | Clock | TASmps:30, REmi:2.3, ALPHA:sweep | 0 "
        f"| 40_PUSHER.fsm | r004 | s002 | p001 | NONE | - | - | - | 26.120 | {workflow} | " + cell
    )
    matrix = root / "jclock.fs"
    matrix.write_text("\n".join([header, rule, row]) + "\n", encoding="utf-8")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        plan, rendered = _rendered(root, matrix)
    return plan, rendered, [item for item in caught]


_JCLOCK582_CELL = "J_CLOCK: 1.3 / DELTA_THETA: 20 / REVOLUTIONS: 2 / LAST_REVS_AVG: 1"


@pytest.mark.requirement("P0582-JCLOCK-COMPATIBILITY")
def test_p0582_existing_power_off_advance_ratio_keeps_its_rotor_block_diameter(tmp_path):
    cell = _JCLOCK582_CELL.replace("J_CLOCK", "ADVANCE_RATIO")
    plan, rendered, _ = _jclock582_plan(tmp_path, cell)
    assert not plan.blocked and len(rendered) == 1, plan.summary()
    lines = next(iter(rendered.values())).splitlines()
    delta = next(line.split()[1] for line in lines if line.startswith("DELTA_TIME "))
    expected = 20 / (6 * round(60 * 30 / (1.3 * 7), 4))
    assert float(delta) == pytest.approx(expected, rel=1e-6)


@pytest.mark.requirement("P0582-JCLOCK-READY")
@pytest.mark.parametrize("blocks", [0, 1, 2])
@pytest.mark.parametrize(
    "clock_motion", ["", " / CLOCK_MOTION: PUSHER", " / CLOCK_MOTION: unrelated"]
)
def test_p0582_jclock_reference_clock_plans_ready(tmp_path, blocks, clock_motion):
    """n=30/(1.3*2), dt=(20/360)*1.3*2/30, regardless of rotor selection."""
    plan, rendered, _ = _jclock582_plan(tmp_path, _JCLOCK582_CELL + clock_motion, blocks=blocks)
    assert not plan.blocked, plan.summary()
    assert len(rendered) == 1
    lines = next(iter(rendered.values())).splitlines()
    assert "TIME_ITERATIONS 36" in lines
    delta = next(line.split()[1] for line in lines if line.startswith("DELTA_TIME "))
    assert float(delta) == pytest.approx((20 / 360) * 1.3 * 2 / 30, rel=1e-6)
    assert "CREATE_NEW_MOTION" not in lines


@pytest.mark.requirement("P0582-JCLOCK-REFUSALS")
@pytest.mark.parametrize("blocks", [0, 1, 2])
@pytest.mark.parametrize(
    ("extra", "key"),
    [
        (" / ADVANCE_RATIO: 1.3", "ADVANCE_RATIO"),
        (" / RPM: 800", "RPM"),
        (" / DELTA_TIME: 0.01", "DELTA_TIME"),
    ],
)
def test_p0582_jclock_two_clocks_refused(tmp_path, extra, key, blocks):
    plan, _, _ = _jclock582_plan(tmp_path, _JCLOCK582_CELL + extra, blocks=blocks)
    assert plan.blocked, plan.summary()
    assert "J_CLOCK" in plan.summary() and key in plan.summary(), plan.summary()


@pytest.mark.requirement("P0582-JCLOCK-POSITIVE")
@pytest.mark.parametrize("value", ["0", "-1", "nan", "inf", "wrong"])
def test_p0582_jclock_requires_positive_finite_value(tmp_path, value):
    plan, _, _ = _jclock582_plan(tmp_path, _JCLOCK582_CELL.replace("1.3", value))
    assert plan.blocked, plan.summary()
    assert "J_CLOCK" in plan.summary(), plan.summary()


@pytest.mark.requirement("P0582-JCLOCK-DIAMETER")
def test_p0582_jclock_missing_reference_diameter_refused_even_with_rotor_block(tmp_path):
    plan, _, _ = _jclock582_plan(tmp_path, _JCLOCK582_CELL, diameter=False)
    assert plan.blocked, plan.summary()
    assert "J_CLOCK" in plan.summary() and "rotor_diameter_m" in plan.summary(), plan.summary()


@pytest.mark.requirement("P0582-JCLOCK-TURNING")
def test_p0582_jclock_turning_row_refused(tmp_path):
    cell = _JCLOCK582_CELL + " / RPM: 800 / MOVING_BC_ALIAS: PUSHER"
    plan, _, _ = _jclock582_plan(tmp_path, cell, workflow="unsteady_rotor")
    assert plan.blocked, plan.summary()
    assert "J_CLOCK" in plan.summary() and "turn" in plan.summary(), plan.summary()


@pytest.mark.requirement("P0582-JCLOCK-STEADY")
def test_p0582_jclock_steady_row_warned_and_skipped(tmp_path):
    from pyflightstream._errors import NotApplicableWarning

    plan, rendered, caught = _jclock582_plan(tmp_path, "J_CLOCK: 1.3", workflow="steady")
    assert not plan.blocked and rendered, plan.summary()
    assert any(
        issubclass(item.category, NotApplicableWarning) and "J_CLOCK" in str(item.message)
        for item in caught
    ), [str(item.message) for item in caught]


@pytest.mark.requirement("P0582-JCLOCK-OUTPUT")
def test_p0582_jclock_record_and_product_use_the_reference_clock():
    from types import SimpleNamespace

    from pyflightstream.cases import ReferenceData
    from pyflightstream.cases.workflows import reduction_windows, unsteady_time_stepping
    from pyflightstream.post.products import point_condition
    from tests.tier1_offline.test_workflows import unsteady_case

    case = unsteady_case(
        DELTA_TIME=None,
        TIME_ITERATIONS=None,
        J_CLOCK="1.3",
        DELTA_THETA="20",
        REVOLUTIONS="2",
        LAST_ITERS_AVG=None,
        LAST_REVS_AVG="1",
        VELOCITY="30",
    )
    case = case.model_copy(update={"reference": ReferenceData(area=1, length=1, rotor_diameter=2)})
    plan = reduction_windows(case)
    assert plan is not None and plan.get("steps_per_revolution") == 18, plan
    assert plan["time_iterations"] == 36 and plan["time_average"]["windows"] == [[19, 36]]
    stepping = unsteady_time_stepping(case)
    assert stepping.delta_time_s == pytest.approx((20 / 360) * 1.3 * 2 / 30, rel=1e-14)
    artifact = SimpleNamespace(rotor_diameter_m=2, rotors={"OTHER": _Rotor(7)})
    facts = clock_rotor_facts(
        _Record(plan), _Row({"J_CLOCK": "1.3", "CLOCK_MOTION": "OTHER"}), artifact
    )
    point = SimpleNamespace(loads=None, point={"VINF": 30}, state=None)
    condition = point_condition(point, mach=0.1, clock=facts)
    assert condition["J_CLOCK"] == pytest.approx(1.3, rel=1e-14)
    assert condition["RPM_CLOCK"] == pytest.approx(60 * 30 / (1.3 * 2))


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


@pytest.mark.requirement("FR-118")
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


def test_a_flat_record_that_names_its_clock_takes_no_other_rotors_diameter():
    """The QA lens, 2026-09-22, on what the previous fix still missed.

    A flat record keeps one speed and no rotor block, so the NAME is the only
    thing that identifies the clock. Inferring the identity from the speed map
    left the alias unresolved, and the sole-reference fallback then took the
    other rotor's diameter: at VINF 60 the condition published
    J_CLOCK 0.818181... for a rotor whose span nobody stated.
    """
    from pyflightstream.post.products import point_condition

    record = _Record({"rpm": 2200.0})
    facts = clock_rotor_facts(
        record, _Row({"CLOCK_MOTION": "PUSHER"}), _Artifact({"LIFT": _Rotor(2.0)})
    )
    assert facts["alias"] == "PUSHER", facts
    assert facts["rpm"] == 2200.0, "the flat speed is this clock's, and it is known"
    assert facts["diameter_m"] is None, "another rotor's diameter was taken"

    class _Report:
        angle_of_attack_deg = 0.0
        sideslip_deg = 0.0
        freestream_velocity_m_s = 60.0
        reynolds = None
        reference_velocity_m_s = None

    class _Point:
        name = "AL-000"
        loads = _Report()
        point: dict[str, object] = {}
        state = None

    condition = point_condition(_Point(), mach=0.18, clock=facts)
    assert condition["RPM_CLOCK"] == 2200.0
    assert "J_CLOCK" not in condition, "a ratio was published against a span nobody stated"


def test_a_legacy_flat_record_keeps_the_speed_it_states():
    """The QA lens, 2026-09-22, on a regression the identity fix introduced.

    A record with NO rotor block turns one rotor, and the flat field is its
    speed -- whether or not the row names a clock and whether or not the
    reference declares exactly one rotor. Requiring a resolved alias there
    dropped a speed the record states plainly. The SPAN stays unknown, so no
    ratio is published.
    """
    from pyflightstream.post.products import point_condition

    record = _Record({"rpm": 2200.0})
    artifact = _Artifact({"LIFT": _Rotor(2.0), "PUSHER": _Rotor(1.2)})
    facts = clock_rotor_facts(record, _Row({}), artifact)
    assert facts["rpm"] == 2200.0, "a speed the record states was dropped"
    assert facts["diameter_m"] is None, "no rotor is identified, so no span is"

    class _Report:
        angle_of_attack_deg = 0.0
        sideslip_deg = 0.0
        freestream_velocity_m_s = 60.0
        reynolds = None
        reference_velocity_m_s = None

    class _Point:
        name = "AL-000"
        loads = _Report()
        point: dict[str, object] = {}
        state = None

    condition = point_condition(_Point(), mach=0.18, clock=facts)
    assert condition["RPM_CLOCK"] == 2200.0
    assert "J_CLOCK" not in condition


def test_a_legacy_flat_reference_supplies_the_span_of_its_one_rotor():
    """The fifth independent reading of GitHub main, 2026-09-23.

    A supported flat single-rotor shape: the record keeps a flat `rpm` and no
    rotor block, and the reference keeps no named rotor block but a top-level
    `rotor_diameter_m`. Both facts are stated and nothing has to be borrowed
    from another rotor, so `J_CLOCK` is a number here, not `NA`; the definitions
    page reserves `NA` for the facts the record or the reference does not supply.
    """
    from pyflightstream.post.products import point_condition

    class _FlatArtifact:
        rotors: dict[str, object] = {}
        rotor_diameter_m = 2.0

    facts = clock_rotor_facts(_Record({"rpm": 2200.0}), _Row({}), _FlatArtifact())
    assert facts["rpm"] == 2200.0
    assert facts["diameter_m"] == 2.0, "the one rotor's span was left unread"

    class _Report:
        angle_of_attack_deg = 0.0
        sideslip_deg = 0.0
        freestream_velocity_m_s = 60.0
        reynolds = None
        reference_velocity_m_s = None

    class _Point:
        name = "AL-000"
        loads = _Report()
        point: dict[str, object] = {}
        state = None

    condition = point_condition(_Point(), mach=0.18, clock=facts)
    assert condition["RPM_CLOCK"] == 2200.0
    assert abs(condition["J_CLOCK"] - 60.0 / (2200.0 / 60.0 * 2.0)) < 1e-9, condition["J_CLOCK"]


def test_a_flat_reference_beside_several_declared_rotors_lends_no_span():
    """The flat diameter answers for ONE rotor; with named blocks it says nothing."""

    class _MixedArtifact:
        rotors = {"LIFT": _Rotor(2.0), "PUSHER": _Rotor(1.2)}
        rotor_diameter_m = 2.0

    facts = clock_rotor_facts(_Record({"rpm": 2200.0}), _Row({}), _MixedArtifact())
    assert facts["diameter_m"] is None, "a span was borrowed for a rotor nobody identified"
