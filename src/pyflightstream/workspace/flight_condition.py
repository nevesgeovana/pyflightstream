"""Resolving a flight condition into one flow state (PFS-2027.02, .04).

Pipeline role: the workspace layer, beside :func:`resolve_matrix`, which
is where a matrix row is bound to the input library.

WHY IT IS HERE, stated as what it actually is rather than as an import
dependency. An architect pass found the earlier wording of this
paragraph unsupportable: it claimed the module could not descend to the
floor because it needs the exception catalog and the reference artifact,
and NEITHER is true of the code. This module's whole package import
surface is :mod:`pyflightstream._atmosphere` and
:mod:`pyflightstream._errors`, which is byte for byte a floor module's
surface; the reference length arrives as a plain float parameter and
this module never reaches an artifact; and the exception runs the other
way, since :class:`FlightConditionError` is DEFINED here and the public
catalog imports it FROM here.

The real reason is CALL-SITE DISCIPLINE, which is a weaker claim and the
true one. The resolver is placed with its only caller, downstream of
reference binding, so that no layer below the workspace can resolve a
Reynolds constraint before a reference exists to measure it against.
That guarantee is structural rather than asserted: a caller in a lower
layer cannot import this module at all. Moving the resolver to the floor
would be defensible on imports and would give up exactly that.

The physics/resolution split is a separate and independent argument, and
it stands: the physics can be checked against published tables with no
case and no matrix, and the resolution against a trivial atmosphere. In
one module neither half is testable on its own.

THE WHOLE DESIGN, in one sentence. A flight condition is a SET OF
CONSTRAINTS on one flow state, and the keys given decide WHICH QUANTITY
IS SOLVED FOR. It is not a record with optional fields and it is not a
lookup: the same resolver answers ``MACH:0.20, REmi:5.5`` and
``TASmps:68.08, ALTFT:10000, dISA:5`` by solving for a different unknown
each time.

WHAT EACH KEY DOES TO THE STATE:

* ``ALTFT`` and ``dISA`` fix TEMPERATURE, and therefore the speed of
  sound and the viscosity. Both have defaults, sea level and zero, and
  those defaults are what make a short constraint set legal at all.
* ``MACH`` or ``TASmps`` fixes VELOCITY. Exactly one of them, always:
  none leaves the state under-determined, both is a contradiction the
  resolver refuses rather than silently preferring one.
* ``REmi`` fixes DENSITY, by solving the Reynolds definition for it. If
  it is absent, density is the atmosphere's own value at the stated
  altitude, and the Reynolds number becomes an OUTCOME instead.

THE SOLVED-DENSITY STATE IS NOT A POINT IN ANY ATMOSPHERE, and that is
the design rather than a defect. Holding Mach and Reynolds together at a
fixed temperature is what a wind tunnel does and what a validation case
needs. With ``MACH:0.20, REmi:5.5`` against a one-metre reference the
solved density is about 1.446 kg/m3 against a sea-level 1.225, so the
IMPLIED pressure is not sea level's. For a panel method that is expected
to be harmless: density scales forces, viscosity sets Reynolds, and
nothing in this package reads the pressure.

BUT THE PACKAGE WRITES IT, and that is worth stating beside the claim
rather than leaving the claim to be read as a guarantee.
``pressure_pa`` below carries the ATMOSPHERE's pressure on both
branches, so on the solved branch the emitted fluid state carries a
solved density beside an unsolved pressure and temperature: the three
are not a consistent triple. Whether the solver re-derives anything from
that argument is a question about the solver rather than about this
package, and it is open, recorded for the domain-expert seat because
settling it needs a licensed run.

It stops being harmless the moment a consumer reads that
state as an altitude, which is why :attr:`ResolvedCondition.density_source`
exists, and why the run record carries both it and the inputs as
written, in ``density_source`` and ``flight_condition``.

WHY A REYNOLDS CONSTRAINT NEEDS THE REFERENCE (PFS-2027.04). A Reynolds
number is meaningless without a length, and the dependency is not
academic: the same ``MACH:0.20, REmi:5.5`` against a unit chord gives a
density about 18 percent above sea level, and against a rotor's mean
face length of about 0.15 m gives nearly eight times sea level, at an
implied pressure near 797 kPa. Both figures are computed at sea level
from the constants in ``_atmosphere``; the ratio BETWEEN those two
states is neither of those numbers, it is the ratio of the two lengths,
because on this branch density is inversely proportional to the length
and to nothing else. Same inputs, same resolver, a state that is ordinary or
absurd depending on a number that comes from somewhere else entirely. So
a condition carrying ``REmi`` on a row carrying no reference is REFUSED
naming both, the length actually used is recorded beside the resolved
state, and the resolver runs AFTER reference resolution.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from pyflightstream._atmosphere import (
    ISA,
    METRES_PER_FOOT,
    AtmosphereError,
    feet_to_metres,
    isa,
)
from pyflightstream._errors import PyflightstreamError

#: The keys that fix velocity. Exactly one is required, always.
VELOCITY_KEYS = ("MACH", "TASmps")

#: The key that fixes density by solving the Reynolds definition.
DENSITY_KEY = "REmi"


class FlightConditionError(PyflightstreamError, ValueError):
    """A flight condition does not determine exactly one flow state.

    Catalogued (SRS FR-39) rather than a bare :class:`ValueError`, and
    raised BEFORE any script is emitted and before any solver exists,
    which is the whole point of stating a condition declaratively.
    """


@dataclass(frozen=True)
class ResolvedCondition:
    """Hold one flow state, and enough of its provenance to recompute it.

    Every field carries its unit in its name. ``stated`` is the
    condition AS WRITTEN, kept so a reader can recompute the resolution
    rather than trust it (PFS-2027.05).
    """

    velocity_m_per_s: float
    density_kg_m3: float
    temperature_k: float
    viscosity_pa_s: float
    pressure_pa: float
    sonic_velocity_m_per_s: float
    #: The ratio of specific heats the sonic velocity above was computed
    #: WITH, carried rather than restated. An emitter on a build that
    #: takes the ratio instead of the sonic velocity must emit the same
    #: gas the rest of this state was derived from; a second literal
    #: would let the two drift the moment the floor constant moved, and
    #: the two builds would then solve different gases from one case.
    heat_capacity_ratio: float
    mach: float
    altitude_ft: float
    delta_isa_c: float
    #: Which branch produced the density, and it is not decoration: it is
    #: what stops a later reader treating a solved state as an altitude.
    density_source: str
    #: Absolute Reynolds number. None when nothing determined it, which
    #: happens when no REmi was stated and the row names no reference.
    reynolds: float | None = None
    #: The length the Reynolds number is against, in metres. Recorded
    #: because the state cannot be checked without it.
    reference_length_m: float | None = None
    stated: dict[str, float] = field(default_factory=dict)


def resolve_flight_condition(
    stated: dict[str, float],
    *,
    pol: str,
    reference_length_m: float | None = None,
) -> ResolvedCondition:
    """Resolve a parsed flight condition into one flow state.

    Parameters
    ----------
    stated : dict
        The parsed condition, canonical key to value, in the units the
        keys name. An empty mapping is not resolvable and is refused;
        deciding whether a row is ALLOWED to state none belongs to the
        caller, which knows whether the workflow needs a state.
    pol : str
        The row's POL, named in every refusal so the reader knows which
        cell to edit.
    reference_length_m : float or None
        The reference length the row's REF artifact carries. Required
        only when ``REmi`` is stated, and refused-for by name when it is
        stated and this is None.

    Returns
    -------
    ResolvedCondition

    Raises
    ------
    FlightConditionError
        The set is under-determined, over-determined, states nothing at
        all, or states a Reynolds number with no reference length to
        measure it against.
    AtmosphereError
        The set is well formed and the atmosphere has no answer for it:
        an ``ALTFT`` outside the modelled range, or a ``dISA`` driving
        the temperature to or below absolute zero. Named here because a
        caller writing ``except FlightConditionError`` from this
        docstring alone would not catch a refusal the documentation
        elsewhere tells them to expect; ``except PyflightstreamError``
        catches both.

    Examples
    --------
    Her first example: no altitude, so sea-level temperature, and the
    DENSITY is what moves to meet the Reynolds number.

    >>> state = resolve_flight_condition(
    ...     {"MACH": 0.20, "REmi": 5.5}, pol="P1", reference_length_m=1.0
    ... )
    >>> round(state.velocity_m_per_s, 4)
    68.0588
    >>> state.density_source
    'solved-from-reynolds'

    Her second: an atmosphere point, with Reynolds derived.

    >>> point = resolve_flight_condition(
    ...     {"TASmps": 68.08, "ALTFT": 10000, "dISA": 5},
    ...     pol="P1",
    ...     reference_length_m=1.0,
    ... )
    >>> round(point.mach, 4)
    0.2054
    >>> point.density_source
    'atmosphere'
    """
    if not stated:
        raise FlightConditionError(
            f"POL {pol} states no flight condition, so there is no flow state to "
            f"resolve. State one in FLIGHT_CONDITION, for example "
            f"'MACH:0.20, REmi:5.5' or 'TASmps:68.08, ALTFT:10000, dISA:5'."
        )

    given_velocity = [key for key in VELOCITY_KEYS if key in stated]
    if not given_velocity:
        raise FlightConditionError(
            f"the flight condition of POL {pol} determines no VELOCITY, so the flow "
            f"state is under-determined. State exactly one of "
            f"{' or '.join(VELOCITY_KEYS)}: MACH is dimensionless and is taken "
            f"against the speed of sound at the state's own temperature, TASmps is "
            f"true airspeed in metres per second."
        )
    if len(given_velocity) > 1:
        raise FlightConditionError(
            f"the flight condition of POL {pol} states both "
            f"{' and '.join(f'{key}:{stated[key]}' for key in given_velocity)}, and "
            "each fixes the velocity on its own, so the two together are a "
            "contradiction rather than more information. Preferring one silently "
            "would solve a condition nobody asked for; state one and delete the "
            "other."
        )

    altitude_ft = stated.get("ALTFT", 0.0)
    delta_isa_c = stated.get("dISA", 0.0)
    # The floor speaks metres, because the model is defined in metres,
    # and the user wrote feet. Re-raise here rather than letting the
    # floor's message reach a matrix user unchanged: this is the layer
    # that still knows the POL and the unit the cell was written in, and
    # a release whose whole premise is that a unit must not be lost
    # cannot answer an ALTFT in metres and name no cell.
    altitude_m = feet_to_metres(altitude_ft)
    if not ISA.floor_altitude_m <= altitude_m <= ISA.ceiling_altitude_m:
        # Answered in FEET, because feet is what the cell says. The range
        # is stated in both units so the reader can check the conversion
        # rather than take it.
        # ROUNDED INWARD, both ends. A round-two review found this
        # printing -6562 ft and 65617 ft, which are -2000.1 m and
        # 20000.06 m: both OUTSIDE the model, so a reader who retyped the
        # bound the message gave them met the same refusal. A range in a
        # refusal is an instruction, and every value in it has to resolve.
        floor_ft = math.ceil(ISA.floor_altitude_m / METRES_PER_FOOT)
        ceiling_ft = math.floor(ISA.ceiling_altitude_m / METRES_PER_FOOT)
        raise AtmosphereError(
            f"the flight condition of POL {pol} states ALTFT:{altitude_ft:g}, "
            "which is outside the range this atmosphere models: "
            f"{floor_ft} ft to {ceiling_ft} ft "
            f"({ISA.floor_altitude_m:g} m to {ISA.ceiling_altitude_m:g} m). "
            "ISO 2533 continues above that ceiling with layers this package "
            "does not implement, and extrapolating past it would be wrong in a "
            "way you could not see."
        )
    try:
        atmosphere = isa(altitude_m, delta_isa_c=delta_isa_c)
    except AtmosphereError as refused:
        # Anything else the atmosphere refuses, most reachably a dISA
        # that drives the temperature to absolute zero. Named with the
        # cell that caused it and NOT with the altitude range, which is
        # not the cause here.
        raise AtmosphereError(
            f"the flight condition of POL {pol} states ALTFT:{altitude_ft:g} "
            f"with dISA:{delta_isa_c:g}, which the atmosphere refuses. "
            f"{refused}"
        ) from refused

    if "MACH" in stated:
        velocity = stated["MACH"] * atmosphere.sonic_velocity_m_per_s
    else:
        velocity = stated["TASmps"]
    mach = velocity / atmosphere.sonic_velocity_m_per_s

    reynolds: float | None
    if DENSITY_KEY in stated:
        if reference_length_m is None:
            raise FlightConditionError(
                f"the flight condition of POL {pol} states "
                f"{DENSITY_KEY}:{stated[DENSITY_KEY]}, and a Reynolds number is "
                "meaningless without the reference LENGTH it is measured against, "
                "which lives in the reference artifact the row's REF cell names. "
                "That row names no reference. Give it one, or state the condition "
                "without a Reynolds number and let it be derived. The dependency is "
                "not bookkeeping: on this branch density is inversely proportional "
                "to the length and to nothing else, so the same Reynolds number "
                "against a unit chord and against a rotor's mean face length of "
                "about 0.15 m gives densities differing by the ratio of the two "
                "lengths, near a factor of seven."
            )
        reynolds = stated[DENSITY_KEY] * 1e6
        density = reynolds * atmosphere.viscosity_pa_s / (velocity * reference_length_m)
        density_source = "solved-from-reynolds"
    else:
        density = atmosphere.density_kg_m3
        density_source = "atmosphere"
        reynolds = (
            None
            if reference_length_m is None
            else density * velocity * reference_length_m / atmosphere.viscosity_pa_s
        )

    return ResolvedCondition(
        velocity_m_per_s=velocity,
        density_kg_m3=density,
        temperature_k=atmosphere.temperature_k,
        viscosity_pa_s=atmosphere.viscosity_pa_s,
        pressure_pa=atmosphere.pressure_pa,
        sonic_velocity_m_per_s=atmosphere.sonic_velocity_m_per_s,
        heat_capacity_ratio=ISA.heat_capacity_ratio,
        mach=mach,
        altitude_ft=altitude_ft,
        delta_isa_c=delta_isa_c,
        density_source=density_source,
        reynolds=reynolds,
        reference_length_m=reference_length_m,
        stated=dict(stated),
    )
