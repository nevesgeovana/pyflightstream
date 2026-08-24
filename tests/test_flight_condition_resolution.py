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

import pytest

from pyflightstream._atmosphere import ISA, isa
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
    # And it prices the mistake rather than merely forbidding it.
    assert "eight" in message


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
