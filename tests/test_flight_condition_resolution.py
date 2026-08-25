"""Tier 1: a constraint set resolves to one flow state, or is refused.

PFS-2027.02 and PFS-2027.04. Runs without the solver and without a
licence: refusing an under-determined set is exactly the check that must
happen BEFORE a script is emitted and before a solver exists, which is
the whole reason a condition is declarative.

THE TWO WORKED EXAMPLES ARE THE AUTHOR'S OWN, and they are asserted
against the numbers the specification derived independently, before any
of this code existed, rather than against whatever this implementation
happens to produce. That is
the difference between a regression test and a verification: the second
can fail on the day the code is wrong.
"""

from __future__ import annotations

import re

import pytest
from pydantic import ValidationError

from pyflightstream._atmosphere import ISA, AtmosphereError, isa
from pyflightstream.exceptions import FlightConditionError, PyflightstreamError
from pyflightstream.workspace.flight_condition import (
    DENSITY_KEY,
    VELOCITY_KEYS,
    resolve_flight_condition,
)

#: Agreement required against the independently derived figures. Loose
#: enough to absorb the brief's own rounding (it quotes the gas constant
#: as 287.053 where ISO 2533 defines 287.05287), tight enough that a
#: wrong constant or a wrong branch cannot pass.
TOLERANCE = 1e-4


def test_her_first_example_solves_for_density_at_sea_level_temperature():
    """MACH with REmi and no altitude: the DENSITY is what moves.

    Every figure here was derived in the specification of this feature
    before any of this code existed, so the assertion checks the physics
    rather than snapshotting the implementation.
    """
    state = resolve_flight_condition({"MACH": 0.20, "REmi": 5.5}, pol="P1", reference_length_m=1.0)
    assert state.temperature_k == pytest.approx(288.150, rel=TOLERANCE)
    assert state.sonic_velocity_m_per_s == pytest.approx(340.294, rel=TOLERANCE)
    assert state.velocity_m_per_s == pytest.approx(68.0588, rel=TOLERANCE)
    assert state.viscosity_pa_s == pytest.approx(1.7894e-05, rel=1e-3)
    assert state.density_kg_m3 == pytest.approx(1.446, rel=1e-3)
    assert state.density_source == "solved-from-reynolds"
    assert state.reynolds == pytest.approx(5.5e6)
    assert state.reference_length_m == 1.0


def test_the_solved_state_is_not_a_point_in_any_atmosphere():
    """The design decision, asserted so nobody 'fixes' it into an altitude.

    Holding Mach and Reynolds together at a fixed temperature is what a
    wind tunnel does. The implied pressure is then NOT the pressure at
    any altitude: it is near 119.6 kPa against a sea-level 101.325 kPa.
    """
    state = resolve_flight_condition({"MACH": 0.20, "REmi": 5.5}, pol="P1", reference_length_m=1.0)
    implied = state.density_kg_m3 * ISA.gas_constant_j_per_kg_k * state.temperature_k
    assert implied == pytest.approx(119_600, rel=1e-3)
    assert implied > ISA.sea_level_pressure_pa
    # The state deliberately does NOT agree with the standard atmosphere
    # it borrowed its temperature from.
    assert state.density_kg_m3 > isa().density_kg_m3
    # And it says so about itself, which is what stops the misreading.
    assert state.density_source == "solved-from-reynolds"


def test_her_second_example_is_an_atmosphere_point_with_reynolds_derived():
    """TASmps with ALTFT and dISA: Reynolds is the OUTCOME."""
    state = resolve_flight_condition(
        {"TASmps": 68.08, "ALTFT": 10000, "dISA": 5}, pol="P1", reference_length_m=1.0
    )
    assert state.temperature_k == pytest.approx(273.338, rel=TOLERANCE)
    assert state.pressure_pa == pytest.approx(69681.6, rel=TOLERANCE)
    assert state.density_kg_m3 == pytest.approx(0.88809, rel=TOLERANCE)
    assert state.sonic_velocity_m_per_s == pytest.approx(331.432, rel=TOLERANCE)
    assert state.mach == pytest.approx(0.2054, rel=1e-3)
    assert state.density_source == "atmosphere"
    assert state.reynolds is not None


