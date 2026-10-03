"""Build a matrix row's sweep and refuse repeated point names before model validation."""

from __future__ import annotations

from pyflightstream.cases import SweepAxis
from pyflightstream.cases.naming import POINT_AXIS_KEYS, name_field
from pyflightstream.cases.workflows import SWEEP_WORD

_HELD_POINT_KEYS = ("ALPHA", "BETA")


def _condition_sweep_axes() -> dict[str, str]:
    """Read the matrix vocabulary into the package's point axes."""
    from pyflightstream.cases.matrix import ATTITUDE_KEYS, FLIGHT_CONDITION_KEYS

    return {
        cell_key: axis
        for axis, cell_key in POINT_AXIS_KEYS.items()
        if cell_key in FLIGHT_CONDITION_KEYS or cell_key in ATTITUDE_KEYS
    }


def refuse_repeated_names(pol: str, values_text: str, axis: str, held: dict[str, float]) -> None:
    """Refuse two values that share the name precision, keeping their original text."""
    from pyflightstream.cases.matrix import MatrixError

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
            raise MatrixError(
                f"POL {pol}: SWEEP_VALUES repeats {a} (position {i}) and {b} (position {j}): "
                f"both points write the name {name}, so they would share one run_id and one "
                "datapoint folder; remove the repeat, or separate the values by 0.1 degree "
                "for an angle or 0.01 for an advance ratio."
            )
        seen[name] = (j, b)


def _sweep_of_condition(
    condition: dict[str, float | str], sweep_values: str, pol: str
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
    from pyflightstream.cases.matrix import MatrixError

    axes = _condition_sweep_axes()
    swept = [key for key, value in condition.items() if value == SWEEP_WORD]
    if not swept:
        raise MatrixError(
            f"POL {pol}: no key of FLIGHT_CONDITION carries the word {SWEEP_WORD!r}, so "
            "nothing says which variable this row varies, and SWEEP_VALUES would be a "
            f"column nobody reads. Write {SWEEP_WORD} as the value of the one key that "
            "varies, for example 'MACH:0.2, REmi:5.5, ALPHA:sweep, BETA:0'."
        )
    if len(swept) > 1:
        raise MatrixError(
            f"POL {pol}: {len(swept)} keys of FLIGHT_CONDITION carry the word "
            f"{SWEEP_WORD!r} ({', '.join(swept)}), and a row sweeps ONE variable. Two "
            "swept variables were the paired AL/BE sweep, which this release retires: "
            "write one row per value of the second."
        )
    key = swept[0]
    axis = axes.get(key)
    if axis is None:
        raise MatrixError(
            f"POL {pol}: FLIGHT_CONDITION sweeps {key}, which this release cannot vary "
            f"yet. The keys it varies are {', '.join(sorted(axes))}. "
            "Every other key of the cell may carry the word in a later release; today "
            "it is refused rather than accepted and ignored."
        )
    values = [float(token) for token in sweep_values.split(",") if token.strip()]
    if not values:
        raise MatrixError(
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
    refuse_repeated_names(pol, sweep_values, axis, held)
    return SweepAxis.model_validate({"type": axis, "values": values, "held": held})
