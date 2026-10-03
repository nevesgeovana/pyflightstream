"""Build a matrix row's sweep and refuse repeated point names before model validation."""

from __future__ import annotations

from pyflightstream.cases import SweepAxis
from pyflightstream.cases.naming import POINT_AXIS_KEYS, name_field
from pyflightstream.cases.workflows import SWEEP_WORD

#: The CLOSED set of flight-condition keys, each with the unit it is
#: written in and the quantity it constrains (PFS-2027.01).
#:
#: A flight condition is a SET OF CONSTRAINTS on one flow state, and the
#: keys given decide which quantity is solved for. That sentence is the
#: whole design: the same resolver answers ``MACH:0.20, REmi:5.5`` and
#: ``TASmps:68.08, ALTFT:10000, dISA:5`` by solving for a different
#: unknown each time. This table is the vocabulary; the resolving lives
#: one layer up, where a row can reach the reference artifact.
#:
#: WHY THE SET IS CLOSED. An unrecognised key is REFUSED here rather
#: than ignored, which is the difference between a typo that costs a
#: message and a typo that costs a campaign. Extending it later costs
#: one row in this table and no rewrite, which is why the first cut can
#: be narrow without being a trap.
#:
#: THE UNITS RIDE THE KEYS rather than the values, which is why the
#: names are not plain words: ``ALTFT`` is feet, ``dISA`` is Celsius and
#: ``REmi`` is millions. A cell that said ``ALTITUDE:10000`` would be
#: ambiguous between feet and metres in a repository that has already
#: shipped a solver command whose metres argument three builds read as
#: feet.
FLIGHT_CONDITION_KEYS: dict[str, tuple[str, str]] = {
    "MACH": (
        "dimensionless",
        "velocity, through the speed of sound at the state's own temperature",
    ),
    "TASmps": ("m/s", "velocity directly"),
    # The second element is the quantity the key CONSTRAINS, which for
    # REmi is the density alone. It read "density, velocity and reference
    # length over viscosity" until a release review pointed out that this
    # is the DEFINITION of a Reynolds number rather than a constraint, and
    # that read as a constraint list it says REmi pins three things.
    "REmi": ("millions", "density"),
    "ALTFT": ("feet", "pressure, and temperature through the standard lapse"),
    "dISA": ("Celsius, a DELTA", "temperature, as an offset on the standard value"),
    # THE FIVE PINS (FR-54, PFS-2030.02). Each overrides the constant the
    # standard atmosphere would otherwise supply, so a row can state the
    # fluid the reference scripts pinned and the emitted FLUID_PROPERTIES
    # block carries those numbers and no others. The units ride the keys.
    "RHOkgm3": ("kg/m^3", "density directly, overriding both the atmosphere and REmi"),
    "MUPas": ("Pa s", "dynamic viscosity, which REmi then solves the density against"),
    "ASMPS": ("m/s", "sonic velocity, which MACH is then taken against"),
    "TK": ("kelvin", "temperature, stated rather than lapsed"),
    "PPA": ("pascal", "pressure, stated rather than lapsed"),
}

#: THE ATTITUDE KEYS (FR-69, the rule of 2026-09-10), which the same cell
#: carries and which are NOT part of the flow state: they fix where the
#: aircraft points, not what the air is doing, so they are parsed here and
#: never handed to the atmosphere resolver. A row states both on every
#: row, so that no run reaches the solver at an angle nobody wrote; the
#: swept one carries the word `sweep` and the other a number.
#:
#: ADVANCE_RATIO joins them (FR-70): stated here it governs every motion
#: of the row that states no speed of its own.
ATTITUDE_KEYS: dict[str, tuple[str, str]] = {
    "ALPHA": ("degrees", "the incidence of the free stream"),
    "BETA": ("degrees", "the sideslip of the free stream"),
    "ADVANCE_RATIO": ("dimensionless", "the speed of every motion that states none"),
    # RPM JOINS THEM AT 0.21.0, on the cluster feedback of 2026-09-15: a rotor
    # study varies the SPEED and holds the flow, and the speed had no home in
    # the cell at all -- it could only be written on a motion record, where it
    # cannot be swept and where every motion of the row needs its own copy.
    # Stated here it reaches every motion that states none, exactly as the
    # advance ratio does, and a MOTIONS record naming a speed still wins.
    "RPM": (
        "rev/min",
        "the speed of every motion that states none, a magnitude: the sense is "
        "the reference's rpm_sign",
    ),
    # THE BODY RATES (0.21.0, the cluster feedback of 2026-09-15). One of
    # them, non-zero, turns the free stream about the moment reference point
    # of the row's REF: it is how a run states a pull-up, a roll or a yaw
    # rather than a straight flight. Flight-mechanics signs, deg/s.
    "roll_rate": ("deg/s", "the roll rate of the aircraft, about the REF's MRP"),
    "pitch_rate": ("deg/s", "the pitch rate of the aircraft, about the REF's MRP"),
    "yaw_rate": ("deg/s", "the yaw rate of the aircraft, about the REF's MRP"),
}