def test_her_two_examples_are_not_the_same_condition():
    """Measured, and flagged to the author rather than assumed away.

    The two examples are nearly the same speed and NOT the same Mach,
    because the sound speed at 10000 ft ISA+5 is
    lower. If they were meant to be one condition, they are not, and
    this test is what would notice a later edit quietly making them
    agree.
    """
    first = resolve_flight_condition({"MACH": 0.20, "REmi": 5.5}, pol="P1", reference_length_m=1.0)
    second = resolve_flight_condition(
        {"TASmps": 68.08, "ALTFT": 10000, "dISA": 5}, pol="P1", reference_length_m=1.0
    )
    assert first.velocity_m_per_s == pytest.approx(second.velocity_m_per_s, rel=1e-3)
    assert first.mach != pytest.approx(second.mach, rel=1e-3)
    assert abs(second.mach - first.mach) / first.mach == pytest.approx(0.027, abs=0.003)


# --- determinacy: the refusals that teach ----------------------------------


def test_a_set_with_no_velocity_key_is_refused_naming_what_would_supply_it():
    with pytest.raises(FlightConditionError) as raised:
        resolve_flight_condition({"ALTFT": 10000}, pol="P7")
    message = str(raised.value)
    assert "P7" in message
    assert "under-determined" in message
    for key in VELOCITY_KEYS:
        assert key in message, f"the refusal does not name {key} as a way to supply it"


def test_both_velocity_keys_together_are_refused_as_a_conflict():
    """Over-determined, named as a contradiction rather than resolved."""
    with pytest.raises(FlightConditionError) as raised:
        resolve_flight_condition({"MACH": 0.20, "TASmps": 68.08}, pol="P7")
    message = str(raised.value)
    assert "MACH" in message and "TASmps" in message
    assert "0.2" in message and "68.08" in message
    # The refusal must say WHY silence would be worse, not merely refuse.
    assert "silently" in message


def test_an_empty_condition_is_refused_with_an_example_to_copy():
    with pytest.raises(FlightConditionError) as raised:
        resolve_flight_condition({}, pol="P7")
    assert "MACH:0.20, REmi:5.5" in str(raised.value)


# --- the defaults, each asserted on its own --------------------------------


def test_an_absent_isa_deviation_is_zero():
    """Asserted directly rather than inherited from an example."""
    state = resolve_flight_condition({"MACH": 0.20}, pol="P1")
    assert state.delta_isa_c == 0.0
    assert state.temperature_k == pytest.approx(ISA.sea_level_temperature_k)


def test_an_absent_altitude_is_sea_level():
    """Also asserted directly, and it is what makes a short set legal."""
    state = resolve_flight_condition({"MACH": 0.20}, pol="P1")
    assert state.altitude_ft == 0.0
    assert state.pressure_pa == pytest.approx(ISA.sea_level_pressure_pa)
    assert state.density_kg_m3 == pytest.approx(isa().density_kg_m3)


def test_the_two_defaults_are_independent():
    """A deviation with no altitude, and an altitude with no deviation.

    Written because one default silently standing in for the other is
    the kind of thing a test that only ever omits BOTH cannot catch.
    """
    hot_sea_level = resolve_flight_condition({"MACH": 0.20, "dISA": 15}, pol="P1")
    assert hot_sea_level.altitude_ft == 0.0
    assert hot_sea_level.delta_isa_c == 15.0
    assert hot_sea_level.temperature_k == pytest.approx(ISA.sea_level_temperature_k + 15.0)

    standard_altitude = resolve_flight_condition({"MACH": 0.20, "ALTFT": 10000}, pol="P1")
    assert standard_altitude.delta_isa_c == 0.0
    assert standard_altitude.altitude_ft == 10000.0
    assert standard_altitude.temperature_k < ISA.sea_level_temperature_k


# --- PFS-2027.04, the reference-length coupling ----------------------------


def test_a_reynolds_constraint_with_no_reference_is_refused_naming_both():
    with pytest.raises(FlightConditionError) as raised:
        resolve_flight_condition({"MACH": 0.20, "REmi": 5.5}, pol="P7")
    message = str(raised.value)
    assert "P7" in message
    assert DENSITY_KEY in message
    assert "reference" in message.lower()
    # And it prices the mistake rather than merely forbidding it. This
    # asserted the literal word "eight" until a release review found the
    # message was pricing it WRONG: eight is the rotor state against sea
    # level, not the ratio between the two states. A test that pins a
    # magnitude WORD cannot tell a right number from a wrong one, and
    # this one held the wrong one in place. So the assertion is on the
    # MECHANISM, which is checkable, and the magnitudes are pinned
    # numerically in test_the_figures_the_prose_quotes_are_the_figures_
    # the_resolver_gives.
    assert "inversely proportional" in message
    assert "ratio of the two lengths" in message


