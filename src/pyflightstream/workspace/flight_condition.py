"""Resolving a flight condition into one flow state (PFS-2027.02, .04).

Pipeline role: the workspace layer, beside :func:`resolve_matrix`, which
is where a matrix row is bound to the input library. It sits here and
not on the floor with :mod:`pyflightstream._atmosphere` because
resolution is not pure: it needs the exception catalog and it needs the
REFERENCE LENGTH, which lives in the reference artifact a row names. The
physics can be checked against published tables with no case and no
matrix; the resolution can be checked against a trivial atmosphere. In
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
IMPLIED pressure is not sea level's. For a panel method that is
harmless: density scales forces, viscosity sets Reynolds, and nothing
reads pressure. It stops being harmless the moment a consumer reads that
state as an altitude, which is why :attr:`ResolvedCondition.density_source`
exists and why the run record carries the inputs as written.

WHY A REYNOLDS CONSTRAINT NEEDS THE REFERENCE (PFS-2027.04). A Reynolds
number is meaningless without a length, and the dependency is not
academic: the same ``MACH:0.20, REmi:5.5`` against a unit chord gives a
density about 18 percent above sea level, and against a rotor's mean
face length gives nearly eight times sea level, at an implied pressure
near 794 kPa. Same inputs, same resolver, a state that is ordinary or
absurd depending on a number that comes from somewhere else entirely. So
a condition carrying ``REmi`` on a row carrying no reference is REFUSED
naming both, the length actually used is recorded beside the resolved
state, and the resolver runs AFTER reference resolution.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pyflightstream._atmosphere import feet_to_metres, isa
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
        The set is under-determined, over-determined, or states a
        Reynolds number with no reference length to measure it against.

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
    atmosphere = isa(feet_to_metres(altitude_ft), delta_isa_c=delta_isa_c)

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
                "not bookkeeping: the same Reynolds number against a unit chord and "
                "against a rotor's mean face length gives densities that differ by "
                "nearly a factor of eight."
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
        mach=mach,
        altitude_ft=altitude_ft,
        delta_isa_c=delta_isa_c,
        density_source=density_source,
        reynolds=reynolds,
        reference_length_m=reference_length_m,
        stated=dict(stated),
    )
