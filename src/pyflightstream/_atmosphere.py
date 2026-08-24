"""The standard atmosphere, below every layer (PFS-2027.03).

Pipeline role: a FLOOR rather than a stage. It imports nothing from this
package except the base exception, and several layers need it. Nothing
flows THROUGH it, which is the distinction :mod:`pyflightstream.overview`
draws between the two shapes; :mod:`pyflightstream._errors` is the other
module of this kind and the precedent this one follows.

WHY IT IS NOT IN ``utils``. That was asked directly, and the answer is
the package's own declared architecture rather than a preference.
``utils`` is a SIDE BRANCH in the layer table, "maintainer tooling
outside the pipeline", and nothing in the pipeline imports it. Putting
the atmosphere there would create the first pipeline-to-``utils``
dependency, in the one module family whose position in the layer rule is
undefined, and would answer that open question by accident in the
direction nobody argued for.

WHY IT IS SEPARATE FROM THE RESOLUTION THAT USES IT. The split is the
design and it pays for itself in testing. The physics here can be
checked against published ISA tables with no case, no matrix and no
script. The resolution of a flight condition -- deciding which unknown
the given keys leave, refusing an under- or over-determined set, and
reaching the reference artifact for a length -- is PIPELINE work: it
needs the exception catalog and the reference, so it does not descend
here. In one module neither half is testable on its own.

WHAT THIS MODULE DOES NOT DO. It does not emit. The script layer's
``helpers.atmosphere`` is the emitter and stays one: it writes
``AIR_ALTITUDE`` or the explicit fluid properties and computes nothing.
It cannot serve this feature for two reasons, and they are not equally
well evidenced, so they are stated separately.

THE FIRST IS A FACT ABOUT THE GRAMMAR. ``AIR_ALTITUDE`` has no argument
for an ISA deviation. So any condition carrying ``dISA`` must be emitted
as explicit fluid properties computed on this side, and so must the
solved-density path, which is not an atmosphere point at all. That one
needs no probe: it is the command's own signature.

THE SECOND IS WEAKER THAN AN EARLIER VERSION OF THIS DOCSTRING SAID, and
the correction is worth keeping. ``AIR_ALTITUDE`` is recorded ``broken``
on three supported builds, 26.100, 26.101 and 26.120. That count is
exact. What those three rows RECORD is only that the command ran and the
expected density was not observed. **Only 26.120 has a reading behind
it** -- 1.056 against the 0.736 expected, the 5000-foot standard state,
seen twice on build 7012026 (RPT-014). On 26.100 and 26.101 the probe
recorded absence and nothing more.

This docstring previously said all three read their metres argument as
feet, and cited the compat evidence for it. The evidence refuses that:
``commands/boundary_conditions.yaml`` says in its own notes that the
"reads ignored" sentence is the probe spec's STATIC ``effect_note``
rather than a per-run reading, and proves it by pointing out that the
same sentence appears in 26.121's row under outcome ``verified``.
Whether those builds read every altitude in feet is an open question
about three solvers and needs the density read back on 26.100 and 26.101
as well.

What survives is still enough to decide the design, which is why the
conclusion did not move: a command that is ``broken`` on three of nine
registered builds is refused by the emitter unless a caller passes
``allow_broken``, and on 25.000 it takes a bare value read in FEET. So
computing here and emitting explicit properties is the more robust route
across the supported range. That argument rests on the recorded STATUS,
which is committed and dated, and not on a mechanism nobody measured.

THE CONVENTION THAT IS WORTH WRITING DOWN. An ISA deviation moves
temperature and leaves PRESSURE alone, so density follows from the
offset temperature at the unchanged pressure altitude. That is the
standard reading of "ISA+5". The other reading, shifting pressure too,
is what a reader who has not met the convention will assume, which is
why it is stated here and asserted in ``tests/test_atmosphere.py``
rather than left to be inferred from the arithmetic.

``delta_isa_c`` is a DELTA in Celsius, and a temperature difference in
Celsius and in Kelvin is the same number. So no conversion exists here
to get wrong, and its absence is deliberate rather than an omission.

SOURCE OF THE CONSTANTS, cited rather than recalled. The atmosphere is
ISO 2533:1975, published identically as ICAO Doc 7488/3, whose defining
constants are reproduced in :data:`ISA` below. The viscosity law is
Sutherland's, with the air coefficients of White, *Viscous Fluid Flow*,
3rd ed., eq. (1-36). Every constant this module uses is in one of those
two places and none is a number someone remembered.

WHAT THIS DOES NOT CLAIM. The model is the standard atmosphere, not the
weather: it says what ISA defines at a pressure altitude, and nothing
about any particular day. Above the ceiling in :data:`ISA` it refuses
rather than extrapolating, because ISO 2533 continues with further
layers this module does not implement and a silent extrapolation would
be wrong in a way no caller could see.
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
    """Hold the defining constants of ISO 2533:1975, in one citable object.

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
    #: The top of what this module models, m. ISO 2533 continues above
    #: it with layers this module does not implement, so the ceiling is
    #: a refusal boundary rather than the end of the standard.
    ceiling_altitude_m: float = 20000.0
    #: The bottom, m. ISO 2533 is defined from -2000 m.
    floor_altitude_m: float = -2000.0


#: The single instance every function here reads.
ISA: Final = IsaConstants()

#: Sutherland's law for air: White, *Viscous Fluid Flow*, 3rd ed.,
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
            "ISO 2533 continues above that ceiling with layers this module "
            "does not implement, and extrapolating past it would be wrong in "
            "a way the caller could not see."
        )
    exponent = ISA.gravity_m_per_s2 / (ISA.lapse_rate_k_per_m * ISA.gas_constant_j_per_kg_k)
    if altitude_m <= ISA.tropopause_altitude_m:
        temperature = ISA.sea_level_temperature_k - ISA.lapse_rate_k_per_m * altitude_m
        return ISA.sea_level_pressure_pa * (temperature / ISA.sea_level_temperature_k) ** exponent
    tropopause_pressure = ISA.sea_level_pressure_pa * (
        ISA.tropopause_temperature_k / ISA.sea_level_temperature_k
    ) ** exponent
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