def test_a_condition_without_a_reynolds_number_needs_no_reference():
    """The coupling is to REmi specifically, not to conditions at large."""
    state = resolve_flight_condition({"MACH": 0.20, "ALTFT": 5000}, pol="P1")
    assert state.density_source == "atmosphere"
    assert state.reference_length_m is None
    # Nothing determined a Reynolds number, and None says so rather than
    # a zero that would read as a measurement.
    assert state.reynolds is None


def test_the_reference_length_used_is_recorded_beside_the_state():
    """The state cannot be checked without it, so it is not optional."""
    state = resolve_flight_condition({"MACH": 0.20, "REmi": 5.5}, pol="P1", reference_length_m=2.5)
    assert state.reference_length_m == 2.5


def test_the_same_condition_against_two_lengths_gives_two_densities():
    """The dependency the specification prices, reproduced here.

    This is the test that makes the coupling a fact rather than a
    caution: same inputs, same resolver, densities that differ by the
    ratio of the lengths.
    """
    short = resolve_flight_condition({"MACH": 0.20, "REmi": 5.5}, pol="P1", reference_length_m=1.0)
    long = resolve_flight_condition({"MACH": 0.20, "REmi": 5.5}, pol="P1", reference_length_m=8.0)
    assert short.density_kg_m3 == pytest.approx(8.0 * long.density_kg_m3)
    assert short.velocity_m_per_s == pytest.approx(long.velocity_m_per_s)


def test_the_condition_is_kept_as_written():
    """PFS-2027.05 rests on this: a reader recomputes rather than trusts."""
    written = {"MACH": 0.20, "REmi": 5.5}
    state = resolve_flight_condition(written, pol="P1", reference_length_m=1.0)
    assert state.stated == written
    # A copy, so a later mutation of the caller's dict cannot rewrite
    # what the record says was asked for.
    written["MACH"] = 0.99
    assert state.stated["MACH"] == 0.20


def test_the_refusal_is_catalogued_rather_than_a_bare_value_error():
    assert issubclass(FlightConditionError, PyflightstreamError)
    assert issubclass(FlightConditionError, ValueError)


def test_the_figures_the_prose_quotes_are_the_figures_the_resolver_gives():
    """Every number the reference-length argument is made with, pinned.

    A release review found the argument stated with the wrong one: the
    refusal message, the CHANGELOG and a test docstring all said the two
    states "differ by nearly a factor of eight", while the ratio between
    them is the ratio of the two lengths and nothing else. Eight was the
    rotor state against SEA LEVEL, a third quantity none of those three
    sentences named, and which the page states correctly.

    Prose is where that mistake is invisible, so the four figures the
    prose quotes are asserted here and the DISTINCTION between them is
    asserted too. Recomputing them by hand is what caught it; this is
    what makes the next drift red instead.
    """
    unit = resolve_flight_condition({"MACH": 0.20, "REmi": 5.5}, pol="P1", reference_length_m=1.0)
    rotor = resolve_flight_condition({"MACH": 0.20, "REmi": 5.5}, pol="P1", reference_length_m=0.15)
    sea_level = ISA.sea_level_pressure_pa / (
        ISA.gas_constant_j_per_kg_k * ISA.sea_level_temperature_k
    )

    # "about 18 percent above sea level", against a unit chord.
    assert unit.density_kg_m3 / sea_level == pytest.approx(1.18, abs=0.005)
    # "nearly eight times sea level", against the rotor length.
    assert rotor.density_kg_m3 / sea_level == pytest.approx(7.87, abs=0.005)
    # "near 797 kPa", the implied pressure of the rotor state. Implied,
    # not carried: the resolved condition's own pressure_pa is the
    # atmosphere's, which is the whole point of the branch marker.
    implied = rotor.density_kg_m3 * ISA.gas_constant_j_per_kg_k * rotor.temperature_k
    assert implied == pytest.approx(797_000, abs=1_000)

    # And the one the review corrected: the ratio BETWEEN the two states
    # is neither of the two figures above. It is 1 / 0.15.
    assert rotor.density_kg_m3 / unit.density_kg_m3 == pytest.approx(1.0 / 0.15)
    assert rotor.density_kg_m3 / unit.density_kg_m3 == pytest.approx(6.667, abs=0.001)


