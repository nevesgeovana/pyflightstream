"""P0400-TKPIN (PFS-2081.23) and P0400-PTRIPLE (PFS-2104.050): one consistent gas state.

A ``TK`` pin is the state's temperature, so the speed of sound, the Sutherland
viscosity, the Mach conversion and the density follow it, exactly as they
follow a ``dISA``. A solved or pinned density is emitted beside the pressure
``p = rho R T`` of that density at the state's temperature, unless ``PPA``
pins it; an unconstrained density is the ideal-gas density of the pressure
and temperature. Unpinned states keep the atmosphere's values to the bit.
"""

from __future__ import annotations

import math

import pytest

from pyflightstream._atmosphere import ISA, isa, sutherland_viscosity
from pyflightstream.workspace import flight_condition
from pyflightstream.workspace.flight_condition import resolve_flight_condition

R = ISA.gas_constant_j_per_kg_k
GAMMA = ISA.heat_capacity_ratio


def _triple_holds(state) -> bool:
    return state.pressure_pa == pytest.approx(
        state.density_kg_m3 * R * state.temperature_k, rel=1e-12
    )


def test_p0400_tkpin_sound_speed_viscosity_and_density_follow_the_pinned_temperature():
    """P0400-TKPIN: TK=400 moves a, mu, the Mach conversion and rho; the pressure stays."""
    state = resolve_flight_condition({"MACH": 0.2, "TK": 400.0}, pol="P1", reference_length_m=1.0)
    sea = isa()
    assert state.temperature_k == 400.0
    assert state.sonic_velocity_m_per_s == pytest.approx(math.sqrt(GAMMA * R * 400.0), rel=1e-12)
    assert state.viscosity_pa_s == pytest.approx(sutherland_viscosity(400.0), rel=1e-12)
    assert state.velocity_m_per_s == pytest.approx(0.2 * math.sqrt(GAMMA * R * 400.0), rel=1e-12)
    assert state.mach == pytest.approx(0.2, rel=1e-12)
    assert state.pressure_pa == sea.pressure_pa
    assert state.density_kg_m3 == pytest.approx(sea.pressure_pa / (R * 400.0), rel=1e-12)
    assert state.reynolds == pytest.approx(
        state.density_kg_m3 * state.velocity_m_per_s * 1.0 / state.viscosity_pa_s, rel=1e-12
    )
    assert _triple_holds(state)


def test_p0400_tkpin_its_own_pins_still_replace_what_the_temperature_would_give():
    """P0400-TKPIN: ASMPS and MUPas pins beside TK are emitted as written."""
    state = resolve_flight_condition(
        {"TASmps": 50.0, "TK": 400.0, "ASMPS": 340.29, "MUPas": 1.789e-5}, pol="P1"
    )
    assert state.sonic_velocity_m_per_s == 340.29
    assert state.viscosity_pa_s == 1.789e-5
    assert state.mach == pytest.approx(50.0 / 340.29, rel=1e-12)


def test_p0400_tkpin_an_unpinned_state_is_the_atmosphere_to_the_bit():
    """P0400-TKPIN: with nothing pinned the resolved state equals isa() exactly."""
    state = resolve_flight_condition({"MACH": 0.3, "ALTFT": 10000, "dISA": 5}, pol="P1")
    air = isa(10000 * 0.3048, delta_isa_c=5)
    assert state.temperature_k == air.temperature_k
    assert state.sonic_velocity_m_per_s == air.sonic_velocity_m_per_s
    assert state.viscosity_pa_s == air.viscosity_pa_s
    assert state.density_kg_m3 == air.density_kg_m3
    assert state.pressure_pa == air.pressure_pa


def test_p0400_ptriple_a_solved_density_carries_its_own_pressure():
    """P0400-PTRIPLE: REmi solves rho and the emitted pressure is rho R T, not sea level's."""
    state = resolve_flight_condition({"MACH": 0.2, "REmi": 5.5}, pol="P1", reference_length_m=1.0)
    assert state.density_source == "solved-from-reynolds"
    assert state.density_kg_m3 == pytest.approx(1.446, abs=5e-4)
    assert state.pressure_pa == pytest.approx(119.6e3, rel=1e-3)
    assert _triple_holds(state)


def test_p0400_ptriple_a_pinned_density_carries_its_own_pressure():
    """P0400-PTRIPLE: RHOkgm3 alone gives p = rho R T at the state's temperature."""
    state = resolve_flight_condition({"MACH": 0.2, "RHOkgm3": 1.0, "TK": 300.0}, pol="P1")
    assert state.pressure_pa == pytest.approx(1.0 * R * 300.0, rel=1e-12)
    assert _triple_holds(state)


def test_p0400_ptriple_a_pinned_pressure_sets_the_density_and_pins_stay_as_written():
    """P0400-PTRIPLE: PPA alone sets rho = p / (R T); PPA beside a solved rho is kept."""
    alone = resolve_flight_condition({"MACH": 0.2, "PPA": 80000.0}, pol="P1")
    assert alone.pressure_pa == 80000.0
    assert alone.density_kg_m3 == pytest.approx(80000.0 / (R * isa().temperature_k), rel=1e-12)
    assert _triple_holds(alone)
    pinned = resolve_flight_condition(
        {"MACH": 0.2, "REmi": 5.5, "PPA": 90000.0}, pol="P1", reference_length_m=1.0
    )
    assert pinned.pressure_pa == 90000.0


def test_p0400_ptriple_the_module_no_longer_admits_an_inconsistent_triple():
    """P0400-PTRIPLE: the public docstring states the consistent triple, not an open question."""
    doc = " ".join((flight_condition.__doc__ or "").split())
    assert "not a consistent triple" not in doc
    assert "p = rho R T" in doc
