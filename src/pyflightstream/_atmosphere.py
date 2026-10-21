"""The standard atmosphere, below every pipeline layer (PFS-2027.03).

This module computes atmospheric properties and imports only the package's
base exception. Flight-condition resolution belongs to workspace, where a
reference is available for Reynolds constraints. The script layer emits
AIR_ALTITUDE or explicit fluid properties; this module emits no commands.

AIR_ALTITUDE has no ISA-deviation argument. Conditions carrying dISA and
conditions solved from density therefore need explicit fluid properties.
The command is recorded broken on builds 26.100, 26.101 and 26.120. Only the
26.120 evidence quantifies the discrepancy: density 1.056 against 0.736
expected, consistent with the 5000-foot rather than 5000-metre standard state
(RPT-014, build 7012026). On 26.100 and 26.101 the probe records absence of
the expected effect, not its cause. A static effect_note is not a per-run
reading. The emitter refuses a broken command unless allow_broken is set;
on 25.000 AIR_ALTITUDE takes a bare value in feet. Explicit properties avoid
these build-dependent command limitations.

An ISA deviation changes temperature at unchanged pressure altitude and
pressure. Density follows from the offset temperature. delta_isa_c is a
temperature difference, with the same numerical value in Celsius and Kelvin.
The model describes the standard atmosphere, not local weather, and refuses
altitudes outside ISA's modeled layers instead of extrapolating.

Atmosphere constants follow ISO 2533:1975, also published as ICAO Doc 7488/3
[REF-01]. Sutherland's viscosity law uses the air coefficients attributed to
White, Viscous Fluid Flow, third edition, equation (1-36) [REF-02].
METRES_PER_FOOT is the exact defining value of the international foot.

The viscosity attribution has an unresolved limitation: the cited book is
not available in this repository. The implemented reference temperature and
Sutherland constant are 273.15 K and 110.4 K. A 273 K / 111 K triplet commonly
attributed to the equation gives different results: about 0.0492 percent
at sea level, 0.0536 percent at 300 K and 0.0164 percent at the tropopause.
The difference propagates into density solved on the REmi path. Resolving
which triplet belongs to the cited equation requires the source.

The atmosphere tests pin viscosity with rel=1e-4 at three temperatures.
The alternative triplet differs by 1.64e-4 at 216.65 K, 3.59e-4 at 255.65 K
and 5.36e-4 at 300 K, exceeding that tolerance at all three points.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final

from pyflightstream._errors import PyflightstreamError


class AtmosphereError(PyflightstreamError, ValueError):
    """An atmosphere was asked for outside the range this module models.

    Catalogued (SRS FR-39) rather than a bare :class:`ValueError`, so a
    caller can tell a refusal of this package's from one of Python's.
    """


@dataclass(frozen=True)
class IsaConstants:
    """Hold the defining constants of ISO 2533:1975 [REF-01], in one citable object.

    Held as data rather than as module-level names so that a test can
    read the values it is checking out of the same object the physics
    uses. A test that restates a constant proves the restatement.
    """

    #: Sea-level temperature, K.
    sea_level_temperature_k: float = 288.15
    #: Sea-level pressure, Pa.
    sea_level_pressure_pa: float = 101325.0
    #: Specific gas constant of dry air, J/(kg K).
    gas_constant_j_per_kg_k: float = 287.05287
    #: Ratio of specific heats of dry air, dimensionless.
    heat_capacity_ratio: float = 1.4
    #: Standard gravity, m/s2.
    gravity_m_per_s2: float = 9.80665
    #: Troposphere temperature lapse rate, K/m (a DECREASE with height).
    lapse_rate_k_per_m: float = 0.0065
    #: Geopotential height of the tropopause, m.
    tropopause_altitude_m: float = 11000.0
    #: Temperature of the isothermal layer above the tropopause, K.
    tropopause_temperature_k: float = 216.65
    #: The top of what this module models, m. ISO 2533 continues above [REF-01]
    #: it with layers this module does not implement, so the ceiling is
    #: a refusal boundary rather than the end of the standard.
    ceiling_altitude_m: float = 20000.0
    #: The bottom, m. ISO 2533 is defined from -2000 m. [REF-01]
    floor_altitude_m: float = -2000.0


#: The single instance every function here reads.
ISA: Final = IsaConstants()

#: Sutherland's law for air: White, *Viscous Fluid Flow*, 3rd ed., [REF-02]
#: eq. (1-36). The reference viscosity is at the reference temperature,
#: and S is the Sutherland constant of air.
SUTHERLAND_REFERENCE_VISCOSITY_PA_S: Final = 1.716e-5
SUTHERLAND_REFERENCE_TEMPERATURE_K: Final = 273.15
SUTHERLAND_CONSTANT_K: Final = 110.4

#: Exactly, by definition of the international foot.
METRES_PER_FOOT: Final = 0.3048


@dataclass(frozen=True)
class AtmosphereState:
    """Hold one fully determined air state.

    Every field carries its unit in its name, which is this
    repository's rule rather than this module's habit.
    """

    temperature_k: float
    pressure_pa: float
    density_kg_m3: float
    sonic_velocity_m_per_s: float
    viscosity_pa_s: float


def feet_to_metres(altitude_ft: float) -> float:
    """Convert an altitude in feet to metres.

    Here rather than at the caller because ``ALTFT`` is the interface
    unit a flight condition is written in and metres are the unit this
    module works in, so the conversion belongs at the boundary between
    them and should exist exactly once.
    """
    return altitude_ft * METRES_PER_FOOT


def sutherland_viscosity(temperature_k: float) -> float:
    """Dynamic viscosity of air at ``temperature_k``, in Pa s."""
    if temperature_k <= 0.0:
        raise AtmosphereError(
            f"temperature {temperature_k} K is not above absolute zero, so "
            "Sutherland's law has no value there"
        )
    ratio = temperature_k / SUTHERLAND_REFERENCE_TEMPERATURE_K
    return (
        SUTHERLAND_REFERENCE_VISCOSITY_PA_S
        * ratio**1.5
        * (SUTHERLAND_REFERENCE_TEMPERATURE_K + SUTHERLAND_CONSTANT_K)
        / (temperature_k + SUTHERLAND_CONSTANT_K)
    )


def speed_of_sound(temperature_k: float) -> float:
    """Speed of sound in dry air at ``temperature_k``, in m/s."""
    if temperature_k <= 0.0:
        raise AtmosphereError(
            f"temperature {temperature_k} K is not above absolute zero, so the "
            "speed of sound has no value there"
        )
    return math.sqrt(ISA.heat_capacity_ratio * ISA.gas_constant_j_per_kg_k * temperature_k)


def density(pressure_pa: float, temperature_k: float) -> float:
    """Density of dry air from the ideal gas law, in kg/m3."""
    if temperature_k <= 0.0:
        raise AtmosphereError(
            f"temperature {temperature_k} K is not above absolute zero, so the "
            "ideal gas law has no density there"
        )
    return pressure_pa / (ISA.gas_constant_j_per_kg_k * temperature_k)


def standard_pressure(altitude_m: float) -> float:
    """ISA pressure at a geopotential altitude, in Pa.

    An ISA deviation does NOT appear here, and that is the convention
    this module exists to make explicit: a deviation moves temperature
    and leaves the pressure at a pressure altitude alone.
    """
    if not ISA.floor_altitude_m <= altitude_m <= ISA.ceiling_altitude_m:
        raise AtmosphereError(
            f"altitude {altitude_m} m is outside the range this atmosphere "
            f"models, {ISA.floor_altitude_m} m to {ISA.ceiling_altitude_m} m. "
            "ISO 2533 continues above that ceiling with layers this module [REF-01] "
            "does not implement, and extrapolating past it would be wrong in "
            "a way the caller could not see."
        )
    exponent = ISA.gravity_m_per_s2 / (ISA.lapse_rate_k_per_m * ISA.gas_constant_j_per_kg_k)
    if altitude_m <= ISA.tropopause_altitude_m:
        temperature = ISA.sea_level_temperature_k - ISA.lapse_rate_k_per_m * altitude_m
        return ISA.sea_level_pressure_pa * (temperature / ISA.sea_level_temperature_k) ** exponent
    tropopause_pressure = (
        ISA.sea_level_pressure_pa
        * (ISA.tropopause_temperature_k / ISA.sea_level_temperature_k) ** exponent
    )
    height_above = altitude_m - ISA.tropopause_altitude_m
    return tropopause_pressure * math.exp(
        -ISA.gravity_m_per_s2
        * height_above
        / (ISA.gas_constant_j_per_kg_k * ISA.tropopause_temperature_k)
    )


def standard_temperature(altitude_m: float) -> float:
    """ISA temperature at a geopotential altitude, in K, with no deviation."""
    if not ISA.floor_altitude_m <= altitude_m <= ISA.ceiling_altitude_m:
        raise AtmosphereError(
            f"altitude {altitude_m} m is outside the range this atmosphere "
            f"models, {ISA.floor_altitude_m} m to {ISA.ceiling_altitude_m} m"
        )
    if altitude_m <= ISA.tropopause_altitude_m:
        return ISA.sea_level_temperature_k - ISA.lapse_rate_k_per_m * altitude_m
    return ISA.tropopause_temperature_k


def isa(altitude_m: float = 0.0, *, delta_isa_c: float = 0.0) -> AtmosphereState:
    """Return the air state at a pressure altitude, with an optional ISA deviation.

    Parameters
    ----------
    altitude_m:
        Geopotential pressure altitude in metres. Defaults to sea level,
        which is what an absent altitude means in a flight condition.
    delta_isa_c:
        Temperature offset from the standard value, in Celsius, applied
        as a DELTA. Defaults to 0. Pressure is unaffected by it; see the
        module docstring.

    Examples
    --------
    >>> state = isa()
    >>> round(state.temperature_k, 2)
    288.15
    >>> round(state.sonic_velocity_m_per_s, 3)
    340.294

    An ISA deviation moves temperature and density and leaves pressure
    exactly where it was:

    >>> hot = isa(0.0, delta_isa_c=15.0)
    >>> hot.pressure_pa == state.pressure_pa
    True
    >>> hot.density_kg_m3 < state.density_kg_m3
    True
    """
    pressure = standard_pressure(altitude_m)
    temperature = standard_temperature(altitude_m) + delta_isa_c
    if not math.isfinite(temperature):
        raise AtmosphereError(
            f"an ISA deviation of {delta_isa_c} C at {altitude_m} m gives a non-finite "
            f"temperature ({temperature}); the deviation must be a finite number"
        )
    if temperature <= 0.0:
        raise AtmosphereError(
            f"an ISA deviation of {delta_isa_c} C at {altitude_m} m puts the "
            f"temperature at {temperature} K, which is not above absolute zero"
        )
    return AtmosphereState(
        temperature_k=temperature,
        pressure_pa=pressure,
        density_kg_m3=density(pressure, temperature),
        sonic_velocity_m_per_s=speed_of_sound(temperature),
        viscosity_pa_s=sutherland_viscosity(temperature),
    )