def test_an_out_of_range_altitude_is_refused_in_the_unit_the_cell_was_written_in():
    """A release whose premise is that a unit must not be lost.

    The floor module works in metres and answers in metres, which is
    right for the floor and wrong for a matrix user: a review found
    `ALTFT:70000` refused as "altitude 21336.0 m is outside the range",
    naming no ALTFT, no feet, no cell and no POL, leaving the reader to
    convert back by hand to connect the message to what they typed. The
    resolver is the layer that still knows both, so it answers.
    """
    with pytest.raises(AtmosphereError) as raised:
        resolve_flight_condition({"MACH": 0.20, "ALTFT": 70000.0}, pol="P7")
    message = str(raised.value)
    assert "P7" in message
    assert "ALTFT:70000" in message
    assert "ft" in message
    # Both units, so the reader can check the conversion rather than take it.
    assert "65616 ft" in message and "20000 m" in message
    # And the metres-only phrasing the floor uses is not what reaches them.
    assert "21336" not in message


def test_the_floor_is_refused_too_not_only_the_ceiling():
    with pytest.raises(AtmosphereError) as raised:
        resolve_flight_condition({"MACH": 0.20, "ALTFT": -9000.0}, pol="P7")
    assert "ALTFT:-9000" in str(raised.value)


def test_a_refusal_that_is_not_about_the_range_does_not_quote_the_range():
    """The trailer must name the cause, not whatever is nearby.

    A first draft of the fix above appended the altitude range to EVERY
    atmosphere refusal, including one caused by a dISA driving the
    temperature below absolute zero, where the range is true and
    irrelevant and sends the reader to the wrong cell.
    """
    with pytest.raises(AtmosphereError) as raised:
        resolve_flight_condition({"MACH": 0.20, "ALTFT": 10000.0, "dISA": -400.0}, pol="P7")
    message = str(raised.value)
    assert "dISA:-400" in message
    assert "absolute zero" in message
    assert "65617 ft" not in message


def test_every_altitude_the_refusal_names_as_in_range_actually_resolves():
    """A range in a refusal is an instruction, so retyping it must work.

    A round-two review found this message printing -6562 ft and 65617 ft,
    which are -2000.1 m and 20000.06 m: BOTH outside the model. A reader
    who did the obvious thing and retyped the bound the message handed
    them met the same refusal, and the test above pinned the outward
    rounding in place by asserting the string.

    So the bounds round INWARD now, and this asserts the property rather
    than the numbers: whatever the message names as the edge of the
    range, resolving at exactly that value succeeds.
    """
    with pytest.raises(AtmosphereError) as raised:
        resolve_flight_condition({"MACH": 0.20, "ALTFT": 99999.0}, pol="P7")
    quoted = re.findall(r"(-?\d+) ft", str(raised.value))
    assert len(quoted) == 2, f"the refusal names {len(quoted)} bounds in feet, expected 2"
    for bound in quoted:
        state = resolve_flight_condition({"MACH": 0.20, "ALTFT": float(bound)}, pol="P7")
        assert state.temperature_k > 0.0, f"{bound} ft is named in range and does not resolve"

    # And the top of the range is still the tropopause, so rounding
    # inward narrowed the message rather than the model.
    top = resolve_flight_condition({"MACH": 0.20, "ALTFT": float(quoted[1])}, pol="P7")
    assert top.temperature_k == pytest.approx(216.65, abs=0.01)


def test_the_fluid_state_carries_no_second_literal_of_the_floor_constant():
    """ARCH: one resolved state in two homes must not restate a constant.

    ResolvedCondition carries the specific-heat ratio from the floor
    rather than restating it, with a comment saying why: a second
    literal lets the two drift the moment the floor constant moves, and
    the two builds would then solve different gases from one case. A
    release review found FluidState, the object a builder actually
    reads, defaulting it to a hard 1.4 anyway. Round one fixed the
    emitter side of this defect; the model default survived it, which is
    why the assertion is on the DEFAULT and not on a resolved instance.
    """
    from pyflightstream.cases import FluidState

    assert FluidState.model_fields["heat_capacity_ratio"].default == ISA.heat_capacity_ratio


def test_the_density_branch_marker_has_no_default_to_fall_back_on():
    """A provenance marker must not assert a branch nothing established."""
    from pyflightstream.cases import FluidState

    assert FluidState.model_fields["source"].is_required()
    with pytest.raises(ValidationError):
        FluidState(
            velocity_m_per_s=68.0,
            density_kg_m3=1.225,
            pressure_pa=101325.0,
            temperature_k=288.15,
            viscosity_pa_s=1.789e-05,
            sonic_velocity_m_per_s=340.3,
        )