_HELD_POINT_KEYS = ("ALPHA", "BETA")


def _condition_sweep_axes() -> dict[str, str]:
    """Read the matrix vocabulary into the package's point axes."""
    return {
        cell_key: axis
        for axis, cell_key in POINT_AXIS_KEYS.items()
        if cell_key in FLIGHT_CONDITION_KEYS or cell_key in ATTITUDE_KEYS
    }


def refuse_repeated_names(
    pol: str, values_text: str, axis: str, held: dict[str, float], *, error: type[ValueError]
) -> None:
    """Refuse two values that share the name precision, keeping their original text."""
    seen: dict[str, tuple[int, str]] = {}
    for j, token in enumerate(values_text.split(","), 1):
        b = token.strip()
        if not b:
            continue
        point = {**held, axis: float(b)}
        name = "".join(
            name_field(POINT_AXIS_KEYS[key], point[key]) for key in POINT_AXIS_KEYS if key in point
        )
        if name in seen:
            i, a = seen[name]
            raise error(
                f"POL {pol}: SWEEP_VALUES repeats {a} (position {i}) and {b} (position {j}): "
                f"both write the name {name}, so they would share one run_id and one "
                "datapoint folder; remove the repeat, or separate the values by 0.1 degree "
                "for an angle or 0.01 for an advance ratio."
            )
        seen[name] = (j, b)


def _sweep_of_condition(
    condition: dict[str, float | str],
    sweep_values: str,
    pol: str,
    *,
    error: type[ValueError],
) -> SweepAxis:
    """Build the row's sweep from the key of its condition that carries the word (FR-69).

    PRIVATE for the same reason as ``_split_attitude`` above, and it is
    the one that mattered: it took three POSITIONAL parameters of which
    two were adjacent strings with no unit between them, so swapping them
    was legal and produced a ValueError from ``float`` rather than a
    matrix refusal. It is a seam, called once, from the loop that builds
    a row (the interface and architecture lenses, 2026-09-10).

    The rule of 2026-09-10: a sweep is applied to a variable that DEFINES
    the flight condition, and to exactly ONE variable. The cell says which
    by carrying ``sweep`` where that key's value would be, and
    ``SWEEP_VALUES`` holds the values.

    A row with no swept key, or with two, is refused naming the keys: the
    first would run one point under a column of values nobody reads, and
    the second is the paired sweep this release retires.
    """
    axes = _condition_sweep_axes()
    swept = [key for key, value in condition.items() if value == SWEEP_WORD]
    if not swept:
        raise error(
            f"POL {pol}: no key of FLIGHT_CONDITION carries the word {SWEEP_WORD!r}, so "
            "nothing says which variable this row varies, and SWEEP_VALUES would be a "
            f"column nobody reads. Write {SWEEP_WORD} as the value of the one key that "
            "varies, for example 'MACH:0.2, REmi:5.5, ALPHA:sweep, BETA:0'."
        )
    if len(swept) > 1:
        raise error(
            f"POL {pol}: {len(swept)} keys of FLIGHT_CONDITION carry the word "
            f"{SWEEP_WORD!r} ({', '.join(swept)}), and a row sweeps ONE variable. Two "
            "swept variables were the paired AL/BE sweep, which this release retires: "
            "write one row per value of the second."
        )
    key = swept[0]
    axis = axes.get(key)
    if axis is None:
        raise error(
            f"POL {pol}: FLIGHT_CONDITION sweeps {key}, which this release cannot vary "
            f"yet. The keys it varies are {', '.join(sorted(axes))}. "
            "Every other key of the cell may carry the word in a later release; today "
            "it is refused rather than accepted and ignored."
        )
    values = [float(token) for token in sweep_values.split(",") if token.strip()]
    if not values:
        raise error(
            f"POL {pol}: FLIGHT_CONDITION sweeps {key} and SWEEP_VALUES holds "
            f"{sweep_values!r}, which is no values at all. Write them there, "
            "comma-separated, for example '0.0,2.0,4.0'. A cell of only separators or "
            "only spaces holds none, which is why this can look wrong to the eye."
        )
    # A HELD ANGLE IS PART OF THE POINT, which is what keeps the upgrade
    # from renaming a run: `AL/BE` over `-4,0,4/0` tagged its points
    # `a-04.0_b+00.0`, and the same row spelled `ALPHA:sweep, BETA:0.0`
    # tags them the same way. The reasoning is on `SweepAxis.held`.
    held = {
        axes[name]: float(value)
        for name, value in condition.items()
        if name in _HELD_POINT_KEYS and value != SWEEP_WORD
    }
    refuse_repeated_names(pol, sweep_values, axis, held, error=error)
    return SweepAxis.model_validate({"type": axis, "values": values, "held": held})
